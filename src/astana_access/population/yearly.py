import json

import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.accessibility.coverage import facilities, origin_destination
from astana_access.accessibility.e2sfca import load_inputs, supply_measures
from astana_access.accessibility.network import load
from astana_access.config import CRS_METRIC, PROCESSED, REPORTS
from astana_access.equity.analysis import BASE
from astana_access.ingest import stat_ages
from astana_access.population.projection import POOLED_NAME
from astana_access.validation.uncertainty import RADIUS_M, FastIndex, dwelling_table

YEARS = (2026, 2027, 2028, 2029)
MEASURES = ("school", "preschool")


def group_of(district: pd.Series) -> pd.Series:
    return district.where(~district.isin(stat_ages.POOLED), POOLED_NAME)


def factors(report: dict, year: int, measure: str) -> pd.DataFrame:
    rows = {}
    for group in report["groups"]:
        base = report["observed"][group]["2026"][measure]
        ageing = report["projection"]["ageing"][group][str(year)][measure]
        trend = report["projection"]["trend"][group][str(year)][measure]
        rows[group] = {
            "factor": min(ageing, trend) / base,
            "increment": max(trend - ageing, 0.0),
        }
    return pd.DataFrame(rows).T


def housing_points() -> pd.DataFrame:
    forecast = pd.read_parquet(PROCESSED / "housing_forecast.parquet")
    forecast = forecast[forecast["predicted_2026_2029"] > 0].copy()
    grid = gpd.read_file(PROCESSED / "grid_population.gpkg")[["h3", "geometry"]].to_crs(CRS_METRIC)
    centre = grid.set_index("h3").geometry.centroid.reindex(forecast["h3"])
    forecast["group"] = group_of(forecast["district"].fillna("none"))
    total = forecast.groupby("group")["predicted_2026_2029"].transform("sum")
    return pd.DataFrame(
        {
            "point_id": "n" + forecast["h3"].to_numpy(),
            "h3": forecast["h3"].to_numpy(),
            "x": centre.x.to_numpy(),
            "y": centre.y.to_numpy(),
            "group": forecast["group"].to_numpy(),
            "share": (forecast["predicted_2026_2029"] / total).fillna(0).to_numpy(),
        }
    )


def cell_means(cells: np.ndarray, access: np.ndarray, weight: np.ndarray) -> pd.Series:
    frame = pd.DataFrame({"h3": cells, "aw": access * weight, "w": weight})
    grouped = frame.groupby("h3")[["aw", "w"]].sum()
    mean = grouped["aw"].sum() / grouped["w"].sum()
    return (grouped["aw"] / grouped["w"].replace(0, np.nan) / mean).where(grouped["w"] > 0)


def run() -> dict:
    report = json.loads((REPORTS / "demography_2030.json").read_text(encoding="utf-8"))
    points, od = load_inputs()
    dwellings = dwelling_table(points)
    new = housing_points()
    sites = facilities()
    network = load()
    od_new = {
        kind: origin_destination(network, new, sites[kind], "facility_id") for kind in MEASURES
    }
    ids = pd.Index(list(dwellings["point_id"]) + list(new["point_id"]))
    cells = np.concatenate(
        [
            points.set_index("point_id")["h3"].reindex(dwellings["point_id"]).to_numpy(),
            new["h3"].to_numpy(),
        ]
    )
    groups = np.concatenate([group_of(dwellings["unit"]).to_numpy(), new["group"].to_numpy()])
    supplies = supply_measures()
    index = {
        kind: FastIndex(
            pd.concat([od[kind], od_new[kind]], ignore_index=True),
            ids,
            supplies[kind][BASE[kind]["supply"]],
            BASE[kind]["d0"],
            BASE[kind]["d0_load"],
        )
        for kind in MEASURES
    }
    school_od = pd.concat([od["school"], od_new["school"]], ignore_index=True)
    nearest = school_od.groupby("point_id")["distance_m"].min().reindex(ids).fillna(np.inf)
    uncovered = nearest.to_numpy() > RADIUS_M
    n_old = len(dwellings)
    rows, totals = [], {}
    for year in YEARS:
        children = {}
        for measure in MEASURES:
            base = (dwellings["pop_station"] * dwellings[f"{measure}_share"]).to_numpy()
            table = factors(report, year, measure)
            old = base * pd.Series(groups[:n_old]).map(table["factor"]).fillna(1.0).to_numpy()
            added = (
                new["share"].to_numpy()
                * pd.Series(new["group"]).map(table["increment"]).fillna(0.0).to_numpy()
            )
            children[measure] = np.concatenate([old, added])
        frame = (
            pd.DataFrame(
                {
                    "h3": cells,
                    "school_children": children["school"],
                    "preschool_children": children["preschool"],
                    "uncovered_1000": children["school"] * uncovered,
                }
            )
            .groupby("h3")
            .sum()
        )
        for measure in MEASURES:
            access = index[measure](children[measure])
            frame[f"{measure}_access"] = cell_means(cells, access, children[measure]).reindex(
                frame.index
            )
        frame["year"] = year
        rows.append(frame.reset_index())
        totals[str(year)] = {
            "school_children": float(children["school"].sum()),
            "preschool_children": float(children["preschool"].sum()),
            "uncovered_1000": float((children["school"] * uncovered).sum()),
        }
    table = pd.concat(rows, ignore_index=True)
    table.to_parquet(PROCESSED / "yearly_cells.parquet")
    result = {"years": list(YEARS), "totals": totals, "new_housing_points": int(len(new))}
    (REPORTS / "yearly_cells.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))

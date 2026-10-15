import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.accessibility.coverage import facilities, origin_destination
from astana_access.accessibility.e2sfca import load_inputs
from astana_access.accessibility.network import load
from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW, REPORTS, SEED
from astana_access.optimization import realistic
from astana_access.optimization.backtest import candidates, covered
from astana_access.optimization.plan import by_district, reach_sum
from astana_access.optimization.programme import auc_with_interval, paired_difference

SOURCE = RAW / "team" / "team_2026-10-15" / "astana_gis_education_buildings.csv"
SCHOOL = "Школа"
EXISTING_M = 150.0
RADII_M = (1000, 1500)
DEMAND_COLUMN = "school_station"
PLAN_SITES = 17
PLAN_CAPACITY = 3365.0
SEATS = re.compile(r"на\s*(\d[\d\s]*)\s*(?:учащ|обуч|уч-ся|мест)", re.I)


def seats(text: str) -> float:
    found = SEATS.search(str(text))
    return float(found.group(1).replace(" ", "")) if found else np.nan


def school_sites() -> gpd.GeoDataFrame:
    table = pd.read_csv(SOURCE, sep=";", dtype=str, encoding="utf-8-sig")
    table = table[table["Категория по тексту"] == SCHOOL].copy()
    frame = gpd.GeoDataFrame(
        {
            "object_id": table["OBJECTID ГИС"].to_numpy(),
            "purpose": table["Назначение в ГИС"].to_numpy(),
            "seats": table["Назначение в ГИС"].map(seats).to_numpy(),
        },
        geometry=gpd.points_from_xy(
            pd.to_numeric(table["Долгота"]), pd.to_numeric(table["Широта"])
        ),
        crs=CRS_GEO,
    ).to_crs(CRS_METRIC)
    schools = facilities()["school"]
    frame["existing_gap_m"] = frame.geometry.apply(lambda p: float(schools.distance(p).min()))
    frame["planned"] = frame["existing_gap_m"] > EXISTING_M
    frame["facility_id"] = "pdp" + frame["object_id"]
    return frame


def run() -> dict | None:
    if not SOURCE.exists():
        return None
    rng = np.random.default_rng(SEED)
    sites = school_sites()
    planned = sites[sites["planned"]].copy()
    network = load()
    points, od = load_inputs()
    dwellings = points[points["kind"] == "dwelling"]
    weight = dwellings.set_index("point_id")[DEMAND_COLUMN].fillna(0)
    district = dwellings.set_index("point_id")["district"]
    od_planned = origin_destination(network, points, planned, "facility_id")
    pool = candidates(points)
    od_pool = origin_destination(network, points, pool, "facility_id")
    nearest = {
        pool.loc[pool.geometry.distance(p).idxmin(), "facility_id"] for p in planned.geometry
    }
    pool["planned"] = pool["facility_id"].isin(nearest).astype(int)
    districts = gpd.read_file(PROCESSED / "districts.gpkg", layer="districts").to_crs(CRS_METRIC)
    located = gpd.sjoin(planned, districts[["name_en", "geometry"]], how="left")
    cells = pd.read_parquet(PROCESSED / "access_cells_school.parquet")
    cold = set(cells.index[(cells["p"] < 0.05) & (cells["quadrant"] == "LL")])
    cold_points = dwellings.loc[dwellings["h3"].isin(cold), "point_id"]
    report = {
        "school_objects": int(len(sites)),
        "at_existing_school": int((~sites["planned"]).sum()),
        "planned_sites": int(len(planned)),
        "planned_seats_known": int(planned["seats"].notna().sum()),
        "planned_seats": float(planned["seats"].sum()),
        "planned_by_district": located["name_en"].value_counts().to_dict(),
        "radii": {},
    }
    for radius in RADII_M:
        before = covered(od["school"], radius)
        uncovered = weight[~weight.index.isin(before) & (weight > 0)]
        reach = od_planned[od_planned["distance_m"] <= radius]
        reached = uncovered.reindex(list(set(reach["point_id"]) & set(uncovered.index)))
        remaining = uncovered[~uncovered.index.isin(reached.index)]
        reach_pool = od_pool[od_pool["distance_m"] <= radius]
        frame = pool.set_index("facility_id")
        deficit = reach_sum(reach_pool, uncovered, frame.index).to_numpy()
        density = reach_sum(reach_pool, weight, frame.index).to_numpy()
        label = frame["planned"].to_numpy()
        unit = realistic.demand_units(points, uncovered)
        unit_weight = uncovered.groupby(unit).sum()
        units = pd.Series(unit.to_numpy(), index=uncovered.index)
        pairs = realistic.unit_pairs(od_planned, units, uncovered, radius)
        chosen, best = realistic.capacitated(pairs, unit_weight, PLAN_SITES, PLAN_CAPACITY)
        report["radii"][str(radius)] = {
            "uncovered_children": float(uncovered.sum()),
            "best_sites_among_planned": float(best),
            "best_sites_ids": chosen,
            "reached_by_planned_sites": float(reached.sum()),
            "reached_share": float(reached.sum() / uncovered.sum()),
            "uncovered_by_district": by_district(uncovered, district),
            "remaining_by_district": by_district(remaining, district),
            "selection": {
                "deficit": auc_with_interval(label, deficit, rng),
                "density": auc_with_interval(label, density, rng),
                "deficit_minus_density": paired_difference(label, deficit, density, rng),
            },
        }
    near = od_planned.loc[od_planned["distance_m"] <= 1000, "point_id"]
    report["low_low_children"] = float(weight.reindex(cold_points).sum())
    report["low_low_children_within_1km"] = float(
        weight.reindex(list(set(cold_points) & set(near))).sum()
    )
    plan_layer = gpd.read_file(PROCESSED / "backtest.gpkg", layer="plan_2026_2028").to_crs(
        CRS_METRIC
    )
    plan_new = plan_layer[plan_layer["kind"] == "new"]
    report["plan_sites_within_500m_of_a_planned_site"] = int(
        sum(planned.distance(p).min() <= 500 for p in plan_new.geometry)
    )
    report["plan_new_sites"] = int(len(plan_new))
    planned.to_crs(CRS_GEO).to_file(PROCESSED / "backtest.gpkg", layer="pdp_schools", driver="GPKG")
    (REPORTS / "detailed_plans.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False, default=float))

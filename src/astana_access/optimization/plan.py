import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.ops import nearest_points

from astana_access.accessibility.coverage import facilities, origin_destination
from astana_access.accessibility.e2sfca import index, load_inputs, supply_measures
from astana_access.accessibility.network import load
from astana_access.config import CRS_GEO, CRS_METRIC, DATA, PROCESSED, REPORTS, SEED
from astana_access.equity.analysis import BASE, summary
from astana_access.ingest import school_register
from astana_access.inventory.addresses import load_gazetteer
from astana_access.optimization import realistic
from astana_access.optimization.backtest import candidates, covered
from astana_access.optimization.programme import auc_with_interval, paired_difference
from astana_access.population.stations import LineIndex

TABLE = DATA / "labels" / "planned_schools_2026_2028.csv"
RADII_M = (1000, 1500)
YEARS = (2026, 2027, 2028)
DEMAND_COLUMN = "school_station"
CROWD_M = 1500.0
TWO_SHIFTS = 2.0


def metric_point(lon: float, lat: float) -> Point:
    return gpd.GeoSeries([Point(lon, lat)], crs=CRS_GEO).to_crs(CRS_METRIC).iloc[0]


def locate(row: pd.Series, lines: LineIndex, gazetteer, schools: gpd.GeoDataFrame) -> Point | None:
    kind = row["locate"]
    if kind == "school":
        hit = schools[schools["number"] == float(row["school_number"])]
        return hit.geometry.iloc[0] if len(hit) else None
    if kind == "point":
        return metric_point(float(row["lon"]), float(row["lat"]))
    if kind == "address":
        found = gazetteer.locate(row["address_street"], str(row["address_house"]))
        return metric_point(found.lon, found.lat) if found.lon is not None else None
    if kind == "street":
        line = lines.street(row["street_a"])
        return nearest_points(line, line.centroid)[0] if line is not None else None
    if kind == "intersection":
        first, second = lines.street(row["street_a"]), lines.street(row["street_b"])
        if first is None or second is None:
            return None
        crossing = first.intersection(second)
        if not crossing.is_empty:
            return crossing.representative_point()
        a, b = nearest_points(first, second)
        return Point((a.x + b.x) / 2, (a.y + b.y) / 2)
    return None


def plan_sites() -> gpd.GeoDataFrame:
    table = pd.read_csv(TABLE, dtype={"address_house": str})
    lines = LineIndex()
    gazetteer = load_gazetteer()
    schools = facilities(programme=False)["school"]
    points = [locate(row, lines, gazetteer, schools) for _, row in table.iterrows()]
    frame = gpd.GeoDataFrame(table, geometry=points, crs=CRS_METRIC)
    frame["facility_id"] = "plan_" + frame["plan_id"]
    number = schools.dropna(subset=["number"]).drop_duplicates("number").set_index("number")
    frame["target_id"] = frame["school_number"].map(number["facility_id"])
    return frame


def crowding_near(sites: gpd.GeoDataFrame, schools: gpd.GeoDataFrame) -> pd.DataFrame:
    register = school_register.linked().dropna(subset=["facility_id"])
    load = register.groupby("facility_id")[["enrolment_2025", "capacity"]].sum()
    positions = schools.set_index("facility_id").geometry.reindex(load.index).dropna()
    load = load.loc[positions.index]
    excess = (load["enrolment_2025"] - TWO_SHIFTS * load["capacity"]).clip(lower=0)
    rows = []
    for point in sites.geometry:
        near = positions.distance(point) <= CROWD_M
        enrolled, places = load.loc[near, "enrolment_2025"].sum(), load.loc[near, "capacity"].sum()
        rows.append(
            {
                "beyond_two_shifts": float(excess[near].sum()),
                "pupils_per_place": float(enrolled / places) if places else 0.0,
            }
        )
    return pd.DataFrame(rows, index=sites.index)


def by_district(values: pd.Series, district: pd.Series) -> dict:
    return values.groupby(district.reindex(values.index)).sum().round().to_dict()


def reach_sum(reach: pd.DataFrame, values: pd.Series, index: pd.Index) -> pd.Series:
    mapped = reach["point_id"].map(values).fillna(0)
    return mapped.groupby(reach["facility_id"]).sum().reindex(index).fillna(0)


def run() -> dict:
    rng = np.random.default_rng(SEED)
    network = load()
    points, od = load_inputs()
    dwellings = points[points["kind"] == "dwelling"]
    weight = dwellings.set_index("point_id")[DEMAND_COLUMN].fillna(0)
    district = dwellings.set_index("point_id")["district"]
    od_existing = od["school"]
    plan = plan_sites()
    located = plan[plan.geometry.notna()].copy()
    new = located[located["kind"] == "new"].copy()
    od_new = origin_destination(network, points, new, "facility_id")
    pool = candidates(points)
    od_pool = origin_destination(network, points, pool, "facility_id")
    plots = realistic.feasible_sites(points, 2026)
    od_plots = origin_destination(network, points, plots, "facility_id")
    capacity = new.set_index("facility_id")["seats"].astype(float)
    nearest_cell = [
        pool.loc[pool.geometry.distance(point).idxmin(), "facility_id"] for point in new.geometry
    ]
    pool["planned"] = pool["facility_id"].isin(set(nearest_cell)).astype(int)

    report = {
        "objects": int(len(plan)),
        "located": int(len(located)),
        "not_located": plan.loc[plan.geometry.isna(), "plan_id"].tolist(),
        "seats_by_year": plan.groupby("year")["seats"].sum().to_dict(),
        "seats_by_kind": plan.groupby("kind")["seats"].sum().to_dict(),
        "seats_by_district": plan.groupby("district")["seats"].sum().to_dict(),
        "new_sites_located": int(len(new)),
        "confidence": located["confidence"].value_counts().to_dict(),
        "school_age_children": float(weight.sum()),
        "radii": {},
    }
    for radius in RADII_M:
        before = covered(od_existing, radius)
        uncovered = weight[~weight.index.isin(before) & (weight > 0)]
        unit = realistic.demand_units(points, uncovered)
        unit_weight = uncovered.groupby(unit).sum()
        units = pd.Series(unit.to_numpy(), index=uncovered.index)
        stages = {}
        for year in YEARS:
            ids = list(new.loc[new["year"] <= year, "facility_id"])
            reach = od_new[(od_new["distance_m"] <= radius) & od_new["facility_id"].isin(ids)]
            reached_points = set(reach["point_id"]) & set(uncovered.index)
            pairs = realistic.unit_pairs(reach, units, uncovered, radius)
            capped = 0.0
            if len(pairs):
                _, capped = realistic.capacitated(
                    pairs, unit_weight, None, capacity, fixed=list(pairs["facility_id"].unique())
                )
            remaining = uncovered[~uncovered.index.isin(reached_points)]
            stages[str(year)] = {
                "sites": len(ids),
                "reached": float(uncovered.reindex(list(reached_points)).sum()),
                "reached_with_capacity": float(capped),
                "remaining_by_district": by_district(remaining, district),
            }
        k = len(new)
        pairs_cells = realistic.unit_pairs(od_pool, units, uncovered, radius)
        pairs_plots = realistic.unit_pairs(od_plots, units, uncovered, radius)
        typical = float(capacity.mean())
        _, optimal_any = realistic.capacitated(pairs_cells, unit_weight, k, typical)
        chosen, optimal_plots = realistic.capacitated(pairs_plots, unit_weight, k, typical)
        plots[plots["facility_id"].isin(chosen)].to_crs(CRS_GEO).to_file(
            PROCESSED / "backtest.gpkg", layer=f"plan_optimal_{radius}", driver="GPKG"
        )
        realised = stages[str(YEARS[-1])]["reached_with_capacity"]
        reach_pool = od_pool[od_pool["distance_m"] <= radius]
        frame = pool.set_index("facility_id")
        frame["deficit"] = reach_sum(reach_pool, uncovered, frame.index)
        frame["density"] = reach_sum(reach_pool, weight, frame.index)
        label = frame["planned"].to_numpy()
        report["radii"][str(radius)] = {
            "uncovered_children": float(uncovered.sum()),
            "uncovered_by_district": by_district(uncovered, district),
            "stages": stages,
            "optimal_any_cell": optimal_any,
            "optimal_feasible_plot": optimal_plots,
            "plan_over_optimal_any_cell": realised / optimal_any if optimal_any else None,
            "plan_over_optimal_feasible_plot": realised / optimal_plots if optimal_plots else None,
            "selection": {
                "deficit": auc_with_interval(label, frame["deficit"].to_numpy(), rng),
                "density": auc_with_interval(label, frame["density"].to_numpy(), rng),
                "deficit_minus_density": paired_difference(
                    label, frame["deficit"].to_numpy(), frame["density"].to_numpy(), rng
                ),
            },
        }

    crowd = crowding_near(pool, facilities()["school"])
    label = pool["planned"].to_numpy()
    by_site = crowding_near(new, facilities()["school"])
    by_site.index = new["plan_id"].to_numpy()
    register = school_register.linked().dropna(subset=["facility_id"])
    beyond = (register["enrolment_2025"] - TWO_SHIFTS * register["capacity"]).clip(lower=0)
    report["crowding"] = {
        "radius_m": CROWD_M,
        "selection": {
            "beyond_two_shifts": auc_with_interval(
                label, crowd["beyond_two_shifts"].to_numpy(), rng
            ),
            "pupils_per_place": auc_with_interval(label, crowd["pupils_per_place"].to_numpy(), rng),
        },
        "by_site": by_site.round(2).to_dict("index"),
        "pupils_beyond_two_shifts_by_district": beyond.groupby(register["district"])
        .sum()
        .to_dict(),
    }

    base = BASE["school"]
    supply = supply_measures()["school"][base["supply"]].copy()
    for row in located.itertuples():
        added = row.seats / TWO_SHIFTS
        if row.kind == "new":
            supply.loc[row.facility_id] = added
        elif row.kind == "extension":
            supply.loc[row.target_id] = supply.get(row.target_id, 0.0) + added
        else:
            supply.loc[row.target_id] = max(supply.get(row.target_id, 0.0), added)
    od_all = pd.concat([od_existing, od_new], ignore_index=True)
    demand = points.set_index("point_id")[DEMAND_COLUMN].fillna(0)
    settings = (base["decay"], base["d0"], base["d0_load"])
    now = index(od_existing, demand, supply_measures()["school"][base["supply"]], *settings)
    after = index(od_all, demand, supply, *settings)
    before_summary = summary(points, now, DEMAND_COLUMN)
    after_summary = summary(points, after, DEMAND_COLUMN)
    cells = pd.read_parquet(PROCESSED / "access_cells_school.parquet")
    cold = set(cells.index[(cells["p"] < 0.05) & (cells["quadrant"] == "LL")])
    cold_points = dwellings.loc[dwellings["h3"].isin(cold), "point_id"]
    reach_new = od_new[od_new["distance_m"] <= 1000]
    report["access"] = {
        "district_relative_now": before_summary["district_relative"],
        "district_relative_after_plan": after_summary["district_relative"],
        "mean_access_gain": after_summary["mean"] / before_summary["mean"] - 1,
        "gini_now": before_summary["gini"],
        "gini_after_plan": after_summary["gini"],
        "zero_access_now": before_summary["zero_access_share"],
        "zero_access_after_plan": after_summary["zero_access_share"],
        "low_low_children": float(weight.reindex(cold_points).sum()),
        "low_low_children_within_1km_of_new_school": float(
            weight.reindex(list(set(cold_points) & set(reach_new["point_id"]))).sum()
        ),
        "low_low_children_by_district": by_district(weight.reindex(cold_points), district),
    }
    located.to_crs(CRS_GEO).to_file(
        PROCESSED / "backtest.gpkg", layer="plan_2026_2028", driver="GPKG"
    )
    (REPORTS / "plan_2026_2028.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False, default=float))

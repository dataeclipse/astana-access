import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix, vstack

from astana_access.accessibility.coverage import facilities, origin_destination
from astana_access.accessibility.network import load
from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, REPORTS, SEED

PROGRAMME_FIRST_NUMBER = 99
RADII_M = (1000, 1500)
MIN_CELL_CHILDREN = 20.0
RANDOM_DRAWS = 200
DEMAND_COLUMN = "school_station"


def split_schools() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    schools = facilities()["school"]
    presumed = schools["presumed_new"].astype(bool)
    programme = presumed | (schools["number"] >= PROGRAMME_FIRST_NUMBER)
    return schools[~programme], schools[programme]


def candidates(points: pd.DataFrame) -> gpd.GeoDataFrame:
    dwellings = points[points["kind"] == "dwelling"]
    cells = dwellings.groupby("h3").agg(
        children=(DEMAND_COLUMN, "sum"),
        x=(
            "x",
            lambda v: float(np.average(v, weights=dwellings.loc[v.index, DEMAND_COLUMN] + 1e-9)),
        ),
        y=(
            "y",
            lambda v: float(np.average(v, weights=dwellings.loc[v.index, DEMAND_COLUMN] + 1e-9)),
        ),
    )
    cells = cells[cells["children"] >= MIN_CELL_CHILDREN].reset_index()
    return gpd.GeoDataFrame(
        {"facility_id": "cell" + cells["h3"], "h3": cells["h3"], "children": cells["children"]},
        geometry=gpd.points_from_xy(cells["x"], cells["y"]),
        crs=CRS_METRIC,
    )


def covered(od: pd.DataFrame, radius: float) -> set[str]:
    return set(od.loc[od["distance_m"] <= radius, "point_id"])


def solve(gain: pd.DataFrame, weight: pd.Series, k: int) -> tuple[list[str], float]:
    sites = sorted(gain["facility_id"].unique())
    demand = sorted(gain["point_id"].unique())
    site_index = {s: i for i, s in enumerate(sites)}
    point_index = {p: i for i, p in enumerate(demand)}
    n, m = len(sites), len(demand)
    rows = gain["point_id"].map(point_index).to_numpy()
    cols = gain["facility_id"].map(site_index).to_numpy()
    link = coo_matrix((-np.ones(len(gain)), (rows, cols)), shape=(m, n))
    identity = coo_matrix((np.ones(m), (np.arange(m), np.arange(m))), shape=(m, m))
    from scipy.sparse import hstack

    a_cover = hstack([link, identity])
    a_budget = coo_matrix((np.ones(n), (np.zeros(n), np.arange(n))), shape=(1, n + m))
    matrix = vstack([a_cover, a_budget]).tocsr()
    lower = np.concatenate([np.full(m, -np.inf), [k]])
    upper = np.concatenate([np.zeros(m), [k]])
    objective = np.concatenate([np.zeros(n), -weight.reindex(demand).fillna(0).to_numpy()])
    integrality = np.concatenate([np.ones(n), np.zeros(m)])
    result = milp(
        objective,
        constraints=LinearConstraint(matrix, lower, upper),
        integrality=integrality,
        bounds=Bounds(0, 1),
        options={"time_limit": 600, "mip_rel_gap": 1e-4},
    )
    chosen = [sites[i] for i in np.flatnonzero(result.x[:n] > 0.5)]
    return chosen, float(-result.fun)


def gained(gain: pd.DataFrame, weight: pd.Series, sites: list[str]) -> float:
    reached = gain.loc[gain["facility_id"].isin(sites), "point_id"].unique()
    return float(weight.reindex(reached).fillna(0).sum())


def run() -> dict:
    network = load()
    points = pd.read_parquet(PROCESSED / "demand_points.parquet")
    points = points[points["kind"] == "dwelling"].reset_index(drop=True)
    weight = points.set_index("point_id")[DEMAND_COLUMN].fillna(0)
    existing, programme = split_schools()
    od_existing = origin_destination(network, points, existing, "facility_id")
    od_programme = origin_destination(network, points, programme, "facility_id")
    pool = candidates(points)
    od_pool = origin_destination(network, points, pool, "facility_id")
    rng = np.random.default_rng(SEED)
    k = len(programme)
    report = {
        "programme_schools": int(k),
        "programme_numbered": int(programme["number"].notna().sum()),
        "programme_presumed": int(programme["presumed_new"].astype(bool).sum()),
        "existing_schools": int(len(existing)),
        "candidate_cells": int(len(pool)),
        "school_age_children": float(weight.sum()),
        "radii": {},
    }
    for radius in RADII_M:
        before = covered(od_existing, radius)
        uncovered = weight[~weight.index.isin(before)]
        gain_pool = od_pool[
            (od_pool["distance_m"] <= radius) & od_pool["point_id"].isin(uncovered.index)
        ]
        gain_programme = od_programme[
            (od_programme["distance_m"] <= radius) & od_programme["point_id"].isin(uncovered.index)
        ]
        realised = float(uncovered.reindex(gain_programme["point_id"].unique()).sum())
        chosen, optimal = solve(gain_pool, uncovered, k)
        density = pool.sort_values("children", ascending=False)["facility_id"].head(k).tolist()
        sites = pool["facility_id"].to_numpy()
        random_gains = [
            gained(gain_pool, uncovered, list(rng.choice(sites, size=k, replace=False)))
            for _ in range(RANDOM_DRAWS)
        ]
        programme_points = programme.geometry
        chosen_points = pool.set_index("facility_id").loc[chosen].geometry
        distance_to_programme = [
            float(programme_points.distance(point).min()) for point in chosen_points
        ]
        report["radii"][str(radius)] = {
            "covered_before_share": float(weight.reindex(list(before)).sum() / weight.sum()),
            "uncovered_children": float(uncovered.sum()),
            "realised_gain": realised,
            "optimal_gain": optimal,
            "density_gain": gained(gain_pool, uncovered, density),
            "random_gain_mean": float(np.mean(random_gains)),
            "random_gain_p95": float(np.percentile(random_gains, 95)),
            "realised_over_optimal": realised / optimal if optimal else 0.0,
            "optimal_sites_within_1km_of_a_programme_school": float(
                np.mean(np.array(distance_to_programme) <= 1000)
            ),
        }
        chosen_frame = pool[pool["facility_id"].isin(chosen)].to_crs(CRS_GEO)
        chosen_frame.to_file(PROCESSED / "backtest.gpkg", layer=f"optimal_{radius}", driver="GPKG")
    programme.to_crs(CRS_GEO).to_file(PROCESSED / "backtest.gpkg", layer="programme", driver="GPKG")
    (REPORTS / "backtest.json").write_text(
        json.dumps(report, indent=1, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=float))

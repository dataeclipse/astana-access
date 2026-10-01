import json

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, vstack

from astana_access import norms
from astana_access.accessibility.coverage import origin_destination
from astana_access.accessibility.network import load
from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, REPORTS
from astana_access.optimization.backtest import (
    DEMAND_COLUMN,
    RADII_M,
    candidates,
    covered,
    split_schools,
)
from astana_access.optimization.land import load_clearance, plot_sites

UNIT_RESOLUTION = 10
SEARCH_M = 600.0
DEDUPLICATE_M = 150.0
CAPACITY = norms.COMFORTABLE_SCHOOL_SEATS * norms.SHIFTS
PLOT_M2 = norms.school_land_m2(norms.COMFORTABLE_SCHOOL_SEATS)
CLEARANCE_M = float(np.sqrt(PLOT_M2 / np.pi))


def feasible_sites(points: pd.DataFrame) -> gpd.GeoDataFrame:
    cells = candidates(points)
    clearance, transform = load_clearance()
    centres = np.column_stack([cells.geometry.x, cells.geometry.y])
    sites, distance = plot_sites(centres, clearance, transform, CLEARANCE_M, SEARCH_M)
    keep = np.isfinite(distance)
    frame = pd.DataFrame(sites[keep], columns=["x", "y"])
    frame["h3"] = cells.loc[keep, "h3"].to_numpy()
    frame["shift_m"] = distance[keep]
    frame["key"] = (
        (frame["x"] // DEDUPLICATE_M).astype(int).astype(str)
        + "_"
        + (frame["y"] // DEDUPLICATE_M).astype(int).astype(str)
    )
    frame = frame.drop_duplicates("key").reset_index(drop=True)
    return gpd.GeoDataFrame(
        {
            "facility_id": "plot" + frame.index.astype(str),
            "h3": frame["h3"],
            "shift_m": frame["shift_m"],
        },
        geometry=gpd.points_from_xy(frame["x"], frame["y"]),
        crs=CRS_METRIC,
    )


def demand_units(points: pd.DataFrame, uncovered: pd.Series) -> pd.Series:
    lonlat = gpd.GeoSeries(gpd.points_from_xy(points["x"], points["y"]), crs=CRS_METRIC).to_crs(
        CRS_GEO
    )
    unit = pd.Series(
        [h3.latlng_to_cell(p.y, p.x, UNIT_RESOLUTION) for p in lonlat], index=points["point_id"]
    )
    return unit.reindex(uncovered.index)


def unit_pairs(od: pd.DataFrame, unit: pd.Series, weight: pd.Series, radius: float) -> pd.DataFrame:
    table = od[od["point_id"].isin(weight.index)].copy()
    table["unit"] = table["point_id"].map(unit)
    table["w"] = table["point_id"].map(weight)
    table["inside"] = table["distance_m"] <= radius
    grouped = table.groupby(["unit", "facility_id"]).apply(
        lambda g: g.loc[g["inside"], "w"].sum(), include_groups=False
    )
    grouped = grouped[grouped > 0].rename("reach").reset_index()
    return grouped


def capacitated(
    pairs: pd.DataFrame,
    unit_weight: pd.Series,
    k: int | None,
    capacity: float,
    fixed: list[str] | None = None,
) -> tuple[list[str], float]:
    sites = sorted(pairs["facility_id"].unique()) if fixed is None else sorted(fixed)
    pairs = pairs[pairs["facility_id"].isin(sites)].reset_index(drop=True)
    units = sorted(pairs["unit"].unique())
    site_index = {s: i for i, s in enumerate(sites)}
    unit_index = {u: i for i, u in enumerate(units)}
    n, m, p = len(sites), len(units), len(pairs)
    reach = pairs["reach"].to_numpy()
    total = unit_weight.reindex(units).to_numpy()
    rows_u = pairs["unit"].map(unit_index).to_numpy()
    cols_s = pairs["facility_id"].map(site_index).to_numpy()
    flow_cols = n + np.arange(p)
    assignment = csr_matrix((reach, (rows_u, flow_cols)), shape=(m, n + p))
    capacity_rows = csr_matrix(
        (
            np.concatenate([reach, -np.full(n, capacity)]),
            (np.concatenate([cols_s, np.arange(n)]), np.concatenate([flow_cols, np.arange(n)])),
        ),
        shape=(n, n + p),
    )
    blocks = [assignment, capacity_rows]
    lower = [np.zeros(m), np.full(n, -np.inf)]
    upper = [total, np.zeros(n)]
    if fixed is None:
        blocks.append(csr_matrix((np.ones(n), (np.zeros(n), np.arange(n))), shape=(1, n + p)))
        lower.append([k])
        upper.append([k])
    matrix = vstack(blocks).tocsr()
    objective = np.concatenate([np.zeros(n), -reach])
    bounds_low = np.zeros(n + p)
    bounds_high = np.ones(n + p)
    if fixed is not None:
        bounds_low[:n] = 1.0
    integrality = np.concatenate([np.ones(n), np.zeros(p)])
    result = milp(
        objective,
        constraints=LinearConstraint(matrix, np.concatenate(lower), np.concatenate(upper)),
        integrality=integrality,
        bounds=Bounds(bounds_low, bounds_high),
        options={"time_limit": 900, "mip_rel_gap": 1e-3},
    )
    chosen = [sites[i] for i in np.flatnonzero(result.x[:n] > 0.5)]
    return chosen, float(-result.fun)


def run() -> dict:
    network = load()
    points = pd.read_parquet(PROCESSED / "demand_points.parquet")
    points = points[points["kind"] == "dwelling"].reset_index(drop=True)
    weight = points.set_index("point_id")[DEMAND_COLUMN].fillna(0)
    existing, programme = split_schools()
    od_existing = origin_destination(network, points, existing, "facility_id")
    od_programme = origin_destination(network, points, programme, "facility_id")
    plots = feasible_sites(points)
    od_plots = origin_destination(network, points, plots, "facility_id")
    report = {
        "plot_m2": PLOT_M2,
        "clearance_m": CLEARANCE_M,
        "capacity_children": CAPACITY,
        "feasible_plots": int(len(plots)),
        "median_shift_from_cell_centre_m": float(plots["shift_m"].median()),
        "programme_schools": int(len(programme)),
        "radii": {},
    }
    for radius in RADII_M:
        before = covered(od_existing, radius)
        uncovered = weight[~weight.index.isin(before) & (weight > 0)]
        unit = demand_units(points, uncovered)
        unit_weight = uncovered.groupby(unit).sum()
        uncovered_units = pd.Series(unit.to_numpy(), index=uncovered.index)
        pairs_plots = unit_pairs(od_plots, uncovered_units, uncovered, radius)
        pairs_programme = unit_pairs(od_programme, uncovered_units, uncovered, radius)
        k = len(programme)
        _, uncapacitated = capacitated(pairs_plots, unit_weight, k, 1e12)
        chosen, optimal = capacitated(pairs_plots, unit_weight, k, CAPACITY)
        _, realised_cap = capacitated(
            pairs_programme,
            unit_weight,
            None,
            CAPACITY,
            fixed=list(pairs_programme["facility_id"].unique()),
        )
        _, realised_free = capacitated(
            pairs_programme,
            unit_weight,
            None,
            1e12,
            fixed=list(pairs_programme["facility_id"].unique()),
        )
        report["radii"][str(radius)] = {
            "uncovered_children": float(uncovered.sum()),
            "realised_uncapacitated": realised_free,
            "realised_capacitated": realised_cap,
            "optimal_on_feasible_plots_uncapacitated": uncapacitated,
            "optimal_on_feasible_plots_capacitated": optimal,
            "realised_over_optimal_capacitated": realised_cap / optimal if optimal else 0.0,
        }
        plots[plots["facility_id"].isin(chosen)].to_crs(CRS_GEO).to_file(
            PROCESSED / "backtest.gpkg", layer=f"realistic_{radius}", driver="GPKG"
        )
    (REPORTS / "backtest_realistic.json").write_text(
        json.dumps(report, indent=1, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=float))

import json

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from astana_access import norms
from astana_access.accessibility.coverage import origin_destination
from astana_access.accessibility.network import load
from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, REPORTS, SEED
from astana_access.ingest.stat_ages import cohort_shares
from astana_access.optimization import realistic
from astana_access.optimization.backtest import (
    DEMAND_COLUMN,
    RADII_M,
    RANDOM_DRAWS,
    candidates,
    covered,
    gained,
    solve,
    split_schools,
)
from astana_access.optimization.land import load_clearance, plot_sites
from astana_access.population.history import UNIT_2023

BOOTSTRAP = 2000
YEAR = 2023


def demand_2023() -> pd.DataFrame:
    dwellings = gpd.read_parquet(PROCESSED / "dwellings_2023.parquet")
    centre = dwellings.geometry.representative_point()
    lonlat = gpd.GeoSeries(centre, crs=CRS_METRIC).to_crs(CRS_GEO)
    cells = [h3.latlng_to_cell(p.y, p.x, 9) for p in lonlat]
    shares = cohort_shares(YEAR)["school"]
    share = dwellings["district"].map(UNIT_2023).map(shares).fillna(shares["City"])
    frame = pd.DataFrame(
        {
            "point_id": "b" + dwellings["id"].astype(str),
            "kind": "dwelling",
            "h3": cells,
            "x": centre.x.to_numpy(),
            "y": centre.y.to_numpy(),
        }
    )
    frame[DEMAND_COLUMN] = dwellings["pop_2023"].to_numpy() * share.to_numpy()
    return frame


def auc_with_interval(label: np.ndarray, score: np.ndarray, rng: np.random.Generator) -> dict:
    point = roc_auc_score(label, score)
    draws = []
    n = len(label)
    for _ in range(BOOTSTRAP):
        index = rng.integers(0, n, n)
        if label[index].min() == label[index].max():
            continue
        draws.append(roc_auc_score(label[index], score[index]))
    low, high = np.percentile(draws, [2.5, 97.5])
    return {"auc": float(point), "low": float(low), "high": float(high)}


def paired_difference(
    label: np.ndarray, first: np.ndarray, second: np.ndarray, rng: np.random.Generator
) -> dict:
    n = len(label)
    draws = []
    for _ in range(BOOTSTRAP):
        index = rng.integers(0, n, n)
        if label[index].min() == label[index].max():
            continue
        draws.append(
            roc_auc_score(label[index], first[index]) - roc_auc_score(label[index], second[index])
        )
    low, high = np.percentile(draws, [2.5, 97.5])
    return {
        "difference": float(roc_auc_score(label, first) - roc_auc_score(label, second)),
        "low": float(low),
        "high": float(high),
        "share_above_zero": float(np.mean(np.array(draws) > 0)),
    }


def run() -> dict:
    rng = np.random.default_rng(SEED)
    network = load()
    points = demand_2023()
    weight = points.set_index("point_id")[DEMAND_COLUMN].fillna(0)
    existing, programme = split_schools(YEAR)
    od_existing = origin_destination(network, points, existing, "facility_id")
    od_programme = origin_destination(network, points, programme, "facility_id")
    pool = candidates(points)
    od_pool = origin_destination(network, points, pool, "facility_id")
    plots = realistic.feasible_sites(points, YEAR)
    od_plots = origin_destination(network, points, plots, "facility_id")
    programme_capacity = (programme.set_index("facility_id")["seats"] * norms.SHIFTS).astype(float)
    clearance, transform = load_clearance(YEAR)
    centres = np.column_stack([pool.geometry.x, pool.geometry.y])
    _, plot_distance = plot_sites(
        centres, clearance, transform, realistic.CLEARANCE_M, realistic.SEARCH_M
    )
    pool["land_feasible"] = np.isfinite(plot_distance)

    nearest_cell = [
        pool.loc[pool.geometry.distance(point).idxmin(), "facility_id"]
        for point in programme.geometry
    ]
    pool["programme"] = pool["facility_id"].isin(set(nearest_cell)).astype(int)
    report = {
        "year": YEAR,
        "school_age_children_2023": float(weight.sum()),
        "candidate_cells": int(len(pool)),
        "programme_cells": int(pool["programme"].sum()),
        "programme_cells_land_feasible": int(
            pool.loc[pool["programme"] == 1, "land_feasible"].sum()
        ),
        "land_feasible_cells": int(pool["land_feasible"].sum()),
        "programme_schools_located": int(len(programme)),
        "programme_seats": float(programme["seats"].sum()),
        "feasible_plots": int(len(plots)),
        "selection": {},
        "backtest": {},
        "capacitated": {},
    }
    for radius in RADII_M:
        before = covered(od_existing, radius)
        uncovered = weight[~weight.index.isin(before) & (weight > 0)]
        reach = od_pool[od_pool["distance_m"] <= radius]
        deficit = reach["point_id"].map(uncovered).fillna(0).groupby(reach["facility_id"]).sum()
        density = reach["point_id"].map(weight).fillna(0).groupby(reach["facility_id"]).sum()
        frame = pool.set_index("facility_id")
        frame["deficit"] = deficit.reindex(frame.index).fillna(0)
        frame["density"] = density.reindex(frame.index).fillna(0)
        label = frame["programme"].to_numpy()
        scores = {
            "deficit": frame["deficit"].to_numpy(),
            "density": frame["density"].to_numpy(),
            "cell_children": frame["children"].to_numpy(),
            "land_feasible": frame["land_feasible"].astype(float).to_numpy(),
            "deficit_if_feasible": (frame["deficit"] * frame["land_feasible"]).to_numpy(),
        }
        report["selection"][str(radius)] = {
            **{name: auc_with_interval(label, score, rng) for name, score in scores.items()},
            "deficit_minus_density": paired_difference(
                label, scores["deficit"], scores["density"], rng
            ),
        }

        gain_pool = od_pool[
            (od_pool["distance_m"] <= radius) & od_pool["point_id"].isin(uncovered.index)
        ]
        gain_programme = od_programme[
            (od_programme["distance_m"] <= radius) & od_programme["point_id"].isin(uncovered.index)
        ]
        k = len(programme)
        realised = float(uncovered.reindex(gain_programme["point_id"].unique()).sum())
        _, optimal = solve(gain_pool, uncovered, k)
        feasible_ids = list(pool.loc[pool["land_feasible"], "facility_id"])
        _, optimal_feasible = solve(
            gain_pool[gain_pool["facility_id"].isin(feasible_ids)], uncovered, k
        )
        sites = pool["facility_id"].to_numpy()
        random_gains = [
            gained(gain_pool, uncovered, list(rng.choice(sites, size=k, replace=False)))
            for _ in range(RANDOM_DRAWS)
        ]
        density_sites = (
            pool.sort_values("children", ascending=False)["facility_id"].head(k).tolist()
        )
        unit = realistic.demand_units(points, uncovered)
        unit_weight = uncovered.groupby(unit).sum()
        units = pd.Series(unit.to_numpy(), index=uncovered.index)
        pairs_plots = realistic.unit_pairs(od_plots, units, uncovered, radius)
        pairs_cells = realistic.unit_pairs(od_pool, units, uncovered, radius)
        pairs_programme = realistic.unit_pairs(od_programme, units, uncovered, radius)
        fixed = list(pairs_programme["facility_id"].unique())
        _, realised_capacitated = realistic.capacitated(
            pairs_programme, unit_weight, None, programme_capacity, fixed=fixed
        )
        _, cells_capacitated = realistic.capacitated(
            pairs_cells, unit_weight, k, realistic.CAPACITY
        )
        chosen_plots, plots_capacitated = realistic.capacitated(
            pairs_plots, unit_weight, k, realistic.CAPACITY
        )
        plots[plots["facility_id"].isin(chosen_plots)].to_crs(CRS_GEO).to_file(
            PROCESSED / "backtest.gpkg", layer=f"optimal_2023_{radius}", driver="GPKG"
        )
        uncovered_points = points.set_index("point_id").loc[uncovered.index, ["x", "y", "h3"]]
        uncovered_points.assign(children=uncovered.to_numpy()).groupby("h3")[
            "children"
        ].sum().to_frame().to_parquet(PROCESSED / f"uncovered_2023_{radius}.parquet")
        _, plots_free = realistic.capacitated(pairs_plots, unit_weight, k, 1e12)
        report["capacitated"][str(radius)] = {
            "realised": realised_capacitated,
            "optimal_any_cell": cells_capacitated,
            "optimal_feasible_plot": plots_capacitated,
            "optimal_feasible_plot_without_capacity": plots_free,
            "realised_over_optimal_any_cell": realised_capacitated / cells_capacitated,
            "realised_over_optimal_feasible_plot": realised_capacitated / plots_capacitated,
            "capacity_cost_feasible_plot": 1 - plots_capacitated / plots_free,
        }
        report["backtest"][str(radius)] = {
            "uncovered_children_2023": float(uncovered.sum()),
            "realised_gain": realised,
            "optimal_gain": optimal,
            "optimal_gain_land_feasible": optimal_feasible,
            "realised_over_optimal": realised / optimal if optimal else 0.0,
            "realised_over_optimal_land_feasible": realised / optimal_feasible
            if optimal_feasible
            else 0.0,
            "density_gain": gained(gain_pool, uncovered, density_sites),
            "random_gain_mean": float(np.mean(random_gains)),
            "random_gain_p95": float(np.percentile(random_gains, 95)),
            "realised_random_percentile": float(np.mean(np.array(random_gains) < realised)),
        }
    programme.to_crs(CRS_GEO).to_file(
        PROCESSED / "backtest.gpkg", layer="programme_2023", driver="GPKG"
    )
    existing.to_crs(CRS_GEO).to_file(
        PROCESSED / "backtest.gpkg", layer="existing_2023", driver="GPKG"
    )
    (REPORTS / "programme_2023.json").write_text(
        json.dumps(report, indent=1, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=float))

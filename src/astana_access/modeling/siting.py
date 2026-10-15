import json

import geopandas as gpd
import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from scipy.spatial import cKDTree
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from astana_access.accessibility.coverage import facilities, origin_destination
from astana_access.accessibility.e2sfca import load_inputs
from astana_access.accessibility.network import load
from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW, REPORTS, SEED
from astana_access.optimization import realistic
from astana_access.optimization.backtest import candidates, covered, gained, split_schools
from astana_access.optimization.land import load_clearance, plot_sites
from astana_access.optimization.plan import plan_sites
from astana_access.optimization.programme import auc_with_interval, demand_2023

CENTRE_LONLAT = (71.4305, 51.1283)
RING_M = 500.0
PLOT_CAP_M = 2000.0
SITES = 17
FEATURES = [
    "deficit_1000",
    "deficit_1500",
    "density_1000",
    "cell_children",
    "plot_distance_m",
    "nearest_school_m",
    "centre_m",
    "construction_share",
    "residential_share",
]
LOGGED = {"deficit_1000", "deficit_1500", "density_1000", "cell_children"}
PARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.03,
    "num_leaves": 4,
    "min_child_samples": 10,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "verbose": -1,
}


def landuse(year: int) -> gpd.GeoDataFrame:
    if year < 2026:
        frame = gpd.read_parquet(PROCESSED / "landuse_2023.parquet")
    else:
        frame = gpd.read_file(RAW / "osm" / "landuse.gpkg").to_crs(CRS_METRIC)
    return frame[frame["value"].isin(["construction", "residential"])][["value", "geometry"]]


def area_share(centres: gpd.GeoSeries, polygons: gpd.GeoDataFrame, value: str) -> np.ndarray:
    rings = gpd.GeoDataFrame(
        {"cell": np.arange(len(centres))},
        geometry=centres.buffer(RING_M).to_numpy(),
        crs=CRS_METRIC,
    )
    polygons = polygons.to_crs(CRS_METRIC)
    chosen = polygons[polygons["value"] == value]
    if chosen.empty:
        return np.zeros(len(centres))
    joined = gpd.overlay(rings, chosen[["geometry"]], how="intersection")
    area = joined.assign(a=joined.area).groupby("cell")["a"].sum()
    return (area.reindex(range(len(centres))).fillna(0) / (np.pi * RING_M**2)).to_numpy()


def features(points: pd.DataFrame, existing: gpd.GeoDataFrame, year: int) -> gpd.GeoDataFrame:
    network = load()
    weight = points.set_index("point_id")["school_station"].fillna(0)
    pool = candidates(points)
    od_existing = origin_destination(network, points, existing, "facility_id")
    od_pool = origin_destination(network, points, pool, "facility_id")
    frame = pool.set_index("facility_id")
    for radius in (1000, 1500):
        before = covered(od_existing, radius)
        uncovered = weight[~weight.index.isin(before) & (weight > 0)]
        reach = od_pool[od_pool["distance_m"] <= radius]
        deficit = reach["point_id"].map(uncovered).fillna(0).groupby(reach["facility_id"]).sum()
        frame[f"deficit_{radius}"] = deficit.reindex(frame.index).fillna(0)
        if radius == 1000:
            density = reach["point_id"].map(weight).fillna(0).groupby(reach["facility_id"]).sum()
            frame["density_1000"] = density.reindex(frame.index).fillna(0)
            frame.attrs["uncovered"] = uncovered
            frame.attrs["reach"] = reach
    frame["cell_children"] = frame["children"]
    clearance, transform = load_clearance(year)
    centres = np.column_stack([frame.geometry.x, frame.geometry.y])
    _, plot_distance = plot_sites(
        centres, clearance, transform, realistic.CLEARANCE_M, realistic.SEARCH_M
    )
    frame["plot_distance_m"] = np.minimum(
        np.nan_to_num(plot_distance, posinf=PLOT_CAP_M), PLOT_CAP_M
    )
    tree = cKDTree(np.column_stack([existing.geometry.x, existing.geometry.y]))
    frame["nearest_school_m"] = tree.query(centres)[0]
    centre = gpd.GeoSeries(gpd.points_from_xy([CENTRE_LONLAT[0]], [CENTRE_LONLAT[1]]), crs=CRS_GEO)
    centre = centre.to_crs(CRS_METRIC).iloc[0]
    frame["centre_m"] = frame.geometry.distance(centre)
    uses = landuse(year)
    frame["construction_share"] = area_share(frame.geometry, uses, "construction")
    frame["residential_share"] = area_share(frame.geometry, uses, "residential")
    district = points[points["kind"] == "dwelling"].groupby("h3")["district"].first()
    frame["district"] = district.reindex(frame["h3"]).fillna("none").to_numpy()
    return frame


def label_nearest(frame: gpd.GeoDataFrame, sites: gpd.GeoDataFrame) -> np.ndarray:
    nearest = {frame.geometry.distance(point).idxmin() for point in sites.geometry}
    return frame.index.isin(nearest).astype(int)


def matrix(frame: pd.DataFrame) -> np.ndarray:
    table = frame[FEATURES].astype(float).copy()
    for column in LOGGED:
        table[column] = np.log1p(table[column])
    return table.to_numpy()


def models() -> dict:
    return {
        "logistic": lambda: make_pipeline(
            StandardScaler(), LogisticRegression(C=0.5, max_iter=5000, class_weight="balanced")
        ),
        "lightgbm": lambda: lgb.LGBMClassifier(**PARAMS, random_state=SEED),
    }


def out_of_fold(x: np.ndarray, y: np.ndarray, groups: np.ndarray, make) -> np.ndarray:
    predicted = np.zeros(len(y))
    for train, test in GroupKFold(n_splits=len(np.unique(groups))).split(x, y, groups):
        if y[train].sum() == 0:
            continue
        model = make().fit(x[train], y[train])
        predicted[test] = model.predict_proba(x[test])[:, 1]
    return predicted


def reach_of(frame: gpd.GeoDataFrame, chosen: list[str]) -> float:
    reach = frame.attrs["reach"]
    gain = reach[reach["point_id"].isin(frame.attrs["uncovered"].index)]
    return gained(gain, frame.attrs["uncovered"], chosen)


def run() -> dict:
    rng = np.random.default_rng(SEED)
    existing_2023, programme = split_schools(2023)
    points_2023 = demand_2023()
    dwellings = gpd.read_parquet(PROCESSED / "dwellings_2023.parquet")
    points_2023["district"] = dwellings["district"].to_numpy()
    past = features(points_2023, existing_2023, 2023)
    past["label"] = label_nearest(past, programme)

    points_2026, _ = load_inputs()
    existing_2026 = facilities()["school"]
    present = features(points_2026, existing_2026, 2026)
    plan = plan_sites()
    new = plan[plan.geometry.notna() & (plan["kind"] == "new")]
    present["label"] = label_nearest(present, new)

    x_past, y_past = matrix(past), past["label"].to_numpy()
    x_now, y_now = matrix(present), present["label"].to_numpy()
    groups = past["district"].fillna("none").to_numpy()
    report = {
        "features": FEATURES,
        "cells_2023": int(len(past)),
        "programme_cells": int(y_past.sum()),
        "cells_2026": int(len(present)),
        "plan_cells": int(y_now.sum()),
        "models": {},
    }
    fitted = {}
    for name, make in models().items():
        oof = out_of_fold(x_past, y_past, groups, make)
        model = make().fit(x_past, y_past)
        fitted[name] = model
        score_now = model.predict_proba(x_now)[:, 1]
        present[f"score_{name}"] = score_now
        top = present.sort_values(f"score_{name}", ascending=False).index[:SITES].tolist()
        report["models"][name] = {
            "programme_spatial_cv": auc_with_interval(y_past, oof, rng),
            "plan_2026_transfer": auc_with_interval(y_now, score_now, rng),
            "top_cells_reach_1000": reach_of(present, top),
        }
    coefficients = fitted["logistic"][-1].coef_[0]
    boot = []
    for _ in range(500):
        index = rng.integers(0, len(y_past), len(y_past))
        if y_past[index].sum() < 3:
            continue
        boot.append(models()["logistic"]().fit(x_past[index], y_past[index])[-1].coef_[0])
    boot = np.array(boot)
    report["logistic_standardised"] = {
        feature: {
            "coefficient": float(coefficients[i]),
            "low": float(np.percentile(boot[:, i], 2.5)),
            "high": float(np.percentile(boot[:, i], 97.5)),
        }
        for i, feature in enumerate(FEATURES)
    }
    explainer = shap.TreeExplainer(fitted["lightgbm"])
    values = explainer.shap_values(x_past)
    values = values[1] if isinstance(values, list) else values
    report["lightgbm_mean_abs_shap"] = dict(
        sorted(
            zip(FEATURES, np.abs(values).mean(axis=0).round(4).tolist(), strict=True),
            key=lambda item: -item[1],
        )
    )
    plan_cells = present.index[present["label"] == 1].tolist()
    report["plan_cells_near_construction"] = int(
        (present.loc[present["label"] == 1, "construction_share"] > 0).sum()
    )
    report["cells_near_construction_share"] = float((present["construction_share"] > 0).mean())
    report["plan_cells_reach_1000"] = reach_of(present, plan_cells)
    report["univariate_2023"] = {
        feature: auc_with_interval(y_past, past[feature].to_numpy(dtype=float), rng)
        for feature in FEATURES
    }
    report["univariate_2026"] = {
        feature: auc_with_interval(y_now, present[feature].to_numpy(dtype=float), rng)
        for feature in FEATURES
    }
    keep = ["h3", *FEATURES, "label", "score_logistic", "score_lightgbm"]
    (REPORTS / "siting_model.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    scores = pd.DataFrame(present[keep])
    scores.attrs = {}
    scores.to_parquet(PROCESSED / "siting_scores_2026.parquet")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))

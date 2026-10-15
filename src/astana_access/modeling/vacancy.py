import json

import geopandas as gpd
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from astana_access.accessibility.e2sfca import supply_measures
from astana_access.config import CRS_METRIC, PROCESSED, REPORTS, SEED

RADII_M = (500, 1000)
BLOCK_M = 2000.0
FOLDS = 5
REPEATS = 5
BOOTSTRAP = 1000
PRESSURE = "children_per_place_1000"
OWN = [
    "state",
    "branch",
    "min_age",
    "kazakh_only",
    "russian",
    "nursery",
    "mini_centre",
    "approximate_position",
    "capacity",
]
CONTEXT = [
    "children_500",
    "children_1000",
    "rivals_500",
    "rivals_1000",
    "children_per_place_500",
    "children_per_place_1000",
    "nearest_rival_m",
]
PARAMS = {
    "objective": "binary",
    "learning_rate": 0.03,
    "num_leaves": 4,
    "min_child_samples": 40,
    "reg_lambda": 5.0,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "n_estimators": 150,
    "verbose": -1,
}


def dataset() -> pd.DataFrame:
    preschools = gpd.read_file(PROCESSED / "facilities.gpkg", layer="preschools")
    preschools = preschools[preschools.geometry.notna()].to_crs(CRS_METRIC).reset_index(drop=True)
    points = pd.read_parquet(PROCESSED / "demand_points.parquet")
    points = points[points["kind"] == "dwelling"].set_index("point_id")
    od = pd.read_parquet(PROCESSED / "od_walk_preschool.parquet")
    od["children"] = od["point_id"].map(points["preschool_station"]).fillna(0)
    frame = pd.DataFrame(
        {
            "facility_id": preschools["facility_id"],
            "district": preschools["district"],
            "free": (preschools["free_places"] > 0).astype(int),
            "state": (preschools["ownership"] == "state").astype(int),
            "branch": preschools["branch"].astype(int),
            "min_age": preschools["min_age"].fillna(preschools["min_age"].median()),
            "kazakh_only": (preschools["languages"].fillna("").str.strip() == "казахский").astype(
                int
            ),
            "russian": preschools["languages"].fillna("").str.contains("русск").astype(int),
            "nursery": (preschools["kind"] == "nursery_kindergarten").astype(int),
            "mini_centre": (preschools["kind"] == "mini_centre").astype(int),
            "approximate_position": (preschools["coord_source"] == "gazetteer_approximate").astype(
                int
            ),
        }
    )
    places = supply_measures()["preschool"]["capacity"]
    frame["capacity"] = frame["facility_id"].map(places).to_numpy()
    centre = preschools.geometry
    xy = np.column_stack([centre.x, centre.y])
    tree = cKDTree(xy)
    for radius in RADII_M:
        near = od[od["distance_m"] <= radius].groupby("facility_id")["children"].sum()
        frame[f"children_{radius}"] = frame["facility_id"].map(near).fillna(0).to_numpy()
        groups = tree.query_ball_point(xy, r=radius)
        rivals = np.array([len(items) - 1 for items in groups])
        nearby = np.array([frame["capacity"].to_numpy()[items].sum() for items in groups])
        frame[f"rivals_{radius}"] = rivals
        frame[f"children_per_place_{radius}"] = frame[f"children_{radius}"] / nearby
    distance, _ = tree.query(xy, k=2)
    frame["nearest_rival_m"] = distance[:, 1]
    frame["x"] = xy[:, 0]
    frame["y"] = xy[:, 1]
    frame["block"] = (
        (frame["x"] // BLOCK_M).astype(int).astype(str)
        + "_"
        + (frame["y"] // BLOCK_M).astype(int).astype(str)
    )
    return frame


def evaluate(frame: pd.DataFrame, features: list[str], model: str) -> dict[str, float]:
    scores = {"roc_auc": [], "pr_auc": [], "brier": []}
    target = frame["free"].to_numpy()
    for repeat in range(REPEATS):
        rng = np.random.default_rng(SEED + repeat)
        blocks = frame["block"].unique()
        mapping = dict(zip(blocks, rng.permutation(len(blocks)), strict=True))
        groups = frame["block"].map(mapping)
        oof = np.zeros(len(frame))
        for train, test in GroupKFold(n_splits=FOLDS).split(frame, target, groups):
            if model == "lightgbm":
                fitted = lgb.LGBMClassifier(**PARAMS, random_state=SEED + repeat)
            else:
                fitted = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
            fitted.fit(frame.iloc[train][features], target[train])
            oof[test] = fitted.predict_proba(frame.iloc[test][features])[:, 1]
        scores["roc_auc"].append(roc_auc_score(target, oof))
        scores["pr_auc"].append(average_precision_score(target, oof))
        scores["brier"].append(brier_score_loss(target, oof))
    return {
        f"{key}_{stat}": float(fn(values))
        for key, values in scores.items()
        for stat, fn in (("mean", np.mean), ("sd", np.std))
    }


def pressure_coefficient(data: pd.DataFrame, own: list[str]) -> dict[str, float]:
    features = [*own, PRESSURE]
    rng = np.random.default_rng(SEED)
    target = data["free"].to_numpy()

    def coefficient(index: np.ndarray) -> float:
        fitted = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
        fitted.fit(data.iloc[index][features], target[index])
        return float(fitted[-1].coef_[0][-1])

    point = coefficient(np.arange(len(data)))
    draws = [coefficient(rng.integers(0, len(data), len(data))) for _ in range(BOOTSTRAP)]
    low, high = np.percentile(draws, [2.5, 97.5])
    return {"coefficient": point, "low": float(low), "high": float(high)}


def run() -> dict:
    frame = dataset()
    frame.to_parquet(PROCESSED / "preschool_vacancy.parquet")
    report = {
        "n": int(len(frame)),
        "with_free_places": int(frame["free"].sum()),
        "state_with_free_places": int(frame.loc[frame["state"] == 1, "free"].sum()),
        "state_total": int(frame["state"].sum()),
        "results": {},
    }
    subsets = {"all": frame, "private": frame[frame["state"] == 0]}
    for subset, data in subsets.items():
        own = [f for f in OWN if data[f].nunique() > 1]
        for name, features in (("own", own), ("own_context", own + CONTEXT)):
            for model in ("logistic", "lightgbm"):
                key = f"{subset}/{name}/{model}"
                report["results"][key] = evaluate(data, features, model)
    data = frame[frame["state"] == 0]
    fitted = lgb.LGBMClassifier(**PARAMS, random_state=SEED)
    own = [f for f in OWN if data[f].nunique() > 1]
    fitted.fit(data[own + CONTEXT], data["free"])
    report["importance_private"] = dict(
        sorted(
            zip(own + CONTEXT, (int(v) for v in fitted.feature_importances_), strict=True),
            key=lambda item: -item[1],
        )
    )
    report["pressure_coefficient_private"] = pressure_coefficient(data, own)
    contrast = data.assign(
        high=data["children_per_place_1000"] > data["children_per_place_1000"].median()
    )
    report["free_share_by_pressure_private"] = (
        contrast.groupby("high")["free"]
        .mean()
        .rename({True: "above_median", False: "below_median"})
        .to_dict()
    )
    (REPORTS / "preschool_vacancy.json").write_text(
        json.dumps(report, indent=1, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=float))

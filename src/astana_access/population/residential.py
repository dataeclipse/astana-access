import json

import geopandas as gpd
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold

from astana_access.config import INTERIM, PROCESSED, REPORTS, SEED

FEATURES = [
    "footprint_m2",
    "perimeter_m",
    "compactness",
    "floors",
    "osm",
    "addresses",
    "flats",
    "poi_nodes",
    "in_residential",
    "in_allotments",
    "in_construction",
    "n_100",
    "area_median_100",
    "built_share_100",
    "floors_median_100",
    "n_300",
    "area_median_300",
    "built_share_300",
    "floors_median_300",
]
BLOCK_M = 1000.0
FOLDS = 5
PARAMS = {
    "objective": "binary",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "n_estimators": 400,
    "random_state": SEED,
    "verbose": -1,
}


def design(frame: pd.DataFrame) -> pd.DataFrame:
    table = frame.copy()
    table["floors"] = pd.to_numeric(table["num_floors"], errors="coerce")
    table["osm"] = table["osm"].astype(int)
    for group in ("residential", "allotments", "construction"):
        table[f"in_{group}"] = (table["landuse"] == group).astype(int)
    positive = (table["label_tag"] == 1) | (table["label_list"] == 1) | (table["label_use"] == 1)
    negative = (
        (table["label_tag"] == 0) | (table["landuse"] == "nonres") | (table["label_use"] == 0)
    )
    table["target"] = np.where(positive, 1.0, np.where(negative, 0.0, np.nan))
    table["block"] = (
        (table["x"] // BLOCK_M).astype(int).astype(str)
        + "_"
        + (table["y"] // BLOCK_M).astype(int).astype(str)
    )
    return table


def scores(target: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    predicted = probability >= 0.5
    tn, fp, fn, tp = confusion_matrix(target, predicted).ravel()
    return {
        "n": int(len(target)),
        "positive_share": float(target.mean()),
        "roc_auc": float(roc_auc_score(target, probability)),
        "pr_auc": float(average_precision_score(target, probability)),
        "f1": float(f1_score(target, predicted)),
        "brier": float(brier_score_loss(target, probability)),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
    }


def cross_validate(table: pd.DataFrame) -> tuple[dict[str, float], np.ndarray]:
    labelled = table[table["target"].notna()]
    oof = np.zeros(len(labelled))
    folds = GroupKFold(n_splits=FOLDS)
    for train, test in folds.split(labelled, labelled["target"], labelled["block"]):
        model = lgb.LGBMClassifier(**PARAMS)
        model.fit(labelled.iloc[train][FEATURES], labelled.iloc[train]["target"])
        oof[test] = model.predict_proba(labelled.iloc[test][FEATURES])[:, 1]
    return scores(labelled["target"].to_numpy(), oof), oof


def transfer_test(table: pd.DataFrame) -> dict[str, float]:
    listed = table["label_list"] == 1
    train = table[table["target"].notna() & ~listed]
    held = table[listed & table["label_tag"].isna()]
    model = lgb.LGBMClassifier(**PARAMS)
    model.fit(train[FEATURES], train["target"])
    probability = model.predict_proba(held[FEATURES])[:, 1]
    return {
        "n": int(len(held)),
        "recall": float((probability >= 0.5).mean()),
        "mean_probability": float(probability.mean()),
    }


def fit_predict() -> tuple[gpd.GeoDataFrame, dict]:
    frame = gpd.read_parquet(INTERIM / "buildings_features.parquet")
    table = design(frame)
    cv, _ = cross_validate(table)
    transfer = transfer_test(table)
    labelled = table[table["target"].notna()]
    model = lgb.LGBMClassifier(**PARAMS)
    model.fit(labelled[FEATURES], labelled["target"])
    frame["p_residential"] = model.predict_proba(table[FEATURES])[:, 1]
    known = table["target"].notna()
    frame.loc[known, "p_residential"] = table.loc[known, "target"]
    frame["label_source"] = np.where(known, "observed", "model")
    importance = dict(
        sorted(
            zip(FEATURES, (int(v) for v in model.feature_importances_), strict=True),
            key=lambda item: -item[1],
        )
    )
    report = {"spatial_cv": cv, "transfer_to_lists": transfer, "importance": importance}
    (REPORTS / "residential_classifier.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8"
    )
    frame.to_parquet(PROCESSED / "buildings.parquet")
    return frame, report

import json

import geopandas as gpd
import h3
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW, REPORTS, SEED
from astana_access.population.history import buildings_2023, existed, landuse_2023

SNAPSHOTS = {
    2017: "2017-01-01T00:00:00Z",
    2020: "2020-01-01T00:00:00Z",
    2023: "2023-01-01T00:00:00Z",
}
CENTRE_LONLAT = (71.4305, 51.1283)
MAJOR = {"motorway", "trunk", "primary", "secondary"}
BLOCKED = {
    "forest",
    "park",
    "cemetery",
    "industrial",
    "military",
    "railway",
    "farmland",
    "allotments",
}
NEW_M2 = 1000.0
TOP_SHARE = 0.1
FEATURES = [
    "floor",
    "floor_ring1",
    "floor_ring2",
    "new_prev",
    "new_prev_ring1",
    "new_prev_ring2",
    "construction",
    "construction_ring1",
    "built_share",
    "blocked_share",
    "centre_m",
    "road_m",
    "district_code",
]
PARAMS = {
    "objective": "tweedie",
    "tweedie_variance_power": 1.3,
    "n_estimators": 400,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 20,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "verbose": -1,
}


def cell_of(geometry: gpd.GeoSeries) -> np.ndarray:
    lonlat = gpd.GeoSeries(geometry.representative_point(), crs=CRS_METRIC).to_crs(CRS_GEO)
    return np.array([h3.latlng_to_cell(p.y, p.x, 9) for p in lonlat])


def ring_sum(values: pd.Series, k: int) -> pd.Series:
    lookup = values.to_dict()
    return pd.Series(
        {
            cell: sum(lookup.get(n, 0.0) for n in h3.grid_disk(cell, k)) - lookup.get(cell, 0.0)
            for cell in values.index
        }
    )


def share_in_cells(cells: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame) -> pd.Series:
    if polygons.empty:
        return pd.Series(0.0, index=cells["h3"])
    joined = gpd.overlay(cells[["h3", "geometry"]], polygons[["geometry"]], how="intersection")
    area = joined.assign(a=joined.area).groupby("h3")["a"].sum()
    return (area / cells.set_index("h3").area).reindex(cells["h3"]).fillna(0.0).clip(0, 1)


def static_features(cells: gpd.GeoDataFrame) -> pd.DataFrame:
    centre = gpd.GeoSeries(gpd.points_from_xy([CENTRE_LONLAT[0]], [CENTRE_LONLAT[1]]), crs=CRS_GEO)
    centre = centre.to_crs(CRS_METRIC).iloc[0]
    lines = gpd.read_file(RAW / "osm" / "lines.gpkg").to_crs(CRS_METRIC)
    roads = lines[(lines["kind"] == "highway") & lines["class"].isin(MAJOR)].union_all()
    middle = cells.geometry.centroid
    return pd.DataFrame(
        {
            "centre_m": middle.distance(centre).to_numpy(),
            "road_m": middle.distance(roads).to_numpy(),
            "district_code": pd.factorize(cells["district"].fillna("none"))[0],
        },
        index=cells["h3"],
    )


def snapshot_layers(year: int) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    if year >= 2026:
        buildings = gpd.read_file(RAW / "osm" / "buildings.gpkg").to_crs(CRS_METRIC)
        uses = gpd.read_file(RAW / "osm" / "landuse.gpkg").to_crs(CRS_METRIC)
    else:
        buildings = buildings_2023(SNAPSHOTS[year])
        uses = landuse_2023(SNAPSHOTS[year])
    return buildings[["geometry"]], uses[["value", "geometry"]]


def period_table(
    year: int,
    dwellings: pd.DataFrame,
    present: dict[int, np.ndarray],
    cells: gpd.GeoDataFrame,
    static: pd.DataFrame,
) -> pd.DataFrame:
    floor = dwellings["floor_area_m2"].to_numpy()
    now = present[year]
    before = present[year - 3]
    index = cells["h3"]

    def by_cell(mask: np.ndarray) -> pd.Series:
        return (
            pd.Series(floor * mask)
            .groupby(dwellings["cell"].to_numpy())
            .sum()
            .reindex(index)
            .fillna(0.0)
        )

    table = pd.DataFrame(index=index)
    table["floor"] = by_cell(now)
    table["new_prev"] = by_cell(now & ~before)
    for k in (1, 2):
        table[f"floor_ring{k}"] = ring_sum(table["floor"], k).reindex(index).to_numpy()
        table[f"new_prev_ring{k}"] = ring_sum(table["new_prev"], k).reindex(index).to_numpy()
    buildings, uses = snapshot_layers(year)
    built = gpd.GeoDataFrame(geometry=buildings.geometry.buffer(0), crs=CRS_METRIC)
    table["built_share"] = share_in_cells(cells, built).to_numpy()
    table["construction"] = share_in_cells(cells, uses[uses["value"] == "construction"]).to_numpy()
    table["construction_ring1"] = ring_sum(table["construction"], 1).reindex(index).to_numpy()
    table["blocked_share"] = share_in_cells(cells, uses[uses["value"].isin(BLOCKED)]).to_numpy()
    table = table.join(static)
    if year + 3 in present:
        table["target"] = by_cell(present[year + 3] & ~now).to_numpy()
    table["district"] = cells.set_index("h3")["district"].reindex(index).to_numpy()
    return table


def evaluate(actual: np.ndarray, score: np.ndarray) -> dict:
    order = np.argsort(-score)
    top = order[: int(len(order) * TOP_SHARE)]
    return {
        "spearman": float(spearmanr(actual, score).statistic),
        "roc_auc_any_new": float(roc_auc_score(actual >= NEW_M2, score)),
        "top_decile_capture": float(actual[top].sum() / actual.sum()),
    }


def run() -> dict:
    dwellings = gpd.read_parquet(PROCESSED / "dwellings.parquet")
    sources = pd.read_parquet(PROCESSED / "buildings.parquet", columns=["id", "source"])
    dwellings = dwellings.merge(sources, on="id", how="left")
    dwellings["cell"] = cell_of(dwellings.geometry)
    present = {
        year: existed(dwellings, buildings_2023(snapshot)) for year, snapshot in SNAPSHOTS.items()
    }
    present[2026] = np.ones(len(dwellings), dtype=bool)
    cells = gpd.read_file(PROCESSED / "grid_population.gpkg")[
        ["h3", "district", "geometry"]
    ].to_crs(CRS_METRIC)
    static = static_features(cells)
    tables = {
        year: period_table(year, dwellings, present, cells, static) for year in (2020, 2023, 2026)
    }
    train, test = tables[2020], tables[2023]
    model = lgb.LGBMRegressor(**PARAMS, random_state=SEED).fit(train[FEATURES], train["target"])
    predicted = model.predict(test[FEATURES])
    actual = test["target"].to_numpy()
    momentum = (test["new_prev"] + 0.25 * test["new_prev_ring1"]).to_numpy()
    report = {
        "cells": int(len(cells)),
        "new_floor_m2": {
            "2017_2020": float(train["new_prev"].sum()),
            "2020_2023": float(train["target"].sum()),
            "2023_2026": float(actual.sum()),
        },
        "temporal_test_2023_2026": {
            "lightgbm": evaluate(actual, predicted),
            "momentum": evaluate(actual, momentum),
            "construction_sites": evaluate(
                actual, test["construction"].to_numpy() + 1e-9 * momentum
            ),
        },
    }
    groups = test["district"].fillna("none").to_numpy()
    oof = np.zeros(len(test))
    for fit_rows, held in GroupKFold(n_splits=6).split(test, groups=groups):
        fold = lgb.LGBMRegressor(**PARAMS, random_state=SEED)
        fold.fit(test.iloc[fit_rows][FEATURES], test.iloc[fit_rows]["target"])
        oof[held] = fold.predict(test.iloc[held][FEATURES])
    report["spatial_cv_2023_2026"] = {
        "lightgbm": evaluate(actual, oof),
        "momentum": evaluate(actual, momentum),
    }
    final = lgb.LGBMRegressor(**PARAMS, random_state=SEED).fit(test[FEATURES], test["target"])
    forecast = tables[2026].copy()
    forecast["predicted_2026_2029"] = np.clip(final.predict(forecast[FEATURES]), 0, None)
    report["importance"] = dict(
        sorted(
            zip(FEATURES, (int(v) for v in final.feature_importances_), strict=True),
            key=lambda item: -item[1],
        )
    )
    report["forecast_by_district_share"] = (
        (
            forecast.groupby("district")["predicted_2026_2029"].sum()
            / forecast["predicted_2026_2029"].sum()
        )
        .round(3)
        .to_dict()
    )
    report["observed_2023_2026_by_district_share"] = (
        (test.groupby("district")["target"].sum() / test["target"].sum()).round(3).to_dict()
    )
    forecast.reset_index(names="h3")[
        ["h3", "district", "predicted_2026_2029", *FEATURES]
    ].to_parquet(PROCESSED / "housing_forecast.parquet")
    (REPORTS / "housing_forecast.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))

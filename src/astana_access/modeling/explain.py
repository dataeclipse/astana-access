import json

import geopandas as gpd
import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

from astana_access.config import INTERIM, PROCESSED, REPORTS, SEED
from astana_access.modeling import vacancy
from astana_access.population import residential
from astana_access.viz import style

SAMPLE = 4000
LABELS = {
    "footprint_m2": "Footprint area",
    "perimeter_m": "Perimeter",
    "compactness": "Compactness",
    "floors": "Tagged floors",
    "osm": "Mapped in OSM",
    "addresses": "Address points inside",
    "flats": "Tagged flats",
    "poi_nodes": "Points of interest inside",
    "in_residential": "Residential land use",
    "in_allotments": "Allotment land use",
    "in_construction": "Construction land use",
    "n_100": "Buildings within 100 m",
    "area_median_100": "Median footprint within 100 m",
    "built_share_100": "Built-up share within 100 m",
    "floors_median_100": "Median floors within 100 m",
    "n_300": "Buildings within 300 m",
    "area_median_300": "Median footprint within 300 m",
    "built_share_300": "Built-up share within 300 m",
    "floors_median_300": "Median floors within 300 m",
    "state": "State organisation",
    "branch": "Branch or mini-centre",
    "min_age": "Minimum enrolment age",
    "kazakh_only": "Kazakh only",
    "russian": "Russian groups",
    "nursery": "Nursery and kindergarten",
    "mini_centre": "Mini-centre",
    "approximate_position": "Approximate position",
    "children_500": "Children within 500 m",
    "children_1000": "Children within 1 km",
    "rivals_500": "Preschools within 500 m",
    "rivals_1000": "Preschools within 1 km",
    "children_per_org_500": "Children per preschool, 500 m",
    "children_per_org_1000": "Children per preschool, 1 km",
    "nearest_rival_m": "Distance to nearest preschool",
}


def ranked(values: np.ndarray, features: list[str]) -> dict[str, float]:
    mean = np.abs(values).mean(axis=0)
    order = np.argsort(-mean)
    return {features[i]: float(mean[i]) for i in order}


def figure(values: np.ndarray, data: pd.DataFrame, name: str, top: int) -> None:
    style.apply()
    shap.summary_plot(
        values,
        data.rename(columns=LABELS),
        max_display=top,
        show=False,
        plot_size=(6.3, 0.32 * top + 1.2),
        color_bar_label="Feature value",
    )
    fig = plt.gcf()
    style.save(fig, name)
    plt.close(fig)


def residential_model() -> dict:
    frame = gpd.read_parquet(INTERIM / "buildings_features.parquet")
    table = residential.design(frame)
    labelled = table[table["target"].notna()]
    model = lgb.LGBMClassifier(**residential.PARAMS)
    model.fit(labelled[residential.FEATURES], labelled["target"])
    sample = table[residential.FEATURES].sample(SAMPLE, random_state=SEED)
    values = shap.TreeExplainer(model).shap_values(sample)
    values = values[1] if isinstance(values, list) else values
    figure(values, sample, "shap_residential", 12)
    return ranked(values, residential.FEATURES)


def vacancy_model() -> dict:
    frame = pd.read_parquet(PROCESSED / "preschool_vacancy.parquet")
    data = frame[frame["state"] == 0]
    features = [f for f in vacancy.OWN if data[f].nunique() > 1] + vacancy.CONTEXT
    model = lgb.LGBMClassifier(**vacancy.PARAMS, random_state=SEED)
    model.fit(data[features], data["free"])
    values = shap.TreeExplainer(model).shap_values(data[features])
    values = values[1] if isinstance(values, list) else values
    figure(values, data[features], "shap_vacancy_private", 10)
    return ranked(values, features)


def run() -> dict:
    report = {"residential": residential_model(), "vacancy_private": vacancy_model()}
    (REPORTS / "shap.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))

import json

import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.accessibility.coverage import facilities, origin_destination
from astana_access.accessibility.e2sfca import load_inputs
from astana_access.accessibility.network import load
from astana_access.config import CRS_METRIC, PROCESSED, REPORTS
from astana_access.ingest import stat_ages
from astana_access.population.demography import school_age_factors
from astana_access.population.projection import POOLED_NAME
from astana_access.validation.uncertainty import (
    RADIUS_M,
    SITES_COMPARED,
    dwelling_table,
    site_reach,
)
from astana_access.viz.dashboard import greedy

MIN_NEW_CHILDREN = 1.0


def group_of(district: pd.Series) -> pd.Series:
    return district.where(~district.isin(stat_ages.POOLED), POOLED_NAME)


def new_housing_points(districts: pd.DataFrame) -> pd.DataFrame:
    forecast = pd.read_parquet(PROCESSED / "housing_forecast.parquet")
    grid = gpd.read_file(PROCESSED / "grid_population.gpkg")[["h3", "geometry"]].to_crs(CRS_METRIC)
    centre = grid.set_index("h3").geometry.centroid
    forecast["group"] = group_of(forecast["district"].fillna("none"))
    increment = (districts["cohort_2028"] - districts["ageing_2028"]).clip(lower=0)
    total = forecast.groupby("group")["predicted_2026_2029"].transform("sum")
    share = (forecast["predicted_2026_2029"] / total.replace(0, np.nan)).fillna(0)
    forecast["children"] = share * forecast["group"].map(increment).fillna(0)
    forecast = forecast[forecast["children"] >= MIN_NEW_CHILDREN]
    return pd.DataFrame(
        {
            "point_id": "n" + forecast["h3"],
            "x": centre.reindex(forecast["h3"]).x.to_numpy(),
            "y": centre.reindex(forecast["h3"]).y.to_numpy(),
            "district": forecast["district"].to_numpy(),
            "children": forecast["children"].to_numpy(),
        }
    )


def scenario(
    children: np.ndarray, uncovered: np.ndarray, district: np.ndarray, lists, plan_points, pdp_ids
) -> dict:
    weight = children * uncovered
    order = greedy(lists, list(weight), pdp_ids)
    plan = float(weight[plan_points].sum())
    chosen = [item["id"] for item in order[:SITES_COMPARED]]
    return {
        "school_age_children": float(children.sum()),
        "uncovered": float(weight.sum()),
        "plan_reach": plan,
        "plan_share": plan / float(weight.sum()),
        "best_reach": float(order[SITES_COMPARED - 1]["cumulative"]),
        "best_over_plan": float(order[SITES_COMPARED - 1]["cumulative"]) / plan,
        "best_sites": chosen,
        "uncovered_by_district": pd.Series(weight).groupby(district).sum().round().to_dict(),
    }


def reach_of(sites: list[str], lists: dict, weight: np.ndarray) -> float:
    taken = np.zeros(len(weight), dtype=bool)
    for site in sites:
        taken[lists.get(site, [])] = True
    return float(weight[taken].sum())


def run() -> dict:
    districts = school_age_factors()
    points, od = load_inputs()
    dwellings = dwelling_table(points)
    new = new_housing_points(districts)
    existing = facilities()["school"]
    od_new = origin_destination(load(), new, existing, "facility_id")
    nearest_new = (
        od_new.groupby("point_id")["distance_m"].min().reindex(new["point_id"]).fillna(np.inf)
    )
    ids = pd.Index(dwellings["point_id"])
    nearest_old = od["school"].groupby("point_id")["distance_m"].min().reindex(ids).fillna(np.inf)
    located = points.set_index("point_id").loc[ids, ["x", "y"]].reset_index()
    combined = pd.concat([located, new[["point_id", "x", "y"]]], ignore_index=True)
    all_ids = pd.Index(combined["point_id"])
    uncovered = np.concatenate([nearest_old.to_numpy(), nearest_new.to_numpy()]) > RADIUS_M
    lists, plan_points, pdp_ids = site_reach(combined, all_ids, uncovered)

    group = group_of(dwellings["unit"])
    children_2026 = (dwellings["pop_station"] * dwellings["school_share"]).to_numpy()
    shrink = districts["cohort_factor"].where(districts["cohort_2028"] < districts["ageing_2028"])
    factor = shrink.fillna(districts["ageing_factor"])
    old_2028 = children_2026 * group.map(factor).to_numpy()
    zeros = np.zeros(len(new))
    district = np.concatenate(
        [dwellings["unit"].to_numpy(), new["district"].fillna("none").to_numpy()]
    )
    flat = children_2026 * group.map(districts["cohort_factor"]).to_numpy()
    demands = {
        "2026": np.concatenate([children_2026, zeros]),
        "2028_present_pattern": np.concatenate([flat, zeros]),
        "2028_with_new_housing": np.concatenate([old_2028, new["children"].to_numpy()]),
    }
    report = {
        "new_housing_cells": int(len(new)),
        "children_in_new_housing": float(new["children"].sum()),
        "new_housing_children_without_school_1km": float(
            new["children"][nearest_new.to_numpy() > RADIUS_M].sum()
        ),
        "scenarios": {
            name: scenario(children, uncovered, district, lists, plan_points, pdp_ids)
            for name, children in demands.items()
        },
    }
    target = demands["2028_with_new_housing"] * uncovered
    chosen_now = report["scenarios"]["2026"]["best_sites"]
    chosen_future = report["scenarios"]["2028_with_new_housing"]["best_sites"]
    report["sites_chosen_on_2026_reach_2028"] = reach_of(chosen_now, lists, target)
    report["sites_chosen_on_2028_reach_2028"] = reach_of(chosen_future, lists, target)
    report["sites_in_common"] = len(set(chosen_now) & set(chosen_future))
    dwelling_cells = points.set_index("point_id")["h3"].reindex(ids).to_numpy()
    cells = np.concatenate([dwelling_cells, new["point_id"].str[1:].to_numpy()])
    housing = pd.read_parquet(PROCESSED / "housing_forecast.parquet").set_index("h3")
    by_cell = pd.DataFrame({"h3": cells, "uncovered_2028": target}).groupby("h3").sum()
    by_cell["new_children"] = pd.Series(new["children"].to_numpy(), index=new["point_id"].str[1:])
    by_cell = by_cell.join(housing[["predicted_2026_2029"]], how="outer").fillna(0.0)
    by_cell.reset_index(names="h3").to_parquet(PROCESSED / "forecast_2028_cells.parquet")
    (REPORTS / "siting_2028.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))

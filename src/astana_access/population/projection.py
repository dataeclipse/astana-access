import json

import numpy as np
import pandas as pd

from astana_access.accessibility.e2sfca import load_inputs
from astana_access.config import REPORTS
from astana_access.ingest import stat_ages
from astana_access.validation.uncertainty import (
    RADIUS_M,
    SITES_COMPARED,
    dwelling_table,
    site_reach,
)
from astana_access.viz.dashboard import greedy

BASE_YEAR = 2026
TARGET_YEAR = 2028
STEP = TARGET_YEAR - BASE_YEAR
LOW, HIGH = stat_ages.COHORT_AGES["school"]
POOLED_NAME = "+".join(stat_ages.POOLED)


def single_ages(table: pd.DataFrame) -> pd.DataFrame:
    single = table[table["age"].map(lambda age: isinstance(age, int))].copy()
    single["age"] = single["age"].astype(int)
    single = single[single["district"] != "City"]
    single["group"] = single["district"].where(
        ~single["district"].isin(stat_ages.POOLED), POOLED_NAME
    )
    return single.groupby(["group", "year", "age"])["people"].sum()


def project(people: pd.Series) -> pd.DataFrame:
    rows = {}
    for group in people.index.get_level_values("group").unique():
        n = people.loc[group]
        ages = range(LOW, HIGH + 1)
        base = sum(n.get((BASE_YEAR, a), 0.0) for a in ages)
        ageing = sum(n.get((BASE_YEAR, a - STEP), 0.0) for a in ages)
        ratios = {
            a: n.get((BASE_YEAR, a), np.nan) / n.get((BASE_YEAR - STEP, a - STEP), np.nan)
            for a in ages
        }
        cohort = sum(n.get((BASE_YEAR, a - STEP), 0.0) * ratios[a] for a in ages)
        rows[group] = {
            "school_age_2026": float(base),
            "ageing_2028": float(ageing),
            "cohort_2028": float(cohort),
            "cohort_ratio_median": float(np.nanmedian(list(ratios.values()))),
        }
    frame = pd.DataFrame(rows).T
    frame["ageing_factor"] = frame["ageing_2028"] / frame["school_age_2026"]
    frame["cohort_factor"] = frame["cohort_2028"] / frame["school_age_2026"]
    return frame


def scenario(
    children: np.ndarray,
    uncovered: np.ndarray,
    district: np.ndarray,
    lists: dict[str, list[int]],
    plan_points: np.ndarray,
    pdp_ids: list[str],
) -> dict:
    weight = children * uncovered
    order = greedy(lists, list(weight), pdp_ids)
    plan = float(weight[plan_points].sum())
    best = float(order[SITES_COMPARED - 1]["cumulative"])
    return {
        "school_age_children": float(children.sum()),
        "uncovered": float(weight.sum()),
        "plan_reach": plan,
        "after_plan": float(weight.sum() - plan),
        "plan_share": plan / float(weight.sum()),
        "best_reach": best,
        "best_over_plan": best / plan,
        "uncovered_by_district": pd.Series(weight).groupby(district).sum().round().to_dict(),
    }


def run() -> dict:
    table = stat_ages.load()
    districts = project(single_ages(table))
    points, od = load_inputs()
    dwellings = dwelling_table(points)
    ids = pd.Index(dwellings["point_id"])
    nearest = (
        od["school"].groupby("point_id")["distance_m"].min().reindex(ids).fillna(np.inf).to_numpy()
    )
    uncovered = nearest > RADIUS_M
    lists, plan_points, pdp_ids = site_reach(points, ids, uncovered)
    children = (dwellings["pop_station"] * dwellings["school_share"]).to_numpy()
    group = dwellings["unit"].where(~dwellings["unit"].isin(stat_ages.POOLED), POOLED_NAME)
    district = dwellings["unit"].to_numpy()
    report = {
        "base_year": BASE_YEAR,
        "target_year": TARGET_YEAR,
        "ages": [LOW, HIGH],
        "method": "Hamilton-Perry cohort change ratios of the official single-age tables",
        "districts": districts.round(4).to_dict(orient="index"),
        "city": {
            column: float(districts[column].sum())
            for column in ("school_age_2026", "ageing_2028", "cohort_2028")
        },
        "scenarios": {},
    }
    for name, column in (
        ("2026", None),
        ("ageing_2028", "ageing_factor"),
        ("cohort_2028", "cohort_factor"),
    ):
        factor = 1.0 if column is None else group.map(districts[column]).to_numpy()
        report["scenarios"][name] = scenario(
            children * factor, uncovered, district, lists, plan_points, pdp_ids
        )
    (REPORTS / "projection_2028.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))

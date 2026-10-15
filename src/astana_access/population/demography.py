import json

import numpy as np
import pandas as pd

from astana_access.config import REPORTS
from astana_access.ingest import stat_ages

STEP = 2
BASE_YEAR = 2026
HORIZON = 2030
OLDEST = 100
PARENT_AGES = (20, 39)
COHORTS = {
    "total": (0, OLDEST),
    "preschool": stat_ages.COHORT_AGES["preschool"],
    "school": stat_ages.COHORT_AGES["school"],
}
RATIO_BOUNDS = (0.2, 5.0)
POOLED_NAME = "+".join(stat_ages.POOLED)


def ages_table(table: pd.DataFrame) -> pd.DataFrame:
    rows = table[(table["age"] != "Всего") & (table["district"] != "City")].copy()
    rows["age"] = rows["age"].map(lambda age: OLDEST if age == f"{OLDEST}+" else int(age))
    rows["group"] = rows["district"].where(~rows["district"].isin(stat_ages.POOLED), POOLED_NAME)
    wide = rows.groupby(["group", "year", "age"])["people"].sum().unstack("age").fillna(0.0)
    return wide.reindex(columns=range(OLDEST + 1), fill_value=0.0)


def ratios(start: np.ndarray, end: np.ndarray) -> np.ndarray:
    out = np.ones(OLDEST + 1)
    for age in range(STEP, OLDEST + 1):
        before = start[age - STEP] + (start[OLDEST] if age == OLDEST else 0.0)
        if before > 0:
            out[age] = end[age] / before
    return np.clip(out, *RATIO_BOUNDS)


def step(now: np.ndarray, change: np.ndarray, infants_per_parent: float) -> np.ndarray:
    nxt = np.zeros(OLDEST + 1)
    for age in range(STEP, OLDEST):
        nxt[age] = now[age - STEP] * change[age]
    nxt[OLDEST] = (now[OLDEST - STEP] + now[OLDEST - 1] + now[OLDEST]) * change[OLDEST]
    parents = nxt[PARENT_AGES[0] : PARENT_AGES[1] + 1].sum()
    infants = infants_per_parent * parents
    share = now[0] / max(now[0] + now[1], 1e-9)
    nxt[0], nxt[1] = infants * share, infants * (1 - share)
    return nxt


def infant_ratio(ages: np.ndarray) -> float:
    return float(ages[:STEP].sum() / max(ages[PARENT_AGES[0] : PARENT_AGES[1] + 1].sum(), 1e-9))


def cohorts(ages: np.ndarray) -> dict[str, float]:
    return {name: float(ages[low : high + 1].sum()) for name, (low, high) in COHORTS.items()}


def project(
    history: dict[int, np.ndarray], base: int, horizon: int, scenario: str
) -> dict[int, np.ndarray]:
    now = history[base]
    if scenario == "ageing":
        change = np.ones(OLDEST + 1)
    elif scenario == "trend":
        change = ratios(history[base - STEP], now)
    else:
        first = ratios(history[base - 2 * STEP], history[base - STEP])
        second = ratios(history[base - STEP], now)
        change = np.sqrt(first * second)
    result = {base: now}
    infants = infant_ratio(now)
    year = base
    while year < horizon:
        result[year + STEP] = step(result[year], change, infants)
        year += STEP
    for odd in range(base + 1, horizon, STEP):
        result[odd] = np.sqrt(result[odd - 1] * result[odd + 1])
    return dict(sorted(result.items()))


def error(predicted: dict[str, float], observed: dict[str, float]) -> dict[str, float]:
    return {name: predicted[name] / observed[name] - 1 for name in COHORTS}


def city_table(table: pd.DataFrame) -> dict[int, np.ndarray]:
    rows = table[(table["district"] == "City") & (table["age"] != "Всего")].copy()
    rows["age"] = rows["age"].map(lambda age: OLDEST if age == f"{OLDEST}+" else int(age))
    wide = (
        rows.groupby(["year", "age"])["people"]
        .sum()
        .unstack("age")
        .reindex(columns=range(OLDEST + 1), fill_value=0.0)
    )
    return {int(year): wide.loc[year].to_numpy() for year in wide.index}


def controlled(
    city: dict[int, np.ndarray], districts: dict[str, dict[int, np.ndarray]]
) -> dict[str, dict[int, dict[str, float]]]:
    out = {group: {} for group in districts}
    for year, ages in city.items():
        totals = cohorts(ages)
        parts = {group: cohorts(path[year]) for group, path in districts.items()}
        for name in COHORTS:
            denominator = sum(part[name] for part in parts.values())
            for group, part in parts.items():
                out[group].setdefault(year, {})[name] = totals[name] * part[name] / denominator
    return out


def district_scenario(scenario: str) -> str:
    return "ageing" if scenario == "ageing" else "trend"


def backtest(wide: pd.DataFrame, groups: list[str], city: dict[int, np.ndarray]) -> dict:
    out = {}
    for scenario in ("ageing", "trend", "average"):
        districts = {
            group: project(
                {year: wide.loc[(group, year)].to_numpy() for year in (2022, 2024)},
                2024,
                2026,
                district_scenario(scenario),
            )
            for group in groups
        }
        city_path = project(city, 2024, 2026, scenario)
        joint = controlled(
            {2026: city_path[2026]}, {g: {2026: p[2026]} for g, p in districts.items()}
        )
        fixed = controlled(
            {2026: city_path[2026]},
            {g: {2026: wide.loc[(g, 2024)].to_numpy()} for g in groups},
        )
        free, tied, still = {}, {}, {}
        for group in groups:
            observed = cohorts(wide.loc[(group, 2026)].to_numpy())
            free[group] = error(cohorts(districts[group][2026]), observed)
            tied[group] = error(joint[group][2026], observed)
            still[group] = error(fixed[group][2026], observed)
        out[scenario] = {
            "district_only": pd.DataFrame(free).T.abs().mean().round(4).to_dict(),
            "controlled_to_city": pd.DataFrame(tied).T.abs().mean().round(4).to_dict(),
            "constant_share": pd.DataFrame(still).T.abs().mean().round(4).to_dict(),
            "controlled_by_group": pd.DataFrame(tied).T.round(4).to_dict(orient="index"),
            "constant_share_by_group": pd.DataFrame(still).T.round(4).to_dict(orient="index"),
        }
    return out


def city_backtest(city: dict[int, np.ndarray]) -> dict:
    out = {}
    for scenario in ("ageing", "trend", "average"):
        two = project(city, 2024, 2026, scenario)[2026]
        four = project(city, 2022, 2026, scenario)[2026]
        observed = cohorts(city[2026])
        out[scenario] = {
            "two_years": {k: round(v, 4) for k, v in error(cohorts(two), observed).items()},
            "four_years": {k: round(v, 4) for k, v in error(cohorts(four), observed).items()},
        }
    return out


def run() -> dict:
    table = stat_ages.load()
    wide = ages_table(table)
    city = city_table(table)
    groups = sorted(wide.index.get_level_values("group").unique())
    report = {
        "method": "Hamilton-Perry cohort change ratios over two-year steps for the city; "
        "districts take their share of each cohort from their own projection; "
        "children aged 0-1 from their ratio to adults aged 20-39",
        "cohorts": {name: list(bounds) for name, bounds in COHORTS.items()},
        "groups": groups,
        "observed": {
            group: {
                str(year): cohorts(wide.loc[(group, year)].to_numpy())
                for year in range(2022, BASE_YEAR + 1)
            }
            for group in groups
        }
        | {"City": {str(year): cohorts(city[year]) for year in range(2016, BASE_YEAR + 1)}},
        "projection": {},
        "backtest_districts_2024_2026": backtest(wide, groups, city),
        "backtest_city": city_backtest(city),
    }
    for scenario in ("ageing", "average", "trend"):
        city_path = project(city, BASE_YEAR, HORIZON, scenario)
        districts = {
            group: project(
                {year: wide.loc[(group, year)].to_numpy() for year in (2024, 2026)},
                BASE_YEAR,
                HORIZON,
                district_scenario(scenario),
            )
            for group in groups
        }
        joint = controlled(city_path, districts)
        report["projection"][scenario] = {
            group: {str(year): values for year, values in joint[group].items()} for group in groups
        } | {"City": {str(year): cohorts(ages) for year, ages in city_path.items()}}
        base = {
            g: {year: wide.loc[(g, BASE_YEAR)].to_numpy() for year in city_path} for g in groups
        }
        fixed = controlled(city_path, base)
        report.setdefault("projection_constant_share", {})[scenario] = {
            group: {str(year): values for year, values in fixed[group].items()} for group in groups
        }
    (REPORTS / "demography_2030.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    for scenario, values in result["projection"].items():
        for group in ("City", "Nura", "Esil"):
            path = values[group]
            print(
                scenario,
                group,
                {
                    y: {k: round(v / 1000, 1) for k, v in path[y].items()}
                    for y in ("2026", "2028", "2030")
                },
            )
    print(json.dumps(result["backtest_districts_2024_2026"], indent=1)[:2500])
    print(json.dumps(result["backtest_city"], indent=1))


def school_age_factors(year: int = 2028) -> pd.DataFrame:
    path = REPORTS / "demography_2030.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else run()
    rows = {}
    for group in report["groups"]:
        base = report["observed"][group][str(BASE_YEAR)]["school"]
        rows[group] = {
            "school_age_2026": base,
            "ageing_2028": report["projection"]["ageing"][group][str(year)]["school"],
            "cohort_2028": report["projection"]["trend"][group][str(year)]["school"],
        }
    frame = pd.DataFrame(rows).T
    frame["ageing_factor"] = frame["ageing_2028"] / frame["school_age_2026"]
    frame["cohort_factor"] = frame["cohort_2028"] / frame["school_age_2026"]
    return frame

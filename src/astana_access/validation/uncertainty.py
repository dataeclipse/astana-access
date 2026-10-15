import json

import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.accessibility.coverage import origin_destination
from astana_access.accessibility.e2sfca import gaussian, load_inputs, supply_measures
from astana_access.accessibility.network import load
from astana_access.config import PROCESSED, REPORTS, SEED
from astana_access.equity.analysis import BASE
from astana_access.population.model import (
    DEFAULT_ALPHA,
    OFFICIAL_2026,
    error_against_official,
    house_factor,
)
from astana_access.viz.dashboard import greedy, sites

DRAWS = 200
ALPHA_RANGE = (0.0, 0.3)
NOISE_GRID = tuple(np.round(np.arange(0.05, 1.01, 0.05), 2))
CALIBRATION_DRAWS = 200
RADIUS_M = 1000
SITES_COMPARED = 17
NORM_M = {"school": 500, "preschool": 300}
QUANTILES = (0.05, 0.5, 0.95)


def dwelling_table(points: pd.DataFrame) -> pd.DataFrame:
    dwellings = pd.read_parquet(
        PROCESSED / "dwellings.parquet",
        columns=["id", "station", "form", "floor_area_m2", "pop_station"],
    )
    buildings = pd.read_parquet(
        PROCESSED / "buildings.parquet", columns=["id", "p_residential", "label_source", "district"]
    )
    dwellings = dwellings.merge(buildings, on="id", how="left")
    dwellings["point_id"] = "b" + dwellings["id"].astype(str)
    located = points[points["kind"] == "dwelling"].set_index("point_id")
    dwellings = dwellings[dwellings["point_id"].isin(located.index)].reset_index(drop=True)
    dwellings["unit"] = dwellings["district"]
    dwellings["area"] = dwellings["point_id"].map(located["district"])
    dwellings = dwellings[dwellings["unit"].isin(OFFICIAL_2026)].reset_index(drop=True)
    factor, _ = house_factor(dwellings)
    dwellings["weight"] = dwellings["floor_area_m2"] * np.where(
        dwellings["form"] == "house", factor, 1.0
    )
    dwellings["keep_p"] = np.where(
        dwellings["label_source"] == "model", dwellings["p_residential"], 1.0
    )
    for cohort in ("school", "preschool"):
        ratio = located[f"{cohort}_station"] / dwellings.set_index("point_id")[
            "pop_station"
        ].reindex(located.index)
        dwellings[f"{cohort}_share"] = dwellings["point_id"].map(ratio).fillna(0.0).to_numpy()
    return dwellings


def allocate(
    dwellings: pd.DataFrame, weight: np.ndarray, alpha: float, noise: np.ndarray | None
) -> np.ndarray:
    station_code, stations = pd.factorize(dwellings["station"])
    station_weight = np.bincount(station_code, weights=weight, minlength=len(stations))
    unit_of = (
        dwellings.groupby(station_code)["unit"]
        .agg(lambda values: values.mode().iat[0])
        .reindex(range(len(stations)))
    )
    tempered = np.where(station_weight > 0, station_weight**alpha, 0.0)
    if noise is not None:
        tempered = tempered * noise[: len(stations)]
    unit_sum = pd.Series(tempered).groupby(unit_of.to_numpy()).transform("sum").to_numpy()
    share = np.divide(tempered, unit_sum, out=np.zeros_like(tempered), where=unit_sum > 0)
    station_population = share * unit_of.map(OFFICIAL_2026).to_numpy()
    within = np.divide(
        weight,
        station_weight[station_code],
        out=np.zeros_like(weight),
        where=station_weight[station_code] > 0,
    )
    return within * station_population[station_code]


def calibrate(dwellings: pd.DataFrame, rng: np.random.Generator) -> dict:
    station_code, stations = pd.factorize(dwellings["station"])
    station_weight = np.bincount(
        station_code, weights=dwellings["weight"].to_numpy(), minlength=len(stations)
    )
    unit_of = (
        dwellings.groupby(station_code)["unit"]
        .agg(lambda values: values.mode().iat[0])
        .reindex(range(len(stations)))
        .to_numpy()
    )
    model = station_weight**DEFAULT_ALPHA
    observed = error_against_official(pd.Series(model).groupby(unit_of).sum())["mean_abs_error"]
    curve = {}
    for sigma in NOISE_GRID:
        errors = []
        for _ in range(CALIBRATION_DRAWS):
            truth = (
                pd.Series(model * rng.lognormal(-0.5 * sigma**2, sigma, len(model)))
                .groupby(unit_of)
                .sum()
            )
            estimate = pd.Series(model).groupby(unit_of).sum()
            ratio = (estimate / estimate.sum()) / (truth / truth.sum())
            errors.append(float((ratio - 1).abs().mean()))
        curve[float(sigma)] = float(np.median(errors))
    sigma = min(curve, key=lambda s: abs(curve[s] - observed))
    return {
        "observed_district_error": float(observed),
        "sigma": float(sigma),
        "median_error_by_sigma": curve,
        "stations": int(len(stations)),
    }


class FastIndex:
    def __init__(
        self, od: pd.DataFrame, point_ids: pd.Index, supply: pd.Series, d0: float, d0_load: float
    ):
        table = od[od["point_id"].isin(point_ids)]
        self.points = len(point_ids)
        position = pd.Series(np.arange(len(point_ids)), index=point_ids)
        load = table[table["distance_m"] <= d0_load]
        self.load_point = position.reindex(load["point_id"]).to_numpy()
        self.load_facility, facilities = pd.factorize(load["facility_id"])
        weight = gaussian(load["distance_m"].to_numpy(dtype=float), d0_load)
        total = np.bincount(self.load_point, weights=weight, minlength=self.points)
        self.load_share = np.divide(
            weight,
            total[self.load_point],
            out=np.zeros_like(weight),
            where=total[self.load_point] > 0,
        )
        self.supply = supply.reindex(facilities).to_numpy(dtype=float)
        reach = table[table["distance_m"] <= d0]
        self.reach_point = position.reindex(reach["point_id"]).to_numpy()
        code = pd.Series(np.arange(len(facilities)), index=facilities)
        self.reach_facility = code.reindex(reach["facility_id"]).to_numpy()
        self.reach_known = ~np.isnan(self.reach_facility)
        self.reach_facility = np.nan_to_num(self.reach_facility).astype(int)
        self.reach_weight = (
            gaussian(reach["distance_m"].to_numpy(dtype=float), d0) * self.reach_known
        )
        self.facilities = len(facilities)

    def __call__(self, demand: np.ndarray) -> np.ndarray:
        load = np.bincount(
            self.load_facility,
            weights=demand[self.load_point] * self.load_share,
            minlength=self.facilities,
        )
        ratio = np.divide(self.supply, load, out=np.zeros_like(load), where=load > 0)
        ratio = np.nan_to_num(ratio)
        return np.bincount(
            self.reach_point,
            weights=ratio[self.reach_facility] * self.reach_weight,
            minlength=self.points,
        )


def district_relative(
    access: np.ndarray, demand: np.ndarray, district: np.ndarray
) -> dict[str, float]:
    inside = district != "none"
    access, demand, district = access[inside], demand[inside], district[inside]
    mean = float(np.sum(access * demand) / demand.sum())
    frame = pd.DataFrame({"aw": access * demand, "w": demand, "d": district})
    grouped = frame.groupby("d")[["aw", "w"]].sum()
    return (grouped["aw"] / grouped["w"] / mean).to_dict()


def band(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {f"q{int(q * 100):02d}": float(np.quantile(array, q)) for q in QUANTILES} | {
        "mean": float(array.mean())
    }


def site_reach(
    points: pd.DataFrame, ids: pd.Index, uncovered: np.ndarray
) -> tuple[dict[str, list[int]], np.ndarray, list[str]]:
    plan, pdp = sites()
    new = plan[plan["kind"] == "new"]
    candidates = gpd.GeoDataFrame(
        pd.concat(
            [new[["facility_id", "geometry"]], pdp[["facility_id", "geometry"]]], ignore_index=True
        ),
        geometry="geometry",
        crs=pdp.crs,
    )
    reach = origin_destination(load(), points, candidates, "facility_id")
    reach = reach[(reach["distance_m"] <= RADIUS_M) & reach["point_id"].isin(ids)]
    position = pd.Series(np.arange(len(ids)), index=ids)
    lists = {
        fid: sorted(position[p] for p in group["point_id"] if uncovered[position[p]])
        for fid, group in reach.groupby("facility_id")
    }
    plan_points = np.zeros(len(ids), dtype=bool)
    for fid in new["facility_id"]:
        plan_points[lists.get(fid, [])] = True
    return lists, plan_points, list(pdp["facility_id"])


def run(draws: int = DRAWS) -> dict:
    rng = np.random.default_rng(SEED)
    points, od = load_inputs()
    dwellings = dwelling_table(points)
    ids = pd.Index(dwellings["point_id"])
    district = dwellings["area"].fillna("none").to_numpy()
    calibration = calibrate(dwellings, rng)
    sigma = calibration["sigma"]

    supplies = supply_measures()
    index = {
        kind: FastIndex(od[kind], ids, supplies[kind][base["supply"]], base["d0"], base["d0_load"])
        for kind, base in BASE.items()
    }
    nearest = {
        kind: od[kind]
        .groupby("point_id")["distance_m"]
        .min()
        .reindex(ids)
        .fillna(np.inf)
        .to_numpy()
        for kind in NORM_M
    }
    uncovered = nearest["school"] > RADIUS_M
    lists, plan_points, pdp_ids = site_reach(points, ids, uncovered)

    noise_size = dwellings["station"].nunique()
    fixed = np.zeros(len(ids), dtype=bool)
    rows = []
    for draw in range(draws + 1):
        if draw == 0:
            alpha, noise, keep = DEFAULT_ALPHA, None, np.ones(len(dwellings), dtype=bool)
        else:
            alpha = float(rng.uniform(*ALPHA_RANGE))
            noise = rng.lognormal(-0.5 * sigma**2, sigma, noise_size)
            keep = rng.random(len(dwellings)) < dwellings["keep_p"].to_numpy()
        population = allocate(dwellings, dwellings["weight"].to_numpy() * keep, alpha, noise)
        row = {"draw": draw, "alpha": alpha}
        for cohort in ("school", "preschool"):
            demand = population * dwellings[f"{cohort}_share"].to_numpy()
            access = index[cohort](demand)
            relative = district_relative(access, demand, district)
            row |= {f"{cohort}_rel_{d}": v for d, v in relative.items()}
            row[f"{cohort}_worst"] = min(relative, key=relative.get)
            row[f"{cohort}_norm_share"] = float(
                demand[nearest[cohort] <= NORM_M[cohort]].sum() / demand.sum()
            )
            if cohort == "school":
                children = demand * uncovered
                row["uncovered"] = float(children.sum())
                row["plan_reach"] = float(children[plan_points].sum())
                order = greedy(lists, list(children), pdp_ids)
                row["best_reach"] = (
                    float(order[SITES_COMPARED - 1]["cumulative"])
                    if len(order) >= SITES_COMPARED
                    else float("nan")
                )
                row["best_over_plan"] = row["best_reach"] / row["plan_reach"]
                if draw == 0:
                    for item in order[:SITES_COMPARED]:
                        fixed[lists[item["id"]]] = True
                row["fixed_reach"] = float(children[fixed].sum())
                row["fixed_over_plan"] = row["fixed_reach"] / row["plan_reach"]
                row["plan_share"] = row["plan_reach"] / row["uncovered"]
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame.to_csv(REPORTS / "uncertainty_draws.csv", index=False)
    base, sample = frame.iloc[0], frame.iloc[1:]
    numeric = [c for c in frame.columns if c not in ("draw", "school_worst", "preschool_worst")]
    report = {
        "draws": int(draws),
        "alpha_range": list(ALPHA_RANGE),
        "calibration": calibration,
        "dwellings": int(len(dwellings)),
        "model_decided_dwellings": int((dwellings["label_source"] == "model").sum()),
        "baseline": {c: float(base[c]) for c in numeric}
        | {"school_worst": base["school_worst"], "preschool_worst": base["preschool_worst"]},
        "bands": {c: band(sample[c]) for c in numeric if c != "alpha"},
        "worst_district": {
            kind: sample[f"{kind}_worst"].value_counts().to_dict()
            for kind in ("school", "preschool")
        },
        "best_beats_plan_share": float((sample["best_reach"] > sample["plan_reach"]).mean()),
        "best_over_plan_at_least_2": float((sample["best_over_plan"] >= 2).mean()),
        "fixed_beats_plan_share": float((sample["fixed_reach"] > sample["plan_reach"]).mean()),
        "fixed_over_plan_at_least_2": float((sample["fixed_over_plan"] >= 2).mean()),
    }
    (REPORTS / "uncertainty.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False)[:3000])

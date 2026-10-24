import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from astana_access.accessibility.e2sfca import DECAY, load_inputs, supply_measures
from astana_access.accessibility.official_catchments import assigned_dwellings
from astana_access.config import PROCESSED, REPORTS
from astana_access.equity.analysis import BASE

BETA_KM = (0.1, 5.0)
FLOOR = 1e-12


def enrolment_by_school(facilities: pd.Index) -> tuple[pd.Series, int]:
    from astana_access.ingest import school_register

    register = school_register.linked().dropna(subset=["facility_id"])
    table = register.groupby("facility_id")[["enrolment_2025", "capacity"]].sum()
    enrolment = table["enrolment_2025"].reindex(facilities)
    per_place = (table["enrolment_2025"] / table["capacity"]).median()
    capacity = supply_measures()["school"]["capacity"].reindex(facilities)
    missing = enrolment.isna() | (enrolment <= 0)
    enrolment[missing] = capacity[missing] * per_place
    return enrolment, int(missing.sum())


def weights(distance_m: np.ndarray, beta_km: float) -> np.ndarray:
    return np.exp(-np.asarray(distance_m, dtype=float) / 1000.0 / beta_km)


class Flows:
    """Each school draws its pupils from the children within walking reach.

    A school j receives from dwelling i a share of its enrolment proportional to the
    children of i times a decay of the walking distance, so that the pupils of every
    school equal its official enrolment. Nothing is iterated and no origin is forced
    to send exactly its children; the balance of the origins is reported instead.
    """

    def __init__(self, od: pd.DataFrame, children: pd.Series, enrolment: pd.Series) -> None:
        table = od[od["point_id"].isin(children.index[children > 0])].reset_index(drop=True)
        self.table = table
        self.points = pd.Index(table["point_id"].unique())
        self.schools = pd.Index(table["facility_id"].unique())
        self.i = self.points.get_indexer(table["point_id"])
        self.j = self.schools.get_indexer(table["facility_id"])
        self.origin = children.reindex(self.points).to_numpy(dtype=float)
        self.destination = enrolment.reindex(self.schools).to_numpy(dtype=float)
        self.distance = table["distance_m"].to_numpy(dtype=float)

    def flow(self, beta_km: float) -> np.ndarray:
        mass = self.origin[self.i] * weights(self.distance, beta_km)
        column = np.bincount(self.j, weights=mass, minlength=len(self.schools))
        return self.destination[self.j] * mass / column[self.j]

    def frame(self, beta_km: float) -> pd.DataFrame:
        return self.table.assign(children=self.flow(beta_km))

    def balance(self, beta_km: float) -> dict:
        drawn = np.bincount(self.i, weights=self.flow(beta_km), minlength=len(self.points))
        share = self.destination.sum() / self.origin.sum()
        ratio = drawn / (self.origin * share)
        return {
            "state_share": float(share),
            "children_reachable": float(self.origin.sum()),
            "drawn_over_available_median": float(np.median(ratio)),
            "drawn_over_available_p10": float(np.quantile(ratio, 0.1)),
            "drawn_over_available_p90": float(np.quantile(ratio, 0.9)),
            "dwellings_drawn_beyond_double": float(np.mean(ratio > 2.0)),
        }


def official_rows(od: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    rows = od[od["point_id"].isin(pairs["point_id"].unique())].copy()
    mark = pairs[["point_id", "facility_id"]].drop_duplicates().assign(official=True)
    rows = rows.merge(mark, on=["point_id", "facility_id"], how="left")
    rows["official"] = rows["official"].fillna(False).astype(bool)
    reachable = rows.groupby("point_id")["official"].transform("any")
    rows = rows[reachable].reset_index(drop=True)
    rows["code"] = pd.factorize(rows["point_id"])[0]
    return rows


def mass_on_official(rows: pd.DataFrame, probability: np.ndarray) -> np.ndarray:
    code = rows["code"].to_numpy()
    total = np.bincount(code, weights=probability)
    mine = np.bincount(code, weights=probability * rows["official"].to_numpy())
    return mine / np.where(total > 0, total, np.nan)


def per_dwelling(rows: pd.DataFrame, probability: np.ndarray) -> pd.DataFrame:
    frame = rows[["point_id", "official"]].assign(p=probability)
    total = frame.groupby("point_id")["p"].transform("sum").replace(0.0, np.nan)
    frame["p"] = frame["p"] / total
    mass = (frame["p"] * frame["official"]).groupby(frame["point_id"]).sum()
    frame = frame.sort_values(["point_id", "p"], ascending=[True, False])
    frame["rank"] = frame.groupby("point_id").cumcount() + 1
    top1 = frame[frame["rank"] == 1].set_index("point_id")["official"]
    top3 = frame[frame["rank"] <= 3].groupby("point_id")["official"].any()
    return pd.DataFrame({"mass": mass, "top1": top1, "top3": top3}).fillna(0.0)


def summarise(table: pd.DataFrame) -> dict:
    return {
        "dwellings": int(len(table)),
        "mass_on_official": round(float(table["mass"].mean()), 3),
        "top1": round(float(table["top1"].mean()), 3),
        "top3": round(float(table["top3"].mean()), 3),
    }


def fit_beta(objective, keep: np.ndarray | None = None) -> float:
    def loss(beta: float) -> float:
        mass = np.nan_to_num(objective(beta))
        mass = mass if keep is None else mass[keep]
        return -float(np.log(np.clip(mass, FLOOR, None)).sum())

    return float(minimize_scalar(loss, bounds=BETA_KM, method="bounded").x)


def flow_summary(flows: pd.DataFrame) -> dict:
    nearest = flows.groupby("point_id")["distance_m"].transform("min")
    total = flows["children"].sum()
    distance = flows["distance_m"].to_numpy()
    weight = flows["children"].to_numpy()
    order = np.argsort(distance)
    cumulative = np.cumsum(weight[order]) / total
    return {
        "mean_distance_m": float((distance * weight).sum() / total),
        "median_distance_m": float(distance[order][np.searchsorted(cumulative, 0.5)]),
        "p90_distance_m": float(distance[order][np.searchsorted(cumulative, 0.9)]),
        "share_to_nearest_school": float(weight[flows["distance_m"] == nearest].sum() / total),
        "share_beyond_1000m": float(weight[distance > 1000].sum() / total),
        "share_beyond_1500m": float(weight[distance > 1500].sum() / total),
    }


def run() -> dict:
    points, od = load_inputs()
    od_school = od["school"]
    dwellings = points[points["kind"] == "dwelling"].set_index("point_id")
    children = dwellings["school_station"].fillna(0.0)
    schools = pd.Index(od_school["facility_id"].unique())
    enrolment, filled = enrolment_by_school(schools)
    model = Flows(od_school, children, enrolment)

    pairs = assigned_dwellings()
    district = pairs.drop_duplicates("point_id").set_index("point_id")["district"]
    rows = official_rows(model.table, pairs)
    key = pd.MultiIndex.from_frame(model.table[["point_id", "facility_id"]])
    position = key.get_indexer(pd.MultiIndex.from_frame(rows[["point_id", "facility_id"]]))

    def constrained(beta: float) -> np.ndarray:
        return mass_on_official(rows, model.flow(beta)[position])

    def unconstrained(beta: float) -> np.ndarray:
        return mass_on_official(rows, weights(rows["distance_m"], beta))

    beta = fit_beta(constrained)
    beta_free = fit_beta(unconstrained)
    nearest = rows.groupby("point_id")["distance_m"].transform("min")
    base = BASE["school"]
    gaussian = DECAY[base["decay"]](rows["distance_m"].to_numpy(dtype=float), base["d0_load"])
    tables = {
        "nearest_school": per_dwelling(rows, np.where(rows["distance_m"] == nearest, 1.0, 1e-9)),
        "e2sfca_gaussian_share": per_dwelling(rows, gaussian + 1e-12),
        "decay_fitted_without_enrolment": per_dwelling(
            rows, weights(rows["distance_m"], beta_free)
        ),
        "gravity_with_enrolment": per_dwelling(rows, model.flow(beta)[position] + 1e-12),
    }

    ordered = pd.Series(pd.unique(rows["point_id"]))
    home = ordered.map(district)
    held = {}
    for name in sorted(home.dropna().unique()):
        beta_out = fit_beta(constrained, (home != name).to_numpy())
        table = per_dwelling(rows, model.flow(beta_out)[position] + 1e-12)
        held[name] = {"beta_km": round(beta_out, 3)} | summarise(
            table[table.index.map(district) == name]
        )

    flows = model.frame(beta)
    flows["share"] = flows["children"] / flows.groupby("point_id")["children"].transform("sum")
    flows[["point_id", "facility_id", "children", "share"]].astype(
        {"children": "float32", "share": "float32"}
    ).to_parquet(PROCESSED / "flows.parquet")
    report = {
        "beta_km": round(beta, 3),
        "beta_without_enrolment_km": round(beta_free, 3),
        "enrolment_filled_schools": filled,
        "schools": int(len(schools)),
        "official_dwellings_evaluated": int(len(tables["nearest_school"])),
        "agreement_with_official_territories": {k: summarise(v) for k, v in tables.items()},
        "leave_one_district_out": held,
        "balance_of_origins": model.balance(beta),
        "flows": flow_summary(flows),
        "children_in_dwellings": float(children.sum()),
        "children_unreached": float(children.sum() - model.origin.sum()),
    }
    (REPORTS / "flows.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False, default=float))

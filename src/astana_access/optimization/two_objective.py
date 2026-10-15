import json

import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.accessibility.coverage import origin_destination
from astana_access.accessibility.e2sfca import gaussian, load_inputs
from astana_access.accessibility.network import load
from astana_access.config import PROCESSED, REPORTS
from astana_access.equity.analysis import BASE
from astana_access.ingest import school_register
from astana_access.viz.dashboard import sites

RADIUS_M = 1000
SITES = 17
SHIFTS = 2
DEFAULT_SEATS = 1200.0
WEIGHTS = tuple(np.round(np.linspace(0, 1, 11), 2))
TOP_SHARE = 0.25


def excess_rate() -> pd.Series:
    register = school_register.linked().dropna(subset=["facility_id", "capacity", "enrolment_2025"])
    table = register.groupby("facility_id")[["capacity", "enrolment_2025"]].sum()
    excess = (table["enrolment_2025"] - SHIFTS * table["capacity"]).clip(lower=0)
    return excess / table["enrolment_2025"]


def crowded_pupils(points: pd.DataFrame, od: pd.DataFrame, rate: pd.Series) -> pd.Series:
    dwellings = points[points["kind"] == "dwelling"].set_index("point_id")
    children = dwellings["school_station"].fillna(0)
    d0 = BASE["school"]["d0_load"]
    table = od[(od["distance_m"] <= d0) & od["point_id"].isin(children.index)].copy()
    table["w"] = gaussian(table["distance_m"].to_numpy(dtype=float), d0)
    total = table.groupby("point_id")["w"].transform("sum")
    table["share"] = (table["w"] / total.replace(0, np.nan)).fillna(0)
    table["pupils"] = (
        table["point_id"].map(children) * table["share"] * table["facility_id"].map(rate).fillna(0)
    )
    return table.groupby("point_id")["pupils"].sum().reindex(children.index).fillna(0)


def greedy(
    lists: dict[str, tuple[np.ndarray, np.ndarray]],
    deficit: np.ndarray,
    relief: np.ndarray,
    caps: dict[str, float],
    weight: float,
    scale: tuple[float, float],
    k: int,
) -> list[dict]:
    taken_d = np.zeros(len(deficit), dtype=bool)
    taken_r = np.zeros(len(relief), dtype=bool)
    chosen, order = set(), []
    total_d = total_r = 0.0
    for _ in range(k):
        best = None
        for site, (near_d, near_r) in lists.items():
            if site in chosen:
                continue
            gain_d = float(deficit[near_d][~taken_d[near_d]].sum())
            gain_r = min(float(relief[near_r][~taken_r[near_r]].sum()), caps[site])
            score = weight * gain_d / scale[0] + (1 - weight) * gain_r / scale[1]
            if best is None or score > best[0]:
                best = (score, site, gain_d, gain_r)
        if best is None or best[0] <= 0:
            break
        _, site, gain_d, gain_r = best
        chosen.add(site)
        taken_d[lists[site][0]] = True
        taken_r[lists[site][1]] = True
        total_d += gain_d
        total_r += gain_r
        order.append({"id": site, "deficit": total_d, "relief": total_r})
    return order


def totals(chosen: list[str], lists, deficit, relief, caps) -> tuple[float, float]:
    taken_d = np.zeros(len(deficit), dtype=bool)
    taken_r = np.zeros(len(relief), dtype=bool)
    total_r = 0.0
    for site in chosen:
        near_d, near_r = lists.get(site, (np.array([], int), np.array([], int)))
        taken_d[near_d] = True
        gain = float(relief[near_r][~taken_r[near_r]].sum())
        total_r += min(gain, caps.get(site, np.inf))
        taken_r[near_r] = True
    return float(deficit[taken_d].sum()), total_r


def run() -> dict:
    points, od = load_inputs()
    dwellings = points[points["kind"] == "dwelling"]
    ids = pd.Index(dwellings["point_id"])
    children = dwellings.set_index("point_id")["school_station"].fillna(0).reindex(ids).to_numpy()
    nearest = od["school"].groupby("point_id")["distance_m"].min().reindex(ids).fillna(np.inf)
    deficit = children * (nearest.to_numpy() > RADIUS_M)
    rate = excess_rate()
    relief = crowded_pupils(points, od["school"], rate).reindex(ids).to_numpy()

    plan, pdp = sites()
    new = plan[plan["kind"] == "new"]
    candidates = gpd.GeoDataFrame(
        pd.concat(
            [new[["facility_id", "geometry"]], pdp[["facility_id", "geometry"]]], ignore_index=True
        ),
        geometry="geometry",
        crs=pdp.crs,
    )
    reach = origin_destination(load(), dwellings, candidates, "facility_id")
    reach = reach[reach["distance_m"] <= RADIUS_M]
    position = pd.Series(np.arange(len(ids)), index=ids)
    lists = {}
    for site, group in reach.groupby("facility_id"):
        near = position.reindex(group["point_id"]).dropna().astype(int).to_numpy()
        lists[site] = (near[deficit[near] > 0], near[relief[near] > 0])
    seats = pdp.set_index("facility_id")["seats"].astype(float).fillna(DEFAULT_SEATS)
    caps = {site: SHIFTS * seats.get(site, DEFAULT_SEATS) for site in pdp["facility_id"]}
    caps |= dict(zip(new["facility_id"], new["seats"].astype(float), strict=True))
    pdp_lists = {site: lists[site] for site in pdp["facility_id"] if site in lists}

    alone = {
        site: (float(deficit[d].sum()), min(float(relief[r].sum()), caps[site]))
        for site, (d, r) in pdp_lists.items()
    }
    best_d = greedy(pdp_lists, deficit, relief, caps, 1.0, (1.0, 1.0), SITES)[-1]["deficit"]
    best_r = greedy(pdp_lists, deficit, relief, caps, 0.0, (1.0, 1.0), SITES)[-1]["relief"]
    scale = (best_d, best_r)
    rankings = {
        name: greedy(pdp_lists, deficit, relief, caps, weight, scale, len(pdp_lists))
        for name, weight in (("distance", 1.0), ("crowding", 0.0), ("both", 0.5))
    }
    frontier = []
    for weight in WEIGHTS:
        order = greedy(pdp_lists, deficit, relief, caps, float(weight), scale, SITES)
        frontier.append(
            {
                "weight_distance": float(weight),
                "deficit": order[-1]["deficit"],
                "relief": order[-1]["relief"],
                "sites": [item["id"] for item in order],
            }
        )
    plan_d, plan_r = totals(list(new["facility_id"]), lists, deficit, relief, caps)
    values = pd.DataFrame(alone, index=["deficit", "relief"]).T
    reaching = values[(values["deficit"] > 0) | (values["relief"] > 0)]
    threshold_d = reaching["deficit"].quantile(1 - TOP_SHARE)
    threshold_r = reaching["relief"].quantile(1 - TOP_SHARE)
    both = values[(values["deficit"] >= threshold_d) & (values["relief"] >= threshold_r)]
    balanced = frontier[len(WEIGHTS) // 2]
    dominating = [
        point for point in frontier if point["deficit"] >= plan_d and point["relief"] >= plan_r
    ]
    report = {
        "radius_m": RADIUS_M,
        "relief_pool": float(relief.sum()),
        "deficit_pool": float(deficit.sum()),
        "plan": {"deficit": plan_d, "relief": plan_r},
        "best_distance_only": {
            "deficit": best_d,
            "relief": rankings["distance"][SITES - 1]["relief"],
        },
        "best_crowding_only": {
            "deficit": rankings["crowding"][SITES - 1]["deficit"],
            "relief": best_r,
        },
        "balanced": {k: balanced[k] for k in ("deficit", "relief")},
        "frontier": frontier,
        "frontier_sets_dominating_plan": len(dominating),
        "sites_good_for_both": sorted(both.index.tolist()),
        "thresholds": {"deficit": float(threshold_d), "relief": float(threshold_r)},
        "alone": {site: {"deficit": d, "relief": r} for site, (d, r) in alone.items()},
        "rankings": {
            name: [
                {
                    "id": item["id"],
                    "deficit": round(item["deficit"]),
                    "relief": round(item["relief"]),
                }
                for item in order
            ]
            for name, order in rankings.items()
        },
    }
    (REPORTS / "two_objective.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    used = sorted({int(i) for _, near in lists.values() for i in near})
    compact = {old: new_index for new_index, old in enumerate(used)}
    atlas = {
        "relief": [round(float(relief[i]), 2) for i in used],
        "sites": {site: [compact[int(i)] for i in near] for site, (_, near) in lists.items()},
        "caps": {site: float(cap) for site, cap in caps.items()},
    }
    (PROCESSED / "two_objective_atlas.json").write_text(json.dumps(atlas), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("alone", "rankings", "frontier")},
            indent=1,
        )
    )
    for point in result["frontier"]:
        print(point["weight_distance"], round(point["deficit"]), round(point["relief"]))

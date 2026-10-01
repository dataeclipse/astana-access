import itertools
import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from astana_access.accessibility.coverage import VARIANTS, facilities
from astana_access.accessibility.e2sfca import index, load_inputs, supply_measures
from astana_access.config import PROCESSED, REPORTS, SEED
from astana_access.equity.inequality import gini, local_moran, neighbours, theil

COHORT = {"school": "school", "preschool": "preschool"}
BASE = {
    "school": {
        "variant": "station",
        "supply": "floor_area",
        "decay": "gaussian",
        "d0": 1500,
        "d0_load": 3000,
    },
    "preschool": {
        "variant": "station",
        "supply": "class_mean",
        "decay": "gaussian",
        "d0": 1000,
        "d0_load": 2000,
    },
}
GRID = {
    "variant": VARIANTS,
    "decay": ("gaussian", "linear", "step"),
    "d0": {"school": (1000, 1500), "preschool": (500, 1000)},
}
DEFICIT_SHARE = 0.2


def cell_values(points: pd.DataFrame, access: pd.Series, weight_column: str) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "h3": points["h3"].to_numpy(),
            "district": points["district"].to_numpy(),
            "w": points[weight_column].fillna(0).to_numpy(),
            "a": points["point_id"].map(access).fillna(0).to_numpy(),
        }
    )
    frame = frame[(frame["w"] > 0) & frame["district"].notna()]
    frame["aw"] = frame["a"] * frame["w"]
    cells = frame.groupby("h3").agg(
        w=("w", "sum"), aw=("aw", "sum"), district=("district", "first")
    )
    cells["a"] = cells["aw"] / cells["w"]
    return cells


def summary(points: pd.DataFrame, access: pd.Series, weight_column: str) -> dict:
    weight = points[weight_column].fillna(0).to_numpy()
    mask = (weight > 0) & points["district"].notna().to_numpy()
    values = points["point_id"].map(access).fillna(0).to_numpy()[mask]
    weight = weight[mask]
    district = points["district"].fillna("none").to_numpy()[mask]
    mean = float(np.sum(values * weight) / weight.sum())
    by_district = (
        pd.DataFrame({"a": values, "w": weight, "d": district})
        .groupby("d")
        .apply(lambda g: float(np.sum(g["a"] * g["w"]) / g["w"].sum() / mean), include_groups=False)
        .to_dict()
    )
    return {
        "mean": mean,
        "zero_access_share": float(weight[values == 0].sum() / weight.sum()),
        "gini": gini(values, weight),
        **theil(values, weight, district),
        "district_relative": by_district,
    }


def deficit_cells(cells: pd.DataFrame) -> set[str]:
    ordered = cells.sort_values("a")
    cumulative = ordered["w"].cumsum() / ordered["w"].sum()
    return set(ordered.index[cumulative <= DEFICIT_SHARE])


def run() -> dict:
    points, od = load_inputs()
    supplies = supply_measures()
    presumed = facilities()["school"]
    presumed_ids = frozenset(presumed.loc[presumed["presumed_new"].astype(bool), "facility_id"])
    report: dict = {}
    sensitivity_rows = []
    for kind, base in BASE.items():
        demand_column = f"{COHORT[kind]}_{base['variant']}"
        demand = points.set_index("point_id")[demand_column].fillna(0)
        access = index(
            od[kind],
            demand,
            supplies[kind][base["supply"]],
            base["decay"],
            base["d0"],
            base["d0_load"],
        )
        cells = cell_values(points, access, demand_column)
        cell_list = list(cells.index)
        moran = local_moran(cells["a"].to_numpy(), neighbours(cell_list), seed=SEED)
        moran.index = cells.index
        significant = moran["p"] < 0.05
        cold = cells[significant & (moran["quadrant"] == "LL")]
        hot = cells[significant & (moran["quadrant"] == "HH")]
        children = cells["w"].sum()
        report[kind] = {
            "base": base,
            **summary(points, access, demand_column),
            "global_moran_i": moran.attrs["global_i"],
            "cold_spot_cells": int(len(cold)),
            "cold_spot_children_share": float(cold["w"].sum() / children),
            "cold_spot_children_by_district": (cold.groupby("district")["w"].sum() / children)
            .round(4)
            .to_dict(),
            "hot_spot_children_share": float(hot["w"].sum() / children),
        }
        if kind == "school":
            no_new = index(
                od[kind],
                demand,
                supplies[kind][base["supply"]],
                base["decay"],
                base["d0"],
                base["d0_load"],
                exclude=presumed_ids,
            )
            report[kind]["without_presumed_new"] = summary(points, no_new, demand_column)
        cells_out = cells.join(moran[["local_i", "p", "quadrant"]])
        cells_out.to_parquet(PROCESSED / f"access_cells_{kind}.parquet")

        base_district = pd.Series(report[kind]["district_relative"])
        base_deficit = deficit_cells(cells)
        scale = {"d0": base["d0_load"] / base["d0"]}
        for variant, supply, decay, d0 in itertools.product(
            GRID["variant"], supplies[kind], GRID["decay"], GRID["d0"][kind]
        ):
            column = f"{COHORT[kind]}_{variant}"
            alt_demand = points.set_index("point_id")[column].fillna(0)
            alt = index(od[kind], alt_demand, supplies[kind][supply], decay, d0, d0 * scale["d0"])
            alt_summary = summary(points, alt, column)
            alt_cells = cell_values(points, alt, column)
            district = pd.Series(alt_summary["district_relative"]).reindex(base_district.index)
            shared = deficit_cells(alt_cells)
            sensitivity_rows.append(
                {
                    "kind": kind,
                    "variant": variant,
                    "supply": supply,
                    "decay": decay,
                    "d0": d0,
                    "gini": alt_summary["gini"],
                    "between_share": alt_summary["between_share"],
                    "district_rank_rho": float(spearmanr(base_district, district).correlation),
                    "deficit_jaccard": len(base_deficit & shared) / len(base_deficit | shared),
                    "worst_district": district.idxmin(),
                    **{f"rel_{k}": v for k, v in district.items()},
                }
            )
    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity.to_csv(REPORTS / "sensitivity_access.csv", index=False)
    sensitivity["population"] = np.where(
        sensitivity["variant"] == "worldpop", "worldpop", "buildings"
    )
    report["sensitivity_by_population"] = {
        f"{kind}/{population}": {
            "runs": int(len(group)),
            "district_rank_rho_median": float(group["district_rank_rho"].median()),
            "district_rank_rho_min": float(group["district_rank_rho"].min()),
            "deficit_jaccard_median": float(group["deficit_jaccard"].median()),
            "deficit_jaccard_min": float(group["deficit_jaccard"].min()),
            "worst_district_counts": group["worst_district"].value_counts().to_dict(),
        }
        for (kind, population), group in sensitivity.groupby(["kind", "population"])
    }
    report["sensitivity"] = {
        kind: {
            "runs": int(len(group)),
            "district_rank_rho_median": float(group["district_rank_rho"].median()),
            "district_rank_rho_min": float(group["district_rank_rho"].min()),
            "deficit_jaccard_median": float(group["deficit_jaccard"].median()),
            "deficit_jaccard_min": float(group["deficit_jaccard"].min()),
            "worst_district_counts": group["worst_district"].value_counts().to_dict(),
            "gini_range": [float(group["gini"].min()), float(group["gini"].max())],
        }
        for kind, group in sensitivity.groupby("kind")
    }
    (REPORTS / "access_equity.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    out = run()
    print(json.dumps(out, indent=1, ensure_ascii=False, default=float))

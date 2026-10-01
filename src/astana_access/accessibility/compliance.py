import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from astana_access import norms
from astana_access.accessibility.coverage import facilities, nearest
from astana_access.accessibility.e2sfca import load_inputs
from astana_access.config import REPORTS

VARIANTS = ("floor", "station", "station_equal")


def straight_line(points: pd.DataFrame, sites) -> np.ndarray:
    centre = sites.geometry.representative_point()
    tree = cKDTree(np.column_stack([centre.x, centre.y]))
    distance, _ = tree.query(points[["x", "y"]].to_numpy())
    return distance


def run() -> dict:
    points, od = load_inputs()
    points = points[(points["kind"] == "dwelling") & points["district"].notna()].reset_index(
        drop=True
    )
    sites = facilities()
    presumed = sites["school"]["presumed_new"].astype(bool)
    rows = []
    for kind in ("school", "preschool"):
        radius = norms.RADIUS_M[kind]
        measures = {
            "network": nearest(points, od[kind]).to_numpy(),
            "straight_line": straight_line(points, sites[kind]),
        }
        if kind == "school":
            named = od[kind][
                ~od[kind]["facility_id"].isin(set(sites[kind].loc[presumed, "facility_id"]))
            ]
            measures["network_named_only"] = nearest(points, named).to_numpy()
        for measure, distance in measures.items():
            for limit_name, limit in (
                ("norm", radius),
                ("norm_plus_10pct", radius * (1 + norms.RADIUS_TOLERANCE)),
            ):
                for variant in VARIANTS:
                    weight = points[f"{kind}_{variant}"].fillna(0).to_numpy()
                    inside = distance <= limit
                    for district, index in [("city", np.arange(len(points)))] + list(
                        points.groupby("district").indices.items()
                    ):
                        w = weight[index]
                        rows.append(
                            {
                                "kind": kind,
                                "measure": measure,
                                "limit": limit_name,
                                "radius_m": limit,
                                "variant": variant,
                                "area": district,
                                "children": float(w.sum()),
                                "compliant_share": float(w[inside[index]].sum() / w.sum()),
                            }
                        )
    table = pd.DataFrame(rows)
    table.to_csv(REPORTS / "compliance.csv", index=False)
    base = table[(table["variant"] == "station") & (table["limit"] == "norm")]
    summary = {
        "source": norms.SOURCE,
        "radius_m": norms.RADIUS_M,
        "station_model": {
            f"{kind}/{measure}": group.set_index("area")["compliant_share"].round(3).to_dict()
            for (kind, measure), group in base.groupby(["kind", "measure"])
        },
        "variant_range_city": {
            f"{kind}/{measure}/{limit}": [
                float(group["compliant_share"].min()),
                float(group["compliant_share"].max()),
            ]
            for (kind, measure, limit), group in table[table["area"] == "city"].groupby(
                ["kind", "measure", "limit"]
            )
        },
    }
    (REPORTS / "compliance.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False, default=float))

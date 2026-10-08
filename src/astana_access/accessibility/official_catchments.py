import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from astana_access.accessibility.coverage import facilities
from astana_access.accessibility.e2sfca import DECAY, load_inputs, supply_measures
from astana_access.config import CRS_GEO, CRS_METRIC, INTERIM, PROCESSED, REPORTS
from astana_access.equity.analysis import BASE

EXACT = ("house", "house_spread", "range", "street")
SNAP_M = 25.0
DISTANCES = (500, 1000, 1500, 2000)
NAME_KEYS = {
    "сатбаев": "sch0061",
    "мырза": "sch0073",
    "кекил": "sch0041",
    "алтынсарин": "sch0043",
    "бөкейхан": "binom_bokeikhan",
    "байтұрсын": "sch0153",
}


def school_ids(points: pd.DataFrame, schools: gpd.GeoDataFrame) -> pd.Series:
    numbered = schools.dropna(subset=["number"]).drop_duplicates("number")
    by_number = dict(zip(numbered["number"].astype(int), numbered["facility_id"], strict=True))
    programme_path = PROCESSED / "comfortable_schools.gpkg"
    if programme_path.exists():
        sites = gpd.read_file(programme_path)
        sites = sites[(sites["status"] == "built") & sites["number"].notna()]
        for number, facility in zip(sites["number"].astype(int), sites["facility_id"], strict=True):
            by_number.setdefault(number, facility)

    def resolve(row) -> str | None:
        if pd.notna(row["number"]):
            return by_number.get(int(row["number"]))
        name = str(row["school"]).lower()
        for key, facility in NAME_KEYS.items():
            if key in name:
                return facility
        return None

    return points.apply(resolve, axis=1)


def assigned_dwellings() -> pd.DataFrame:
    points = pd.read_csv(INTERIM / "catchments_geocoded.csv")
    points = points[points["precision"].isin(EXACT)].dropna(subset=["lon", "lat"])
    schools = facilities()["school"]
    points["facility_id"] = school_ids(points, schools)
    points = points.dropna(subset=["facility_id"])
    geometry = gpd.points_from_xy(points["lon"], points["lat"], crs=CRS_GEO).to_crs(CRS_METRIC)
    points = gpd.GeoDataFrame(points, geometry=geometry, crs=CRS_METRIC)
    dwellings = gpd.read_parquet(PROCESSED / "dwellings.parquet")[["id", "geometry"]]
    joined = gpd.sjoin_nearest(
        points, dwellings, how="inner", max_distance=SNAP_M, distance_col="snap_m"
    )
    pairs = joined[["id", "facility_id", "district"]].drop_duplicates(["id", "facility_id"])
    pairs["point_id"] = "b" + pairs["id"].astype(str)
    pairs["share"] = 1.0 / pairs.groupby("point_id")["facility_id"].transform("count")
    return pairs


def weighted_median(values: pd.Series, weights: pd.Series) -> float:
    order = np.argsort(values.to_numpy())
    cumulative = np.cumsum(weights.to_numpy()[order]) / weights.sum()
    return float(values.to_numpy()[order][np.searchsorted(cumulative, 0.5)])


def allocated_load(od: pd.DataFrame, demand: pd.Series, base: dict) -> pd.Series:
    d0_load = base["d0_load"]
    table = od[od["distance_m"] <= d0_load]
    weight = DECAY[base["decay"]](table["distance_m"].to_numpy(dtype=float), d0_load)
    total = pd.Series(weight).groupby(table["point_id"].to_numpy()).transform("sum").to_numpy()
    share = np.divide(weight, total, out=np.zeros_like(weight), where=total > 0)
    children = table["point_id"].map(demand).fillna(0.0).to_numpy() * share
    return pd.Series(children).groupby(table["facility_id"].to_numpy()).sum()


def run() -> dict:
    pairs = assigned_dwellings()
    points, od = load_inputs()
    base = BASE["school"]
    column = f"school_{base['variant']}"
    demand = points.set_index("point_id")[column].fillna(0)
    district = points.set_index("point_id")["district"]
    children = demand[points.loc[points["kind"] == "dwelling", "point_id"]]
    covered = pairs["point_id"].unique()
    covered_share = float(children[children.index.isin(covered)].sum() / children.sum())
    by_district = (
        children.groupby(district.reindex(children.index))
        .apply(lambda s: float(s[s.index.isin(covered)].sum() / s.sum()))
        .round(3)
        .to_dict()
    )

    walk = od["school"][["point_id", "facility_id", "distance_m"]].copy()
    walk = walk.sort_values(["point_id", "distance_m"])
    walk["rank"] = walk.groupby("point_id").cumcount() + 1
    merged = pairs.merge(walk, on=["point_id", "facility_id"], how="left")
    merged["children"] = merged["point_id"].map(demand).fillna(0.0) * merged["share"]
    weight = merged["children"]
    reached = merged["distance_m"].notna()
    distance = merged["distance_m"].fillna(np.inf)
    rank = merged["rank"].fillna(np.inf)

    def weighted(mask) -> float:
        return float(weight[mask].sum() / weight.sum())

    by_district_distance = {}
    for name, group in merged.groupby("district"):
        w = group["children"]
        d = group["distance_m"].fillna(np.inf)
        by_district_distance[name] = {
            f"within_{limit}m": round(float(w[d <= limit].sum() / w.sum()), 3)
            for limit in (500, 1000)
        } | {"nearest_share": round(float(w[group["rank"] == 1].sum() / w.sum()), 3)}

    assigned = merged.groupby("facility_id")["children"].sum()
    model_load = allocated_load(od["school"], demand, base)
    supply = supply_measures()["school"]["floor_area"]
    both = pd.DataFrame({"assigned": assigned, "model": model_load, "floor": supply}).dropna()
    both = both[both["assigned"] > 0]
    rho_load = spearmanr(both["assigned"], both["model"]).correlation
    by_radius = {}
    for radius in (1500, 2000, 3000, 4000):
        variant = allocated_load(od["school"], demand, base | {"d0_load": radius})
        pair = pd.concat([assigned, variant], axis=1, keys=["a", "m"]).dropna()
        pair = pair[pair["a"] > 0]
        by_radius[radius] = float(spearmanr(pair["a"], pair["m"]).correlation)
    counted = od["school"][od["school"]["distance_m"] <= base["d0"]]
    counted_load = (
        (
            counted["point_id"].map(demand).fillna(0.0)
            * DECAY[base["decay"]](counted["distance_m"].to_numpy(dtype=float), base["d0"])
        )
        .groupby(counted["facility_id"])
        .sum()
    )
    pair = pd.concat([assigned, counted_load], axis=1, keys=["a", "m"]).dropna()
    pair = pair[pair["a"] > 0]
    by_radius["e2sfca_counted_at_every_school"] = float(spearmanr(pair["a"], pair["m"]).correlation)
    places = both["floor"] / 15.4
    overload = (both["assigned"] / places).sort_values(ascending=False)
    names = facilities()["school"].set_index("facility_id")["name"]

    report = {
        "schools_with_territory": int(pairs["facility_id"].nunique()),
        "dwellings_assigned": int(pairs["point_id"].nunique()),
        "dwellings_with_several_schools": int((pairs.groupby("point_id").size() > 1).sum()),
        "school_age_children_in_assigned_dwellings": covered_share,
        "school_age_children_in_assigned_dwellings_by_district": by_district,
        "assigned_school_reached_within_4km": weighted(reached),
        "assigned_is_nearest": weighted(rank == 1),
        "assigned_in_two_nearest": weighted(rank <= 2),
        "median_distance_to_assigned_m": weighted_median(
            merged.loc[reached, "distance_m"], merged.loc[reached, "children"]
        ),
        **{f"assigned_within_{limit}m": weighted(distance <= limit) for limit in DISTANCES},
        "by_district": by_district_distance,
        "load_rank_correlation_assigned_vs_model": float(rho_load),
        "load_schools_compared": int(len(both)),
        "assigned_over_model_load_median": float((both["assigned"] / both["model"]).median()),
        "load_rank_correlation_by_allocation_radius": by_radius,
        "most_overloaded": [
            {
                "facility_id": fid,
                "name": str(names.get(fid, fid))[:80],
                "assigned_children": round(float(both.at[fid, "assigned"])),
                "children_per_place_proxy": round(float(value), 2),
            }
            for fid, value in overload.head(10).items()
        ],
    }
    pairs.to_csv(INTERIM / "catchment_dwellings.csv", index=False)
    (REPORTS / "official_catchments.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False, default=float))

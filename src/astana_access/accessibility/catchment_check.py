import json
import re

import geopandas as gpd
import pandas as pd

from astana_access.accessibility.coverage import LIMIT_M, facilities, origin_destination
from astana_access.accessibility.network import load
from astana_access.config import CRS_GEO, CRS_METRIC, INTERIM, RAW, REPORTS


def assigned_houses() -> pd.DataFrame:
    schools = pd.read_csv(RAW / "sakura" / "schools.csv", dtype={"sakura_id": str})
    schools["number"] = schools["name"].map(
        lambda name: int(re.search(r"№\s*(\d+)", name).group(1))
    )
    houses = pd.read_csv(INTERIM / "sakura_catchment_geocoded.csv", dtype={"sakura_id": str})
    houses = houses[houses["precision"] == "house"].drop_duplicates(["lon", "lat", "sakura_id"])
    houses = houses.merge(schools[["sakura_id", "number"]], on="sakura_id")
    points = gpd.GeoSeries(gpd.points_from_xy(houses["lon"], houses["lat"]), crs=CRS_GEO).to_crs(
        CRS_METRIC
    )
    houses["x"] = points.x.to_numpy()
    houses["y"] = points.y.to_numpy()
    houses["point_id"] = [f"h{i}" for i in range(len(houses))]
    return houses


def run() -> dict:
    network = load()
    schools = facilities()["school"]
    houses = assigned_houses()
    od = origin_destination(network, houses, schools, "facility_id")
    number_of = schools.set_index("facility_id")["number"]
    od["number"] = od["facility_id"].map(number_of)
    od = od.sort_values(["point_id", "distance_m"])
    od["rank"] = od.groupby("point_id").cumcount() + 1
    joined = houses.merge(od, on=["point_id", "number"], how="left")
    nearest = od.drop_duplicates("point_id").set_index("point_id")
    joined["nearest_distance_m"] = joined["point_id"].map(nearest["distance_m"])
    joined["extra_m"] = joined["distance_m"] - joined["nearest_distance_m"]
    reached = joined["rank"].notna()
    by_school = joined.groupby("number").agg(
        houses=("point_id", "size"),
        nearest_share=("rank", lambda r: float((r == 1).mean())),
        top2_share=("rank", lambda r: float((r <= 2).mean())),
        median_distance_m=("distance_m", "median"),
    )
    summary = {
        "houses": int(len(joined)),
        "schools": int(joined["number"].nunique()),
        f"assigned_within_{int(LIMIT_M)}m": float(reached.mean()),
        "assigned_is_nearest": float((joined["rank"] == 1).mean()),
        "assigned_in_two_nearest": float((joined["rank"] <= 2).mean()),
        "median_distance_to_assigned_m": float(joined["distance_m"].median()),
        "p90_distance_to_assigned_m": float(joined["distance_m"].quantile(0.9)),
        "median_extra_over_nearest_m": float(joined.loc[joined["rank"] > 1, "extra_m"].median()),
        "by_school": by_school.round(3).reset_index().to_dict(orient="records"),
    }
    (REPORTS / "catchment_check.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False, default=float))

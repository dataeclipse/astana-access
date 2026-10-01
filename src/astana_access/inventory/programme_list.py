import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.ops import nearest_points

from astana_access.accessibility.coverage import facilities
from astana_access.config import CRS_GEO, CRS_METRIC, DATA, PROCESSED, REPORTS
from astana_access.inventory.addresses import load_gazetteer
from astana_access.population.stations import LineIndex

TABLE = DATA / "labels" / "comfortable_schools.csv"
MATCH_M = 600.0
JOIN_M = 300.0
OTAU = (71.55591, 51.12931)


def locate(row: pd.Series, index: LineIndex, gazetteer, schools: gpd.GeoDataFrame) -> tuple:
    if row["locate"] == "osm":
        hit = schools[schools["number"] == float(row["osm_number"])]
        if len(hit):
            return hit.geometry.iloc[0], "osm_number", 0.0
        return None, "osm_number_missing", np.nan
    if row["locate"] == "osm_ground":
        if pd.notna(row.get("anchor_number")):
            anchor = schools[schools["number"] == float(row["anchor_number"])].geometry.iloc[0]
        else:
            anchor = gpd.GeoSeries([Point(OTAU)], crs=CRS_GEO).to_crs(CRS_METRIC).iloc[0]
        grounds = schools[schools["presumed_new"].astype(bool)]
        distance = grounds.distance(anchor)
        return grounds.geometry[distance.idxmin()], "ground_near_anchor", float(distance.min())
    if row["locate"] == "unresolved":
        return None, "unresolved", np.nan
    if row["locate"] == "address":
        found = gazetteer.locate(row["address_street"], str(row["address_house"]))
        if found.precision == "house":
            point = gpd.GeoSeries([Point(found.lon, found.lat)], crs=CRS_GEO).to_crs(CRS_METRIC)
            return point.iloc[0], "address", 0.0
        return None, f"address_{found.precision}", np.nan
    first, second = index.street(row["street_a"]), index.street(row["street_b"])
    if first is None or second is None:
        return None, "street_missing", np.nan
    crossing = first.intersection(second)
    if not crossing.is_empty:
        return crossing.representative_point(), "intersection", 0.0
    a, b = nearest_points(first, second)
    gap = a.distance(b)
    if gap > JOIN_M:
        return None, "streets_apart", float(gap)
    return Point((a.x + b.x) / 2, (a.y + b.y) / 2), "near_intersection", float(gap)


def build() -> tuple[gpd.GeoDataFrame, dict]:
    table = pd.read_csv(TABLE, dtype={"address_house": str})
    schools = facilities()["school"]
    index = LineIndex()
    gazetteer = load_gazetteer()
    rows = []
    for _, row in table.iterrows():
        point, method, gap = locate(row, index, gazetteer, schools)
        record = row.to_dict() | {"method": method, "gap_m": gap}
        if point is not None:
            distance = schools.distance(point)
            nearest = distance.idxmin()
            record |= {
                "x": point.x,
                "y": point.y,
                "nearest_facility": schools.at[nearest, "facility_id"],
                "nearest_number": schools.at[nearest, "number"],
                "nearest_m": float(distance[nearest]),
            }
        rows.append(record)
    sites = pd.DataFrame(rows)
    sites["matched"] = sites["nearest_m"] <= MATCH_M
    sites["facility_id"] = np.where(
        sites["matched"], sites["nearest_facility"], "site_" + sites["site"]
    )
    located = sites[sites["x"].notna()]
    frame = gpd.GeoDataFrame(
        located, geometry=gpd.points_from_xy(located["x"], located["y"]), crs=CRS_METRIC
    )
    frame.to_crs(CRS_GEO).to_file(PROCESSED / "comfortable_schools.gpkg", driver="GPKG")
    built = sites[sites["status"] == "built"]
    duplicate = built.loc[built["matched"], "facility_id"].duplicated(keep=False)
    summary = {
        "sites_listed": int(len(sites)),
        "built": int(len(built)),
        "located": int(built["x"].notna().sum()),
        "matched_to_school_layer": int(built["matched"].sum()),
        "unmatched_located": built.loc[~built["matched"] & built["x"].notna(), "site"].tolist(),
        "not_located": built.loc[built["x"].isna(), ["site", "method"]].to_dict("records"),
        "shared_facility": built.loc[built["matched"] & duplicate, ["site", "facility_id"]].to_dict(
            "records"
        ),
        "by_method": built["method"].value_counts().to_dict(),
        "sites": sites[
            [
                "site",
                "number",
                "seats",
                "opened",
                "method",
                "gap_m",
                "nearest_number",
                "nearest_m",
                "matched",
            ]
        ].to_dict("records"),
    }
    (REPORTS / "comfortable_schools.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return frame, summary


def programme_sites() -> gpd.GeoDataFrame:
    frame = gpd.read_file(PROCESSED / "comfortable_schools.gpkg").to_crs(CRS_METRIC)
    frame = frame[frame["status"] == "built"].copy()
    frame["matched"] = frame["matched"].astype(bool)
    return frame


if __name__ == "__main__":
    _, out = build()
    print(json.dumps(out, indent=1, ensure_ascii=False, default=float))

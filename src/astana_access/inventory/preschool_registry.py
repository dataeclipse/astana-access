import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from astana_access.config import CRS_GEO, CRS_METRIC, INTERIM, PROCESSED, RAW
from astana_access.inventory.addresses import (
    district_hint,
    geocode_frame,
    load_gazetteer,
    norm_house,
    norm_street,
)
from astana_access.inventory.names import extract_number, normalize

SNAPSHOT = "2026-09-30"
OSM_LINK_RADIUS_M = 60.0
BRAND_MATCH = 75
BRANCH = re.compile(r"объект|обьект|мини[- ]?центр|корпус|филиал|комплекс|шағын орталы", re.I)
GENERIC = re.compile(
    r"(?<![а-я])(?:гккп|кгу|гу|ясли|сад\w*|детск\w*|детсад|балаба[кқ]ша\w*|б[оө]бекжай\w*|"
    r"акимат\w*|город\w*|астан\w*|санаторн\w*|государственн\w*|коммунальн\w*|казенн\w*|"
    r"предприяти\w*)(?![а-я])|№|\d+",
    re.I,
)
APPROXIMATE = ("house_spread", "neighbour", "house_base")


def brand(name: str | None) -> str:
    value = GENERIC.sub(" ", normalize(str(name or "")))
    return re.sub(r"[^а-яa-z ]", " ", value).strip()


def same_brand(left: str | None, right: str | None) -> bool:
    a, b = brand(left), brand(right)
    if not a or not b:
        return True
    return fuzz.token_set_ratio(a, b) >= BRAND_MATCH


def load_registry() -> tuple[pd.DataFrame, dict[str, int]]:
    registry = pd.read_csv(RAW / "indigo" / f"registry_{SNAPSHOT}.csv")
    totals = json.loads((RAW / "indigo" / f"totals_{SNAPSHOT}.json").read_text(encoding="utf-8"))
    state = registry["ownership"] == "state"
    registry["branch"] = registry["name"].map(lambda name: bool(BRANCH.search(str(name))))
    registry["number"] = [
        extract_number(normalize(str(name))) if is_state else None
        for name, is_state in zip(registry["name"], state, strict=True)
    ]
    return registry, totals


def nominatim_verified(frame: pd.DataFrame) -> pd.DataFrame:
    path = INTERIM / "indigo_nominatim_fallback.csv"
    if not path.exists() or path.stat().st_size < 10:
        return pd.DataFrame(columns=["indigo_id", "lon_n", "lat_n"])
    gazetteer = load_gazetteer()
    fallback = pd.read_csv(path).drop_duplicates("indigo_id")
    parsed = frame.set_index("indigo_id")[["parsed_street", "parsed_house"]]
    rows = []
    for row in fallback.itertuples():
        if row.indigo_id not in parsed.index:
            continue
        street, house = parsed.loc[row.indigo_id]
        wanted, _ = gazetteer.match_street(norm_street(street))
        parts = [part.strip() for part in str(row.display).split(",")]
        house_ok = any(norm_house(part) == norm_house(house) for part in parts)
        street_ok = bool(wanted) and any(
            gazetteer.match_street(norm_street(part))[0] == wanted for part in parts
        )
        if house_ok and street_ok:
            rows.append({"indigo_id": row.indigo_id, "lon_n": row.lon_n, "lat_n": row.lat_n})
    return pd.DataFrame(rows, columns=["indigo_id", "lon_n", "lat_n"])


def assign_coordinates(registry: pd.DataFrame, osm: gpd.GeoDataFrame) -> pd.DataFrame:
    frame = geocode_frame(registry)
    frame["coord_source"] = "unresolved"
    frame.loc[frame["precision"] == "house", "coord_source"] = "gazetteer_house"
    frame["osm_conflict_m"] = np.nan

    state_osm = osm[osm["catchment_based"] & osm["number"].notna()]
    counts = state_osm["number"].value_counts()
    state_osm = state_osm[state_osm["number"].map(counts) == 1].set_index("number")
    metric = gpd.GeoSeries(
        gpd.points_from_xy(frame["lon"], frame["lat"]), index=frame.index, crs=CRS_GEO
    ).to_crs(CRS_METRIC)
    osm_metric = state_osm.geometry.to_crs(CRS_METRIC)
    for i, row in frame.iterrows():
        number = row["number"]
        if pd.isna(number) or row["branch"] or number not in state_osm.index:
            continue
        if not same_brand(row["name"], state_osm.at[number, "name"]):
            continue
        if row["coord_source"] == "gazetteer_house":
            frame.at[i, "osm_conflict_m"] = metric[i].distance(osm_metric[number])
            continue
        point = state_osm.geometry[number]
        frame.at[i, "lon"] = point.x
        frame.at[i, "lat"] = point.y
        frame.at[i, "coord_source"] = "osm_number"

    verified = nominatim_verified(frame).set_index("indigo_id")
    for i, row in frame[frame["coord_source"] == "unresolved"].iterrows():
        if row["indigo_id"] in verified.index:
            frame.at[i, "lon"] = verified.at[row["indigo_id"], "lon_n"]
            frame.at[i, "lat"] = verified.at[row["indigo_id"], "lat_n"]
            frame.at[i, "coord_source"] = "nominatim_house"

    approximate = (frame["coord_source"] == "unresolved") & frame["precision"].isin(APPROXIMATE)
    frame.loc[approximate, "coord_source"] = "gazetteer_approximate"
    lost = frame["coord_source"] == "unresolved"
    frame.loc[lost, ["lon", "lat"]] = np.nan
    return frame


def build() -> gpd.GeoDataFrame:
    registry, totals = load_registry()
    osm = gpd.read_file(PROCESSED / "facilities_osm.gpkg", layer="preschools")
    frame = assign_coordinates(registry, osm)

    points = gpd.GeoDataFrame(
        frame, geometry=gpd.points_from_xy(frame["lon"], frame["lat"]), crs=CRS_GEO
    )
    districts = gpd.read_file(PROCESSED / "districts.gpkg", layer="districts")
    located = points["lon"].notna()
    joined = gpd.sjoin(
        points[located], districts[["name_en", "geometry"]], how="left", predicate="within"
    )
    joined = joined[~joined.index.duplicated()]
    points["district"] = joined["name_en"].reindex(points.index)
    outside = located & points["district"].isna()
    points.loc[outside, "coord_source"] = "unresolved"
    points.loc[points["coord_source"] == "unresolved", "geometry"] = None
    hints = points["address"].map(district_hint)
    points["district_stated"] = [next(iter(hint)) if len(hint) == 1 else None for hint in hints]

    osm_metric = osm.to_crs(CRS_METRIC)
    valid = points[points.geometry.notna()].to_crs(CRS_METRIC)
    points["osm_ref"] = None
    points["floor_m2"] = np.nan
    taken: set[int] = set()
    order = valid.index[np.argsort(valid["coord_source"].ne("osm_number").to_numpy())]
    for i in order:
        distances = osm_metric.distance(valid.geometry[i])
        j = distances.idxmin()
        if distances[j] <= OSM_LINK_RADIUS_M and j not in taken:
            taken.add(j)
            points.at[i, "osm_ref"] = osm.at[j, "osm_ref"]
            points.at[i, "floor_m2"] = osm.at[j, "floor_m2_observed"]

    mean_size = {
        "state": totals["state_children"] / totals["state_organisations"],
        "private": totals["private_children"] / totals["private_organisations"],
    }
    points["children_class_mean"] = points["ownership"].map(mean_size)
    points["facility_id"] = [f"kg{int(value):06d}" for value in points["indigo_id"]]
    keep = [
        "facility_id",
        "indigo_id",
        "name",
        "address",
        "ownership",
        "kind",
        "branch",
        "number",
        "min_age",
        "languages",
        "free_places",
        "children_class_mean",
        "coord_source",
        "precision",
        "matched_street",
        "osm_conflict_m",
        "district",
        "district_stated",
        "osm_ref",
        "floor_m2",
        "geometry",
    ]
    result = gpd.GeoDataFrame(points[keep], geometry="geometry", crs=CRS_GEO)
    result.to_file(PROCESSED / "facilities.gpkg", layer="preschools", driver="GPKG")
    return result

import re

import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW
from astana_access.inventory.capacity import attach
from astana_access.inventory.names import extract_number, normalize

TERRITORY_FILE = "kindergarten_territories.gpkg"
DUPLICATE_RADIUS_M = 120.0
BUILDING_NAME_RADIUS_M = 30.0
ORPHAN_BUILDING_RADIUS_M = 120.0
UNDERCAPTURE_M2 = 400.0

PRESCHOOL = re.compile(
    r"детс(ад|кий\s+сад)|\bд/?с\b|ясли|ясли-сад|балабакша|бобекжай|бөбекжай|"
    r"мини-?центр|шагын орталык|дошкольн",
    re.I,
)
OUT_OF_SCOPE = re.compile(
    r"колледж|клуб|студи|школа развития|центр развития|развивающ|танц|музыкальн|"
    r"логопед|бассейн|лицей|гимназ|университет|поликлиник|больниц",
    re.I,
)
STATE = re.compile(
    r"\bгккп\b|\bкгкп\b|\bкгу\b|\bгу\b|коммунальн|государствен|акимат|управлени", re.I
)
PRIVATE = re.compile(r"товарищество|\bтоо\b|\bжшс\b|\bип\b|частн|некоммерческ|филиал|\bчу\b", re.I)


def ownership(name: str, number: float | None) -> tuple[str, str]:
    text = str(name or "")
    if STATE.search(text):
        return "state", "legal_form"
    if PRIVATE.search(text):
        return "private", "legal_form"
    if number is not None and not pd.isna(number):
        return "state", "number"
    if not text or text == "nan":
        return "unknown", "no_name"
    return "private", "brand_heuristic"


def in_scope(name: str | None, source: str) -> bool:
    if not name or str(name) == "nan":
        return source == "osm_facility"
    text = normalize(str(name))
    if OUT_OF_SCOPE.search(text):
        return False
    if source == "osm_building":
        return bool(PRESCHOOL.search(text))
    return True


def facility_layer() -> gpd.GeoDataFrame:
    facilities = gpd.read_file(RAW / "osm" / "facilities.gpkg")
    frame = facilities[facilities["category"] == "kindergarten"].reset_index(drop=True).copy()
    frame["label"] = frame["name_ru"].fillna(frame["name"])
    frame["osm_ref"] = frame["osm_type"] + "/" + frame["osm_id"].astype(str)
    frame["source"] = "osm_facility"
    return frame


def building_layer() -> gpd.GeoDataFrame:
    buildings = gpd.read_file(RAW / "osm" / "buildings.gpkg")
    named = buildings["name"].fillna("")
    mask = (buildings["building"] == "kindergarten") | named.str.contains(
        r"детс|ясли|балабақша|балабакша|бөбекжай|д/с", case=False, regex=True
    )
    return buildings[mask].reset_index(drop=True)


def drop_duplicates(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    metric = frame.to_crs(CRS_METRIC)
    points = metric.geometry.centroid
    keep = np.ones(len(frame), dtype=bool)
    order = frame["label"].notna().astype(int).sort_values(ascending=False).index
    used: list[int] = []
    for i in order:
        if not keep[frame.index.get_loc(i)]:
            continue
        for j in frame.index:
            if j == i or not keep[frame.index.get_loc(j)]:
                continue
            same_number = (
                not pd.isna(frame.at[i, "number"])
                and frame.at[i, "number"] == frame.at[j, "number"]
            )
            unnamed = pd.isna(frame.at[j, "label"])
            if not (same_number or unnamed):
                continue
            if points.loc[i].distance(points.loc[j]) <= DUPLICATE_RADIUS_M:
                keep[frame.index.get_loc(j)] = False
        used.append(i)
    return frame[keep].reset_index(drop=True)


def build() -> gpd.GeoDataFrame:
    facilities = facility_layer()
    buildings = building_layer()

    bld_m = buildings.to_crs(CRS_METRIC)
    named_bld = bld_m[bld_m["name"].notna()]
    fac_m = facilities.to_crs(CRS_METRIC)
    for i in facilities.index[facilities["label"].isna()]:
        if named_bld.empty:
            break
        distances = named_bld.distance(fac_m.geometry.iloc[i].centroid)
        j = distances.idxmin()
        if distances[j] <= BUILDING_NAME_RADIUS_M:
            facilities.at[i, "label"] = named_bld.at[j, "name"]
            facilities.at[i, "source"] = "osm_facility+building_name"

    centroids = facilities.to_crs(CRS_METRIC).geometry.centroid
    bld = buildings.copy()
    bld["distance"] = [centroids.distance(c).min() for c in bld_m.geometry.centroid]
    orphans = bld[(bld["distance"] > ORPHAN_BUILDING_RADIUS_M) & bld["name"].notna()].copy()
    orphans["label"] = orphans["name"]
    orphans["osm_ref"] = "way/" + orphans["osm_id"].astype(str)
    orphans["source"] = "osm_building"
    orphans["geometry"] = orphans.to_crs(CRS_METRIC).geometry.centroid.to_crs(CRS_GEO)

    columns = ["label", "osm_ref", "source", "geometry"]
    frame = pd.concat([facilities[columns], orphans[columns]], ignore_index=True)
    frame = gpd.GeoDataFrame(frame, geometry="geometry", crs=CRS_GEO)
    frame["geometry"] = frame.to_crs(CRS_METRIC).geometry.centroid.to_crs(CRS_GEO)
    frame["number"] = [
        extract_number(normalize(str(v))) if v and str(v) != "nan" else None for v in frame["label"]
    ]
    frame = drop_duplicates(frame)

    frame["in_scope"] = [
        in_scope(v, s) for v, s in zip(frame["label"], frame["source"], strict=True)
    ]
    resolved = [ownership(n, num) for n, num in zip(frame["label"], frame["number"], strict=True)]
    frame["ownership"] = [r[0] for r in resolved]
    frame["ownership_source"] = [r[1] for r in resolved]
    frame["catchment_based"] = frame["in_scope"] & (frame["ownership"] == "state")

    districts = gpd.read_file(PROCESSED / "districts.gpkg", layer="districts")
    joined = gpd.sjoin(frame, districts[["name_en", "geometry"]], how="left", predicate="within")
    frame["district"] = joined[~joined.index.duplicated(keep="first")]["name_en"].to_numpy()

    frame = attach(frame, territories_file=TERRITORY_FILE, tagged_type="kindergarten")
    frame["floor_m2_observed"] = frame["floor_m2"]
    frame["floor_source"] = frame["building_method"]
    reference = frame[frame["in_scope"] & (frame["floor_m2"] >= UNDERCAPTURE_M2)]
    median_floor = float(reference["floor_m2"].median()) if len(reference) else np.nan
    for i, row in frame[frame["in_scope"]].iterrows():
        if pd.isna(row["floor_m2"]):
            frame.at[i, "floor_m2"] = median_floor
            frame.at[i, "floor_source"] = "imputed_missing"
        elif row["floor_m2"] < UNDERCAPTURE_M2:
            frame.at[i, "floor_m2"] = median_floor
            frame.at[i, "floor_source"] = "imputed_undercapture"
    frame["capacity_index"] = frame["floor_m2"] / median_floor
    frame = frame.reset_index(drop=True)
    frame["facility_id"] = [f"kg{i:04d}" for i in range(len(frame))]

    keep = [
        "facility_id",
        "label",
        "number",
        "ownership",
        "ownership_source",
        "in_scope",
        "catchment_based",
        "district",
        "source",
        "osm_ref",
        "territory_ha",
        "buildings_n",
        "footprint_m2",
        "floor_m2",
        "floor_m2_observed",
        "floor_source",
        "levels_imputed_n",
        "capacity_index",
        "geometry",
    ]
    result = frame[keep].rename(columns={"label": "name"})
    result.to_file(PROCESSED / "facilities.gpkg", layer="preschools", driver="GPKG")
    return result

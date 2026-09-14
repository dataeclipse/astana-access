import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.config import CRS_METRIC, PROCESSED, RAW

TERRITORY_SNAP_M = 50.0
SCHOOL_BUILDING_RADIUS_M = 80.0
FALLBACK_RADIUS_M = 80.0
FALLBACK_MIN_FOOTPRINT_M2 = 800.0
MAX_LEVELS = 6
EXCLUDED_TYPES = {
    "apartments",
    "house",
    "detached",
    "residential",
    "garages",
    "garage",
    "industrial",
    "retail",
    "commercial",
    "shed",
    "roof",
    "service",
    "hut",
    "kiosk",
    "greenhouse",
}


def load_buildings() -> gpd.GeoDataFrame:
    frame = gpd.read_file(RAW / "osm" / "buildings.gpkg").to_crs(CRS_METRIC)
    frame["levels_tag"] = pd.to_numeric(frame["levels"], errors="coerce").clip(1, MAX_LEVELS)
    frame["footprint_m2"] = frame.area
    frame["point"] = frame.representative_point()
    return frame


def load_territories() -> gpd.GeoDataFrame:
    return gpd.read_file(RAW / "osm" / "school_territories.gpkg", layer="territories").to_crs(
        CRS_METRIC
    )


def _floor(buildings: gpd.GeoDataFrame, median_levels: float) -> tuple[float, int]:
    levels = buildings["levels_tag"]
    return float((buildings["footprint_m2"] * levels.fillna(median_levels)).sum()), int(
        levels.isna().sum()
    )


def attach(schools: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    buildings = load_buildings()
    territories = load_territories()
    usable = buildings[~buildings["building"].isin(EXCLUDED_TYPES)]
    school_tagged = usable[usable["building"] == "school"]
    tagged_levels = school_tagged["levels_tag"].dropna()
    median_levels = float(tagged_levels.median()) if len(tagged_levels) else 3.0

    points = schools.to_crs(CRS_METRIC).geometry
    order = schools.assign(
        _priority=schools["catchment_based"].astype(int) * 2 + schools["in_scope"].astype(int)
    )
    order = order.sort_values("_priority", ascending=False).index

    used_territories: set[int] = set()
    used_buildings: set[int] = set()
    rows: dict[int, dict[str, object]] = {}
    for i in order:
        point = points.loc[i]
        record: dict[str, object] = {
            "territory_ha": np.nan,
            "buildings_n": 0,
            "footprint_m2": 0.0,
            "floor_m2": np.nan,
            "levels_imputed_n": 0,
            "under_construction_buildings": 0,
            "building_method": "none",
        }
        free_t = territories[~territories.index.isin(used_territories)]
        distances = free_t.distance(point)
        chosen = None
        if len(distances) and distances.min() <= TERRITORY_SNAP_M:
            chosen = distances.idxmin()
        candidates = gpd.GeoDataFrame()
        if chosen is not None:
            polygon = territories.geometry.loc[chosen]
            inside = usable[usable["point"].within(polygon) & ~usable.index.isin(used_buildings)]
            if len(inside):
                used_territories.add(chosen)
                record["territory_ha"] = float(polygon.area / 1e4)
                candidates = inside
                record["building_method"] = "territory"
        if candidates.empty:
            near = school_tagged[
                (school_tagged.distance(point) <= SCHOOL_BUILDING_RADIUS_M)
                & ~school_tagged.index.isin(used_buildings)
            ]
            if len(near):
                candidates = near
                record["building_method"] = "school_buildings"
        if candidates.empty:
            near = usable[
                (usable.distance(point) <= FALLBACK_RADIUS_M)
                & (usable["footprint_m2"] >= FALLBACK_MIN_FOOTPRINT_M2)
                & ~usable.index.isin(used_buildings)
            ]
            if len(near):
                candidates = near.loc[[near["footprint_m2"].idxmax()]]
                record["building_method"] = "largest_nearby"
        if not candidates.empty:
            construction = candidates["building"] == "construction"
            built = candidates[~construction]
            floor, imputed = _floor(built, median_levels)
            record.update(
                buildings_n=int(len(built)),
                footprint_m2=float(built["footprint_m2"].sum()),
                floor_m2=floor if len(built) else np.nan,
                levels_imputed_n=imputed,
                under_construction_buildings=int(construction.sum()),
            )
            used_buildings.update(candidates.index)
        rows[i] = record

    out = schools.copy()
    extra = pd.DataFrame.from_dict(rows, orient="index").reindex(schools.index)
    for column in extra.columns:
        out[column] = extra[column]
    out["median_levels_used"] = median_levels
    return out


UNDERCAPTURE_M2 = 3000.0
NEW_SCHOOL_NUMBER = 86


def impute(schools: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = schools.copy()
    out["floor_m2_observed"] = out["floor_m2"]
    out["floor_source"] = out["building_method"]
    reference = out[
        out["catchment_based"] & out["floor_m2"].notna() & (out["floor_m2"] >= UNDERCAPTURE_M2)
    ]
    new = reference["number"] >= NEW_SCHOOL_NUMBER
    median_new = float(reference.loc[new, "floor_m2"].median())
    median_old = float(reference.loc[~new, "floor_m2"].median())
    for i, row in out[out["catchment_based"]].iterrows():
        missing = pd.isna(row["floor_m2"])
        under = not missing and row["floor_m2"] < UNDERCAPTURE_M2
        if not (missing or under):
            continue
        is_new = not pd.isna(row["number"]) and row["number"] >= NEW_SCHOOL_NUMBER
        out.at[i, "floor_m2"] = median_new if is_new else median_old
        out.at[i, "floor_source"] = "imputed_missing" if missing else "imputed_undercapture"
    out["capacity_index"] = out["floor_m2"] / float(
        out.loc[out["catchment_based"], "floor_m2"].median()
    )
    out.attrs["median_new"] = median_new
    out.attrs["median_old"] = median_old
    return out


def run() -> gpd.GeoDataFrame:
    schools = gpd.read_file(PROCESSED / "facilities.gpkg", layer="schools")
    keep = [
        c
        for c in schools.columns
        if c
        not in {
            "territory_ha",
            "buildings_n",
            "footprint_m2",
            "floor_m2",
            "levels_imputed_n",
            "under_construction_buildings",
            "building_method",
            "median_levels_used",
            "floor_m2_observed",
            "floor_source",
            "capacity_index",
        }
    ]
    result = impute(attach(schools[keep]))
    result.to_file(PROCESSED / "facilities.gpkg", layer="schools", driver="GPKG")
    return result

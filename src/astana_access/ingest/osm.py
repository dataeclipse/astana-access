import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon

from astana_access.config import CRS_GEO, RAW, settings
from astana_access.ingest.http import post_json

CITY_RELATION = 3087155

FACILITY_FILTERS = {
    "kindergarten": ['["amenity"="kindergarten"]'],
    "school": ['["amenity"="school"]'],
    "clinic": ['["amenity"="clinic"]', '["amenity"="doctors"]', '["healthcare"="centre"]'],
}

TEMPLATE = """
[out:json][timeout:180];
rel({city});
map_to_area -> .city;
(
{clauses}
);
out tags center;
"""


def _query(clauses: list[str]) -> dict:
    body = "\n".join(
        f"  node{c}(area.city);\n  way{c}(area.city);\n  rel{c}(area.city);" for c in clauses
    )
    query = TEMPLATE.format(city=CITY_RELATION, clauses=body)
    return post_json(settings.overpass_url, {"data": query})


def _elements_to_frame(elements: list[dict], category: str) -> gpd.GeoDataFrame:
    rows = []
    for element in elements:
        if element["type"] == "node":
            lon, lat = element.get("lon"), element.get("lat")
        else:
            center = element.get("center") or {}
            lon, lat = center.get("lon"), center.get("lat")
        if lon is None or lat is None:
            continue
        tags = element.get("tags", {})
        rows.append(
            {
                "osm_type": element["type"],
                "osm_id": element["id"],
                "category": category,
                "name": tags.get("name"),
                "name_ru": tags.get("name:ru"),
                "name_kk": tags.get("name:kk"),
                "operator": tags.get("operator"),
                "operator_type": tags.get("operator:type"),
                "street": tags.get("addr:street"),
                "housenumber": tags.get("addr:housenumber"),
                "capacity": tags.get("capacity"),
                "isced": tags.get("isced:level"),
                "geometry": Point(lon, lat),
            }
        )
    return gpd.GeoDataFrame(rows, crs=CRS_GEO)


def fetch_facilities(force: bool = False) -> gpd.GeoDataFrame:
    target = RAW / "osm" / "facilities.gpkg"
    if target.exists() and not force:
        return gpd.read_file(target)
    frames = []
    for category, clauses in FACILITY_FILTERS.items():
        payload = _query(clauses)
        frames.append(_elements_to_frame(payload.get("elements", []), category))
    result = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=CRS_GEO)
    target.parent.mkdir(parents=True, exist_ok=True)
    result.to_file(target, layer="facilities", driver="GPKG")
    return result


def fetch_buildings(force: bool = False) -> gpd.GeoDataFrame:
    target = RAW / "osm" / "buildings.gpkg"
    if target.exists() and not force:
        return gpd.read_file(target)
    query = f"""
    [out:json][timeout:600];
    rel({CITY_RELATION});
    map_to_area -> .city;
    way["building"](area.city);
    out geom;
    """
    payload = post_json(settings.overpass_url, {"data": query})
    rows = []
    for element in payload.get("elements", []):
        geometry = element.get("geometry")
        if not geometry or len(geometry) < 4:
            continue
        tags = element.get("tags", {})
        rows.append(
            {
                "osm_id": element["id"],
                "building": tags.get("building"),
                "levels": tags.get("building:levels"),
                "name": tags.get("name"),
                "amenity": tags.get("amenity"),
                "geometry": Polygon([(p["lon"], p["lat"]) for p in geometry]),
            }
        )
    result = gpd.GeoDataFrame(rows, crs=CRS_GEO)
    target.parent.mkdir(parents=True, exist_ok=True)
    result.to_file(target, layer="buildings", driver="GPKG")
    return result

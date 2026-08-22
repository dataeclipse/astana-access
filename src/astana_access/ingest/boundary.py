import json
import time
from pathlib import Path

import geopandas as gpd
import httpx
from shapely.geometry import shape

from astana_access.config import CRS_GEO, RAW, settings

CITY_RELATION = 3087155
NOMINATIM_LOOKUP = "https://nominatim.openstreetmap.org/lookup"
OVERPASS_DISTRICTS = """
[out:json][timeout:120];
rel({city});
map_to_area -> .city;
rel["boundary"="administrative"]["admin_level"~"^(6|8)$"](area.city);
out tags center;
"""


def _lookup(osm_ids: list[str]) -> list[dict]:
    response = httpx.get(
        NOMINATIM_LOOKUP,
        params={
            "osm_ids": ",".join(osm_ids),
            "format": "json",
            "polygon_geojson": "1",
        },
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout * 2,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.json()


def _to_frame(records: list[dict]) -> gpd.GeoDataFrame:
    rows = []
    for record in records:
        geometry = record.get("geojson")
        if geometry is None:
            continue
        rows.append(
            {
                "osm_id": record["osm_id"],
                "osm_type": record["osm_type"],
                "name": record.get("name") or record.get("display_name", "").split(",")[0],
                "display_name": record.get("display_name"),
                "geometry": shape(geometry),
            }
        )
    return gpd.GeoDataFrame(rows, crs=CRS_GEO)


def fetch_city(force: bool = False) -> gpd.GeoDataFrame:
    target = RAW / "boundary" / "city.geojson"
    if target.exists() and not force:
        return gpd.read_file(target)
    frame = _to_frame(_lookup([f"R{CITY_RELATION}"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(target, driver="GeoJSON")
    return frame


def district_relations() -> list[int]:
    query = OVERPASS_DISTRICTS.format(city=CITY_RELATION)
    response = httpx.post(
        settings.overpass_url,
        data={"data": query},
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout * 4,
    )
    response.raise_for_status()
    return [element["id"] for element in response.json().get("elements", [])]


def fetch_districts(force: bool = False) -> gpd.GeoDataFrame:
    target = RAW / "boundary" / "districts.geojson"
    if target.exists() and not force:
        return gpd.read_file(target)
    ids = district_relations()
    time.sleep(settings.request_delay)
    frame = _to_frame(_lookup([f"R{i}" for i in ids]))
    city = fetch_city().union_all()
    frame = frame[frame.representative_point().within(city)].reset_index(drop=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(target, driver="GeoJSON")
    return frame


def write_manifest(path: Path, entries: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

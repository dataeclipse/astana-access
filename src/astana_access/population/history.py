import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW, settings
from astana_access.ingest.http import post_json

SNAPSHOT = "2023-01-01T00:00:00Z"
BBOX = "50.95,71.15,51.40,71.85"
OFFICIAL_2023 = {
    "Almaty+Saraishyk": 366_708,
    "Esil+Nura": 409_282,
    "Saryarka": 345_193,
    "Baikonur": 233_252,
}
UNIT_2023 = {
    "Almaty": "Almaty+Saraishyk",
    "Saraishyk": "Almaty+Saraishyk",
    "Esil": "Esil+Nura",
    "Nura": "Esil+Nura",
    "Saryarka": "Saryarka",
    "Baikonur": "Baikonur",
}
ALPHA = 0.2
MATCH_SHARE = 0.3


def fetch(query_body: str, name: str) -> dict:
    target = RAW / "osm" / f"{name}_{SNAPSHOT[:10]}.json"
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    query = f'[out:json][timeout:600][date:"{SNAPSHOT}"];\n{query_body}\nout tags geom;'
    payload = post_json(settings.overpass_url, {"data": query})
    target.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def polygons(payload: dict, keys: tuple[str, ...]) -> gpd.GeoDataFrame:
    rows = []
    for element in payload["elements"]:
        geometry = element.get("geometry")
        if not geometry or len(geometry) < 4:
            continue
        ring = [(p["lon"], p["lat"]) for p in geometry]
        if ring[0] != ring[-1]:
            continue
        tags = element.get("tags", {})
        rows.append(
            {
                "osm_id": element["id"],
                **{key: tags.get(key) for key in keys},
                "geometry": Polygon(ring),
            }
        )
    return gpd.GeoDataFrame(rows, crs=CRS_GEO).to_crs(CRS_METRIC)


def buildings_2023() -> gpd.GeoDataFrame:
    payload = fetch(f"way({BBOX})[building];", "buildings")
    return polygons(payload, ("building",))


def landuse_2023() -> gpd.GeoDataFrame:
    body = (
        f'(way({BBOX})[landuse];way({BBOX})[amenity~"^(school|kindergarten|university|college|'
        f'hospital|clinic|marketplace|parking|place_of_worship|prison|fuel)$"];'
        f'way({BBOX})[leisure~"^(park|stadium|sports_centre|pitch|garden)$"];'
        f"way({BBOX})[military];way({BBOX})[aeroway];);"
    )
    payload = fetch(body, "landuse")
    frame = polygons(payload, ("landuse", "amenity", "leisure", "military", "aeroway", "building"))
    frame = frame[frame["building"].isna()]
    frame["value"] = (
        frame["landuse"].fillna(frame["amenity"]).fillna(frame["leisure"]).fillna(frame["military"])
    ).fillna(frame["aeroway"])
    return frame


def existed(dwellings: gpd.GeoDataFrame, old: gpd.GeoDataFrame) -> np.ndarray:
    osm = dwellings["source"] == "OpenStreetMap"
    joined = gpd.overlay(
        dwellings.loc[osm, ["id", "geometry"]], old[["osm_id", "geometry"]], how="intersection"
    )
    overlap = joined.assign(area=joined.area).groupby("id")["area"].sum()
    own = dwellings.set_index("id").geometry.area
    share = (overlap / own.reindex(overlap.index)).reindex(dwellings["id"]).fillna(0).to_numpy()
    return np.where(osm.to_numpy(), share >= MATCH_SHARE, True)


def build() -> dict:
    current = gpd.read_parquet(PROCESSED / "dwellings.parquet")
    buildings = pd.read_parquet(
        PROCESSED / "buildings.parquet", columns=["id", "source", "district"]
    )
    current = current.merge(buildings, on="id", how="left")
    old = buildings_2023()
    current["existed_2023"] = existed(current, old)
    kept = current[current["existed_2023"]].copy()
    kept["unit"] = kept["district"].map(UNIT_2023)
    kept["w"] = kept["floor_area_m2"]
    station = kept.groupby("station")["w"].sum()
    station_unit = kept.groupby("station")["unit"].agg(lambda values: values.mode().iat[0])
    tempered = station**ALPHA
    share = tempered / tempered.groupby(station_unit).transform("sum")
    station_population = share * station_unit.map(OFFICIAL_2023)
    within = kept["w"] / kept["station"].map(station)
    kept["pop_2023"] = within * kept["station"].map(station_population)
    kept[["id", "station", "district", "unit", "pop_2023", "geometry"]].to_parquet(
        PROCESSED / "dwellings_2023.parquet"
    )
    landuse_2023().to_parquet(PROCESSED / "landuse_2023.parquet")
    summary = {
        "osm_buildings_2023": int(len(old)),
        "dwellings_now": int(len(current)),
        "dwellings_existing_2023": int(len(kept)),
        "floor_area_share_existing_2023": float(
            kept["floor_area_m2"].sum() / current["floor_area_m2"].sum()
        ),
        "new_floor_area_by_district_share": (
            current.loc[~current["existed_2023"]].groupby("district")["floor_area_m2"].sum()
            / current.groupby("district")["floor_area_m2"].sum()
        )
        .round(3)
        .to_dict(),
        "population_2023": float(kept["pop_2023"].sum()),
    }
    return summary

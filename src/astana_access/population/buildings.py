import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from astana_access.config import CRS_GEO, CRS_METRIC, INTERIM, PROCESSED, RAW

OVERTURE = RAW / "overture" / "buildings_astana_2026-09-23.parquet"
RESIDENTIAL = {
    "apartments",
    "residential",
    "dormitory",
    "house",
    "detached",
    "semidetached_house",
    "terrace",
    "bungalow",
}
ANCILLARY = {"garage", "garages", "shed", "roof", "hut", "carport", "greenhouse", "service"}
NONRES_SUBTYPE = {
    "commercial",
    "education",
    "industrial",
    "civic",
    "transportation",
    "outbuilding",
    "service",
    "medical",
    "entertainment",
    "religious",
    "agricultural",
    "military",
}
LANDUSE_GROUP = {
    "residential": "residential",
    "allotments": "allotments",
    "industrial": "nonres",
    "commercial": "nonres",
    "retail": "nonres",
    "garages": "nonres",
    "railway": "nonres",
    "military": "nonres",
    "institutional": "nonres",
    "construction": "construction",
    "school": "nonres",
    "kindergarten": "nonres",
    "university": "nonres",
    "college": "nonres",
    "hospital": "nonres",
    "clinic": "nonres",
    "marketplace": "nonres",
    "prison": "nonres",
    "place_of_worship": "nonres",
    "aerodrome": "nonres",
    "apron": "nonres",
    "cemetery": "nonres",
}
USE_KEYS = ["amenity", "office", "shop", "tourism", "government", "leisure", "healthcare", "craft"]
HOME_NAME = r"(?i)(?<![а-яa-z])жк(?![а-яa-z])|жилой комплекс|жилой дом|тұрғын үй|общежити"
WORK_NAME = (
    r"(?i)(?<![а-яa-z])(?:бц|трц|тц|трк|тд)(?![а-яa-z])|бизнес|торгов|министерств|офис|гостиниц|"
    r"отель|hotel|банк|завод|склад|рынок|базар|mall|маркет|market|центр|автосалон|азс|"
    r"поликлиник|больниц|школ|колледж|университет|мечеть|церковь|музей|театр|спорт"
)
MIN_DWELLING_M2 = 35.0
HOUSE_MAX_M2 = 300.0
NEIGHBOUR_RADII = (100.0, 300.0)
LABEL_SNAP_M = 12.0


def load() -> gpd.GeoDataFrame:
    raw = pd.read_parquet(OVERTURE)
    geometry = shapely.from_wkb(raw["wkb"].apply(bytes))
    frame = gpd.GeoDataFrame(raw.drop(columns="wkb"), geometry=geometry, crs=CRS_GEO)
    city = gpd.read_file(RAW / "boundary" / "city.geojson").union_all()
    frame = frame[frame.geometry.representative_point().within(city)].to_crs(CRS_METRIC)
    frame = frame[frame.geometry.is_valid & ~frame.geometry.is_empty].reset_index(drop=True)
    frame["footprint_m2"] = frame.area
    frame["perimeter_m"] = frame.length
    frame["compactness"] = 4 * np.pi * frame["footprint_m2"] / frame["perimeter_m"] ** 2
    centre = frame.geometry.representative_point()
    frame["x"] = centre.x
    frame["y"] = centre.y
    frame["osm"] = frame["source"] == "OpenStreetMap"
    districts = gpd.read_file(PROCESSED / "districts.gpkg", layer="districts").to_crs(CRS_METRIC)
    points = gpd.GeoDataFrame(frame[["id"]], geometry=centre, crs=CRS_METRIC)
    joined = gpd.sjoin(points, districts[["name_en", "geometry"]], how="left", predicate="within")
    frame["district"] = joined.loc[~joined.index.duplicated(), "name_en"].to_numpy()
    return frame


def add_landuse(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    landuse = gpd.read_file(RAW / "osm" / "landuse.gpkg").to_crs(CRS_METRIC)
    landuse["group"] = landuse["value"].map(LANDUSE_GROUP)
    landuse = landuse[landuse["group"].notna()].copy()
    landuse["area"] = landuse.area
    points = gpd.GeoDataFrame(
        frame[["id"]], geometry=gpd.points_from_xy(frame["x"], frame["y"]), crs=CRS_METRIC
    )
    joined = gpd.sjoin(points, landuse[["group", "area", "geometry"]], predicate="within")
    smallest = joined.sort_values("area").groupby(level=0)["group"].first()
    frame["landuse"] = smallest.reindex(frame.index).fillna("none").to_numpy()
    return frame


def add_addresses(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    addresses = pd.read_parquet(RAW / "osm" / "addresses.parquet")
    addresses = addresses[addresses["housenumber"].notna()]
    points = gpd.GeoDataFrame(
        addresses[["flats"]],
        geometry=gpd.points_from_xy(addresses["lon"], addresses["lat"]),
        crs=CRS_GEO,
    ).to_crs(CRS_METRIC)
    joined = gpd.sjoin(points, frame[["geometry"]], predicate="within")
    counts = joined.groupby("index_right").size()
    flats = pd.to_numeric(joined["flats"], errors="coerce").groupby(joined["index_right"]).max()
    frame["addresses"] = counts.reindex(frame.index).fillna(0).to_numpy()
    frame["flats"] = flats.reindex(frame.index).to_numpy()
    return frame


def add_neighbourhood(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    coords = frame[["x", "y"]].to_numpy()
    tree = cKDTree(coords)
    area = frame["footprint_m2"].to_numpy()
    floors = pd.to_numeric(frame["num_floors"], errors="coerce").to_numpy()
    for radius in NEIGHBOUR_RADII:
        neighbours = tree.query_ball_point(coords, r=radius)
        tag = int(radius)
        frame[f"n_{tag}"] = [len(items) - 1 for items in neighbours]
        frame[f"area_median_{tag}"] = [float(np.median(area[items])) for items in neighbours]
        frame[f"built_share_{tag}"] = [
            float(area[items].sum() / (np.pi * radius**2)) for items in neighbours
        ]
        frame[f"floors_median_{tag}"] = [
            float(np.nanmedian(floors[items])) if np.isfinite(floors[items]).any() else np.nan
            for items in neighbours
        ]
    return frame


def add_uses(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    uses = pd.read_parquet(RAW / "osm" / "uses.parquet")
    points = gpd.GeoDataFrame(
        uses, geometry=gpd.points_from_xy(uses["lon"], uses["lat"]), crs=CRS_GEO
    ).to_crs(CRS_METRIC)
    joined = gpd.sjoin(points, frame[["geometry"]], predicate="within")
    nodes = joined[joined["osm_type"] == "node"]
    frame["poi_nodes"] = nodes.groupby("index_right").size().reindex(frame.index).fillna(0)
    whole = joined[joined["osm_type"] != "node"].copy()
    whole = whole[~whole["index_right"].duplicated()]
    name = whole["name"].fillna("")
    use_tag = whole[USE_KEYS].notna().any(axis=1)
    home = name.str.contains(HOME_NAME, regex=True)
    work = name.str.contains(WORK_NAME, regex=True)
    verdict = pd.Series(np.nan, index=whole.index)
    verdict[use_tag | work] = 0.0
    verdict[home & ~work] = 1.0
    frame["label_use"] = pd.Series(verdict.to_numpy(), index=whole["index_right"]).reindex(
        frame.index
    )
    return frame


def label_points() -> gpd.GeoDataFrame:
    polling = pd.read_csv(PROCESSED / "polling_houses.csv")
    polling = polling[polling["lon"].notna() & polling["role"].isin(["listed", "include"])]
    polling = polling.assign(origin="polling")[["lon", "lat", "origin"]]
    catchment = pd.read_csv(INTERIM / "sakura_catchment_geocoded.csv")
    catchment = catchment[catchment["precision"] == "house"]
    catchment = catchment.assign(origin="catchment")[["lon", "lat", "origin"]]
    both = pd.concat([polling, catchment], ignore_index=True)
    return gpd.GeoDataFrame(
        both, geometry=gpd.points_from_xy(both["lon"], both["lat"]), crs=CRS_GEO
    ).to_crs(CRS_METRIC)


def add_labels(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    kind = frame["class"].fillna("")
    subtype = frame["subtype"].fillna("")
    tagged = pd.Series(np.nan, index=frame.index)
    tagged[kind.isin(RESIDENTIAL)] = 1.0
    nonres = subtype.isin(NONRES_SUBTYPE) | kind.isin(ANCILLARY)
    tagged[nonres & ~kind.isin(RESIDENTIAL)] = 0.0
    frame["label_tag"] = tagged
    points = label_points()
    nearest = gpd.sjoin_nearest(
        points, frame[["geometry"]], max_distance=LABEL_SNAP_M, distance_col="gap"
    )
    nearest = nearest[~nearest.index.duplicated()]
    frame["label_list"] = np.nan
    for origin, group in nearest.groupby("origin"):
        frame.loc[group["index_right"].unique(), "label_list"] = 1.0
        frame.loc[group["index_right"].unique(), "list_origin"] = origin
    return frame


def build() -> gpd.GeoDataFrame:
    frame = load()
    frame = add_landuse(frame)
    frame = add_addresses(frame)
    frame = add_neighbourhood(frame)
    frame = add_uses(frame)
    frame = add_labels(frame)
    frame.to_parquet(INTERIM / "buildings_features.parquet")
    return frame

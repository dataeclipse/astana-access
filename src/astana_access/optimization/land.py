import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt

from astana_access.config import CRS_METRIC, PROCESSED, RAW

CELL_M = 10.0
ROAD_HALF_WIDTH_M = {
    "trunk": 20.0,
    "trunk_link": 10.0,
    "primary": 18.0,
    "primary_link": 9.0,
    "secondary": 14.0,
    "secondary_link": 8.0,
    "tertiary": 10.0,
    "tertiary_link": 6.0,
    "residential": 6.0,
    "unclassified": 6.0,
    "living_street": 5.0,
    "service": 4.0,
}
BLOCKING_LANDUSE = {
    "industrial",
    "commercial",
    "retail",
    "garages",
    "railway",
    "military",
    "cemetery",
    "forest",
    "allotments",
    "construction",
    "landfill",
    "quarry",
    "reservoir",
    "aerodrome",
    "apron",
    "school",
    "kindergarten",
    "university",
    "college",
    "hospital",
    "clinic",
    "prison",
    "park",
    "stadium",
    "sports_centre",
    "pitch",
    "garden",
    "parking",
    "place_of_worship",
    "marketplace",
    "fuel",
}
BUILDING_BUFFER_M = 10.0
WATER_BUFFER_M = 60.0
RAIL_BUFFER_M = 25.0


def building_footprints(year: int) -> gpd.GeoSeries:
    frame = pd.read_parquet(PROCESSED / "buildings.parquet", columns=["source", "geometry"])
    current = gpd.GeoSeries.from_wkb(frame["geometry"], crs=CRS_METRIC)
    if year >= 2026:
        return current
    from astana_access.population.history import buildings_2023

    microsoft = current[(frame["source"] != "OpenStreetMap").to_numpy()]
    return pd.concat([microsoft, buildings_2023().geometry], ignore_index=True)


def landuse_frame(year: int) -> gpd.GeoDataFrame:
    if year >= 2026:
        return gpd.read_file(RAW / "osm" / "landuse.gpkg").to_crs(CRS_METRIC)
    return gpd.read_parquet(PROCESSED / "landuse_2023.parquet")


def obstacles(year: int) -> list:
    shapes = []
    shapes.extend(building_footprints(year).buffer(BUILDING_BUFFER_M, resolution=2))
    edges = pd.read_parquet(PROCESSED / "walk_edges.parquet")
    nodes = pd.read_parquet(PROCESSED / "walk_nodes.parquet")
    xy = nodes[["x", "y"]].to_numpy()
    from shapely import linestrings

    for highway, width in ROAD_HALF_WIDTH_M.items():
        part = edges[edges["highway"] == highway]
        if part.empty:
            continue
        coords = np.stack([xy[part["i"].to_numpy()], xy[part["j"].to_numpy()]], axis=1)
        lines = gpd.GeoSeries(linestrings(coords), crs=CRS_METRIC)
        shapes.extend(lines.buffer(width, resolution=2))
    lines = gpd.read_file(RAW / "osm" / "lines.gpkg").to_crs(CRS_METRIC)
    shapes.extend(lines[lines["kind"] == "waterway"].buffer(WATER_BUFFER_M, resolution=2))
    shapes.extend(lines[lines["kind"] == "railway"].buffer(RAIL_BUFFER_M, resolution=2))
    landuse = landuse_frame(year)
    shapes.extend(landuse[landuse["value"].isin(BLOCKING_LANDUSE)].geometry)
    return shapes


def free_land_raster(year: int = 2026) -> tuple[np.ndarray, rasterio.Affine]:
    city = gpd.read_file(RAW / "boundary" / "city.geojson").to_crs(CRS_METRIC)
    minx, miny, maxx, maxy = city.total_bounds
    width = int(np.ceil((maxx - minx) / CELL_M))
    height = int(np.ceil((maxy - miny) / CELL_M))
    transform = from_origin(minx, maxy, CELL_M, CELL_M)
    inside = rasterize(
        [(geometry, 1) for geometry in city.geometry],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
    )
    blocked = rasterize(
        [
            (geometry, 1)
            for geometry in obstacles(year)
            if geometry is not None and not geometry.is_empty
        ],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
    )
    free = (inside == 1) & (blocked == 0)
    clearance = distance_transform_edt(free) * CELL_M
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": CRS_METRIC,
        "transform": transform,
        "compress": "deflate",
    }
    with rasterio.open(clearance_path(year), "w", **profile) as target:
        target.write(clearance.astype("float32"), 1)
    return clearance, transform


def clearance_path(year: int):
    return PROCESSED / (
        "free_land_clearance.tif" if year >= 2026 else f"free_land_clearance_{year}.tif"
    )


def load_clearance(year: int = 2026) -> tuple[np.ndarray, rasterio.Affine]:
    path = clearance_path(year)
    if not path.exists():
        return free_land_raster(year)
    with rasterio.open(path) as source:
        return source.read(1), source.transform


def plot_sites(
    centres: np.ndarray, clearance: np.ndarray, transform, radius_needed_m: float, search_m: float
) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = np.nonzero(clearance >= radius_needed_m)
    if len(rows) == 0:
        return np.full((len(centres), 2), np.nan), np.full(len(centres), np.inf)
    xs = transform.c + (cols + 0.5) * transform.a
    ys = transform.f + (rows + 0.5) * transform.e
    from scipy.spatial import cKDTree

    tree = cKDTree(np.column_stack([xs, ys]))
    distance, index = tree.query(centres, distance_upper_bound=search_m)
    found = np.isfinite(distance)
    sites = np.full((len(centres), 2), np.nan)
    sites[found] = np.column_stack([xs, ys])[index[found]]
    return sites, distance

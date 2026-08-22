import geopandas as gpd
import h3
import pandas as pd
from exactextract import exact_extract
from shapely.geometry import Polygon

from astana_access.config import CRS_GEO, CRS_METRIC, H3_RESOLUTION, PROCESSED

COHORTS = {
    "preschool": {"t_01": 1.0, "t_05": 0.4},
    "school": {"t_05": 0.6, "t_10": 1.0, "t_15": 0.6},
}


def cells_for(geometry, resolution: int = H3_RESOLUTION, contain: str = "overlap") -> list[str]:
    shape = h3.geo_to_h3shape(geometry.__geo_interface__)
    return list(h3.h3shape_to_cells_experimental(shape, resolution, contain=contain))


def cell_polygon(cell: str) -> Polygon:
    return Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)])


def build_grid(city: gpd.GeoDataFrame, resolution: int = H3_RESOLUTION) -> gpd.GeoDataFrame:
    geometry = city.to_crs(CRS_GEO).union_all()
    cells = sorted(set(cells_for(geometry, resolution)))
    rows = [{"h3": cell, "geometry": cell_polygon(cell)} for cell in cells]
    grid = gpd.GeoDataFrame(rows, crs=CRS_GEO)
    grid["area_km2"] = grid.to_crs(CRS_METRIC).area / 1e6
    return grid


def zonal_sum(grid: gpd.GeoDataFrame, rasters: dict[str, str]) -> pd.DataFrame:
    result = pd.DataFrame({"h3": grid["h3"].to_numpy()})
    for name, path in rasters.items():
        extracted = exact_extract(str(path), grid, ["sum"], output="pandas")
        result[name] = extracted["sum"].to_numpy()
    return result


def add_cohorts(population: pd.DataFrame) -> pd.DataFrame:
    frame = population.copy()
    for cohort, weights in COHORTS.items():
        total = 0.0
        for band, weight in weights.items():
            total = total + frame[band].fillna(0) * weight
        frame[cohort] = total
    return frame


def assign_districts(grid: gpd.GeoDataFrame, districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    points = grid.copy()
    points["geometry"] = grid.representative_point()
    joined = gpd.sjoin(points, districts[["name_en", "geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    out = grid.copy()
    out["district"] = joined["name_en"].to_numpy()
    return out


def write(grid: gpd.GeoDataFrame, name: str = "grid") -> None:
    target = PROCESSED / "grid.gpkg"
    target.parent.mkdir(parents=True, exist_ok=True)
    grid.to_file(target, layer=name, driver="GPKG")

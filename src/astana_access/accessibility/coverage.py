import geopandas as gpd
import h3
import numpy as np
import pandas as pd

from astana_access.accessibility.network import WalkNetwork, load
from astana_access.config import CRS_GEO, CRS_METRIC, H3_RESOLUTION, PROCESSED, RAW

LIMIT_M = 2500.0
RADII_M = (300, 500, 750, 1000, 1500)
VARIANTS = ("worldpop", "floor", "station", "station_equal")
COHORT = {"school": "school", "preschool": "preschool"}
MIN_GROUND_M2 = 10_000.0
GROUND_GAP_M = 150.0


def unnamed_school_grounds(schools: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    landuse = gpd.read_file(RAW / "osm" / "landuse.gpkg").to_crs(CRS_METRIC)
    grounds = landuse[
        (landuse["key"] == "amenity") & (landuse["value"] == "school") & landuse["name"].isna()
    ].copy()
    grounds = grounds[grounds.area >= MIN_GROUND_M2]
    known = schools[schools["in_scope"]].to_crs(CRS_METRIC)
    gap = grounds.geometry.apply(lambda geometry: known.distance(geometry).min())
    grounds = grounds[gap > GROUND_GAP_M]
    return gpd.GeoDataFrame(
        {
            "facility_id": "ground" + grounds["osm_id"].astype(str),
            "number": np.nan,
            "presumed_new": True,
            "area_ha": grounds.area / 1e4,
        },
        geometry=grounds.geometry.centroid,
        crs=CRS_METRIC,
    )


def facilities() -> dict[str, gpd.GeoDataFrame]:
    every = gpd.read_file(PROCESSED / "facilities.gpkg", layer="schools")
    schools = every[every["catchment_based"] & every.geometry.notna()].copy()
    schools["facility_id"] = schools["facility_id"].astype(str)
    schools["presumed_new"] = False
    schools = schools.to_crs(CRS_METRIC)
    grounds = unnamed_school_grounds(every)
    preschools = gpd.read_file(PROCESSED / "facilities.gpkg", layer="preschools")
    preschools = preschools[preschools.geometry.notna()].copy()
    return {
        "school": pd.concat([schools, grounds], ignore_index=True),
        "preschool": preschools.to_crs(CRS_METRIC),
    }


def demand_points() -> pd.DataFrame:
    dwellings = gpd.read_parquet(PROCESSED / "dwellings.parquet")
    centre = dwellings.geometry.representative_point()
    lonlat = gpd.GeoSeries(centre, crs=CRS_METRIC).to_crs(CRS_GEO)
    cells = [h3.latlng_to_cell(p.y, p.x, H3_RESOLUTION) for p in lonlat]
    grid = gpd.read_file(PROCESSED / "grid_population.gpkg").set_index("h3")
    share = {}
    for cohort in COHORT.values():
        ratio = (grid[cohort] / grid["total"]).where(grid["total"] > 0)
        unit_ratio = grid.groupby("unit")[cohort].transform("sum") / grid.groupby("unit")[
            "total"
        ].transform("sum")
        share[cohort] = ratio.fillna(unit_ratio)
    frame = pd.DataFrame(
        {
            "point_id": "b" + dwellings["id"].astype(str),
            "kind": "dwelling",
            "h3": cells,
            "x": centre.x.to_numpy(),
            "y": centre.y.to_numpy(),
        }
    )
    for variant in ("floor", "station", "station_equal"):
        population = dwellings[f"pop_{variant}"].to_numpy()
        for cohort in COHORT.values():
            frame[f"{cohort}_{variant}"] = (
                population * frame["h3"].map(share[cohort]).fillna(0).to_numpy()
            )
    cells_frame = grid.reset_index()
    cells_frame = cells_frame[cells_frame["pop_worldpop"] > 0]
    centroid = gpd.GeoSeries(cells_frame.geometry, crs=CRS_GEO).to_crs(CRS_METRIC).centroid
    cell_points = pd.DataFrame(
        {
            "point_id": "c" + cells_frame["h3"].astype(str),
            "kind": "cell",
            "h3": cells_frame["h3"].to_numpy(),
            "x": centroid.x.to_numpy(),
            "y": centroid.y.to_numpy(),
        }
    )
    for cohort in COHORT.values():
        cell_points[f"{cohort}_worldpop"] = cells_frame[f"{cohort}_worldpop"].to_numpy()
    return pd.concat([frame, cell_points], ignore_index=True)


def origin_destination(
    network: WalkNetwork, points: pd.DataFrame, sites: gpd.GeoDataFrame, id_column: str
) -> pd.DataFrame:
    point_node, point_gap = network.snap(points["x"].to_numpy(), points["y"].to_numpy())
    centre = sites.geometry.representative_point()
    site_node, site_gap = network.snap(centre.x.to_numpy(), centre.y.to_numpy())
    columns = np.unique(point_node)
    column_of = np.searchsorted(columns, point_node)
    rows = []
    for start in range(0, len(sites), 64):
        block = network.distances(site_node[start : start + 64], LIMIT_M)[:, columns]
        for offset, distances in enumerate(block):
            index = start + offset
            reach = distances[column_of] + point_gap + site_gap[index]
            hit = np.flatnonzero(reach <= LIMIT_M)
            rows.append(
                pd.DataFrame(
                    {
                        "facility_id": sites[id_column].iloc[index],
                        "point_id": points["point_id"].to_numpy()[hit],
                        "distance_m": reach[hit].astype("float32"),
                    }
                )
            )
    return pd.concat(rows, ignore_index=True)


def build() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    network = load()
    points = demand_points()
    points.to_parquet(PROCESSED / "demand_points.parquet")
    od = {}
    for kind, sites in facilities().items():
        table = origin_destination(network, points, sites, "facility_id")
        table.to_parquet(PROCESSED / f"od_walk_{kind}.parquet")
        od[kind] = table
    return points, od


def nearest(points: pd.DataFrame, od: pd.DataFrame) -> pd.Series:
    best = od.groupby("point_id")["distance_m"].min()
    return points["point_id"].map(best).fillna(np.inf)


def coverage_table(
    points: pd.DataFrame,
    od: dict[str, pd.DataFrame],
    by: str | None = None,
    exclude: frozenset[str] = frozenset(),
) -> pd.DataFrame:
    rows = []
    for kind, table in od.items():
        table = table[~table["facility_id"].isin(exclude)]
        distance = nearest(points, table).to_numpy()
        groups = points.groupby(by).indices if by else {"city": np.arange(len(points))}
        for group, index in groups.items():
            for variant in VARIANTS:
                column = f"{COHORT[kind]}_{variant}"
                if column not in points:
                    continue
                weight = points[column].fillna(0).to_numpy()[index]
                if weight.sum() <= 0:
                    continue
                for radius in RADII_M:
                    rows.append(
                        {
                            "kind": kind,
                            "area": group,
                            "variant": variant,
                            "radius_m": radius,
                            "children": float(weight.sum()),
                            "covered_share": float(
                                weight[distance[index] <= radius].sum() / weight.sum()
                            ),
                        }
                    )
    return pd.DataFrame(rows)

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED

MIN_DWELLING_M2 = 35.0
LARGE_M2 = 300.0
NEIGHBOURS = 7
REACH_M = 400.0
SNAP_M = 12.0
OFFICIAL_2025 = {
    "Almaty+Saraishyk": 409_873,
    "Baikonur": 227_043,
    "Esil": 293_451,
    "Nura": 246_763,
    "Saryarka": 351_573,
}
UNIT = {"Almaty": "Almaty+Saraishyk", "Saraishyk": "Almaty+Saraishyk"}


def impute_floors(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    table = frame.copy()
    floors = pd.to_numeric(table["num_floors"], errors="coerce")
    floors = floors.where((floors >= 1) & (floors <= 60))
    large = table["footprint_m2"] >= LARGE_M2
    table["floors"] = floors
    table["floors_source"] = np.where(floors.notna(), "tag", "")

    small_known = table[~large & floors.notna()]
    small_median = float(small_known["floors"].median()) if len(small_known) else 1.0
    small_missing = ~large & floors.isna()
    table.loc[small_missing, "floors"] = small_median
    table.loc[small_missing, "floors_source"] = "small_median"

    donors = table[large & floors.notna() & (table["p_residential"] >= 0.5)]
    tree = cKDTree(donors[["x", "y"]].to_numpy())
    donor_floors = donors["floors"].to_numpy()
    district_median = donors.groupby("district")["floors"].median()
    city_median = float(donors["floors"].median())

    def estimate(points: np.ndarray, skip_self: bool) -> np.ndarray:
        k = NEIGHBOURS + int(skip_self)
        distance, index = tree.query(points, k=k, distance_upper_bound=REACH_M)
        if skip_self:
            distance, index = distance[:, 1:], index[:, 1:]
        values = np.where(
            np.isfinite(distance), donor_floors[np.minimum(index, len(donors) - 1)], np.nan
        )
        counts = np.isfinite(values).sum(axis=1)
        with np.errstate(all="ignore"):
            median = np.nanmedian(values, axis=1)
        return np.where(counts >= 3, median, np.nan)

    check = estimate(donors[["x", "y"]].to_numpy(), skip_self=True)
    valid = np.isfinite(check)
    error = check[valid] - donor_floors[valid]
    quality = {
        "donors": int(len(donors)),
        "checked": int(valid.sum()),
        "mae_floors": float(np.abs(error).mean()),
        "bias_floors": float(error.mean()),
        "within_2_floors": float((np.abs(error) <= 2).mean()),
        "small_median": small_median,
    }

    large_missing = large & floors.isna()
    guess = estimate(table.loc[large_missing, ["x", "y"]].to_numpy(), skip_self=False)
    fallback = table.loc[large_missing, "district"].map(district_median).fillna(city_median)
    table.loc[large_missing, "floors"] = np.where(np.isfinite(guess), guess, fallback.to_numpy())
    table.loc[large_missing, "floors_source"] = np.where(
        np.isfinite(guess), "neighbours", "district_median"
    )
    dwelling = (table["p_residential"] >= 0.5) & (table["footprint_m2"] >= MIN_DWELLING_M2)
    table["dwelling"] = dwelling
    table["floor_area_m2"] = np.where(dwelling, table["footprint_m2"] * table["floors"], 0.0)
    table["form"] = np.where(large | (table["floors"] >= 3), "block", "house")
    return table, quality


def assign_stations(buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    stations = gpd.read_file(PROCESSED / "polling.gpkg", layer="stations")
    houses = pd.read_csv(PROCESSED / "polling_houses.csv")
    houses = houses[houses["lon"].notna()]
    points = gpd.GeoDataFrame(
        houses, geometry=gpd.points_from_xy(houses["lon"], houses["lat"]), crs=CRS_GEO
    ).to_crs(CRS_METRIC)
    table = buildings.copy()
    table["station"] = np.nan
    table["station_tier"] = ""
    dwellings = table[table["dwelling"]]

    snapped = gpd.sjoin_nearest(
        points, dwellings[["geometry"]], max_distance=SNAP_M, distance_col="gap"
    )
    snapped = snapped[~snapped.index.duplicated()]
    explicit = snapped[snapped["role"].isin(["listed", "include"])].drop_duplicates("index_right")
    table.loc[explicit["index_right"], "station"] = explicit["number"].to_numpy()
    table.loc[explicit["index_right"], "station_tier"] = "listed"
    barred = set(
        zip(
            snapped.loc[snapped["role"] == "exclude", "index_right"],
            snapped.loc[snapped["role"] == "exclude", "number"],
            strict=True,
        )
    )

    polygons = stations[stations.geometry.notna()].to_crs(CRS_METRIC).copy()
    polygons["poly_area"] = polygons.area
    polygons["complete"] = polygons["resolved"] == polygons["features"]
    centres = gpd.GeoDataFrame(
        dwellings[["district"]],
        geometry=gpd.points_from_xy(dwellings["x"], dwellings["y"]),
        crs=CRS_METRIC,
    )
    inside = gpd.sjoin(
        centres,
        polygons[["number", "district", "poly_area", "complete", "geometry"]],
        predicate="within",
    )
    inside = inside[inside["district_left"] == inside["district_right"]]
    inside = inside[
        [
            (index, number) not in barred
            for index, number in zip(inside.index, inside["number"], strict=True)
        ]
    ]
    inside = inside.sort_values(["complete", "poly_area"], ascending=[False, True])
    best = inside[~inside.index.duplicated()]
    free = best.index[table.loc[best.index, "station"].isna()]
    table.loc[free, "station"] = best.loc[free, "number"].to_numpy()
    table.loc[free, "station_tier"] = np.where(
        best.loc[free, "complete"], "polygon", "polygon_partial"
    )

    table["fill_distance_m"] = np.nan
    for _district, group in table[table["dwelling"]].groupby("district"):
        seeded = group[group["station"].notna()]
        open_rows = group[group["station"].isna()]
        if seeded.empty or open_rows.empty:
            continue
        tree = cKDTree(seeded[["x", "y"]].to_numpy())
        distance, index = tree.query(open_rows[["x", "y"]].to_numpy())
        table.loc[open_rows.index, "station"] = seeded["station"].to_numpy()[index]
        table.loc[open_rows.index, "station_tier"] = "nearest"
        table.loc[open_rows.index, "fill_distance_m"] = distance
    return table


def occupancy_weights(table: pd.DataFrame, house_factor: float) -> pd.Series:
    factor = np.where(table["form"] == "house", house_factor, 1.0)
    return table["floor_area_m2"] * factor


def district_fit(table: pd.DataFrame) -> pd.DataFrame:
    dwellings = table[table["dwelling"]].copy()
    dwellings["unit"] = dwellings["district"].replace(UNIT)
    area = dwellings.pivot_table(
        index="unit", columns="form", values="floor_area_m2", aggfunc="sum", fill_value=0.0
    )
    area["official"] = pd.Series(OFFICIAL_2025)
    return area.dropna()


def allocate(table: pd.DataFrame, house_factor: float) -> pd.Series:
    dwellings = table[table["dwelling"]]
    weight = occupancy_weights(dwellings, house_factor)
    unit = dwellings["district"].replace(UNIT)
    total = weight.groupby(unit).transform("sum")
    population = weight / total * unit.map(OFFICIAL_2025)
    return population.reindex(table.index).fillna(0.0)

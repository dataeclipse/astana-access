import json

import geopandas as gpd
import h3
import numpy as np
import pandas as pd

from astana_access.config import CRS_GEO, CRS_METRIC, H3_RESOLUTION, PROCESSED, REPORTS
from astana_access.ingest.stat_ages import cohort_shares, pooled_shares
from astana_access.population.surface import assign_stations, impute_floors

OFFICIAL_2026 = {
    "Almaty": 250_987,
    "Baikonur": 218_341,
    "Esil": 320_652,
    "Nura": 304_136,
    "Saraishyk": 192_351,
    "Saryarka": 352_709,
}
AGE_YEAR = 2026
HOUSING_STOCK_2025_MM2 = 36.7
APARTMENT_SHARE_2025 = 0.873
COMMISSIONED_2025_MM2 = 4.904965
COMMISSIONED_2025_INDIVIDUAL_MM2 = 0.068148
ALPHAS = (0.0, 0.1, 0.2, 0.3, 0.5, 1.0)
DEFAULT_ALPHA = 0.2
COHORTS = ("preschool", "school")


def house_factor(dwellings: pd.DataFrame) -> tuple[float, dict[str, float]]:
    gross = dwellings.groupby("form")["floor_area_m2"].sum() / 1e6
    blocks = HOUSING_STOCK_2025_MM2 * APARTMENT_SHARE_2025
    houses = HOUSING_STOCK_2025_MM2 - blocks
    blocks += COMMISSIONED_2025_MM2 - COMMISSIONED_2025_INDIVIDUAL_MM2
    houses += COMMISSIONED_2025_INDIVIDUAL_MM2
    detail = {
        "gross_block_mm2": float(gross["block"]),
        "gross_house_mm2": float(gross["house"]),
        "official_block_mm2": blocks,
        "official_house_mm2": houses,
        "net_to_gross_block": float(blocks / gross["block"]),
        "net_to_gross_house": float(houses / gross["house"]),
    }
    return float((houses / gross["house"]) / (blocks / gross["block"])), detail


def error_against_official(predicted: pd.Series) -> dict[str, float]:
    official = pd.Series(OFFICIAL_2026)
    scaled = predicted / predicted.sum() * official.sum()
    ratio = scaled / official
    return {
        "mean_abs_error": float((ratio - 1).abs().mean()),
        **{f"ratio_{k}": float(v) for k, v in ratio.items()},
    }


def allocate(dwellings: pd.DataFrame, alpha: float) -> pd.Series:
    station = dwellings.groupby("station")["weight"].sum()
    unit_of = dwellings.groupby("station")["unit"].agg(lambda values: values.mode().iat[0])
    tempered = station**alpha
    share = tempered / tempered.groupby(unit_of).transform("sum")
    station_population = share * unit_of.map(OFFICIAL_2026)
    within = dwellings["weight"] / dwellings["station"].map(station)
    return within * dwellings["station"].map(station_population)


def to_cells(frame: gpd.GeoDataFrame, columns: list[str]) -> pd.DataFrame:
    points = gpd.GeoSeries(
        gpd.points_from_xy(frame["x"], frame["y"]), crs=CRS_METRIC, index=frame.index
    ).to_crs(CRS_GEO)
    cells = [h3.latlng_to_cell(point.y, point.x, H3_RESOLUTION) for point in points]
    return frame[columns].groupby(np.asarray(cells)).sum()


def build() -> tuple[gpd.GeoDataFrame, dict]:
    buildings = gpd.read_parquet(PROCESSED / "buildings.parquet")
    table, floors_quality = impute_floors(buildings)
    table = assign_stations(gpd.GeoDataFrame(table, geometry="geometry", crs=CRS_METRIC))
    dwellings = table[table["dwelling"] & table["station"].notna()].copy()
    dwellings["unit"] = dwellings["district"]
    factor, housing = house_factor(dwellings)
    dwellings["weight"] = dwellings["floor_area_m2"] * np.where(
        dwellings["form"] == "house", factor, 1.0
    )

    grid = gpd.read_file(PROCESSED / "grid_pop.gpkg")
    grid["unit"] = grid["district"]
    diagnostics = {
        "floors": floors_quality,
        "housing": {**housing, "house_factor": factor},
        "district_fit": {
            "worldpop": error_against_official(grid.groupby("unit")["total"].sum()),
            "floor_area": error_against_official(dwellings.groupby("unit")["weight"].sum()),
        },
        "stations_with_buildings": int(dwellings["station"].nunique()),
        "assignment_share_of_floor_area": (
            dwellings.groupby("station_tier")["floor_area_m2"].sum()
            / dwellings["floor_area_m2"].sum()
        ).to_dict(),
    }
    station_weight = dwellings.groupby("station")["weight"].sum()
    station_unit = dwellings.groupby("station")["unit"].agg(lambda values: values.mode().iat[0])
    for alpha in ALPHAS:
        predicted = (station_weight**alpha).groupby(station_unit).sum()
        diagnostics["district_fit"][f"stations_alpha_{alpha}"] = error_against_official(predicted)

    unit_weight = dwellings.groupby("unit")["weight"].transform("sum")
    dwellings["pop_floor"] = (
        dwellings["weight"] / unit_weight * dwellings["unit"].map(OFFICIAL_2026)
    )
    dwellings["pop_station"] = allocate(dwellings, DEFAULT_ALPHA)
    dwellings["pop_station_equal"] = allocate(dwellings, 0.0)
    models = ["pop_floor", "pop_station", "pop_station_equal"]
    cells = to_cells(dwellings, models)

    grid = grid.set_index("h3")
    unit_total = grid.groupby("unit")["total"].transform("sum")
    grid["pop_worldpop"] = grid["total"] / unit_total * grid["unit"].map(OFFICIAL_2026)
    for model in models:
        grid[model] = cells[model].reindex(grid.index).fillna(0.0)
    outside = float(cells[models[0]].sum() - grid[models[0]].sum())
    diagnostics["population_outside_grid"] = outside
    official_shares = cohort_shares(AGE_YEAR)
    model_shares = pooled_shares(AGE_YEAR)
    diagnostics["cohort_share_official"] = official_shares.round(4).to_dict()
    diagnostics["cohort_share_model"] = model_shares.round(4).to_dict()
    diagnostics["cohort_share_worldpop"] = {
        cohort: (grid.groupby("unit")[cohort].sum() / grid.groupby("unit")["total"].sum())
        .round(4)
        .to_dict()
        for cohort in COHORTS
    }
    for cohort in COHORTS:
        share = grid["unit"].map(model_shares[cohort]).fillna(model_shares.at["City", cohort])
        grid[cohort] = grid["total"] * share
        for model in ["pop_worldpop", *models]:
            grid[f"{cohort}_{model.removeprefix('pop_')}"] = grid[model] * share
    correlation = grid[["pop_worldpop", *models]].corr(method="spearman")
    diagnostics["cell_rank_correlation"] = correlation.round(3).to_dict()
    grid = grid.reset_index()
    grid.to_file(PROCESSED / "grid_population.gpkg", layer="grid", driver="GPKG")
    keep = ["id", "station", "station_tier", "form", "floors", "floor_area_m2", *models, "geometry"]
    dwellings[keep].to_parquet(PROCESSED / "dwellings.parquet")
    (REPORTS / "population_model.json").write_text(
        json.dumps(diagnostics, indent=1, default=float), encoding="utf-8"
    )
    return grid, diagnostics

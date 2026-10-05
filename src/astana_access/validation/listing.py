import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from astana_access.accessibility.e2sfca import index, load_inputs, supply_measures
from astana_access.config import CRS_GEO, CRS_METRIC, DATA, PROCESSED, RAW, REPORTS
from astana_access.equity.analysis import BASE, COHORT, cell_values, deficit_cells, summary

SOURCE = RAW / "team" / "astana_spatial_inequity.xlsx"
PAIR_M = 150.0
NUMBER = re.compile(r"№\s*(\d+)")


def school_number(name: str) -> float:
    found = NUMBER.search(str(name))
    return float(found.group(1)) if found else np.nan


def load() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    city = gpd.read_file(RAW / "boundary" / "city.geojson").to_crs(CRS_METRIC).union_all()
    frames = []
    for sheet in (0, 1):
        table = pd.read_excel(SOURCE, sheet_name=sheet)
        table = table.drop_duplicates("2gis_url")
        frame = gpd.GeoDataFrame(
            table, geometry=gpd.points_from_xy(table["lon"], table["lat"]), crs=CRS_GEO
        ).to_crs(CRS_METRIC)
        frames.append(frame[frame.within(city)].copy())
    homes, schools = frames
    schools["number"] = schools["name"].map(school_number)
    return homes, schools


def schools_check(listing: gpd.GeoDataFrame) -> dict:
    every = gpd.read_file(PROCESSED / "facilities.gpkg", layer="schools").to_crs(CRS_METRIC)
    state = every[every["catchment_based"]]
    ours = set(state["number"].dropna())
    theirs = set(listing["number"].dropna())
    numbered = listing.dropna(subset=["number"]).drop_duplicates("number")
    pairs = numbered.merge(
        state.dropna(subset=["number"])[["number", "geometry"]], on="number", suffixes=("", "_ours")
    )
    distance = gpd.GeoSeries(pairs["geometry"]).distance(gpd.GeoSeries(pairs["geometry_ours"]))
    other = every[~every["catchment_based"]].dropna(subset=["number"])
    only_listing = sorted(theirs - ours)
    programme = pd.read_csv(DATA / "labels" / "comfortable_schools.csv")
    programme_numbers = set(programme["number"].dropna())
    nearest = gpd.sjoin_nearest(
        listing, every[["geometry"]], how="left", distance_col="gap"
    ).drop_duplicates("2gis_url")
    return {
        "listing_schools_in_city": int(len(listing)),
        "listing_numbered": int(len(numbered)),
        "our_state_catchment_schools": int(len(state)),
        "same_number_pairs": int(len(pairs)),
        "pair_distance_median_m": float(distance.median()),
        "pair_distance_p90_m": float(distance.quantile(0.9)),
        "pairs_within_150m": float((distance <= PAIR_M).mean()),
        "numbers_only_in_listing": only_listing,
        "only_in_listing_selective_or_evening": sorted(set(only_listing) & set(other["number"])),
        "only_in_listing_programme": sorted(set(only_listing) & programme_numbers),
        "only_in_listing_unexplained": sorted(
            set(only_listing) - set(other["number"]) - programme_numbers
        ),
        "numbers_only_in_ours": sorted(ours - theirs),
        "listing_schools_over_150m_from_any_school_object": int((nearest["gap"] > PAIR_M).sum()),
    }


def homes_in_buildings(homes: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame) -> pd.DataFrame:
    joined = gpd.sjoin(
        homes[["2gis_url", "floors", "under_construction", "geometry"]],
        buildings[["id", "p_residential", "label_source", "num_floors", "geometry"]],
        how="inner",
        predicate="within",
    )
    return joined.drop_duplicates("2gis_url")


def residential_check(joined: pd.DataFrame, listed: int) -> dict:
    model = joined[joined["label_source"] != "observed"]
    return {
        "listing_homes_in_city": listed,
        "inside_a_footprint": int(len(joined)),
        "classified_residential": float((joined["p_residential"] >= 0.5).mean()),
        "model_decided": int(len(model)),
        "model_recall": float((model["p_residential"] >= 0.5).mean()),
    }


def floors_check(joined: pd.DataFrame, dwellings: pd.DataFrame) -> tuple[dict, pd.Series]:
    listed = joined.dropna(subset=["floors"]).groupby("id")["floors"].median()
    tagged = joined.drop_duplicates("id").set_index("id")["num_floors"].notna()
    ours = dwellings.set_index("id")["floors"]
    common = listed.index.intersection(ours.index)
    error = ours[common] - listed[common]
    report = {}
    for label, mask in (("tagged", tagged[common]), ("imputed", ~tagged[common])):
        part = error[mask.to_numpy()]
        report[label] = {
            "buildings": int(len(part)),
            "mae_floors": float(part.abs().mean()),
            "bias_floors": float(part.mean()),
            "within_2_floors": float((part.abs() <= 2).mean()),
        }
    imputed = common[~tagged[common].to_numpy()]
    return report, listed[imputed]


def reweighted(dwellings: pd.DataFrame, listed_floors: pd.Series) -> pd.Series:
    frame = dwellings.set_index("id")
    ratio = (listed_floors / frame.loc[listed_floors.index, "floors"]).reindex(frame.index)
    before = frame["pop_station"]
    after = before * ratio.fillna(1.0)
    station = frame["station"]
    share_before = before / before.groupby(station).transform("sum")
    share_after = after / after.groupby(station).transform("sum")
    return (share_after / share_before).fillna(1.0)


def floors_sensitivity(factor: pd.Series, refloored: int) -> dict:
    points, od = load_inputs()
    supplies = supply_measures()
    scale = points["point_id"].map(lambda p: factor.get(p[1:], 1.0) if p.startswith("b") else 1.0)
    report = {
        "buildings_refloored": refloored,
        "dwellings_reweighted": int((factor - 1).abs().gt(1e-9).sum()),
    }
    for kind, base in BASE.items():
        column = f"{COHORT[kind]}_{base['variant']}"
        points[f"{column}_listing"] = points[column] * scale.to_numpy()
        results = {}
        for name in (column, f"{column}_listing"):
            demand = points.set_index("point_id")[name].fillna(0)
            access = index(
                od[kind],
                demand,
                supplies[kind][base["supply"]],
                base["decay"],
                base["d0"],
                base["d0_load"],
            )
            results[name] = (summary(points, access, name), cell_values(points, access, name))
        (old, old_cells), (new, new_cells) = results.values()
        districts = pd.Series(old["district_relative"])
        moved = pd.Series(new["district_relative"]).reindex(districts.index)
        a, b = deficit_cells(old_cells), deficit_cells(new_cells)
        report[kind] = {
            "district_relative_base": old["district_relative"],
            "district_relative_listing_floors": new["district_relative"],
            "district_rank_rho": float(spearmanr(districts, moved).correlation),
            "max_district_change": float((moved - districts).abs().max()),
            "gini_base": old["gini"],
            "gini_listing_floors": new["gini"],
            "deficit_jaccard": len(a & b) / len(a | b),
        }
    return report


def run() -> dict | None:
    if not SOURCE.exists():
        return None
    homes, schools = load()
    buildings = gpd.read_parquet(PROCESSED / "buildings.parquet")
    dwellings = gpd.read_parquet(PROCESSED / "dwellings.parquet")
    joined = homes_in_buildings(homes, buildings)
    floors, listed = floors_check(joined, dwellings)
    factor = reweighted(dwellings, listed)
    report = {
        "schools": schools_check(schools),
        "residential_classifier": residential_check(joined, len(homes)),
        "floors": floors,
        "floors_population_sensitivity": floors_sensitivity(factor, len(listed)),
        "listing_homes_by_district": homes["district"].value_counts(dropna=False).to_dict(),
        "listing_homes_under_construction": int(homes["under_construction"].sum()),
    }
    (REPORTS / "listing_check.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False, default=float))

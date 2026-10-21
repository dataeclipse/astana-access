import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import wkt

from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW, REPORTS

SOURCE = RAW / "team" / "astana_spatial_inequity.xlsx"
OUT = REPORTS / "population_by_complex.xlsx"
OVERLAP = 0.5
LOW, HIGH = 0.6, 1.4


def listing() -> gpd.GeoDataFrame:
    table = pd.read_excel(SOURCE, sheet_name=0)
    table["row"] = np.arange(len(table)) + 2
    polygons = table["geometry_polygon"].map(
        lambda text: wkt.loads(text) if isinstance(text, str) else None
    )
    frame = gpd.GeoDataFrame(table, geometry=polygons, crs=CRS_GEO)
    point = gpd.points_from_xy(table["lon"], table["lat"], crs=CRS_GEO)
    frame["geometry"] = frame.geometry.where(
        frame.geometry.notna(), gpd.GeoSeries(point, index=frame.index)
    )
    return frame.to_crs(CRS_METRIC)


def match_dwellings(frame: gpd.GeoDataFrame, dwellings: gpd.GeoDataFrame) -> pd.DataFrame:
    left = frame[["row", "geometry"]].reset_index(drop=True)
    right = dwellings[["id", "pop_station", "pop_floor", "geometry"]].rename(
        columns={"geometry": "dw"}
    )
    right = right.set_geometry("dw")
    joined = gpd.sjoin(left, right, how="inner", predicate="intersects")
    dw_geometry = dwellings.set_index("id").geometry
    inside = []
    for geometry, dw_id in zip(joined.geometry, joined["id"], strict=True):
        shape = dw_geometry.loc[dw_id]
        inside.append(geometry.intersection(shape).area / shape.area if shape.area else 0.0)
    joined["inside"] = inside
    joined = joined[joined["inside"] >= OVERLAP]
    grouped = joined.groupby("row").agg(
        dwellings_matched=("id", "nunique"),
        pop_model=("pop_station", "sum"),
        pop_floor_surface=("pop_floor", "sum"),
    )
    return grouped


def run() -> dict:
    frame = listing()
    dwellings = gpd.read_parquet(PROCESSED / "dwellings.parquet")
    blocks = dwellings[dwellings["form"] != "house"]
    per_m2 = float(blocks["pop_station"].sum() / blocks["floor_area_m2"].sum())

    table = frame.drop(columns="geometry").merge(
        match_dwellings(frame, dwellings), on="row", how="left"
    )
    table["dwellings_matched"] = table["dwellings_matched"].fillna(0).astype(int)
    table["pop_gfa"] = table["gross_floor_area_m2"] * per_m2
    matched = table["dwellings_matched"] > 0
    table["method"] = np.where(
        matched, "model: dwellings inside the footprint", "gross floor area x city mean"
    )
    table.loc[table["pop_gfa"].isna() & ~matched, "method"] = "no estimate: no footprint or area"
    central = table["pop_model"].where(matched, table["pop_gfa"])
    table["population_when_occupied"] = central.round(-1)
    done = table["under_construction"].fillna(0) == 0
    table["population_now"] = table["population_when_occupied"].where(done, 0.0)
    table["range_low"] = (table["population_now"] * LOW).round(-1)
    table["range_high"] = (table["population_now"] * HIGH).round(-1)
    first = ~table["building_id"].duplicated() | table["building_id"].isna()
    table["counted_in_totals"] = first

    columns = [
        "row",
        "name",
        "address",
        "district",
        "building_id",
        "is_new_building",
        "under_construction",
        "floors",
        "gross_floor_area_m2",
        "entrance_count",
        "dwellings_matched",
        "pop_model",
        "pop_floor_surface",
        "pop_gfa",
        "method",
        "population_when_occupied",
        "population_now",
        "range_low",
        "range_high",
        "counted_in_totals",
        "lat",
        "lon",
        "2gis_url",
    ]
    buildings = table[columns].copy()
    for name in ("pop_model", "pop_floor_surface", "pop_gfa"):
        buildings[name] = buildings[name].round(0)

    counted = buildings[buildings["counted_in_totals"]]
    complexes = (
        counted.groupby(["name", "district"], dropna=False)
        .agg(
            buildings=("row", "size"),
            floors_max=("floors", "max"),
            gross_floor_area_m2=("gross_floor_area_m2", "sum"),
            under_construction=("under_construction", "sum"),
            new_buildings=("is_new_building", "sum"),
            population_now=("population_now", "sum"),
            population_when_occupied=("population_when_occupied", "sum"),
            range_low=("range_low", "sum"),
            range_high=("range_high", "sum"),
        )
        .reset_index()
        .sort_values("population_now", ascending=False)
    )
    summary = {
        "rows": int(len(table)),
        "rows_counted": int(first.sum()),
        "complexes": int(len(complexes)),
        "matched_to_model": int(matched.sum()),
        "formula_fallback": int((~matched & table["pop_gfa"].notna()).sum()),
        "no_estimate": int((table["method"] == "no estimate: no footprint or area").sum()),
        "under_construction_rows": int((table["under_construction"] == 1).sum()),
        "people_per_gross_m2_blocks": per_m2,
        "population_now_total": float(counted["population_now"].sum()),
        "population_when_occupied_total": float(counted["population_when_occupied"].sum()),
        "model_vs_formula_median_ratio": float(
            (table.loc[matched, "pop_model"] / table.loc[matched, "pop_gfa"]).median()
        ),
    }
    notes = pd.DataFrame(
        {
            "note": [
                "Estimates, not a census: no official population exists below the district.",
                "population_now: residents of the building today; zero while under construction.",
                "population_when_occupied: the same building once finished and fully occupied.",
                "pop_model: people the population model of the project places in the dwellings inside the footprint (district totals of 1 January 2026, polling stations, floor area).",
                "pop_gfa: gross floor area times the mean people per gross square metre of blocks in the model; used only where no dwelling matches the footprint.",
                f"range: from {LOW} to {HIGH} times the estimate; the median error against school enrolment per territory is about 40 per cent.",
                "Rows sharing one building_id are the same building listed under several names; only the first counts in complex totals.",
                "New buildings may be only partly occupied; the model assumes full occupancy.",
            ]
        }
    )
    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        complexes.to_excel(writer, sheet_name="complexes", index=False)
        buildings.to_excel(writer, sheet_name="buildings", index=False)
        notes.to_excel(writer, sheet_name="notes", index=False)
    (REPORTS / "population_by_complex.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))

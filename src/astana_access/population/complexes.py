import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import wkt

from astana_access.accessibility.coverage import facilities
from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW, REPORTS

SOURCE = RAW / "team" / "astana_spatial_inequity.xlsx"
OUT = REPORTS / "population_by_complex.xlsx"
OVERLAP = 0.5
LOW, HIGH = 0.5, 2.0
NEAR_M = 300.0


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


def match_dwellings(
    frame: gpd.GeoDataFrame, dwellings: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
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
    return grouped, joined[["row", "id"]]


def school_labels() -> pd.Series:
    sites = facilities()["school"].set_index("facility_id")
    label = sites["number"].map(lambda v: f"School {int(v)}" if pd.notna(v) else None)
    return label.fillna(sites["name"].astype(str).str.slice(0, 32))


def school_links(links: pd.DataFrame) -> pd.DataFrame:
    path = PROCESSED / "flows.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["row", "facility_id", "children", "drawn"])
    flows = pd.read_parquet(path)
    demand = pd.read_parquet(
        PROCESSED / "demand_points.parquet", columns=["point_id", "school_station"]
    )
    demand = demand.set_index("point_id")["school_station"]
    state_share = float(flows["children"].sum() / demand.reindex(flows["point_id"].unique()).sum())
    linked = links.assign(point_id="b" + links["id"].astype(str)).merge(
        flows.rename(columns={"children": "drawn"}), on="point_id"
    )
    linked["children"] = linked["point_id"].map(demand) * state_share * linked["share"]
    return linked.groupby(["row", "facility_id"], as_index=False)[["children", "drawn"]].sum()


def borrowed_flows(
    frame: gpd.GeoDataFrame, unmatched: pd.DataFrame, dwellings: gpd.GeoDataFrame
) -> pd.DataFrame:
    path = PROCESSED / "flows.parquet"
    if not path.exists() or unmatched.empty:
        return pd.DataFrame(columns=["row", "facility_id", "children", "source"])
    flows = pd.read_parquet(path)
    share = flows["children"] / flows.groupby("point_id")["children"].transform("sum")
    flows = flows.assign(share=share)
    points = pd.read_parquet(
        PROCESSED / "demand_points.parquet", columns=["kind", "school_station"]
    )
    school = float(points.loc[points["kind"] == "dwelling", "school_station"].sum())
    per_person = school / float(dwellings["pop_station"].sum())
    state_share = float(flows["children"].sum()) / school
    left = frame[frame["row"].isin(unmatched["row"])][["row", "geometry"]].copy()
    left["geometry"] = left.geometry.centroid
    near = gpd.sjoin_nearest(
        left, dwellings[["id", "geometry"]], how="inner", max_distance=NEAR_M, distance_col="gap_m"
    ).drop_duplicates("row")
    near["point_id"] = "b" + near["id"].astype(str)
    near = near.merge(unmatched, on="row")
    borrowed = near[["row", "point_id", "population_now"]].merge(
        flows[["point_id", "facility_id", "share"]], on="point_id"
    )
    borrowed["children"] = borrowed["population_now"] * per_person * state_share * borrowed["share"]
    borrowed["source"] = f"nearest dwelling within {NEAR_M:.0f} m"
    return borrowed[["row", "facility_id", "children", "source"]]


def top_items(
    table: pd.DataFrame, keys: list[str], item: str, count: int, value: str = "children"
) -> pd.Series:
    table = table[table[value] > 0]
    share = table[value] / table.groupby(keys)[value].transform("sum")
    ranked = table.assign(share=share).sort_values(keys + [value], ascending=False)
    ranked = ranked[ranked.groupby(keys).cumcount() < count]
    text = (
        ranked[item].astype(str)
        + " "
        + (ranked["share"] * 100).round().astype(int).astype(str)
        + "%"
    )
    return text.groupby([ranked[k] for k in keys]).agg("; ".join)


def run() -> dict:
    frame = listing()
    dwellings = gpd.read_parquet(PROCESSED / "dwellings.parquet")
    blocks = dwellings[dwellings["form"] != "house"]
    per_m2 = float(blocks["pop_station"].sum() / blocks["floor_area_m2"].sum())

    grouped, links = match_dwellings(frame, dwellings)
    table = frame.drop(columns="geometry").merge(grouped, on="row", how="left")
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

    labels = school_labels()
    flows = school_links(links).assign(source="dwellings inside the footprint")
    unmatched = table.loc[~matched & (table["population_now"].fillna(0) > 0)]
    unmatched = unmatched[["row", "population_now"]]
    flows = pd.concat([flows, borrowed_flows(frame, unmatched, dwellings)], ignore_index=True)
    flows["school"] = flows["facility_id"].map(labels).fillna(flows["facility_id"])
    by_row = flows.groupby("row")["children"].sum().round()
    table["children_in_state_schools"] = table["row"].map(by_row)
    table["top_schools"] = table["row"].map(top_items(flows, ["row"], "school", 3))
    table["flows_source"] = table["row"].map(flows.groupby("row")["source"].first())

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
        "children_in_state_schools",
        "top_schools",
        "flows_source",
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
    city_total = float(dwellings["pop_station"].sum())
    listed_now = float(counted["population_now"].sum())
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
    complexes["share_of_city_pct"] = (complexes["population_now"] / city_total * 100).round(2)
    named = table[["row", "name", "district", "counted_in_totals"]].copy()
    named["district"] = named["district"].fillna("")
    named["name"] = named["name"].fillna("(no name)")
    in_complex = flows.merge(named[named["counted_in_totals"]], on="row")
    keys = ["name", "district"]
    complex_children = in_complex.groupby(keys)["children"].sum().round()
    complex_schools = in_complex.groupby(keys + ["facility_id", "school"], as_index=False)[
        "children"
    ].sum()
    complexes["name"] = complexes["name"].fillna("(no name)")
    complexes["district_key"] = complexes["district"].fillna("")
    index = pd.MultiIndex.from_frame(complexes[["name", "district_key"]])
    complexes["children_in_state_schools"] = complex_children.reindex(index).to_numpy()
    complexes["top_schools"] = (
        top_items(complex_schools, keys, "school", 3).reindex(index).to_numpy()
    )
    complexes = complexes.drop(columns="district_key")

    counted_rows = table.loc[table["counted_in_totals"], "row"]
    once = links[links["row"].isin(counted_rows)].drop_duplicates("id")
    once = once.assign(point_id="b" + once["id"].astype(str))
    stored = pd.read_parquet(PROCESSED / "flows.parquet")
    drawn = once.merge(stored[["point_id", "facility_id", "children"]], on="point_id")
    drawn = drawn.merge(named[["row", "name"]], on="row")
    drawn["school"] = drawn["facility_id"].map(labels).fillna(drawn["facility_id"])
    by_school = (
        drawn.groupby(["facility_id", "school"], as_index=False)["children"]
        .sum()
        .rename(columns={"children": "drawn"})
    )
    enrolment = (
        pd.read_parquet(PROCESSED / "flows.parquet").groupby("facility_id")["children"].sum()
    )
    by_school["enrolment_2025"] = by_school["facility_id"].map(enrolment).round()
    by_school["share_of_pupils_pct"] = (
        by_school["drawn"] / by_school["enrolment_2025"] * 100
    ).round(1)
    by_school["drawn"] = by_school["drawn"].round()
    from_complex = (
        drawn.groupby(["facility_id", "name"], as_index=False)["children"]
        .sum()
        .rename(columns={"children": "drawn"})
    )
    by_school["top_complexes"] = by_school["facility_id"].map(
        top_items(from_complex, ["facility_id"], "name", 5, "drawn")
    )
    school_catchments = by_school.rename(
        columns={"drawn": "pupils_from_listed_complexes"}
    ).sort_values("pupils_from_listed_complexes", ascending=False)
    summary = {
        "rows": int(len(table)),
        "rows_counted": int(first.sum()),
        "complexes": int(len(complexes)),
        "matched_to_model": int(matched.sum()),
        "formula_fallback": int((~matched & table["pop_gfa"].notna()).sum()),
        "no_estimate": int((table["method"] == "no estimate: no footprint or area").sum()),
        "under_construction_rows": int((table["under_construction"] == 1).sum()),
        "people_per_gross_m2_blocks": per_m2,
        "city_population_model": city_total,
        "listed_share_of_city": listed_now / city_total,
        "population_now_total": listed_now,
        "population_when_occupied_total": float(counted["population_when_occupied"].sum()),
        "model_vs_formula_median_ratio": float(
            (table.loc[matched, "pop_model"] / table.loc[matched, "pop_gfa"]).median()
        ),
    }
    notes = pd.DataFrame(
        {
            "note": [
                "Estimates, not a census: no official population exists below the district.",
                f"Totals cover only the buildings of the listing: {listed_now:,.0f} people, "
                f"{listed_now / city_total:.0%} of the {city_total:,.0f} that the model places in "
                "the whole city (official total of 1 January 2026: 1,638,233).",
                "The rest of the city is not in the listing: private houses, older blocks that "
                "2GIS does not file as a residential complex, dormitories and other housing.",
                "share_of_city_pct: population_now of the complex as a share of the whole city.",
                "population_now: residents of the building today; zero while under construction.",
                "population_when_occupied: the same building once finished and fully occupied.",
                "pop_model: people the population model of the project places in the dwellings "
                "inside the footprint (district totals of 1 January 2026, polling stations, "
                "floor area).",
                "pop_gfa: gross floor area times the mean people per gross square metre of blocks "
                "in the model; used only where no dwelling matches the footprint.",
                f"range_low, range_high: {LOW} and {HIGH} times the estimate. It is the spread "
                "between the population model and the area formula, which agree within this "
                "factor for about 80 per cent of buildings; it is not a measured error, because "
                "no population exists below the district to measure against. Against school "
                "enrolment the median error is about 40 per cent for a school territory of "
                "thousands of people. For a complex of several buildings the range is "
                "conservative: errors of single buildings partly cancel.",
                "Rows sharing one building_id are the same building listed under several names; "
                "only the first counts in complex totals.",
                "New buildings may be only partly occupied; the model assumes full occupancy.",
                "children_in_state_schools, top_schools: modelled flows, not observed. A "
                "doubly constrained gravity model sends the school-age children of every dwelling "
                "to the state schools so that each school receives its official enrolment of "
                "2025/26; the decay with walking distance is fitted to the official school "
                "territories. Buildings with no dwelling of the model inside the footprint "
                "(often new complexes missing from the building layer) borrow the school mix of "
                "the nearest dwelling within 300 m, see flows_source; where none is near, the "
                "flows are empty. The "
                "state schools take about 92 per cent of the children, the rest attend private "
                "schools or live outside the city.",
                "Sheet school_catchments: for each state school the children who come from the "
                "listed complexes and the five complexes that send the most.",
            ]
        }
    )
    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        complexes.to_excel(writer, sheet_name="complexes", index=False)
        buildings.to_excel(writer, sheet_name="buildings", index=False)
        school_catchments.to_excel(writer, sheet_name="school_catchments", index=False)
        notes.to_excel(writer, sheet_name="notes", index=False)
    (REPORTS / "population_by_complex.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))

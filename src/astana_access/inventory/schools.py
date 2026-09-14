import re

import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW, ROOT
from astana_access.inventory.link import load_osm_schools, merge_osm_duplicates
from astana_access.inventory.names import parse

LINKAGE = PROCESSED / "linkage"
GOLD = ROOT / "data" / "labels" / "linkage_gold.csv"

TERRITORY_RADIUS_M = 50.0
BUILDING_NAME_RADIUS_M = 30.0
ORPHAN_BUILDING_RADIUS_M = 150.0

IN_SCOPE_KINDS = {
    "general",
    "gymnasium",
    "lyceum",
    "nis",
    "rfmsh",
    "international",
    "special",
    "complex_kg",
}
OUT_OF_SCOPE = re.compile(
    r"карат|балет|спортив|sport|языков\w* центр|центр немецк|step by step|бэби|"
    r"академия наук|дошкольн|колледж|"
    r"учебно-воспитательн|центр развития|школа развития|virere|медицин",
    re.I,
)
STATE = re.compile(
    r"государствен|государтвен|\bкгу\b|\bгу\b|коммунальн|управлени\w* образования|акимат", re.I
)
AUTONOMOUS = re.compile(r"назарбаев|физико-математ|физика-математика|республиканск", re.I)
PRIVATE = re.compile(
    r"товарищество|\bтоо\b|частн|некоммерческ|филиал оф|фонд|акционерн|"
    r"international|school|schule|academy|"
    r"международн|^\W*учреждение\b|qazbilim|nurorda",
    re.I,
)


SELECTIVE_KINDS = {"nis", "rfmsh", "international", "special"}
SELECTIVE = re.compile(
    r"одаренн|одарённ|дарын|зерде|специализированн|интернат|назарбаев|республиканск", re.I
)
ADDRESS_LINK_RADIUS_M = 60.0
ADDRESSES = ROOT / "data" / "labels" / "registry_addresses.csv"


def link_by_address(
    inventory: gpd.GeoDataFrame, registry: pd.DataFrame, linked: set[int]
) -> tuple[gpd.GeoDataFrame, set[int]]:
    from astana_access.ingest.geocode import geocode_address

    table = pd.read_csv(ADDRESSES, dtype=str)
    inv_m = inventory.to_crs(CRS_METRIC)
    additions = []
    for _, row in table.iterrows():
        hits = registry.index[registry["name"].str.startswith(row["registry_name_prefix"][:70])]
        if len(hits) != 1 or int(hits[0]) in linked:
            continue
        reg_idx = int(hits[0])
        located = geocode_address(row["street"], row["housenumber"])
        if located is None:
            continue
        point = (
            gpd.GeoSeries(gpd.points_from_xy([located["lon"]], [located["lat"]]), crs=CRS_GEO)
            .to_crs(CRS_METRIC)
            .iloc[0]
        )
        free = inv_m[inventory["registry_idx"].isna()]
        distances = free.distance(point)
        if len(distances) and distances.min() <= ADDRESS_LINK_RADIUS_M:
            k = distances.idxmin()
            inventory.at[k, "registry_idx"] = reg_idx
            inventory.at[k, "link_method"] = "address"
        else:
            additions.append(
                {
                    "label": registry.at[reg_idx, "name"],
                    "osm_number": registry.at[reg_idx, "reg_number"],
                    "osm_kind": registry.at[reg_idx, "reg_kind"],
                    "osm_ref": None,
                    "source": "registry_geocoded",
                    "under_construction": False,
                    "registry_idx": reg_idx,
                    "link_method": "address_geocoded",
                    "link_score": np.nan,
                    "geometry": gpd.points_from_xy([located["lon"]], [located["lat"]])[0],
                }
            )
        linked.add(reg_idx)
    if additions:
        extra = gpd.GeoDataFrame(additions, geometry="geometry", crs=CRS_GEO)
        inventory = gpd.GeoDataFrame(
            pd.concat([inventory, extra], ignore_index=True), geometry="geometry", crs=CRS_GEO
        )
    return inventory, linked


def ownership_from_name(text: str, number: float | None) -> str:
    value = str(text or "")
    if AUTONOMOUS.search(value):
        return "autonomous"
    if STATE.search(value):
        return "state"
    if PRIVATE.search(value):
        return "private"
    if number is not None and not pd.isna(number):
        return "state"
    return "unknown"


def _points(frame: pd.DataFrame) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        frame, geometry=gpd.points_from_xy(frame["lon"], frame["lat"]), crs=CRS_GEO
    )


def facility_layer() -> gpd.GeoDataFrame:
    osm = merge_osm_duplicates(load_osm_schools()).reset_index(drop=True)
    osm["label"] = osm["name_ru"].fillna(osm["name"])
    metric = osm.to_crs(CRS_METRIC)
    points = metric.geometry.centroid
    named = osm["label"].notna()
    drop = []
    for i in osm.index[~named]:
        distances = points[named].distance(points[i])
        if len(distances) and distances.min() <= TERRITORY_RADIUS_M:
            drop.append(i)
    osm = osm.drop(index=drop).reset_index(drop=True)
    osm["source"] = "osm_facility"
    osm["osm_ref"] = osm["osm_type"] + "/" + osm["osm_id"].astype(str)
    return osm


def building_layer() -> gpd.GeoDataFrame:
    buildings = gpd.read_file(RAW / "osm" / "buildings.gpkg")
    mask = (buildings["building"] == "school") | buildings["name"].fillna("").str.contains(
        r"школ|мектеп|лицей|гимназ|school", case=False
    )
    return buildings[mask].reset_index(drop=True)


def enrich_names(facilities: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = facilities.copy()
    fac_m = out.to_crs(CRS_METRIC)
    bld_m = buildings.to_crs(CRS_METRIC)
    named_bld = bld_m[bld_m["name"].notna()]
    for i in out.index[out["label"].isna()]:
        if named_bld.empty:
            break
        distances = named_bld.distance(fac_m.geometry.iloc[i].centroid)
        j = distances.idxmin()
        if distances[j] <= BUILDING_NAME_RADIUS_M:
            out.at[i, "label"] = named_bld.at[j, "name"]
            out.at[i, "source"] = "osm_facility+building_name"
    parsed = [parse(v) for v in out["label"]]
    out["osm_number"] = [
        p.number if p.number is not None else n
        for p, n in zip(parsed, out["osm_number"], strict=True)
    ]
    out["osm_kind"] = [p.kind if p.raw else k for p, k in zip(parsed, out["osm_kind"], strict=True)]
    return out


def orphan_buildings(facilities: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    fac_m = facilities.to_crs(CRS_METRIC).geometry.centroid
    bld = buildings.copy()
    bld_m = bld.to_crs(CRS_METRIC)
    bld["distance"] = [fac_m.distance(c).min() for c in bld_m.geometry.centroid]
    orphans = bld[(bld["distance"] > ORPHAN_BUILDING_RADIUS_M) & bld["name"].notna()].copy()
    parsed = [parse(v) for v in orphans["name"]]
    orphans["label"] = orphans["name"]
    orphans["osm_number"] = [p.number for p in parsed]
    orphans["osm_kind"] = [p.kind for p in parsed]
    orphans["osm_ref"] = "way/" + orphans["osm_id"].astype(str)
    orphans["source"] = "osm_building"
    orphans["under_construction"] = orphans["building"] == "construction"
    orphans["geometry"] = (
        orphans.geometry.centroid
        if orphans.crs.is_geographic is False
        else orphans.to_crs(CRS_METRIC).geometry.centroid.to_crs(CRS_GEO)
    )
    return gpd.GeoDataFrame(orphans, geometry="geometry", crs=CRS_GEO)


def final_links(facility_osm_index: pd.Series) -> pd.DataFrame:
    matches = pd.read_parquet(LINKAGE / "matches_v2.parquet")
    matches["method"] = "automatic_v2"
    gold = pd.read_csv(GOLD, dtype={"gold_osm_idx": str}, keep_default_na=False)
    auto = set(matches["reg_idx"].astype(int))
    extra = gold[(gold["gold_osm_idx"] != "") & (gold["gold_osm_idx"] != "AMBIGUOUS")]
    extra = extra[~extra["reg_idx"].isin(auto)]
    manual = pd.DataFrame(
        {
            "reg_idx": extra["reg_idx"].astype(int),
            "osm_idx": extra["gold_osm_idx"].astype(int),
            "score": np.nan,
            "method": "manual_review",
        }
    )
    links = pd.concat([matches, manual], ignore_index=True)
    links["osm_ref"] = links["osm_idx"].map(facility_osm_index)
    return links


def build() -> gpd.GeoDataFrame:
    registry = pd.read_parquet(LINKAGE / "registry.parquet")
    dedup = _points(pd.read_parquet(LINKAGE / "osm_schools.parquet"))
    dedup_ref = dedup["osm_type"] + "/" + dedup["osm_id"].astype(str)

    buildings = building_layer()
    facilities = enrich_names(facility_layer(), buildings)
    orphans = orphan_buildings(facilities, buildings)

    columns = ["label", "osm_number", "osm_kind", "osm_ref", "source", "geometry"]
    facilities["under_construction"] = False
    inventory = pd.concat(
        [facilities[columns + ["under_construction"]], orphans[columns + ["under_construction"]]],
        ignore_index=True,
    )
    inventory = gpd.GeoDataFrame(inventory, geometry="geometry", crs=CRS_GEO)
    inventory["geometry"] = inventory.to_crs(CRS_METRIC).geometry.centroid.to_crs(CRS_GEO)

    links = final_links(dedup_ref)
    by_ref = links.set_index("osm_ref")
    inventory["registry_idx"] = inventory["osm_ref"].map(by_ref["reg_idx"])
    inventory["link_method"] = inventory["osm_ref"].map(by_ref["method"])
    inventory["link_score"] = inventory["osm_ref"].map(by_ref["score"])

    linked = set(inventory["registry_idx"].dropna().astype(int))
    for i, row in registry.iterrows():
        if i in linked or pd.isna(row["reg_number"]):
            continue
        candidates = inventory[
            (inventory["source"] == "osm_building")
            & (inventory["osm_number"] == row["reg_number"])
            & inventory["registry_idx"].isna()
        ]
        if len(candidates) == 1:
            k = candidates.index[0]
            inventory.at[k, "registry_idx"] = i
            inventory.at[k, "link_method"] = "building_number"
            linked.add(i)

    inventory, linked = link_by_address(inventory, registry, linked)

    reg = registry.add_prefix("registry_")
    inventory = inventory.merge(reg, left_on="registry_idx", right_index=True, how="left")
    inventory["name"] = inventory["registry_name"].fillna(inventory["label"])
    inventory["number"] = inventory["registry_reg_number"].fillna(inventory["osm_number"])
    inventory["kind"] = inventory["registry_reg_kind"].fillna(inventory["osm_kind"])
    inventory["ownership"] = [
        ownership_from_name(n, num)
        for n, num in zip(inventory["name"], inventory["number"], strict=True)
    ]
    text = inventory["name"].fillna("")
    inventory["in_scope"] = (
        inventory["kind"].isin(IN_SCOPE_KINDS)
        & ~text.str.contains(OUT_OF_SCOPE)
        & inventory["name"].notna()
    )
    inventory["catchment_based"] = (
        inventory["in_scope"]
        & (inventory["ownership"] == "state")
        & ~inventory["kind"].isin(SELECTIVE_KINDS)
        & ~text.str.contains(SELECTIVE)
    )

    districts = gpd.read_file(PROCESSED / "districts.gpkg", layer="districts")
    joined = gpd.sjoin(
        inventory, districts[["name_en", "geometry"]], how="left", predicate="within"
    )
    inventory["district"] = joined[~joined.index.duplicated(keep="first")]["name_en"].to_numpy()
    inventory = inventory.reset_index(drop=True)
    inventory["facility_id"] = [f"sch{i:04d}" for i in range(len(inventory))]

    unmatched_registry = registry.loc[~registry.index.isin(linked)].copy()
    unmatched_registry["ownership"] = [
        ownership_from_name(n, num)
        for n, num in zip(unmatched_registry["name"], unmatched_registry["reg_number"], strict=True)
    ]

    keep = [
        "facility_id",
        "name",
        "number",
        "kind",
        "ownership",
        "in_scope",
        "catchment_based",
        "under_construction",
        "district",
        "source",
        "osm_ref",
        "registry_idx",
        "registry_id",
        "registry_area",
        "link_method",
        "link_score",
        "geometry",
    ]
    result = inventory[keep]
    result.to_file(PROCESSED / "facilities.gpkg", layer="schools", driver="GPKG")
    unmatched_registry.to_parquet(LINKAGE / "registry_unlocated.parquet", index=False)
    return result

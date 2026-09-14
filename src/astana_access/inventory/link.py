from dataclasses import asdict

import geopandas as gpd
import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from astana_access.config import CRS_METRIC, PROCESSED, RAW
from astana_access.inventory.names import ParsedName, kinds_compatible, parse

REGISTRY_DISTRICTS = {
    "район «Есиль»": {"Esil", "Nura"},
    "район «Алматы»": {"Almaty", "Saraishyk"},
    "район «Сарыарка»": {"Saryarka"},
    "район 'Байқоңыр'": {"Baikonur"},
}

MERGE_RADIUS_M = 300.0
ACCEPT_SCORE = 0.60
NAME_OVERRIDE = 0.55


def load_registry() -> pd.DataFrame:
    frame = pd.read_parquet(RAW / "egov" / "schools_astana.parquet").reset_index(drop=True)
    parsed = [parse(n, k) for n, k in zip(frame["name"], frame["name_kz"], strict=True)]
    return _attach(frame, parsed, "reg")


def load_osm_schools() -> gpd.GeoDataFrame:
    facilities = gpd.read_file(RAW / "osm" / "facilities.gpkg")
    schools = facilities[facilities["category"] == "school"].reset_index(drop=True)
    parsed = [
        parse(a, b, c)
        for a, b, c in zip(schools["name"], schools["name_ru"], schools["name_kk"], strict=True)
    ]
    schools = _attach(schools, parsed, "osm")
    districts = gpd.read_file(PROCESSED / "districts.gpkg", layer="districts")
    joined = gpd.sjoin(schools, districts[["name_en", "geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    schools["district"] = joined["name_en"].to_numpy()
    return schools


def _attach(frame: pd.DataFrame, parsed: list[ParsedName], prefix: str) -> pd.DataFrame:
    out = frame.copy()
    out[f"{prefix}_number"] = [p.number for p in parsed]
    out[f"{prefix}_kind"] = [p.kind for p in parsed]
    out[f"{prefix}_tokens"] = [" ".join(p.tokens) for p in parsed]
    out[f"{prefix}_latin"] = [p.latin for p in parsed]
    out[f"{prefix}_label"] = [p.raw for p in parsed]
    return out


def merge_osm_duplicates(schools: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    metric = schools.to_crs(CRS_METRIC)
    xy = np.column_stack([metric.geometry.centroid.x, metric.geometry.centroid.y])
    group = np.arange(len(schools))
    for i in range(len(schools)):
        for j in range(i + 1, len(schools)):
            ni, nj = schools.at[i, "osm_number"], schools.at[j, "osm_number"]
            if pd.isna(ni) or ni != nj:
                continue
            if not kinds_compatible(schools.at[i, "osm_kind"], schools.at[j, "osm_kind"]):
                continue
            if np.hypot(*(xy[i] - xy[j])) <= MERGE_RADIUS_M:
                group[group == group[j]] = group[i]
    schools = schools.copy()
    schools["facility_group"] = group
    schools["members"] = schools.groupby("facility_group")["osm_id"].transform("count")
    order = schools.assign(
        _named=schools["name_ru"].notna().astype(int),
        _way=(schools["osm_type"] != "node").astype(int),
    ).sort_values(["facility_group", "_named", "_way"], ascending=[True, False, False])
    return (
        order.drop_duplicates("facility_group")
        .drop(columns=["_named", "_way"])
        .reset_index(drop=True)
    )


def pair_score(reg: pd.Series, osm: pd.Series) -> dict[str, float]:
    rn, on = reg["reg_number"], osm["osm_number"]
    number_known = not pd.isna(rn) and not pd.isna(on)
    if number_known and rn != on:
        return {"score": 0.0, "number": 0.0, "kind": 0.0, "name": 0.0, "district": 0.0}
    kind_ok = kinds_compatible(reg["reg_kind"], osm["osm_kind"])
    kind = 1.0 if reg["reg_kind"] == osm["osm_kind"] else (0.6 if kind_ok else 0.0)
    name = name_similarity(reg["reg_tokens"], osm["osm_tokens"], reg["reg_latin"], osm["osm_latin"])
    allowed = REGISTRY_DISTRICTS.get(reg["area"], set())
    district = 1.0 if osm.get("district") in allowed else 0.0
    if number_known:
        score = 0.55 + 0.20 * kind + 0.15 * name + 0.10 * district
    elif pd.isna(rn) and pd.isna(on):
        score = 0.15 * kind + 0.70 * name + 0.15 * district
    else:
        score = 0.10 * kind + 0.45 * name + 0.10 * district
    if not kind_ok and name < NAME_OVERRIDE:
        score *= 0.5
    return {
        "score": score,
        "number": float(number_known),
        "kind": kind,
        "name": name,
        "district": district,
    }


def name_similarity(tokens_a: str, tokens_b: str, latin_a: str, latin_b: str) -> float:
    if not tokens_a and not tokens_b:
        return 0.5
    if not tokens_a or not tokens_b:
        return 0.0
    best = 0.0
    for a, b in ((tokens_a, tokens_b), (latin_a, latin_b)):
        blended = 0.5 * fuzz.token_set_ratio(a, b) + 0.5 * fuzz.token_sort_ratio(a, b)
        best = max(best, blended / 100.0)
    return best


def score_matrix(registry: pd.DataFrame, osm: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    matrix = np.zeros((len(registry), len(osm)))
    rows = []
    for i, reg in registry.iterrows():
        for j, candidate in osm.iterrows():
            parts = pair_score(reg, candidate)
            matrix[i, j] = parts["score"]
            if parts["score"] > 0.2:
                rows.append({"reg_idx": i, "osm_idx": j, **parts})
    return matrix, pd.DataFrame(rows)


def assign(matrix: np.ndarray, threshold: float = ACCEPT_SCORE) -> pd.DataFrame:
    rows, cols = linear_sum_assignment(-matrix)
    pairs = [
        {"reg_idx": int(r), "osm_idx": int(c), "score": float(matrix[r, c])}
        for r, c in zip(rows, cols, strict=True)
        if matrix[r, c] >= threshold
    ]
    return pd.DataFrame(pairs)


def run() -> dict[str, pd.DataFrame]:
    registry = load_registry()
    osm = merge_osm_duplicates(load_osm_schools())
    matrix, candidates = score_matrix(registry, osm)
    matches = assign(matrix)
    target = PROCESSED / "linkage"
    target.mkdir(parents=True, exist_ok=True)
    registry.to_parquet(target / "registry.parquet", index=False)
    osm.drop(columns="geometry").assign(
        lon=osm.geometry.centroid.x, lat=osm.geometry.centroid.y
    ).to_parquet(target / "osm_schools.parquet", index=False)
    candidates.to_parquet(target / "candidates.parquet", index=False)
    matches.to_parquet(target / "matches.parquet", index=False)
    np.save(target / "score_matrix.npy", matrix)
    return {"registry": registry, "osm": osm, "candidates": candidates, "matches": matches}


def describe(parsed: ParsedName) -> dict[str, object]:
    return asdict(parsed)

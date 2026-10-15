import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from shapely.geometry import Point

from astana_access.accessibility.coverage import VARIANTS, facilities
from astana_access.accessibility.e2sfca import DECAY, load_inputs, supply_measures
from astana_access.accessibility.official_catchments import allocated_load
from astana_access.config import CRS_GEO, CRS_METRIC, INTERIM, PROCESSED, RAW, REPORTS
from astana_access.equity.analysis import BASE
from astana_access.ingest import school_register
from astana_access.ingest.stat_ages import cohort_shares, pooled_shares
from astana_access.inventory.addresses import district_hint, load_gazetteer, split_address
from astana_access.population.model import AGE_YEAR
from astana_access.validation.listing import school_number

LISTING = RAW / "team" / "astana_spatial_inequity.xlsx"
FAR_M = 400.0
CONFIRM_M = 150.0
TWO_SHIFTS = 2.0
HINT_WORD = {
    "Almaty": "Алматы",
    "Esil": "Есиль",
    "Nura": "Нура",
    "Saryarka": "Сарыарка",
    "Baikonur": "Байконур",
    "Saraishyk": "Сарайшык",
}


def address_check(register: pd.DataFrame, schools: gpd.GeoDataFrame) -> dict:
    gazetteer = load_gazetteer()
    position = schools.set_index("facility_id").geometry
    rows = []
    for row in register.itertuples():
        street, house = split_address(row.address)
        hint = district_hint(f"район {HINT_WORD.get(row.district, '')}")
        found = gazetteer.locate(street, house, hint)
        if found.lon is None or row.facility_id not in position.index:
            continue
        point = gpd.GeoSeries([Point(found.lon, found.lat)], crs=CRS_GEO).to_crs(CRS_METRIC)
        rows.append(
            {
                "facility_id": row.facility_id,
                "number": row.number,
                "distance_m": float(point.iloc[0].distance(position[row.facility_id])),
            }
        )
    table = pd.DataFrame(rows)
    far = table[table["distance_m"] > FAR_M].copy()
    confirmed = []
    if LISTING.exists() and len(far):
        listing = pd.read_excel(LISTING, sheet_name="astana_schools")
        listing["number"] = listing["name"].map(school_number)
        listing = gpd.GeoDataFrame(
            listing, geometry=gpd.points_from_xy(listing["lon"], listing["lat"]), crs=CRS_GEO
        ).to_crs(CRS_METRIC)
        for row in far.itertuples():
            same = listing[listing["number"] == row.number]
            gap = same.distance(position[row.facility_id]).min() if len(same) else np.inf
            if gap <= CONFIRM_M:
                confirmed.append(int(row.number))
    return {
        "geocoded": int(len(table)),
        "median_distance_m": float(table["distance_m"].median()),
        "within_100m_share": float((table["distance_m"] <= 100).mean()),
        "farther_than_400m": far.sort_values("distance_m")[["number", "distance_m"]]
        .round()
        .to_dict("records"),
        "far_but_confirmed_by_listing": confirmed,
    }


def crowding(register: pd.DataFrame) -> dict:
    frame = register.copy()
    frame["ratio"] = frame["enrolment_2025"] / frame["capacity"]
    frame["beyond_two_shifts"] = (frame["enrolment_2025"] - TWO_SHIFTS * frame["capacity"]).clip(
        lower=0
    )
    district = frame.groupby("district").agg(
        schools=("capacity", "size"),
        capacity=("capacity", "sum"),
        enrolment_2025=("enrolment_2025", "sum"),
        enrolment_2026=("enrolment_2026", "sum"),
        beyond_two_shifts=("beyond_two_shifts", "sum"),
    )
    district["pupils_per_place"] = district["enrolment_2025"] / district["capacity"]
    district["growth_2026"] = district["enrolment_2026"] / district["enrolment_2025"] - 1
    over = frame[frame["ratio"] > TWO_SHIFTS]
    district["share_in_schools_beyond_two_shifts"] = (
        over.groupby("district")["enrolment_2025"].sum() / district["enrolment_2025"]
    ).fillna(0.0)
    return {
        "schools": int(len(frame)),
        "capacity": float(frame["capacity"].sum()),
        "enrolment_2025": float(frame["enrolment_2025"].sum()),
        "enrolment_2026": float(frame["enrolment_2026"].sum()),
        "pupils_per_place": float(frame["enrolment_2025"].sum() / frame["capacity"].sum()),
        "shifts": frame["shifts"].value_counts().to_dict(),
        "schools_beyond_two_shifts": int(len(over)),
        "pupils_in_schools_beyond_two_shifts_share": float(
            over["enrolment_2025"].sum() / frame["enrolment_2025"].sum()
        ),
        "pupils_beyond_two_shifts": float(frame["beyond_two_shifts"].sum()),
        "by_district": district.round(3).to_dict("index"),
    }


def official_split_demand(points: pd.DataFrame, demand: pd.Series, cohort: str) -> pd.Series:
    official = cohort_shares(AGE_YEAR)[cohort]
    model = pooled_shares(AGE_YEAR)[cohort]
    district = points.set_index("point_id")["district"].reindex(demand.index)
    factor = district.map((official / model).to_dict()).fillna(1.0)
    return demand * factor


def load_check(register: pd.DataFrame) -> dict:
    points, od = load_inputs()
    base = BASE["school"]
    demand = points.set_index("point_id")[f"school_{base['variant']}"].fillna(0)
    enrolled = register.groupby("facility_id")["enrolment_2025"].sum()
    enrolled = enrolled[enrolled > 0]
    district = register.groupby("facility_id")["district"].first()
    result = {}
    for name, values in (
        ("combined_almaty_saraishyk", demand),
        ("official_split", official_split_demand(points, demand, "school")),
    ):
        load = allocated_load(od["school"], values, base)
        pair = pd.concat([enrolled, load], axis=1, keys=["enrolled", "model"]).dropna()
        by_district = pair.groupby(district.reindex(pair.index)).sum()
        error = (by_district["model"] / by_district["enrolled"] - 1).round(3)
        result[name] = {
            "schools": int(len(pair)),
            "spearman": float(spearmanr(pair["enrolled"], pair["model"]).correlation),
            "district_model_over_enrolled": error.to_dict(),
            "district_mean_abs_error": float(error.abs().mean()),
        }
    counted = od["school"][od["school"]["distance_m"] <= base["d0"]]
    weight = DECAY[base["decay"]](counted["distance_m"].to_numpy(dtype=float), base["d0"])
    original = (
        (counted["point_id"].map(demand).fillna(0.0) * weight).groupby(counted["facility_id"]).sum()
    )
    pair = pd.concat([enrolled, original], axis=1, keys=["enrolled", "model"]).dropna()
    result["original_first_step_spearman"] = float(
        spearmanr(pair["enrolled"], pair["model"]).correlation
    )
    return result


def proxy_check(register: pd.DataFrame) -> dict:
    supply = supply_measures()["school"]["floor_area"]
    table = register.set_index("facility_id")[["capacity", "enrolment_2025"]].join(
        supply.rename("floor")
    )
    table = table.dropna()
    return {
        "schools": int(len(table)),
        "spearman_floor_capacity": float(spearmanr(table["floor"], table["capacity"]).correlation),
        "spearman_floor_enrolment": float(
            spearmanr(table["floor"], table["enrolment_2025"]).correlation
        ),
        "spearman_capacity_enrolment": float(
            spearmanr(table["capacity"], table["enrolment_2025"]).correlation
        ),
    }


def territory_check(register: pd.DataFrame) -> dict:
    path = INTERIM / "catchment_dwellings.csv"
    if not path.exists():
        return {}
    pairs = pd.read_csv(path)
    points = pd.read_parquet(PROCESSED / "demand_points.parquet").set_index("point_id")
    enrolled = register.groupby("facility_id")["enrolment_2025"].sum()
    enrolled = enrolled[enrolled > 0]
    result = {}
    for variant in VARIANTS:
        column = f"school_{variant}"
        children = pairs["point_id"].map(points[column]).fillna(0.0) * pairs["share"]
        inside = children.groupby(pairs["facility_id"]).sum()
        pair = pd.concat([enrolled, inside], axis=1, keys=["enrolled", "model"]).dropna()
        pair = pair[pair["model"] > 0]
        result[variant] = {
            "schools": int(len(pair)),
            "spearman": float(spearmanr(pair["enrolled"], pair["model"]).correlation),
        }
    return result


def run() -> dict | None:
    if not school_register.SOURCE.exists():
        return None
    register = school_register.build()
    schools = facilities()["school"]
    linked = register.dropna(subset=["facility_id"])
    state = register[register["section"] == "state"]
    comfortable = register[register["comfortable"].astype(bool)]
    report = {
        "rows": {
            "state": int(len(state)),
            "private": int((register["section"] == "private").sum()),
        },
        "linked": {
            "state": int(state["facility_id"].notna().sum()),
            "binom": int(register["binom"].notna().sum()),
            "unlinked_state": state.loc[state["facility_id"].isna(), "name"].tolist(),
            "supply_without_register_row": sorted(
                set(schools["facility_id"]) - set(linked["facility_id"])
            ),
        },
        "comfortable_school": {
            "listed": int(len(comfortable)),
            "numbers": sorted(comfortable["number"].dropna().astype(int).tolist()),
            "capacity": float(comfortable["capacity"].sum()),
            "opened": comfortable["last_year"].value_counts().sort_index().to_dict(),
            "enrolment_2025": float(comfortable["enrolment_2025"].sum()),
        },
        "private_schools": {
            "capacity": float(register.loc[register["section"] == "private", "capacity"].sum()),
            "enrolment_2025": float(
                register.loc[register["section"] == "private", "enrolment_2025"].sum()
            ),
        },
        "address_check": address_check(linked, schools),
        "crowding": crowding(linked),
        "proxy_check": proxy_check(linked),
        "load_check": load_check(linked),
        "territory_check": territory_check(linked),
    }
    (REPORTS / "school_register_check.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False, default=float))

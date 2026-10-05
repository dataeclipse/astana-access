import json

import geopandas as gpd
import pandas as pd

from astana_access.config import PROCESSED, RAW, REPORTS
from astana_access.ingest.stat_ages import cohort_shares, load

SOURCE = RAW / "stat" / "astana"
DISTRICTS = {
    "г. Астана": "City",
    "город Астана": "City",
    "район Алматы": "Almaty",
    "район Есиль": "Esil",
    "район Сарыарка": "Saryarka",
    "район Байқоңыр": "Baikonur",
    "район Нұра": "Nura",
    "район Сарайшық": "Saraishyk",
}


def year_of(label) -> int | None:
    text = str(label).split("/")[0].split(".")[0]
    digits = "".join(ch for ch in text if ch.isdigit())[:4]
    return int(digits) if len(digits) == 4 else None


def series(name: str, sheet=0, block: int = 0) -> pd.DataFrame:
    frame = pd.read_excel(SOURCE / f"{name}.xlsx", sheet_name=sheet, header=None)
    header = next(i for i, row in frame.iterrows() if sum(year_of(v) is not None for v in row) > 5)
    years = {col: year_of(v) for col, v in frame.loc[header].items() if year_of(v) is not None}
    rows = []
    seen: dict[str, int] = {}
    for _, row in frame.loc[header + 1 :].iterrows():
        label = next((str(v).strip() for v in row if isinstance(v, str) and v.strip()), "")
        district = DISTRICTS.get(label)
        if district is None:
            continue
        seen[district] = seen.get(district, 0) + 1
        if seen[district] != block + 1:
            continue
        values = [v for v in row.tolist() if pd.notna(v)][1:]
        cols = sorted(years)[-len(values) :] if values else []
        for col, value in zip(cols, values, strict=True):
            number = pd.to_numeric(str(value).replace(",", "."), errors="coerce")
            if pd.notna(number):
                rows.append((district, years[col], float(number)))
    return pd.DataFrame(rows, columns=["district", "year", "value"])


def latest(frame: pd.DataFrame, district: str = "City") -> tuple[int, float]:
    part = frame[frame["district"] == district].sort_values("year")
    return int(part["year"].iloc[-1]), float(part["value"].iloc[-1])


def run() -> dict | None:
    if not SOURCE.exists():
        return None
    ages = cohort_shares(2026, load())
    official_children = load()
    totals = official_children[
        (official_children["year"] == 2026) & (official_children["age"] == "Всего")
    ].set_index("district")["people"]
    school_age = float(ages.at["City", "school"] * totals["City"])
    preschool_age = float(ages.at["City", "preschool"] * totals["City"])
    schools_year, schools = latest(series("schools"))
    pupils_year, pupils = latest(series("school_pupils"))
    places_year, places = latest(series("preschool_places"))
    children_year, children = latest(series("preschool_children"))
    orgs_year, orgs = latest(series("preschool_orgs"))
    state = latest(series("preschool_orgs_ownership", block=0))[1]
    private = latest(series("preschool_orgs_ownership", block=1))[1]
    births = series("births", sheet="2009-2025")
    births = births[births["year"] >= 2019].pivot(index="year", columns="district", values="value")
    register = gpd.read_file(PROCESSED / "facilities.gpkg", layer="preschools")
    every = gpd.read_file(PROCESSED / "facilities.gpkg", layer="schools")
    report = {
        "schools": {
            "official_year": schools_year,
            "official_all_types": schools,
            "inventory_state_catchment": int(every["catchment_based"].sum()),
        },
        "pupils": {
            "official_year": pupils_year,
            "official_day_schools": pupils,
            "official_children_7_17_on_1_january_2026": school_age,
            "pupils_over_children": pupils / school_age,
        },
        "preschools": {
            "official_year": orgs_year,
            "official_organisations": orgs,
            "official_state": state,
            "official_private": private,
            "register_organisations": int(len(register)),
            "official_places": places,
            "official_children": children,
            "children_per_100_places": 100 * children / places,
            "official_children_1_6": preschool_age,
            "attendance_over_children_1_6": children / preschool_age,
            "places_year": places_year,
            "children_year": children_year,
        },
        "births": births.round(0).to_dict(),
    }
    (REPORTS / "official_checks.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False, default=float))

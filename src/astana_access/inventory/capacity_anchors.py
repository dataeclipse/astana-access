import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.config import DATA, PROCESSED, RAW

VERIFIED = {
    "capacity": {
        13: 392,
        35: 1500,
        40: 850,
        42: 450,
        44: 1240,
        69: 1200,
        71: 1200,
        77: 1200,
        79: 1200,
        83: 1200,
    },
    "total_area_m2": {71: 16112.0, 79: 14663.7, 83: 16296.2},
    "enrolment": {32: 3091, 34: 465, 35: 1989, 42: 462, 65: 3028, 69: 3129, 71: 5334, 79: 670},
    "shifts": {65: 2, 69: 2, 71: 2, 77: 2, 79: 2},
}
MANUAL = [
    (65, "capacity", 1200, "Мектептің сыйымдылығы - 1200 оқушы"),
    (77, "enrolment", 1650, "Қазіргі таңда 1650 оқушы білім алу үстінде"),
    (83, "enrolment", 3555, "Количество учащихся: 3555"),
]
TRUSTED_FLOOR = ("territory", "school_buildings")


def _snippet_source(raw: pd.DataFrame, number: int, needle: str) -> tuple[str, str]:
    rows = raw[(raw["number"] == number) & raw["snippet"].str.contains(needle, regex=False)]
    if rows.empty:
        return "", ""
    return rows.iloc[0]["url"], rows.iloc[0]["snippet"]


def build() -> pd.DataFrame:
    raw = pd.read_csv(RAW / "school_sites" / "extracted_raw.csv")
    records = []
    for field, values in VERIFIED.items():
        for number, value in values.items():
            rows = raw[
                (raw["number"] == number) & (raw["field"] == field) & (raw["value"] == value)
            ]
            if rows.empty:
                raise ValueError(f"no evidence for school {number} {field} {value}")
            row = rows.iloc[0]
            records.append(
                {
                    "number": number,
                    "field": field,
                    "value": value,
                    "year": row["year"],
                    "url": row["url"],
                    "evidence": row["snippet"],
                }
            )
    for number, field, value, needle in MANUAL:
        url, snippet = _snippet_source(raw, number, needle)
        if not url:
            raise ValueError(f"no evidence for school {number} {field} {value}")
        records.append(
            {
                "number": number,
                "field": field,
                "value": value,
                "year": np.nan,
                "url": url,
                "evidence": snippet,
            }
        )
    anchors = pd.DataFrame(records).sort_values(["field", "number"])
    target = DATA / "labels"
    target.mkdir(parents=True, exist_ok=True)
    anchors.to_csv(target / "school_site_facts.csv", index=False, encoding="utf-8-sig")
    return anchors


def compare(anchors: pd.DataFrame) -> pd.DataFrame:
    schools = gpd.read_file(PROCESSED / "facilities.gpkg", layer="schools")
    schools = schools[schools["catchment_based"] & schools["number"].notna()]
    wide = anchors.pivot_table(index="number", columns="field", values="value", aggfunc="first")
    table = schools.set_index("number")[["floor_m2", "floor_source"]].join(wide, how="inner")
    table["m2_per_place"] = table["floor_m2"] / table["capacity"]
    table["area_error"] = table["floor_m2"] / table["total_area_m2"] - 1
    table["load"] = table["enrolment"] / table["capacity"]
    table["trusted_floor"] = table["floor_source"].isin(TRUSTED_FLOOR)
    return table.sort_index()

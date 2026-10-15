import re

import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.config import INTERIM, PROCESSED, RAW

SOURCE = RAW / "official_reply_3" / "schools.xlsx"
TABLE = INTERIM / "school_register.csv"
HEADER_ROW = 1
PRIVATE_MARK = "Частные школы"
COLUMNS = {
    "Район": "district_raw",
    "Наименование организации": "name",
    "БИН": "bin",
    "фактический адрес": "address",
    "Проектная мощность, мест": "capacity",
    "Контингент 1-11 (12) кл (2025-2026 уч.год)": "enrolment_2025",
    "Контингент 1-11 (12) кл (2026-2027 уч.год)": "enrolment_2026",
    "Форма собственности": "ownership",
    "количество смен обучения": "shifts",
    "Год ввода здания в эксплуатацию": "years",
    "Примечание": "note",
}
DISTRICTS = {
    "алматы": "Almaty",
    "есиль": "Esil",
    "сарыарка": "Saryarka",
    "байқоңыр": "Baikonur",
    "нура": "Nura",
    "нұра": "Nura",
    "сарайшық": "Saraishyk",
}
NUMBER = re.compile(r"(?:№|лицей)\s*(\d+)")
BINOM_KEYS = {
    "кекилба": "кекил",
    "алтынсарин": "алтынсарин",
    "мырза": "мырза",
    "байтурсын": "байтурсын",
    "букейхан": "bokeikhan",
}


def district_of(text: str) -> str | None:
    key = str(text).lower().replace("район", "").strip()
    return DISTRICTS.get(key)


def school_number(name: str) -> float:
    found = NUMBER.search(str(name))
    return float(found.group(1)) if found else np.nan


def building_years(text) -> list[int]:
    return [int(y) for y in re.findall(r"\d{4}", str(text))]


def bin_year(value) -> float:
    digits = re.sub(r"\D", "", str(value)).zfill(12)
    year = int(digits[:2])
    return float(2000 + year if year <= 30 else 1900 + year)


def binom_key(name: str) -> str | None:
    lowered = str(name).lower()
    if "binom" not in lowered:
        return None
    for key, value in BINOM_KEYS.items():
        if key in lowered:
            return value
    return None


def load() -> pd.DataFrame:
    raw = pd.read_excel(SOURCE, header=HEADER_ROW, dtype={"БИН": str})
    raw.columns = [str(c).strip() for c in raw.columns]
    first = raw.columns[0]
    mark = raw.index[raw.iloc[:, 1].astype(str).str.strip() == PRIVATE_MARK]
    raw["section"] = "state"
    if len(mark):
        raw.loc[mark[0] :, "section"] = "private"
    frame = raw.rename(columns=COLUMNS)
    frame = frame[frame["name"].notna() & frame["capacity"].notna()].copy()
    frame["row"] = frame[first]
    frame["district"] = frame["district_raw"].map(district_of)
    frame["name"] = frame["name"].astype(str).str.strip()
    frame["address"] = frame["address"].astype(str).str.strip().replace("nan", "")
    frame["number"] = frame["name"].map(school_number)
    frame.loc[frame["section"] == "private", "number"] = np.nan
    frame["binom"] = frame["name"].map(binom_key)
    years = frame["years"].map(building_years)
    frame["first_year"] = years.map(lambda v: min(v) if v else np.nan)
    frame["last_year"] = years.map(lambda v: max(v) if v else np.nan)
    frame["bin_year"] = frame["bin"].map(bin_year)
    frame["comfortable"] = frame["note"].astype(str).str.strip().eq("КШ")
    for column in ("capacity", "enrolment_2025", "enrolment_2026", "shifts"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    keep = [
        "row",
        "section",
        "district",
        "number",
        "binom",
        "name",
        "bin",
        "bin_year",
        "address",
        "capacity",
        "enrolment_2025",
        "enrolment_2026",
        "shifts",
        "years",
        "first_year",
        "last_year",
        "comfortable",
        "ownership",
    ]
    return frame[keep].reset_index(drop=True)


def facility_numbers(schools: gpd.GeoDataFrame) -> pd.Series:
    number = schools.set_index("facility_id")["number"].copy()
    path = PROCESSED / "comfortable_schools.gpkg"
    if path.exists():
        sites = gpd.read_file(path)
        sites = sites[(sites["status"] == "built") & sites["number"].notna()]
        listed = sites.set_index("facility_id")["number"]
        number = number.fillna(listed.reindex(number.index))
    return number


def link(register: pd.DataFrame, schools: gpd.GeoDataFrame) -> pd.Series:
    number = facility_numbers(schools).dropna()
    by_number = {int(n): f for f, n in number.items()}
    names = schools.set_index("facility_id")["name"].fillna("").str.lower()
    binom = {
        key: next((f for f, n in names.items() if "binom" in n and key in n), None)
        for key in BINOM_KEYS.values()
    }

    def resolve(row) -> str | None:
        if row["section"] == "state" and pd.notna(row["number"]):
            return by_number.get(int(row["number"]))
        if row["binom"]:
            return binom.get(row["binom"])
        return None

    return register.apply(resolve, axis=1)


def build() -> pd.DataFrame:
    from astana_access.accessibility.coverage import facilities

    register = load()
    register["facility_id"] = link(register, facilities()["school"])
    TABLE.parent.mkdir(parents=True, exist_ok=True)
    register.to_csv(TABLE, index=False)
    return register


def linked() -> pd.DataFrame:
    if not TABLE.exists():
        return build()
    return pd.read_csv(TABLE, dtype={"bin": str})

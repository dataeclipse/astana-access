import openpyxl
import pandas as pd

from astana_access.config import RAW

SOURCE = RAW / "stat" / "astana" / "population_single_age.xlsx"
SHEETS = {
    "г. Астана": "City",
    "район Алматы": "Almaty",
    "район Есиль": "Esil",
    "район Сарыарка": "Saryarka",
    "район Байқоңыр": "Baikonur",
    "район Нұра": "Nura",
    "район Сарайшық": "Saraishyk",
}
HEADER_ROW = 6
COHORT_AGES = {"preschool": (1, 6), "school": (7, 17)}


def parse_sheet(rows: list[tuple]) -> list[tuple]:
    header = rows[HEADER_ROW]
    end = header.index("Возраст", 1)
    years = header[1:end]
    records = []
    for row in rows[HEADER_ROW + 1 :]:
        if row[0] is None:
            continue
        for year, value in zip(years, row[1:end], strict=True):
            if value is not None:
                records.append((row[0], int(year), int(value)))
    return records


def load() -> pd.DataFrame:
    book = openpyxl.load_workbook(SOURCE, read_only=True)
    frames = []
    for sheet in book.worksheets:
        records = parse_sheet(list(sheet.iter_rows(values_only=True)))
        frame = pd.DataFrame(records, columns=["age", "year", "people"])
        frame["district"] = SHEETS[sheet.title]
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def totals(year: int, table: pd.DataFrame | None = None) -> dict[str, int]:
    table = load() if table is None else table
    rows = table[
        (table["year"] == year) & (table["age"] == "Всего") & (table["district"] != "City")
    ]
    return {
        district: int(value)
        for district, value in zip(rows["district"], rows["people"], strict=True)
    }


def cohort_shares(year: int, table: pd.DataFrame | None = None) -> pd.DataFrame:
    table = load() if table is None else table
    rows = table[table["year"] == year]
    single = rows[rows["age"].map(lambda age: isinstance(age, int))].copy()
    single["age"] = single["age"].astype(int)
    total = rows[rows["age"] == "Всего"].set_index("district")["people"]
    shares = {
        cohort: single[single["age"].between(low, high)].groupby("district")["people"].sum() / total
        for cohort, (low, high) in COHORT_AGES.items()
    }
    return pd.DataFrame(shares)

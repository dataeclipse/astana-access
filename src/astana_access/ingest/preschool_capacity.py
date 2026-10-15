import json

import geopandas as gpd
import pandas as pd
from scipy.stats import spearmanr

from astana_access.config import PROCESSED, RAW, REPORTS

SOURCE = RAW / "indigo" / "cards_2026-10-15" / "astana_kindergarten_capacity.csv"
ATTENDANCE = RAW / "indigo" / "team_2026-10-15" / "astana_actual_children.csv"
QUEUE = RAW / "indigo" / "team_2026-10-15" / "astana_queue_by_age.csv"
REGISTRY = RAW / "indigo" / "registry_2026-09-30.csv"
TOTALS = RAW / "indigo" / "totals_2026-09-30.json"
OWNERSHIP = {"Государственная": "state", "Частная": "private"}
AGES = ["До 2 лет", "2 года", "3 года", "4 года", "От 5 лет"]


def load() -> pd.DataFrame:
    table = pd.read_csv(SOURCE, sep=";", dtype=str, encoding="utf-8-sig")
    return pd.DataFrame(
        {
            "indigo_id": pd.to_numeric(table["ID Indigo"]).astype(int),
            "capacity": pd.to_numeric(table["Проектная мощность, мест"], errors="coerce"),
            "ownership": table["Форма собственности"].map(OWNERSHIP),
            "address": table["Адрес"].str.strip(),
        }
    )


def capacity_by_id() -> pd.Series:
    table = load().dropna(subset=["capacity"])
    return table.drop_duplicates("indigo_id").set_index("indigo_id")["capacity"]


def attendance_by_id() -> pd.Series:
    if not ATTENDANCE.exists():
        return pd.Series(dtype=float)
    table = pd.read_csv(ATTENDANCE, sep=";", dtype=str, encoding="utf-8-sig")
    children = pd.to_numeric(table["Фактическая нагрузка, детей"], errors="coerce")
    ids = pd.to_numeric(table["ID Indigo"]).astype(int)
    return pd.Series(children.to_numpy(), index=ids).dropna()


def queue() -> dict:
    table = pd.read_csv(QUEUE, sep=";", dtype=str, encoding="utf-8-sig")
    result = {}
    for row in table.itertuples(index=False):
        values = dict(zip(table.columns, row, strict=True))
        key = f"{values['Вид очереди']} / {values['Режим']}"
        result[key] = {"total": int(values["Всего в очереди"])} | {
            age: int(values[age]) for age in AGES
        }
    return result


def load_check(attendance: pd.Series) -> dict:
    from astana_access.accessibility.e2sfca import load_inputs
    from astana_access.accessibility.official_catchments import allocated_load
    from astana_access.equity.analysis import BASE

    preschools = gpd.read_file(PROCESSED / "facilities.gpkg", layer="preschools")
    ids = pd.to_numeric(preschools["indigo_id"], errors="coerce")
    observed = pd.Series(ids.map(attendance).to_numpy(), index=preschools["facility_id"])
    district = pd.Series(preschools["district"].to_numpy(), index=preschools["facility_id"])
    points, od = load_inputs()
    base = BASE["preschool"]
    demand = points.set_index("point_id")[f"preschool_{base['variant']}"].fillna(0)
    model = allocated_load(od["preschool"], demand, base)
    pair = pd.concat([observed, model], axis=1, keys=["observed", "model"]).dropna()
    pair = pair[pair["observed"] > 0]
    return {
        "organisations": int(len(pair)),
        "spearman_allocated_load": float(spearmanr(pair["observed"], pair["model"]).correlation),
        "attending_by_district": observed.groupby(district).sum().to_dict(),
    }


def check() -> dict | None:
    if not SOURCE.exists():
        return None
    cards = load()
    registry = pd.read_csv(REGISTRY, encoding="utf-8-sig")
    totals = json.loads(TOTALS.read_text(encoding="utf-8"))
    merged = registry.merge(cards, on="indigo_id", how="left", suffixes=("", "_card"))
    places = cards.groupby("ownership")["capacity"].sum()
    report = {
        "organisations": int(len(cards)),
        "with_capacity": int(cards["capacity"].notna().sum()),
        "places": float(cards["capacity"].sum()),
        "places_by_ownership": places.to_dict(),
        "children_by_ownership_2026_09_30": {
            "state": totals["state_children"],
            "private": totals["private_children"],
        },
        "registry_without_card": int(merged["capacity"].isna().sum()),
        "cards_not_in_registry": int((~cards["indigo_id"].isin(registry["indigo_id"])).sum()),
        "ownership_agreement": float(
            (merged["ownership"] == merged["ownership_card"]).sum()
            / merged["capacity"].notna().sum()
        ),
        "address_agreement": float(
            (merged["address"].str.strip() == merged["address_card"]).sum()
            / merged["capacity"].notna().sum()
        ),
        "free_places_above_capacity": int((merged["free_places"] > merged["capacity"]).sum()),
        "free_share_of_places": (
            merged.groupby("ownership")["free_places"].sum()
            / merged.groupby("ownership")["capacity"].sum()
        ).to_dict(),
    }
    attendance = attendance_by_id()
    if len(attendance):
        cards["attending"] = cards["indigo_id"].map(attendance)
        ratio = cards["attending"] / cards["capacity"]
        merged["attending"] = merged["indigo_id"].map(attendance)
        gap = merged["capacity"] - merged["attending"]
        preschools = gpd.read_file(PROCESSED / "facilities.gpkg", layer="preschools")
        district = pd.Series(
            preschools["district"].to_numpy(),
            index=pd.to_numeric(preschools["indigo_id"], errors="coerce"),
        )
        cards["district"] = cards["indigo_id"].map(district[~district.index.duplicated()])
        by_district = cards.groupby("district")[["capacity", "attending"]].sum()
        by_district["children_per_place"] = by_district["attending"] / by_district["capacity"]
        report["attendance"] = {
            "attending": float(cards["attending"].sum()),
            "attending_by_ownership": cards.groupby("ownership")["attending"].sum().to_dict(),
            "children_per_place_by_ownership": (
                cards.groupby("ownership")["attending"].sum()
                / cards.groupby("ownership")["capacity"].sum()
            ).to_dict(),
            "above_capacity": int((ratio > 1).sum()),
            "at_capacity": int((ratio == 1).sum()),
            "median_children_per_place": float(ratio.median()),
            "spearman_free_places_vs_spare_places": float(
                spearmanr(merged["free_places"], gap, nan_policy="omit").correlation
            ),
            "by_district": by_district.round(3).to_dict("index"),
            **load_check(attendance),
        }
    if QUEUE.exists():
        report["queue_city"] = queue()
    (REPORTS / "preschool_capacity_check.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(check(), indent=1, ensure_ascii=False, default=float))

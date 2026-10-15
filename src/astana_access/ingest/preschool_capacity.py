import json

import pandas as pd

from astana_access.config import RAW, REPORTS

SOURCE = RAW / "indigo" / "cards_2026-10-15" / "astana_kindergarten_capacity.csv"
REGISTRY = RAW / "indigo" / "registry_2026-09-30.csv"
TOTALS = RAW / "indigo" / "totals_2026-09-30.json"
OWNERSHIP = {"Государственная": "state", "Частная": "private"}


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
        "children_per_place": {
            "state": totals["state_children"] / float(places["state"]),
            "private": totals["private_children"] / float(places["private"]),
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
    (REPORTS / "preschool_capacity_check.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=float), encoding="utf-8"
    )
    return report

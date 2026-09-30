import html
import json
import re
from pathlib import Path

import pandas as pd

from astana_access.config import RAW

MANUAL = RAW / "manual"
ITEM = re.compile(
    r'<div class="g-list-item" data-key="\d+"[^>]*>(.*?)(?=<div class="g-list-item" data-key="|\Z)',
    re.S,
)
TOTALS = re.compile(
    r"Всего\s+Дошкольных организаций\s*-\s*([\d\s]+)\s+Ходит детей\s*-\s*([\d\s]+)\s+"
    r"Государственных\s+Дошкольных организаций\s*-\s*([\d\s]+)\s+Ходит детей\s*-\s*([\d\s]+)\s+"
    r"Частных\s+Дошкольных организаций\s*-\s*([\d\s]+)\s+Ходит детей\s*-\s*([\d\s]+)"
)
KIND = [
    ("mini_centre", re.compile(r"мини[- ]?центр|шағын орталы|шагын орталы", re.I)),
    ("complex_school", re.compile(r"школа|мектеп|гимнази|лицей", re.I)),
    ("nursery_kindergarten", re.compile(r"ясли|бөбекжай|бобекжай", re.I)),
    ("kindergarten", re.compile(r"детск\w*\s+сад|балабақша|балабакша|д/с", re.I)),
]


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.S)
    return _clean(match.group(1)) if match else ""


def kind_of(name: str) -> str:
    for kind, pattern in KIND:
        if pattern.search(name):
            return kind
    return "other"


def parse_registry(path: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    page = path.read_text(encoding="utf-8", errors="replace")
    rows = []
    for block in ITEM.findall(page):
        link = re.search(r'href="[^"]*/view/(\d+)"', block)
        name = _first(r'class="g-list-title"[^>]*>(.*?)</a>', block)
        info = _first(r'class="g-list-info">(.*?)</div>', block)
        free = re.search(r"Свободные места:\s*(\d+)", block)
        age = re.search(r"Зачисление с\s*(\d+)", info)
        languages = re.search(r"языки:\s*(.*)", info)
        badges = {
            _clean(b) for b in re.findall(r'class="g-bg-block[^"]*">(.*?)</span>', block, re.S)
        }
        ownership = (
            "state"
            if "Государственная" in badges
            else ("private" if "Частная" in badges else "unknown")
        )
        rows.append(
            {
                "indigo_id": int(link.group(1)) if link else None,
                "name": name.strip('" '),
                "address": _first(r'class="g-list-adress">(.*?)</div>', block),
                "ownership": ownership,
                "kind": kind_of(name),
                "min_age": int(age.group(1)) if age else None,
                "languages": languages.group(1).strip() if languages else "",
                "free_places": int(free.group(1)) if free else 0,
            }
        )
    text = _clean(re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S))
    totals: dict[str, int] = {}
    match = TOTALS.search(text)
    if match:
        values = [int(re.sub(r"\D", "", g)) for g in match.groups()]
        keys = (
            "organisations",
            "children",
            "state_organisations",
            "state_children",
            "private_organisations",
            "private_children",
        )
        totals = dict(zip(keys, values, strict=True))
    return pd.DataFrame(rows), totals


def parse_free_places(path: Path) -> pd.DataFrame:
    page = path.read_text(encoding="utf-8", errors="replace")
    start = page.find("searchPlaces.setData(")
    if start < 0:
        return pd.DataFrame()
    payload, _ = json.JSONDecoder().raw_decode(page[start + len("searchPlaces.setData(") :])
    groups = {int(key): name for key, name in payload.get("ageGroups", {}).items()}
    languages = {int(key): name for key, name in payload.get("languages", {}).items()}
    rows = []
    for item in payload["results"]:
        for group in item["AgeGroupFreePlaces"]:
            rows.append(
                {
                    "indigo_id": item["Id"],
                    "name": item["Name"],
                    "address": item["Address"],
                    "ownership": {1: "state", 2: "private"}.get(item["OwnershipFormId"], "unknown"),
                    "age_group_id": group["Id"],
                    "age_group": groups.get(group["Id"], str(group["Id"])),
                    "language": languages.get(group.get("StudyLanguageId"), ""),
                    "free_places": group["Count"],
                }
            )
    return pd.DataFrame(rows)


def run(snapshot: str = "2026-09-30") -> tuple[pd.DataFrame, dict[str, int], pd.DataFrame]:
    registry, totals = parse_registry(MANUAL / f"indigo_registry_{snapshot}.html")
    free = parse_free_places(MANUAL / f"indigo_free_places_{snapshot}.html")
    target = RAW / "indigo"
    target.mkdir(parents=True, exist_ok=True)
    registry.to_csv(target / f"registry_{snapshot}.csv", index=False, encoding="utf-8-sig")
    free.to_csv(target / f"free_places_{snapshot}.csv", index=False, encoding="utf-8-sig")
    (target / f"totals_{snapshot}.json").write_text(json.dumps(totals, indent=1), encoding="utf-8")
    return registry, totals, free

import html
import json
import re
import time
from pathlib import Path

import httpx
import pandas as pd

from astana_access.config import RAW

BASE = "https://sakura-nursultan.e-orda.kz/ru/school-registr"
CACHE = RAW / "sakura"
USER_AGENT = "Mozilla/5.0 (compatible; astana-access/0.1; academic research)"
DELAY_S = 1.0
ROW = re.compile(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", re.S)
CLASS_ROW = re.compile(
    r"<tr>\s*<td>(.*?)</td>\s*<td>.*?</td>\s*<td>(.*?)</td>\s*<td>(\d+)</td>\s*<td>(\d+)</td>\s*</tr>",
    re.S,
)
FIELDS = {
    "languages": "Языки обучения",
    "ownership": "Форма собственности",
    "kind": "Вид",
    "founded": "Год основания",
    "website": "Web-сайт",
}


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def fetch(url: str, target: Path, client: httpx.Client, ajax: bool = False) -> str:
    if target.exists():
        return target.read_text(encoding="utf-8", errors="replace")
    headers = {"X-Requested-With": "XMLHttpRequest"} if ajax else {}
    response = client.get(url, headers=headers)
    response.raise_for_status()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(response.text, encoding="utf-8")
    time.sleep(DELAY_S)
    return response.text


def parse_info(page: str) -> dict[str, str]:
    text = _clean(re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S))
    labels = "|".join(map(re.escape, [*FIELDS.values(), "Уклон", "Базовая стоимость", "Адрес"]))
    found = {}
    for key, label in FIELDS.items():
        match = re.search(
            re.escape(label) + r":\s*(.*?)\s*(?=(?:" + labels + r"|Номер лицензии|Телефон):)", text
        )
        found[key] = match.group(1) if match else ""
    return found


def parse_houses(fragment: str) -> list[tuple[str, str]]:
    rows = []
    for area, houses in ROW.findall(fragment):
        for house in re.findall(r"<span>(.*?)</span>", houses, flags=re.S):
            rows.append((_clean(area), _clean(house)))
    return rows


def parse_classes(page: str) -> list[dict]:
    start = page.find('id="classComplect"')
    end = page.find("d-lg-none", start)
    rows = []
    for label, language, pupils, free in CLASS_ROW.findall(page[start:end]):
        rows.append(
            {
                "class": _clean(label),
                "language": _clean(language),
                "pupils": int(pupils),
                "free_places": int(free),
            }
        )
    return rows


def run() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    schools, classes, catchment = [], [], []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=40, follow_redirects=True
    ) as client:
        listing = json.loads(
            fetch(f"{BASE}/coordinates", CACHE / "coordinates.json", client, ajax=True)
        )
        for item in listing["result"]:
            sid = item["id"]
            info = parse_info(fetch(f"{BASE}/view?id={sid}", CACHE / f"view_{sid}.html", client))
            schools.append(
                {
                    "sakura_id": sid,
                    "name": item["name"].strip(),
                    "address": item["address"],
                    "lat": item["lat"],
                    "lon": item["lng"],
                    "private": item["chastnaya"],
                    **info,
                }
            )
            page = fetch(
                f"{BASE}/view?id={sid}&tab=classComplect",
                CACHE / f"view_{sid}_classComplect.html",
                client,
            )
            classes.extend({"sakura_id": sid, **row} for row in parse_classes(page))
            fragment = fetch(
                f"{BASE}/houses?school={sid}", CACHE / f"houses_{sid}.html", client, ajax=True
            )
            catchment.extend(
                {"sakura_id": sid, "area": area, "house": house}
                for area, house in parse_houses(fragment)
            )
    frames = (pd.DataFrame(schools), pd.DataFrame(classes), pd.DataFrame(catchment))
    for frame, name in zip(frames, ("schools", "first_grade", "catchment"), strict=True):
        frame.to_csv(CACHE / f"{name}.csv", index=False, encoding="utf-8-sig")
    return frames

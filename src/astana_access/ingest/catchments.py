import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import pandas as pd

from astana_access.config import INTERIM, RAW

SOURCE = RAW / "official_reply"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DISTRICT = {
    "Алматы": "Almaty",
    "Байқоңыр": "Baikonur",
    "Есиль": "Esil",
    "Нура": "Nura",
    "Сарайшық": "Saraishyk",
    "Сарыарка": "Saryarka",
}
STREET_TYPE = re.compile(
    r"(?<![а-яәғқңөұүһіa-z.])(ул|улица|пр|проспект|пер|переулок|шоссе|б-р|бульвар|тупик|проезд|"
    r"мкр|микрорайон|ж\.?\s?м|п(?=\s*\.\s*«)|пос)\s*\.\s*",
    re.I,
)
NOTE = re.compile(r"\([^()]*\)")
LABEL = re.compile(r"[^;,.]*(?:класс|обучени)[^:;]*:?", re.I)
NAMED = re.compile(
    r"(?:ЖК|ДО\b|д/о|дачн|коттедж|таунхаус|ж\.?\s?м|жилой массив|пос[её]лок|общество)", re.I
)
HOUSE = re.compile(r"^(\d+)\s*([а-яa-z])?\s*(?:/\s*(\d+)\s*([а-яa-z])?)?(?:\s*блок\s*\S+)?$", re.I)
RANGE = re.compile(r"^(\d+)[^\d-]*\s*-\s*(\d+)")
NUMBER = re.compile(r"№\s*(\d+)")
ALL = re.compile(r"\(?\s*вс[её]\s*\)?|четн|нечетн", re.I)
SETTLEMENT = re.compile(r"[«\"]([^»\"]+)[»\"]")


@dataclass
class Item:
    street: str
    house: str
    kind: str


def read_rows(path) -> list[list[str]]:
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    rows = []
    for row in root.iter(W + "tr"):
        cells = [
            "".join(t.text or "" for t in cell.iter(W + "t")).strip()
            for cell in row.findall(W + "tc")
        ]
        rows.append(cells)
    return rows


def load_rows() -> pd.DataFrame:
    records = []
    for path in sorted(SOURCE.glob("Территория обслуживания школ*.docx")):
        label = re.search(r"«([^»]+)»", path.name).group(1).strip()
        for cells in read_rows(path):
            if len(cells) < 2 or not cells[0]:
                continue
            number = NUMBER.search(cells[0])
            records.append(
                {
                    "district": DISTRICT[label],
                    "school": cells[0],
                    "number": int(number.group(1)) if number else None,
                    "text": cells[-1],
                }
            )
    return pd.DataFrame(records)


def clean(text: str) -> str:
    text = text.replace("\xa0", " ").replace("–", "-").replace("—", "-")
    previous = None
    while previous != text:
        previous = text
        text = NOTE.sub(" ; ", text)
    text = re.sub(r"(?<=\d)(?=(?:ул|пр|пер|мкр)\s*\.)", "; ", text, flags=re.I)
    text = re.sub(r"(?<=[а-я])(?=(?:ул|пр|пер|мкр)\s*\.)", " ; ", text)
    text = LABEL.sub(" ; ", text)
    text = re.sub(r"(?<![а-яa-z])д\s*\.\s*", "", text)
    text = re.sub(r"(?<=[\dа-яa-z])\s*блок\s*[A-ZА-Яa-zа-я0-9]{1,3}(?![а-яa-z])", "", text)
    text = re.sub(r"(?<![а-яa-z])блок\s*[A-ZА-Яa-zа-я0-9]{1,3}(?![а-яa-z])", "", text)
    return text


def is_house(token: str) -> bool:
    return bool(HOUSE.match(token.strip()))


def split_name(token: str) -> tuple[str, list[str]]:
    words = token.split()
    for i in range(len(words)):
        tail = " ".join(words[i:])
        name = " ".join(words[:i])
        if i > 0 and any(ch.isalpha() for ch in name) and (is_house(tail) or RANGE.match(tail)):
            return name, [tail]
    return token, []


def parse(text: str) -> list[Item]:
    items: list[Item] = []
    street = ""
    for segment in re.split(r";", clean(text)):
        segment = segment.strip(" .,")
        if not segment:
            continue
        settlement = SETTLEMENT.search(segment)
        if settlement and not re.search(r"\d", SETTLEMENT.sub("", segment)):
            for name in SETTLEMENT.findall(segment):
                items.append(Item(name.strip(" :"), "", "settlement"))
            continue
        parts = STREET_TYPE.split(segment)
        chunks = []
        if parts[0].strip():
            chunks.append(("", parts[0]))
        for i in range(1, len(parts) - 1, 2):
            chunks.append((parts[i].lower(), parts[i + 1]))
        for kind, chunk in chunks:
            tokens = [t.strip(" .") for t in chunk.split(",") if t.strip(" .")]
            if kind and tokens:
                name, houses = split_name(tokens[0])
                name = name.rstrip(":").strip()
                street = f"{kind}. {name}".strip() if kind not in ("п", "пос", "с") else name
                tokens = houses + tokens[1:]
                if (
                    kind in ("п", "пос", "с", "ж.м", "жм", "ж. м", "мкр", "микрорайон")
                    and not tokens
                ):
                    items.append(Item(name.strip(' «»"'), "", "settlement"))
                    continue
                if not tokens:
                    items.append(Item(street, "", "street"))
                    continue
            for token in tokens:
                token = token.strip()
                if is_house(token):
                    items.append(Item(street, token, "house"))
                elif RANGE.match(token):
                    low, high = map(int, RANGE.match(token).groups())
                    items.append(Item(street, f"{low}-{high}", "range"))
                elif ALL.search(token):
                    items.append(Item(street, "", "street"))
                elif token and token[0].isalpha():
                    if NAMED.search(token) or SETTLEMENT.search(token):
                        for name in SETTLEMENT.findall(token) or [token]:
                            items.append(Item(name.strip(" :"), "", "settlement"))
                        continue
                    name, houses = split_name(token)
                    street = name.rstrip(":").strip()
                    if not houses:
                        items.append(Item(street, "", "street"))
                    for house in houses:
                        if RANGE.match(house):
                            low, high = map(int, RANGE.match(house).groups())
                            items.append(Item(street, f"{low}-{high}", "range"))
                        else:
                            items.append(Item(street, house, "house"))
    return [item for item in items if item.street]


def expand() -> pd.DataFrame:
    rows = load_rows()
    records = []
    for row in rows.itertuples(index=False):
        for item in parse(row.text):
            records.append(
                {
                    "district": row.district,
                    "school": row.school,
                    "number": row.number,
                    "street": item.street,
                    "house": item.house,
                    "kind": item.kind,
                }
            )
    frame = pd.DataFrame(records)
    frame.to_csv(INTERIM / "catchments_parsed.csv", index=False)
    return frame


def geocode(frame: pd.DataFrame | None = None) -> pd.DataFrame:
    from astana_access.inventory.addresses import house_base, load_gazetteer, norm_street

    frame = expand() if frame is None else frame
    gazetteer = load_gazetteer()
    records = []
    for row in frame.itertuples(index=False):
        hint = frozenset({row.district})
        base = {
            "district": row.district,
            "school": row.school,
            "number": row.number,
            "street": row.street,
            "house": row.house,
            "kind": row.kind,
        }
        if row.kind == "house":
            found = gazetteer.locate(row.street, row.house, hint)
            records.append(
                base | {"lon": found.lon, "lat": found.lat, "precision": found.precision}
            )
            continue
        if row.kind not in ("range", "street"):
            records.append(base | {"lon": None, "lat": None, "precision": "settlement"})
            continue
        keys = gazetteer.candidates(norm_street(row.street))
        if len(keys) != 1:
            records.append(base | {"lon": None, "lat": None, "precision": "street_unmatched"})
            continue
        group = gazetteer.by_street[keys[0]]
        group = group[group["district"] == row.district]
        if row.kind == "range":
            low, high = map(int, row.house.split("-"))
            bases = group["house_key"].map(house_base)
            group = group[(bases >= low) & (bases <= high)]
        if not len(group):
            records.append(base | {"lon": None, "lat": None, "precision": f"{row.kind}_empty"})
            continue
        for address in group.itertuples(index=False):
            records.append(
                base
                | {
                    "house": address.housenumber,
                    "lon": address.lon,
                    "lat": address.lat,
                    "precision": row.kind,
                }
            )
    result = pd.DataFrame(records)
    result.to_csv(INTERIM / "catchments_geocoded.csv", index=False)
    return result

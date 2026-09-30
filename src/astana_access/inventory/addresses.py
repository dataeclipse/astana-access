import re
from dataclasses import dataclass
from functools import lru_cache

import geopandas as gpd
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from astana_access.config import CRS_GEO, PROCESSED, RAW
from astana_access.inventory.names import KAZAKH

LATIN = str.maketrans("abcehkmoptxy", "авсенкмортху")

STREET_TYPES = (
    r"улиц[аыеу]|ул|к[оө]ше(?:с[іи])?|проспек[тс]\w*|просп|пр-т|пр|да[нң][гғ]ылы|переулок|пер|"
    r"т[ұу]йы[кқгғ]ы?|орамы?|желекжолы|шоссе|тас жолы|бульвар\w*|площадь|ала[нң]ы|"
    r"микрорайон|мкр|мк-н|ша[гғ]ын ауданы|жилой массив|ж\.?\s?м|т[ұу]р[гғ]ын алабы|т\.?\s?а|"
    r"трасса|тупик|проезд"
)
CITY = re.compile(
    r"\b(?:город|г|каласы|қаласы)\.?\s*(?:астана|нур\s*-?\s*султан)\b|\b(?:астана|нур\s*-?\s*султан)\s*(?:каласы|қаласы|город|г)?\b",
    re.I,
)
DISTRICT = re.compile(
    r"\bрайон\w*\s+[\"«]?(?:алматы|есиль?|есил|сарыарк[аи]|байконы?р|байконур|нура|нуры|сарайшы[кқ])[\"»]?|"
    r"\b(?:алматы|алматинск\w+|есиль?ск\w+|есиль?|есил|сарыарк\w+|байконы?р\w*|байконур\w*|нур[аы]|нуринск\w+|сарайшы[кқ]\w*)\s+(?:район\w*|ройон|ауданы)",
    re.I,
)
TAIL = re.compile(
    r",?\s*\b(?:нп|вп|н\.п|в\.п|офис|оф|кв|квартира|помещение|пом|блок|корпус|этаж|подъезд)\b.*$",
    re.I,
)
HOUSE = re.compile(
    r"(?:\b(?:дом|здание|зд|строение|стр|уч|участок|д)\b\.?\s*)?№?\s*"
    r"(?<![а-яa-z\d])(\d{1,4}\s*[а-яa-z]?(?:\s*/\s*\d{1,3}\s*[а-яa-z]?)?)(?![\dа-я])",
    re.I,
)


CODE = re.compile(r"(?<![а-яa-z\d])([еаea])\s*[- ]?\s*(\d{1,4})(?![\dа-я/])", re.I)
SURNAME_TAIL = re.compile(r"^(.{4,}(?:ов|ев|ин|ын))а$")
STREET_KEY = re.compile(
    r"(?<![а-я])(?:улиц[аыеу]|ул|проспект\w*|пр-т|просп|пр|переулок|пер|шоссе|бульвар|тупик|проезд|трасса)(?![а-я])\.?",
    re.I,
)


LANE = re.compile(r"(?<![а-я])(?:переулок|пер|тупик|т[ұу]йы[кқгғ]ы?|орамы?|проезд)(?![а-я])", re.I)
NUMBERED_STREET = re.compile(
    r"(?<![а-я])(улиц[аы]|ул|переулок|пер|проезд)\.?\s*№?\s*(\d{1,4})(?=\s*[,;]|\s+(?:д|дом|здание|зд)(?![а-я]))",
    re.I,
)
LANE_TOKEN = "пер#"
SPREAD_LIMIT_M = 150.0
SPREAD_WIDE_M = 400.0
MERGE_RADIUS_M = 3000.0
MERGE_RATIO = 86
TOKEN_RATIO = 88
MERGE_TOKEN_RATIO = 92
TOKEN_MIN = 5
DISTRICT_HINTS = (
    (re.compile(r"сарыар[кқ]", re.I), frozenset({"Saryarka", "Baikonur"})),
    (re.compile(r"байконы?р|байқоңыр|байконур", re.I), frozenset({"Baikonur"})),
    (re.compile(r"сарайшы[кқ]", re.I), frozenset({"Saraishyk"})),
    (re.compile(r"(?<![а-я])нур[аы](?![а-я-])|нуринск|нұра", re.I), frozenset({"Nura"})),
    (re.compile(r"есиль?|есіл", re.I), frozenset({"Esil", "Nura"})),
    (re.compile(r"алмат", re.I), frozenset({"Almaty", "Saraishyk", "Baikonur"})),
)
DISTRICT_MENTION = re.compile(
    r"(?:район\w*|ройон|ауданы?|р-н)\s*[\"«]?\s*([а-яәғқңөұүһі]+)|([а-яәғқңөұүһі]+)\s+(?:район\w*|ройон|ауданы)",
    re.I,
)


def district_hint(address: str | None) -> frozenset[str]:
    text = str(address or "").lower()
    for match in DISTRICT_MENTION.finditer(text):
        word = match.group(1) or match.group(2)
        for pattern, names in DISTRICT_HINTS:
            if pattern.search(word):
                return names
    return frozenset()


WORD = re.compile(r"[a-zа-яәғқңөұүһіё]+")
CYRILLIC = re.compile(r"[а-яәғқңөұүһіё]")
ORDINAL = re.compile(r"(\d+)\s*-?\s*(?:ш[iіи]|ая|ой|й|я)(?![а-яa-z])")
GLUED = re.compile(r"([а-я]{3,})(\d)")


def _mixed(match: re.Match) -> str:
    word = match.group(0)
    return word.replace("i", "і").translate(LATIN) if CYRILLIC.search(word) else word


def _fold(text: str | None) -> str:
    value = WORD.sub(_mixed, str(text or "").lower())
    value = value.translate(KAZAKH).replace("ё", "е")
    value = ORDINAL.sub(r"\1 ", value)
    value = GLUED.sub(r"\1 \2", value)
    return CODE.sub(lambda m: " " + m.group(1).translate(LATIN) + m.group(2) + " ", value)


PHONETIC = str.maketrans({"ы": "и", "й": "и", "э": "е", "ь": None, "ъ": None})


def _stem(token: str) -> str:
    token = token.translate(PHONETIC).replace("дж", "ж")
    match = SURNAME_TAIL.match(token)
    return match.group(1) if match else token


def norm_street(text: str | None) -> str:
    value = re.sub(r"\([^)]*\)", " ", _fold(text))
    value = re.sub(r"[\"«»'`.,()]", " ", value)
    lane = bool(LANE.search(value))
    value = re.sub(r"(?<![а-я])(?:" + STREET_TYPES + r")(?![а-я])\.?", " ", value)
    tokens = [t for t in re.split(r"[\s\-]+", value) if t]
    tokens = [_stem(t) for t in tokens if len(t) > 1 or t.isdigit()]
    if not tokens:
        return ""
    return " ".join(sorted(tokens) + ([LANE_TOKEN] if lane else []))


def spread_m(group: pd.DataFrame) -> float:
    lat = group["lat"].to_numpy()
    lon = group["lon"].to_numpy()
    return float(np.hypot((lat - lat.mean()) * 111_000, (lon - lon.mean()) * 69_700).max())


def norm_house(text: str | None) -> str:
    value = str(text or "").lower().translate(LATIN)
    value = re.sub(r"\b(?:дом|здание|зд|строение|стр|д)\b\.?", "", value)
    return re.sub(r"[\s№.\-]", "", value)


def house_base(text: str) -> int | None:
    match = re.match(r"(\d+)", text)
    return int(match.group(1)) if match else None


def street_initials(text: str | None) -> frozenset[str]:
    value = re.sub(r"[\"«»'`.,()]", " ", _fold(text))
    value = re.sub(r"(?<![а-я])(?:" + STREET_TYPES + r")(?![а-я])\.?", " ", value)
    return frozenset(t for t in re.split(r"[\s\-]+", value) if len(t) == 1 and t.isalpha())


def split_address(address: str) -> tuple[str, str]:
    value = _fold(str(address).replace("\\", "/"))
    value = re.sub(r"(\d)\s*(н\.?\s?п|в\.?\s?п|дом)(?![а-я])", r"\1 \2", value)
    value = re.sub(r"\b(?:республика\s+)?каза[кх]стан\b", " ", value)
    value = re.sub(r"\b(?:город\w*|г)\.?\s*(?:а[кс]?стан[аы]|нур\s*-?\s*[сc]ултан)\b", " ", value)
    value = re.sub(r"\b(?:астана|нур\s*-?\s*султан)\s+каласы\b", " ", value)
    value = re.sub(r"^\s*(?:астана|нур\s*-?\s*султан)\s*[,. ]", " ", value)
    value = DISTRICT.sub(" ", value)
    value = re.sub(
        r"\bр(?:-н|айон)?\.?\s*(?:алматы|есиль?|есил|сарыарк\w*|байконы?р|байконур|нур[аы]|сарайшы[кқ])\b",
        " ",
        value,
    )
    value = TAIL.sub("", value)
    value = re.sub(r"\s+", " ", value).strip(" ,.;")
    value = re.sub(r"\bастана\s+[кқ]аласы\b", " ", value).strip(" ,.;")
    value = re.sub(r"([а-я]{4,})дом(?=\s*\d)", r"\1 дом", value)
    numbered = NUMBERED_STREET.search(value)
    if numbered:
        house = HOUSE.search(value, numbered.end())
        if house:
            lane = "переулок " if LANE.search(numbered.group(1)) else "улица "
            return lane + numbered.group(2), house.group(1)
    for key in reversed(list(STREET_KEY.finditer(value))):
        rest = HOUSE.sub(" ", value[key.end() :])
        if re.search(r"[а-я]{3,}|[еа]\d", rest):
            value = value[key.start() :]
            break
    matches = list(HOUSE.finditer(value))
    if not matches:
        return value, ""
    chosen = matches[0]
    for match in matches:
        if re.search(r"дом|здание|зд|строение", match.group(0), re.I):
            chosen = match
            break
    street = value[: chosen.start()].strip(" ,.;")
    if not street:
        street = value[chosen.end() :].strip(" ,.;")
    street = re.sub(r"[\s,]+(?:здание|дом|зд|д)$", "", street)
    return street, chosen.group(1)


@dataclass
class Located:
    lon: float | None
    lat: float | None
    precision: str
    street_score: float
    matched_street: str


def is_lane(key: str) -> bool:
    return key.endswith(LANE_TOKEN)


def street_aliases(streets: pd.DataFrame) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(key: str) -> str:
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def keys_of(row: pd.Series, columns: tuple[str, ...]) -> list[str]:
        values = []
        for column in columns:
            for part in str(row[column] or "").split(";") if pd.notna(row[column]) else []:
                key = norm_street(part)
                if key:
                    values.append(key)
        return values

    unique = streets.drop_duplicates(
        ["name", "name_ru", "name_kk", "alt_name", "old_name", "old_name_ru"]
    )
    former: dict[str, set[str]] = {}
    rows = []
    for _, row in unique.iterrows():
        current = keys_of(row, ("name", "name_ru", "name_kk", "alt_name"))
        if not current:
            continue
        for key in current[1:]:
            parent[find(key)] = find(current[0])
        rows.append((current[0], keys_of(row, ("old_name", "old_name_ru"))))
    for anchor, old in rows:
        for key in old:
            former.setdefault(key, set()).add(find(anchor))
    aliases = {key: find(key) for key in list(parent)}
    for key, roots in former.items():
        if key not in aliases and len(roots) == 1:
            aliases[key] = next(iter(roots))
    return aliases


class Gazetteer:
    def __init__(self, addresses: pd.DataFrame, aliases: dict[str, str] | None = None) -> None:
        self.aliases = dict(aliases or {})
        frame = addresses[addresses["street"].notna()].copy()
        frame["street_key"] = frame["street"].map(norm_street)
        frame["house_key"] = frame["housenumber"].map(norm_house)
        frame = frame[frame["street_key"] != ""]
        if "district" not in frame.columns:
            frame["district"] = None
        frame["street_key"] = frame["street_key"].map(lambda key: self.aliases.get(key, key))
        self._merge_variants(frame)
        frame["street_key"] = frame["street_key"].map(lambda key: self.aliases.get(key, key))
        self.frame = frame
        known = set(frame["street_key"])
        self.lookup = {key: root for key, root in self.aliases.items() if root in known}
        self.lookup.update({key: key for key in known})
        self.streets = sorted(self.lookup)
        self.pools = {
            True: [key for key in self.streets if is_lane(key)],
            False: [key for key in self.streets if not is_lane(key)],
        }
        self.by_street = {key: group for key, group in frame.groupby("street_key")}
        self.token_index: dict[str, set[str]] = {}
        for key in self.pools[False]:
            for token in key.split():
                if len(token) >= TOKEN_MIN and token.isalpha():
                    self.token_index.setdefault(token, set()).add(self.lookup[key])
        self.tokens = sorted(self.token_index)

    def _merge_variants(self, frame: pd.DataFrame) -> None:
        centre = frame.groupby("street_key")[["lon", "lat"]].median()
        size = frame.groupby("street_key").size()
        keys = [key for key in centre.index if not any(c.isdigit() for c in key)]

        def near(a: str, b: str) -> bool:
            dx = (centre.at[a, "lon"] - centre.at[b, "lon"]) * 69_700
            dy = (centre.at[a, "lat"] - centre.at[b, "lat"]) * 111_000
            return float(np.hypot(dx, dy)) <= MERGE_RADIUS_M

        merged: dict[str, str] = {}
        plain = [key for key in keys if not is_lane(key)]
        multi = [key for key in plain if len(key.split()) > 1]
        for key in plain:
            if " " in key or len(key) < TOKEN_MIN:
                continue
            siblings = [
                other
                for other in multi
                if any(fuzz.ratio(key, token) >= MERGE_TOKEN_RATIO for token in other.split())
            ]
            if len(siblings) == 1 and near(key, siblings[0]):
                merged[key] = siblings[0]
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                if is_lane(a) != is_lane(b) or a in merged or b in merged:
                    continue
                if min(len(a), len(b)) < 10:
                    continue
                if fuzz.token_sort_ratio(a, b) >= MERGE_RATIO and near(a, b):
                    small, large = (a, b) if size[a] <= size[b] else (b, a)
                    merged[small] = large
        for key in list(merged):
            target = merged[key]
            while target in merged:
                target = merged[target]
            self.aliases[key] = target
        for key, root in list(self.aliases.items()):
            if root in merged:
                self.aliases[key] = self.aliases[root]

    @lru_cache(maxsize=8192)  # noqa: B019
    def candidates(self, key: str, initials: frozenset[str] = frozenset()) -> tuple[str, ...]:
        if not key:
            return ()
        if key in self.lookup:
            return (self.lookup[key],)
        lane = is_lane(key)
        tokens = [t for t in key.split() if t != LANE_TOKEN]
        if not lane and len(tokens) == 1:
            found = self._by_token(tokens[0], initials)
            if found:
                return found
        pool = self.pools[lane]
        if not pool:
            return ()
        best = process.extractOne(key, pool, scorer=fuzz.token_sort_ratio)
        if best and best[1] >= 86:
            return (self.lookup[best[0]],)
        if len(tokens) > 1:
            loose = process.extractOne(key, pool, scorer=fuzz.token_set_ratio)
            if loose and loose[1] >= 96:
                shared = set(tokens) & set(loose[0].split())
                if any(len(token) >= TOKEN_MIN for token in shared):
                    return (self.lookup[loose[0]],)
        return ()

    def _by_token(self, token: str, initials: frozenset[str]) -> tuple[str, ...]:
        if len(token) < TOKEN_MIN or not token.isalpha():
            return ()
        streets = self.token_index.get(token)
        if not streets:
            hits = process.extract(token, self.tokens, scorer=fuzz.ratio, limit=3)
            if not hits or hits[0][1] < TOKEN_RATIO:
                return ()
            if len(hits) > 1 and hits[1][1] >= hits[0][1] - 4:
                return ()
            token = hits[0][0]
            streets = self.token_index[token]
        if len(streets) > 1 and initials:
            fitting = [
                street
                for street in streets
                if any(t != token and t[0] in initials for t in street.split())
            ]
            if fitting:
                return tuple(sorted(fitting))
        return tuple(sorted(streets))

    def match_street(self, key: str, initials: frozenset[str] = frozenset()) -> tuple[str, float]:
        found = self.candidates(key, initials)
        if len(found) == 1:
            return found[0], 100.0 if key in self.lookup else 90.0
        return "", 0.0

    def locate(
        self,
        street: str,
        house: str,
        hint: frozenset[str] = frozenset(),
    ) -> Located:
        found = self.candidates(norm_street(street), street_initials(street))
        if not found:
            return Located(None, None, "none", 0.0, "")
        results = [self._locate_on(key, house, hint) for key in found]
        if len(found) == 1:
            return results[0]
        exact = [r for r in results if r.precision in ("house", "house_spread")]
        if len(exact) == 1:
            return exact[0]
        return Located(None, None, "ambiguous", 0.0, " | ".join(found))

    def _locate_on(self, key: str, house: str, hint: frozenset[str]) -> Located:
        score = 100.0
        group = self.by_street[key]
        if hint:
            inside = group[group["district"].isin(hint)]
            if len(inside):
                group = inside
        house_key = norm_house(house)
        exact = group[group["house_key"] == house_key]
        if house_key and len(exact):
            spread = spread_m(exact)
            if spread > SPREAD_WIDE_M:
                return Located(None, None, "ambiguous", score, key)
            return Located(
                float(exact["lon"].mean()),
                float(exact["lat"].mean()),
                "house" if spread <= SPREAD_LIMIT_M else "house_spread",
                score,
                key,
            )
        base = house_base(house_key)
        if base is not None:
            bases = group["house_key"].map(house_base)
            same = group[bases == base]
            if len(same) and spread_m(same) <= SPREAD_LIMIT_M:
                return Located(
                    float(same["lon"].mean()), float(same["lat"].mean()), "house_base", score, key
                )
            valid = bases.dropna()
            if len(valid) and not len(same):
                nearest = (valid - base).abs().sort_values().index[:2]
                near = group.loc[nearest]
                gap = float((valid.loc[nearest] - base).abs().max())
                if gap <= 4 and spread_m(near) <= 2 * SPREAD_LIMIT_M:
                    return Located(
                        float(near["lon"].mean()),
                        float(near["lat"].mean()),
                        "neighbour",
                        score,
                        key,
                    )
        return Located(None, None, "street", score, key)


def load_gazetteer() -> Gazetteer:
    addresses = pd.read_parquet(RAW / "osm" / "addresses.parquet")
    districts = gpd.read_file(PROCESSED / "districts.gpkg", layer="districts")
    points = gpd.GeoDataFrame(
        addresses[["osm_ref"]],
        geometry=gpd.points_from_xy(addresses["lon"], addresses["lat"]),
        crs=CRS_GEO,
    )
    joined = gpd.sjoin(points, districts[["name_en", "geometry"]], how="left", predicate="within")
    addresses["district"] = joined.loc[~joined.index.duplicated(), "name_en"].to_numpy()
    streets_path = RAW / "osm" / "streets.parquet"
    aliases = street_aliases(pd.read_parquet(streets_path)) if streets_path.exists() else {}
    return Gazetteer(addresses, aliases)


def geocode_frame(frame: pd.DataFrame, column: str = "address") -> pd.DataFrame:
    gazetteer = load_gazetteer()
    rows = []
    for address in frame[column]:
        street, house = split_address(address)
        located = gazetteer.locate(street, house, district_hint(address))
        rows.append(
            {
                "parsed_street": street,
                "parsed_house": house,
                "lon": located.lon,
                "lat": located.lat,
                "precision": located.precision,
                "street_score": located.street_score,
                "matched_street": located.matched_street,
            }
        )
    out = pd.DataFrame(rows, index=frame.index)
    out["lon"] = out["lon"].astype(float)
    out["lat"] = out["lat"].astype(float)
    return pd.concat([frame, out], axis=1)

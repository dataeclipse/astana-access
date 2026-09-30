import re
from dataclasses import dataclass, field

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry import MultiPoint, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

from astana_access.config import CRS_GEO, CRS_METRIC, PROCESSED, RAW
from astana_access.inventory.addresses import (
    Gazetteer,
    load_gazetteer,
    norm_street,
    street_aliases,
    street_initials,
)

DECISION = RAW / "polling" / "decision_01-7_2026-02-18.txt"
DISTRICTS = {
    "Алматы": "Almaty",
    "Байқоңыр": "Baikonur",
    "Есиль": "Esil",
    "Нұра": "Nura",
    "Сарайшық": "Saraishyk",
    "Сарыарка": "Saryarka",
}
APPENDIX = re.compile(r'Избирательные участки района "([^"]+)" города Астаны')
STATION = re.compile(
    r"Избирательный участок №\s*(\d+)\s*\(центр\s*[–-]\s*(.*?)\)\s*Границ[аы]:\s*(.*?)"
    r"(?=Избирательный участок №|Приложение \d|$)",
    re.S,
)
TYPE = (
    r"улиц[аыеу]|проспект[ау]?|переулк[ау]|переулок|шоссе|трасс[аыеу]|бульвар[ау]?|"
    r"алле[яию]|тупик[ау]?|проезд[ау]?"
)
NOMINATIVE = (
    (re.compile(r"улиц"), "улица"),
    (re.compile(r"проспект"), "проспект"),
    (re.compile(r"переул"), "переулок"),
    (re.compile(r"шоссе"), "шоссе"),
    (re.compile(r"трасс"), "трасса"),
    (re.compile(r"бульвар"), "бульвар"),
    (re.compile(r"алле"), "улица"),
    (re.compile(r"тупик"), "тупик"),
    (re.compile(r"проезд"), "проезд"),
)
STOP = (
    r"(?=\s*,|\s*;|\s+до\s|\s+по\s|\s+от\s|\s+вдоль\s"
    r"|\s+и\s+(?:дом|исключая|включая|улиц|проспект|переулк)"
    r"|\s+включая|\s+исключая|\s*\.?\s*$)"
)
NUMBERS = r"([\dА-Яа-яA-Za-z/]+(?:\s*,\s*[\dА-Яа-яA-Za-z/]+)*)"
HOUSES_ON = re.compile(
    r"дом(?:а|ов|у|ом)?\s*№\s*" + NUMBERS + r"\s+по\s+(" + TYPE + r")\s+(.+?)" + STOP, re.I
)
STREET_HOUSES = re.compile(
    r"(" + TYPE + r")\s+(.+?),?\s+дом(?:а|ов)?\s*№\s*" + NUMBERS + r"(?=\s*,|\s*\.|\s*$)", re.I
)
CLAUSE = re.compile(
    r"(исключая|включая)\s+(.*?)"
    r"(?=\s*(?:,|и)\s*(?:исключая|включая)|,\s*(?:от|по|вдоль|до)\s|\s*\.?\s*$)",
    re.I | re.S,
)
FEATURE = re.compile(
    r"(?P<house>дом(?:а|ов|у|ом)?\s*№\s*"
    + NUMBERS
    + r"\s+по\s+(?P<htype>"
    + TYPE
    + r")\s+(?P<hname>(?!до\s|по\s|от\s).+?)"
    + STOP
    + r")|(?P<water>(?:русл\w+\s+|набережн\w+\s+)?(?:рек[аиу]|руч(?:ья|ью|ей|ьем)|канал[ау]?)"
    r"\s+(?P<wname>(?!до\s|по\s|от\s).+?)" + STOP + r")"
    r"|(?P<rail>железн\w+\s+дорог\w+|железнодорожн\w+\s+\w+)"
    r"|(?P<edge>границ\w+\s+город\w*)"
    r"|(?P<street>(?P<stype>" + TYPE + r")\s+(?P<sname>(?!до\s|по\s|от\s).+?)" + STOP + r")",
    re.I,
)
WALK = re.compile(r"(?:^|,\s*)(?:от|вдоль)\s|сторон[еы]\s", re.I)
WATER_NAMES = {"есил": "есил", "есиль": "есил", "сарыбулак": "сарыбулак", "акбулак": "акбулак"}
JOIN_LIMIT_M = 400.0
NATURAL_LIMIT_M = 800.0
LOCAL_RADIUS_M = 3000.0
NATURAL = ("water", "rail", "edge")
CLUSTER_M = 150.0
MAX_AREA_KM2 = 40.0


@dataclass
class Territory:
    number: int
    district: str
    centre: str
    bounds: str
    kind: str
    chain: list[tuple[str, str, str]] = field(default_factory=list)
    include: list[tuple[str, str]] = field(default_factory=list)
    exclude: list[tuple[str, str]] = field(default_factory=list)
    listed: list[tuple[str, str]] = field(default_factory=list)


def nominative(kind: str) -> str:
    lowered = kind.lower()
    for pattern, value in NOMINATIVE:
        if pattern.match(lowered):
            return value
    return "улица"


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace('"', " ")).strip(" ,.")


def split_numbers(numbers: str) -> list[str]:
    return [part.strip() for part in numbers.split(",") if part.strip()]


def houses_in(fragment: str) -> list[tuple[str, str]]:
    found = []
    for numbers, kind, name in HOUSES_ON.findall(fragment):
        street = f"{nominative(kind)} {clean_name(name)}"
        found.extend((street, number) for number in split_numbers(numbers))
    return found


def parse_bounds(number: int, district: str, centre: str, bounds: str) -> Territory:
    text = re.sub(r"\s+", " ", bounds.replace("иcключая", "исключая")).strip()
    text = text.replace("Керей, Жәнібек", "Керей Жәнібек")
    territory = Territory(number, district, centre, text, "walk" if WALK.search(text) else "list")
    if territory.kind == "list":
        for kind, name, numbers in STREET_HOUSES.findall(text):
            street = f"{nominative(kind)} {clean_name(name)}"
            territory.listed.extend((street, house) for house in split_numbers(numbers))
        body = CLAUSE.sub(" ", text)
        territory.listed.extend(pair for pair in houses_in(body) if pair not in territory.listed)
        for mode, content in CLAUSE.findall(text):
            target = territory.listed if mode.lower() == "включая" else territory.exclude
            target.extend(houses_in(content))
        if "в границах жилого массива" in text:
            territory.kind = "area"
        elif not territory.listed:
            territory.kind = "site"
        return territory
    for mode, content in CLAUSE.findall(text):
        target = territory.include if mode.lower() == "включая" else territory.exclude
        target.extend(houses_in(content))
    walk = CLAUSE.sub(" ", text)
    for match in FEATURE.finditer(walk):
        if match.group("house"):
            street = f"{nominative(match.group('htype'))} {clean_name(match.group('hname'))}"
            house = split_numbers(match.group(2))[0]
            item = ("house", street, house)
        elif match.group("water"):
            item = ("water", clean_name(match.group("wname")), "")
        elif match.group("rail"):
            item = ("rail", "", "")
        elif match.group("edge"):
            item = ("edge", "", "")
        else:
            street = f"{nominative(match.group('stype'))} {clean_name(match.group('sname'))}"
            item = ("street", street, "")
        if not territory.chain or territory.chain[-1] != item:
            territory.chain.append(item)
    return territory


def parse_decision() -> list[Territory]:
    text = DECISION.read_text(encoding="utf-8")
    marks = [(m.start(), DISTRICTS[m.group(1)]) for m in APPENDIX.finditer(text)]
    territories = []
    for index, (start, district) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(text)
        tail = text.find("Избирательные участки при представительствах", start)
        if 0 <= tail < end:
            end = tail
        for number, centre, bounds in STATION.findall(text[start:end]):
            territories.append(parse_bounds(int(number), district, centre.strip(), bounds))
    return territories


class LineIndex:
    def __init__(self) -> None:
        lines = gpd.read_file(RAW / "osm" / "lines.gpkg").to_crs(CRS_METRIC)
        streets = lines[lines["kind"] == "highway"].copy()
        for column in ("old_name_ru",):
            streets[column] = None
        centre = streets.geometry.centroid.to_crs(CRS_GEO)
        frame = pd.DataFrame(
            {
                "street": streets["name"].to_numpy(),
                "housenumber": None,
                "lon": centre.x.to_numpy(),
                "lat": centre.y.to_numpy(),
            }
        )
        self.matcher = Gazetteer(
            frame, street_aliases(pd.DataFrame(streets.drop(columns="geometry")))
        )
        keys = self.matcher.frame["street_key"]
        geometry = streets.geometry.reset_index(drop=True)
        self.streets = {
            key: unary_union(geometry[index].to_list())
            for key, index in keys.groupby(keys).groups.items()
        }
        water = lines[lines["kind"] == "waterway"]
        self.water: dict[str, BaseGeometry] = {}
        for name, group in water.groupby(
            water["name"].map(lambda v: norm_street(v).replace(" ", ""))
        ):
            self.water[name] = unary_union(group.geometry.to_list())
        self.rail = unary_union(lines[lines["kind"] == "railway"].geometry.to_list())
        city = gpd.read_file(RAW / "boundary" / "city.geojson").to_crs(CRS_METRIC)
        self.edge = city.union_all().boundary

    def street(self, name: str) -> BaseGeometry | None:
        found = self.matcher.candidates(norm_street(name), street_initials(name))
        if not found:
            return None
        return unary_union([self.streets[key] for key in found if key in self.streets])

    def waterway(self, name: str) -> BaseGeometry | None:
        key = norm_street(name).replace(" ", "")
        key = WATER_NAMES.get(key, key)
        for candidate, geometry in self.water.items():
            if key and (key in candidate or candidate in key):
                return geometry
        return None


def _cluster(points: list[Point]) -> list[Point]:
    clusters: list[list[Point]] = []
    for point in points:
        for cluster in clusters:
            if cluster[0].distance(point) <= CLUSTER_M:
                cluster.append(point)
                break
        else:
            clusters.append([point])
    return [MultiPoint(cluster).centroid for cluster in clusters]


def _candidates(a: tuple[str, BaseGeometry], b: tuple[str, BaseGeometry]) -> list[Point]:
    (kind_a, geom_a), (kind_b, geom_b) = a, b
    if isinstance(geom_a, Point):
        return [geom_a]
    if isinstance(geom_b, Point):
        return [geom_b]
    crossing = geom_a.intersection(geom_b)
    if not crossing.is_empty:
        parts = getattr(crossing, "geoms", [crossing])
        return _cluster([part.representative_point() for part in parts])
    near_a, near_b = nearest_points(geom_a, geom_b)
    natural = kind_a in NATURAL or kind_b in NATURAL
    if near_a.distance(near_b) > (NATURAL_LIMIT_M if natural else JOIN_LIMIT_M):
        return []
    if kind_a in NATURAL and kind_b not in NATURAL:
        return [near_a]
    if kind_b in NATURAL and kind_a not in NATURAL:
        return [near_b]
    return [Point((near_a.x + near_b.x) / 2, (near_a.y + near_b.y) / 2)]


def localise(items: list[tuple[str, BaseGeometry]]) -> list[tuple[str, BaseGeometry]]:
    crossings = []
    for (_, a), (_, b) in zip(items, items[1:] + items[:1], strict=True):
        if isinstance(a, Point):
            crossings.append(a)
        elif not isinstance(b, Point) and a.intersects(b):
            crossings.append(a.intersection(b).representative_point())
    if not crossings:
        return items
    xs = sorted(p.x for p in crossings)
    ys = sorted(p.y for p in crossings)
    reach = Point(xs[len(xs) // 2], ys[len(ys) // 2]).buffer(LOCAL_RADIUS_M)
    kept = []
    for kind, geometry in items:
        if isinstance(geometry, Point):
            if geometry.within(reach):
                kept.append((kind, geometry))
            continue
        clipped = geometry.intersection(reach)
        if not clipped.is_empty:
            kept.append((kind, clipped))
    return kept


def build_polygon(items: list[tuple[str, BaseGeometry]]) -> tuple[Polygon | None, int]:
    items = localise(items)
    if len(items) < 3:
        return None, 0
    options = [_candidates(a, b) for a, b in zip(items, items[1:] + items[:1], strict=True)]
    options = [option for option in options if option]
    if len(options) < 3:
        return None, len(options)
    anchor = MultiPoint([option[0] for option in options if len(option) == 1] or [options[0][0]])
    previous = anchor.centroid
    vertices: list[Point] = []
    for option in options:
        chosen = min(option, key=previous.distance)
        if all(vertex.distance(chosen) > 5 for vertex in vertices[-1:]):
            vertices.append(chosen)
        previous = chosen
    while len(vertices) >= 2 and vertices[0].distance(vertices[-1]) <= 5:
        vertices.pop()
    if len(vertices) < 3:
        return None, len(vertices)
    polygon = make_valid(Polygon([(p.x, p.y) for p in vertices]))
    if polygon.geom_type != "Polygon":
        parts = [g for g in getattr(polygon, "geoms", []) if g.geom_type == "Polygon"]
        if not parts:
            return None, len(vertices)
        polygon = max(parts, key=lambda g: g.area)
    if polygon.area / 1e6 > MAX_AREA_KM2:
        return None, len(vertices)
    return polygon, len(vertices)


def locate_houses(
    pairs: list[tuple[str, str]], gazetteer: Gazetteer, district: str
) -> list[Point | None]:
    hint = frozenset({district})
    points = []
    for street, house in pairs:
        found = gazetteer.locate(street, house, hint)
        points.append(Point(found.lon, found.lat) if found.precision == "house" else None)
    return points


def to_metric(points: list[Point | None]) -> list[Point]:
    kept = [p for p in points if p is not None]
    if not kept:
        return []
    return list(gpd.GeoSeries(kept, crs=CRS_GEO).to_crs(CRS_METRIC))


def build() -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    gazetteer = load_gazetteer()
    index = LineIndex()
    rows, houses = [], []
    for territory in parse_decision():
        record = {
            "number": territory.number,
            "district": territory.district,
            "kind": territory.kind,
            "centre": territory.centre,
            "features": len(territory.chain),
            "resolved": 0,
            "vertices": 0,
            "listed": len(territory.listed),
            "geometry": None,
        }
        for role, pairs in (
            ("listed", territory.listed),
            ("include", territory.include),
            ("exclude", territory.exclude),
        ):
            located = locate_houses(pairs, gazetteer, territory.district)
            for (street, house), point in zip(pairs, located, strict=True):
                houses.append(
                    {
                        "number": territory.number,
                        "role": role,
                        "street": street,
                        "house": house,
                        "lon": point.x if point else None,
                        "lat": point.y if point else None,
                    }
                )
        if territory.kind == "walk":
            items = []
            for kind, name, house in territory.chain:
                if kind == "street":
                    geometry = index.street(name)
                elif kind == "water":
                    geometry = index.waterway(name)
                elif kind == "rail":
                    geometry = index.rail
                elif kind == "edge":
                    geometry = index.edge
                else:
                    metric = to_metric(
                        locate_houses([(name, house)], gazetteer, territory.district)
                    )
                    geometry = metric[0] if metric else None
                if geometry is not None and not geometry.is_empty:
                    items.append((kind, geometry))
            record["resolved"] = len(items)
            if len(items) >= 3:
                record["geometry"], record["vertices"] = build_polygon(items)
        rows.append(record)
    stations = gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS_METRIC).to_crs(CRS_GEO)
    house_table = pd.DataFrame(houses)
    stations.to_file(PROCESSED / "polling.gpkg", layer="stations", driver="GPKG")
    house_table.to_csv(PROCESSED / "polling_houses.csv", index=False, encoding="utf-8-sig")
    return stations, house_table

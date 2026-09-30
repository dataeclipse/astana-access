import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from astana_access.population.model import OFFICIAL_2026, allocate, error_against_official
from astana_access.population.stations import build_polygon, parse_bounds

LIST_BOUNDS = (
    "проспект Абылай хана, дома № 2, 2А, 4/2, 4/4, 6/1, 6/2, 6/3, 6/4, 6/5, 12/2, 14/1, 14/2, "
    "улица Қажымұқана, дом № 15."
)
WALK_BOUNDS = (
    "от улицы Орынбор по четной стороне проспекта Мәңгілік Ел до дома № 38 по проспекту "
    "Мәңгілік Ел, от дома № 38 по проспекту Мәңгілік Ел до улицы Ә. Бөкейхана, от улицы "
    "Ә. Бөкейхана по четной стороне улицы Ә. Бөкейхана до улицы Орынбор, от улицы Орынбор "
    "до проспекта Мәңгілік Ел."
)
CLAUSE_BOUNDS = (
    "от улицы М. Дулатова по четной стороне улицы К. Байсейітовой до улицы М. Жәлела, по четной "
    "стороне улицы М. Жәлела до улицы Қарталы, по нечетной стороне улицы Қарталы до улицы "
    "М. Дулатова, исключая дома № 28, 28/1 по улице күйші Дина, включая дома № 2, 2А по "
    "переулку Қосбасар."
)
SITE_BOUNDS = "улица Манаса, № 17."
RIVER_BOUNDS = (
    "от улицы А. Бараева по нечетной стороне проспекта Республики до улицы Ғ. Қараша, по четной "
    "стороне улицы Ғ. Қараша до улицы Ә. Мәмбетова, от улицы Ә. Мәмбетова, по набережной реки "
    "Есиль до улицы А. Бараева."
)


def test_house_list_is_parsed() -> None:
    territory = parse_bounds(1, "Almaty", "", LIST_BOUNDS)
    assert territory.kind == "list"
    assert len(territory.listed) == 13
    assert territory.listed[0] == ("проспект Абылай хана", "2")
    assert territory.listed[-1] == ("улица Қажымұқана", "15")


def test_single_address_is_an_institution() -> None:
    assert parse_bounds(67, "Almaty", "", SITE_BOUNDS).kind == "site"


def test_walk_chain_keeps_order_and_house_anchor() -> None:
    territory = parse_bounds(182, "Esil", "", WALK_BOUNDS)
    assert territory.kind == "walk"
    assert territory.chain[:4] == [
        ("street", "улица Орынбор", ""),
        ("street", "проспект Мәңгілік Ел", ""),
        ("house", "проспект Мәңгілік Ел", "38"),
        ("street", "улица Ә. Бөкейхана", ""),
    ]


def test_include_and_exclude_clauses_leave_the_chain() -> None:
    territory = parse_bounds(366, "Saryarka", "", CLAUSE_BOUNDS)
    assert territory.exclude == [("улица күйші Дина", "28"), ("улица күйші Дина", "28/1")]
    assert territory.include == [("переулок Қосбасар", "2"), ("переулок Қосбасар", "2А")]
    names = [name for kind, name, _ in territory.chain if kind == "street"]
    assert "улица күйші Дина" not in names
    assert "переулок Қосбасар" not in names


def test_river_is_a_boundary_feature() -> None:
    territory = parse_bounds(315, "Saryarka", "", RIVER_BOUNDS)
    assert ("water", "Есиль", "") in territory.chain


def test_polygon_from_four_crossing_streets() -> None:
    south = LineString([(-100, 0), (1100, 0)])
    east = LineString([(1000, -100), (1000, 1100)])
    north = LineString([(1100, 1000), (-100, 1000)])
    west = LineString([(0, 1100), (0, -100)])
    items = [("street", line) for line in (south, east, north, west)]
    polygon, vertices = build_polygon(items)
    assert vertices == 4
    assert polygon.area == pytest.approx(1_000_000)


def test_polygon_uses_a_house_as_a_vertex() -> None:
    south = LineString([(-100, 0), (1100, 0)])
    east = LineString([(1000, -100), (1000, 1100)])
    west = LineString([(0, 1100), (0, -100)])
    items = [("street", south), ("street", east), ("house", Point(500, 800)), ("street", west)]
    polygon, _ = build_polygon(items)
    assert polygon is not None
    assert polygon.covers(Point(500, 400))


def test_allocation_preserves_official_totals() -> None:
    dwellings = pd.DataFrame(
        {
            "station": [1, 1, 2, 3, 3],
            "unit": ["Baikonur", "Baikonur", "Baikonur", "Esil", "Esil"],
            "weight": [100.0, 300.0, 50.0, 10.0, 30.0],
        }
    )
    for alpha in (0.0, 0.2, 1.0):
        population = allocate(dwellings, alpha)
        totals = population.groupby(dwellings["unit"]).sum()
        assert totals["Baikonur"] == pytest.approx(OFFICIAL_2026["Baikonur"])
        assert totals["Esil"] == pytest.approx(OFFICIAL_2026["Esil"])
    equal = allocate(dwellings, 0.0).groupby(dwellings["station"]).sum()
    assert equal[1] == pytest.approx(equal[2])


def test_perfect_prediction_has_zero_error() -> None:
    result = error_against_official(pd.Series(OFFICIAL_2026) * 3.0)
    assert result["mean_abs_error"] == pytest.approx(0.0)

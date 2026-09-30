import pandas as pd
import pytest

from astana_access.inventory.addresses import (
    Gazetteer,
    district_hint,
    norm_house,
    norm_street,
    split_address,
    street_aliases,
    street_initials,
)

OSM_ROWS = [
    ("Қарасай Батыр көшесі", "31/1", 71.389821, 51.198282, "Saryarka"),
    ("Мұхтар Әуезов көшесі", "43/2", 71.418863, 51.180786, "Saryarka"),
    ("улица Кокжиек", "4", 71.335059, 51.178369, "Saryarka"),
    ("Қайым Мұхамедханов көшесі", "28", 71.361266, 51.144012, "Nura"),
    ("Ұлы Дала даңғылы", "51", 71.431837, 51.095706, "Esil"),
    ("переулок Култегин", "3", 71.3731, 51.1379, "Nura"),
]
OSM_STREETS = [
    ("Қарасай Батыр көшесі", "улица Карасай батыра", None),
    ("Мұхтар Әуезов көшесі", "улица Мухтара Ауэзова", None),
    ("Әзілхан Нұршайықов көшесі", "улица Азильхана Нуршаихова", "улица Е 11"),
]


@pytest.fixture(scope="module")
def gazetteer() -> Gazetteer:
    addresses = pd.DataFrame(OSM_ROWS, columns=["street", "housenumber", "lon", "lat", "district"])
    streets = pd.DataFrame(OSM_STREETS, columns=["name", "name_ru", "old_name"])
    for column in ("name_kk", "alt_name", "old_name_ru"):
        streets[column] = None
    return Gazetteer(addresses, street_aliases(streets))


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Қарасай Батыр көшесі", "улица Батыр Карасай"),
        ("улица Е- 18", "Е 18"),
        ("проспект Тәуелсіздік", "пр. Тауельсыздык"),
        ("улица Кaйым Мyхaмедханова", "Қайым Мұхамедханов көшесі"),
        ("улица Торгай (Сарыарка)", "Торгай"),
    ],
)
def test_street_variants_share_key(left: str, right: str) -> None:
    assert norm_street(left) == norm_street(right)


def test_lane_is_kept_apart_from_street() -> None:
    assert norm_street("переулок Култегин") != norm_street("улица Култегин")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("дом 28a", "28а"), ("здание 34/1", "34/1"), ("№ 3/3", "3/3"), ("43 а", "43а")],
)
def test_house_normalisation(raw: str, expected: str) -> None:
    assert norm_house(raw) == expected


@pytest.mark.parametrize(
    ("address", "street", "house"),
    [
        ("город Астана, улица Карасай батыра, 31/1", "улица карасай батыра", "31/1"),
        ('Город Астана, район "Алматы", улица Петрова, 7/2', "улица петрова", "7/2"),
        ("город Нур-Султан, район Сарыарка, улица 187, дом 20/6", "улица 187", "20/6"),
        ("город Астана, улица Мустафина13/1 ВП 2", "улица мустафина", "13/1"),
        ("г. Астана, район Алматы, ул.Магжан Жумабаев дом 32\\10", "ул.магжан жумабаев", "32/10"),
        ("город Астана, проспект Республика 43 а ВП-4", "проспект республика", "43 а"),
    ],
)
def test_split_address(address: str, street: str, house: str) -> None:
    assert split_address(address) == (street, house)


def test_initials_are_extracted() -> None:
    assert street_initials("ул. Ч. Айтматова") == frozenset({"ч"})


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("город Астана, район Нура, улица Е 15", {"Nura"}),
        ("город Астана, район Есиль, улица Орынбор, 1", {"Esil", "Nura"}),
        ("Алматинский район, жилой массив Железнодорожный", {"Almaty", "Saraishyk", "Baikonur"}),
        ("город Астана, улица Шу, 36", set()),
    ],
)
def test_district_hint(address: str, expected: set[str]) -> None:
    assert set(district_hint(address)) == expected


def test_exact_house_is_located(gazetteer: Gazetteer) -> None:
    found = gazetteer.locate("улица Карасай батыра", "31/1")
    assert found.precision == "house"
    assert found.lon == pytest.approx(71.389821)


def test_surname_only_query_resolves(gazetteer: Gazetteer) -> None:
    assert gazetteer.locate("улица Ауезова", "43/2").precision == "house"


def test_former_street_code_resolves_to_current_name(gazetteer: Gazetteer) -> None:
    assert (
        gazetteer.aliases[norm_street("улица Е 11")]
        == gazetteer.aliases[norm_street("Әзілхан Нұршайықов көшесі")]
    )


def test_street_does_not_match_lane(gazetteer: Gazetteer) -> None:
    assert gazetteer.locate("улица Култегин", "3").precision == "none"


def test_unknown_house_is_not_guessed(gazetteer: Gazetteer) -> None:
    found = gazetteer.locate("улица Кокжиек", "40")
    assert found.precision == "street"
    assert found.lon is None

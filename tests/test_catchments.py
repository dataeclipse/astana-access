import pandas as pd

from astana_access.accessibility.official_catchments import weighted_median
from astana_access.ingest.catchments import parse


def items(text: str) -> list[tuple[str, str, str]]:
    return [(item.street, item.house, item.kind) for item in parse(text)]


def test_street_with_house_list() -> None:
    found = items("ул.Сауран 5, 5а, 12/1; пр.Кабанбай батыр 40, 42")
    assert ("ул. Сауран", "5", "house") in found
    assert ("ул. Сауран", "5а", "house") in found
    assert ("ул. Сауран", "12/1", "house") in found
    assert ("пр. Кабанбай батыр", "42", "house") in found


def test_initials_are_not_street_types() -> None:
    found = items("ул.Ш.Айманова 9, 11")
    assert ("ул. Ш.Айманова", "9", "house") in found


def test_ranges_whole_streets_and_settlements() -> None:
    found = items("ул.Берел 1- 31, ул.Щорса (все); ул.Герцена, Белякова; п.«Куйгенжар»")
    assert ("ул. Берел", "1-31", "range") in found
    assert ("ул. Белякова", "", "street") in found or ("Белякова", "", "street") in found
    assert ("Куйгенжар", "", "settlement") in found


def test_language_notes_are_dropped() -> None:
    found = items("ул.Конаева, 29 (классы с русским языком обучения в ШГ № 17); ул.Арай, 35а")
    assert all("класс" not in street.lower() for street, _, _ in found)
    assert ("ул. Арай", "35а", "house") in found


def test_weighted_median() -> None:
    values = pd.Series([100.0, 200.0, 900.0])
    weights = pd.Series([1.0, 1.0, 5.0])
    assert weighted_median(values, weights) == 900.0

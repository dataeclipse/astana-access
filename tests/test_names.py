import pytest

from astana_access.inventory.link import name_similarity
from astana_access.inventory.names import extract_number, kinds_compatible, normalize, parse


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Государственное учреждение 'Школа-гимназия №14' Управления образования", 14),
        ("№31 мектеп-гимназия", 31),
        ("ЖОББМ №103", 103),
        ("Школа № 34", 34),
        ("Средняя школа  № 49", 49),
        ("Назарбаев Интеллектуальная школа г. Астана", None),
        ("Товарищество с ограниченной ответственностью 'Alpamys school'", None),
    ],
)
def test_extract_number(text, expected):
    assert extract_number(normalize(text)) == expected


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Школа-гимназия №14", "gymnasium"),
        ("Школа-лицей №60", "lyceum"),
        ("№101 жалпы орта білім беретін мектеп", "general"),
        ("Вечерняя сменная школа №39", "evening"),
        ("Комплекс 'Детский сад-начальная школа №12'", "complex_kg"),
        ("Специальная школа-интернат №1", "special"),
        ("Профессиональный лицей №1", "college"),
        ("Назарбаев Интеллектуальная школа", "nis"),
        ("Республиканская физико-математическая школа", "rfmsh"),
        ("Spectrum International School", "international"),
    ],
)
def test_classify(text, kind):
    assert parse(text).kind == kind


def test_kazakh_letters_normalised():
    assert normalize("Қадыр Мырза Әлі") == "кадыр мырза али"


def test_general_family_compatible():
    assert kinds_compatible("general", "lyceum")
    assert kinds_compatible("gymnasium", "general")
    assert not kinds_compatible("college", "general")


def test_boilerplate_removed_from_tokens():
    tokens = parse("Товарищество с ограниченной ответственностью 'Astana Garden School'").tokens
    assert "товар" not in tokens
    assert "garde" in tokens


def test_subset_name_not_perfect_match():
    assert name_similarity("колле", "колле менед бизне", "kolle", "kolle mened bizne") < 0.8


def test_identical_names_match():
    assert name_similarity("курма", "курма", "kurma", "kurma") == 1.0

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from astana_access.config import CRS_METRIC
from astana_access.ingest.school_register import (
    bin_year,
    binom_key,
    building_years,
    district_of,
    link,
    school_number,
)
from astana_access.validation.register import crowding


def test_number_district_and_years_are_read() -> None:
    assert school_number("ГКП на ПХВ «Школа-гимназия № 74имени Мукагали Макатаева»") == 74
    assert school_number("ГКП на ПХВ «Школа-лицей 60» акимата города Астана") == 60
    assert np.isnan(school_number('КГУ Лицей-интернат "Білім-инновация"'))
    assert district_of("район Нұра") == "Nura"
    assert district_of("район Байқоңыр") == "Baikonur"
    assert building_years("1972, 2024") == [1972, 2024]
    assert bin_year("001040001753") == 2000
    assert bin_year("241240036495") == 2024
    assert bin_year("660740000020") == 1966


def test_binom_schools_are_linked_by_name() -> None:
    assert binom_key('ТОО "BINOM EDUCATION" Школа-лицей BINOM SCHOOL имени Абиша Кекилбаев') == (
        "кекил"
    )
    assert binom_key("Школа-лицей № 72") is None
    schools = gpd.GeoDataFrame(
        {
            "facility_id": ["sch1", "sch2"],
            "number": [74.0, np.nan],
            "name": ["Школа-гимназия №74", "Binom School им. А. Кекилбаева"],
        },
        geometry=[Point(0, 0), Point(1, 1)],
        crs=CRS_METRIC,
    )
    register = pd.DataFrame(
        {
            "section": ["state", "private", "state"],
            "number": [74.0, np.nan, 9.0],
            "binom": [None, "кекил", None],
        }
    )
    linked = link(register, schools)
    assert linked.iloc[:2].tolist() == ["sch1", "sch2"]
    assert pd.isna(linked.iloc[2])


def test_crowding_counts_pupils_beyond_two_shifts() -> None:
    register = pd.DataFrame(
        {
            "district": ["Nura", "Nura", "Esil"],
            "capacity": [1000.0, 1000.0, 500.0],
            "enrolment_2025": [2500.0, 1500.0, 500.0],
            "enrolment_2026": [2600.0, 1500.0, 550.0],
            "shifts": [2, 2, 1],
        }
    )
    result = crowding(register)
    assert result["pupils_beyond_two_shifts"] == pytest.approx(500.0)
    assert result["schools_beyond_two_shifts"] == 1
    assert result["by_district"]["Nura"]["pupils_per_place"] == pytest.approx(2.0)

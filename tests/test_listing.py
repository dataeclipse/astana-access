import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from astana_access.ingest import stat_ages
from astana_access.inventory.programme_list import locate
from astana_access.population.history import OFFICIAL_2023
from astana_access.population.model import OFFICIAL_2026
from astana_access.validation.listing import reweighted, school_number


def test_school_number_from_listing_name() -> None:
    assert school_number("Комфортная средняя школа №105") == 105
    assert school_number("Комфортная средняя школа № 115") == 115
    assert np.isnan(school_number("Alpamys school"))


def test_listed_point_is_projected() -> None:
    row = pd.Series({"locate": "point", "lon": 71.340137, "lat": 51.202279})
    point, method, gap = locate(row, None, None, None)
    assert method == "listed_point"
    assert gap == 0.0
    assert isinstance(point, Point)
    assert 600_000 < point.x < 700_000


def test_reweighting_keeps_station_totals() -> None:
    dwellings = pd.DataFrame(
        {
            "id": ["a", "b", "c"],
            "station": ["s1", "s1", "s2"],
            "floors": [5.0, 5.0, 9.0],
            "pop_station": [100.0, 100.0, 50.0],
        }
    )
    factor = reweighted(dwellings, pd.Series({"a": 15.0}))
    population = dwellings.set_index("id")["pop_station"] * factor
    assert population["a"] == pytest.approx(150.0)
    assert population["b"] == pytest.approx(50.0)
    assert population["c"] == pytest.approx(50.0)


def test_official_ages_match_model_constants() -> None:
    if not stat_ages.SOURCE.exists():
        pytest.skip("statistics file not present")
    table = stat_ages.load()
    assert stat_ages.totals(2026, table) == OFFICIAL_2026
    assert stat_ages.totals(2023, table) == OFFICIAL_2023
    shares = stat_ages.cohort_shares(2026, table)
    assert shares.loc["City", "preschool"] == pytest.approx(0.1264, abs=1e-3)
    assert shares.loc["City", "school"] == pytest.approx(0.1897, abs=1e-3)


def test_sheet_parsing_skips_empty_year() -> None:
    header = [None] * 6 + [("Возраст", 2009, 2010, "Возраст", 2009, 2010)]
    rows = header + [("Всего", None, 120, "Всего", None, 60), (0, None, 7, 0, None, 3)]
    records = stat_ages.parse_sheet(rows)
    assert records == [("Всего", 2010, 120), (0, 2010, 7)]

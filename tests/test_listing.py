import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from astana_access.inventory.programme_list import locate
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

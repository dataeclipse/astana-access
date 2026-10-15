import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from astana_access.config import CRS_METRIC
from astana_access.optimization.plan import TABLE, by_district, locate, reach_sum


def test_plan_table_matches_official_totals() -> None:
    table = pd.read_csv(TABLE)
    assert len(table) == 25
    assert table["plan_id"].is_unique
    assert table.groupby("year").size().to_dict() == {2026: 4, 2027: 12, 2028: 9}
    assert table.groupby("year")["seats"].sum().to_dict() == {2026: 8150, 2027: 29566, 2028: 32600}
    assert set(table["kind"]) == {"new", "extension", "rebuild"}


def test_locate_point_school_and_unresolved() -> None:
    schools = gpd.GeoDataFrame(
        {"number": [15.0], "facility_id": ["sch1"]},
        geometry=[Point(700_000, 5_670_000)],
        crs=CRS_METRIC,
    )
    school = locate(pd.Series({"locate": "school", "school_number": 15}), None, None, schools)
    assert school.equals(Point(700_000, 5_670_000))
    point = locate(pd.Series({"locate": "point", "lon": 71.43, "lat": 51.04}), None, None, schools)
    assert 600_000 < point.x < 800_000
    assert locate(pd.Series({"locate": "unresolved"}), None, None, schools) is None


def test_reach_sum_and_district_totals() -> None:
    reach = pd.DataFrame({"facility_id": ["a", "a", "b"], "point_id": ["p1", "p2", "p2"]})
    values = pd.Series({"p1": 10.0, "p2": 5.0})
    summed = reach_sum(reach, values, pd.Index(["a", "b", "c"]))
    assert summed.to_dict() == pytest.approx({"a": 15.0, "b": 5.0, "c": 0.0})
    district = pd.Series({"p1": "Nura", "p2": "Esil"})
    assert by_district(values, district) == {"Esil": 5.0, "Nura": 10.0}


def test_seats_are_read_from_detailed_plan_purpose() -> None:
    from astana_access.optimization.detailed_plans import seats

    assert seats("Общеобразовательная школа на 2000 обучающихся") == 2000
    assert seats("Общеобразовательная школа на 1200 уч-ся") == 1200
    assert seats("Образовательная школа на 2300 учащихся") == 2300
    assert np.isnan(seats("Школа"))

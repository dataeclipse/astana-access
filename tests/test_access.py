import numpy as np
import pandas as pd
import pytest

from astana_access.accessibility.e2sfca import facility_ratio, gaussian, index, linear, step
from astana_access.equity.inequality import gini, theil

OD = pd.DataFrame(
    {
        "facility_id": ["s1", "s1", "s2", "s2", "s2"],
        "point_id": ["a", "b", "b", "c", "d"],
        "distance_m": [100.0, 900.0, 200.0, 400.0, 2500.0],
    }
)
DEMAND = pd.Series({"a": 100.0, "b": 50.0, "c": 50.0, "d": 30.0})
SUPPLY = pd.Series({"s1": 120.0, "s2": 60.0})


def test_decay_functions_are_one_at_zero_and_zero_beyond_catchment() -> None:
    distance = np.array([0.0, 1000.0, 1001.0])
    for function in (gaussian, linear, step):
        weights = function(distance, 1000.0)
        assert weights[0] == pytest.approx(1.0)
        assert weights[2] == 0.0
    assert gaussian(np.array([1000.0]), 1000.0)[0] == pytest.approx(0.0)


def test_allocation_counts_each_child_once() -> None:
    ratio = facility_ratio(OD, DEMAND, SUPPLY, "step", 1000.0)
    load = SUPPLY / ratio
    assert load.sum() == pytest.approx(DEMAND[["a", "b", "c"]].sum())


def test_children_beyond_allocation_radius_load_nothing() -> None:
    ratio = facility_ratio(OD, DEMAND, SUPPLY, "step", 1000.0)
    assert SUPPLY["s2"] / ratio["s2"] == pytest.approx(75.0)


def test_point_without_facility_in_catchment_has_zero_access() -> None:
    access = index(OD, DEMAND, SUPPLY, "step", 1000.0)
    assert "d" not in access.index or access["d"] == 0.0
    assert access["a"] > 0


def test_excluded_facility_is_ignored() -> None:
    access = index(OD, DEMAND, SUPPLY, "step", 1000.0, exclude=frozenset({"s2"}))
    assert "c" not in access.index


def test_gini_extremes() -> None:
    weights = np.ones(4)
    assert gini(np.array([5.0, 5.0, 5.0, 5.0]), weights) == pytest.approx(0.0)
    assert gini(np.array([0.0, 0.0, 0.0, 8.0]), weights) == pytest.approx(0.75)


def test_gini_respects_weights() -> None:
    values = np.array([1.0, 3.0])
    assert gini(values, np.array([1.0, 1.0])) == pytest.approx(
        gini(np.array([1.0, 1.0, 3.0, 3.0]), np.ones(4))
    )


def test_theil_decomposes_exactly() -> None:
    rng = np.random.default_rng(1)
    values = rng.gamma(2.0, 2.0, 200)
    weights = rng.uniform(1, 5, 200)
    groups = np.repeat(np.array(["a", "b", "c", "d"]), 50)
    result = theil(values, weights, groups)
    assert result["between"] + result["within"] == pytest.approx(result["theil"])
    assert 0 <= result["between_share"] <= 1

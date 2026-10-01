import numpy as np
import pandas as pd
import pytest
from rasterio.transform import from_origin

from astana_access import norms
from astana_access.optimization.backtest import solve
from astana_access.optimization.land import plot_sites
from astana_access.optimization.realistic import capacitated


def test_school_plot_follows_standard_bands() -> None:
    assert norms.school_land_m2(250) == pytest.approx(250 * 43)
    assert norms.school_land_m2(1000) == pytest.approx(1000 * 19)
    assert norms.school_land_m2(2000) == pytest.approx(38_000)


def test_norm_radii() -> None:
    assert norms.RADIUS_M == {"preschool": 300.0, "school": 500.0}


def test_plot_found_only_where_clearance_is_enough() -> None:
    clearance = np.zeros((50, 50), dtype="float32")
    clearance[10, 10] = 120.0
    transform = from_origin(0, 500, 10, 10)
    centres = np.array([[100.0, 400.0], [450.0, 50.0]])
    sites, distance = plot_sites(centres, clearance, transform, 110.0, 50.0)
    assert np.isfinite(distance[0])
    assert sites[0] == pytest.approx([105.0, 395.0])
    assert not np.isfinite(distance[1])


GAIN = pd.DataFrame(
    {
        "facility_id": ["a", "a", "b", "c", "c"],
        "point_id": ["p1", "p2", "p2", "p3", "p4"],
    }
)
WEIGHT = pd.Series({"p1": 10.0, "p2": 50.0, "p3": 30.0, "p4": 25.0})


def test_maximal_covering_picks_best_pair() -> None:
    chosen, value = solve(GAIN, WEIGHT, 2)
    assert set(chosen) == {"a", "c"}
    assert value == pytest.approx(115.0)


def test_capacity_limits_coverage() -> None:
    pairs = pd.DataFrame(
        {"unit": ["u1", "u2", "u2"], "facility_id": ["a", "a", "b"], "reach": [100.0, 80.0, 80.0]}
    )
    units = pd.Series({"u1": 100.0, "u2": 80.0})
    _, free = capacitated(pairs, units, 1, 1e9)
    _, limited = capacitated(pairs, units, 1, 120.0)
    assert free == pytest.approx(180.0)
    assert limited == pytest.approx(120.0)

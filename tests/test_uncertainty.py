import numpy as np
import pandas as pd
import pytest

from astana_access.accessibility.e2sfca import index
from astana_access.population import model
from astana_access.validation.uncertainty import FastIndex, allocate, band, district_relative

OD = pd.DataFrame(
    {
        "facility_id": ["s1", "s1", "s2", "s2", "s2", "s3"],
        "point_id": ["a", "b", "b", "c", "d", "d"],
        "distance_m": [100.0, 900.0, 200.0, 400.0, 2500.0, 1200.0],
    }
)
DEMAND = pd.Series({"a": 100.0, "b": 50.0, "c": 50.0, "d": 30.0})
SUPPLY = pd.Series({"s1": 120.0, "s2": 60.0})
DWELLINGS = pd.DataFrame(
    {
        "station": ["p1", "p1", "p2", "p3", "p3", "p4"],
        "unit": ["Esil", "Esil", "Esil", "Nura", "Nura", "Nura"],
        "weight": [100.0, 300.0, 50.0, 200.0, 200.0, 25.0],
    }
)


def test_fast_index_matches_reference_index() -> None:
    points = pd.Index(["a", "b", "c", "d"])
    fast = FastIndex(OD, points, SUPPLY, 1500.0, 3000.0)(DEMAND.reindex(points).to_numpy())
    reference = index(OD, DEMAND, SUPPLY, "gaussian", 1500.0, 3000.0).reindex(points).fillna(0)
    assert fast == pytest.approx(reference.to_numpy())


def test_allocation_without_noise_matches_population_model() -> None:
    reference = model.allocate(DWELLINGS, 0.2)
    result = allocate(DWELLINGS, DWELLINGS["weight"].to_numpy(), 0.2, None)
    assert result == pytest.approx(reference.to_numpy())


def test_noisy_allocation_keeps_official_district_totals() -> None:
    noise = np.random.default_rng(0).lognormal(0.0, 0.8, 4)
    result = allocate(DWELLINGS, DWELLINGS["weight"].to_numpy(), 0.1, noise)
    totals = pd.Series(result).groupby(DWELLINGS["unit"]).sum()
    assert totals["Esil"] == pytest.approx(model.OFFICIAL_2026["Esil"])
    assert totals["Nura"] == pytest.approx(model.OFFICIAL_2026["Nura"])


def test_district_relative_ignores_points_without_district() -> None:
    access = np.array([1.0, 3.0, 100.0])
    demand = np.array([1.0, 1.0, 5.0])
    relative = district_relative(access, demand, np.array(["Esil", "Nura", "none"]))
    assert relative == pytest.approx({"Esil": 0.5, "Nura": 1.5})


def test_band_reports_quantiles_in_order() -> None:
    result = band(list(range(101)))
    assert result["q05"] == pytest.approx(5.0)
    assert result["q50"] == pytest.approx(50.0)
    assert result["q95"] == pytest.approx(95.0)


def test_projection_ages_cohorts_and_applies_change_ratios() -> None:
    from astana_access.population.projection import LOW, project

    index = []
    values = []
    for year, shift in ((2024, 0), (2026, 0)):
        for age in range(LOW - 2, LOW + 12):
            index.append(("Nura", year, age))
            values.append(100.0 if year == 2024 else 150.0 + shift)
    people = pd.Series(
        values, index=pd.MultiIndex.from_tuples(index, names=["group", "year", "age"])
    )
    row = project(people).loc["Nura"]
    assert row["ageing_factor"] == pytest.approx(1.0)
    assert row["cohort_factor"] == pytest.approx(1.5)


def test_demography_step_ages_cohorts_and_keeps_infant_ratio() -> None:
    from astana_access.population.demography import OLDEST, infant_ratio, step

    now = np.full(OLDEST + 1, 100.0)
    nxt = step(now, np.ones(OLDEST + 1), infant_ratio(now))
    assert nxt[10] == pytest.approx(100.0)
    assert infant_ratio(nxt) == pytest.approx(infant_ratio(now))
    assert nxt[OLDEST] == pytest.approx(300.0)


def test_demography_ratios_are_bounded() -> None:
    from astana_access.population.demography import OLDEST, RATIO_BOUNDS, ratios

    start = np.full(OLDEST + 1, 10.0)
    end = np.full(OLDEST + 1, 1000.0)
    assert ratios(start, end)[20] == pytest.approx(RATIO_BOUNDS[1])


def test_demography_districts_add_up_to_the_city() -> None:
    from astana_access.population.demography import OLDEST, cohorts, controlled

    city = {2028: np.full(OLDEST + 1, 30.0)}
    districts = {
        "a": {2028: np.full(OLDEST + 1, 1.0)},
        "b": {2028: np.full(OLDEST + 1, 2.0)},
    }
    joint = controlled(city, districts)
    for name, value in cohorts(city[2028]).items():
        assert joint["a"][2028][name] + joint["b"][2028][name] == pytest.approx(value)
    assert joint["b"][2028]["total"] == pytest.approx(2 * joint["a"][2028]["total"])

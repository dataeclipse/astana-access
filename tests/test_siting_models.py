import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from astana_access.config import CRS_METRIC
from astana_access.modeling.siting import area_share, label_nearest, matrix
from astana_access.population.housing import evaluate, ring_sum, share_in_cells


def test_area_share_counts_polygon_inside_ring() -> None:
    centres = gpd.GeoSeries([Point(0, 0), Point(5000, 0)], crs=CRS_METRIC, index=["a", "b"])
    polygons = gpd.GeoDataFrame(
        {"value": ["construction"]}, geometry=[box(-100, -100, 100, 100)], crs=CRS_METRIC
    )
    share = area_share(centres, polygons, "construction")
    assert share[0] == pytest.approx(40000 / (np.pi * 500**2), rel=1e-3)
    assert share[1] == 0.0


def test_label_nearest_marks_one_cell_per_site() -> None:
    frame = gpd.GeoDataFrame(
        {"h3": ["x", "y", "z"]},
        geometry=[Point(0, 0), Point(1000, 0), Point(2000, 0)],
        crs=CRS_METRIC,
        index=["c1", "c2", "c3"],
    )
    sites = gpd.GeoDataFrame(geometry=[Point(950, 10), Point(2100, 0)], crs=CRS_METRIC)
    assert label_nearest(frame, sites).tolist() == [0, 1, 1]


def test_matrix_logs_count_features_only() -> None:
    from astana_access.modeling.siting import FEATURES

    row = {feature: 9.0 for feature in FEATURES}
    values = matrix(pd.DataFrame([row]))[0]
    logged = FEATURES.index("deficit_1000")
    plain = FEATURES.index("centre_m")
    assert values[logged] == pytest.approx(np.log(10.0))
    assert values[plain] == pytest.approx(9.0)


def test_ring_sum_excludes_the_cell_itself() -> None:
    centre = h3.latlng_to_cell(51.13, 71.43, 9)
    neighbour = next(cell for cell in h3.grid_disk(centre, 1) if cell != centre)
    values = pd.Series({centre: 5.0, neighbour: 2.0})
    result = ring_sum(values, 1)
    assert result[centre] == pytest.approx(2.0)
    assert result[neighbour] == pytest.approx(5.0)


def test_share_in_cells_is_clipped_area_share() -> None:
    cells = gpd.GeoDataFrame(
        {"h3": ["a", "b"]}, geometry=[box(0, 0, 100, 100), box(200, 0, 300, 100)], crs=CRS_METRIC
    )
    polygons = gpd.GeoDataFrame(geometry=[box(50, 0, 150, 100)], crs=CRS_METRIC)
    share = share_in_cells(cells, polygons)
    assert share.tolist() == pytest.approx([0.5, 0.0])


def test_evaluate_rewards_perfect_ranking() -> None:
    actual = np.array([0.0] * 18 + [5000.0, 3000.0])
    perfect = evaluate(actual, actual)
    assert perfect["roc_auc_any_new"] == pytest.approx(1.0)
    assert perfect["top_decile_capture"] == pytest.approx(1.0)


def test_two_objective_greedy_follows_the_weight() -> None:
    from astana_access.optimization.two_objective import greedy

    deficit = np.array([100.0, 0.0, 0.0])
    relief = np.array([0.0, 50.0, 0.0])
    lists = {
        "a": (np.array([0]), np.array([], dtype=int)),
        "b": (np.array([], dtype=int), np.array([1])),
    }
    caps = {"a": 1e9, "b": 1e9}
    assert greedy(lists, deficit, relief, caps, 1.0, (1.0, 1.0), 1)[0]["id"] == "a"
    assert greedy(lists, deficit, relief, caps, 0.0, (1.0, 1.0), 1)[0]["id"] == "b"


def test_two_objective_totals_cap_relief_and_count_children_once() -> None:
    from astana_access.optimization.two_objective import totals

    deficit = np.array([10.0, 20.0])
    relief = np.array([300.0, 300.0])
    lists = {"a": (np.array([0, 1]), np.array([0, 1])), "b": (np.array([1]), np.array([1]))}
    covered, relieved = totals(["a", "b"], lists, deficit, relief, {"a": 400.0, "b": 400.0})
    assert covered == pytest.approx(30.0)
    assert relieved == pytest.approx(400.0)

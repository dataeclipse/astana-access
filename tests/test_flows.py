import numpy as np
import pandas as pd

from astana_access.accessibility.flows import (
    Flows,
    fit_beta,
    mass_on_official,
    official_rows,
    per_dwelling,
    weights,
)

OD = pd.DataFrame(
    {
        "point_id": ["a", "a", "b", "b", "b", "c", "c"],
        "facility_id": ["s1", "s2", "s1", "s2", "s3", "s2", "s3"],
        "distance_m": [200.0, 900.0, 500.0, 300.0, 1200.0, 400.0, 800.0],
    }
)
CHILDREN = pd.Series({"a": 40.0, "b": 100.0, "c": 60.0, "z": 25.0})
ENROLMENT = pd.Series({"s1": 50.0, "s2": 90.0, "s3": 40.0})


def test_every_school_receives_its_enrolment() -> None:
    model = Flows(OD, CHILDREN, ENROLMENT)
    flows = model.frame(0.5)
    assert (flows["children"] >= 0).all()
    by_school = flows.groupby("facility_id")["children"].sum()
    assert np.allclose(by_school.reindex(ENROLMENT.index), ENROLMENT)


def test_origins_without_a_school_in_reach_are_left_out() -> None:
    model = Flows(OD, CHILDREN, ENROLMENT)
    assert "z" not in set(model.frame(0.5)["point_id"])
    balance = model.balance(0.5)
    assert balance["children_reachable"] == 200.0
    assert abs(balance["state_share"] - 180.0 / 200.0) < 1e-12


def test_a_school_draws_in_proportion_to_children_and_decay() -> None:
    model = Flows(OD, CHILDREN, ENROLMENT)
    flows = model.frame(0.4).set_index(["point_id", "facility_id"])["children"]
    ratio = flows[("a", "s1")] / flows[("b", "s1")]
    expected = (40.0 * weights(200.0, 0.4)) / (100.0 * weights(500.0, 0.4))
    assert abs(ratio - expected) < 1e-12


def test_beta_is_recovered_from_simulated_choices() -> None:
    rng = np.random.default_rng(7)
    true_beta = 0.6
    rows = []
    for n in range(3000):
        distance = rng.uniform(200.0, 3000.0, size=4)
        p = weights(distance, true_beta)
        chosen = rng.choice(4, p=p / p.sum())
        for k in range(4):
            rows.append((f"p{n}", f"s{k}", distance[k], k == chosen))
    table = pd.DataFrame(rows, columns=["point_id", "facility_id", "distance_m", "official"])
    table["code"] = pd.factorize(table["point_id"])[0]
    estimate = fit_beta(lambda beta: mass_on_official(table, weights(table["distance_m"], beta)))
    assert abs(estimate - true_beta) / true_beta < 0.15


def test_official_rows_drop_dwellings_whose_school_is_out_of_reach() -> None:
    pairs = pd.DataFrame({"point_id": ["a", "b"], "facility_id": ["s1", "s9"]})
    rows = official_rows(OD, pairs)
    assert set(rows["point_id"]) == {"a"}
    assert rows.loc[rows["facility_id"] == "s1", "official"].all()


def test_agreement_counts_the_nearest_school_as_first() -> None:
    rows = official_rows(OD, pd.DataFrame({"point_id": ["a", "b"], "facility_id": ["s1", "s3"]}))
    nearest = rows.groupby("point_id")["distance_m"].transform("min")
    table = per_dwelling(rows, np.where(rows["distance_m"] == nearest, 1.0, 1e-9))
    assert table.loc["a", "top1"] == 1.0
    assert table.loc["b", "top1"] == 0.0
    assert table.loc["b", "top3"] == 1.0


def test_mass_on_official_is_a_share_of_each_dwelling() -> None:
    rows = official_rows(OD, pd.DataFrame({"point_id": ["a"], "facility_id": ["s1"]}))
    mass = mass_on_official(rows, np.array([3.0, 1.0]))
    assert abs(mass[0] - 0.75) < 1e-12

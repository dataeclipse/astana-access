import geopandas as gpd
import numpy as np
import pandas as pd

from astana_access.accessibility.coverage import facilities
from astana_access.config import PROCESSED

PRESCHOOL_CLASS_MEAN = {"state": 29_429 / 148, "private": 36_973 / 642}


def gaussian(distance: np.ndarray, d0: float) -> np.ndarray:
    weight = (np.exp(-0.5 * (distance / d0) ** 2) - np.exp(-0.5)) / (1 - np.exp(-0.5))
    return np.where(distance <= d0, weight, 0.0)


def step(distance: np.ndarray, d0: float) -> np.ndarray:
    return np.where(distance <= d0, 1.0, 0.0)


def linear(distance: np.ndarray, d0: float) -> np.ndarray:
    return np.where(distance <= d0, 1.0 - distance / d0, 0.0)


DECAY = {"gaussian": gaussian, "step": step, "linear": linear}


def design_capacity(floor: pd.Series) -> pd.Series:
    from astana_access.ingest import school_register

    if not school_register.SOURCE.exists():
        return floor
    register = school_register.linked().dropna(subset=["facility_id", "capacity"])
    capacity = register.groupby("facility_id")["capacity"].sum().reindex(floor.index)
    per_floor = (capacity / floor).median()
    return capacity.fillna(floor * per_floor)


def preschool_capacity(preschools: pd.DataFrame, class_mean: pd.Series) -> pd.Series:
    from astana_access.ingest import preschool_capacity as cards

    if not cards.SOURCE.exists():
        return class_mean
    by_id = cards.capacity_by_id()
    ids = pd.to_numeric(preschools["indigo_id"], errors="coerce")
    capacity = ids.map(by_id)
    typical = capacity.groupby(preschools["ownership"]).transform("median")
    return capacity.fillna(typical).fillna(class_mean).astype(float)


def supply_measures() -> dict[str, dict[str, pd.Series]]:
    sites = facilities()
    schools = sites["school"].set_index("facility_id")
    floor = schools["floor_m2"].astype(float)
    floor = floor.fillna(floor[~schools["presumed_new"].astype(bool)].median())
    preschools = sites["preschool"].set_index("facility_id")
    class_mean = preschools["ownership"].map(PRESCHOOL_CLASS_MEAN).astype(float)
    return {
        "school": {
            "capacity": design_capacity(floor),
            "floor_area": floor,
            "equal": pd.Series(1.0, index=schools.index),
        },
        "preschool": {
            "capacity": preschool_capacity(preschools, class_mean),
            "class_mean": class_mean,
            "equal": pd.Series(1.0, index=preschools.index),
        },
    }


def facility_ratio(
    od: pd.DataFrame,
    demand: pd.Series,
    supply: pd.Series,
    decay: str,
    d0_load: float,
    exclude: frozenset[str] = frozenset(),
) -> pd.Series:
    table = od[(od["distance_m"] <= d0_load) & ~od["facility_id"].isin(exclude)]
    weight = DECAY[decay](table["distance_m"].to_numpy(dtype=float), d0_load)
    children = table["point_id"].map(demand).fillna(0.0).to_numpy()
    if d0_load > 0:
        nearest = table.groupby("point_id")["distance_m"].transform("min").to_numpy()
        share = (
            weight
            / pd.Series(weight)
            .groupby(table["point_id"].to_numpy())
            .transform("sum")
            .replace(0.0, np.nan)
            .fillna(1.0)
            .to_numpy()
        )
        children = children * np.where(nearest <= d0_load, share, 0.0)
    load = pd.Series(children).groupby(table["facility_id"].to_numpy()).sum()
    ratio = supply.reindex(load.index) / load.replace(0.0, np.nan)
    return ratio.reindex(supply.index).fillna(0.0)


def index(
    od: pd.DataFrame,
    demand: pd.Series,
    supply: pd.Series,
    decay: str,
    d0: float,
    d0_load: float | None = None,
    exclude: frozenset[str] = frozenset(),
) -> pd.Series:
    if d0_load is None:
        table = od[(od["distance_m"] <= d0) & ~od["facility_id"].isin(exclude)]
        weight = DECAY[decay](table["distance_m"].to_numpy(dtype=float), d0)
        children = table["point_id"].map(demand).fillna(0.0).to_numpy()
        load = pd.Series(children * weight).groupby(table["facility_id"].to_numpy()).sum()
        ratio = (supply.reindex(load.index) / load.replace(0.0, np.nan)).fillna(0.0)
    else:
        ratio = facility_ratio(od, demand, supply, decay, d0_load, exclude)
    table = od[(od["distance_m"] <= d0) & ~od["facility_id"].isin(exclude)]
    weight = DECAY[decay](table["distance_m"].to_numpy(dtype=float), d0)
    contribution = table["facility_id"].map(ratio).fillna(0.0).to_numpy() * weight
    return pd.Series(contribution).groupby(table["point_id"].to_numpy()).sum()


def load_inputs() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    points = pd.read_parquet(PROCESSED / "demand_points.parquet")
    grid = gpd.read_file(PROCESSED / "grid_population.gpkg")[["h3", "district"]]
    points = points.merge(grid, on="h3", how="left")
    od = {
        kind: pd.read_parquet(PROCESSED / f"od_walk_{kind}.parquet")
        for kind in ("school", "preschool")
    }
    return points, od

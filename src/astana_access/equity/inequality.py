import h3
import numpy as np
import pandas as pd


def gini(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    total = cumulative[-1]
    mean = np.sum(values * weights) / total
    if mean == 0:
        return 0.0
    lorenz = np.cumsum(values * weights) / (mean * total)
    previous = np.concatenate([[0.0], lorenz[:-1]])
    return float(1.0 - np.sum((weights / total) * (lorenz + previous)))


def theil(values: np.ndarray, weights: np.ndarray, groups: np.ndarray) -> dict[str, float]:
    total = weights.sum()
    mean = np.sum(values * weights) / total
    share = values / mean
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(share > 0, share * np.log(share), 0.0)
    overall = float(np.sum(weights * term) / total)
    frame = pd.DataFrame({"v": values, "w": weights, "g": groups, "t": term})
    between = 0.0
    within = 0.0
    for _, group in frame.groupby("g"):
        weight = group["w"].sum()
        group_mean = np.sum(group["v"] * group["w"]) / weight
        population_share = weight / total
        income_share = population_share * group_mean / mean
        if group_mean > 0:
            between += income_share * np.log(group_mean / mean)
            ratio = group["v"] / group_mean
            with np.errstate(divide="ignore", invalid="ignore"):
                inner = np.where(ratio > 0, ratio * np.log(ratio), 0.0)
            within += income_share * float(np.sum(group["w"] * inner) / weight)
    return {
        "theil": overall,
        "between": float(between),
        "within": float(within),
        "between_share": float(between / overall) if overall else 0.0,
    }


def neighbours(cells: list[str]) -> list[np.ndarray]:
    position = {cell: index for index, cell in enumerate(cells)}
    links = []
    for cell in cells:
        ring = [position[n] for n in h3.grid_ring(cell, 1) if n in position]
        links.append(np.array(ring, dtype=int))
    return links


def local_moran(
    values: np.ndarray, links: list[np.ndarray], permutations: int = 999, seed: int = 0
) -> pd.DataFrame:
    z = (values - values.mean()) / values.std()
    lag = np.array([z[link].mean() if len(link) else 0.0 for link in links])
    local = z * lag
    rng = np.random.default_rng(seed)
    count = np.zeros(len(z))
    pool = np.arange(len(z))
    for i, link in enumerate(links):
        k = len(link)
        if k == 0:
            count[i] = permutations
            continue
        others = np.delete(pool, i)
        draws = rng.choice(others, size=(permutations, k), replace=True)
        simulated = z[i] * z[draws].mean(axis=1)
        if local[i] >= 0:
            count[i] = np.sum(simulated >= local[i])
        else:
            count[i] = np.sum(simulated <= local[i])
    p = (count + 1) / (permutations + 1)
    quadrant = np.where(z >= 0, np.where(lag >= 0, "HH", "HL"), np.where(lag >= 0, "LH", "LL"))
    has = np.array([len(link) > 0 for link in links])
    global_i = float(np.sum(z[has] * lag[has]) / has.sum())
    result = pd.DataFrame({"local_i": local, "p": p, "quadrant": quadrant})
    result.attrs["global_i"] = global_i
    return result

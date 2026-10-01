import json

import geopandas as gpd
import matplotlib.patheffects as effects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D

from astana_access.config import CRS_METRIC, PROCESSED, REPORTS
from astana_access.viz import style

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID_GRAY = "#d9d8d4"
NEUTRAL = "#f0efec"
BLUE_RAMP = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
DIVERGING = LinearSegmentedColormap.from_list(
    "access", ["#c23b3a", "#e34948", NEUTRAL, "#3987e5", "#1c5cab"]
)
SEQUENTIAL = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
ORDER = ["Almaty", "Saraishyk", "Baikonur", "Saryarka", "Esil", "Nura"]


def districts() -> gpd.GeoDataFrame:
    return gpd.read_file(PROCESSED / "districts.gpkg", layer="districts").to_crs(CRS_METRIC)


def base_map(ax: plt.Axes, frame: gpd.GeoDataFrame) -> None:
    frame.boundary.plot(ax=ax, color=INK_SECONDARY, linewidth=0.6)
    for _, row in frame.iterrows():
        point = row.geometry.representative_point()
        ax.annotate(
            row["name_en"],
            (point.x, point.y),
            ha="center",
            fontsize=7,
            color=INK,
            path_effects=[effects.withStroke(linewidth=2.5, foreground="white")],
        )
    ax.set_axis_off()


def h1_district_error() -> None:
    model = json.loads((REPORTS / "population_model.json").read_text(encoding="utf-8"))
    fits = model["district_fit"]
    units = ["Almaty+Saraishyk", "Baikonur", "Esil", "Nura", "Saryarka"]
    series = {
        "WorldPop": fits["worldpop"],
        "Residential floor area": fits["floor_area"],
        "Polling stations, model": fits["stations_alpha_0.2"],
    }
    fig, ax = plt.subplots(figsize=(6.3, 3.2))
    width = 0.26
    y = np.arange(len(units))
    for i, (name, fit) in enumerate(series.items()):
        values = [fit[f"ratio_{unit}"] for unit in units]
        ax.barh(y + (i - 1) * width, values, height=width - 0.04, color=SERIES[i], label=name)
    ax.axvline(1.0, color=INK, linewidth=0.8)
    ax.set_yticks(y, [u.replace("+", " + ") for u in units])
    ax.invert_yaxis()
    ax.set_xlabel("Predicted over official population, 1 January 2026")
    ax.legend(loc="lower right")
    style.save(fig, "h1_district_error")
    plt.close(fig)


def compliance() -> None:
    table = pd.read_csv(REPORTS / "compliance.csv")
    base = table[(table["variant"] == "station") & (table["limit"] == "norm")]
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 3.0), sharey=True)
    for ax, kind, title in zip(
        axes,
        ("school", "preschool"),
        ("School within 500 m", "Preschool within 300 m"),
        strict=True,
    ):
        rows = ["city", *ORDER]
        straight = base[(base["kind"] == kind) & (base["measure"] == "straight_line")].set_index(
            "area"
        )["compliant_share"]
        walking = base[(base["kind"] == kind) & (base["measure"] == "network")].set_index("area")[
            "compliant_share"
        ]
        y = np.arange(len(rows))
        for i, area in enumerate(rows):
            ax.plot(
                [walking[area] * 100, straight[area] * 100],
                [i, i],
                color=GRID_GRAY,
                linewidth=2,
                zorder=1,
            )
        ax.scatter(
            walking.reindex(rows) * 100,
            y,
            s=36,
            color=SERIES[0],
            zorder=2,
            label="Walking distance",
            edgecolor="white",
            linewidth=1,
        )
        ax.scatter(
            straight.reindex(rows) * 100,
            y,
            s=36,
            color=SERIES[1],
            zorder=2,
            label="Straight line",
            edgecolor="white",
            linewidth=1,
        )
        ax.set_yticks(y, ["City", *ORDER])
        ax.set_xlim(0, 100)
        ax.set_title(title, loc="left")
        ax.set_xlabel("Share of children, %")
    axes[0].invert_yaxis()
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.06))
    style.save(fig, "compliance_by_district")
    plt.close(fig)


def frame_extent(ax: plt.Axes, frame: gpd.GeoDataFrame, margin: float = 800.0) -> None:
    centre = frame.geometry.centroid
    ax.set_xlim(centre.x.quantile(0.005) - margin, centre.x.quantile(0.995) + margin)
    ax.set_ylim(centre.y.quantile(0.005) - margin, centre.y.quantile(0.995) + margin)


def access_map(kind: str) -> None:
    cells = pd.read_parquet(PROCESSED / f"access_cells_{kind}.parquet")
    grid = gpd.read_file(PROCESSED / "grid_population.gpkg")[["h3", "geometry"]].set_index("h3")
    frame = gpd.GeoDataFrame(
        cells.join(grid, how="inner"), geometry="geometry", crs=grid.crs
    ).to_crs(CRS_METRIC)
    mean = np.average(frame["a"], weights=frame["w"])
    frame["relative"] = np.log2((frame["a"] / mean).clip(lower=0.25, upper=4.0))
    fig, ax = plt.subplots(figsize=(6.3, 6.0))
    norm = TwoSlopeNorm(vmin=-2, vcenter=0, vmax=2)
    frame.plot(ax=ax, column="relative", cmap=DIVERGING, norm=norm, linewidth=0)
    cold = frame[(frame["p"] < 0.05) & (frame["quadrant"] == "LL")]
    cold.dissolve().boundary.plot(ax=ax, color=INK, linewidth=0.7)
    base_map(ax, districts())
    frame_extent(ax, frame)
    mappable = plt.cm.ScalarMappable(norm=norm, cmap=DIVERGING)
    bar = fig.colorbar(mappable, ax=ax, shrink=0.6, pad=0.01, ticks=[-2, -1, 0, 1, 2])
    bar.ax.set_yticklabels(["1/4 or less", "1/2", "city mean", "2x", "4x or more"])
    bar.set_label("Accessibility per child, relative to city mean")
    ax.legend(
        handles=[Line2D([0], [0], color=INK, linewidth=0.7, label="Significant low-low cluster")],
        loc="upper right",
    )
    style.save(fig, f"access_map_{kind}")
    plt.close(fig)


def population_map() -> None:
    grid = gpd.read_file(PROCESSED / "grid_population.gpkg").to_crs(CRS_METRIC)
    grid = grid[grid["pop_station"] > 0].copy()
    grid["density"] = grid["pop_station"] / grid["area_km2"] / 1000
    fig, ax = plt.subplots(figsize=(6.3, 6.0))
    grid.plot(
        ax=ax,
        column="density",
        cmap=SEQUENTIAL,
        linewidth=0,
        vmax=float(grid["density"].quantile(0.98)),
    )
    base_map(ax, districts())
    frame_extent(ax, grid)
    mappable = plt.cm.ScalarMappable(
        norm=plt.Normalize(0, float(grid["density"].quantile(0.98))), cmap=SEQUENTIAL
    )
    bar = fig.colorbar(mappable, ax=ax, shrink=0.6, pad=0.01)
    bar.set_label("Residents per sq km, thousands")
    style.save(fig, "population_station_model")
    plt.close(fig)


def programme_map(radius: int = 1000) -> None:
    layers = PROCESSED / "backtest.gpkg"
    existing = gpd.read_file(layers, layer="existing_2023").to_crs(CRS_METRIC)
    programme = gpd.read_file(layers, layer="programme_2023").to_crs(CRS_METRIC)
    optimal = gpd.read_file(layers, layer=f"optimal_2023_{radius}").to_crs(CRS_METRIC)
    uncovered = pd.read_parquet(PROCESSED / f"uncovered_2023_{radius}.parquet")
    grid = gpd.read_file(PROCESSED / "grid_population.gpkg")[["h3", "geometry"]].set_index("h3")
    cells = gpd.GeoDataFrame(
        uncovered.join(grid, how="inner"), geometry="geometry", crs=grid.crs
    ).to_crs(CRS_METRIC)
    fig, ax = plt.subplots(figsize=(6.3, 6.0))
    cells.plot(
        ax=ax,
        column="children",
        cmap=SEQUENTIAL,
        linewidth=0,
        vmax=float(cells["children"].quantile(0.95)),
    )
    base_map(ax, districts())
    existing.plot(
        ax=ax, color=INK_SECONDARY, markersize=8, marker="o", label="State schools in 2023"
    )
    programme.plot(
        ax=ax,
        color=SERIES[1],
        markersize=36,
        marker="s",
        edgecolor="white",
        linewidth=0.8,
        label="Programme schools",
    )
    optimal.plot(
        ax=ax,
        color=SERIES[0],
        markersize=40,
        marker="^",
        edgecolor="white",
        linewidth=0.8,
        label="Optimal sites on free plots",
    )
    frame_extent(ax, cells, 1500.0)
    ax.legend(loc="lower left")
    mappable = plt.cm.ScalarMappable(
        norm=plt.Normalize(0, float(cells["children"].quantile(0.95))), cmap=SEQUENTIAL
    )
    bar = fig.colorbar(mappable, ax=ax, shrink=0.6, pad=0.01)
    bar.set_label(
        f"School-age children without a state school within {radius / 1000:g} km, per cell"
    )
    style.save(fig, f"programme_2023_{radius}")
    plt.close(fig)


def lorenz() -> None:
    reported = json.loads((REPORTS / "access_equity.json").read_text(encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(4.2, 4.0))
    for i, kind in enumerate(("school", "preschool")):
        cells = pd.read_parquet(PROCESSED / f"access_cells_{kind}.parquet")
        order = np.argsort(cells["a"].to_numpy())
        weight = cells["w"].to_numpy()[order]
        value = cells["a"].to_numpy()[order] * weight
        x = np.concatenate([[0], np.cumsum(weight) / weight.sum()])
        y = np.concatenate([[0], np.cumsum(value) / value.sum()])
        g = reported[kind]["gini"]
        ax.plot(x, y, color=SERIES[i], linewidth=2, label=f"{kind.capitalize()}s, Gini {g:.2f}")
    ax.plot([0, 1], [0, 1], color=GRID_GRAY, linewidth=1)
    ax.set_xlabel("Cumulative share of children")
    ax.set_ylabel("Cumulative share of accessibility")
    ax.legend(loc="upper left")
    style.save(fig, "lorenz_access")
    plt.close(fig)


def run() -> None:
    style.apply()
    h1_district_error()
    compliance()
    population_map()
    access_map("school")
    access_map("preschool")
    lorenz()
    if (PROCESSED / "uncovered_2023_1000.parquet").exists():
        programme_map(1000)


if __name__ == "__main__":
    run()

import time
from collections.abc import Callable

import geopandas as gpd
import typer

from astana_access.config import PROCESSED

app = typer.Typer(add_completion=False, help="Reproduce the analysis stage by stage.")


def stage_boundary() -> None:
    from astana_access.grid import districts
    from astana_access.ingest import boundary

    boundary.fetch_city()
    boundary.fetch_districts()
    districts.build()


def stage_worldpop() -> None:
    from astana_access.ingest import worldpop

    worldpop.fetch_all()


def stage_grid() -> None:
    from astana_access.config import RAW
    from astana_access.grid.build import add_cohorts, assign_districts, build_grid, zonal_sum
    from astana_access.ingest import worldpop

    city = gpd.read_file(RAW / "boundary" / "city.geojson")
    grid = build_grid(city)
    paths = worldpop.fetch_all()
    population = add_cohorts(zonal_sum(grid, {name: str(path) for name, path in paths.items()}))
    grid = grid.merge(population, on="h3")
    districts = gpd.read_file(PROCESSED / "districts.gpkg", layer="districts")
    grid = assign_districts(grid, districts)
    grid.to_file(PROCESSED / "grid_pop.gpkg", driver="GPKG")


def stage_osm() -> None:
    from astana_access.ingest import osm

    osm.fetch_facilities()
    osm.fetch_buildings()


def stage_schools() -> None:
    from astana_access.inventory import capacity, schools

    schools.build()
    capacity.run()


def stage_preschools() -> None:
    from astana_access.ingest import indigo
    from astana_access.inventory import preschool_registry, preschools

    preschools.build()
    indigo.run()
    preschool_registry.build()


def stage_population() -> None:
    from astana_access.population import buildings, history, model, residential, stations

    stations.build()
    buildings.build()
    residential.fit_predict()
    model.build()
    history.build()


def stage_access() -> None:
    from astana_access.accessibility import catchment_check, compliance, coverage
    from astana_access.equity import analysis
    from astana_access.inventory import programme_list

    programme_list.build()
    coverage.build()
    compliance.run()
    catchment_check.run()
    analysis.run()


def stage_models() -> None:
    from astana_access.modeling import explain, vacancy

    vacancy.run()
    explain.run()


def stage_programme() -> None:
    from astana_access.optimization import backtest, programme

    backtest.run()
    programme.run()


def stage_checks() -> None:
    from astana_access.validation import listing

    if listing.run() is None:
        typer.echo("team listing not found, check skipped")


def stage_figures() -> None:
    from astana_access.viz import figures

    figures.run()


STAGES: dict[str, Callable[[], None]] = {
    "boundary": stage_boundary,
    "worldpop": stage_worldpop,
    "grid": stage_grid,
    "osm": stage_osm,
    "schools": stage_schools,
    "preschools": stage_preschools,
    "population": stage_population,
    "access": stage_access,
    "models": stage_models,
    "programme": stage_programme,
    "checks": stage_checks,
    "figures": stage_figures,
}


@app.command("list")
def list_stages() -> None:
    for name in STAGES:
        typer.echo(name)


@app.command()
def run(
    start: str = typer.Option("boundary", help="First stage to run."),
    stop: str = typer.Option("figures", help="Last stage to run."),
) -> None:
    names = list(STAGES)
    for name in names[names.index(start) : names.index(stop) + 1]:
        began = time.time()
        typer.echo(f"{name} ...")
        STAGES[name]()
        typer.echo(f"{name} done in {time.time() - began:.0f} s")


if __name__ == "__main__":
    app()

# astana-access

An open, data-driven framework for assessing walking accessibility to social infrastructure and evaluating its siting, applied to the state schools and preschools of Astana. It is the software part of the diploma "Data-Driven Framework for Spatial Accessibility Assessment and Optimal Siting of Social Infrastructure" (Astana IT University, 6B06103 Big Data Analysis).

The framework:

1. reconstructs population below the district level from official district totals, the territories of 386 polling stations and building footprints classified by a LightGBM model, and counts children with the official age structure of each district;
2. computes walking distances from every dwelling to every school and preschool on the OpenStreetMap street network;
3. measures accessibility per child with an enhanced two-step floating catchment index in which each child is allocated once, with official design capacity as supply;
4. describes inequality (Gini, Theil split by district, local Moran clusters) and compliance with the service radii of SP RK 3.01-101-2013;
5. tests the sites of the Comfortable School programme and the city's 2026-2028 construction plan against a capacitated maximal covering model on free land, and ranks the 238 school sites reserved in the detailed planning projects;
6. models how the city chooses school sites and forecasts where new housing will be built, so that sites can be ranked on the demand of 2028;
7. publishes the results as a static web atlas.

## Setup

Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
cp .env.example .env
```

`.env` holds optional keys: `EGOV_API_KEY` for the open data portal of eGov and `TWOGIS_API_KEY` for geocoding. Neither is needed to reproduce the results from the saved inputs.

## Running

```bash
uv run astana-access list
uv run astana-access run
uv run astana-access run --start access --stop dashboard
```

`run` executes the thirteen stages in order, from `boundary` to `dashboard`; `--start` and `--stop` run a slice.

| Stage | What it does | Main outputs |
|---|---|---|
| `boundary` | City and district boundaries | `data/processed/districts.gpkg` |
| `worldpop` | WorldPop rasters, the comparison surface | `data/raw/worldpop/` |
| `grid` | H3 grid with WorldPop population | `data/processed/grid_pop.gpkg` |
| `osm` | Facilities, buildings, streets, land use | `data/raw/osm/` |
| `schools` | School inventory linked to the register | `data/processed/facilities.gpkg` |
| `preschools` | Preschool inventory from the INDIGO register | `data/processed/facilities.gpkg` |
| `population` | Polling stations, residential classifier, population surface, 2023 city | `reports/population_model.json` |
| `access` | Walking access, E2SFCA, compliance, official territories, inequality | `reports/access_equity.json`, `reports/compliance.json` |
| `models` | Preschool vacancy model and SHAP | `reports/preschool_vacancy.json`, `reports/shap.json` |
| `programme` | Programme backtest, plan 2026-2028, model of siting choices, housing forecast, detailed plans, siting on 2028 demand, ranking by distance and crowding | `reports/programme_2023.json`, `reports/plan_2026_2028.json`, `reports/siting_model.json`, `reports/housing_forecast.json`, `reports/detailed_plans.json`, `reports/siting_2028.json`, `reports/two_objective.json` |
| `checks` | Checks against official replies and team-compiled sources | `reports/school_register_check.json`, `reports/preschool_capacity_check.json` |
| `figures` | Thesis figures in EPS and PDF | `thesis/figures/` |
| `dashboard` | Data of the web atlas and the ranking of reserved sites | `dashboard/data/`, `reports/pdp_site_ranking.csv` |

Stages that need an input which is not present skip their check and say so.

## Inputs that code does not fetch

Most sources are downloaded by the pipeline. The following are saved by hand under `data/raw/` and are not in the repository:

| Path | Source |
|---|---|
| `polling/decision_01-7_2026-02-18.txt` | Akim's decision No. 01-7 on polling stations, as amended 18 February 2026 |
| `stat/astana/` | Bureau of National Statistics, population by single year of age and education tables |
| `overture/` | Overture Maps building footprints |
| `indigo/` | INDIGO preschool register and organisation cards; the portal forbids crawling, so pages are saved manually |
| `official_reply*/` | Replies of the city's education and construction departments to information requests |
| `team/` | 2GIS listings and the school buildings of the detailed planning projects, compiled by the project team |

Official letters contain the applicant's personal data and are never committed.

## Web atlas

```bash
python -m http.server 8765 --directory dashboard
```

Open `http://localhost:8765`. The atlas has four views: a scrolling story, a layer explorer, site screening of the reserved sites and the method. `?theme=light` or `?theme=dark` forces a colour scheme; the key P switches to a large-screen mode for projectors.

## Tests and checks

```bash
uv run pytest
uv run ruff check src tests
python scripts/check_thesis.py
```

`check_thesis.py` reports citations missing from the bibliography, unresolved references and missing figures.

## Layout

| Path | Contents |
|---|---|
| `src/astana_access/ingest` | Source acquisition and parsing |
| `src/astana_access/inventory` | School and preschool inventories, record linkage |
| `src/astana_access/population` | Polling stations, residential classifier, population surface |
| `src/astana_access/grid` | H3 grid and districts |
| `src/astana_access/accessibility` | Walking network, E2SFCA, compliance, official territories |
| `src/astana_access/equity` | Gini, Theil, Moran's I, LISA |
| `src/astana_access/modeling` | Preschool vacancy model, SHAP |
| `src/astana_access/optimization` | Land layer, capacitated MCLP, backtests, plan and detailed plans |
| `src/astana_access/validation` | Checks against official and team-compiled sources |
| `src/astana_access/viz` | Figures and atlas data |
| `dashboard` | Static web atlas |
| `thesis` | LaTeX sources, figures, bibliography |
| `reports` | Generated tables, result summaries and working notes |
| `tests` | Unit tests |
| `data` | Untracked raw, interim, processed and external inputs |

## Conventions

- CRS: EPSG:4326 for storage, EPSG:32642 for metric operations.
- Grid: H3 resolution 9.
- Figures are written as EPS and PDF only, into `thesis/figures`.
- Random seed is fixed in `astana_access.config`.
- Real data only: no synthetic values; every estimate is labelled as such.

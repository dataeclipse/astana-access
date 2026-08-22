# astana-access

Spatial accessibility assessment and optimal siting of social infrastructure in Astana.

## Layout

| Path | Contents |
|---|---|
| `src/astana_access/ingest` | Source acquisition: gridded population, OSM, open registries |
| `src/astana_access/grid` | H3 grid construction and population disaggregation |
| `src/astana_access/accessibility` | Travel time matrices and E2SFCA |
| `src/astana_access/equity` | Gini, Theil, Moran's I, LISA, normative compliance |
| `src/astana_access/modeling` | Siting model, spatial cross-validation, SHAP |
| `src/astana_access/optimization` | MCLP, p-median, Pareto front |
| `src/astana_access/viz` | Figure style and vector export |
| `thesis` | LaTeX sources, figures in EPS and PDF, bibliography |
| `data` | Untracked. Raw, interim, processed and external inputs |
| `scripts` | Entry points for each pipeline stage |
| `reports` | Generated tables and result summaries |

## Setup

```bash
uv sync --all-extras
```

## Conventions

- CRS: EPSG:4326 for storage, EPSG:32642 for metric operations.
- Grid: H3 resolution 9.
- Figures are written as EPS and PDF only, into `thesis/figures`.
- Random seed is fixed in `astana_access.config`.

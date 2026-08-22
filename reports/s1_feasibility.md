# Sprint 1 feasibility note

Data snapshot 2026-08-23. All figures reproducible from the pipeline in `src/astana_access`.

## Verdict

The quantitative core stands, but not on raw gridded population. The hard gate set for this sprint was whether modelled population can be reconciled with official figures. It can at city level, and it cannot at district level without correction. The correction is available and is now part of the method rather than an afterthought.

## Study area

| Item | Value | Source |
|---|---|---|
| City boundary | OSM relation 3087155 | Nominatim, snapshot 2026-08-23 |
| City area | 800.2 km2 | computed, EPSG:32642 |
| Districts | 6 | Bureau of National Statistics, administrative-territorial units as of 2026-01-01 |
| Analysis grid | H3 resolution 9, overlap containment | 6710 cells, 845.8 km2 |
| Mean cell area | 0.1256 km2 (edge approx 190 m) | h3.cell_area, agrees with projected area to 0.4 percent |
| Populated cells | 3192 of 6710 | cells with more than 0.5 residents |

The district layer required correction. The OSM polygon for Esil is stale and still covers the territory of Nura, which was separated from it in 2018. Subtracting Nura yields a clean partition: six polygons, zero pairwise overlap, zero uncovered area, sum equal to union equal to the city area of 800.23 km2. Saraishyk district, created on 2024-05-23 by dividing Almaty district and formally established on 2025-01-29, is tagged at admin level 8 in OSM while the other five are at level 6, so a level filter alone does not produce the correct set.

## Population reconciliation

WorldPop R2025A constrained, 100 m, with age and sex structure, was downloaded for Kazakhstan: the total layer plus age bands 0, 1-4, 5-9, 10-14 and 15-19.

City level:

| Reference | Official | WorldPop | Ratio |
|---|---|---|---|
| 2025-01-01 | 1,528,703 | 1,419,164 | 0.928 |
| 2025-06-01 | 1,566,566 | 1,419,164 | 0.906 |

A 7 to 9 percent city-level undercount is expected for a capital growing by roughly 90,000 people per year and is correctable by rescaling.

District level is the problem:

| District | Official 2025-01-01 | WorldPop 2025 | Ratio |
|---|---|---|---|
| Almaty and Saraishyk | 409,873 | 398,862 | 0.973 |
| Baikonur | 227,043 | 333,386 | 1.468 |
| Esil | 293,451 | 212,950 | 0.726 |
| Nura | 246,763 | 199,733 | 0.809 |
| Saryarka | 351,573 | 273,652 | 0.778 |

Mean absolute district error 23.6 percent, worst case 46.8 percent. Almaty and Saraishyk are combined because the official figures for early 2025 predate the split.

The error is not noise and not uniform. It is directional: the model overstates the established Baikonur district and understates Esil, Nura and Saryarka. Uniform rescaling to the official city total would leave this misallocation untouched, and the understated districts include exactly the peripheral growth areas where a social infrastructure deficit is expected. Using raw WorldPop would therefore bias the central result of the work toward finding no deficit where the deficit most likely is.

## Weighting surface

The same conclusion was reached independently before the official district figures were located, using residential floor area from OSM building footprints as a proxy. The proxy predicted the direction of the WorldPop error in every district.

| Predictor of official district share | Mean absolute error | Correlation with official share |
|---|---|---|
| WorldPop | 22.8 percent | 0.534 |
| OSM residential floor area | 14.7 percent | 0.744 |

Floor area is the better predictor but is not good enough alone: it understates Saryarka by 27.8 percent, the dense inherited core, where older apartment stock is less completely attributed in OSM and the building levels tag is often missing.

Neither surface is acceptable on its own. The method adopted is dasymetric redistribution of official district totals across cells, using a weighting surface built from WorldPop and building floor area, so that district totals match by construction and only the within-district distribution is modelled. The residual within-district uncertainty is documented rather than hidden, and its effect is carried into the sensitivity analysis.

Absolute floor area figures should not be read as reliable. The implied city-wide residential provision of 46 m2 per person is roughly double the national norm, because 44,918 of 49,778 mapped buildings carry only the untyped `building=yes` tag and some non-residential stock is counted. The relative pattern between districts is the usable signal, and the direction of any contamination from untyped commercial buildings in the centre would work against the observed result, so the finding is conservative.

## Cohorts

Cohorts are reconstructed from the age bands by linear allocation within each band: preschool as ages 1 to 6, school as ages 7 to 17.

| Cohort | Count | Share of total |
|---|---|---|
| Preschool, 1-6 | 182,480 | 12.8 percent |
| School, 7-17 | 264,121 | 18.6 percent |
| All bands 0-19 | 515,915 | 36.2 percent |

These shares are plausible for Kazakhstan. They are pre-correction figures and will move once the dasymetric step is applied, and the linear within-band allocation remains an approximation to be stated as a limitation.

## Facility supply

OSM facilities inside the city boundary, snapshot 2026-08-23:

| Category | Count |
|---|---|
| amenity=school | 161 |
| amenity=kindergarten | 131 |
| clinic, doctors, healthcare centre | 123 |

Three defects, in order of severity.

First, capacity is absent. Not one of the 415 facilities carries a capacity tag. This confirms the risk registered at planning time and means capacity must come from the national school construction programme figures and from a floor-area proxy for the rest.

Second, public and private cannot be distinguished. Only 9 of 415 objects carry `operator:type`. A fee-charging private school is not a substitute for a state school place in an accessibility or equity analysis, so this distinction is not optional. It has to come from the official registries.

Third, `amenity=school` conflates categories. Of 161 objects, 112 match a numbered general school pattern, 8 are clearly out of scope, such as martial arts and language centres, and 41 need classification by hand. The unclassified group is genuinely mixed: it contains Nazarbayev Intellectual Schools, Binom schools and named lyceums, which are real schools, alongside a sports complex and a baby club, which are not.

Building footprints are available: 49,778 objects, of which 20,028 carry a levels tag, and 102 are tagged `building=school`, which gives an independent cross-check on school locations.

## Blockers

1. **data.egov.kz API key.** The portal exposes a working REST API at `/api/v4/{index}/v1` but rejects requests without a key, and a key requires account registration. Needed for the authoritative school and kindergarten registries, and above all for the public and private distinction that OSM cannot supply.
2. **Official district populations from the primary source.** The figures used here were located through a secondary source and match the official city total exactly, but the thesis must cite the Bureau of National Statistics directly. The current district level series was not found in the portal's published tables during this sprint.
3. **Boundary-consistent historical figures.** The 2024 act on the formation of a new district and the establishment and modification of the boundaries of Astana districts changed more than one boundary, so district figures from before 2025 are not comparable with current geometry without the act's text.

## Carried into the method

- Population disaggregation is dasymetric and constrained to official district totals. Raw WorldPop is a weighting input, not a result.
- District geometry is corrected for the stale Esil polygon and validated as a partition before use.
- Facility classification into general schools, other educational objects and non-schools is an explicit pipeline stage with a measured error rate, not a filter applied silently.
- The public and private split is a hard requirement on the supply layer.

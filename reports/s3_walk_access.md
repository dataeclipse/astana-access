# Sprint 3, first results: walking network and normative coverage

Written 2026-10-01. Code: `src/astana_access/accessibility/network.py`, `coverage.py`, `catchment_check.py`. Outputs: `data/processed/od_walk_school.parquet`, `od_walk_preschool.parquet`, `reports/coverage_city.csv`, `reports/coverage_district.csv`, `reports/catchment_check.json`.

## 1. Norms

The full text of SP RK 3.01-101-2013 is not openly available; the Paragraph system shows only a demo, and copies on document mirrors could not be opened. What is official and citable:

- Government decree No. 710 of 2 September 2025, "On the system of regional standards for settlements", in the edition of 14 July 2026, sets the principle of 20-minute walking access to services in the capital and refers the calculation of school and preschool places to SP RK 3.01-101-2013, appendix V, table V.1.
- SP RK 3.01-101-2013 states that a residential quarter serves everyday needs within a radius of 500 m, with schools and preschools governed by its tables 10.1 and 10.2. The numbers in those tables are still to be read from the primary text.

Until the tables are read, coverage is reported at 300, 500, 750, 1,000 and 1,500 m. A 20-minute walk at 75 m per minute is 1,500 m.

## 2. Network

All OSM ways with a highway tag inside the city, except motorways, ways under construction and ways closed to pedestrians, treated as two-way: 152,491 nodes and 5,934 km. 98.1 per cent of nodes lie in one connected component, which is the one used. Distances are network length plus the straight-line gap from each building and each facility to its nearest node; the median gap is 37 m for buildings and 51 m for schools.

Check: over 206,000 building-school pairs more than 300 m apart, the network distance is never shorter than the straight line, and the median ratio of the two is 1.41.

## 3. Do families go to the nearest school?

The school enrolment portal publishes the houses assigned to 11 schools. 2,988 of them resolve to an exact building.

| Measure | Value |
|---|---|
| Assigned school is the nearest by network | 57.0% |
| Assigned school is one of the two nearest | 67.5% |
| Median walking distance to the assigned school | 957 m |
| 90th percentile | 2,176 m |
| Assigned school farther than 2.5 km | 15.3% |

Three schools follow the nearest rule almost exactly (numbers 38, 68 and 74, above 97 per cent). Others do not: for number 41 the share is 27 per cent, for number 52 it is zero. The date of these lists is not published, schools opened since may have redrawn the boundaries, and part of the houses lie in streets of detached housing where geocoding is weakest.

Consequence for the method: the nearest-school assumption is a simplification that holds for about half of households. Measures that let a household reach several schools, such as the floating catchment family, are better suited than assigning each household to its nearest school, and the official catchments are kept as a test set.

## 4. Normative coverage

Share of children with a facility within the given walking distance, city level:

| | 300 m | 500 m | 750 m | 1,000 m | 1,500 m |
|---|---|---|---|---|---|
| Preschool, station model | 33.6% | 67.9% | 86.9% | 92.6% | 96.6% |
| Preschool, WorldPop | 18.4% | 39.2% | 57.2% | 67.0% | 79.1% |
| School, station model | 4.8% | 20.2% | 48.6% | 70.2% | 89.6% |
| School, WorldPop | 3.2% | 10.3% | 26.8% | 41.4% | 66.0% |

WorldPop places part of the population in cells without dwellings and measures from cell centres, which lowers coverage everywhere. The three building-based variants differ by at most 3 points from each other.

By district, station model:

| District | School within 500 m | School within 1 km | Preschool within 300 m | Preschool within 500 m |
|---|---|---|---|---|
| Almaty | 23.4% | 81.6% | 38.6% | 79.5% |
| Baikonur | 24.7% | 79.2% | 30.7% | 64.2% |
| Esil | 18.8% | 60.0% | 38.7% | 70.0% |
| Nura | 9.4% | 54.6% | 34.6% | 63.9% |
| Saraishyk | 20.3% | 72.6% | 27.0% | 62.6% |
| Saryarka | 25.8% | 77.6% | 29.6% | 65.7% |

For schools the pattern matches H2: Nura and Esil, the districts of recent growth, have the lowest coverage at both distances. For preschools the districts differ less and no clear pattern is visible yet.

## 5. Completeness of the school layer

The school layer holds 111 state schools with catchment admission; the city reported 122 state schools in September 2025, a figure that also counts selective, special and evening schools, which are excluded here by design. The risk is that recent schools in exactly the districts of recent growth are missing, which would make H2 an artefact.

Checks against announced sites of the Comfortable School programme:

| Announced site | Result |
|---|---|
| School 99, Kabanbai Batyr avenue and Syganak street | In the layer, 234 m from the crossing |
| Egemen Kazakhstan and A. Imanov streets, 2,000 places, 2025 | In the layer as school 119, 142 m |
| School 106, Beibarys Sultan street 15 | Not in the layer; nearest school 739 m |
| School 105, Koktal, Ulytau and Nauryz streets | Not in the layer; nearest school 657 m |
| M. Tulebaev and Burabay streets, 2,000 places, 2025 | Not in the layer; nearest school 1.2 km |

Five unnamed school grounds of 1.1 to 3.4 ha are mapped in OSM more than 150 m from any known school: two in Saraishyk, two in Nura and one in Saryarka. They are almost certainly new schools whose names are not yet mapped. They are added as a second supply variant, `with_presumed`.

Share of school-age children with a state school within walking distance, station model:

| District | 500 m, named | 1 km, named | 500 m, with presumed | 1 km, with presumed |
|---|---|---|---|---|
| Almaty | 23.4% | 81.6% | 23.4% | 81.6% |
| Baikonur | 24.7% | 79.2% | 24.7% | 79.2% |
| Esil | 18.8% | 60.0% | 18.8% | 60.0% |
| Nura | 9.4% | 54.6% | 9.7% | 56.5% |
| Saraishyk | 20.3% | 72.6% | 22.1% | 75.7% |
| Saryarka | 25.8% | 77.6% | 25.8% | 80.6% |

Adding the presumed schools raises coverage by up to 3 points and does not change the order: Nura and Esil stay lowest. Three caveats remain. At least one announced school, at Tulebaev and Burabay streets, is not mapped at all; it lies in Almaty, the best-covered district, so its absence does not favour H2. Esil has the largest number of private schools, which this analysis excludes by design; coverage there describes access to free public schooling, not to any school. And the OSM layer reflects mapping as of September 2026, so a school opened recently but not yet mapped is still possible in any district.

## 6. Preschool vacancy as a test of demand pressure (H4a, first pass)

The preschool portal publishes free places only after the evening distribution to waiting lists, so a place that is published means the organisation's waiting list for that group is empty. On 30 September 2026, 428 of the 728 located organisations had at least one free place: 395 of 591 private ones and 33 of 137 state ones.

For each organisation, demand pressure is measured as the number of preschool-age children, under the station population model, living within 500 m and 1 km of walking distance, alone and divided by the number of preschools within the same straight-line radius. Two feature sets are compared under spatial cross-validation with 2 km blocks, five folds, repeated five times: the organisation's own characteristics (ownership, branch, minimum age, language, type, position accuracy) and the same plus demand pressure.

| Organisations | Model | Own characteristics, ROC-AUC | With demand pressure, ROC-AUC |
|---|---|---|---|
| All | Logistic regression | 0.660 | 0.697 |
| All | LightGBM, regularised | 0.680 | 0.693 |
| Private only | Logistic regression | 0.574 | 0.610 |
| Private only | LightGBM, regularised | 0.585 | 0.564 |

Among private organisations, 73.0 per cent of those below the median of children per organisation within 1 km had free places, against 60.7 per cent above it. In a logistic regression on private organisations, the standardised coefficient of the logarithm of that ratio is -0.16, with a bootstrap 95 per cent interval from -0.35 to 0.02.

The direction is the one H4a predicts: more children per organisation nearby, fewer free places. The effect is small and not yet distinguishable from zero, and the tree model does not gain from the pressure features among private organisations. A single evening is a noisy label. Planned improvements: several snapshots of the portal, matching free places to the age group they belong to, and replacing the straight-line competitor count with the floating catchment demand from the accessibility model.

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

## 5. Caveat that must be resolved before H2 is claimed

The school layer holds 111 state schools; the city reported 122 in September 2025. The missing schools are most likely recent ones, including Comfortable School buildings in Nura and Esil. If they are missing from the supply, coverage in exactly those districts is understated and H2 would be confirmed by an artefact. The next step is to geocode the announced Comfortable School sites and every school opened since 2023, and to complete the supply layer.

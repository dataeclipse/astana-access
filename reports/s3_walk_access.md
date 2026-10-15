# Sprint 3, first results: walking network and normative coverage

Written 2026-10-01. Code: `src/astana_access/accessibility/network.py`, `coverage.py`, `catchment_check.py`. Outputs: `data/processed/od_walk_school.parquet`, `od_walk_preschool.parquet`, `reports/coverage_city.csv`, `reports/coverage_district.csv`, `reports/catchment_check.json`.

## 1. Norms

Source: SP RK 3.01-101-2013 "Urban planning. Planning and development of urban and rural settlements", edition of 9 July 2021 including orders 45-NK of 5 March 2018 and 46-NK of 1 April 2019, copy obtained from smeta-kz.com and kept in `data/raw/norms/`. The current edition is dated 2 June 2025; the values below must be checked against it before the thesis cites them as current.

| Norm | Value | Place in SP RK |
|---|---|---|
| Service radius, preschools in cities | 300 m | Table 2-1, clause 7.7 |
| Service radius, preschools in rural settlements and small towns with low-rise housing | 500 m | Table 2-1 |
| Service radius, general schools | 500 m | Table 2-1 |
| Allowed increase in settlements with a complex layout or under reconstruction | up to 10% | Table 2-1, note |
| Transport access instead of walking | 15 min one way for primary grades, at most 50 min for other grades | Table 2-1, note |
| Preschool provision | up to 85% of children; in new-build areas without demographic data up to 180 places per 1,000 residents, of which at most 100 inside housing areas | Table V.1 |
| School provision | 100% of grades 1-9 and up to 75% of grades 10-11 in one shift; in new-build areas at least 180 places per 1,000 residents | Table V.1 |
| School plot | 19 sq m per pupil for 900-1,200 pupils, so 3.8 ha for a 2,000-seat school | Table V.1 |

Government decree No. 710 of 2 September 2025 on regional standards, in the edition of 14 July 2026, adds the principle of 20-minute walking access in the capital and refers school and preschool provision to the same standard.

Two readings of "radius" are reported: straight-line distance, which is how planners usually apply a service radius, and walking distance over the network, which is what a child actually walks.

Compliance, share of children within the norm, station population model (`reports/compliance.json`):

| District | School 500 m, straight line | School 500 m, walking | Preschool 300 m, straight line | Preschool 300 m, walking |
|---|---|---|---|---|
| City | 60.3% | 20.5% | 76.3% | 33.6% |
| Almaty | 65.7% | 23.4% | 89.2% | 38.6% |
| Baikonur | 67.8% | 24.7% | 70.1% | 30.7% |
| Esil | 48.1% | 18.8% | 78.1% | 38.7% |
| Nura | 48.1% | 9.7% | 73.4% | 34.6% |
| Saraishyk | 61.9% | 22.1% | 71.1% | 27.0% |
| Saryarka | 72.3% | 25.8% | 73.8% | 29.6% |

The two readings differ by a factor of two to three: most children who live within the statutory radius of a school as the crow flies do not live within it on foot. Across the three building-based population surfaces the city-level shares vary by less than 2.5 points.

## 2. Network

All OSM ways with a highway tag inside the city, except motorways, ways under construction and ways closed to pedestrians, treated as two-way: 152,491 nodes and 5,934 km. 98.1 per cent of nodes lie in one connected component, which is the one used. Distances are network length plus the straight-line gap from each building and each facility to its nearest node; the median gap is 37 m for buildings and 51 m for schools.

Check: over 206,000 building-school pairs more than 300 m apart, the network distance is never shorter than the straight line, and the median ratio of the two is 1.41.

## 3. Do families go to the nearest school?

The school enrolment portal publishes the houses assigned to 11 schools. 2,988 of them resolve to an exact building.

| Measure | Value |
|---|---|
| Assigned school is the nearest by network | 57.3% |
| Assigned school is one of the two nearest | 67.8% |
| Assigned school within 4 km of walking | 99.1% |
| Median walking distance to the assigned school | 1,133 m |
| 90th percentile | 2,765 m |
| Median extra distance when the assigned school is not the nearest | 767 m |

A first run that searched only within 2.5 km reported a median of 957 m; it left out the 15 per cent of houses whose assigned school lies farther away, and the values above replace it.

Three schools follow the nearest rule almost exactly (numbers 38, 68 and 74, above 97 per cent). Others do not: for number 41 the share is 28 per cent, for number 52 it is zero. The date of these lists is not published, schools opened since may have redrawn the boundaries, and part of the houses lie in streets of detached housing where geocoding is weakest.

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

## 7. Floating catchment accessibility, inequality and deficit clusters (H2, H3)

Code: `accessibility/e2sfca.py`, `equity/inequality.py`, `equity/analysis.py`. Outputs: `reports/access_equity.json`, `reports/sensitivity_access.csv`, `data/processed/access_cells_*.parquet`.

### Choice of the load step

The enhanced two-step floating catchment area method counts a child towards every facility within the catchment, and children with no facility within it load none. Where many children live beyond walking distance, this understates the load on the schools that actually receive them. The alternative tested here distributes each child once over the facilities within a wider allocation radius, in proportion to the distance weights, before the supply-to-demand ratio is computed; the accessibility step is then summed within the walking catchment as usual.

The choice was settled against observed enrolment at the ten schools for which it is published:

| Load step | Rank correlation with enrolment | Median modelled over observed | Children allocated |
|---|---|---|---|
| E2SFCA, 1.5 km, children counted at every school in reach | 0.41 | 1.37 | 395,406, more than exist |
| Each child allocated once within 1.5 km | 0.61 | 0.84 | 267,831 |
| Each child allocated once within 3 km | 0.55 | 0.95 | 292,863 |
| Each child allocated once within 4 km | 0.39 | 0.93 | 293,605 |

The city has 304,022 school-age children under the station model. Allocation within 3 km reaches 96 per cent of them and reproduces the level of enrolment; the 1.5 km allocation ranks schools slightly better but leaves 12 per cent of children unallocated. The baseline uses 3 km for the load step and 1.5 km, a 20-minute walk, for the accessibility step. For preschools the pair is 2 km and 1 km. The enrolment figures date from 2015 to 2023, and school 79 reports its opening-year enrolment, so ten points support the choice but do not prove it.

### Baseline

Schools: supply is floor area; preschools: supply is the attendance class mean. Values are relative to the city mean per child.

| District | Schools | Preschools |
|---|---|---|
| Almaty | 1.06 | 1.59 |
| Baikonur | 1.14 | 0.64 |
| Esil | 0.73 | 1.08 |
| Nura | 0.73 | 0.90 |
| Saraishyk | 0.94 | 1.01 |
| Saryarka | 1.38 | 0.79 |

| Measure | Schools | Preschools |
|---|---|---|
| Children with no facility within the catchment | 8.7% | 7.4% |
| Gini, weighted by children | 0.395 | 0.460 |
| Theil index | 0.284 | 0.366 |
| Share of Theil between districts | 11% | 11% |
| Global Moran's I over H3 cells | 0.84 | 0.83 |
| Children in significant low-low clusters | 11.1% | 9.6% |
| Largest share of those, by district | Esil, 4.4% of all children | Saryarka, 2.7%; Baikonur, 2.2% |

### What this says about H2

For schools, H2 holds: Esil and Nura have about 73 per cent of the city's accessibility per child, the largest deficit clusters lie in Esil, and removing the five presumed new schools makes Nura worse (0.70), not better.

For preschools, H2 fails. The deficit lies in the established districts, Baikonur at 64 per cent of the mean and Saryarka at 79, while Almaty is best served. A plausible reading, to be tested rather than assumed, is that private preschools, which hold most places, opened where new housing created paying demand, leaving the older districts dependent on an ageing state network.

In both cases nine-tenths of the inequality lies within districts rather than between them. Comparing district averages, the way provision is usually reported, misses most of it.

### Robustness, H3

48 runs per facility type: four population surfaces, two supply measures, three decay functions and two catchment sizes, each compared with the baseline.

| | Building-based population, 36 runs | WorldPop, 12 runs |
|---|---|---|
| Schools, district rank correlation, median and minimum | 0.91, 0.77 | 0.77, 0.66 |
| Schools, overlap of the worst-served fifth of children, Jaccard, median and minimum | 0.83, 0.66 | 0.14, 0.12 |
| Schools, worst district | Nura 30 times, Esil 6 | Nura 7, Esil 5 |
| Preschools, district rank correlation, median and minimum | 0.94, 0.83 | 0.83, 0.83 |
| Preschools, overlap of the worst-served fifth, median and minimum | 0.81, 0.76 | 0.14, 0.12 |
| Preschools, worst district | Baikonur 36 times | Baikonur 12 |

H3 holds at district level under every specification: the worst district never changes from Nura or Esil for schools and from Baikonur for preschools. At the level of individual cells it holds across the three building-based population surfaces, where the same deficit areas recur, but not with WorldPop, whose deficit cells barely overlap with any building-based result. Where the deficit is depends on how population is placed, which is the reason H1 matters.

## 8. The programme list and the comparison with 2026

Code: `inventory/programme_list.py`, `optimization/backtest.py`. Inputs: `data/labels/comfortable_schools.csv` and `data/labels/comfortable_schools_sources.csv`. Outputs: `reports/comfortable_schools.json`, `data/processed/comfortable_schools.gpkg`, `reports/backtest.json`.

### Which schools the programme built

The first pass approximated the programme by school number. It is now reconstructed site by site from ten public sources: the list of 24 sites published by Samruk-Kazyna Construction in August 2023, the enrolment announcement of July 2024 that gives the numbers of eight schools, completion and opening reports of December 2024 and of July, August and September 2025, a press report of April 2026 on a site still unbuilt, and public listing titles on 2GIS and krisha.kz for schools whose number and address are not given elsewhere.

| | Sites |
|---|---|
| Listed in August 2023 | 24 |
| Reported built by September 2025 | 23 (16 in 2024, 7 in 2025) |
| Not built by April 2026 (Nazhimedenov and A56 streets) | 1 |
| Located with high confidence: OSM school with the published number, or an address that resolves to it | 15 |
| Located with medium confidence | 6 |
| Not located | 2 |
| Seats at the 21 located sites | 38,400 in one shift |

Medium confidence covers two schools not yet mapped in OSM and placed at the announced street crossing (number 105 in Koktal; Tulebaev and Burabai streets), two schools placed on the only new unnamed school ground near the place the reports name (Otau; number 100 near school 90), and two numbered schools whose programme status rests on a listing title (115 and 118). The two sites not located are announced only by street codes (E48 and E77; E30, E751 and E796 near the Sat City complex) that OSM does not carry and no report links to a school number; the second may coincide with one of the located 2025 schools.

The list differs from the number-based approximation in three places: two unnamed school grounds previously counted as programme schools are not confirmed by any source and are now treated as other new schools, and school 105 and the school at Tulebaev and Burabai streets, absent from OSM, are added.

### Comparison with the population of 2026

| | Within 1 km | Within 1.5 km |
|---|---|---|
| Children without a state school, programme removed | 106,964 | 41,718 |
| Reached by the 21 programme schools | 23,263 | 16,545 |
| Optimal 21 cells, no land or capacity constraint | 60,685 | 34,132 |
| Programme as a share of that optimum | 38% | 48% |
| 21 most populous cells | 17,686 | 4,917 |
| 21 random cells, mean and 95th percentile | 15,595 and 22,053 | 10,700 and 16,257 |
| Optimal sites within 1 km of a programme school | 71% | 48% |

This comparison is kept for reference. It judges a choice made in 2022 and 2023 against the city of 2026; section 9 replaces it.

## 9. The programme against the demand of 2023 (H4)

Code: `population/history.py`, `optimization/land.py`, `optimization/realistic.py`, `optimization/programme.py`. Output: `reports/programme_2023.json`. The programme is the list of section 8: 21 located schools with their seats.

**Demand in 2023.** OSM as of 1 January 2023 is read through the Overpass history interface: 72,442 buildings, against 74,559 now. A current dwelling mapped in OSM counts as existing in 2023 if at least 30 per cent of its footprint overlaps a building that was mapped then; Microsoft footprints, which carry no date, are treated as existing. 36,714 of 39,735 dwellings pass, holding 70 per cent of current residential floor area. Floor area added since 2023 is 46 per cent of the current total in Nura, 38 in Esil and 34 in Saraishyk, against 8 to 12 per cent in the older districts. The official population on 1 January 2023 (Bureau of National Statistics, 1,354,435 in four reporting units, with Nura still inside Esil and Saraishyk inside Almaty) is allocated through the same station model. School-age children: 251,355. The 2023 school network is every state school except the programme and two new school grounds of unknown date. Buildings that stood in 2022 but were mapped only later count as new, which makes the 2023 city slightly emptier than it was.

**Land in 2023.** A plot is feasible if a disc of 3.8 ha, the plot that SP RK prescribes for a 2,000-seat school, fits on land that in 2023 was free of buildings, roads, water, railways, parks, forest, cemeteries, industry, allotments, construction sites and other institutions. Each candidate cell takes the nearest such plot within 600 m, and the school is placed on the plot itself; plots closer than 150 m to each other are merged. 191 plots remain. Ownership of the land is not known.

### Were programme sites chosen by deficit or by density?

Each of the 21 programme schools is assigned to its nearest candidate cell. Scores come from the 2023 state before the programme: the number of children with no state school within walking distance who would gain one from a school in the cell (deficit), and the total number of children within the same distance (density).

| Score | ROC-AUC, 1 km | 95% interval | ROC-AUC, 1.5 km | 95% interval |
|---|---|---|---|---|
| Deficit | 0.63 | 0.48 to 0.77 | 0.64 | 0.51 to 0.75 |
| Density | 0.46 | 0.33 to 0.59 | 0.45 | 0.34 to 0.56 |
| Children in the cell | 0.48 | 0.32 to 0.63 | 0.48 | 0.32 to 0.63 |
| Feasible plot in 2023 | 0.67 | 0.56 to 0.77 | 0.67 | 0.55 to 0.77 |

| Difference of AUC, deficit minus density | Value | 95% interval | Bootstrap share above zero |
|---|---|---|---|
| 1 km | +0.18 | +0.02 to +0.29 | 98.7% |
| 1.5 km | +0.19 | +0.00 to +0.34 | 97.5% |

Density predicts the chosen sites no better than chance; deficit does, and the difference is positive in 97 to 99 per cent of bootstrap samples, with the lower bound of the interval at or just above zero. Land is again the strongest single predictor: 13 of the 21 sites had a feasible plot in 2023, against 29 per cent of all cells. The first part of H4 holds, with the caveat that 21 sites give wide intervals.

### Backtest against the 2023 state, with land and capacity

Capacity is the number of seats times two shifts: 4,000 children for a 2,000-seat school, 2,400 and 1,200 for the smaller programme schools. The optimisation is the capacitated maximal covering problem over 21 sites, solved exactly; demand is aggregated to H3 cells of resolution 10, about 70 m across, which changes realised coverage by less than 0.2 per cent.

| | Within 1 km | Within 1.5 km |
|---|---|---|
| Children without a state school in 2023 | 78,459 | 29,927 |
| Reached by the programme, with its capacities | 17,197 | 11,649 |
| Optimal 21 sites anywhere, with capacity | 45,810 | 25,424 |
| Optimal 21 sites on feasible plots, with capacity | 19,063 | 17,275 |
| Same, without capacity | 19,063 | 17,275 |
| Programme as a share of the unconstrained optimum | 38% | 46% |
| Programme as a share of the land-feasible optimum | 90% | 67% |
| 21 most populous cells | 10,587 | 3,866 |
| 21 random cells, mean | 12,208 | 7,665 |
| Programme percentile among random draws | 96.5 | 95.0 |

Three findings.

Capacity never binds. With 4,000 places per school, no optimal or realised school receives more uncovered children within walking distance than it can seat, so the capacitated and uncapacitated optima coincide. The binding constraint is not school size but where a plot exists.

Land explains most of the gap. Without a land constraint the best 21 sites would reach 2.7 times as many uncovered children within 1 km as the programme did. Restricted to plots that were free in 2023, the best choice reaches only 11 per cent more at 1 km and 48 per cent more at 1.5 km.

The programme did well within the land it had. It beats the density rule by a wide margin and 95 to 97 per cent of random choices, and reaches 90 per cent of the land-feasible optimum at 1 km. The second part of H4, as stated, holds against the unconstrained optimum only; against land that was actually free, the room for better siting is modest at 1 km and about a third at 1.5 km.

An earlier version of this section placed each optimal school at the population centre of its cell whenever a plot existed within 600 m, which gave a land-feasible optimum of 31,520 at 1 km. A school stands on its plot, not at the centre of the cell, so that figure overstated what free land allowed and is replaced by the values above. A first comparison with land as it is in 2026 is also discarded: by 2026 much of the land free in 2023 had been built on, including the plots of the programme itself.

## 10. Model explanations and the age-specific vacancy label

Code: `modeling/explain.py`. Figures: `thesis/figures/shap_residential.*`, `thesis/figures/shap_vacancy_private.*`. Values: `reports/shap.json`, mean absolute SHAP value per feature.

**Residential classifier.** The largest contributions come from whether the footprint is mapped in OSM (1.42), whether it stands on residential land (1.41), the number of address points inside it (1.17), and the number of buildings within 300 m (0.79) and 100 m (0.70); footprint area follows (0.67). The model separates dwellings mainly by context and addressing, not by the shape of the building alone.

**Vacancy among private preschools.** The largest contribution comes from children per preschool within 1 km (0.20), followed by whether the organisation runs Russian-language groups (0.16), children per preschool within 500 m (0.15), the distance to the nearest other preschool (0.14) and the number of preschools within 500 m (0.13). Demand pressure is the leading feature even though, as section 6 showed, the gain it brings in prediction is small.

**Age-specific label.** A second label marks organisations with free places in groups for two- and three-year-olds, where waiting is longest: 276 of 728 organisations. Among private organisations, logistic regression reaches ROC-AUC 0.629 on own characteristics and 0.646 with demand pressure, against 0.574 and 0.610 for the any-age label. The age-specific label is easier to predict, but demand pressure adds less to it. Single-year age counts, which would allow a proper match of groups and children, are not available below the five-year WorldPop cohorts.

## 11. Correction of 5 October 2026: programme schools from the 2GIS listing

Code: `validation/listing.py`, `inventory/programme_list.py`, `accessibility/coverage.py`. Input: `data/raw/team/astana_spatial_inequity.xlsx`, a listing of residential complexes and schools compiled from 2GIS by a member of the team. Output: `reports/listing_check.json`. The values below replace those of sections 1, 3, 7, 8 and 9 wherever they differ.

### What changed

| Site | Before | After |
|---|---|---|
| P07, school 105 | Street crossing of Ulytau and Nauryz, medium confidence | Listed position at Ulytau 48, 1.07 km away |
| P17, school 116 | Crossing of Tulebaev and Burabai, number unknown | Listed position at Mukan Tulebaev 3, 235 m away; number 116 confirmed by a krisha.kz listing |
| P13, school 112 | Unnamed ground near Otau, number unknown | Same ground; the listing of school 112 lies 7 m from it |
| P02, P20, P23 | Medium confidence | High: listings of schools 100, 115 and 118 lie within 79 m |

All 21 located sites are now located with high confidence. Two built schools that OSM does not map, 105 and 116, were missing from the 2026 supply; they are now added with the floor area per seat of the mapped programme schools.

### Effect on results

| Result | Before | After |
|---|---|---|
| Schools within 500 m, straight line / walking | 60.3% / 20.5% | 60.7% / 20.6% |
| School access, Esil and Nura, share of city mean | 0.73 / 0.73 | 0.71 / 0.71 |
| School access, Almaty / Baikonur | 1.06 / 1.14 | 1.13 / 1.11 |
| School Gini / Theil / between share | 0.395 / 0.284 / 11% | 0.390 / 0.275 / 12% |
| Low-low school clusters, Esil / Nura | 4.4% / 2.0% | 4.7% / 2.4% |
| H3, schools, district rank correlation median (buildings / WorldPop) | 0.91 / 0.77 | 0.89 / 0.86 |
| Catchment check, assigned school nearest / in two nearest | 57.3% / 67.8% | 52.4% / 66.4% |
| H4, deficit AUC 1 km / 1.5 km | 0.63 / 0.64 | 0.61 / 0.64 |
| H4, deficit minus density, 1 km | +0.18 (+0.02 to +0.29) | +0.15 (-0.00 to +0.27), positive in 97% |
| H4, sites with a feasible plot in 2023 | 13 of 21, AUC 0.67 | 14 of 21, AUC 0.69 |
| Programme, children reached 1 km / 1.5 km | 17,197 / 11,649 | 15,844 / 11,418 |
| Programme over land-feasible optimum | 90% / 67% | 83% / 66% |
| Programme over unconstrained optimum | 38% / 46% | 35% / 45% |
| Programme percentile among random choices | 96.5 / 95.0 | 91.5 / 94.5 |

Preschool results do not change. The direction of every hypothesis is unchanged. The first part of H4 is weaker: the bootstrap interval of the difference between deficit and density now touches zero at both distances.

### Checks against the listing

| Check | Result |
|---|---|
| School numbers in both sources | 104; median distance 32 m, 97% within 150 m |
| Numbers only in the listing | 9, 39, 81, 82 (selective or evening, excluded by design); 100, 105, 106, 112, 116 (programme); none unexplained |
| Residential complexes inside a footprint | 1,584 of 2,022; 91.7% classed as dwellings |
| Recall on buildings decided by the model alone | 77.9% of 551, against 80.5% in the house-list transfer test |
| Floors where OSM has a tag | MAE 1.9, bias -0.3 |
| Floors imputed | MAE 4.4, bias -1.9 over 438 buildings |
| Population with listed floors for those 438 buildings | district ranking unchanged for both facility types, largest district change 0.003 of the city mean, 99% of worst-served cells unchanged |

Not used from the listing: walking distances to the nearest school (computed on the same OSM network and including private schools), bus stops, parking and entrance counts. The 351 complexes marked as under construction are not used; the listing does not state how complete it is.

## 12. Update of 5 October 2026: official age structure and six district totals

Population model updated as in section 8 of `s2b_population.md`. The values below replace earlier ones.

| Result | Before | After |
|---|---|---|
| Compliance, city, school 500 m straight / walking | 60.7% / 20.6% | 60.8% / 20.6% |
| Compliance, city, preschool 300 m straight / walking | 76.3% / 33.6% | 77.9% / 34.7% |
| Schools, access relative to mean: Almaty, Baikonur, Esil, Nura, Saraishyk, Saryarka | 1.13, 1.11, 0.71, 0.71, 0.94, 1.38 | 0.88, 1.30, 0.70, 0.72, 1.12, 1.46 |
| Same with the combined age share of Almaty and Saraishyk | - | 1.06, 1.31, 0.69, 0.71, 0.80, 1.45 |
| Preschools, same order | 1.59, 0.64, 1.08, 0.90, 1.01, 0.79 | 1.17, 0.99, 0.94, 0.83, 1.25, 0.94 |
| Preschools with combined share | - | 1.43, 1.01, 0.94, 0.83, 0.83, 0.95 |
| Gini schools / preschools | 0.390 / 0.460 | 0.398 / 0.435 |
| Theil share between districts | 12% / 11% | 16% / 3% |
| Low-low clusters, share of children | 11.1% / 9.6% | 10.8% / 8.2% |
| H3 schools, worst district | Nura 30, Esil 6 | Nura 28, Esil 8 |
| H3 preschools, worst district | Baikonur 36 | Saryarka 16, Nura 12, Baikonur 8 |
| H3 district rank correlation, median, buildings | 0.89 / 0.94 | 0.94 / 0.57 |
| Vacancy, private, logistic with pressure | 0.610 | 0.595 |
| Vacancy, pressure coefficient and 95% interval | -0.16 (-0.35, 0.02) | -0.09 (-0.26, 0.08) |
| H4, school-age children 2023 | 251,355 (modelled share) | 236,457 (official) |
| H4, deficit AUC 1 km / 1.5 km | 0.61 / 0.64 | 0.62 / 0.63 |
| H4, deficit minus density | +0.15 / +0.18 | +0.17 (+0.03, +0.30) / +0.19 (-0.00, +0.36) |
| Programme over land-feasible optimum | 83% / 66% | 89% / 64% |
| Programme over unconstrained optimum | 35% / 45% | 33% / 43% |
| Programme percentile among random choices | 91.5 / 94.5 | 81 / 89 |

Consequences. For schools nothing qualitative changes: Esil and Nura remain the worst served. For preschools the deficit of Baikonur was an artefact of the uniform age structure: Baikonur has the smallest share of preschool children in the city. Under the official structure the districts are close, Nura lowest at 0.83, and 97 per cent of inequality lies within districts; H2 is not supported for preschools, and H3 holds for them only at the cell level.

## 13. Update of 5 October 2026: official tables downloaded from stat.gov.kz

Files in `data/raw/stat/astana/`, checks in `validation/official.py` and `reports/official_checks.json`.

The official single-age table differs from the copy used in section 12 for past years: the Bureau recomputes the series of every district in its present boundaries, with Nura and Saraishyk from 2022. The 2026 values are identical. The 2023 reconstruction now uses six districts (Almaty 202,962, Saraishyk 163,827, Esil 236,086, Nura 173,179, Saryarka 345,226, Baikonur 233,282) and their own age shares. In 2023 Saraishyk had 13.7% preschool children and Almaty 14.2%, which confirms that the 2026 split (8.1% and 19.8%) is an anomaly of that year.

H4 after the change: deficit AUC 0.62 / 0.64, density 0.45 / 0.45; difference +0.17 (+0.01, +0.30) and +0.19 (+0.01, +0.36). Programme 14,083 / 10,395 children; optimum anywhere 42,423 / 23,960; on feasible plots 16,304 / 16,271; programme at 86% / 64% of the land-feasible optimum and 33% / 43% of the unconstrained one; percentile among random choices 86 / 92.

City checks:

| Check | Value |
|---|---|
| Pupils in day schools, 2025/26 | 311,282, against 310,892 children aged 7-17 on 1 January 2026 |
| General schools, all types, 2025/26 | 208 (state catchment schools in the inventory: 111) |
| Preschool organisations, 2025 | 737: 122 state, 615 private (register, September 2026: 790) |
| Preschool places / children, 2025 | 80,521 / 63,637, 79 children per 100 places |
| Attendance over children aged 1-6 | 31% |
| Births 2019 to 2025 | Baikonur 4,648 to 2,707; Saryarka 7,405 to 5,357; Nura 6,103 in 2025, the most of any district |

The tables of places commissioned end in 2021 and 2024 and do not cover the programme; they are not used. The gross enrolment tables are in the old xls format and are not parsed.

## 14. Current edition of the planning standard

SP RK 3.01-101-2013 with amendments as of 2 June 2025, official publication of the Unified State Fund of Normative Technical Documents (`data/raw/norms/sp_rk_3.01-101-2013_2025-06-02.pdf`). Table 2-1 (radius 300 m for urban preschools, 500 m for schools, up to 10% more in complex layouts, transport access 15 and 50 min) and Table V.1 (provision norms, school plot 19 sq m per pupil above 900 pupils) are unchanged from the edition of 9 July 2021. New in note 2 to Table 2-1: the walk of primary pupils must not cross a main road at grade. The Astana norms SNiP RK 3.01-01As-2007 (amendments as of 15 May 2019, official edition 2023) set walking access of 300-500 m for everyday facilities, including preschools and schools. No result changes.

## 15. Official reply of 8 October 2026: school service territories

Files in `data/raw/official_reply/` (not in git): population of districts 2023-2026 and children 0-17 by single year of age (identical to the Bureau tables downloaded in section 13, within 2 persons), the two joint decisions on the Saraishyk district, and the service territories of all 121 schools with catchment admission in six district files. The reply contains no capacity, enrolment or shifts.

Code: `ingest/catchments.py` (parser and geocoder), `accessibility/official_catchments.py`, `data/labels/catchment_overrides.csv`. Output: `reports/official_catchments.json`, `data/interim/catchments_geocoded.csv`, `data/interim/catchment_dwellings.csv`.

### Parsing and matching

| Item | Value |
|---|---|
| Schools in the reply | 121 (115 numbered, 6 Binom schools named) |
| Parsed entries | 8,938: 8,272 houses, 254 ranges, 373 whole streets, 39 named places |
| Single houses geocoded exactly | 77% (Almaty 88%, Saryarka 79%, Baikonur 76%, Esil 75%, Nura 59%, Saraishyk 51%) |
| Address points after expanding ranges and streets | 19,690 |
| Dwellings assigned, within 25 m | 13,764, of which 1,140 to more than one school (classes by language) |
| School-age children in assigned dwellings | 57% (Almaty 65%, Baikonur 63%, Saryarka 63%, Esil 60%, Saraishyk 44%, Nura 41%) |

### Supply corrected

Every numbered school in the reply is in the supply layer or among programme schools. Changes: six Binom schools (private, financed by state order) and Daryn lyceum 82 have service territories and enter the supply; complex 47 (kindergarten-school) has none and leaves it. Binom named after Bokeikhan is absent from OSM and placed from the 2GIS listing. All Binom buildings were mapped in OSM on 1 January 2023 and enter the 2023 supply too.

### Assigned school against walking distance (children-weighted)

| Measure | Value |
|---|---|
| Assigned school reached within 4 km | 98.5% |
| Assigned school is the nearest | 61.5% |
| One of the two nearest | 82.9% |
| Median walk to the assigned school | 786 m |
| Within 500 / 1000 / 1500 / 2000 m | 19.6% / 67.6% / 87.7% / 94.9% |
| Within 1 km, by district | Baikonur 82%, Saryarka 74%, Almaty 73%, Saraishyk 63%, Esil 58%, Nura 52% |

### Load step

Spearman correlation between children assigned to each school and the load allocated by the index, 115 schools: allocation within 1.5 km 0.63, 2 km 0.63, 3 km 0.62, 4 km 0.63; original E2SFCA first step 0.58. Allocating each child once describes school loads better; the radius barely matters. Assigned children over model load, median 0.53, because only 57% of children could be matched.

### Effect of the supply correction on results

| Result | Before | After |
|---|---|---|
| School access relative to mean: Almaty, Baikonur, Esil, Nura, Saraishyk, Saryarka | 0.88, 1.30, 0.70, 0.72, 1.12, 1.46 | 0.80, 1.13, 0.97, 0.83, 1.27, 1.22 |
| Same with combined age share of Almaty and Saraishyk | 1.06, 1.31, 0.69, 0.71, 0.80, 1.45 | 0.97, 1.15, 0.95, 0.82, 0.90, 1.21 |
| School Gini / Theil / between share | 0.398 / 0.284 / 16% | 0.380 / 0.256 / 6% |
| Low-low school clusters, Esil / Nura | 4.8% / 2.3% | 3.4% / 1.3% |
| Compliance, school 500 m straight / walking | 60.8% / 20.6% | 63.9% / 22.1% |
| Walking compliance Esil / Nura | 18.8% / 9.7% | 22.3% / 13.7% |
| H3 schools, worst district (buildings) | Nura 28, Esil 8 | Nura 20, Almaty 16 |
| H4 deficit AUC 1 km / 1.5 km | 0.62 / 0.64 | 0.59 / 0.57 |
| H4 deficit minus density | +0.17 (+0.01, +0.30) / +0.19 (+0.01, +0.36) | +0.14 (-0.03, +0.29) / +0.13 (-0.08, +0.32) |
| H4 land-feasible plot AUC | 0.69 | 0.69 (0.59, 0.79) |
| Programme over land-feasible optimum | 86% / 64% | 87% / 56% |
| Programme over unconstrained optimum | 33% / 43% | 29% / 38% |
| Percentile among random choices | 86 / 92 | 74 / 87 |

Preschool results do not change. H2 for schools becomes partial: Nura stays lowest wherever the age structure is plausible, Esil moves to the mean but keeps the largest cluster. H4 part 1 keeps its direction but the deficit-density difference is no longer significant; land availability is the significant predictor.

## 16. Audit of processed data, 12 October 2026

Script-based checks of every processed layer (counts, totals against official figures, ranges, ids, point positions, distances against the straight line). All passed except one finding, fixed below.

| Layer | Check | Result |
|---|---|---|
| facilities | 117 schools with territory, 790 preschools (728 placed), all points inside the city, ids unique | ok; school number 45 appeared twice (fixed) |
| buildings | 93,507 unique ids (50,095 OSM, 43,412 Microsoft), p in [0, 1] | ok; 43,123 classed residential, of which 3,388 under 35 sq m are excluded from dwellings by rule |
| dwellings 2026 | 39,735; three surfaces sum to 1,639,176; every district equals its official total | ok |
| dwellings 2023 | 36,714, a subset of 2026; total 1,354,562 equals the sum of six official districts (city figure 1,354,559) | ok |
| grid | 6,710 H3 cells; all four surfaces sum to 1,639,176; children 1-6 and 7-17 within 0.3% of official age counts | ok |
| network | 155,433 nodes stored, 152,491 (98.1%) in the connected component used | ok |
| OD | distances 19-4,000 m; walk never shorter than the straight line (median ratio 1.35 on a 20k sample) | ok |
| access cells | 1,307 cells, no NaN or negative values | ok |
| polling | 422 stations, 386 territorial, 247 polygons | ok |
| free land 2023 | 10 m raster, EPSG:32642; 186 feasible plots after the supply corrections (191 before) | ok |
| catchments | 13,764 dwellings, 115 schools, all ids valid | ok |

**School 45.** OSM carries two objects named school 45: an old building in Esil (sch0072, 4,011 sq m, linked to the stale egov register) and a new building in Nura (sch0078, 27,650 sq m) at Tole bi 25/2, which the official list of service territories, the 2GIS listing and the company register give as the school's address. The Esil object is now excluded (`data/labels/catchment_overrides.csv`). Before the fix, the official catchment of school 45 had been matched to the Esil object 4 km away.

Whether the new building already operated on 1 January 2023 is not known; OSM history is too incomplete to tell (it also misses buildings of schools 2, 8, 12, 25 and 30, which are old). H4 under both readings:

| 2023 school 45 | Deficit AUC 1 km | Difference to density, 1 km | Programme over land-feasible optimum, 1 km |
|---|---|---|---|
| New building in Nura (baseline) | 0.62 | +0.17 (+0.01, +0.31) | 90% |
| Old building in Esil | 0.59 | +0.14 (-0.03, +0.29) | 86% |

At 1.5 km the difference is not significant in either reading. The thesis reports H4 part 1 as holding in direction but not robustly.

Other changes from the fix: school access Esil 0.97 to 0.92, Nura 0.83 to 0.84; between-district share 6% to 7%; load correlation with assigned children 0.62 to 0.63, original first step 0.58 to 0.60; programme at 90% / 56% of the land-feasible optimum, 33% / 38% of the unconstrained one, percentile 86 / 87 among random choices.

## 17. Construction plan for 2026-2028, 12 October 2026

Source: reply of the Construction Department of Astana, letter ZhT-2026-04463590 of 8 October 2026, with the table of 25 school projects (`data/raw/official_reply_2/`). Transcribed to `data/labels/planned_schools_2026_2028.csv`; code `src/astana_access/optimization/plan.py`; output `reports/plan_2026_2028.json`, layers `plan_2026_2028` and `plan_optimal_{1000,1500}` in `data/processed/backtest.gpkg`, figure `plan_2026_2028_1000`.

Plan: 25 projects, 70,316 places in two shifts (2026: 4 projects, 8,150; 2027: 12, 29,566; 2028: 9, 32,600). 18 new schools (61,198), 3 extensions (3,550), 4 new buildings for existing schools (5,568). The official table's 2027 total row shows `#REF!` and "14 projects"; the 12 listed rows are used.

Location: 24 of 25 placed (14 high, 4 medium, 6 low confidence). N24 (Nazhimedenov x A90) not placed: street A90 absent from OSM and from all address lists. Street C189 (N25) is not in OSM; the fuzzy match had picked a wrong street, so N25 is placed at the middle of Zemlyanichnaya street in the dacha area of the same name.

Coverage of children without a school within walking distance, demand of 2026, new schools only (extensions and rebuilds do not change walking coverage):

| | 1 km | 1.5 km |
|---|---|---|
| Without a school, 2026 | 76,542 | 19,830 |
| Reached, 2026 (1 site) | 165 | 18 |
| Reached, to 2027 (9 sites) | 7,829 | 3,131 |
| Reached, to 2028 (17 sites) | 11,145 | 3,780 |
| Without 6 low-confidence sites | 8,291 | 3,398 |
| Optimum anywhere, 17 sites, mean planned capacity | 38,917 | 14,637 |
| Optimum on feasible plots, 17 sites | 9,379 | 8,443 |
| Deficit AUC (95% CI) | 0.54 (0.38-0.69) | 0.49 (0.33-0.65) |
| Density AUC | 0.55 (0.42-0.66) | 0.50 (0.38-0.60) |

Capacity never binds. Remaining in 2028 at 1 km by district: Esil 20,728 (from 21,521), Nura 13,563 (19,032), Saryarka 11,525 (12,689), Almaty 8,657 (10,517), Baikonur 6,733 (6,733), Saraishyk 4,011 (5,870). Places by district: Saraishyk 22,800, Nura 20,998, Esil 10,800, Saryarka 9,918, Almaty 4,000, Baikonur 1,800.

Per site, uncovered children within 1 km: N06 2,825, N10 2,799, N07 1,860, N25 1,165, N12 981, N13 940, N21 919, N20 605, N18 369, N05 318, N17 259, N01 165, N19 132; N08, N11, N22 and N23 reach none (inside areas already covered; they would relieve crowded schools). N12 and N19 have few children around today (981 and 132 within 1 km in all), i.e. they anticipate housing.

Low-low clusters (school E2SFCA, p < 0.05): 28,626 children, of them 3,513 (12%) within 1 km of a planned new school; Esil holds 10,926.

E2SFCA with the plan (added floor = places / 2 x 13.35 sq m, the median floor per place of programme schools; extensions add, rebuilds take the larger of old and new): mean access +37%, zero-access share 6.3% to 5.1%, Gini 0.378 to 0.391. District relative: Nura 0.84 to 1.08, Saraishyk 1.28 to 1.64, Saryarka 1.24 to 1.09, Baikonur 1.15 to 0.85, Esil 0.92 to 0.96, Almaty 0.81 to 0.73.

Reading: for future decisions the first part of H4 does not hold; the plan is not targeted at the deficit. The plan beats the optimum on currently free plots (119% at 1 km) because it uses land the layer counts as built (for example the garage cooperative on Tokpanov street).

## 18. Official list of schools, 15 October 2026

Source: reply of the Education Department of Astana, letter ZhT-2026-04418142/1 of 14 October 2026 (`data/raw/official_reply_3/schools.xlsx`, not in git: the letter holds personal data). 122 state and 76 private schools with district, address, design capacity, enrolment 2025-2026 and 2026-2027, shifts, year of commissioning and the mark "KSh" for Comfortable School buildings. Preschool data were not given; the department refers to the INDIGO system. The second reply of the Bureau (ZhT-2026-04428341 of 14 October 2026) only points to the dynamic tables already used. Code: `ingest/school_register.py`, `validation/register.py`; output `data/interim/school_register.csv`, `reports/school_register_check.json`.

**Linking.** 115 of 122 state rows by number, 5 Binom schools by name. Unlinked state rows: two boarding lyceums Bilim-innovation, specialised lyceum 9, evening school 39, school 47 and school 120 (no service territory), international school 81. Supply entries without a row: Binom Satpayev (sch0061) and two presumed new school grounds; their capacity is estimated from floor area (median capacity per sq m).

**Positions.** Official addresses geocode to a median of 25 m from our positions (105 geocoded, 80% within 100 m). Eight are more than 400 m apart; six of them (15, 16, 21, 43, 69, 105) are confirmed at our position by the 2GIS listing, so the official address differs from the building; schools 25 and 36 share one official address and one 2GIS address. School 118: official address E-899 8 (same as 117, opened 2026, no pupils in 2025-2026), while OSM and 2GIS place it elsewhere; kept at the OSM/2GIS position.

**Capacity and crowding.** 162,344 places, 273,340 pupils in 2025-2026 (294,751 in 2026-2027), 1.68 pupils per place; 109 of 120 schools in two shifts, 11 in one. 45 schools enrol more than twice their capacity; 49% of pupils attend them; 18,486 pupils beyond two shifts.

| District | Places | Pupils 2025 | Pupils per place | Growth to 2026 | Pupils in schools beyond two shifts | Pupils beyond two shifts |
|---|---|---|---|---|---|---|
| Almaty | 27,143 | 46,400 | 1.71 | +3.6% | 22% | 893 |
| Baikonur | 16,454 | 25,434 | 1.55 | -0.6% | 38% | 1,184 |
| Esil | 30,742 | 50,478 | 1.64 | +10.6% | 58% | 3,226 |
| Nura | 31,700 | 50,086 | 1.58 | +17.2% | 54% | 2,876 |
| Saraishyk | 21,432 | 42,621 | 1.99 | +11.2% | 75% | 6,445 |
| Saryarka | 34,873 | 58,321 | 1.67 | +1.9% | 43% | 3,862 |

**Proxy.** Floor area vs capacity: Spearman 0.64; floor vs enrolment 0.39; capacity vs enrolment 0.54. Design capacity is now the baseline school supply; floor area and equal weight are sensitivity alternatives (72 school runs).

**Load step against enrolment (119 schools).** Allocated load: Spearman 0.55; original first step: 0.38. District error of allocated load vs enrolment under the official age split: Almaty +38%, Saraishyk -32%; with the combined Almaty+Saraishyk school share: +11% and -6%, Spearman 0.60. Enrolment supports the combined share.

**Comfortable School.** The list marks 23 buildings: 33, 45, 99-119; 42,400 places; opened 14 in 2024, 8 in 2025, 1 in 2026. 33 and 45 match in year and district the two announced sites P14 and P19 we could not locate. The programme in H4 is now this list with official capacities (`backtest.official_programme`). The 2023 city drops schools 94-97 (opened 2023 or later, organisations registered from 2022) and uses the old Esil building of school 45 (`data/labels/former_buildings.csv`), which settles the school 45 question of section 16.

**Changed results.** School access relative to the city mean: Nura 0.84 to 0.77, Esil 0.92 to 0.82, Almaty 0.81 to 0.87 (combined share 1.05), Saraishyk 1.28 to 1.33 (0.94), Baikonur 1.15 to 1.24, Saryarka 1.24 to 1.27. Gini 0.378 to 0.380, between-district share 7% to 9%, LL children 9.2% to 10.0% (Esil 4.6%). H4 with 23 schools: deficit AUC 0.59 at both radii (0.45-0.72), density 0.42, difference +0.16 (0.00, +0.31) and +0.17 (-0.03, +0.37); land AUC 0.71; programme 12,496 / 8,375 children, 84% / 60% of the land-feasible optimum, 30% / 42% of the unconstrained one, percentile 66 / 96 among random choices. Plan 2026-2028: places by district follow pupils beyond two shifts (Spearman 0.71 over six districts) rather than children without a school within 1 km (0.09); at cell level crowding does not single out planned sites (AUC 0.49 and 0.58).

## 19. Design capacity of preschools from the INDIGO cards, 15 October 2026

Source: the public organisation cards of the INDIGO register (`https://indigo-nursultan.e-orda.kz/ru/view/<id>`), compiled by members of the project team and the supervisor between 12 and 15 October 2026 (`data/raw/indigo/cards_2026-10-15/`). Not an official reply. A Word file presented with it as a letter of the Bureau of National Statistics was the Bureau's reply ZhT-2026-04428341 edited on 15 October 2026 (revision 54, last modified by the student, three paragraphs replaced); it is not used or cited anywhere. Code: `ingest/preschool_capacity.py`; check `reports/preschool_capacity_check.json`.

**Checks.** 794 cards with capacity (790 in the register of 30 September, 5 new, 1 gone). Ownership and address agree with the register for every organisation. Free places exceed capacity for one organisation. Places: 29,939 state, 43,480 private, 73,419 in all, for 29,429 and 36,973 attending children (0.98 and 0.85 children per place). Free places on 30 September were 1.4% of state and 10.3% of private places. Typical values: 280 places for nursery-kindergartens of the standard project, 30 for mini-centres. Capacity does not correlate with OSM floor area (Spearman 0.02, 105 buildings).

**Use.** Design capacity is the baseline preschool supply (`e2sfca.preschool_capacity`; missing values by ownership median); mean attendance and equal weight are alternatives (72 runs per facility type). Vacancy model: capacity added to the own characteristics; children per place within 500 m and 1 km replace children per preschool.

**Changed results.** Preschool access relative to the city mean: Nura 0.83 to 0.77, Esil 0.94 to 0.87, Baikonur 0.99 to 0.91, Saryarka 0.94 to 1.01, Saraishyk 1.25 to 1.18 (combined share 0.79), Almaty 1.17 to 1.27 (1.57). Gini 0.435 to 0.454, between-district share 3% to 5%, LL children 8.2% to 8.9%. Sensitivity: Nura worst in 24 of 54 building runs (12 of 18 with capacity), Saryarka in the 16 equal-weight runs, Baikonur in 14; rank correlation median 0.77, minimum -0.09. Vacancy ROC-AUC, own / with pressure: all logistic 0.707 / 0.708, LightGBM 0.736 / 0.712; private logistic 0.677 / 0.669, LightGBM 0.678 / 0.640. Capacity is the largest SHAP contribution (0.48). Pressure coefficient (children per place within 1 km, private, standardised) -0.087, bootstrap interval -0.27 to 0.11. Free places: 69% below and 65% above the median pressure.

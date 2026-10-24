# Likely committee questions and short answers

Answers use the numbers of the thesis as of 16 October 2026. Backup slides B1-B5 support the questions marked with them.

## Data

**1. Why not use official population data below the district level?**
None is published. The Bureau publishes districts only, and in reply to our request it referred us to the same district tables. So we reconstructed it and tested the reconstruction against the six official district totals (H1).

**2. Why polling stations? (B1)**
The akim's decision is a legal document that assigns every address to one of 386 territorial stations, and stations are formed with similar numbers of voters. The station count of an area is therefore an official signal of registered residents. With it the district error is 10 per cent, against 26 for WorldPop and 28 for floor area alone.

**3. Registered residents are not actual residents. Is that a problem?**
Yes, partly: people registered in one place may live in another, especially in new housing. That is why the station level is tempered by floor area (alpha = 0.2), and why every result is repeated with alpha = 0, with floor area alone and with WorldPop (H3). The cell-level deficit is stable across the building-based surfaces (overlap about 0.8).

**4. Why did you replace the official age split of Almaty and Saraishyk? (B4)**
The 2026 series gives Saraishyk, a district of new housing, 8 per cent preschool children and Almaty 20, while in 2023 it gave both about 14. Official school enrolment decides: under the official split the model gives Almaty 38 per cent more pupils than are enrolled and Saraishyk 32 per cent fewer; under the combined share 11 and 6 per cent. Results under the official split are reported in brackets.

**5. How were the team-collected data obtained, and is that legitimate? (B5)**
Official data came as replies to information requests through eGov. The preschool register forbids crawling, so its list was saved by hand. The INDIGO organisation cards, the geoportal layer and 2GIS listings were compiled by the team; they are used to check and to locate, and no personal data are used. [Confirm with the team how they were collected before the defence.]

**6. Can the results be reproduced?**
Yes: one command runs the thirteen pipeline stages from the raw sources, the last of which publishes the web atlas; 116 unit tests cover parsing, allocation, the index, inequality, optimisation and the uncertainty simulation. Letters with personal data are kept out of the repository.

## Method

**7. Why the floating catchment index and not distance to the nearest school? (B2)**
Families are not assigned to the nearest school: the official service territories send four children in ten past a nearer one. The index lets a child reach every school within 1.5 km and accounts for each school's capacity and load.

**8. What did you change in the index, and does it help? (B2)**
Each child is allocated once among the schools within 3 km instead of being counted at every school. Against official enrolment of 119 schools the allocated load correlates at 0.60, the original method at 0.41.

**9. Why 1.5 km and a Gaussian decay?**
1.5 km is about 20 minutes on foot. The sensitivity analysis varies the catchment (1 and 1.5 km for schools), the decay (Gaussian, linear, step) and the supply measure; the deficit cells hardly move.

**10. Why walking distance rather than the straight line the planners use?**
The standard does not say which is meant. The difference is large: the 500 m norm is met for 64 per cent of school-age children in a straight line and 22 per cent on foot; the walk is a median 1.41 times the line.

**11. How do you check the residential classifier?**
Spatial cross-validation with 1 km blocks gives ROC-AUC 0.982 and F1 0.922. It recovers 80.5 per cent of houses named in legal house lists that it never saw as labels, and 91.7 per cent of 2GIS residential complexes.

## Results

**12. Is H2 confirmed or not?**
In part. For schools the two growth districts are the worst served (Nura 76, Esil 81 per cent of the mean), and Nura is worst in all 54 building-based runs. For preschools Nura is lowest (77) with Saraishyk close (79). But over 90 per cent of inequality lies within districts, so the deficit is a matter of blocks rather than districts.

**13. What does "places exist but not near every child" mean for preschools?**
The register counts 73,419 places for 66,574 children, and only 210 children aged two or older are in the net waiting list. Yet only 34 per cent of preschool-age children live within 300 m on foot. The problem is location, not quantity.

**14. Schools have 1.7 pupils per place: isn't that a shortage of places, not of location?**
Both exist. Crowding peaks in Saraishyk (2.0 pupils per place), the walking deficit in Esil and Nura. The thesis treats them as separate deficits.

**15. Was the Comfortable School programme well sited? (B3)**
It went where land was free (ROC-AUC 0.71); deficit points the right way (0.59 against 0.42 for density) but with 23 sites the difference is borderline. On land free in 2023 it reached 84 per cent of the optimum within 1 km; without a land limit the optimum is 3.4 times higher.

**16. How was 2023 reconstructed?**
From the OpenStreetMap history as of 1 January 2023: buildings, land use and schools of that date, with the official 2023 district population and age shares. The official list of schools corrected it: schools 94 to 97 opened later, and school 45 was still in its old building.

**17. What about the 2026-2028 plan?**
It reaches 15 per cent of the 77,870 children without a school within 1 km. Planned places by district follow pupils beyond two shifts (0.71) more than the walking deficit (0.60).

**18. What is the practical recommendation?**
The detailed plans already hold 238 school sites. Choosing the 17 of them that reach the most children without a school would reach 2.4 times as many as the plan. The framework produces that ranking.

**18a. How certain are these numbers?**
We propagated the error of the population surface by a Monte Carlo simulation of 200 draws: the allocation exponent, the size of every polling station (a spread large enough to explain the whole 10 per cent district error) and the dwellings the classifier decided. 90 per cent intervals: statutory radius met on foot for 20-24 per cent of school children; 68-87 thousand children without a school within 1 km; the plan reaches 8-16 thousand, the same 17 reserved sites 24-37 thousand, 1.9-3.4 times as many and more than the plan in every draw. Nura or Esil is the worst-served district for schools in 199 of 200 draws.

**18b. The plan opens by 2028, but you measure 2026 demand. Isn't that unfair?**
We projected 2028 from the official single-age tables with cohort change ratios of 2024-2026 (Hamilton-Perry). The school-age population grows from 311 to 333-374 thousand by 2028 and to 355-447 thousand by 2030; children without a school within 1 km grow from 78 to 84-99 thousand by 2028, or 106 thousand when new housing is placed in the estates being built. The plan still reaches 15-17 per cent of them, and the best reserved sites 2.2-2.4 times as many. The projection keeps the present pattern within districts, so new housing after 2026 is not placed.

**18c. Can machine learning predict where schools should be built?**
Not directly: the only examples of chosen sites are the city's own choices, and H4 shows they followed free land, so a model trained on them would learn the same habit. We use ML for two honest tasks instead. A model of the city's choices (logistic regression and LightGBM, leave-one-district-out validation) confirms that free land, not the deficit, explained the programme (ROC-AUC 0.71) and shows that the 2026-2028 plan follows construction sites: 16 of its 17 new schools stand within 500 m of land under construction (ROC-AUC 0.76). A LightGBM forecast of new housing, tested on 2023-2026 after training on 2020-2023, places the children of 2028 in the estates being built; the optimisation then chooses sites on that demand. The ranking of reserved sites barely changes: 14 of the 17 best sites stay the same.

**18d. Does the housing model beat a simple rule?**
Only partly, and we say so. It finds where housing appears better (ROC-AUC 0.94 against 0.92 for "construction continues where it was"), but the simple rule captures slightly more of the new floor area in its top tenth of cells on the temporal test (81 against 76 per cent). The training period is weakened by OSM: much of what appears in 2017-2020 is old housing mapped late.

**18e. The plan answers crowding. Doesn't your ranking ignore it?**
No. We scored every reserved site on both goals: children with no school within 1 km, and pupils of schools beyond two full shifts who live within 1 km of the site. Every set of 17 sites on the trade-off line beats the plan on both goals at once. Even the set chosen only for crowding offers a nearby place to 7,400 pupils of overcrowded schools against 2,800 for the plan, and still reaches 14,200 children without a school against 11,900. A balanced choice reaches 25,200 and 6,000. Fifteen reserved sites are in the top quarter on both goals. The atlas lets the user switch between distance, crowding and both.

**18f. How many people and children will Astana have by 2030?**
We projected the official single-age tables with the Hamilton-Perry method, for the city as a whole and with districts taking their share. By 2030 the city has 1.75 million people if nobody moves in, 2.06 million if the average change of 2022-2026 continues, and 2.15 million at the pace of 2024-2026. School-age children grow from 311 to 355-447 thousand, preschool-age children stay at 174-222 thousand against 207 now, because births have fallen since 2022. Tested on the past, the central scenario missed the city of 2026 by 2-4 per cent four years ahead. For districts the error is larger, and Nura grew faster than any trend predicted, so district figures are given as a range.

**18g. Which school does a child from a given block or residential complex attend?**
We cannot observe it. A gravity model lets each state school draw its official enrolment of 2025-2026 from the children within walking reach, in proportion to their number and to a decay of walking distance fitted to the official school territories (scale 0.25 km). The assigned school is its first choice for 67 per cent of children and among the first three for 94 per cent, a little better than a decay fitted without enrolment (66 and 94). In the flows 74 per cent of children attend the nearest school and 14 per cent walk more than 1 km. The flows do not reproduce the children of each dwelling: a median dwelling sends 32 per cent of its children to the schools that draw from it, which shows how far population by dwelling and enrolment by school still disagree. We present the flows as what enrolment implies, not as observed choices; the workbook of residential complexes lists, for every complex, the three schools that receive most of its children.

## Limitations and future work

**19. What are the main limitations?**
Sub-district population is an estimate; school territories could be matched for 56 per cent of children, too few to test population at that level; the status of detailed-plan sites is not published; preschool vacancy comes from one evening.

**20. What would you do next?**
Validate population with voters by station (requested), add the waiting list by district (requested), public transport and winter walking, and apply the framework to polyclinics and other cities.

**21. Where is machine learning essential, not decorative?**
The residential classifier decides which of 93,507 buildings receive population; without it 43,412 machine-detected footprints would have no type. The vacancy model tests revealed demand and shows that capacity, not demand pressure, explains free places so far.

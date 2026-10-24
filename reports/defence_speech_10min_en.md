# Defence speech, 10-minute version (English)

The same 18 slides as the full version, about 900 words: eight minutes of speech at a calm pace, which leaves two minutes for pointing at the slides and for the optional atlas demonstration. Times are targets; the running total is in brackets. Slides 5, 10 and 15 are the ones to move through quickly if time is short. The atlas demonstration is optional and replaces the second half of slide 13 (see `atlas_demo_script.md`).

## Slide 1. Title (0:15, 0:15)

Good morning, members of the committee. I am Dias Bolatov, and with my teammates Daulet Dandykulov and Arsen Baktygaliyev I present a data-driven framework for assessing walking access to schools and preschools and for siting new ones, applied to Astana. Our supervisor is Aidana Zhalgas.

## Slide 2. A city growing faster than its schools (0:40, 0:55)

Astana grew from 1.35 to 1.64 million people in three years. Schools have not kept up: the official list of schools counts 1.7 pupils per design place, and on foot only 22 per cent of school-age children live within the 500 metres the planning standard prescribes. Yet the data a planner needs — population below the district, the capacity of each school, the catchments — are not published. Our work shows how to obtain them and what they reveal.

## Slide 3. Aim and hypotheses (0:35, 1:30)

We built and validated a framework that measures walking access, diagnoses its inequality and evaluates siting. Four hypotheses: H1, open data estimate population below the district better than WorldPop; H2, deficits concentrate in districts of recent growth; H3, the pattern is robust; H4, the Comfortable School programme followed the deficit, and an optimal choice would reach more children.

## Slide 4. Data (0:30, 2:00)

Every estimate is built first from open sources — OpenStreetMap, ninety-three thousand building footprints, the akim's decision on polling stations and the age tables of the statistics bureau. Official replies to our information requests — the service territories of schools, the official list of schools, and the construction plan — were used to check and correct those estimates.

## Slide 5. Method (0:30, 2:30)

Five stages: population, walking distances on the street network, accessibility per child with a floating catchment index in which each child is counted once, inequality, and capacitated covering on free land. One command runs the whole pipeline, and one hundred and sixteen unit tests cover it.

## Slide 6. H1: polling stations beat the satellite grid (0:40, 3:10)

The akim's decision assigns every address to a polling station, and stations hold similar numbers of voters. Spreading the official district totals over these territories, our surface misses district populations by 10 per cent, against 26 for WorldPop. H1 is supported. We also use the official age structure of each district instead of one structure for the whole city.

## Slide 7. The norm on a map and on foot (0:35, 3:45)

As a straight line, the 500-metre norm is met for 64 per cent of school children; walked along streets, for only 22. For preschools, 77 against 34 per cent. The official catchments add that four children in ten are assigned past a nearer school.

## Slide 8. H2: the growing districts are worst served (0:40, 4:25)

With official design capacity as supply, Nura has 76 per cent of the city's mean access to schools and Esil 81 — the two growth districts are the worst served. But 92 per cent of inequality lies within districts: the deficit is a matter of blocks, which a district indicator cannot see. H2 is supported in part.

## Slide 9. Two deficits (0:35, 5:00)

The official list shows a second deficit: 45 of 120 schools enrol more than two full shifts can hold, most of all in Saraishyk. Crowding and walking distance are different deficits in different places. The same data validate our index: allocated load correlates with real enrolment at 0.60, against 0.41 for the original method.

## Slide 10. H3: robustness (0:40, 5:40)

Across 72 specifications Nura is the worst-served district for schools in every building-based run, and the worst-served fifth of children falls in the same cells, with an overlap of 0.8 — but only 0.14 with WorldPop. We also ran a Monte Carlo simulation of the population surface itself, 200 draws: Nura or Esil is the worst served in 199 of them. H3 holds.

## Slide 11. H4: the programme went where land was free (0:45, 6:25)

We rebuilt the city of 2023 from OpenStreetMap history. The programme's 23 sites are explained best by a free plot, ROC-AUC 0.71, not by the deficit or density. An unconstrained choice would have reached 3.4 times as many children; on land that was actually free the programme reached 84 per cent of the best. Land was the binding constraint.

## Slide 12. The plan answers crowding more than distance (0:45, 7:10)

The construction plan for 2026 to 2028 has 25 projects. Its 17 new schools reach 15 per cent of the 78 thousand children without a school within a kilometre. Projected to 2028, when the schools open, those children grow to between 84 and 99 thousand, and the plan still reaches only 15 to 17 per cent. Planned places follow crowding and construction sites: 16 of the 17 new schools stand next to land under construction.

## Slide 13. The land is already reserved (0:50, 8:00)

The city's detailed plans already reserve 238 school sites. Choosing 17 of them by the children each would reach gives almost 29 thousand children instead of 12 — 2.4 times the plan, and more than the plan in every Monte Carlo draw. What is missing is not land but an order of construction, and our atlas ranks the sites.

## Slide 14. Preschools: places exist, but not near every child (0:35, 8:35)

There are 73 thousand preschool places for 66 and a half thousand children, and the waiting list is almost entirely children under two. Yet only 34 per cent live within 300 metres on foot. It is a deficit of distribution, not of places.

## Slide 15. Machine learning (0:25, 9:00)

A LightGBM classifier decides which buildings are homes, ROC-AUC 0.982 under spatial cross-validation, and a second model tests which preschools publish free places.

## Slide 16. Conclusions (0:35, 9:35)

H1 is supported, H2 in part, H3 at the level of cells, H4 in direction. For the city: measure the norm on foot, plan by blocks, reserve land before housing surrounds it, and build first the reserved sites that reach the most children.

## Slide 17. Limitations (0:15, 9:50)

Population below the district remains an estimate, and we have requested voters by station, the waiting list by district and the status of reserved sites.

## Slide 18. Thank you (0:10, 10:00)

Thank you. I am ready for your questions.

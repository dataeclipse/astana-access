# Defence speech (English)

Speaker notes of the slides, in order. About 1,950 words, 13-14 minutes at a calm pace; for a 10-minute slot, shorten slides 5, 10 and 15. Backup slides B1-B5 are for questions only.

## Slide 1. Data-Driven Framework for Spatial Accessibility Assessment and Optimal Siting of Social Infrastructure

Good morning, members of the committee. My name is Dias Bolatov, and together with my team I present our diploma work: a data-driven framework for assessing spatial accessibility and siting of social infrastructure, applied to the schools and preschools of Astana. Our supervisor is Aidana Zhalgas.

## Slide 2. A city growing faster than its schools

Astana is one of the fastest-growing cities of Kazakhstan. Its population rose from 1.35 to 1.64 million in three years, and the new district of Nura grew by 23 per cent in 2025 alone. Housing is built faster than schools: the official list of schools we received counts 1.7 pupils per design place, and 109 of 120 state schools work in two shifts. On foot, only 22 per cent of school-age children live within the 500 metres the planning standard prescribes. Yet the data a planner needs for such questions — population below the district, the capacity of each school and kindergarten, the catchments — are not published. Our work shows how to get them and what they reveal.

## Slide 3. Measure access from open data, then test the siting

The aim of the work is to build and validate a framework that measures walking access to schools and preschools, diagnoses its inequality and evaluates where new facilities are placed. We tested four hypotheses. H1: that open data estimate population below the district level better than the standard gridded product, WorldPop. H2: that deficits concentrate in the districts of recent growth. H3: that this pattern is robust. And H4: that the sites of the national Comfortable School programme follow the deficit rather than density, while an optimal choice of sites would have reached more children. The right column previews the results, which I will now show one by one.

## Slide 4. Open data first, official replies as checks

We set ourselves one rule: real data only, and no result should wait for an official reply. So every estimate is first built from open sources: OpenStreetMap, ninety-three thousand building footprints, the akim’s legal decision on polling stations and the age tables of the statistics bureau. During the work we sent information requests, and the replies — the service territories of all schools, the official list of schools with capacity and enrolment, and the construction plan for 2026 to 2028 — were used to check and correct our estimates. The team also compiled preschool capacity from the INDIGO portal and the school sites of the city’s detailed planning projects.

## Slide 5. Five stages, one reproducible command

The framework has five stages. First, population: official district totals are spread over the territories of polling stations and then over dwellings, which a LightGBM classifier separates from non-residential buildings. Second, walking distances along a network of a hundred and fifty thousand nodes. Third, accessibility per child by an enhanced floating catchment index; our change is that each child is allocated to schools only once. Fourth, inequality: Gini and Theil indices and spatial clusters. Fifth, siting: a capacitated maximal covering model, restricted to land that is actually free. The whole pipeline runs with one command and is covered by ninety-seven unit tests, and every model is checked against data it did not use.

## Slide 6. Polling stations beat the satellite grid

The first result concerns population. Kazakhstan publishes population only by district, so we had to estimate it below that level. The akim’s decision on polling stations describes, by law, which houses belong to each station, and registered voters are spread fairly evenly across stations. Using these territories, our surface misses the official population of the six districts by 10 per cent on average, against 26 per cent for WorldPop and 28 per cent for floor area alone. WorldPop overstates the old Baikonur district by three quarters, while floor area overstates the new districts, where flats are not yet occupied. H1 is supported. We also replaced WorldPop’s single age structure with the official age counts of each district, which, as we will see, changes where the preschool deficit appears.

## Slide 7. The norm met on a map is not met on foot

The planning standard sets service radii: 500 metres to a school and 300 metres to a preschool, but it does not say whether the radius is a straight line or a walk. The difference is large. As a straight line, the norm is met for 64 per cent of school-age children; on foot, for only 22. For preschools, 77 against 34 per cent. Superblocks, fenced courtyards, rivers and highways make the walk a median 1.41 times longer than the line. The official service territories add a second finding: four children in ten are assigned past a nearer school, and only one in five lives within 500 metres of the school they are assigned to.

## Slide 8. The growing districts are the worst served

Now the second hypothesis. The map shows accessibility to state schools per child relative to the city mean: red is below, blue above, and the black outlines are statistically significant clusters of low access. With the official design capacity of schools as supply, the two districts of recent growth are the worst served: Nura at 76 per cent of the city mean and Esil at 81 per cent. For preschools Nura is again the lowest, followed closely by Saraishyk, also a district of new housing. But the differences between districts are small: 92 per cent of inequality for schools and 91 per cent for preschools lies within districts. So H2 is supported in part: the growth districts are behind, but the real deficit is in specific groups of blocks, which a district-level indicator cannot see.

## Slide 9. Two deficits: places and distance

The official list of schools gave us design capacity and enrolment for every school, and it shows a second deficit. 45 of the 120 state schools enrol more than twice their capacity, which is more than two full shifts can hold, and almost half of all pupils study in such schools. Saraishyk is the most crowded district, with two pupils per place. Note that crowding and walking access are different deficits: crowding peaks in Saraishyk, while the lack of a school nearby is worst in Esil and Nura. The same data validated our model: the load our index allocates to each school correlates with its real enrolment at 0.60, against 0.41 for the original method.

## Slide 10. The population surface moves the deficit itself

To test robustness we repeated the analysis 72 times for each facility type, varying the population surface, the supply measure, the distance decay and the catchment size. For schools, Nura is the worst-served district in every one of the 54 building-based runs, and district rankings correlate with the baseline at 0.94. For preschools, Nura and Saraishyk trade the last place. Across all building-based surfaces the worst-served fifth of children falls in the same cells, with an overlap of about 0.8. With WorldPop, the overlap drops to 0.14. Technical choices move individual cells, but the choice of population data moves the deficit itself. We also ran a Monte Carlo simulation of the population surface itself, 200 draws of the allocation exponent, the size of every polling station and the dwellings the classifier decided: Nura or Esil is the worst-served district for schools in 199 of them. H3 holds at the level of cells, and this is the practical meaning of H1: a study built on the standard gridded product would recommend schools in different places.

## Slide 11. The programme went where land was free

The fourth hypothesis tests the national Comfortable School programme: 23 schools with 42,400 places opened in Astana from 2024. We rebuilt the city as it was on 1 January 2023, before the sites were chosen, from the history of OpenStreetMap. What explains the chosen sites best is not deficit and not density, but the availability of a free plot: ROC-AUC 0.71. The deficit points the right way, 0.59 against 0.42 for density, but with 23 sites the difference is borderline. Then we asked whether the same 23 schools could have reached more children. Without a land limit, an optimal choice would reach 3.4 times as many uncovered children within one kilometre; on plots that were actually free, the programme achieved 84 per cent of the best. So land, not the choice among plots, was the binding constraint.

## Slide 12. The plan answers crowding more than distance

We applied the same test to the future. The city’s construction department sent us its plan for 2026 to 2028: 25 school projects with seventy thousand places in two shifts. We located 24 of them. By 2028 the plan brings a school within one kilometre of only 15 per cent of the almost 78 thousand children who now lack one, and the deficit does not single out the chosen sites better than density. The official enrolment data show why: across districts, planned places follow the number of pupils beyond two shifts, at 0.71, more than the walking deficit, at 0.60. So Saraishyk, the most crowded district, gets the most places, while Esil, with the largest walking deficit, sees it fall by less than four per cent. And the plan is judged against today's children, while its schools open by 2028: projected with the official age tables, the children without a school within a kilometre grow to between 84 and 103 thousand, and the plan still reaches only 15 to 17 per cent of them.

## Slide 13. The land is already reserved — on paper

Is the problem a lack of land? The city geoportal shows the detailed planning projects, and they already contain 238 sites for new schools. Fourteen of the seventeen new schools of the plan stand on such sites, and for two of them the city has already begun compulsory acquisition of land. If all 238 were built, 62 per cent of the children without a school nearby would get one. And if the city chose the same number of schools, 17, among these reserved sites by the number of children each would reach, it would reach almost 29 thousand children instead of 12 thousand — 2.4 times as many. So the land is reserved on paper; what is missing is an order of construction, and our framework can provide exactly that ranking.

## Slide 14. Places exist, but not near every child

For preschools the picture is different. The organisation cards of the INDIGO portal count 73 thousand places for 66 and a half thousand attending children. The waiting list confirms it: of 19,500 children in the net need, 19,300 are under two years old; only 210 are two or older, the age from which most kindergartens enrol. Yet only 34 per cent of preschool-age children live within 300 metres on foot. So the problem is not the number of places but where they stand: a deficit of distribution. City-level ratios of places to children, the way provision is usually reported, hide it completely.

## Slide 15. Two models, both under spatial cross-validation

Machine learning appears in two places. First, OpenStreetMap types only five per cent of buildings, so a LightGBM classifier decides which buildings are homes. Under spatial cross-validation it reaches a ROC-AUC of 0.982, and it recovers 80 per cent of houses named in the legal house lists and 92 per cent of residential complexes listed in 2GIS, which it never saw. Second, we modelled which preschools publish free places, as a test of revealed demand. Design capacity is the strongest predictor; demand pressure around a preschool points in the expected direction: 76 per cent of private preschools with few children per place nearby had free places, against 58 per cent of the rest; but its effect is not yet distinguishable from zero. One evening of data is a noisy label, and repeated snapshots would be needed.

## Slide 16. What the city can do with this

To conclude. H1 is supported: open data reconstruct population better than the global product. H2 is supported in part: the growing districts are behind, but most inequality lies within districts. H3 holds at the level of cells. H4 holds in direction, and partly against the optimum on free land. For the city we draw four practical conclusions: measure the planning norm on foot; plan by blocks rather than districts; reserve land for schools before housing surrounds it; and, most immediately, rank the sites already reserved in the detailed plans by the number of children each would reach — the same seventeen schools would reach 2.4 times as many children. The framework is open and can be rerun every year.

## Slide 17. What the data cannot yet tell

The work has limitations. Population below the district level remains an estimate. The official split of children between Almaty and Saraishyk is contradicted by school enrolment, so we use their combined share and report the official split alongside. The geoportal does not say whether the planned school sites are formally reserved, and the preschool vacancy model rests on one evening of data. We have requested the missing data — voters by polling station, the waiting list by district, and the status of the reserved sites. The framework can also be extended to public transport and winter walking, to polyclinics and sports facilities, and to other cities of Kazakhstan.

## Slide 18. Thank you

Thank you for your attention. I am ready to answer your questions.

## Backup population. Why polling stations

If asked why polling stations: the akim’s decision is a legal document that assigns every address in the city to a polling station, and stations are formed with similar numbers of voters. So the number of stations in an area is a direct, official signal of how many residents are registered there. We spread the official district total over stations in proportion to floor area to the power 0.2, which keeps them close to equal, and then over the dwellings of each station by floor area. With alpha equal to 0.2 the surface fits the district totals best.

## Backup e2sfca. Each child is counted once

If asked about the index: in the original enhanced two-step method a child counts towards every school within reach, so demand is multiplied in dense areas. We allocate each child once among the schools within three kilometres, in proportion to distance weights. Against the official enrolment of 119 schools, our allocated load correlates at 0.60, the original at 0.41. Against the official service territories the two are equal, at 0.53, but that test covers only the 56 per cent of children whose houses we could match to a territory.

## Backup mclp. Capacitated covering on free land

If asked about the optimisation: it is the maximal covering location problem with capacities. We maximise the number of uncovered children who get a school within walking distance, subject to each school’s capacity of places times two shifts, with exactly k schools. Candidate sites must fit a 3.8 hectare plot, the size the planning standard prescribes for a 2,000-place school, on land that was free of buildings, roads, water, parks and industry in 2023. The problem is solved exactly with the HiGHS solver.

## Backup agesplit. Enrolment corrects the official age split

If asked why we did not use the official age split for Almaty and Saraishyk: in the 2026 tables, Saraishyk, a district of new housing, has only 8 per cent preschool children and Almaty 20, while the same series gave 14 and 14 per cent in 2023. The official school enrolment decides it: with the official split our model gives Almaty 38 per cent more pupils than are enrolled and Saraishyk 32 per cent fewer; with their combined share the errors fall to 11 and 6 per cent. So we use the combined share and report the official split alongside.

## Backup data. How the data were obtained

If asked about data and ethics: open sources were read through their public interfaces; official data came as replies to information requests through eGov. The preschool register forbids automated crawling, so its pages were saved by hand. The organisation cards of the register, the detailed planning layer of the geoportal and the 2GIS listings were compiled by our team. No personal data are used, and the official letters, which contain the applicant’s personal details, are not published.

# Population model built from open sources

Written 2026-09-30. Code: `src/astana_access/population`. Outputs: `data/processed/grid_population.gpkg`, `data/processed/dwellings.parquet`, `data/processed/polling.gpkg`, diagnostics in `reports/population_model.json` and `reports/residential_classifier.json`.

This report supersedes the population part of the sprint 1 report. That report compared sources with district totals for the start of 2025 and relied on an incomplete reading of the polling-station decision. Both are corrected here.

## Outcome

| Item | Value |
|---|---|
| Official population, 1 January 2026 | 1,638,233 in five reporting units |
| Building footprints in the city | 93,507: 50,095 from OSM, 43,412 from Microsoft |
| Buildings classed as dwellings | 39,735: 7,296 blocks, 32,439 houses |
| Polling stations with a territory | 386 of 422; 36 are institutions |
| Station territories reconstructed | 340 of 386 |
| District error, WorldPop | 27.6% |
| District error, residential floor area | 27.8% |
| District error, polling-station count | 8.7% |
| District error, stations tempered by floor area | 9.0% |
| Model carried forward | district totals, then stations, then buildings |

District error is the mean absolute deviation of predicted district population from the official figure, after scaling the prediction to the city total.

## 1. What is official

**District totals.** The Bureau of National Statistics bulletin "On the change in the population of Astana as of 1 January 2026", number 18-05 of 2 February 2026, gives:

| Unit | Start of 2025 | 1 January 2026 | Growth |
|---|---|---|---|
| Almaty, including Saraishyk | 409,873 | 443,031 | 8.1% |
| Baikonur | 227,043 | 218,232 | -3.9% |
| Esil | 293,451 | 320,472 | 9.2% |
| Nura | 246,763 | 303,914 | 23.2% |
| Saryarka | 351,573 | 352,584 | 0.3% |
| City | 1,528,703 | 1,638,233 | 7.2% |

The bulletin still reports Saraishyk inside Almaty. These five numbers are the only official population figures below city level and they are the hard constraint of the model. One year moved Nura by 23 per cent and Baikonur by minus 4, so a comparison against the 2025 figures, as in sprint 1, misjudges any source that describes the city as it is now.

**Housing stock.** On 1 January 2025 the housing stock of Astana was 36.7 million sq m, 87.3 per cent of it in apartment buildings, about 24 sq m per resident. The figure is attributed to the Bureau of National Statistics by Kazinform; the article could not be opened from the working network and the number still has to be checked against the Bureau's own table. In 2025 the city commissioned 4,904,965 sq m of housing, 68,148 sq m of it by individual builders (Bureau bulletin on construction in 2025, published 3 July 2026). Together these give about 41.6 million sq m on 1 January 2026: 36.9 in apartment buildings and 4.7 in houses.

**Polling stations.** The akim's decision No. 01-7 of 8 April 2025, in the edition of 18 February 2026, lists every polling station of the city with its territory, either as a list of houses or as a walk along named streets. The election law caps a station at 3,000 voters.

Everything else in this report is derived.

## 2. Buildings

Footprints come from the Overture Maps release of 23 September 2026, which merges OpenStreetMap with Microsoft's machine-detected footprints. Inside the city boundary that is 93,507 buildings. Microsoft adds 43,412 that OSM lacks, almost all of them small, which is where OSM is weakest: districts of detached houses.

Only 4,755 OSM buildings carry a type. The rest are tagged `building=yes`, so residential use has to be inferred.

### Residential classifier

Labels:

| Label | Source | Buildings |
|---|---|---|
| Residential | OSM building type | 3,203 |
| Residential | Houses named in polling-station territories and in official school catchments, matched to a footprint within 12 m | 3,208, of which 2,663 untyped in OSM |
| Residential | Building name marks a housing complex | 168 |
| Not residential | OSM building type, or a use tag or name on the building | about 2,100 |
| Not residential | Building stands on land mapped as industrial, commercial, school, hospital or similar | about 6,600 |

Features: footprint area, perimeter, compactness, number of floors where tagged, address points and points of interest inside the footprint, land use at the centroid, and the count, median size, built-up share and median floors of buildings within 100 and 300 m. Model: LightGBM, 400 trees.

| Test | n | Result |
|---|---|---|
| Spatial cross-validation, five folds of 1 km blocks | 13,830 | ROC-AUC 0.982, PR-AUC 0.975, F1 0.922 |
| Transfer: trained without any house-list label, scored on untyped buildings that the house lists prove residential | 2,663 | recall 0.805 |

The second test is the stricter one. The cross-validated scores are flattered by the negative class, which is dominated by buildings on non-residential land and is easy to separate. The house lists are an independent statement that a building is lived in, and the model recovers four in five of them without having seen such labels.

Buildings with an observed label keep it; the model decides the remaining 79,677. Footprints under 35 sq m are never dwellings.

### Floors

Floors are tagged for 16,341 dwellings. Missing values are filled from the median of the seven nearest tagged residential blocks within 400 m, and with one floor for small buildings. Leaving each tagged block out in turn: mean absolute error 2.0 floors, bias -0.3, 71 per cent within two floors. About 61 per cent of block floor area rests on a tagged value.

### Check against the housing stock

| | Gross floor area measured | Official stock | Ratio |
|---|---|---|---|
| Apartment blocks | 73.6 million sq m | 36.9 | 0.50 |
| Houses | 4.4 million sq m | 4.7 | 1.08 |

Houses agree with the official figure. Blocks are measured at twice the official living area. Gross external area always exceeds the area of flats, by a third or so, but not by this much. The rest is floors that are not housing, such as shops, parking and offices in residential towers, buildings mapped before they were commissioned, and classifier and floor errors.

The two ratios give the one coefficient the model needs: a gross square metre of house carries 2.15 times the residents of a gross square metre of block, on the assumption that living area per person is the same in both.

## 3. Polling-station territories

The decision contains 422 stations in the six district annexes. 36 of them have a single address as their territory; they are hospitals and similar institutions and carry no resident population. The other 386 are territorial.

| Form of description | Stations | Treatment |
|---|---|---|
| List of houses | 93 | Each house located through the address gazetteer |
| Walk along streets | 290 | Polygon reconstructed from street geometry |
| Named housing area | 3 | Not reconstructed |

An earlier parse found 366 stations because it missed the singular heading used by 56 entries. The figures in the sprint 1 report and in the first version of the data strategy were based on it.

**Houses.** Of 1,079 listed houses, 897 resolve to an exact building, 83 per cent. Houses named in "including" and "excluding" clauses resolve at 72 and 77 per cent.

**Walks.** A description such as "from Orynbor street along the even side of Mangilik El avenue to house 38, from house 38 to Bokeikhan street, ..." is read as an ordered chain of streets, rivers, railways and house anchors. Each feature is matched to OSM line geometry through the same alias table as addresses; consecutive features are intersected; the intersections, in order, form the polygon. Features of the same name elsewhere in the city are discarded by keeping only geometry within 3 km of the chain.

| Check | Result |
|---|---|
| Walks with every feature matched | 215 of 290 |
| Polygons obtained | 247 of 290 |
| Polygon centroid inside the district the decision assigns the station to | 246 of 247 |
| Overlap between polygons | 8.4 sq km against 102.9 sq km in total |

The district test is independent: the district comes from the annex the station is printed in, the polygon from street geometry. Polygons are coarser in Esil and Nura, where recent streets are less completely named in OSM, and that is where most of the 43 failures are.

**Assignment.** Every dwelling gets one station: a listed house takes its station; otherwise the station whose polygon contains it, complete polygons first and the smallest first; otherwise the station of the nearest assigned dwelling in the same district. By floor area: 14 per cent listed, 45 per cent by polygon, 41 per cent by nearest neighbour. 340 stations receive buildings.

## 4. Which signal predicts district population

Each candidate is scaled to the city total and compared with the five official figures for 1 January 2026.

| Predictor | Almaty+Saraishyk | Baikonur | Esil | Nura | Saryarka | Mean abs. error |
|---|---|---|---|---|---|---|
| WorldPop | 1.04 | 1.76 | 0.77 | 0.76 | 0.90 | 27.6% |
| Residential floor area | 1.13 | 0.59 | 1.16 | 1.34 | 0.66 | 27.8% |
| Number of territorial stations, all 386 | 1.12 | 0.90 | 0.85 | 1.05 | 1.01 | 8.7% |
| Stations with buildings, equal weight | 1.17 | 0.95 | 0.78 | 0.94 | 1.07 | 11.5% |
| Stations weighted by floor area to the power 0.2 | 1.17 | 0.90 | 0.86 | 1.01 | 0.98 | 9.0% |

Values are predicted over official population.

Two findings.

**WorldPop and floor area are wrong by the same amount in opposite directions.** WorldPop places 76 per cent too many people in Baikonur and too few in the new districts; it describes an older city. Floor area does the reverse: it sees the new towers of Nura and Esil and assigns them up to a third more people than are registered there, and it under-counts the old districts by a third or more. New stock is not yet fully occupied, and crowding is higher in old stock. Neither can be used to move population between districts.

**The count of polling stations is three times closer.** Stations are drawn from voter lists under a legal ceiling, so their number tracks the number of residents. The correlation with official district population is 0.97, and the city averages 4,244 residents per station.

Five data points cannot distinguish between the exponents 0 and 0.2. The value 0.2 is used as the default and 0 is kept as a variant.

## 5. The model

1. The official total of each reporting unit is fixed.
2. Inside a unit, each station receives a share proportional to its occupancy-weighted floor area raised to the power 0.2. This is close to an equal share per station.
3. Inside a station, residents are spread over dwellings in proportion to floor area, with houses weighted 2.15 times blocks.
4. Dwellings are summed into H3 cells of resolution 9.
5. Children of preschool and school age are taken as the share of each cohort in the WorldPop cell, or in the district where the cell is empty in WorldPop.

Three variants are written side by side so that every later result can be recomputed on each:

| Column | Meaning |
|---|---|
| `pop_worldpop` | WorldPop scaled to the official district totals |
| `pop_floor` | floor area only, within district |
| `pop_station` | the model above |
| `pop_station_equal` | the model with an equal share per station |

All four sum to 1,638,233. The building-based variants place the population in 1,312 cells; WorldPop spreads it over 3,331. The rank correlation between WorldPop and the building-based variants across cells is 0.68. Between the three building-based variants it is above 0.99, because inside a district they differ only in how much each station holds.

The variants disagree most on the split of the Almaty reporting unit: the station model puts 267,000 in Almaty and 175,000 in Saraishyk, floor area puts 218,000 and 224,000. No official figure separates the two.

## 6. What is not known

1. No figure exists for the population of any area smaller than a district. The model is constrained at district level and is an estimate below it. The only checks available below district level are indirect: the district of each reconstructed territory, and the legal ceiling on station size.
2. Station sizes are not published. Equal or near-equal shares are an assumption supported by the district test, not an observation.
3. 46 territorial stations have no reconstructed territory. Their residents are attributed to neighbouring stations of the same district.
4. 41 per cent of residential floor area reaches its station by nearest neighbour.
5. Age structure is taken from WorldPop, a modelled product. It shifts children between cells only through the cohort share, and the total in each cell comes from the model above.
6. The classifier's negative examples are not a random sample of non-residential buildings.
7. Block floor area is twice the official living area. The model uses floor area only as a relative weight inside a station, which limits the effect, but a tower with offices is weighted as if it were housing.

## 7. Next

1. Raise the share of reconstructed territories, starting with the 75 walks that have an unmatched feature.
2. Carry the four population variants into the accessibility computation and report how far conclusions depend on the choice.

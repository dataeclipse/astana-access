# Data strategy without official responses

Written 2026-09-30. This note fixes how the project obtains every input if no state body answers the information requests in `data_request.md`.

## Rules

1. Every input comes from a source that anyone can open today. An official reply, if one arrives, replaces an estimate; nothing waits for it.
2. No synthetic data. A value is either observed in a source or derived from observed values by a stated rule, and derived values are labelled as such in the data and in the text.
3. Access limits of a source are respected. A site that disallows automated access in `robots.txt` is not fetched by code.
4. Each derived layer is checked against a source that was not used to build it. Where no such check exists, the thesis says so.

## Inputs

| Need | Source in hand | How it is obtained | Independent check | Status |
|---|---|---|---|---|
| City and district boundaries | OSM relations | Overpass | District areas against the official figures | Done |
| Population by age, 100 m | WorldPop, constrained | Download | Official district totals: city -7.2%, districts 23.6% mean absolute error | Done, needs correction |
| District population totals | Bureau of National Statistics | Published table | - | Done |
| Sub-district population signal | 366 polling-station territories, akim decision 01-7 | Text of the decision on adilet.zan.kz | Station counts against district shares: 11.9% error, r = 0.92 | Parsed in part |
| Buildings, levels, addresses | OSM: buildings, 37,925 address objects, 4,822 named streets | Overpass | Stated floor area of 3 schools: within 9% | Done |
| School list | egov registry, 112 records, and OSM, 169 objects | API and Overpass | Registry against OSM: 99 of 112 linked, F1 0.96 | Done |
| School positions | OSM | Overpass | Official coordinates of 11 schools: median 29 m | Done |
| School design capacity | School websites | Crawl of 125 hosts | City totals of pupils and shortage | 11 schools only |
| School enrolment | School websites; city totals in the press service releases | Crawl; published figures | - | 10 schools; city totals for 2023, 2024, 2025 |
| Official school catchments | School enrolment portal, 11 schools, 4,808 houses | Crawl, allowed by robots.txt | - | Done |
| Preschool list, ownership, free places | Preschool enrolment portal, 790 organisations | Pages saved by hand; robots.txt disallows crawling | Portal totals: 148 state, 642 private, reproduced exactly | Done |
| Preschool positions | Registry address through the OSM gazetteer | Local matching | OSM buildings of 70 state preschools: median 9 m | 653 exact, 75 approximate, 62 missing |
| Preschool attendance | Portal totals: 66,402 children, 29,429 state, 36,973 private | Same pages | - | Class totals only |
| Pedestrian network | OSM | Extract for OSRM | Sprint 3 | Pending |
| Norms | SP RK 3.01-101-2013 | Text | - | Text still needed |
| Backtest target | 24 sites of the Comfortable School programme, locations and seats as announced in October 2023 | Published list | OSM schools opened 2024-2025 | To be geocoded |

## City-level reference figures

Used to calibrate and to sanity-check, never as per-facility data.

| Date | Figure | Source |
|---|---|---|
| 16 Aug 2023 | Shortage of 26,454 places; 26,650 first-graders; 8 schools in three shifts | inbusiness.kz |
| 15 Aug 2024 | 187 schools, 282,150 pupils; state: 110 schools, 233,006 pupils; private: 70 schools, 42,674; republican: 7, 6,470; shortage of 27,800 places | zakon.kz |
| 1 Sep 2025 | 206 schools: 122 state, 77 private, 7 republican; over 310,000 pupils; 31,000 first-graders | informburo.kz |
| 2023-2025 | Comfortable School: 24 schools, 88,800 places in two shifts: 21 schools of 2,000, one of 1,200, two of 600 | inbusiness.kz, tengrinews.kz |
| 30 Sep 2026 | 790 preschool organisations, 66,402 children | Preschool enrolment portal |

## What stays an estimate, and how it is treated

**Population inside a district.** Official totals exist for six districts only. The grid is rebuilt in a hierarchy: city total, district totals as hard constraints, then polling-station territories and residential floor area as weights. The constraint guarantees district totals; the distribution inside a district is an estimate. It is tested by withholding one level: station-level weights are fitted without district totals and compared with them.

**School capacity.** Known for 11 schools. Floor area is measured for 96 of 111 and does not predict design capacity school by school. Accessibility is therefore reported twice: on floor area, and on design places obtained from floor area with one city-level ratio. The ratio is bracketed by two unrelated estimates, 13.5 and 17.3 sq m per place, and results are recomputed at both ends.

**Preschool size.** Known as class means: 199 children per state organisation and 58 per private one. Results are reported with class-mean weights and, for the 105 organisations linked to a building, with floor-area weights. If the ranking of districts or cells changes between the two, that is reported as a sensitivity of the result.

**Preschool positions.** 62 organisations are not placed and 75 are placed approximately. Accessibility is computed with exact positions only and again with approximate ones added; the unplaced 7.7 per cent of supply is stated as a bound on every preschool result.

## Sources examined and not used

| Source | Finding | Decision |
|---|---|---|
| Overture Maps places, release 2026-09-23 | 8,817 places in Astana, 75 of them preschool-like, against 790 in the registry | Not used |
| Nominatim | Same OSM data as the local gazetteer; added 4 addresses | Kept as a verified fallback |
| Preschool enrolment portal, automated access | Disallowed by robots.txt | Pages saved by hand instead |
| School enrolment portal, school identifiers not shown in its public list | The catchment endpoint answers for identifiers outside the 11 published schools; their school names are not published and their date is unknown | Not used; only the 11 published schools are taken |
| gov.kz press pages | Not reachable from the working network | City figures taken from news agencies that reproduce the releases |
| 2GIS | Geocoding needs an API key | Optional, see below |

## Optional improvements that need the author

None is required for the project to finish.

1. A 2GIS API key in `.env` as `TWOGIS_API_KEY` would place the 137 preschools that are missing or approximate.
2. Any reply to the information requests would replace the estimates of school capacity and preschool size.
3. The text of SP RK 3.01-101-2013 is needed for the normative radii in chapter 1.

# Sprint 2 report: facility inventory

Data snapshot 2026-09-24; sections 8 and 9 revised 2026-09-30. Everything reproduces from `src/astana_access/inventory`.

Scope of this report: general education schools and preschool organisations.

## Outcome

| Item | Value |
|---|---|
| School objects in the inventory | 169 |
| In scope for general education | 149 |
| State schools with catchment-based admission | **111** |
| Registry records linked to a location | 99 of 112 |
| Catchment schools with a building found | 101 of 111, floor area used as observed for 96 |
| Preschool organisations, official registry | 790: 148 state, 642 private |
| Preschools located at the exact building | 653 of 790 |
| Schools with a stated design capacity | 11 of 111 |
| Automatic linkage, frozen rules (v1) | precision 0.977, recall 0.944, F1 0.960 |
| Automatic linkage, revised rules (v2) | precision 1.000, recall 0.967, F1 0.983 |

Output: `data/processed/facilities.gpkg`, layer `schools`.

## 1. Sources

| Source | Records | Contributes |
|---|---|---|
| egov registry `onirler_oblystar_kalalar_boi4`, Astana subset | 112 | Official name, organisation type, district as recorded |
| OSM `amenity=school` objects | 161, 160 after merging duplicates | Location |
| OSM school buildings and named buildings | 105 | Names missing on objects, schools absent as objects, floor area |
| OSM school territory polygons | 130 | Assignment of buildings to schools |
| Addresses from school websites and directories, geocoded with Nominatim | 5 | Location for registry records absent from OSM |

## 2. Findings that shaped the method

**The registry is stale.** It records four districts, without Nura (separated in 2018) or Saraishyk (created 2024), and its highest school number is about 85. OSM contains 28 state schools numbered above 85: Esil 10, Nura 8, Saraishyk 6, Almaty 2, Baikonur 2. These are the recent construction wave, including the Comfortable School programme. The registry therefore cannot serve as the list of facilities. The inventory is the union of OSM and the registry, and the registry supplies official identity where a link exists.

**Names are split between object and building in OSM.** A school can exist as an unnamed `amenity=school` polygon while its name sits on the building inside it: object 84 is unnamed, its building reads "Комфортная средняя школа №110". Three registry schools missing as OSM objects (numbers 15, 39, 43) exist only as named buildings. Names are therefore taken from buildings within 30 m where the object has none, and named school buildings more than 150 m from any object enter as facilities in their own right.

**Some links are invisible to name matching.** "Специальная коррекционная школа-интернат" and the OSM object "Специальная школа №2" share no name tokens, yet both sit at 9 Zhangeldin Street. Address geocoding found the link.

**Selective schools do not serve a catchment.** Nazarbayev Intellectual Schools, the Republican Physics and Mathematics School, Zhas Ulan, the Daryn and Zerde lyceums, Bilim-Innovation boarding lyceums and special boarding schools admit by competition or referral from the whole city or country. Counting their places as supply for the surrounding cells would inflate accessibility around them. They are kept in the inventory and flagged `catchment_based = False`, together with all private schools.

## 3. Record linkage

### Name parsing

Each name is normalised (Kazakh letters mapped to Russian equivalents, quotes and punctuation removed), the school number is extracted, the organisation type is classified, and legal-form boilerplate in both languages is stripped. What remains is a set of distinctive stems, typically an eponym, plus a Latin transliteration for brand names.

The number resolves most links. It is not sufficient alone: number 1 belongs to a school-lyceum, a vocational lyceum and a special boarding school, and number 2 to a school-gymnasium, a special school and the Daryn lyceum.

### Scoring and assignment

For each registry record and OSM object a score combines number agreement, type compatibility, name similarity and district compatibility. District compatibility accounts for the stale registry: registry Esil is compatible with Esil and Nura, registry Almaty with Almaty and Saraishyk. Differing numbers exclude a pair. The score matrix is solved as a one-to-one assignment with the Hungarian algorithm, and pairs below 0.60 are discarded.

### Gold standard

Every one of the 112 registry records was reviewed against its candidates: all OSM objects with the same number plus the five most similar names. The label was fixed from the names, types and districts, independently of the matcher output.

| Label | Records |
|---|---|
| True link | 90 |
| No counterpart in the OSM object layer | 21 |
| Ambiguous, excluded from evaluation | 1 |
| Of which low confidence | 6 |

The ambiguous record is school number 45: OSM has two objects with that number 4 km apart and the names cannot decide between them.

Low-confidence decisions and their grounds:

| Registry record | Decision | Ground |
|---|---|---|
| Complex "kindergarten-primary school №12" | linked to "School №12" | No other number 12 exists in the registry |
| Complex "kindergarten-primary school №33" | not linked | The only OSM number 33 is a general school in a different district |
| Bilim-Innovation lyceum for boys | linked to the Kazakh-Turkish lyceum for gifted boys | These lyceums were renamed Bilim-Innovation; districts differ |
| NIS of physics and mathematics | linked to NIS of natural sciences and mathematics | Profile wording differs |
| NIS, general | linked to the only generic NIS object | Two NIS objects for three registry entries |
| School number 45 | ambiguous | Two candidates |

**The gold labels were produced during development and must be re-verified by the author before they are reported as manual verification in the thesis.** The six low-confidence rows come first.

### Results

| Version | Links | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| v1, rules frozen before labelling | 88 | 85 | 2 | 5 | 0.977 | 0.944 | 0.960 |
| v2, after error analysis | 88 | 87 | 0 | 3 | 1.000 | 0.967 | 0.983 |

High-confidence labels only: v1 F1 0.965, v2 F1 0.988.

v1 errors had two general causes. A hard veto on type incompatibility blocked correct pairs whose type label changed through renaming, such as specialised gymnasium number 81 recorded as an international school in OSM. And `token_set_ratio` scores a subset as a perfect match, so "college" matched "College of Management and Business". v2 replaces the veto with a penalty waived when names agree strongly, and blends set and sort token ratios. Both changes are general, neither refers to a specific name.

**v2 figures are in-sample.** The rules were revised after inspecting errors on the same 112 records, so v1 is the honest estimate and v2 is optimistic. The thesis reports both. The three remaining v2 misses were not tuned away, to avoid fitting the rules to the gold standard.

### Final link set

| Method | Links |
|---|---|
| Automatic, v2 | 88 |
| Manual review of automatic misses | 3 |
| Registry number to named OSM building | 3 |
| Address geocoding, matched to an existing object | 1 |
| Address geocoding, new location | 4 |
| **Total** | **99** |

Thirteen registry records remain without location. Only one is a catchment state school, the kindergarten-primary complex number 33. The rest are private centres, a college, and republican specialised institutions.

## 4. Inventory

### Scope and ownership

In scope: general schools, gymnasiums, lyceums, NIS, RFMSh, international schools, special schools and kindergarten-school complexes. Out of scope: colleges and vocational lyceums, language, sports, art and ballet schools, development centres, evening schools, unnamed objects.

Ownership comes from the official registry name where linked, otherwise from the OSM name: state institutions carry the state legal forms, private schools carry partnership, private institution or non-profit forms or an unnumbered brand name, and autonomous organisations are the NIS network and republican institutions. Numbered schools without another signal are state, which is the convention for Astana.

| District | State | Private | Autonomous | In scope | Catchment state |
|---|---|---|---|---|---|
| Almaty | 17 | 4 | 1 | 22 | 17 |
| Baikonur | 17 | 0 | 0 | 17 | 16 |
| Esil | 21 | 10 | 2 | 33 | 19 |
| Nura | 18 | 8 | 3 | 29 | 16 |
| Saraishyk | 15 | 2 | 0 | 17 | 15 |
| Saryarka | 31 | 0 | 0 | 31 | 28 |
| **Total** | **119** | **24** | **6** | **149** | **111** |

State schools that are not catchment-based are the selective and special boarding institutions described in section 2. Private schools concentrate in Esil and Nura and are absent from Saryarka and Baikonur, which is itself relevant to the equity analysis.

## 5. Capacity proxy

### Method

Floor area is the sum over buildings of footprint times levels. Buildings are assigned to a school in order of preference:

1. buildings whose representative point lies inside the school territory polygon, when a territory lies within 50 m of the school;
2. otherwise buildings tagged `building=school` within 80 m;
3. otherwise the largest non-residential building of at least 800 sq m within 80 m.

Residential, garage, commercial, industrial and service buildings are never counted. Buildings under construction are counted separately and excluded from floor area. A building is assigned to one school only, and catchment schools are processed first.

Missing levels are imputed with the median of tagged school buildings, 4 levels.

### Coverage

| Floor area source | Catchment schools |
|---|---|
| Territory polygon | 77 |
| Largest nearby building | 13 |
| School-tagged buildings | 6 |
| Imputed, no building found | 10 |
| Imputed, observed area below 3000 sq m | 5 |

The schools without a building are concentrated among recent schools in Nura (numbers 94, 115, 118, 119), whose buildings are not yet mapped. Imputation uses the median floor area of schools numbered 86 and above for those, 16,871 sq m, and of older schools for the rest, 14,595 sq m.

**Levels are imputed for 48.6 percent of assigned buildings.** This is the largest single source of uncertainty in the capacity proxy.

### Why floor area is sufficient for the next sprints

E2SFCA accessibility scales linearly with total supply, and the Gini coefficient, the Theil index and Moran's I are invariant to multiplying all values by a constant. Converting floor area to places with one normative ratio therefore changes no relative result, no inequality measure and no cluster. What matters is whether the ratio varies between schools, for instance between older and newer designs, and that is handled in the sensitivity analysis.

An absolute conversion to places is needed only for statutory compliance in places per child. It waits for the square metres per place norm from SP RK and for the capacity figures requested from the Astana Education Department. The field `capacity_index` stores floor area relative to the median catchment school.

## 6. Supply per child: why the population correction matters

Catchment school floor area per school-age child, by district, with the child cohort taken either from raw WorldPop or rescaled to the official district population totals.

| District | Children, raw | Rescale factor | Children, adjusted | sq m per child, raw | sq m per child, adjusted | Rank raw | Rank adjusted |
|---|---|---|---|---|---|---|---|
| Baikonur | 61,870 | 0.68 | 42,135 | 3.09 | 4.53 | 1 | 1 |
| Almaty | 45,718 | 1.03 | 46,980 | 5.91 | 5.75 | 2 | 2 |
| Saryarka | 50,784 | 1.28 | 65,245 | 7.60 | 5.91 | 4 | 3 |
| Esil | 39,519 | 1.38 | 54,458 | 9.16 | 6.65 | 5 | 4 |
| Saraishyk | 28,303 | 1.03 | 29,084 | 6.95 | 6.76 | 3 | 5 |
| Nura | 37,066 | 1.24 | 45,794 | 9.88 | 8.00 | 6 | 6 |

Rank 1 is the lowest supply per child. The rescale factor for Almaty and Saraishyk is shared because the official figures predate their separation.

The correction changes the rank of four districts out of six. Raw data exaggerate the Baikonur deficit by almost half and overstate the Esil supply by 38 percent. Without the correction the central finding of the work would point at the wrong districts.

This is a district-level preview with a uniform rescale factor, not the full dasymetric redistribution, and floor area is not yet converted to places. It is not a result.

## 7. Limitations carried forward

1. Gold labels produced during development, pending verification by the author.
2. v2 linkage metrics are in-sample.
3. Levels imputed for about half of all assigned buildings.
4. Fifteen catchment schools rely on imputed floor area.
5. Floor area is not capacity: design norms may differ between building generations.
6. One catchment state school, complex number 33, remains unlocated.
7. School 45 has two candidate locations; the linked one is provisional.
8. Addresses for five schools come from school websites and directories rather than an official register.

## 8. Preschool inventory

Revised on 2026-09-30. The first version of this section rested on OpenStreetMap alone, reported 85 state preschools and called that 86 per cent of the network. Both the figure and two of the rules were wrong. The official enrolment registry lists 148 state organisations, so OSM held about 57 per cent of them, and it lists 642 private ones where OSM had 37.

Output: `data/processed/facilities.gpkg`, layer `preschools`. The earlier OSM-only layer is kept in `data/processed/facilities_osm.gpkg` and is now used only as a source of building geometry.

| Item | Value |
|---|---|
| Organisations in the registry | 790 |
| State | 148, of which 99 main sites and 49 branches or mini-centres |
| Private | 642 |
| Children attending, registry total | 66,402 |
| State, children | 29,429, a mean of 199 per organisation |
| Private, children | 36,973, a mean of 58 per organisation |
| Organisations reporting free places | 470, with 4,881 places |
| Located at the exact building | 653, or 82.7 per cent |
| Located approximately | 75, or 9.5 per cent |
| Not located | 62, or 7.8 per cent |

### Source

The list is the public registry of the municipal preschool enrolment portal, `indigo-nursultan.e-orda.kz`, as displayed on 30 September 2026. The portal's `robots.txt` disallows automated access, so the two pages were saved by hand from a browser and are parsed from `data/raw/manual/`. Nothing is fetched from the portal by code. `ingest/indigo.py` extracts, for each organisation, the name, address, ownership badge, minimum enrolment age, languages and free places, and from the second page the free places by age group. The parsed ownership split, 148 and 642, equals the totals printed on the page.

The registry gives attendance only as three totals: all organisations, state, private. It gives no figure per organisation.

### Two rules that changed

**Private preschools are part of supply.** The earlier version excluded them on the ground that they charge fees. In Astana places are allocated through one municipal queue that covers state and private organisations alike, and private organisations hold 56 per cent of attending children. Leaving them out would have removed more than half of the real supply. Private schools remain excluded from school supply; that rule is unchanged.

**The registry, not OSM, defines the list.** OSM is kept for what it is good at, building footprints and positions, and no longer decides which organisations exist.

### Geocoding

The registry has addresses and no coordinates. Addresses are resolved against a gazetteer built from 37,925 OSM address objects and 4,822 named street segments in Astana (`inventory/addresses.py`). The street table supplies the Kazakh name, the Russian name, alternative names and former names of each street, which matters because the registry mixes all four: `улица Е 11`, `Нуршайхова` and `Әзілхан Нұршайықов көшесі` are one street.

The steps are: strip city, district and premises suffixes; normalise the street name, keeping lanes apart from streets of the same name; resolve it through the alias table, then by surname with initials, then by fuzzy match; and look the house number up on that street. A coordinate is accepted only when the house number matches exactly and the matching points lie within 150 m of each other. Nearest-number and same-base matches are kept as a separate approximate class. When a street is found and the house is not, no coordinate is produced.

| Coordinate source | Organisations | Share of children |
|---|---|---|
| Exact house in the gazetteer | 638 | 80.9% |
| OSM object of the same numbered state preschool | 11 | 3.3% |
| Exact house through Nominatim, verified | 4 | 0.3% |
| Approximate, nearest house on the street | 75 | 7.8% |
| Not located | 62 | 7.7% |

Shares of children use the class means, 199 and 58, since no per-organisation figure exists.

### Validation of positions

Three independent checks, none of which was used to build the matcher.

| Check | n | Median error | Within 150 m |
|---|---|---|---|
| Exact-house result against the OSM building of the same state preschool | 70 | 9 m | 98.6% |
| Exact-house result against official coordinates of schools on the school enrolment portal | 10 | 24 m | 100% |
| Stated district in the address against the district of the coordinate | 104 | - | 96.2% agree |

The single disagreement in the first check is preschool number 20: the registry address resolves to one building and OSM places the facility 3.7 km away. The registry address is used and the case is flagged in the column `osm_conflict_m`.

The approximate class is materially worse. Only 3 to 10 such cases, depending on the matcher version, could be compared with an OSM building, and their median error was 180 to 260 m, which is more than one H3 cell. It is kept in the layer with its own label so that accessibility can be computed with and without it.

On residential addresses the gazetteer is weaker than on institutions: of 4,808 houses in the official catchment lists of 11 schools, 65.6 per cent resolve to an exact building, and the share falls below 50 per cent in districts of detached housing. This bounds what address-based population allocation can achieve with OSM alone.

### Distribution

Located organisations by district:

| District | State | Private | Children, estimated | Free places |
|---|---|---|---|---|
| Almaty | 30 | 133 | 13,625 | 1,372 |
| Baikonur | 19 | 39 | 6,024 | 511 |
| Esil | 19 | 135 | 11,553 | 896 |
| Nura | 15 | 133 | 10,642 | 626 |
| Saraishyk | 16 | 71 | 7,270 | 206 |
| Saryarka | 38 | 80 | 12,163 | 947 |
| Not located | 11 | 51 | 5,125 | 323 |
| **Total** | **148** | **642** | **66,402** | **4,881** |

Estimated children are counts of organisations multiplied by the class mean, so they show where organisations are, not how large each one is. Baikonur has the fewest organisations of any district while the raw population grid assigns it the largest preschool cohort; whether that is a real gap or the known overestimate of Baikonur in WorldPop is settled only after the population correction.

### Limitations

1. Attendance per organisation is unknown. The registry publishes three totals. Every organisation of a class carries the class mean until a better weight is available; for the 105 organisations linked to an OSM building, floor area gives a second, independent weight.
2. 62 organisations, 7.7 per cent of children by class mean, have no coordinate and are absent from the map. They are listed in the layer without geometry so that the loss is visible.
3. 75 organisations are placed with an error of a few hundred metres.
4. The registry is a single snapshot. Organisations that are not connected to the municipal queue are not in it.
5. Free places change daily and describe one evening.

## 9. School capacity: what the school websites yield

The capacity proxy in section 5 had never been compared with a stated design capacity. `ingest/school_sites.py` reads the public pages of school websites at `N.astana-bilim.kz` for N from 1 to 125, within the limits of each site's `robots.txt`, and extracts sentences that state design capacity, enrolment, shifts and total floor area. 85 of 125 hosts respond. Every extracted value was checked by reading the sentence it came from; halls, canteens and libraries that match the same patterns were rejected. The accepted values with their source sentence and URL are in `data/labels/school_site_facts.csv`.

| Fact | Schools |
|---|---|
| Design capacity | 11 |
| Enrolment | 10 |
| Shifts | 5 |
| Total floor area | 3 |

The yield is low. Most school sites carry news and no passport of the school.

### What the 11 schools show

| School | Design capacity | Enrolment | Load | Floor area, OSM | sq m per place |
|---|---|---|---|---|---|
| 13 | 392 | - | - | 6,748 | 17.2 |
| 35 | 1,500 | 1,989 | 1.33 | 14,055 | 9.4 |
| 40 | 850 | - | - | 19,454 | 22.9 |
| 42 | 450 | 462 | 1.03 | 9,669 | 21.5 |
| 44 | 1,240 | - | - | 8,253 | 6.7 |
| 65 | 1,200 | 3,028 | 2.52 | 23,748 | 19.8 |
| 69 | 1,200 | 3,129 | 2.61 | 21,084 | 17.6 |
| 71 | 1,200 | 5,334 | 4.44 | 14,595 | 12.2 |
| 77 | 1,200 | 1,650 | 1.38 | 16,235 | 13.5 |
| 79 | 1,200 | 670 | 0.56 | 14,758 | 12.3 |
| 83 | 1,200 | 3,555 | 2.96 | 15,167 | 12.6 |

Enrolment years differ between schools, from 2015 to 2023, and the figure for school 79 dates from its opening year.

**The floor area itself is measured well.** Where a school states its total area, the OSM estimate is within 9 per cent: 14,758 against 14,664 sq m, 15,167 against 16,296, and 14,595 against 16,112.

**Floor area does not predict design capacity.** Across the 11 schools the rank correlation between floor area and capacity is 0.07; on the 6 schools whose floor area comes from a territory polygon or tagged school buildings it is 0.65. Six of the 11 schools have the same design capacity, 1,200, while their floor area ranges from 14,600 to 23,700 sq m. Schools are built to a small set of standard designs, so capacity is closer to a category than to a continuous function of area, and later annexes change area without a published change in capacity.

**The city-level ratio agrees with the sample.** On 15 August 2024 the city reported 233,006 pupils in 110 state schools and a shortage of 27,800 places. If the shortage is measured against two-shift operation, the network holds about 102,600 design places, and the 1.77 million sq m of floor area in the 111 catchment schools gives 17.3 sq m per design place. The sample median is 13.5, with an interquartile range of 12.2 to 18.7. The two estimates come from unrelated sources and are of the same order. The two-shift reading of the shortage figure is an assumption.

**Overcrowding is large and uneven.** Five of the eight schools with both figures enrol more than twice their design capacity, and school 71 enrols 4.4 times. A supply measure that ignores actual load would call these schools well provided.

### Consequence for the method

Design capacity per school cannot be recovered from open sources for the whole network: 11 of 111 schools, and no relationship strong enough to impute the rest. Two supply measures are therefore carried forward, and results are reported for both.

1. Floor area, as measured. It is observed for 96 of 111 schools, verified against stated area, and needs no assumption about seats.
2. Design places, as floor area divided by a single city-level ratio, anchored on the official totals and bracketed by the sample range.

Neither is the design capacity of an individual school, and the thesis will say so.

### Official catchments for 11 schools

The school enrolment portal `sakura-nursultan.e-orda.kz`, whose `robots.txt` allows access, lists 11 state schools with official coordinates and the houses assigned to each: 4,808 house assignments in total (`ingest/sakura.py`, output in `data/raw/sakura/`). This is the only official statement of school catchments found in the open. It serves as a test set: a catchment model can be scored on whether it sends these houses to the school the city assigns them to.

## 10. Next

1. Population: rebuild the grid by dasymetric redistribution constrained to official district totals, using polling-station territories and residential buildings.
2. Pedestrian network and travel-time matrix, sprint 3.

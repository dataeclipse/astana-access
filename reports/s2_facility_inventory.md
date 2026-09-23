# Sprint 2 report: facility inventory

Data snapshot 2026-09-24. Everything reproduces from `src/astana_access/inventory`.

Scope of this report: general education schools and preschool organisations.

## Outcome

| Item | Value |
|---|---|
| School objects in the inventory | 169 |
| In scope for general education | 149 |
| State schools with catchment-based admission | **111** |
| Registry records linked to a location | 99 of 112 |
| Catchment schools with observed floor area | 101 of 111 |
| Preschool objects in scope | 129 |
| State preschools | 85, about 86 per cent of the numbering range |
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

Output: `data/processed/facilities.gpkg`, layer `preschools`.

| Item | Value |
|---|---|
| Objects after deduplication | 134 |
| In scope | 129 |
| State, numbered | 85 |
| Private, inferred from a brand name | 37 |
| Unknown, object carries no name | 7 |
| State objects with observed floor area | 85 of 85 |
| Median floor area of a state preschool | 3,556 sq m |

### Sources and their limits

There is no Astana preschool registry. The egov `kindergartens` dataset returns nothing for Astana, so unlike schools this layer has no official list to link against. It rests on OSM objects tagged `amenity=kindergarten`, enriched with names from buildings within 30 m, plus named preschool buildings more than 120 m from any object. Territory polygons, 84 of them with a median area of 1.0 ha, assign buildings to preschools.

The registry that resolved school identity, ownership and completeness does not exist here. Three consequences follow.

**Scope rests on the tag, not on a name.** An object tagged `amenity=kindergarten` is treated as a preschool unless its name says otherwise, because private preschools carry brand names such as Teremok, Aruana or Erke kids rather than the word kindergarten. An earlier filter that required the word in the name discarded 47 genuine preschools and left only state ones, which would have removed every private facility from the analysis.

**Ownership is inferred, and the inference is recorded.** The field `ownership_source` states how each value was obtained: `number` for the 85 numbered facilities, which in Astana are state institutions, `brand_heuristic` for the 37 named ones with no legal form in the name, and `no_name` for the 7 that cannot be judged at all. Only `number` is firm. The accessibility analysis uses state facilities alone, so a private facility mistaken for state would inflate supply; the reverse mistake only shrinks the private layer, which no reported result depends on.

**Completeness is measurable and incomplete.** The 85 numbered state preschools carry numbers between 1 and 99, and 15 numbers in that range are absent: 10, 11, 12, 13, 18, 29, 30, 43, 48, 51, 55, 81, 83, 96 and 97. Taking the numbering as continuous, OSM holds about 86 per cent of the state network. The missing facilities are not distributed at random: they have to be somewhere, and every one of them adds supply that the model currently does not see. This is a larger gap than for schools, where the official registry and OSM independently agreed on 112 objects.

### Distribution

| District | State | Private | Unknown | In scope |
|---|---|---|---|---|
| Almaty | 17 | 8 | 2 | 27 |
| Baikonur | 10 | 1 | 1 | 12 |
| Esil | 15 | 13 | 2 | 30 |
| Nura | 12 | 3 | 1 | 16 |
| Saraishyk | 8 | 0 | 1 | 9 |
| Saryarka | 23 | 12 | 0 | 35 |
| **Total** | **85** | **37** | **7** | **129** |

Private preschools concentrate in Esil and Saryarka and are almost absent from Saraishyk and Baikonur, echoing the pattern already seen in schools.

### Provisional supply per child

State preschool floor area per child aged 1 to 6, using the raw WorldPop cohort, that is, before the dasymetric correction:

| District | Floor area, sq m | Children 1-6, raw | sq m per child |
|---|---|---|---|
| Baikonur | 26,228 | 42,745 | 0.61 |
| Nura | 48,753 | 25,609 | 1.90 |
| Saraishyk | 38,764 | 19,554 | 1.98 |
| Almaty | 64,510 | 31,586 | 2.04 |
| Saryarka | 79,263 | 35,087 | 2.26 |
| Esil | 64,584 | 27,304 | 2.37 |

Baikonur stands out at roughly a third of every other district. The raw cohort overstates Baikonur by about 47 per cent, so the corrected figure will be nearer 0.9 sq m per child, which still leaves it far below the rest. This is a preview, not a result: it uses uncorrected population, floor area instead of places, and a supply layer known to be about 14 per cent incomplete.

### Preschool limitations, in addition to those in section 7

1. No official registry exists for Astana preschools, so identity, ownership and completeness cannot be verified against a primary source.
2. About 14 per cent of the state network is missing from the supply layer, judged by gaps in the numbering.
3. Ownership for 37 facilities rests on a brand-name heuristic and for 7 cannot be determined.
4. The kindergarten-school complex number 47 is counted in the school layer and excluded here, so its preschool places are not represented as preschool supply.
5. Private preschools are recorded but excluded from accessibility supply, since they charge fees and do not serve a catchment.

The information request to the Astana Education Department covers precisely these gaps: the list of preschools, their capacity, and the waiting list by district.

## 9. Next

2. Dasymetric population redistribution constrained to official district totals.
3. Pedestrian network and travel-time matrix, sprint 3.

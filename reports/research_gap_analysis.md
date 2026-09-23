# Research gap analysis

Applies the 9-step research-gap framework to this diploma project. Sources: `thesis/sections/10_chapter1.tex`, `reports/references.md`, `PROJECT_PLAN_EN.md`.

Project title: **A Data-Driven Framework for Spatial Accessibility Assessment and Optimal Siting of Social Infrastructure in Astana**.

## 1-2. Research area

Spatial accessibility to social infrastructure (schools, kindergartens, primary healthcare) and optimal facility siting, in the context of a fast-growing post-Soviet capital city (Astana).

## 3. Literature reviewed (in place of the guide's "5-10 reviews")

76 bibliography entries verified against Crossref/NeurIPS/WorldCat/primary source (`reports/references.md`). Reviews and synthesis papers actually used, grouped by sub-area:

| Sub-area | Review-type source used |
|---|---|
| Accessibility measures | Geurs and Wee (2004) `geurs2004`; Wang (2012) `wang2012`; McGrail (2012) `mcgrail2012` |
| Equity metrics | Neutens (2015) `neutens2015`; Lucas et al. (2016) `lucas2016` |
| Facility location | Owen and Daskin (1998) `owen1998`; Farahani et al. (2012) `farahani2012`; Murray (2016) `murray2016` |
| Spatial validation | Roberts et al. (2017) `roberts2017`; Wadoux et al. (2021) `wadoux2021` |
| Planning support systems | Geertman and Stillwell (2004) `geertman2004` |

## 4. Future-research directions flagged in those reviews

- Wang (2012) and McGrail (2012): no consensus on decay-function shape or catchment size; service-specific calibration left open.
- Neutens (2015) and Lucas et al. (2016): aggregate equity indices are group-blind; call for disaggregation by subpopulation and area, not just city-level scalars.
- Roberts et al. (2017) / Ploton et al. (2020) / Wadoux et al. (2021): active, unresolved debate on correct spatial validation protocol for spatially autocorrelated targets — flagged as a methodological problem, not solved.
- Farahani et al. (2012) / Murray (2016): capacitated, multi-period, multi-objective covering variants identified as the growth edge of location theory.

## 5. Deep dive on cited-direction papers

- Tianjin school-siting study (Sun et al. 2025, `tianjin2025`) and the TOPSIS hybrid (Başeğmez et al. 2025, `schoolsiting2025`): both train suitability models on **existing** facility locations and present the output as siting guidance, without treating the model as a revealed-preference read of past decisions. Confirms the gap is real, not already closed.
- Koch (2014) `koch2014`, Laszczkowski (2016) `laszczkowski2016`, Atakhanova and Baigaliyeva (2025) `astana2025`: Astana literature is qualitative/political-economy or environmental-cost framed. No fine-grained quantitative accessibility study of Astana turned up in the search.

## 6. Supervisor discussion

Per `PROJECT_PLAN_EN.md` open items: confirmation of diploma-project (vs. diploma-work) classification, and exclusion of shopping-centre siting from scope, are both flagged as **pending supervisor sign-off** — not yet resolved. Treat any gap statement below as provisional until that confirmation lands.

## 7-8. Literature review on identified direction / crisp gaps

Already written up as Section 1.9 of Chapter 1 (`thesis/sections/10_chapter1.tex:102-114`). Three crisp gaps, each under-researched or empirically absent rather than merely under-theorized:

1. **Geographic** — no fine-grained quantitative accessibility study of Astana found in the reviewed literature, despite it being an atypical, fast-moving case (sustained public investment + peripheral growth + active national school programme).
2. **Methodological** — existing ML siting studies (Tianjin, TOPSIS hybrid) read suitability-model output as normative guidance; none set it against an independent normative optimization over the same demand surface to test whether siting follows need or follows something else (e.g. construction activity, centrality).
3. **Evaluative** — siting studies are typically unvalidatable because the counterfactual is unobservable; Astana's Comfortable School programme gives a rare directly-observable backtest target (known facilities, known locations, known dates).

## 9. Resources required to fill the gap

Per `PROJECT_PLAN_EN.md` §7 ("Data: actual status") and §11 (risk register):

- **In hand**: OSM facilities/network, WorldPop grid, H3 grid, egov school registry, district population — sufficient to proceed.
- **Pending**: capacity data (information requests filed, 15-day statutory deadline), full text of SP RK 3.01-101-2013 and order 213/2026 (blocking Section 1.8), primary-source district population figures from the Bureau of National Statistics.
- **Fallback already defined** if capacity data doesn't arrive in time: floor-area proxy calibrated on the 24 known Comfortable School objects, with the substitution stated explicitly as a limitation.

Feasibility: confirmed at gate S1 (23 Aug 2026) — see `reports/s1_feasibility.md`.

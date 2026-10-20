# Methods — rules distilled from 14-paper corpus

Source tags: A1-A4 writing guides; B1 NEJM RCT; B2 BMJ pragmatic RCT; B3 BMJ cohort; B4 BMJ registry observational; C1 dose-response MA; C2 NMA; C3 pairwise MA of RCTs; D1 SR+MA; D2 SR without MA (SWiM); D3 umbrella review. Items marked (gen.) come from general reporting-guideline knowledge, not the corpus.

## Job of this section
Let a reader judge validity and reproduce the work: what was done, to whom, measured how, analysed how, and why each non-obvious choice was made. Methods report decisions with a reason, never results, adjectives, or hindsight. Every deviation from plan is disclosed and dated [B1,C3]. Methods are the least-read section [A1], so make them scannable: one topic per subheading, one decision per sentence.

## Move structure by article type

### RCT [B1,B2]
Subheadings: Study design / Participants / Randomisation (and masking) / Interventions / Outcomes / Sample size / Statistical analysis / Patient and public involvement. NEJM house style uses all-caps subheads [B1]; BMJ uses sentence case [B2,B3].
1. Design in one sentence: parallel/pragmatic/superiority, blinding, phase, N sites, countries [B1,B2].
2. Ethics and governance: committee, approval date/reference, site approvals, consent, GCP, Declaration of Helsinki, sponsor role [B1,B2].
3. Registration and timeline: registry, ID, registration date, protocol publication, SAP approval date relative to unblinding [B2].
4. Participants: setting, inclusion with numeric thresholds, key exclusions, pointer to full list in supplement [B1,B2].
5. Randomisation: baseline data before allocation, who generated the sequence, concealment, ratio, method, each stratification factor with a one-clause reason [B1,B2].
6. Masking: limitation first (what could not be masked), then who was masked and when, who saw allocation [B2]; or blanket statement for double-blind [B1].
7. Interventions: both arms in parallel detail, dose escalation, discontinuation rule, background care, fidelity monitoring [B1,B2].
8. Outcomes: primary (name, instrument, items/range, direction, timepoint, why that timepoint), then secondary, then any post-hoc or changed outcome with date vs unblinding [B1,B2].
9. Sample size: target difference (raw and standardised), SD with source, alpha, power, attrition allowance [B1,B2].
10. Statistical analysis: population (ITT), estimands, multiplicity control, model, covariates, missing data by mechanism, interim and cluster (therapist) effects, prespecified subgroups, software+version [B1,B2].
11. PPI statement [B2].

### Observational cohort [B3]
1. Cohort identity: country, launch year, recruitment, registration, pointer to design paper.
2. Baseline data sources with validation against a reference.
3. Exposure assessment: instrument, repeats, timing, exclusion of implausible reporters.
4. Exposure definition: composition of each group, units.
5. Sub-samples (biological, clinical) with sizes.
6. Outcome ascertainment: sources, linkage, coding system, adjudication, % validated.
7. Statistical analysis: baseline date, analytic population, measurement-error correction, missing data, exposure coding and increment, model and time scale, ordered covariate list, subgroup/interaction tests, sensitivity analyses, software, alpha.
8. PPI.

### Population/registry observational [B4]
1. Exposure construct and its construction (index, domains, small-area unit, quantile groups defined by population share).
2. Outcome and data source: registry, codes, dates, age range, linked exposure at diagnosis.
3. Denominator source and strata.
4. Statistical analysis subsection: model family, aggregation unit, offset, variance method.
5. Model specification and each extension with its rationale (interactions; period splits).
6. Counterfactual ("what if") prediction, stating which inputs are changed and which stay observed.
7. Sensitivity analysis with a data-driven reason (sparse cells).
8. Software and version; reproducibility process; PPI subsection.

### Meta-analysis
Pairwise MA of RCTs [C3,D1]: standards and registration → search → eligibility → extraction (+ derivation rules) → risk of bias → outcomes (post-hoc labelled) → synthesis model → heterogeneity → subgroup/meta-regression with run-thresholds → small-study effects → certainty (GRADE) → PPI.
Dose-response MA [C1]: framework → search → eligibility → extraction (multi-estimate and sex-split rules, digitisation) → risk of bias → statistical methods in order: effect-size conversion; pooling model; heterogeneity; subgroup triggers; publication bias; dose-response trend estimation (category midpoints, open-ended intervals); non-linear model (splines, knot placement, test for non-linearity); software; alpha.
NMA [C2]: protocol/guideline → sources → eligibility (each exclusion with reason) → selection/extraction → outcomes (source of outcome set, numerator/denominator) → ITT and missing data → transitivity (named effect modifiers) → inconsistency (global + local) → heterogeneity and model → effect measure, reference choice, presentation tools → risk of bias and certainty tools (RoB 2, CINeMA) → additional analyses (meta-regression, sensitivity list) → PPI.
Observational MA [D1]: guideline + prospective registration → search → eligibility paragraph with bracketed examples per exclusion → screening → extraction (author contact, duplicate-cohort rule, which estimate) → outcomes (definitions to table) → risk-of-bias scoring rule → synthesis → PPI.

### Systematic review without MA [D2]
Aim → design (registration, guideline, intervention definition, adjacent topics excluded, comparator) → search (librarian, databases, alerts, forward citation, criteria) → selection counts → quality appraisal (tool, why it fits, dual rating, discrepancy count) → data abstraction → synthesis paragraph: why no MA, SWiM guideline, grouping rule, handling of differing metrics, what could not be done (heterogeneity exploration, certainty).

### Umbrella review [D3]
Guideline → PECOS → search (including scope change after pilot search) → screening/extraction with overlap rule → reanalysis model → one subheading per derived statistic (I², prediction interval, excess significance, small-study effects, largest-study test) → visualisation, code and data availability → terminology (direction words) → credibility classes I-V → GRADE → AMSTAR 2 → PPI.

## Length budget (words; estimates unless stated)
| Type | Methods total | Paragraphs | Notes |
|---|---|---|---|
| RCT (B1 ~1,150; B2 ~1,250) | 1,100-1,300 | 12-16 | Detail beyond this goes to supplement/protocol |
| Cohort (B3 ~1,600; B4 ~1,000) | 1,000-1,600 | 9-12 | Statistical analysis 400-600 |
| Pairwise/dose-response MA (C3 ~1,600; C1 ~1,300) | 1,200-1,600 | 8-12 | Statistics 450-600 |
| NMA (C2 ~900) | 800-1,000 | 8-10 | Synthesis subsection ~430 |
| SR+MA (D1 ~1,000) | 900-1,100 | 8-10 | |
| SR without MA (D2 ~900) | 800-1,000 | 8 short subsections | Synthesis ~260 |
| Umbrella (D3 ~1,500) | 1,300-1,500 | 9-10 | |
| PPI statement | 50-130 | 1-2 | All BMJ-style papers |

## Template bank (all slotted; paraphrase freely)

### Design, ethics, registration
1. "This [design descriptor] [design] was conducted at [N] [setting] sites in [country/system]." [B2]
2. "The [committee] approved the study on [date] ([reference]); each site obtained [local approval] before recruitment." [B2]
3. "All participants provided [written/oral] informed consent. The trial followed [GCP] and the Declaration of Helsinki." [B1]
4. "The protocol and statistical analysis plan were [registered/published] on [date] ([registry ID]) [before/after] [recruitment/unblinding]." [B2]
5. "[Cohort] is an [ongoing] [country] cohort launched in [year] to study [aims]; its design is described elsewhere [ref]." [B3]

### Participants, exposure, outcomes
6. "[Adults] with [diagnosis] ([threshold]) and [comorbidity] ([threshold]) were eligible; the full criteria are in [supplement]." [B1]
7. "To represent [construct], we used [index], a [small-area measure] built from [domains]; areas were grouped into [quantiles] of the population." [B4]
8. "We retrieved all records of [population] aged [range] resident in [setting] with [condition] ([code]) diagnosed between [date] and [date]." [B4]
9. "[Cases] were identified through [self-report] and [linkage sources]; each was [adjudicated], and [x]% had [verification]." [B3]
10. "The primary outcome was [measure] at [timepoint]; this timepoint was chosen because [guideline/clinical reason]." [B1,B2]
11. "We selected outcomes recommended by [body]. The primary outcome was the proportion of participants with [state] at [time], without [rescue therapy]." [C2]
12. "Post hoc outcomes are labelled as such below." [C3]

### Randomisation, masking, sample size
13. "A [independent team] generated the sequence and played no part in recruitment; allocation was by [secure web system] using [method], stratified by [factors]." [B2]
14. "Stratification by [factor] was included because [risk rationale]." [B2]
15. "Masking of [participants/clinicians] was not possible because of [reason]; [assessors] were masked until [point]." [B2]
16. "We assumed a between-group difference of [x] (standardised mean difference [d]) and an SD of [s] ([source/reason]); with a two-sided alpha of [a] and [power]% power, [N] participants were needed, allowing for [y]% loss to follow-up." [B1,B2]

### Statistical analysis (primary studies)
17. "The primary analysis followed the intention-to-treat principle, including all participants who [definition]." [B1,B2]
18. "Two estimands were defined: [treatment-regimen estimand: all randomised regardless of adherence] and [efficacy estimand: if all adhered]." [B1]
19. "We used [model] adjusted for [baseline covariates and stratification factors]; [binary outcomes] were analysed with [model]." [B1,B2]
20. "Missing data were handled by [multiple imputation] under [MAR]; [MNAR scenario] was examined as sensitivity analysis; details are in [supplement]." [B1,B2]
21. "[Exposure] was analysed per [increment] and by [sex-specific quantiles]; the increment reflects [distribution]." [B3]
22. "We fitted [model] with [time scale] and adjusted for [demographic], [lifestyle], and [clinical] covariates, adding [subgroup-specific covariates] where relevant." [B3]
23. "As a sensitivity analysis, we [alternative]; because [sparse-data reason], we fitted a reduced model." [B3,B4]
24. "Using the fitted model, we predicted [outcome] after changing [predictor] and leaving other inputs as observed." [B4]
25. "Analyses used [software] version [n]; tests were two-sided with alpha [x]." [B2,B3,B4]

### Reviews
26. "We conducted this review following [handbook/version] and reported it according to [PRISMA 2020/PRISMA-NMA/MOOSE] ([supplement]); the protocol was registered at [registry, ID]." [C2,C3,D1,D3]
27. "We searched [databases] and [registries] from [inception] to [date], without language restrictions; the full strategy is in [supplement]." [C1,C2]
28. "We included [designs] of [population] comparing [exposure] with [comparator]. We excluded [class/setting] because [reason]." [C2,C3]
29. "[N] reviewers independently screened records and extracted data; disagreements were resolved by [consensus/third reviewer]." [C1,C3,D1]
30. "Where [measure] was missing we derived it from [source] with [formula]; values presented only graphically were digitised with [tool]." [C1,C3]
31. "If several publications used the same dataset, we kept the one with [more participants/more complete data]." [C1,D3]
32. "Risk of bias was rated with [tool, version] across [domains]; a study scoring [x] on [domain] was classed as high risk." [C2,D1]
33. "Effects were pooled with a [random-effects model, method]; heterogeneity was quantified with [tau², I²], and I² above [x]% was taken as substantial." [C1,C3,D1]
34. "Subgroup analyses were run only when heterogeneity was substantial and [k] or more studies were available; funnel plots and Egger's test were used only with [10] or more studies." [C1,C3,D1]
35. "We assessed transitivity by comparing [effect modifiers] across comparisons, and inconsistency globally with [test] and locally with [method]." [C2]
36. "[Agent] was the reference because [prescribing frequency and guideline status]." [C2]
37. "Certainty was graded with [GRADE/CINeMA]: starting at [level] for [design], downgraded for [domains] using [thresholds]." [C2,C3]
38. "Meta-analysis was not possible because of heterogeneity in [design] and [outcome measures]; we synthesised findings narratively following [SWiM], grouping studies by [intervention type] and [outcome domain] and, where metrics differed, by direction of finding. Heterogeneity exploration and certainty grading were not feasible." [D2]
39. "Pooled analyses were classed I-V on [criteria]; we reanalysed each with a random-effects model and report prediction intervals where [k] or more studies contributed." [D3]
40. "Code is available at [URL]; the data are archived at [URL]." [D3]

### PPI
41. "[Group] contributors were not formally involved. We did engage with [organisations] about [topic] and discussed a draft with [audience]." [B4]
42. "[Members of the public] advised on [outcome choice/interpretation]; results were shown to [panels] with interventions masked." [C2]

## Tense / voice / person
| Element | Tense | Voice/person |
|---|---|---|
| Actions done (search, screen, recruit, randomise) | Past | Passive; "we" for decisions [B1,C1,D3] |
| Analytic choices and rules | Past | "We" active ("we extracted", "we defined") |
| Definitions, standing facts, instrument properties | Present | Passive/neutral [B2,C2] |
| Cohort/registry description (ongoing) | Present | Neutral [B3] |
| Cross-references ("are provided in the supplement") | Present | Passive [B1] |
| Planned/unexecuted analyses | Avoid; if protocol-only, "was planned" | Declare as planned |
| PPI | Past for involvement, present for dissemination plans | "We" [B4,C1] |
Use "we" consistently once chosen; do not alternate with "the authors".

## Claim-strength ladder (Methods)
Methods contain no outcome claims. Strongest to weakest wording for what Methods may assert:
1. Fact of procedure: "was randomised", "were extracted independently". Allowed only if it happened.
2. Decision + reason: "we used X because Y".
3. Assumption stated as condition: "assuming MAR", "assuming a difference of [x]". Never "we hypothesised the drug works".
4. Prespecified vs post hoc: label both explicitly.
5. Planned-but-not-possible: "could not be conducted because..." [D2].
Design-dependent language: RCT and model-based counterfactuals may say "effect"; cohort and registry designs say "association" (exception: model-based "prevented cases" in B4 is a modelled estimate, framed as prediction). Never write that a design "proves" or "ensures" validity.
Results-linked rules to set up here: pre-specify a margin if any "no difference/equivalence" claim is planned; otherwise a non-significant result will be reported as "no statistically significant difference", never "equivalent" or "equally effective". Unpowered nulls are uninformative [A3]; state the sample-size basis so the reader knows what a null can exclude. A CI crossing 1 is never "reduced by X%".
Certainty wording for reviews: GRADE levels (high, moderate, low, very low); umbrella class labels. Define them once here; Results reuse them.

## Numbers & statistics formatting
- Sample size: power, two-sided alpha, effect, SD, attrition allowance in one sentence [B2].
- Thresholds written as numerals with units and operators: "AHI ≥15 events/h", "event rate <5%", "I² >50%" [B1,C2,C1].
- State global thresholds once (alpha, I² cut-offs, k-study minimums) so later P values read against them [C1,C3].
- Ratio "1:1"; caps as "limited to 70%" [B1].
- Dates exact (day month year) for accrual and follow-up; search cut-off date explicit [B4,C1].
- Thousands separated by a thin space in BMJ style ("101 257") [B3,B4]; NEJM and others differ, follow target journal.
- Effect measure + CI level named once ("odds ratios with 95% CIs"); later use short form [C2,D1].
- Software with version; packages and correction methods named (e.g. Hartung-Knapp, continuity correction) [D1].
- Correlation or imputation constants given as numbers, paired with a sensitivity range [C3].
- GRADE/class phrasing defined once; Results format "[estimate], [CI]; class [N]; [level]" [D3].

## Reporting-guideline checklist
RCT, CONSORT 2010 (item numbers = CONSORT 2010; CONSORT 2025 renumbered the checklist to 30 items, so map numbers separately if the journal uses 2025): trial design (3a), changes to methods (3b), eligibility (4a), settings (4b), interventions (5), outcomes and changes (6a/6b), sample size and interim analyses (7a/7b), sequence generation (8a), allocation type/restriction (8b), concealment (9), implementation (10), blinding (11a), similarity of interventions (11b), statistical methods (12a), subgroup/adjusted analyses (12b), registration, protocol access, funding, ethics.
Cohort/registry, STROBE: study design (4), setting (5), participants (6), variables (7), data sources/measurement (8), bias (9), study size (10), quantitative variables (11), statistical methods incl. confounding, subgroups, missing data, sensitivity (12a-e).
SR/MA, PRISMA 2020: eligibility (5), information sources (6), search strategy (7), selection (8), data collection (9), data items (10), risk of bias (11), effect measures (12), synthesis methods (13), reporting bias (14), certainty (15), registration/protocol (24). MOOSE for observational MA; PRISMA-NMA adds transitivity, inconsistency, geometry; SWiM: grouping, standardised metric, synthesis method, heterogeneity exploration, certainty, data presentation. Report the PRISMA item for abstracts and the registration deviation statement (gen.).
Note: C1 and D1 report certainty poorly (no GRADE) and D1/C1 give no deviation-from-protocol statement; fix these in a new manuscript.

## Do / Don't
- Do justify each stratification factor, exclusion, and reference choice in the same sentence [B2,C2]. / Don't state criteria without reasons.
- Do state the masking limitation first, then who was masked [B2]. / Don't claim "double-blind" when assessors knew.
- Do disclose and date changes to outcomes or instruments [B1]. / Don't hide post hoc analyses; label them [C3].
- Do give decision rules (which duplicate to keep, how risk-of-bias scores map to low/high) [C1,D1]. / Don't write "appropriate", "as needed", "insufficient data" without a rule.
- Do give run-thresholds for subgroup, funnel plot, and dose-response analyses [C3,D1]. / Don't run tests that are unreliable with few studies.
- Do split missing data by mechanism [B1]. / Don't say "missing data were handled appropriately".
- Do name tools with version (RoB 2, CINeMA, AMSTAR 2, R version) [C2,D1,D3]. / Don't cite "standard methods" with no reference.
- Do justify excluding grey literature with a reason [C1]. / Don't call the search "comprehensive" or "exhaustive" [C2].
- Do push long lists (full eligibility, search strings, covariates) to supplement with a pointer [B1,C2]. / Don't bury the primary outcome in a long subsection.
- Do write an honest PPI statement ("not formally involved" + concrete activities) [B4]. / Don't invent involvement.
- Do state the unit of analysis when a study contributes two estimates (sex-split) and pair with a sensitivity check [C1]. / Don't double-count correlated estimates silently.

## LLM-draft failure modes in this section → fix
| Tell | Why it reads as AI / is wrong | Rewrite pattern |
|---|---|---|
| "A comprehensive and rigorous search was performed" | Unfalsifiable adjective; reviewers want sources and dates | List databases, registries, cut-off date, language rule [C2] |
| "Appropriate statistical methods were used" | No reproducible content | Name model, covariates, missing-data method, software+version [B2] |
| Primary outcome undefined or listed among a flat list of "outcomes" | Hides prespecification; breaks CONSORT 6a | One sentence: name, instrument, range/direction, timepoint, rationale [B1,B2] |
| Sample size stated as "sufficient power" | No assumptions to audit | Effect, SD with source, alpha, power, attrition [B2] |
| "Participants were randomised" with no mechanism | Concealment/sequence missing | Who generated, how concealed, method, strata with reasons [B2] |
| "We hypothesised that X would reduce Y" in Methods | Expectation language; Methods state decisions | Move to Introduction aim; Methods say "we assumed [difference]" [B2] |
| Results or interpretation leaking into Methods ("robust", "confirmed") | Wrong section; implies foreknowledge | Delete; Methods say what was done and why |
| Triplet padding ("rigorous, systematic, transparent") | Generic cadence, no content | One concrete fact per clause |
| "Heterogeneity was assessed using I²" without threshold or action | Reader cannot tell what follows from the number | Give cut-off, model choice, and trigger for subgroups [C1,D3] |
| Claiming PRISMA/CONSORT adherence with no checklist pointer or registration | Unverifiable | Cite guideline + supplement table + registry ID and any deviations [C3,D1] |
| Fabricated ethics ID, registration number, or software version | Invented specificity | Leave a bracketed slot; never generate IDs |
| "To our knowledge, this is the first..." or "novel approach" in Methods | Claim of priority, unsupported | Delete |
| Mixed tense ("is performed", "will be used") | Looks like a protocol draft | Past for actions, present for definitions only |
| Passive blame-free decisions ("it was decided") | Hides who and why | "We [chose X] because [Y]" [D1,D3] |

## Mini worked example (fictional)
**Before (LLM-style):**
"A comprehensive and rigorous systematic search was conducted across multiple major databases to identify all relevant studies. Appropriate statistical methods were employed to pool the data, and heterogeneity was assessed. Publication bias was evaluated. The quality of evidence was carefully rated. This novel approach ensures robust conclusions."

**After (journal-style):**
"We registered the protocol (PROSPERO [ID]) and reported the review following PRISMA 2020. We searched MEDLINE, Embase, and CENTRAL from inception to 14 March 2026 without language restrictions (strategy in supplementary table 1) and checked reference lists of included trials. Two reviewers screened records and extracted data independently; a third resolved disagreements. Risk of bias was rated with RoB 2. Mean differences were pooled with a Hartung-Knapp random-effects model; heterogeneity was quantified with tau² and I², with I² above 50% regarded as substantial. Subgroup analyses were run when at least 10 comparisons were available, and funnel plots with Egger's test when at least 10 studies contributed. Certainty was graded with GRADE, starting at high for randomised trials. Analyses used R version 4.3.2 (meta package)."

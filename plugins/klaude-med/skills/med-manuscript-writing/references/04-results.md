# Results — rules distilled from 14-paper corpus

Source tags: A1 writing guide (Rule 7), A3 (inference/NS), A4 (abstract/results selection), B1 NEJM RCT, B2 BMJ pragmatic RCT (NS primary), B3 BMJ cohort, B4 BMJ population observational, C1 dose-response MA, C2 NMA, C3 pairwise MA of RCTs, D1 SR+MA (PRISMA 2020), D2 SR without MA (SWiM), D3 umbrella review.

## Job of this section
Report what was found, in a fixed order the reader can predict, with numbers that can be checked. Contain no interpretation, no mechanisms, no comparison with other studies, and no adjectives of importance; those belong in the Discussion [B1,B2,B3,D1]. Each paragraph answers one question and ends on its answer, so it can be fact-checked in isolation [A1]. Tables and figures hold the full output; the text carries the headline numbers and the exceptions [B4,C2].

## Move structure by article type

### RCT [B1,B2]
Subsections by domain, not by time: Participants; Primary outcome; Secondary outcomes; Harms (B2 adds Adherence; B1 groups by endpoint domain).
1. Flow: dates of recruitment and follow-up, screened → randomised, allocation split, pointer to the flow figure [B1,B2].
2. Attrition: number/percentage completing the primary timepoint, withdrawals, number analysed (state the analysis population) [B2].
3. Baseline: 1–2 sentences of headline descriptors (age, sex, key severity measure) and a pointer to the baseline table; never restate the table [B1,B2].
4. Adherence/crossover: fraction plus percentage per arm and subcategory [B2].
5. Primary outcome first: arm values, then estimate with CI, then P (if used), then the NS/direction statement [B1,B2]. When there are several estimands, name each and keep the order identical across trials [B1].
6. Key secondary outcomes in the order of the Methods; group null secondaries into one sentence [B2,D1].
7. Pre-specified subgroup and sensitivity analyses in one short paragraph, with supplement pointer [B2].
8. Harms: percentage of participants with any AE, SAE, specific adjudicated events, deaths, per arm [B1,B2].

### Observational cohort / population study [B3,B4]
1. Analysed population: N, denominators, sex/age summary, pointer to Table 1 (descriptive comparison across exposure categories) [B3,B4].
2. Follow-up and events: person-years, median follow-up with range, case counts overall and by site [B3,B4].
3. Primary association: unit increment, point estimate, CI, then subgroup breakdown [B3].
4. Secondary exposures, one paragraph each, opened by the exposure name; nulls reported in identical format [B3].
5. Sensitivity/stratified/further-adjusted analyses in one short paragraph; say when adjustment removed the association [B3].
6. Secondary outcome in its own short subsection [B3].
7. Model-based or population-level estimates (e.g. cases prevented) with CI, then subgroup contrasts as "[x]% v [y]%"; say why updated estimates differ from earlier ones [B4].

### Meta-analysis
Pairwise [C3,D1]: flow → study characteristics → risk of bias (counts) → primary outcome (pooled effect, CI, I², P) → secondary outcomes by domain → harms/acceptability → sensitivity → subgroups/meta-regression → dose-response → small-study/publication bias → certainty (GRADE).
Dose-response [C1]: selection funnel with exclusion reasons and overlapping-dataset handling → study characteristics (counts) → highest-vs-lowest pooled estimate per exposure/outcome (papers, participants, events, I²) → non-linearity P, then linear slope per standardised increment → subgroup → sensitivity → publication bias. Pick an increment that matches a plausible real change.
Network MA [C2]: selection + network geometry/connectivity → placebo (reference) comparisons as ranges → head-to-head among active agents → secondary and safety outcomes by drug class → ranking display pointer → certainty per comparison (counts per grade) → transitivity/inconsistency → sensitivity. Report rankings only with their uncertainty; do not rank on point estimates alone [C2].
Null outcomes are grouped in one sentence with a figure pointer; any sensitivity analysis that changes significance is reported in the Results, naming the study removed [C1,D1,C3].

### Systematic review without meta-analysis [D2]
1. Overview paragraph: number and design of studies (with citations), settings, methodological-quality counts ("[n]/[N]").
2. Synthesis grouped by intervention then outcome domain, per the SWiM grouping rule stated in Methods.
3. Per study: author/year, setting, design, outcome, metric, direction (and magnitude if given), significance only if tested.
4. Close each group with the cross-study pattern and name the lower-quality contributors.
5. Single-study groups: one paragraph with a "significant" list and a "no difference reported" list (this exact wording is allowed only for a descriptive list of what a study reported) [D2].
6. State what could not be examined (heterogeneity, certainty) once; do not hint at pooled quantities.

### Umbrella review [D3]
1. Search yield, then included meta-analyses and distinct pooled analyses.
2. Characteristics as n (%).
3. Synthesis overview: proportion meeting the nominal threshold, number surviving the stringent threshold, heterogeneity strata, prediction intervals, small-study effects, largest-study significance, excess significance (each as n of N, %).
4. Per health domain paragraph: every effect followed by "; class [N]; [certainty]" inside the same parenthesis.
5. Quality (AMSTAR 2): critical items failed, then overall rating.

## Length budget
| Type | Words | Paragraphs | Basis |
|---|---|---|---|
| RCT | 450–600 text (exclusive of tables) | 7–8 | B1 ~560, B2 ~450 |
| Cohort / population | 600–650 | 5–8 | B3 ~650, B4 ~600 |
| Pairwise MA | 1500–2600 (estimate for complex MAs) | 12 subsections | C3 ~2600, D1 ~600 |
| Dose-response MA | ~1500 (estimate) | 8–12 | C1 subsections 220–380 each |
| NMA | 1000–1100 (estimate) | 7–9 | C2 ~250+600+190 |
| SR without MA | 1500–2000 (estimate; scales with study count) | by group | D2 overview 400, group ~1100 |
| Umbrella | ~2200 (estimate) | by domain | D3 |
Tables hold everything beyond headline results; if the text exceeds these budgets, move numbers to a table or supplement.

## Template bank (slot with your own data)

### Flow and selection
1. [N] [units] were screened from [N] [sites]; [N] were recruited between [start date] and [end date]. [B2]
2. Overall, [N] participants were randomly assigned to [arm A] (n=[N]) or [arm B] (n=[N]). [B1,B2]
3. [N] participants ([%]) completed the primary outcome assessment and were included in the [analysis population]. [B2]
4. Of [N] records identified, [n] were removed as duplicates or on title/abstract, and [n] of [n] full-text reports were excluded for [reasons], leaving [n] studies with [n] participants (fig [N]). [C3,D1]
5. Where [n] reports drew on overlapping data, we used [report A] for [analysis X] because [reason], and [report B] for [analysis Y]. [C1]

### Baseline and characteristics
6. Baseline characteristics were [similar / are summarised] between groups (table [N]); mean age was [x] (SD [y]) years and [%] were [category]. [B1,B2]
7. Included studies ranged in size from [min] to [max] participants, with follow-up of [a] to [b] years. [C1]
8. Of the [N] included studies, [n] ([%]) were [design/funding feature]. [C2,D1]
9. During [N] person-years of follow-up (median [x] years, range [a] to [b]), [n] incident cases of [outcome] occurred. [B3]

### Primary outcome
10. The [outcome] at [timepoint] changed by [value] [unit] with [drug] and [value] with [comparator], an estimated difference of [value] (95% CI [a] to [b]; P[=/<][p]). [B1]
11. [Exposure] was positively/inversely associated with [outcome] ([measure] per [increment] [x], 95% CI [a] to [b]). [B3]
12. The adjusted mean difference at [timepoint] was [x] (95% CI [a] to [b]), which did not reach statistical significance; the [CI] [did / did not] exclude the pre-specified target difference of [X]. [B2]
13. Pooled across [k] trials ([N] participants), [exposure] [was associated with / was followed by] [a magnitude label] [change] in [outcome] versus [control] (mean difference [x] [unit], 95% CI [a] to [b]; I²=[x]%). [C3]

### Secondary and null outcomes
14. [Outcome A] and [outcome B] improved ([effect], 95% CI [a] to [b]); there was no statistically significant difference for [outcomes C, D, E] (fig [N]). [B2,D1]
15. [Exposure] was not statistically significantly associated with [outcome] (HR [x], 95% CI [a] to [b], [N] cases); power was limited at this site. [B3]
16. We found no clear evidence of a difference in [outcome list] between [groups] (fig [N]). [D1]

### Subgroup and sensitivity
17. Pre-specified subgroup analyses by [variables] showed [no statistically significant interaction / an interaction for [outcome] (P for interaction=[p])]; see supplement [N]. [B2,C3]
18. Removing [study] changed the pooled estimate for [outcome] from [x] ([a] to [b]) to [y] ([c] to [d]), so that it [no longer / now] excluded the null. [C1,D1]
19. Results were similar when [restriction], with estimates ranging from [x] to [y] (appendix [N]). [B3,C2]
20. Small-study effects were detected only for [outcome] (Egger P=[p]). [D1,C1]

### Meta-analytic structure
21. For [exposure], [n] of [N] articles supplied data for the highest versus lowest category; the pooled estimate was [x] (95% CI [a] to [b]; I²=[z]%). [C1]
22. A non-linear association was [not] found (P=[p] for non-linearity); each additional [increment] was associated with a [y]% [higher/lower] [outcome] (pooled estimate [z], 95% CI [a] to [b]). [C1]
23. Compared with placebo, all active [interventions] had [direction] [outcome] (odds ratios from [a] to [b]); [agent] was the exception (OR [x], 95% CI [a] to [b]). [C2]
24. [Agent X] and [agent Y] were similar in point estimate for [outcome] (OR [x], 95% CI [a] to [b]), with the interval compatible with differences in either direction. [C2, adapted]
25. Certainty ranged from [grade] to [grade]; [n] of [N] ([%]) comparisons were rated [grade]. [C2]

### Narrative synthesis and umbrella
26. [Author] ([year]) studied [outcome] after [exposure] in [setting] and reported [direction], from [v1] to [v2]; the study did not report a significance test / reported no statistically significant change. [D2]
27. [n] studies of lower methodological quality ([authors]) contributed to this outcome. [D2]
28. Pooled analyses of [k] [design] studies showed a [direction] association with [outcome] ([measure] [x], [a] to [b]; class [N]; [certainty]). [D3]

### Harms
29. Adverse events were reported by [x]% of participants with [drug] and [y]% with placebo; serious adverse events by [n] ([%]) and [n] ([%]); there were [no / n] deaths. [B1]
30. Expected complications ([list]) occurred with similar frequency (counts per arm), with no statistically significant between-group difference. [B2]

## Tense / voice / person
| Element | Tense | Voice | Person |
|---|---|---|---|
| Counts, flow, findings, analyses done | Past | Passive for events ("were randomised"); active with a named subject for estimates ("the drug lowered…" only if the design supports it) | "We" allowed for analysis actions ("we found", "we checked") [C2,D1]; passive in RCTs [B1,B2] |
| References to tables/figures | Present ("Table 2 shows") [B1,B3,C3] | Active | none |
| Results of a pooled model | Past; present only for stable descriptions of a plot | – | – |
| Cross-study summary lines in SR | Past; lead-in sentence of a group may be present [D2] | – | – |
| Never | Future, conditional, or "may/might" for observed data; reserve for Discussion (dose-response implications only [C3]) | | |

## Claim-strength ladder (strongest → weakest)
| Wording | Allowed when |
|---|---|
| "[X] reduced / increased [outcome] versus [control]" | Randomised comparison, CI excludes null, estimate given [B1] |
| "[X] was associated with higher/lower [outcome]" | Observational design, CI excludes null; no causal verbs (no "caused", "led to", "prevented" unless model-based estimate is explicitly framed as such [B4]) |
| "was positively/inversely associated" + CI + exposure unit | Standard observational wording [B3] |
| "consistent with a [direction] but did not reach statistical significance (95% CI [a] to [b])" | CI crosses null; direction may be stated, never "trend" or "tended to" |
| "no statistically significant difference" / "did not differ significantly" | NS result, any design [B2,D1] |
| "no clear evidence of a difference" | Group of null outcomes in MA/SR [D1] |
| "not statistically significant, but power was limited" | Few events/participants; cite N or events [B3] |
| "evidence is uninformative" | CI wide, includes both meaningful benefit and harm [A3] |
Hard rules: NS never becomes "no difference", "no effect", "equally effective", "similar efficacy", or "equivalent" unless a non-inferiority/equivalence margin was pre-specified and the CI lies within it. "Comparable"/"similar" may describe point estimates only with the CI attached. A CI crossing 1 is never "reduced by X%". "Significant" appears only with its CI/P and threshold. Nulls get the same format, CI and case count as positives [B3,D3]. Magnitude labels (trivial/small/moderate) only if defined in Methods against a minimal important difference [C3]. Vote-counting direction is labelled narrative synthesis, not evidence of effect [C1,D2]. In NMA and umbrella reviews, strength is carried by the stated certainty grade or evidence class, not adjectives ("robust", "strong", "clearly") [C2,D3].

## Numbers & statistics formatting
- Effect estimate order: arm values → difference/ratio → 95% CI → P [B1]. Observational: unit increment → estimate → CI → P [B3].
- CI: "95% CI [a] to [b]" with "to", not a hyphen, especially with negative values; use true minus. Within parentheses after first mention, "[x], [a] to [b]" is acceptable [D1,B3]. Always write "95% CI" in full at first mention per outcome.
- P: exact to 2–3 decimals; "P<0.001" never "0.000"; P is never reported alone; some BMJ-style papers omit P in text (CI only) [B4]; choose one convention for the whole paper. Do not describe P between 0.05 and 0.10 as a "trend" [A3].
- Counts: "n (%)" with the denominator stated ("[n]/[N]") when N<40 or when percentages could mislead [B2,C1,D2]; keep participants and trials separate [C2].
- Absolute and relative together for binary primary outcomes when the data allow (risk difference or events per 1000 plus RR/OR); OR-only results [D1] limit interpretability. Express HR in a time-anchored sentence.
- Decimals: effect ratios 2 decimals; percentages 0–1 decimal and consistent within a sentence set [B1]; continuous clinical measures 1 decimal; thousands separated by a space (23 192) in BMJ style [B4].
- Heterogeneity: I² next to each pooled estimate (not only the primary) [C3]; add τ² or prediction interval for random-effects when available [D3]; I² thresholds labelled low/moderate/high consistently with Methods.
- Certainty: GRADE/CINeMA grade attached to the outcome, with reason for downgrade/upgrade in the same sentence [C3,C2]; counts per grade for NMA.
- Dose-response: name increment and units; report non-linearity P and linear slope separately; convert slope to percent change [C1].
- Denominators at the top of each analysis: person-years [B4], participants analysed [B2], k studies and N [C1].
- State the analysis population (intention-to-treat/estimand) the first time each number appears [B1].
- Write "data not shown" or "not tabulated" when a number lacks a table [B3].

## Reporting-guideline checklist
CONSORT 2010 (RCT) (item numbers = CONSORT 2010; CONSORT 2025 renumbered the checklist to 30 items, so map numbers separately if the journal uses 2025): 13a randomised/allocated/analysed per group; 13b losses and exclusions with reasons; 14a recruitment and follow-up dates; 14b why trial ended/stopped; baseline table pointer (15); 16 numbers analysed by group; 17a primary and secondary outcomes with effect size and precision; 17b binary outcomes in absolute and relative terms; 18 ancillary analyses (subgroup, adjusted, labelled pre-specified vs exploratory); 19 harms per group. 
STROBE: 13 participants at each stage and reasons; 14 descriptive data, follow-up time; 15 outcome events/measures; 16 unadjusted and adjusted estimates with precision, adjustment set; 17 other analyses.
PRISMA 2020: 16 selection (flow, exclusions with reasons); 17 characteristics; 18 risk of bias in studies; 19 individual-study results; 20a–d syntheses (heterogeneity, sensitivity); 21 reporting biases; 22 certainty. PRISMA-NMA adds network geometry, ranking with uncertainty, inconsistency. MOOSE for observational MA (dose-response method named). SWiM: grouping rule, metric/direction, heterogeneity and certainty statements. GRADE: certainty per outcome. Umbrella: AMSTAR 2, evidence class, prediction interval, excess significance.

## Do / Don't
- Do open each paragraph with the question or analysis it answers and end on the number; Don't open with the interpretation [A1].
- Do report the primary outcome first, in the order of Methods; Don't promote a significant secondary above a NS primary [B2].
- Do report NS primary results with direction, CI and the target difference; Don't write "trend", "tended", "promising", "disappointing" [B2,A3].
- Do give a power statement beside nulls from low-event sites; Don't omit CIs for nulls [B3].
- Do say why an earlier estimate changed [B4]; Don't compare with literature in Results.
- Do list all null outcomes in one sentence; Don't give each its own paragraph [D1].
- Do disclose sensitivity analyses that weaken the finding in the same sentence [C1,D1]; Don't hide them in Discussion.
- Do point to tables/figures ("table 2 shows"); Don't re-narrate every cell [B1,B3].
- Do label pre-specified vs post hoc [A3]; Don't present exploratory subgroup patterns as findings.
- Do report subgroup claims via interaction test; Don't infer subgroup effects from one significant and one NS stratum [C1 gap].
- Do keep the same format across trials/exposures [B1].

## LLM-draft failure modes → fix
| Tell | Why it reads as AI / is wrong | Rewrite pattern |
|---|---|---|
| "Interestingly, the intervention showed a remarkable improvement" | Evaluative adjective and interpretation in Results | State the estimate with CI: "[outcome] was [x] vs [y] (difference [d], 95% CI [a] to [b])" |
| Restates the table cell by cell | Duplicates table; hides the headline | Name 3–5 key numbers, point to the table, report exceptions |
| "No difference between groups" for a NS result | Absence of evidence read as evidence of equivalence | "No statistically significant difference (difference [d], 95% CI [a] to [b])" |
| "A trend toward benefit (P=0.07)" | Trend language for NS | "The estimate favoured [arm] (95% CI [a] to [b]), which crossed the null" |
| "HR 0.88 (0.70 to 1.10): 12% reduction" | CI crossing 1 treated as effect | Report HR and CI; omit percent reduction |
| P value without effect size | Not interpretable | Add estimate and CI before P |
| Uniform "Overall, X was… Additionally, Y was…" connectors | Generic transitions | Open with the outcome name or comparison; use exposure/outcome as topic sentence |
| "The results demonstrate that…" | Interpretation verb; certainty overclaim | "[Outcome] was [value] in [group] and [value] in [group]" |
| Rounded or invented numbers, mismatched n and % | Fabrication/accuracy risk | Compute % from the stated n/N; verify against source table before drafting |
| Mixed estimand/analysis populations without labels | Reader cannot tell ITT from per-protocol | Name the estimand in the first clause [B1] |
| Subgroup headline from one significant stratum | Unsupported claim | Report interaction P; label exploratory |
| Pooled estimate with "strongly supports" | Certainty claimed by adjective | Cite certainty grade/class and reasons |
| Explains why the result occurred | Mechanism belongs in Discussion | Delete; keep the observation |

## Mini worked example (fictional)
Before (LLM-style):
"Interestingly, our results demonstrate that the novel digital coaching program significantly improved glycaemic control compared with usual care, with a remarkable reduction in HbA1c. There was a trend toward fewer hypoglycaemic events in the intervention group, suggesting the program is safe. Both groups were comparable at baseline. Overall, the findings highlight the pivotal role of digital health."

After (journal-style):
"Of 1204 adults screened, 640 were randomised to digital coaching (n=320) or usual care (n=320) between March 2022 and June 2023; 592 (92.5%) provided HbA1c data at 12 months. Baseline characteristics are in table 1 (mean age 58.2 (SD 9.1) years; 47.3% women).
At 12 months, mean HbA1c was 7.4% (SD 1.0) with digital coaching and 7.9% (SD 1.1) with usual care (adjusted difference −0.5 percentage points, 95% CI −0.7 to −0.3; P<0.001). Severe hypoglycaemia occurred in 9 (2.8%) and 14 (4.4%) participants, respectively (risk difference −1.6 percentage points, 95% CI −4.5 to 1.3); the difference was not statistically significant. Serious adverse events were similar in frequency (table 3)."

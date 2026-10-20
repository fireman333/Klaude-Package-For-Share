# Cross-cutting style and de-LLM guide — rules distilled from 14-paper corpus

Use after drafting any section, and while drafting. Evidence tags [A1–D3] refer to the corpus. Rules here override a section file only for wording, never for facts.

## A. Sentence-level craft
1. **Vary length on purpose.** Pair short declaratives (6–14 words) with longer multi-clause sentences (30–60 words, mainly Methods). Typical guidance: about 25–30 words average, paragraphs of about 75–150 words [A2,B1,C1,A3]. Never let five consecutive sentences fall in the same length band.
2. **One idea per sentence, one main idea per paragraph.** Put the topic sentence first and let the paragraph's last sentence carry the answer in Results [A1,A2].
3. **Verbs over nominalisations.** "We analysed" not "an analysis was performed"; "X reduced Y" not "the reduction of Y was observed with X". Plain verbs: show, find, suggest, argue, consider [A3,D1].
4. **Concrete numbers over adjectives.** Replace "substantial", "many", "few", "large" with the count, ratio or range, or delete [B1,B2,C2,D2,D3]. "Significant" is reserved for statistical significance and needs a CI/P behind it [D1].
5. **Consistent keywords.** Name each exposure, outcome, group and analysis once and reuse the identical term (no elegant variation). Keep the question's terms in the answer [A4].
6. **Abbreviations defined once** at first use in abstract and again at first use in the main text; avoid abbreviations used fewer than three times; no abbreviations in the title [B1,C2].
7. **Parallel structure for parallel results.** Report trial 1 and trial 2, or each outcome, with identical sentence frames and fixed statistic order (estimate, CI, P, heterogeneity) [B1,C1,C3].
8. **Reasons attached to choices.** Each exclusion, interaction term, sensitivity analysis and model choice gets one clause saying why [B4,D1,C2].
9. **Punctuation.** Use parentheses, commas, colons, semicolons for asides. Em dashes: at most one or two per 1000 words in the corpus; keep to that [A1–D3, passim].
10. **Spelling by journal.** UK (randomised, programme, favouring, haemoglobin) for BMJ/Lancet; US (randomized, program, favoring, hemoglobin) for NEJM/JAMA. Pick once per manuscript and never mix [B1 vs B2].
11. **Voice.** Active with "we" is accepted in Methods/Results/Discussion of all corpus papers; passive survives for procedures where the agent is irrelevant.
12. **Cite selectively** (pertinent, original, recent, actually read); drop citations for standard facts [A2]. Numbers and counts are not claims needing decorative references.

## B. Global tense map (IMRaD)
| Part | Tense | Notes |
|---|---|---|
| Title | none / noun phrase | Name exposure/intervention, population, design where the journal wants it |
| Abstract: background/objective | Present (state) or infinitive | |
| Abstract: methods, results | Past | |
| Abstract: conclusion | Past for the finding, present + modal for implication | Impersonal; bare verbs only for randomised contrast [B1] |
| Introduction: established knowledge, gap, question | Present | Present perfect for prior studies' cumulative status |
| Introduction: this study's aim | Present or past, consistent with the paper | |
| Methods | Past (what was done); present for fixed facts about instruments/definitions | |
| Results | Past; present only to point to tables/figures ("Table 2 shows") | |
| Discussion: own findings | Past | |
| Discussion: interpretation, mechanisms, implications | Present with hedging modal | |
| Limitations | Present or past; modal for direction of bias | |
| Conclusion | Past for the finding, present + modal for implication | Impersonal (no "we") |
[A2,A4,B2,C3,D2]

## C. Unified claim-strength ladder and causal language by design
| Level | Wording | Allowed when |
|---|---|---|
| 1 | "reduced / improved / increased" | Randomised comparison, primary or pre-specified outcome significant, bounded to the measured outcome |
| 2 | "supports", "is consistent with" | Evidence of adequate certainty; or NS with CI excluding the margin (name the margin) |
| 3 | "is associated with" | All observational and pooled-observational findings; default verb |
| 4 | "suggests", "indicates" | Interpretation of a single result or pattern |
| 5 | "might / may / could" + named reason | Mechanism, residual confounding direction, exploratory or post hoc subgroup, policy effects |
| 6 | "did not differ significantly", "no statistically significant difference", "not superior to" | Any NS result; with point estimate, CI, and power or margin comment |
| 7 | "cannot be determined / unknown / unclear" | Evidence absent; do not speculate beyond data |

Rules by design:
- **RCT**: causal verbs allowed for the randomised contrast only; secondary/subgroup results are hypothesis-generating [B1,B2].
- **Cohort / population observational**: "associated with"; causal disclaimer once as a plain sentence in Methods or Discussion, then keep "associated" everywhere (Results, Conclusion) [B3]. Identification claims (natural experiment, cut-off design) are argued as design strengths, not as proof [B4].
- **Pooled observational (dose-response)**: "associated with"; do not translate to "replacing X with Y would extend life" unless you state it as an implication contingent on causality [C1].
- **Meta-analysis of RCTs / NMA**: "may have advantages", "might"; rank claims scoped to certainty, with rankings of efficacy noted as not answering cost or harm questions [C2,C3].
- **SR without MA / umbrella**: direction + strength tier (evidence class, GRADE); never imply a pooled effect [D2,D3].
- **Non-significant**: never "no difference", "equally effective", "equivalent", "no association", "proves safety" without a pre-specified equivalence/non-inferiority margin. CI crossing 1: do not write "reduced by X%". Wide CI: report estimate, CI, say sample cannot exclude moderate effects [A3,B2,B3].
- **Non-inferiority passing margin**: "not inferior within the pre-specified margin", not "same".
- Do not read an NS result as informative about equivalence unless sample size bounds type II error [A3].

## D. Number and statistics style sheet
- **Fixed report order** for each effect: group values or event counts, effect size, 95% CI, P value, heterogeneity [B1,C1,C3].
- **CI style**: choose by journal: "95% CI 0.93 to 0.98" (BMJ, avoids hyphen ambiguity for negatives) or "(0.93–0.98)". Use "to" if any bound is negative. Same style throughout.
- **P values**: exact to two or three significant digits (P=0.03, P<0.001); never "P=0.000"; never P alone without estimate and CI [A4]. "NS" is not a substitute.
- **Absolute + relative**: pair relative measures with absolute risk or risk difference, and state denominators ("n of N (%)") [B2,C2,D3].
- **Denominators** on every percentage first mention; count the same population in text and flow diagram [D2].
- **Decimals**: percentages to whole numbers unless <10% or reasons to show one decimal; effect sizes two decimals (HR 0.84); do not report more precision than the data support. Keep consistent decimals across a table column.
- **Thousands separators**: follow journal (thin space or comma); never mix.
- **Units**: every effect paired with an interpretable increment (per 10 g/d, per 100 mL/d) and why chosen [B3,C1].
- **I²**: give value with a rule stated in Methods for "substantial/moderate heterogeneity"; apply the rule consistently; add tau² or prediction interval when relevant [C1,D1].
- **GRADE/certainty**: tier labels (high/moderate/low/very low) with counts of comparisons or outcomes in each tier; put evidence class and GRADE inside the same parenthesis as the estimate in umbrella reviews [C2,D3].
- **Ranges**: "from X to Y" or en dash, not "X-Y" when negatives present.
- **Subgroups**: paired figures in one sentence ("[x]% v [y]%" in BMJ; "versus" elsewhere), full estimates pointed to a table [B4].
- **Pre-specification label**: mark each subgroup/sensitivity analysis as a priori or post hoc where introduced [C3,A3].
- **Software**: name package and version in Methods [D1,D3].

## E. BANNED / AVOID lexicon of LLM tells
Treat every hit as a revision trigger; replace with a concrete statement or delete. Reserve "robust" only for a named statistical property (robust variance, robust to a named sensitivity analysis) [B2].

| Tell | Journal-style replacement |
|---|---|
| delve into / explore the intricate… | examine, assess, analyse; or state what was measured |
| pivotal, crucial, vital, key role | important only if followed by a measured consequence; usually delete |
| landscape (of treatment/research) | state the field: "current guidelines recommend…" |
| underscore(s), highlight(s), showcase | show, indicate, suggest |
| robust (non-statistical) | consistent across [named analyses]; or name the sensitivity analysis |
| comprehensive | state scope: "searched four databases to [date]" |
| novel, groundbreaking, innovative, game-changing | omit; state the gap filled and the concrete addition |
| intricate, multifaceted, nuanced, complex interplay | name the specific factors |
| Furthermore, Moreover, Additionally (as openers on many sentences) | start with the subject, or use "also"; connect only where logic requires (however, because, so) |
| "It is important to note that…" / "It is worth noting…" | delete and state the fact |
| "plays a crucial role in" | "contributes to" with evidence, or a measured association |
| "sheds light on" / "paves the way for" / "a testament to" | "indicates", "allows [named study]" or delete |
| "In today's world" / "in recent years" openers | open with a quantified burden: "[Condition] affects [N] people…" |
| "In conclusion" mid-Discussion; "Overall" paragraph tails | delete; keep one Conclusion at the end |
| "first study to…" overclaim | "to our knowledge, few studies have…" only if verified by search; or state the gap |
| "not only… but also" balance | two plain clauses, or one clause |
| triplet lists (A, B, and C) for rhythm | list only items actually measured; vary list length |
| em-dash overuse | commas, parentheses, colon, or split the sentence |
| bold-colon pseudo-headings inside paragraphs ("**Key point:**") | prose with a topic sentence; use journal subheadings only |
| "significant" for non-statistical meaning | "large", with the number; or "important" with reason |
| "demonstrates", "proves", "confirms" | "shows" (RCT) or "suggests / is associated with" |
| "leveraging", "utilise", "harness" | use |
| "a wide range of", "a variety of", "numerous" | give the number |
| "emerging evidence suggests" | cite and name the studies |
| "may potentially", "could possibly" | single hedge: "may" |
| "mounting / growing body of literature" | give number of studies or the date range |
| "This highlights the need for further research" | name the next design (see 06-conclusion) |

## F. Structural tells
- **Uniform paragraph length** (all paragraphs 90–110 words). Fix: allow a two-sentence paragraph where the point is short; merge fragments only if one idea.
- **Every paragraph ends with a mini-summary** ("Overall, these findings suggest…"). Fix: end on the last fact or on the paragraph's answer; delete the recap [A1,D3].
- **Symmetric strengths/limitations** (three strengths, three limitations). Fix: write limitations as long as needed, ordered by the size of the threat, each with direction of bias; keep strengths to what actually reduces bias [B1,B3,B4,C3].
- **Hedge stacking** on every sentence. Fix: one hedge per claim, tied to a stated reason (named confounder, sample, missing data) [B3,C3,D2].
- **Uniform openers** (The..., This..., These findings...). Fix: lead with different grammatical subjects: the study group, the comparison, the number.
- **Parallel template across all sections** (same sentence skeleton per paragraph). Fix: keep parallelism only for parallel results; elsewhere vary form.
- **Smooth transitions between every paragraph.** Fix: drop connectors that add no logic [B3 tolerates repeated plain openers: "Since", "Thus"].
- **Generic limitations** ("small sample size, residual confounding"). Fix: quantify (percentage with missing data, number of cases) and name the analysis that addresses it [B2,B3].
- **Perfectly resolved narrative**: report anomalies and unexplained results plainly as unknown [B4,D2,C1].
- **Balanced "pros and cons" in the Discussion opening.** Fix: open with what the data allow without doubt, then move outward [A3].
- **Sections of equal weight.** Fix: let Results carry numbers and Discussion keep interpretation proportionate to evidence.

## G. 12-step revision pass (execute in order)
1. **Fidelity check.** Every number, unit, CI and denominator in the text matches the source table or output. Fix mismatches before style.
2. **Claim audit.** For each conclusion-bearing sentence assign a rung on the ladder (section C); downgrade verbs that exceed the design; replace NS wording ("no difference", "equivalent") with the correct form.
3. **Lexicon sweep.** Search the draft for every word in section E; replace or delete. Re-search after edits.
4. **Opener sweep.** Check first sentences of Introduction, each Discussion paragraph and the Conclusion: remove mood-setting openers; lead with a quantified fact or the paragraph's point.
5. **Connector cull.** Remove Furthermore/Moreover/Additionally and any "In conclusion/Overall" except the final one; keep only logic-bearing connectors.
6. **Punctuation pass.** Count em dashes (≤1–2 per 1000 words), colons used as headings, bold lead-ins; convert to commas, parentheses or sentences.
7. **Triplet and "not only…but also" pass.** Break every reflexive three-item list; keep only those matching real counts.
8. **Rhythm pass.** Mark each sentence's length; split runs of similar length; allow some short declaratives and some long Methods sentences.
9. **Paragraph pass.** One idea each; delete trailing summary sentences; unequalise paragraph lengths naturally.
10. **Hedge pass.** One hedge per claim, with a named reason; delete "may potentially"-type stacks; make limitations specific with direction of bias.
11. **Terminology and spelling pass.** One term per concept; abbreviations defined once; UK/US spelling and CI/P format consistent with target journal; tense map (section B).
12. **Reader-test.** Read abstract then conclusion only: do they answer the same question with the same key terms, without new numbers in the conclusion? Cut anything that does not serve that answer. Then run the guideline checklist (CONSORT/STROBE/PRISMA items) for the section type.

## H. AI-use disclosure (ICMJE, 2023+ recommendations)
Editing to remove LLM-style prose does not remove the duty to disclose. ICMJE recommends that authors disclose use of AI-assisted technologies at submission, describe it in the cover letter and in the Methods or Acknowledgements as the journal directs, keep humans accountable for all content, and not list AI as an author. AI-generated images or text must not replace data. Check the target journal's own policy (wording and location vary).

Template (adapt to journal; keep factual):
> During preparation of this work the author(s) used [tool name, version, developer] for [specific purpose, e.g. language editing, drafting of the first version of the Introduction, code suggestions for the statistical analysis] on [date or period]. The tool was [not] given [participant-level / unpublished] data. After using the tool, the author(s) reviewed and edited the output and take full responsibility for the content of the publication. The tool is not listed as an author.

Practical notes:
- Disclose purpose and extent, not just the product name.
- Do not enter identifiable patient data or unpublished confidential data into tools without institutional approval.
- Reference lists produced with AI assistance must be checked against the original sources; fabricated or mis-stated citations are the authors' responsibility.
- Where the journal states a stricter rule (for example prohibition in peer review), follow the journal.

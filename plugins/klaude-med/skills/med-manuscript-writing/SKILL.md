---
name: med-manuscript-writing
description: "Medical journal manuscript writing + de-LLM revision (corpus: NEJM/BMJ originals, MA, SR). Draft/revise/audit any IMRaD section for RCT, cohort, MA, SR; claim-strength and NS-wording gates; LLM-tell scorer. Trigger: /med-manuscript-writing, /med-write, /mmw, 寫醫學論文 section, 改 manuscript, 去 AI 味, de-LLM. Results from Excel → manuscript-results first."
---

# med-manuscript-writing

Section-level writing harness for medical journal articles. Rules come from a corpus read by 14 Haiku readers and 6 Sonnet synthesizers (2026-10-09). Corpus list: `references/corpus.md`.

## Modes

| Command | What it does |
|---|---|
| `/med-write draft <section> [type] [journal]` | Draft a section from the user's facts/data/outline |
| `/med-write revise <file> [section]` | Revise existing text to journal style (keeps every number) |
| `/med-write de-llm <file>` | Score LLM tells → rewrite pass → re-score; report before/after |
| `/med-write audit <file>` | Read-only: tell score + reporting-guideline gaps + claim-strength errors |
| `/med-write local <file> [--model ...]` | Optional: lexical-only de-LLM pass on a local MLX model, then Claude audits (`scripts/local_revise.py`) |

No mode given → infer: text pasted + "改/revise" → revise; "像 AI 嗎/去 AI 味" → de-llm then audit; facts/outline only → draft.

## Step 0 — Classify (always)

Determine and state in one line: **article type** (RCT / cohort / case-control / cross-sectional / pairwise MA / NMA / dose-response MA / SR without MA / umbrella review), **target journal style** (NEJM/JAMA = US spelling, Background–Methods–Results–Conclusions abstract; BMJ/Lancet = UK spelling, Objective/Design/Setting/Participants… abstract; no journal named → keep the author's existing spelling and use BMJ-style structure). NEJM/JAMA conventions in the references rest on one corpus paper (B1), so treat them as indicative, and **section(s)**. Read project context per **Pipeline integration** below before asking the user anything.

## Pipeline integration (research skills)

**Read inputs in this order; ask only for what is still missing (usually target journal).**

| Source (cwd) | Use |
|---|---|
| `research_plan.json` (from `research-plan`, if you use it) | `study.design` → article type; `estimand_type` (causal/associational) → verb ceiling; `outcomes.primary/secondary` → outcome names, order; `covariates`, `multiplicity`, `advanced_analyses.strobe` → Methods; `table_figure_mapping` → "(Table 2)" pointers; `output_dir`, `manuscript.analysis_files[]` → where results live; `decision_log` → limitations / deviations. `pipeline_profile: explore` → warn that manuscript steps are parked |
| `configs/{step_id}_config.json` with step_id `manuscript` (from `manuscript-results`; standalone runs use `/tmp/manuscript_config.json`) | `language`; `journal_style` is free text and often null, so treat it as a hint only and confirm the target journal with the user |
| `<output_dir>/Results_Section.docx` or Results draft | Results text to **revise/audit only**; never re-draft Results that `manuscript-results` produced |
| `pico.yaml`, `*.qmd` section drafts of a systematic review / meta-analysis (if you have them) | MA/SR type and PICO; sections to audit/de-llm |
| `synthesis.md`, `bibliography.json`, `references.bib` (from `deep-research` or your own literature work) | Introduction burden/gap claims and Discussion comparisons; resolve `[TODO: ref]` only from these, never from memory |

**Who drafts what**

| Section | Drafted by | med-manuscript-writing role |
|---|---|---|
| Results (cohort/RCT with Excel outputs) | `manuscript-results` | revise / audit / de-llm |
| MA manuscript (all sections) | your own MA drafting tool | audit / de-llm on `.qmd`; output `*.revised.md` |
| Title, Abstract, Intro, Methods, Discussion, Conclusion (non-MA) | **this skill** | draft + revise |
| Generic clarity edit | `manuscript-writing-review` | run before this skill |

**Style precedence on conflict**: target journal instructions > the drafting skill's own format rules (e.g. AMA citations) > this skill's sentence-craft / de-LLM rules.

**Downstream**: after a full draft, suggest `research-guardian` (Writing Guard) for content verification.

## Step 1 — Load only the references you need

| Section | File |
|---|---|
| Title, Abstract, key-message box, keywords | `references/01-title-abstract.md` |
| Introduction | `references/02-introduction.md` |
| Methods | `references/03-methods.md` |
| Results | `references/04-results.md` |
| Discussion (incl. strengths/limitations) | `references/05-discussion.md` |
| Conclusion | `references/06-conclusion.md` |
| Any revise / de-llm / audit | `references/07-style-and-de-llm.md` (always) |

Each section file has (10 parts): move structure by article type → length budget → template bank → tense table → claim-strength ladder → number formatting → guideline checklist → do/don't → LLM failure modes → worked example.

## Step 2 — Draft or revise

1. Lay out the **move structure** for the article type first (one line per paragraph), then write paragraph by paragraph.
2. Use the template bank as scaffolds, not boilerplate: vary sentence openings and lengths; fill every slot with the user's real content.
3. **Never invent** numbers, citations, trial names, registration IDs, or results. Missing fact → leave `[TODO: …]` placeholder and list it at the end. Unreferenced background claims ("affects millions") → keep the claim, add `[TODO: ref]`, and replace vague magnitude words only if the text gives the number.
4. Revise mode: preserve every number, CI, p value, effect measure, and drug/disease name exactly; preserve every substantive claim unless it is an overclaim (then downgrade wording, and say so).

## Step 3 — Hard gates before delivery

- **Stats wording gate**: NS result → "no statistically significant difference" / "did not differ significantly"; never "no difference", "equally effective", "equivalent", "similar efficacy" unless a non-inferiority/equivalence margin was prespecified ("comparable"/"similar" only to describe point estimates with the CI attached). CI crossing 1 → no "reduced by X%". Observational design → association language, no causal verbs ("reduced", "prevented", "led to") unless a causal-inference design justifies it and that is stated.
- **Claim ceiling**: Conclusion may not exceed what the primary analysis shows; no practice recommendations ("should be first-line") from a single observational study.
- **Guideline gate**: run the section's checklist from the reference file; list unmet items as `[MISSING: CONSORT 7a sample size]`-style notes.
- **Tell scan**: `python3 ${CLAUDE_SKILL_DIR}/scripts/ai_tell_score.py <file>` before and after; target composite < 15 and zero hits for banned lexicon (see 07). Score the manuscript text only (never a file that also contains the change log, which quotes banned words). Report both scores.

## Step 4 — Output format

- Deliver the revised/drafted text (in the file if given a file; write `<name>.revised.md` next to it rather than overwriting).
- Change log goes in chat or a separate `<name>.changelog.md`, never inside the manuscript file: ① structural changes ② claim-strength downgrades ③ `[TODO]`/`[MISSING]` items ④ tell score before → after.
- Chat explanation in Traditional Chinese (user preference); manuscript text in English unless the user asks otherwise.

## Local-model mode (`local`) — optional, never the default

Default for `de-llm` / `revise` is Claude doing the full pass (lexical + structural + claim strength). In testing, Claude's own pass reached composite 0.0 with all claims corrected; the 4B local model reached 18.1 on lexical items only. Use `local` only when the user explicitly wants offline/local processing (e.g. unpublished data they prefer not to send out).

```bash
# 需 Apple Silicon Mac。preflight: "$PY" -c 'import mlx_lm' must succeed; otherwise create a venv
# (python3 -m venv ~/.venvs/mlx && ~/.venvs/mlx/bin/pip install mlx-lm; ask before downloading any model)
cd ${CLAUDE_SKILL_DIR}/scripts
PY="$HOME/.venvs/mlx/bin/python"   # 換成你自己的 venv
HF_HUB_OFFLINE=1 "$PY" local_revise.py --rules ../references/local-model-rules.md \
  --in draft.md --out draft.local.md        # default model: mlx-community/Qwen3-4B-Instruct-2507-4bit
python3 ai_tell_score.py draft.md draft.local.md
```

- **Minimal-edit design**: the scorer flags exact phrases per sentence; the model may change only those. Free "rewrite this paragraph" prompts made Qwen3-4B invent numbers, studies and even a different drug (tested 2026-10-09).
- **Guards**: a rewrite is rejected (1 retry, then original kept) if it loses or invents any number, changes length >25%, or adds >25% new content words.
- **Default = lexical pass only.** `--claim-pass` lets the local model also fix claim strength, but on a 4B model it inverted an effect direction ("lower bleeding" → "higher bleeding") with no number changed, so nothing caught it. Claim-strength fixes are Claude's job: after any local pass, Claude runs Step 3 gates on the output and fixes residual grammar slips (e.g. "a alternative").
- Always use `HF_HUB_OFFLINE=1` so a missing/incomplete model never triggers a silent multi-GB download; downloading a new model needs the user's explicit OK.

## Ethics note (keep short, say once)

De-LLM editing improves prose; it does not change authorship duties. ICMJE and most journals require disclosure of AI-assisted writing — `07-style-and-de-llm.md` contains a disclosure template. Statistical watermarks are not "removed" by any guarantee; the rewrite pass changes surface style only. 

## Related skills

`manuscript-results` (Excel stats → Results .docx) · `manuscript-writing-review` (generic clarity edit) · `academic-style` (figure styling).

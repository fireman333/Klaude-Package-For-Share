# Academic Slide Conventions (Shared)

Canonical hard rules for any Claude Code skill that produces academic `.pptx` (mentor presentations, case conferences, morning report, grand rounds, journal club). Three rules, all enforced at pre-flight before `pres.save()`.

**Consuming skills**: `case-discussion-pptx`, `journal-club-discussion-pptx`, and any academic pptx skill.

---

## Rule 1 — Slide body English-only; Chinese goes in speaker notes

Visible slide content (`title`, `context`, bullets, decision-tree steps, footer citations) is **English only**. Chinese (including user-facing abbreviation glossaries) goes in `slide.addNotes([...].join("\n"))` as named blocks:

- `=== 縮寫全稱 ===` — list every English abbreviation on this slide with full form + 中文 translation. **Mandatory on every slide with abbreviations**, not just the first one (presenter reads off each slide independently).
- `=== 核心論點 ===` — Chinese rephrasing of key slide argument.
- `=== 可預期提問 ===` — anticipated attending questions.
- `=== 補充數據 ===` — supplemental stats / context not on slide.

**Exceptions**:
- Proper nouns (drug brand names, institutions, trial names like `WATCHMAN`) can appear on slide body as-is.
- `q{n}_memo.md` and markdown working notes are Chinese — but Chinese there must **never** be copy-pasted into slide body.
- OE / other-LLM / PubMed responses in Chinese must be translated to English before landing on slide body.
- User says "中英對照" / "用中文做" / 衛教 slide → relax.

**Pre-flight check (mandatory)**: Scan slide body (not notes) for CJK characters before save. If any, stop and fix. Reference impl: `journal-club-discussion-pptx/render.py` `rule1_preflight()`.


---

## Rule 2 — Citation metadata must include three fields: study type / country / n

Every cited study is formatted:

```
Author Year PMID xxxxx — **<study type>**, **<country>**, n=<N>; <take-home>
```

**Study type vocabulary** (pick the specific variant):
- `RCT (multicenter)` / `secondary analysis of RCT` / `prospective cohort` / `retrospective cohort` / `retrospective propensity-matched cohort` / `case series` / `systematic review` / `SR + meta-analysis` / `Cochrane SR` / `meta-analysis` / `clinical practice guideline` / `analytical method comparison` / `biological variation study` / `EQA simulation study` / `nationwide retrospective cohort`

**Country**:
- Single country: `US` / `UK` / `Japan` / `Taiwan` / `Korea` / `China`
- Multinational: `multinational` + number of countries (`multinational (N=12)`)
- Famous institutions in parens: `US (MSKCC)` / `UK (Leeds + Southampton, FACS trial)`

**n**: participants / eyes / lesions / studies (for meta-analyses).

**Guidelines** (NCCN / ASCO / ASCRS / EAU) have no `n` but still need study type `clinical practice guideline` + country.

**Where these must appear** (all three fields):
- Markdown memo 「補充數據」 inline
- Q&A citations
- Key Citations section
- Speaker notes `=== 補充數據 ===` block

**Slide body exception**: Space-limited slide body may display only `<study type> + n` (country dropped). Speaker notes must still show all three.

**Why**: Audience needs to assess evidence hierarchy (RCT > prospective > retrospective > case series) + regional representativeness (US guideline vs. Asian retrospective) + statistical power (RCT n=234 vs. case series n=30) in one second. One field alone is insufficient.


---

## Rule 3 — Audit verdict may NOT appear in slide body

**Forbidden in slide body** (title / bullet / footer / corner):
- Audit badges `🟢` / `🟡` / `🔴`
- Text `Audit: PASS` / `CAUTION` / `FAIL`
- Any hint of citation-verification status

**Audit info is allowed in**:
1. Speaker notes `=== Audit ===` block (presenter-view only, audience cannot see)
2. Hidden appendix slide (`pres.addSlide({ hidden: true })`, title prefixed `(Appendix) Citation Audit Summary`; unhide on-demand if asked)
3. Markdown source header (for human review, not presented)

**Override**: Only if user explicitly says "audit 頁要顯示" / "show audit on slide".

**Why**: Attending seeing `🟢 PASS` / `🟡 CAUTION` on a slide infers "this is AI-generated and self-validated" — implicit signal that *lowers* citation credibility. Academic norm is "show citations directly; reveal verification only if asked." Don't volunteer verification.


---

## Pre-flight checklist (before `pres.save()`)

```python
def slide_conventions_preflight(pres):
    for idx, slide in enumerate(pres.slides, start=1):
        # Rule 1: body English-only
        if contains_cjk(slide.body_text()):
            raise ValueError(f"Slide {idx}: CJK in body. Rule 1 violation.")
        # Rule 1: abbreviation block in notes
        if has_abbrev_in_body(slide) and not has_block(slide.notes, "=== 縮寫全稱 ==="):
            raise ValueError(f"Slide {idx}: missing 縮寫全稱 notes block.")
        # Rule 3: no audit badges in body
        if has_audit_badge(slide.body_text()):
            raise ValueError(f"Slide {idx}: audit badge in body. Rule 3 violation.")
    # Rule 2: citations have 3 fields — grep text for 'n=' and '<study type>' pattern
    # (run externally via refs_format.py or enforce in citation-building code)
```

Reference pre-flight implementation: `journal-club-discussion-pptx/render.py` (`rule1_preflight`, `rule3_preflight`).

---

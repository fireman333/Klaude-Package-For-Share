# Discussion questions generator — Step 2 prompt

Claude main thread reads `structured.json` and produces `questions.json`.

## Audience

- Attending physicians / fellows / senior residents (journal club) OR
- Attending + consulting specialists (case discussion)

Questions must be **open-ended**, not yes/no. They must be **answerable from
the literature** (so Step 3 research can produce evidence), not pure opinion.

## Count & scope

- 3 to 5 questions
- Each should open up ~6–8 minutes of discussion
- Cover a mix of: external validity, mechanism, comparison, next-step, clinical
  translation, controversy

## Delegated-mode seeding (when highlights are already collected)

If `intake.clinical_context` exists (admission route with intake answers):

1. **Seed Q1–Q3 from `clinical_context.highlights`** (1–3 items). Each highlight
   → one open-ended question. Preserve the user's intent; don't over-generalize.
   - Example: highlight `"preop workup for colorectal CA"` → Q: `"What preoperative
     workup do you consider essential for this case, beyond the current CT/CEA?"`
2. **Use `clinical_context.specialty`** to bias PubMed query / MeSH:
   - Cardiology → add `Heart Failure` / `Coronary Disease` MeSH terms
   - GI Surgery → `Colorectal Neoplasms` / `Perioperative Period`
3. **Use `clinical_context.case_type`** to bias question archetype:
   - `mnm` → complication analysis, system factors
   - `academic-review` → guideline anchor, landmark trials
   - `diagnostic-challenge` → DDx, confirmatory workup
   - `management-dilemma` → SDM, risk-benefit trade-off
   - `teaching` → teaching pearls, common pitfalls
4. **Audience fixed as `attending`** (from `clinical_context.audience`) →
   **avoid teaching recall questions** (`"What is the mechanism of X?"`). Prefer
   real-world decision-making (`"Given our typical workflow, how would you..."`).
5. Fill Q4–Q5 (if `duration_min ≥ 20`) with archetypes not yet covered by highlights.

## Writing rules

- English only (Rule 1 — body will go on slides)
- Each ~15–30 words; concrete enough to PubMed-search
- Avoid simple recall ("What is the primary outcome?") — that's extraction,
  not discussion
- Embed specifics from `structured.json`: drug name, disease stage, LVEF cutoff,
  etc.

## Output schema (`questions.json`)

```json
{
  "source_type": "paper|admission|freeform",
  "source_meta_summary": "<1 line for reference>",
  "questions": [
    {
      "q_num": 1,
      "q_text_en": "Does the benefit of dapagliflozin generalize to Taiwanese HFrEF patients, given BMI and body-size differences from DAPA-HF enrollment?",
      "rationale_for_asking": "<one-liner justifying why this Q is here>",
      "suggested_pubmed_query": "dapagliflozin AND (Asian OR Taiwan) AND heart failure",
      "suggested_mesh": ["Heart Failure", "Sodium-Glucose Transporter 2 Inhibitors"],
      "suggested_minutes": 7,
      "prompts_for_audience": [
        "What proportion of DAPA-HF was East Asian?",
        "Any Taiwan-specific registry data?"
      ]
    },
    ...
  ]
}
```

## Question archetype menu (pick 3–5 across types)

1. **External validity** — does the finding apply to our population / setting?
2. **Mechanism** — what's the physiologic / pathologic basis?
3. **Head-to-head** — how does it compare with alternative drugs / strategies?
4. **Subgroup** — who benefits most / least?
5. **Cost / access / guideline** — local guideline alignment, insurance coverage?
6. **Next-step / open question** — what's the follow-up trial or unknown?
7. **Adverse events / safety** — what are the risks in practice?
8. **Implementation** — how would we change practice Monday morning?

For admission-type cases, substitute:
- **Diagnosis** — differential, confirmatory workup
- **Management** — best evidence-based next step
- **Prognosis** — expected trajectory, complications
- **Disposition** — level of care, follow-up

## Interactive loop

After generating, main thread presents the 3–5 questions to user via
`AskUserQuestion` (or plain numbered list) and offers:
- Keep all
- Edit specific questions (user types new wording)
- Regenerate from different angles

Save final set to `questions.json` only after user confirms.

**Do not skip this checkpoint** — question choice is a load-bearing decision.
Step 3 research cost is proportional to `n_questions × 2 subagents per Q`.

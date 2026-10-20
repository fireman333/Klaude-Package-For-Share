# Paper / admission / freeform structured extraction — main-thread prompt

Claude main thread reads `intake.json.content_md` and writes `structured.json`
with fields keyed by `intake.type`.

## If `intake.type == "paper"` or `"paper_url"`

Extract into this schema:

```json
{
  "paper_meta": {
    "title": "...",                        // verbatim from paper
    "journal": "...",
    "year": 2024,
    "authors_short": "First A, Second B, et al.",
    "full_author_list": "First A, Second B, Third C, Fourth D, et al.",
    "doi": "...",
    "pmid": "...",
    "design": "e.g. Multinational double-blind RCT",
    "funding": "...",
    "main_finding_sentence": "<one-sentence headline>"
  },
  "pico": {
    "population": "<one paragraph, verbatim eligibility criteria>",
    "intervention": "...",
    "comparator": "...",
    "outcome": "<primary endpoint, verbatim wording>",
    "secondary_outcomes": ["...", "..."]
  },
  "methods": {
    "design": "...",
    "n_total": 0,
    "key_inclusion": ["...", "...", "..."],    // 3–5 bullets
    "key_exclusion": ["...", "...", "..."],    // 3–5 bullets
    "primary_endpoint": "...",
    "stats_method": "Cox PH / logistic / ...",
    "follow_up": "median ... months"
  },
  "results": {
    "key_numbers": [
      {"metric": "Primary composite", "value": "HR 0.74",
       "ci": "0.65–0.85", "p": "< 0.001"},
      ...
    ],
    "figure_caption": "<one-line Fig 1 / Fig 2 summary>"
  },
  "limitations": ["...", "...", "..."],        // 2–4 bullets
  "conclusion": "<authors' summary sentence>"
}
```

Rules:
- **Verbatim wherever possible** for P / I / C / O and endpoint wording.
- If paper is a guideline or review, set `methods.design = "Review"` or `"Guideline"` and skip `key_numbers`.
- If values unknown, use `""` or `"N/A"`; do NOT fabricate.

## If `intake.type == "admission"`

```json
{
  "case_profile": {
    "age": 0, "sex": "M|F",
    "chief_complaint": "<English, one sentence>",
    "underlying": "<comma-separated underlying diseases>",
    "tocc": "<travel / occupation / contact / cluster, N/A if none>",
    "medication": "<current regimen, English, N/A if none>"
  },
  "timeline": [
    {"date": "YYYY-MM-DD", "event_en": "<English event description>"},
    ...
  ],
  "findings": {
    "pe": ["Bibasilar crackles", ...],
    "lab": ["NT-proBNP 4820", ...],
    "image": ["CXR: cardiomegaly ...", ...],
    "path": ["<optional>"]
  },
  "dx_mgmt": {
    "active": ["Acute decompensated HFrEF", ...],
    "underlying": ["HTN", "DM2"],
    "orders": ["IV furosemide 40 mg Q8H", ...],
    "goals": ["Dry weight -4 kg", ...]
  }
}
```

Rules:
- **All content English-only** (Rule 1). Chinese names / items → translate to
  closest English term with source term in parentheses if unusual: e.g.
  "Chinese herbs (unknown composition)".
- **PHI must be gone** — `intake.phi_gate.ran_deid` should be true before
  this runs. If any name / date / MRN survives, STOP and flag.
- `date` in timeline is YYYY-MM-DD or `"Day -N"` relative labels.

## If `intake.type == "freeform"`

Claude reads the markdown and either:
1. Uses existing H1/H2 headings as sections, OR
2. Fabricates 4 fallback sections: `background / case / discussion / plan`

```json
{
  "sections": [
    {"heading": "<English H1 title>",
     "body": "<paragraph or bullet list, English>"},
    ...
  ]
}
```

Rule 1 applies: body must be English. The source markdown may be Chinese —
Claude translates to English while preserving meaning.

## Validation before Step 2

Claude main thread re-reads `structured.json` and checks:
- All required keys for the chosen type are present and non-empty
- Rule 1: no CJK in any body field (grep re `[\u3400-\u9FFF]`)
- At least one numeric result / finding (prevents total hallucination)

If any fails, STOP and report the specific field back to the user.

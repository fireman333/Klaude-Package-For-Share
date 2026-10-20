# data_schema.md — DATA dict schema for render.py

## Why Python dict instead of JSON/YAML

1. `\n` inside multi-line strings survives
2. Triple-string preserves special characters (en-dash, em-dash, curly quotes, …)
3. Easy to inline Python comments
4. `render.py` can `importlib.util.spec_from_file_location` load it directly

Each pptx deck is one `<slug>_data.py` module with a module-level `DATA` dict.

## Top-level structure

```python
DATA = {
    "meta": {
        "topic_title": "Journal Club — Dapagliflozin in HFrEF",  # footer
        "theme": "journal_classic",                              # one of:
        # grand_rounds_warm | journal_classic | clinical_modern
        "input_type": "paper",                                   # paper | admission | freeform
        "citation_style": "vancouver",                           # vancouver | ama | apa7
    },
    "cover": { ... },              # dict, passed to slide_cover() kwargs
    "outline_items": [ ... ],      # list of tuples (num, title, meta, desc)
    "slides": [ ... ],             # ordered slide dicts
}
```

`page` field not needed in each slide; `render.py` auto-numbers from slide 2 (cover = no footer).

## `cover` dict

```python
"cover": {
    "label": "Journal Club",                        # top small label (accent)
    "title": "Dapagliflozin in\nHFrEF",             # multi-line allowed
    "subtitle": "Study design, results, translation",
    "big_word_primary": "DAPA",                     # right-side huge word, primary color
    "big_word_accent": "-HF",                       # right-side huge word, accent color
    "caption_en": "SGLT2 inhibition beyond glycemic control",
    "caption_sub": "A landmark HFrEF RCT",          # italic line under caption
    "presenter": "Your Name",
    "date": "2026-04-23",
    "course_tag": "Cardiology RA — Journal Club",   # optional
}
```

## `outline_items` list

5–7 tuples of `(num, title, meta, desc)`:

```python
"outline_items": [
    ("01", "Background & Question", "5 min", "Disease context + knowledge gap."),
    ("02", "Paper at a Glance",     "5 min", "Design / PICO overview."),
    ...
]
```

## `slides` — per-type schema

Each slide dict MUST have `"type"`. Optional `"notes"` becomes the PowerPoint speaker notes (plain text, `\n` preserved). All other keys pass through to the builder function.

### `type: "cover"`

No extra kwargs needed — reads from `DATA["cover"]`.

```python
{"type": "cover"}
```

### `type: "outline"`

Reads from `DATA["outline_items"]`. Optional override: `"heading"` (default `"Outline"`).

```python
{"type": "outline", "notes": "=== Abbreviations ===\n..."}
```

### `type: "section_divider"`

```python
{
    "type": "section_divider",
    "chapter": "01",
    "title": "Background",
    "lead": "HFrEF burden and pre-DAPA-HF guideline gap.",
}
```

### `type: "background"`

Generic intro / context bullet list.

```python
{
    "type": "background",
    "title": "Clinical Context",
    "subtitle": "Why another HFrEF trial?",  # optional italic subline
    "bullets": [
        "Point one.",
        "Point two.",
    ],
}
```

### `type: "paper_meta"` (paper route)

```python
{
    "type": "paper_meta",
    "title": "Dapagliflozin in HFrEF",       # paper title
    "journal": "N Engl J Med",
    "year": 2019,
    "authors_short": "McMurray JJV, et al.",
    "doi": "10.1056/NEJMoa1911303",
    "pmid": "31535829",
    "design": "Multinational double-blind RCT",
    "funding": "AstraZeneca",
    "main_finding": "HR 0.74 (0.65–0.85) for primary composite vs placebo.",
}
```

### `type: "pico"` (paper route)

```python
{
    "type": "pico",
    "population": "Adults with HFrEF (LVEF ≤40%), NYHA II–IV ...",
    "intervention": "Dapagliflozin 10 mg PO daily ...",
    "comparator": "Matching placebo ...",
    "outcome": "Composite of worsening HF or CV death.",
    "secondary_outcomes": ["All-cause mortality", "KCCQ score", ...],
    "title": "PICO",  # optional override
}
```

### `type: "methods"` (paper route)

```python
{
    "type": "methods",
    "design": "1:1 double-blind event-driven RCT",
    "n_total": 4744,
    "key_inclusion": ["NYHA II–IV", "LVEF ≤40%", "NT-proBNP ≥ 600"],
    "key_exclusion": ["eGFR < 30", "T1DM", "SBP < 95"],
    "primary_endpoint": "Time to first worsening HF or CV death",
    "stats_method": "Cox PH, ITT, stratified",
    "follow_up": "Median 18.2 months",
}
```

### `type: "results"` (paper route)

```python
{
    "type": "results",
    "title": "Primary and Key Secondary Results",
    "key_numbers": [
        {"metric": "Primary composite", "value": "HR 0.74",
         "ci": "0.65–0.85", "p": "< 0.001"},
        ...
    ],
    "figure_caption": "KM curves separated within 4 weeks ...",
}
```

### `type: "case_profile"` (admission route)

```python
{
    "type": "case_profile",
    "age": 68, "sex": "M",
    "chief_complaint": "Progressive exertional dyspnea over 2 weeks.",
    "underlying": "HTN, DM2, CKD stage 3",
    "tocc": "None relevant",
    "medication": "Metformin, amlodipine",
}
```

### `type: "case_timeline"` (admission route)

```python
{
    "type": "case_timeline",
    "events": [
        {"date": "2026-03-01", "event_en": "First ER visit with mild orthopnea."},
        {"date": "2026-03-14", "event_en": "Admitted for decompensated HF."},
        ...
    ],
}
```

### `type: "case_findings"` (admission route)

Any subset of `pe / lab / image / path` (lists of English strings). Columns auto-scale (2–4 cols).

```python
{
    "type": "case_findings",
    "pe": ["Bibasilar crackles", "JVD 10 cm"],
    "lab": ["Cr 1.8", "NT-proBNP 4820", "Na 134"],
    "image": ["CXR: cardiomegaly + bilateral infiltrates"],
    "path": [],  # may omit or leave empty — column hides
}
```

### `type: "case_dx_mgmt"` (admission route)

```python
{
    "type": "case_dx_mgmt",
    "active": ["Acute decompensated HFrEF", "AKI on CKD"],
    "underlying": ["HTN", "DM2"],
    "orders": ["IV furosemide 40 mg Q8H", "Start dapagliflozin 10 mg QD"],
    "goals": ["Dry weight -4 kg", "Titrate four-pillar GDMT"],
}
```

### `type: "discussion_question"`

```python
{
    "type": "discussion_question",
    "q_num": 1,
    "q_text_en": "Does the benefit generalize to Taiwanese HFrEF patients?",
    "suggested_minutes": 7,
    "prompts_for_audience": [
        "What proportion of DAPA-HF came from East Asia?",
        "Any Taiwan-specific registry data?",
    ],
}
```

### `type: "literature_evidence"` (pairs with discussion_question)

```python
{
    "type": "literature_evidence",
    "q_num": 1,
    "evidence_summary_en": "East-Asian subgroup and Taiwanese registry ...",
    "citations": [
        {"author_year": "Docherty 2020", "study_type": "RCT subgroup",
         "country": "Multinational", "n": 1145,
         "take_home": "East Asian subset mirrored main result."},
        ...
    ],
}
```

Top-line auto-generated by `research_synth.py`; hand-editable.

### `type: "takeaway"`

```python
{
    "type": "takeaway",
    "title": "Clinical Takeaways",
    "points": [
        ("Add SGLT2i early", "For any HFrEF patient with LVEF ≤ 40% ..."),
        ("Benefit is independent of diabetes", "..."),
        ("Check eGFR and volume status", "..."),
    ],
}
```

Up to 3 points (row heights optimized for 3).

### `type: "references"`

```python
{
    "type": "references",
    "title": "References",
    "style": "vancouver",  # vancouver | ama | apa7
    "citations": [
        {
            "full_author_list": "McMurray JJV, Solomon SD, ...",
            "title": "...", "journal": "N Engl J Med",
            "year": 2019, "volume": "381", "issue": "21",
            "pages": "1995-2008", "pmid": "31535829",
            "doi": "10.1056/NEJMoa1911303",
        },
        ...
    ],
}
```

Or leave `citations` unset and fill from `research_findings.json.all_citations`.

Font auto-scales: ≤6 → 12pt, 7–9 → 11pt, ≥10 → 10pt.

### `type: "blank_teacher"`

```python
{
    "type": "blank_teacher",
    "closing_main": "Floor is open — your critique welcome",   # optional
    "closing_sub": "— Thank you —",                            # optional
}
```

## Speaker notes format (every slide SHOULD have)

Plain text, `\n` preserved. Placed in `notes_slide.notes_text_frame` by render.py.

```
=== Abbreviations ===
HFrEF | heart failure with reduced ejection fraction | 射出分率降低之心衰竭
SGLT2i | sodium–glucose cotransporter 2 inhibitor | 鈉葡萄糖共同轉運蛋白 2 抑制劑

=== 核心論點 ===
（中文 2–3 句，主席口白 / 重點解說）

=== 可預期提問 ===
（中文 2–3 條聽者可能問的問題 + 準備的回答方向）

=== 補充數據 ===
Smith 2024 — RCT multicenter, US, n=1234; drug X cut MACE by 18%.
PMID 12345678.

=== Audit ===              （僅 literature_evidence / references slide）
OE citations verified: 5/6 pass; 1 caution.
```

First-time English term must follow format `English | expansion | 中文` in `=== Abbreviations ===` block (Rule 1, `feedback_academic_slide_conventions.md`).

Slide **body text must be English-only**. `render.py` auto-checks via `rule1_preflight`; CJK in body aborts render. Use `--skip-rule1-check` only for intentional proper nouns.

## Auto page numbering

- Slide 1 (cover): no footer, no page number
- Slide 2+: `page = 2, 3, 4, ...`
- `topic_title` injected from `DATA["meta"]["topic_title"]` into every footer

## Validation checks done by render.py

- `DATA["slides"]` present, list, non-empty
- Each slide dict has `"type"` key, type exists in `builder.LAYOUTS`
- `rule1_preflight` scans body text (not notes) for CJK — fails = abort
- Slides with `"notes"` string → written into presenter notes slide

## Rendering

```bash
cd <this skill folder>
python3 render.py /path/to/data.py /path/to/output.pptx
python3 render.py /path/to/data.py /path/to/output.pptx --skip-rule1-check   # bypass
```

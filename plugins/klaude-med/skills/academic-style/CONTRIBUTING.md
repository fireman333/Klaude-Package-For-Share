# Contributing — Adding a New Journal

Thank you for extending `academic-style` to a new journal. The plugin architecture means you do **not** need to touch any core Python or R code.

## 1. Fork & branch

```bash
git checkout -b add-journal-<short>
cp -r journals/nature journals/<short>
```

## 2. Required files (per journal)

| File | Purpose |
|---|---|
| `spec.yaml` | Source-of-truth typography, dimensions, line widths, palette ref, semantic mapping, submission format, caption template, axis style, table style |
| `palette.json` | Semantic color names → hex codes |
| `prompt.md` | Caption / abstract / cover-letter writing voice for draft mode |
| `references.md` | (a) Author guideline URL  (b) ≥ 2 sample paper DOIs  (c) 5-rule conformance checklist |
| `examples/` (optional but encouraged) | Before/after PNGs to demonstrate the style |

## 3. spec.yaml authority order

When sources conflict, the priority is:

1. **Author guideline** (publisher official PDF / web)
2. **Sample papers** (recent ≤ 2 years, ≥ 2 DOIs from the journal's flagship)
3. **Yuan1z0825 nature-skills** (third-party reference, MIT)

Any deviation from a higher-priority source **must** be documented in `references.md` with a rationale.

## 4. Validate

```bash
python scripts/validate_spec.py journals/<short>/
```

The validator checks:

- `spec.yaml` parses and conforms to schema
- `palette.json` is valid JSON; every name referenced in `semantic_mapping` exists
- `references.md` has ≥ 1 author guideline URL and ≥ 2 sample DOIs
- `prompt.md` is non-empty

## 5. Test

```bash
pytest tests/test_theme_loader.py -k <short>
```

Then run an example end-to-end:

```bash
python scripts/cheatsheet.py <short>
```

## 6. Submit

PR description must include:

- Author guideline URL(s)
- Sample DOIs you reverse-engineered from
- 5-rule conformance evidence (font, panel label format, dpi, single-column width, line weight)
- One before/after PNG in `examples/`

Maintainers review against the spec sources, not aesthetic preference.

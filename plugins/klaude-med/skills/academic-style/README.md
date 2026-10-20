# academic-style

> Apply **Nature / JAMA / NEJM / Lancet** figure & table style to your biostatistical outputs in one command. Plugin-friendly: add a new journal in 4 files.

A Claude Code skill that turns research figures (Kaplan-Meier curves, forest plots, CONSORT flowcharts, Table 1, etc.) into journal-submission-ready visuals — without rewriting your analysis scripts.

## Acknowledgement

This project is inspired by and gratefully credits [**Yuan1z0825/nature-skills**](https://github.com/Yuan1z0825/nature-skills) (MIT). We extended its philosophy into a multi-journal, plugin-style architecture so Nature, JAMA, NEJM and Lancet can coexist and new journals (BMJ, Cell, Annals of IM, Circulation, …) can be added without touching core code.

## Why this skill

| Problem | Without `academic-style` | With `academic-style` |
|---|---|---|
| Submitting to Nature vs JAMA | Manually re-color/re-font every figure | `--style=nature` / `--style=jama` |
| Switching journals after rejection | Rewrite figure scripts again | Change one flag |
| Adding a new journal | Fork + rewrite plotting code | Drop in `journals/<new>/{spec.yaml,palette.json,prompt.md,references.md}` |
| Sharing your style with collaborators | "Here's a 50-line snippet" | One `git clone` |

## Install

```bash
# Installed as part of the klaude-med plugin; cd into the skill folder:
cd path/to/academic-style
pip install -e .          # installs `academic_style` Python package
```

For ggplot2 users:

```r
source("path/to/academic-style/core/ggplot_applier.R")
```

## Quickstart

```bash
# 1. Print a journal's cheat sheet (palette, fonts, sizes, sample caption)
/academic-style nature

# 2. Re-style an existing figure
/academic-style jama --rewrite figures/km_curve.png

# 3. Draft a journal-style manuscript from cwd's biostats outputs
/academic-style nejm --draft
```

In your biostats scripts:

```python
from academic_style import apply_journal_theme, palette, figure_size
import matplotlib.pyplot as plt

with apply_journal_theme("lancet", column="single"):
    fig, ax = plt.subplots(figsize=figure_size("lancet", "single"))
    ax.plot(t, surv, color=palette("lancet", "primary_method"))
    fig.savefig("km_lancet.svg")
```

## Supported journals

| Short | Name | Spec version | Last reviewed |
|---|---|---|---|
| `nature` | Nature | 2025.01 | 2026-05-10 |
| `jama` | JAMA | 2025.01 | 2026-05-10 |
| `nejm` | NEJM (New England Journal of Medicine) | 2025.01 | 2026-05-10 |
| `lancet` | The Lancet | 2025.01 | 2026-05-10 |

## Add your own journal

```bash
cp -r journals/nature journals/bmj
$EDITOR journals/bmj/{spec.yaml,palette.json,prompt.md,references.md}
python scripts/validate_spec.py journals/bmj/
```

Required files per journal:

- `spec.yaml` — typography, dimensions, lines, palette ref, semantic mapping, submission, caption, ax_style, table_style
- `palette.json` — semantic color names → hex codes
- `prompt.md` — caption / abstract / cover-letter prompts for draft mode
- `references.md` — author guideline URL + ≥ 2 sample DOIs + 5-rule conformance checklist

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the PR template.

## Architecture

```
SKILL.md (Claude entry)
    │
    ├── /academic-style <journal> ──→ scripts/cheatsheet.py
    ├── /academic-style <journal> --rewrite ──→ scripts/rewrite.py
    └── /academic-style <journal> --draft ──→ scripts/draft.py (chains manuscript-results)

core/ (importable Python + R)
    │
    ├── theme_loader      ──→ reads journals/<j>/spec.yaml
    ├── matplotlib_applier ──→ rcParams ContextManager (Python)
    ├── ggplot_applier.R   ──→ theme_journal() + palette_journal() (R)
    ├── font_resolver      ──→ Helvetica → Arial → DejaVu fallback
    ├── caption_formatter  ──→ per-journal caption template
    └── helpers            ──→ panel labels, multi-panel layout

journals/<name>/   ──→ plugin sub-folder (4 files + examples/)
```

Biostats skills (kaplan-meier, competing-risk, univariate-forest, psm-matching, flowchart, table1, multivariate-interaction, auc-cstat) accept `--style=<journal>` and import from `academic_style.core`.

## License

MIT — see [LICENSE](./LICENSE).

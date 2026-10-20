---
name: academic-style
description: "academic-style: applies Nature/JAMA/NEJM/Lancet figure & table style to biostats outputs, or drafts a journal-style manuscript skeleton. Trigger: /academic-style, /style, 期刊風格, 套 nature 風格, 套 jama 風格, 套 nejm 風格, 套 lancet 風格, post-process figure for journal submission. Subcommand = journal short name (nature|jama|nejm|lancet). Flags: --rewrite <path>, --draft, --apply."
---

# academic-style

Journal-specific figure & table style for biostats outputs. Plugin-friendly: every journal lives in its own folder, every journal can be added by copying one folder.

## Decision tree (Claude reads this and routes accordingly)

When `/academic-style ...` is invoked, branch on the arguments:

1. **No journal name** (`/academic-style`)
   → List supported journals (`nature`, `jama`, `nejm`, `lancet`) and tell the user the next steps. Run:
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/cheatsheet.py --list
   ```

2. **Just a journal name** (`/academic-style nature`)
   → Print the journal cheat sheet (palette swatch, font, dimensions, sample caption). Run:
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/cheatsheet.py <journal>
   ```

3. **`<journal> --rewrite <path>`**
   → Post-processor mode. Re-style an existing PNG/SVG. Prefer re-running the source script if a sibling `.py` is found. Run:
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/rewrite.py <path> --style <journal>
   ```

4. **`<journal> --draft`** *or* cwd contains biostats artifacts (`*table1*.xlsx`, `*km*.png`, `*forest*.xlsx`, `analysis_log.json`)
   → Draft mode (chain caller). Calls `manuscript-results` for prose, re-runs Wave-1/2 biostats scripts with `--style=<journal>`, wraps in journal voice from `journals/<j>/prompt.md`, outputs `manuscript_<journal>.md` + `figures/`. Run:
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/draft.py --journal <journal>
   ```

5. **`<journal> --apply`** (called from inside a biostats skill chain)
   → Just emit a theme dict to stdout for the calling script. Used internally; users rarely need this.

## Public Python API

```python
from academic_style import apply_journal_theme, palette, figure_size
import matplotlib.pyplot as plt

with apply_journal_theme("nature", column="single") as spec:
    fig, ax = plt.subplots(figsize=figure_size("nature", "single"))
    ax.plot(t, surv,
            color=palette("nature", "primary_method"),
            label="Treatment")
    fig.savefig("km_nature.svg")
```

## Public R API

```r
source("${CLAUDE_SKILL_DIR}/core/ggplot_applier.R")
library(ggplot2)
ggplot(df, aes(time, surv, color = arm)) +
  geom_step(linewidth = 1) +
  scale_color_manual(values = palette_journal("lancet")) +
  theme_journal("lancet")
ggsave("km_lancet.pdf",
       width = figure_size_journal("lancet")[["width"]],
       height = figure_size_journal("lancet")[["height"]])
```

## Integration with existing biostats skills

All 8 biostats skills (table1, kaplan-meier, competing-risk, univariate-forest, multivariate-interaction, psm-matching, auc-cstat, flowchart) accept `--style=<journal>` to opt into journal styling. **Without `--style`, behavior is byte-identical to before**.

| Skill | Style integration | What changes |
|---|---|---|
| kaplan-meier | Wave 1 | Curve colors, font, line widths from theme |
| competing-risk | Wave 1 | Same as KM |
| univariate-forest | Wave 1 | Forest plot colors, axis style |
| psm-matching | Wave 2 | Love plot colors, reference line |
| flowchart | Wave 2 | Box/arrow colors |
| table1 | Wave 3 | Excel decimal places, p-value format |
| multivariate-interaction | Wave 3 | Same as table1 |
| auc-cstat | Wave 3 | Excel formatting + ROC curve if generated |

## Adding a new journal

```bash
cp -r ${CLAUDE_SKILL_DIR}/journals/nature ${CLAUDE_SKILL_DIR}/journals/<new>
$EDITOR ${CLAUDE_SKILL_DIR}/journals/<new>/{spec.yaml,palette.json,prompt.md,references.md}
python ${CLAUDE_SKILL_DIR}/scripts/validate_spec.py ${CLAUDE_SKILL_DIR}/journals/<new>/
```

Required files: 4 (spec.yaml, palette.json, prompt.md, references.md). See [CONTRIBUTING.md](CONTRIBUTING.md) for the full PR template.

## Boundary with manuscript-results / academic-paper

- `manuscript-results` owns *content* (statistical narrative, p-value reporting).
- `academic-style` owns *form* (journal voice wrapper, figure styling, caption formatting).
- Draft mode is a **chain caller**: it asks `manuscript-results` for the Results section, asks biostats skills to re-render with `--style`, and wraps everything in the journal's `prompt.md` voice.
- If `manuscript-results` / `academic-paper` ever internalize journal awareness, the draft mode here will be deprecated and academic-style will fall back to figure-only.

## Acknowledgement

Inspired by [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) (MIT). See `journals/nature/references.md` for spec provenance.

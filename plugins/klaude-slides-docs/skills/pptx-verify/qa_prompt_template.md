# Visual QA Sub-agent Prompt Template

主 agent 在派 sub-agent 時用此模板組 prompt。`{{...}}` 用實際值替換後傳入。

**Spawn 時 Agent tool 參數**:
- `subagent_type: "general-purpose"`
- `model: "sonnet"`（選用）— 版面 QA 屬機械式視覺檢查，中階模型足夠

---

```
Visually inspect these {{N}} slides from "{{deck_title}}". Assume there are issues — find them.

You are reviewing a presentation that was just generated programmatically. The build script's
intent is described per-slide below, but the rendered image is what matters. Your job is to
find every layout, contrast, and content defect, even minor ones — the main agent has the
cognitive blind-spot of "I wrote the code, it should look right" and needs your fresh eyes.

## Priority rubric (use these labels exactly)

- **P1** (critical) — text cut off / element overflows slide / unreadable contrast / wrong content
- **P2** — clear visual defect that hurts comprehension (overlap, illegible at normal zoom)
- **P3** — noticeable but tolerable (uneven spacing, slightly cramped, minor wrap)
- **P4** — cosmetic only (subjective taste, would be nice to fix)

## Issue categories (tag each issue with one)

- `overflow`        — text or shape extending past container or slide edge
- `overlap`         — elements colliding (text through shapes, lines through words)
- `contrast`        — low contrast (dark on dark, light on light, gray on cream)
- `alignment`       — misaligned columns, inconsistent indents, off-grid
- `margin`          — element too close to slide edge or to neighbor (< 0.3")
- `cn-render`       — Chinese glyph rendering issue (missing chars, fallback fonts, weird tracking)
- `placeholder`     — leftover dummy text (lorem, TODO, xxx, "[insert ...]")
- `wrap`            — wrap behaving wrong (orphan word, awkward break)
- `other`           — describe in the issue text

## Specifically look for

- Decorative lines positioned for single-line text but title wrapped to two lines
- Footer / page number colliding with content above
- Bullets where last char is clipped by card bottom border
- Icons that are dark-on-dark or light-on-light (low contrast)
- Text boxes too narrow causing excessive Chinese-character wrapping
- Cards/sections nearly touching (< 0.3" gap) or floating in space (> 1.0" empty band)
- Insufficient margin from slide edges (< 0.5")

## Slides to inspect

(Read these images — use the EXACT absolute paths)

{{#each slides}}
{{N}}. {{absolute_path}} — Expected: {{expected_one_liner}}
{{/each}}

## Output format

For each slide that has issues, output:

```
### Slide {{N}} — {{short label}}
- [P{{1-4}}] [{{category}}] {{issue description}} → suggest: {{specific fix, e.g. "shrink card height from 2.45 to 2.20" or "render icon in white instead of navy"}}
```

Slides with NO issues: list as "Slide N — clean".

End with a **Priority summary** section listing all P1 issues at the top.

If you found ZERO issues across the entire deck, you weren't looking hard enough — go back and
look again with the assumption that contrast, margin, or wrap defects exist.
```

---

## How the main agent should consume this

1. Replace `{{N}}`, `{{deck_title}}`, slide list, and `{{expected_one_liner}}` with real values
2. Spawn `Agent` with `subagent_type: general-purpose` (visual inspection works there) and this prompt
3. Parse the response — pull out P1/P2 issues into chat, save full report to `verify_report.md`
4. If `--re-verify`, prepend the prior issue list and ask sub-agent to verify each is fixed before fresh scan

---
name: material-layout
description: "material-layout: M3 layout foundations for web. Trigger: Material Design layout, M3 layout, responsive layout, adaptive layout, breakpoints, window size class, layout grid, 12-column grid, 4/8dp, canonical layout, list-detail, supporting-pane, supporting pane, feed, navigation rail, Material 排版, Material 版面, 響應式版面, 自適應版面, 斷點, 視窗尺寸, 佈局網格, 12 欄格線, 導覽列, 導覽軌, 抽屜導覽, 前端排版 skill, frontend layout skill."
---

# Material Layout (M3) — Frontend Skill

Apply Material Design 3 layout foundations to a web frontend: size classes, responsive grid, spacing, canonical layouts and adaptive navigation. Use this skill when designing page structure, choosing breakpoints, picking navigation patterns, or translating an M3 Figma/Android spec into HTML/CSS/Tailwind/React.

Material Design is expressed in **dp** (density-independent pixels). On the web, treat **1 dp ≈ 1 CSS px** at baseline density — all numbers below are used directly as `px` / `rem` values.

## Core Concepts (memorize these)

### 1. Window Size Classes (width)

| Class        | Width range (px) | Typical target                             |
|--------------|------------------|--------------------------------------------|
| Compact      | `< 600`          | Phones (portrait)                          |
| Medium       | `600 – 839`      | Small tablets, phones (landscape), foldable inner portrait |
| Expanded     | `840 – 1199`     | Tablets (landscape), small laptops         |
| Large        | `1200 – 1599`    | Desktops                                   |
| Extra-large  | `≥ 1600`         | Large desktops, TV, connected displays     |

Height classes (secondary, used to decide whether to keep a top app bar):
Compact `< 480`, Medium `480–899`, Expanded `≥ 900`.

**Rule of thumb:** drive layout decisions from width first. Only branch on height for top-app-bar density and sticky footers.

### 2. Responsive Grid (columns / gutters / margins)

| Size class     | Columns | Gutter | Margin           |
|----------------|---------|--------|------------------|
| Compact        | 4       | 16 px  | 16 px            |
| Medium         | 8       | 24 px  | 24 px            |
| Expanded       | 12      | 24 px  | 24 px            |
| Large          | 12      | 24 px  | 32 px            |
| Extra-large    | 12      | 24 px  | fluid, ≥ 32 px (center + max-width) |

Content **columns are fluid** (percentage), **gutters and margins are fixed** per breakpoint.

### 3. Spacing System

- Base grid: **8 px** for layout, component padding, stack spacing.
- Sub-grid: **4 px** for small elements (icons, dense chips, inline typography).
- Build a scale: `4, 8, 12, 16, 24, 32, 40, 48, 56, 64` px.
- All component paddings and gaps must snap to this scale.

### 4. Parts of a Layout

Every page has **frame** + **body**:
- **Frame:** status/system bars (web: browser chrome — ignore), top app bar, navigation (bar / rail / drawer), FAB.
- **Body:** one or more **panes**. A pane is a scrollable content region.

### 5. Canonical Layouts

Pick ONE before drafting markup:

1. **List-Detail** — browse a list and inspect a selected item.
   - Compact: single pane; selecting an item pushes a detail route.
   - Expanded+: two side-by-side panes (list ~1/3, detail ~2/3).
2. **Supporting Pane** — primary work area + secondary tools/context.
   - Compact: secondary collapses into a bottom sheet or tab.
   - Expanded+: secondary pane docked to the side (~1/3 width).
3. **Feed** — large scrollable grid/list of equivalent items.
   - Column count follows the grid: 1 → 2 → 3–4 → 4+ as width grows.

### 6. Adaptive Strategies (what to do at each breakpoint)

- **Reflow:** rearrange panes — stack vertically on compact, side-by-side on expanded.
- **Reveal:** show additional content/controls that were hidden at smaller sizes.
- **Expand:** grow a single pane to use extra space (add a max-width to avoid overly long lines).
- **Levitate:** dock/float a secondary pane as a sheet, drawer, or dialog.

### 7. Navigation pattern per breakpoint

| Width         | Primary navigation                |
|---------------|-----------------------------------|
| Compact       | Bottom **navigation bar** (3–5 destinations) |
| Medium        | **Navigation rail** (collapsed, 3–7 destinations) |
| Expanded      | **Navigation rail** (collapsed or expanded) |
| Large / XL    | **Navigation drawer** (persistent) or expanded rail |

Body content should never exceed **~1040 px** of reading width for prose; dashboards can go wider but still cap around 1440–1600 px with fluid margins.

## Workflow

Follow these steps every time this skill is triggered.

### Step 1: Gather Requirements

Ask (skip items already given):
1. **Target platforms / breakpoints** — compact only, or up to large/XL?
2. **Canonical layout** — list-detail, supporting-pane, feed, or custom?
3. **Tech stack** — plain CSS, Tailwind, CSS Modules, styled-components, or a specific framework?
4. **Navigation destinations** — how many top-level sections?
5. **Existing design tokens** — does the project already define colors / spacing / typography? If yes, extend them rather than overriding.

### Step 2: Produce a Layout Plan

Before writing code, output a short plan:
- Which size classes will be supported.
- Which canonical layout was chosen and why.
- Which navigation component each breakpoint uses.
- A table of breakpoint → columns / gutter / margin / nav.

Confirm with the user if anything is ambiguous.

### Step 3: Generate Tokens + Grid Scaffold

Generate (and prefer editing an existing file over creating new ones):

- **Design tokens:** CSS custom properties for spacing, breakpoints, gutters, margins. See `${CLAUDE_SKILL_DIR}/templates/tokens.css`.
- **Grid primitive:** a `.m3-grid` container using CSS grid with variable column count. See `${CLAUDE_SKILL_DIR}/templates/grid.css`.
- **Tailwind users:** extend `theme.screens` and `theme.spacing`. See `${CLAUDE_SKILL_DIR}/templates/tailwind.config.js`.

### Step 4: Assemble the Canonical Layout

Use the template under `templates/` that matches the chosen canonical layout:
- `${CLAUDE_SKILL_DIR}/templates/list-detail.html` — list/detail with reflow at expanded.
- `${CLAUDE_SKILL_DIR}/templates/supporting-pane.html` — primary + supporting at expanded.
- `${CLAUDE_SKILL_DIR}/templates/feed.html` — feed with a column count that follows the grid.

Wire the navigation component to the correct breakpoint per the table above.

### Step 5: Validate

Before reporting done, verify:
- [ ] All paddings/gaps snap to the 4/8 scale — no ad-hoc `7px`, `13px`, etc.
- [ ] The layout actually switches at 600 / 840 / 1200 / 1600 px (test with DevTools responsive mode).
- [ ] Columns are fluid (%) but gutters/margins are fixed per breakpoint.
- [ ] Navigation pattern changes correctly across breakpoints.
- [ ] Text column width stays ≤ ~75ch for prose.
- [ ] No horizontal scroll at any breakpoint.
- [ ] Body max-width is capped for XL so content does not become unreadably wide.

### Step 6: Present Results

- Summarize the breakpoint table, canonical layout, and nav pattern used.
- List the files changed and what each one contributes.
- Call out any trade-offs (e.g., "drawer is persistent at ≥ 1200 px, collapses to rail below").

## Error Handling

- **Tech stack unclear** → ask before generating files; do not assume React/Tailwind.
- **Existing tokens conflict** → read the existing config first and extend, don't replace.
- **Non-standard breakpoints requested** → document the deviation from M3 in a comment and proceed.
- **Missing canonical match** → if none fits, compose from primitives (grid + panes) rather than inventing a new pattern.

## References

- `${CLAUDE_SKILL_DIR}/references/breakpoints.md` — size classes + media-query snippets.
- `${CLAUDE_SKILL_DIR}/references/grid-and-spacing.md` — grid math and the 4/8 spacing scale.
- `${CLAUDE_SKILL_DIR}/references/canonical-layouts.md` — list-detail, supporting-pane, feed details.
- `${CLAUDE_SKILL_DIR}/references/navigation.md` — nav bar / rail / drawer behaviour per breakpoint.

## Templates

- `${CLAUDE_SKILL_DIR}/templates/tokens.css` — CSS custom properties for breakpoints, spacing, gutters, margins.
- `${CLAUDE_SKILL_DIR}/templates/grid.css` — responsive 4/8/12-column grid primitive.
- `${CLAUDE_SKILL_DIR}/templates/tailwind.config.js` — Tailwind theme extension matching M3 tokens.
- `${CLAUDE_SKILL_DIR}/templates/list-detail.html` — canonical list-detail scaffold.
- `${CLAUDE_SKILL_DIR}/templates/supporting-pane.html` — canonical supporting-pane scaffold.
- `${CLAUDE_SKILL_DIR}/templates/feed.html` — canonical feed scaffold.

## Source

Based on the Material Design 3 layout foundations:
<https://m3.material.io/foundations/layout/understanding-layout/overview>

---

## Credits

Layout guidance is based on the Google Material Design 3 documentation (m3.material.io — layout, canonical layouts, navigation, and window size classes). Material Design is a trademark of Google LLC; this skill is an independent summary and is not affiliated with or endorsed by Google.

# Canonical Layouts

M3 defines three reusable page archetypes. Pick the one that matches the task before choosing components.

## 1. List-Detail

Users browse a list and inspect a selected item's detail.

### Rules

- **Compact:** single pane. The list is the landing screen. Selecting an item navigates (pushes a route) to the detail. Back button returns to the list.
- **Medium:** still typically single-pane; detail may appear as a full-screen route or large bottom sheet.
- **Expanded and larger:** show **both panes side-by-side**. List takes ~1/3, detail takes ~2/3 of the body.
- The detail pane must be meaningful on its own (e.g., deep-linkable, shareable).

### Grid placement at expanded (12 columns)

```
| nav | list (4 cols) | detail (8 cols)                |
```

### Skeleton

```html
<main class="m3-grid canonical-list-detail">
  <section class="pane pane--list">    ... </section>
  <section class="pane pane--detail">  ... </section>
</main>
```

```css
.canonical-list-detail .pane--list,
.canonical-list-detail .pane--detail {
  grid-column: 1 / -1;          /* compact: single pane */
}
@media (min-width: 840px) {
  .canonical-list-detail .pane--list   { grid-column: span 4; }
  .canonical-list-detail .pane--detail { grid-column: span 8; }
}
```

## 2. Supporting Pane

A primary working area plus a secondary pane of tools, filters, or contextual info.

### Rules

- Primary occupies **~2/3**, supporting **~1/3** of the body at expanded+.
- On compact, the supporting pane collapses into a **bottom sheet** or **tab**, and is reachable via an explicit control.
- Supporting content is only meaningful **in context** of the primary — do not deep-link to it alone.

### Grid placement at expanded (12 columns)

```
| nav | primary (8 cols) | supporting (4 cols) |
```

### When to prefer list-detail instead

- If the secondary pane is meaningful on its own, use **list-detail** (detail pane is standalone).
- Supporting pane is for tools, inspectors, filter panels, contextual help, revision history, etc.

## 3. Feed

Large scrollable grid of equivalent items (cards, tiles, posts, products).

### Column count by size class

| Class        | Grid columns for items                   |
|--------------|------------------------------------------|
| Compact      | 1 (list) or 2 for small tiles            |
| Medium       | 2–3                                      |
| Expanded     | 3–4                                      |
| Large        | 4–5                                      |
| Extra-large  | 5–6 (cap — too many feels like a table)  |

### Skeleton

```css
.canonical-feed {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
}
@media (min-width: 600px) { .canonical-feed { gap: 24px; } }
```

- Use **cards** with consistent aspect ratios for scannability.
- Lazy-load items as they enter the viewport.
- Keep the tile minimum width around **240–320 px** so `auto-fill` naturally reflows.

## Adaptive strategies

When the window changes size, a pane may:

1. **Reflow** — rearrange (e.g., side-by-side → stacked). Default for list-detail and supporting-pane at compact.
2. **Reveal** — show more controls at wider sizes (e.g., filter chips expanded inline instead of inside a drawer).
3. **Expand** — grow to use extra space up to a sensible max-width. Cap prose at ~75ch.
4. **Levitate** — float a pane as a sheet, drawer, or dialog over the body (used for supporting-pane on compact).

## Choosing a layout quickly

| Question                                                       | Layout            |
|----------------------------------------------------------------|-------------------|
| Many items of one kind to inspect?                             | List-Detail       |
| A main work surface that needs side tools/inspector?           | Supporting Pane   |
| Homogeneous content scrolled for discovery?                    | Feed              |
| Mostly a single form or document?                              | None — use body + grid directly |

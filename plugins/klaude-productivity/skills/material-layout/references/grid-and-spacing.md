# Grid & Spacing

## The responsive grid has three parts

1. **Columns** — fluid tracks that carry content. Width expressed as `%`.
2. **Gutters** — fixed-px space **between** columns.
3. **Margins** — fixed-px space between the grid and the screen edges.

Per size class:

| Class        | Columns | Gutter | Margin | Body max-width               |
|--------------|---------|--------|--------|------------------------------|
| Compact      | 4       | 16 px  | 16 px  | 100%                         |
| Medium       | 8       | 24 px  | 24 px  | 100%                         |
| Expanded     | 12      | 24 px  | 24 px  | 100%                         |
| Large        | 12      | 24 px  | 32 px  | ~1440 px (cap prose ≤ 75ch)  |
| Extra-large  | 12      | 24 px  | ≥ 32 px, fluid | ~1600 px, center       |

> Columns stay fluid. Gutters and margins are **fixed** per class — they don't scale with the screen.

## Canonical CSS grid primitive

```css
.m3-grid {
  --cols: 4;
  --gutter: 16px;
  --margin: 16px;

  display: grid;
  grid-template-columns: repeat(var(--cols), 1fr);
  column-gap: var(--gutter);
  row-gap: var(--gutter);
  padding-inline: var(--margin);
  box-sizing: border-box;
}

@media (min-width: 600px)  { .m3-grid { --cols: 8;  --gutter: 24px; --margin: 24px; } }
@media (min-width: 840px)  { .m3-grid { --cols: 12; --gutter: 24px; --margin: 24px; } }
@media (min-width: 1200px) { .m3-grid { --cols: 12; --gutter: 24px; --margin: 32px; } }
@media (min-width: 1600px) {
  .m3-grid {
    --cols: 12; --gutter: 24px; --margin: 32px;
    max-width: 1600px;
    margin-inline: auto;
  }
}
```

Place children with `grid-column: span <n>`. Example: a hero spans all columns (`span 4 / 8 / 12`), a sidebar spans 3 at expanded.

## Spacing scale (4/8 grid)

Material uses an **8 px baseline** for layout with a **4 px sub-grid** for small elements:

| Token   | Value | Typical use                                   |
|---------|-------|-----------------------------------------------|
| `sp-0`  | 0     |                                               |
| `sp-1`  | 4 px  | icon-to-label gap, dense chips                |
| `sp-2`  | 8 px  | small padding inside buttons/chips            |
| `sp-3`  | 12 px | tight row gap                                 |
| `sp-4`  | 16 px | default component padding, card padding       |
| `sp-6`  | 24 px | section gap, gutter                           |
| `sp-8`  | 32 px | page padding, margin on Large                 |
| `sp-10` | 40 px | large section separation                      |
| `sp-12` | 48 px | hero padding, big vertical rhythm             |
| `sp-14` | 56 px | app-bar height (small)                        |
| `sp-16` | 64 px | app-bar height (medium), large section        |

**Rule:** every padding, margin, and gap in a component must come from this scale. No 7 px, no 13 px, no 21 px.

## CSS custom properties

```css
:root {
  --sp-0:  0;
  --sp-1:  4px;
  --sp-2:  8px;
  --sp-3:  12px;
  --sp-4:  16px;
  --sp-6:  24px;
  --sp-8:  32px;
  --sp-10: 40px;
  --sp-12: 48px;
  --sp-14: 56px;
  --sp-16: 64px;
}
```

## Tailwind `spacing` extension

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      spacing: {
        '0.5': '4px',  '1': '8px',   '1.5': '12px', '2': '16px',
        '3':   '24px', '4': '32px',  '5':   '40px', '6': '48px',
        '7':   '56px', '8': '64px',
      },
    },
  },
};
```

## Vertical rhythm

- Stack related content with `gap: var(--sp-4)` (16 px).
- Separate unrelated sections with `gap: var(--sp-8)` (32 px) or more.
- Never combine two odd values to create rhythm (e.g., `margin-top: 14px` + `padding-bottom: 10px`). Use one scale value in one direction.

## Line length and reading width

For prose content inside any pane, keep `max-width` between `60ch` and `75ch`. Dashboards and data tables can extend to the pane's full width.

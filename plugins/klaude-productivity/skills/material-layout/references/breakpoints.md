# Breakpoints & Window Size Classes

Material Design 3 uses **window size classes** rather than device-specific media queries. The class describes the *available window*, not the device — so resizing a desktop window can cross class boundaries just like rotating a tablet.

## Width classes

| Class        | Range (px)      | Device coverage (from M3 docs)                 |
|--------------|-----------------|-------------------------------------------------|
| Compact      | `< 600`         | ≈99.96% of phones in portrait                   |
| Medium       | `600 – 839`     | ≈93.73% of tablets in portrait, most foldables in portrait |
| Expanded     | `840 – 1199`    | ≈97.22% of tablets in landscape                 |
| Large        | `1200 – 1599`   | Large tablets, small desktop windows            |
| Extra-large  | `≥ 1600`        | Desktop, connected displays                     |

## Height classes

| Class      | Range (px)     | Coverage                                         |
|------------|----------------|--------------------------------------------------|
| Compact    | `< 480`        | ≈99.78% of phones in landscape                   |
| Medium     | `480 – 899`    | Most tablets in landscape, phones in portrait    |
| Expanded   | `≥ 900`        | Tablets in portrait                              |

Use height classes mostly to decide whether to keep or collapse top app bars and to reserve vertical space for persistent controls.

## CSS media queries

```css
/* Width classes */
@media (max-width: 599.98px)                         { /* Compact     */ }
@media (min-width: 600px) and (max-width: 839.98px)  { /* Medium      */ }
@media (min-width: 840px) and (max-width: 1199.98px) { /* Expanded    */ }
@media (min-width: 1200px) and (max-width: 1599.98px){ /* Large       */ }
@media (min-width: 1600px)                           { /* Extra-large */ }

/* Height classes (use sparingly) */
@media (max-height: 479.98px)                         { /* H-compact  */ }
@media (min-height: 480px) and (max-height: 899.98px) { /* H-medium   */ }
@media (min-height: 900px)                            { /* H-expanded */ }
```

## Container queries (preferred for panes)

For a pane whose layout must depend on its own width (not the viewport), use container queries:

```css
.pane { container-type: inline-size; }

@container (min-width: 600px) { /* pane-medium   */ }
@container (min-width: 840px) { /* pane-expanded */ }
```

## Tailwind screens

```js
// tailwind.config.js
module.exports = {
  theme: {
    screens: {
      compact:  { max: '599.98px' },
      medium:   { min: '600px',  max: '839.98px'  },
      expanded: { min: '840px',  max: '1199.98px' },
      large:    { min: '1200px', max: '1599.98px' },
      xlarge:   { min: '1600px' },
      // convenience: mobile-first min-widths
      'md-up': '600px',
      'ex-up': '840px',
      'lg-up': '1200px',
      'xl-up': '1600px',
    },
  },
};
```

## JS hook (React)

```ts
import { useEffect, useState } from 'react';

type SizeClass = 'compact' | 'medium' | 'expanded' | 'large' | 'xlarge';

function classify(w: number): SizeClass {
  if (w < 600)  return 'compact';
  if (w < 840)  return 'medium';
  if (w < 1200) return 'expanded';
  if (w < 1600) return 'large';
  return 'xlarge';
}

export function useWindowSizeClass(): SizeClass {
  const [cls, setCls] = useState<SizeClass>(() =>
    typeof window === 'undefined' ? 'expanded' : classify(window.innerWidth),
  );
  useEffect(() => {
    const onResize = () => setCls(classify(window.innerWidth));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  return cls;
}
```

## Decision table

| Question                                    | Answer per class                                                |
|---------------------------------------------|-----------------------------------------------------------------|
| How many layout columns?                    | 4 → 8 → 12 → 12 → 12                                           |
| Side margin?                                | 16 → 24 → 24 → 32 → fluid (≥32, centered with max-width)        |
| Gutter between columns?                     | 16 → 24 → 24 → 24 → 24                                          |
| Primary navigation?                         | Bar → Rail → Rail → Drawer → Drawer                             |
| Show two panes simultaneously?              | No  → No  → Yes  → Yes   → Yes                                  |
| Top app bar allowed to be tall (large)?     | Only if height ≥ medium; else use small/dense top app bar       |

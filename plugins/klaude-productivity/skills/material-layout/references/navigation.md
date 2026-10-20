# Navigation patterns by size class

M3 swaps the primary navigation component as the window grows. The destinations stay the same; only the surface changes.

| Width (px)    | Primary nav               | Secondary surface            |
|---------------|---------------------------|------------------------------|
| `< 600`       | **Navigation bar** (bottom)| Top app bar (small/center)  |
| `600–1199`    | **Navigation rail** (side) | Top app bar (small)          |
| `≥ 1200`      | **Navigation drawer** (persistent, side) or expanded rail | Top app bar (small) |

## Navigation bar (bottom)

- Shown on **compact** only.
- 3–5 destinations (never more). 5 is the hard cap.
- Height: 80 px (labelled) or 56 px (icon-only).
- Only for top-level destinations; don't put settings or profile here — use the top app bar or a drawer instead.

## Navigation rail (side)

- Shown on **medium** and **expanded** (can be kept on large as the collapsed state).
- 3–7 destinations + optional FAB at the top.
- Widths: **80 px** (collapsed) or **256–360 px** (expanded rail replaces drawer).
- Items are vertically stacked; icon + short label.

## Navigation drawer (persistent / modal)

- Shown on **large / extra-large** as the primary nav.
- **Standard drawer width:** 256–360 px, sits next to body (non-modal).
- **Modal drawer:** overlays body with a scrim; used on medium as the "hamburger" surface.
- Can group destinations, include dividers, and show secondary destinations.

## Top app bar

Pair the primary nav with one top app bar style:

| Style           | Height (px) | Use                                                 |
|-----------------|-------------|-----------------------------------------------------|
| Small           | 64          | Default across all sizes                            |
| Center-aligned  | 64          | Apps with a central brand moment, compact           |
| Medium          | 112         | One line of content, extra vertical presence        |
| Large           | 152         | Hero-style; only on medium/expanded height classes  |

Collapse to small on scroll for content-heavy pages.

## Decision recipe

```txt
if width < 600:
    nav = bottom navigation bar (≤5 destinations)
elif width < 1200:
    nav = navigation rail (collapsed, 80px)
else:
    nav = persistent drawer (or expanded rail 256–360px)
```

## CSS sketch

```css
.app-shell { display: grid; min-height: 100dvh; }

/* compact: top app bar + content + bottom nav */
.app-shell {
  grid-template-rows: 64px 1fr 80px;
  grid-template-areas: "topbar" "body" "bottomnav";
}

/* medium and expanded: rail on the left */
@media (min-width: 600px) {
  .app-shell {
    grid-template-columns: 80px 1fr;
    grid-template-rows: 64px 1fr;
    grid-template-areas:
      "rail topbar"
      "rail body";
  }
  .bottomnav { display: none; }
  .rail { display: flex; grid-area: rail; }
}

/* large: persistent drawer */
@media (min-width: 1200px) {
  .app-shell {
    grid-template-columns: 256px 1fr;
    grid-template-areas:
      "drawer topbar"
      "drawer body";
  }
  .rail { display: none; }
  .drawer { display: flex; grid-area: drawer; }
}
```

## Common mistakes

- Using a bottom nav on desktop — it wastes vertical space and breaks mouse affordance.
- Keeping the drawer *modal* on large — use a persistent drawer at ≥1200 px.
- Cramming > 5 items into the bottom nav.
- Forgetting that rail width is fixed (80 px) — don't let it flex, pin it.
- Two navigation surfaces competing at once (rail + drawer visible together). Pick one per breakpoint.

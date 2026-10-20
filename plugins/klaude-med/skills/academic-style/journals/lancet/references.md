# The Lancet — Spec Provenance

## Author guideline
- https://www.thelancet.com/lancet/information-for-authors (Information for Authors)
- https://www.thelancet.com/pb-assets/Lancet/authors/tlrn-information-for-authors.pdf (downloadable PDF)

## Sample papers (reverse-engineered)
- *The Lancet* 2023 — DOI `10.1016/S0140-6736(23)01230-X`
- *The Lancet* 2024 — DOI `10.1016/S0140-6736(24)00512-6`

## Third-party reference
- [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) (MIT) — line-weight philosophy borrowed; palette wholly Lancet-specific (red anchored)

## 5-rule conformance checklist

| Rule | Spec value | Source |
|---|---|---|
| Sans-serif font | Helvetica primary | Lancet author info §Figures |
| Panel labels | uppercase `A, B, C` bold | Sample DOIs |
| Raster DPI | 300 dpi | Lancet author info |
| Single-column width | 89 mm | Lancet author info |
| Decimal separator | middle dot `·` | Lancet style — confirmed across all sample DOIs |

## Notes / deviations from sources
- Middle-dot decimal formatting is implemented at table render time, not figure render time (matplotlib's tick formatter is overridden when `--style=lancet`).
- Lancet's signature red (`lancet_red = #A41E22`) is calibrated to the printed journal masthead, not the digital splash page.

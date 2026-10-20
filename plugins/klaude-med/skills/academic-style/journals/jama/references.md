# JAMA — Spec Provenance

## Author guideline
- https://jamanetwork.com/journals/jama/pages/instructions-for-authors (Instructions for Authors)
- https://jamanetwork.com/data/Journals/JAMA/0/jama_authorinstructions.pdf (downloadable PDF)

## Sample papers (reverse-engineered)
- *JAMA* 2023 — DOI `10.1001/jama.2023.21443`
- *JAMA* 2024 — DOI `10.1001/jama.2024.6633`

## Third-party reference
- [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) (MIT) — palette / line-weight philosophy borrowed but tones rebuilt for JAMA

## 5-rule conformance checklist

| Rule | Spec value | Source |
|---|---|---|
| Sans-serif font | Helvetica primary | JAMA Instructions §Figures |
| Panel labels | uppercase `A, B, C` bold | Sample DOIs (recurring usage) |
| Raster DPI | 300 dpi | JAMA Instructions §Figures |
| Single-column width | 84 mm | JAMA Instructions |
| P-value format | `<.001` (no leading zero) | JAMA AMA Manual of Style |

## Notes / deviations from sources
- Spines all four sides (`top, bottom, left, right`) keeps a boxed look common to JAMA flagship figures; deviates from Nature's two-spine convention.
- `legend_frame: true` matches recurring style in JAMA forest plots.

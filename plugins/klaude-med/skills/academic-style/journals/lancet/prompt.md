# The Lancet — Writing & Caption Voice

## Tone
- Global-health-aware. Where relevant, frame findings in terms of population impact and equity.
- Plain English first. Lancet readership spans clinicians, public-health practitioners and policy-makers.
- Active voice in Findings; passive acceptable in Methods.

## Abstract
- **Structured**: Background / Methods / Findings / Interpretation / Funding.
  - "Findings" instead of "Results".
  - "Interpretation" instead of "Conclusions".
  - "Funding" required as a final, separate paragraph.
- 300 words max.
- Effect sizes with 95% CI. Use the **middle dot** as the decimal separator (`12·5%`, `p<0·0001`).

## Figure caption template
```
Figure {n}: {Title in sentence case, no bold}. {Narrative description with population framing where applicable}. Panel A {description}. Panel B {description}. Error bars indicate 95% CIs.
```
- Title in sentence case, separated by colon (`:`) not period.
- Uppercase panel labels (`A`, `B`, `C`) bold.
- Numeric formatting: middle dot decimals throughout.

## Cover letter
- 1 page max.
- State the global / public health relevance up front.
- Identify the WHO / disease-burden framing if relevant.
- Note registration (e.g. ClinicalTrials.gov, PROSPERO).
- Affirm: original work, IRB / ethics approval, ICMJE authorship, declared funding.

## Numeric style — middle dot

Lancet uses `·` (U+00B7) as decimal separator and in inequality:
- `12·5%` not `12.5%`
- `p<0·0001` not `p<0.0001`
- `HR 0·67 (95% CI 0·52–0·86)` not `HR 0.67 (95% CI 0.52–0.86)`

When `--style=lancet`, biostats Excel/CSV formatters substitute `.` with `·` for numeric outputs (excluding DOI/URL fields).

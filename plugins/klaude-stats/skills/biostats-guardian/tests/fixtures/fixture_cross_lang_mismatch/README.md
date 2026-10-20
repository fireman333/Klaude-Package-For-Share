# fixture_cross_lang_mismatch

Role 3 should produce **RES-014 block** because the alt-language reproducer (Python `lifelines`) returns HR ~1.5x different from the main R `coxph` output for the primary covariate, with identical events count and N — indicating a coding bug or variable definition drift between languages, not a tied-event method discrepancy.

## Scenario

- Main pipeline: R `survival::coxph` for `treatment_arm` on overall survival
  - Reported HR = 0.62 (95% CI 0.48-0.81), p=0.0003, events=180, N=520
- RES-014 cross-language repro: Python `lifelines.CoxPHFitter`
  - Recomputed HR = 0.93 (95% CI 0.71-1.21), p=0.58, events=180, N=520
- HR rel_diff = |0.62 - 0.93| / 0.62 = 50%, **>> 5% block threshold**
- Events count + N match → not a sample-split bug; likely reference level mismatch or covariate-coding drift

## Expected behavior

Role 3 subagent flags RES-014 with severity=block. May also surface a warn-level RES-014 hint if the subagent notices reference-level discrepancy in script.

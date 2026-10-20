# Routing Table — Flag Combinations → Bundled Skills

The R driver produces `diagnostic_report.json` with six boolean flags. This table expands the routing recommendation to every combination the driver can emit.

Skill names here refer to **the skills bundled in this plugin**, not survival-pipe's original names.

---

## Single-flag routing

| Flag | Primary | Secondary / Reference | Sensitivity / Manuscript note |
|------|---------|-----------------------|-------------------------------|
| (none) | `kaplan-meier` + standard Cox (`univariate-forest` / `multivariate-interaction`) | — | — |
| competing_risks | `competing-risk` (Fine-Gray or Aalen-Johansen CIF + Gray's test) | `kaplan-meier` on primary event only, for supplementary | Cause-specific Cox as sensitivity |
| recurrent_events | **Out of scope** (no user skill) — user must implement AG / PWP / WLW or multi-state manually | — | Flag only; do not silently reduce to first-event |
| time_varying | Extended Cox with `tt()` or counting-process `Surv(tstart, tstop, event)` — no built-in skill, implement manually | `kaplan-meier` with landmark times as reference | Landmark analysis if `immortal_time_risk` in `{medium, high}` |
| left_truncation | Delayed-entry `Surv(entry, exit, event)` — wrap `/kaplan-meier` / `/competing-risk` but manually modify the script's `lifelines`/`survival` call to use `entry_time` | — | Compare to naive `Surv(exit, event)` and report bias magnitude |
| informative_censoring | `kaplan-meier` / `competing-risk` as planned, but flag for manuscript limitation | — | IPCW (inverse probability of censoring weighting) as sensitivity |
| clustering | `kaplan-meier` / `competing-risk`, **+ robust SE via `+ cluster(id)` or frailty term** | — | If ICC > 0.01 → `coxme` frailty; else `+ cluster()` |

---

## Common multi-flag combinations

### competing_risks + clustering
- Primary: `competing-risk` with Fine-Gray regression
- Add: `cluster()` argument to Fine-Gray or use `coxme` with Fine-Gray weights
- Manuscript: report both pooled CIF and cluster-aware SE

### competing_risks + informative_censoring
- Primary: `competing-risk` (Fine-Gray naturally handles competing events as a form of dependent censoring)
- Sensitivity: IPCW on the primary event only
- Note: Fine-Gray ≠ informative-censoring fix — they solve different problems

### time_varying + left_truncation (registry data)
- Primary: extended Cox with `Surv(entry, tstart, tstop, event)` (R `survival::coxph`) — requires careful data setup
- Sensitivity: landmark analysis at clinically meaningful times
- **Reviewer risk**: very high — double-check with biostatistician before submission

### clustering + left_truncation
- Primary: `kaplan-meier` / `competing-risk` with `Surv(entry, exit, event)` + `+ cluster(site)`
- Watch for: `coxme` does not easily combine delayed entry + random effects; consider robust SE + manual variance adjustment

---

## What the driver writes

`diagnostic_report.json$recommended_primary` is a single string. `recommended_secondary` and `recommended_sensitivity` are arrays. Combinations like "competing-risk + frailty" are expressed as:

```json
{
  "recommended_primary": "competing-risk",
  "recommended_secondary": ["kaplan-meier (as reference only)"],
  "recommended_sensitivity": ["frailty Cox (coxme)", "landmark analysis"]
}
```

The downstream skill (`/competing-risk`) should read `diagnostic_report.json` in its Step 0 Context Recovery to detect the flags and auto-add frailty covariates or landmark sensitivity without re-asking.

---

## When to override the recommendation

The diagnostic is **evidence**, not a command. Override is appropriate when:

- **Sample size is tiny (< 50 events)**: Fine-Gray may fail to converge even if CIF-KM divergence > 0.05. Fall back to `kaplan-meier` and note limitation.
- **Competing event rate < 5%**: `1 − KM` ≈ CIF; standard KM is defensible, even if flag fires.
- **Cluster count < 3**: too few clusters for frailty estimation regardless of ICC. Use robust SE only.
- **Recurrent events with tiny fraction (`pct_recurrent` just above 0.05)**: consider first-event analysis with sensitivity to repeated-event count.

Always document the override in the manuscript Methods section.

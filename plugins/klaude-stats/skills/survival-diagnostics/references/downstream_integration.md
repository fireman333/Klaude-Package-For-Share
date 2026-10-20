# Downstream Skill Integration — Reading `diagnostic_report.json`

This reference is pointed to by the Step 0 of:
- `/kaplan-meier`
- `/competing-risk`
- `/univariate-forest`
- `/multivariate-interaction`

When the skill runs, it should look for a `diagnostic_report.json` produced by `/survival-diagnostics` and honor the recommendations below before asking the user for config overrides.

---

## Where to look

In order of precedence:

1. `{working_dir}/diagnostics/diagnostic_report.json` (default location when invoked via `research-plan` Step 3.5)
2. `{working_dir}/diagnostic_report.json` (ad-hoc location when user ran `/survival-diagnostics` manually)
3. `{parent_of_research_plan_json}/diagnostics/diagnostic_report.json`

If none found → proceed without diagnostic context (no warning needed).

---

## Fields to read

```json
{
  "recommended_primary": "kaplan-meier | competing-risk",
  "recommended_sensitivity": ["frailty Cox (coxme)", "..."],
  "checks": {
    "competing_risks": { "detected": bool, "n_event_types": int, "cif_km_divergence": float },
    "clustering":      { "detected": bool, "cluster_variable": str, "icc": float, "recommendation": "frailty|robust_se" },
    "left_truncation": { "detected": bool, "pct_truncated": float },
    "informative_censoring": { "detected": bool, "censoring_rate": float },
    "time_varying":    { "detected": bool, "immortal_time_risk": "low|medium|high" }
  }
}
```

---

## Per-skill response rules

### `/kaplan-meier`

| Flag | Action |
|------|--------|
| `recommended_primary="competing-risk"` | ⚠ Warn: "資料偵測到 competing risks（cif_km_divergence={x}），1−KM 會高估累積事件發生率。建議改用 `/competing-risk`。" Ask [A] switch to `/competing-risk` / [B] continue KM as reference only / [C] override. |
| `clustering.detected=true` | Offer to **stratify by cluster** (KM doesn't take `cluster()` argument): prefill `grouping.stratify_by = cluster_variable`, or add as covariate to sensitivity Cox. |
| `left_truncation.detected=true` | ⚠ KM with `Surv(time, event)` biased; this skill doesn't support `Surv(entry, exit, event)`. Recommend user manually modify output script or note as limitation. |
| `informative_censoring.detected=true` | Add to manuscript limitation note: "censoring appears informative (min p={p}, covariate={var})". |

### `/competing-risk`

| Flag | Action |
|------|--------|
| `competing_risks.detected=false` | ⚠ Note: "偵測到只有單一 event type，Fine-Gray 可能退化成 Cox。確認 event coding（0=censor, 1=primary, 2+=competing）是否正確。" |
| `clustering.detected=true, recommendation="frailty"` | Prefill `cluster_column` for Fine-Gray + frailty sensitivity. |
| `time_varying.detected=true` | ⚠ Counting-process not supported natively — flag as manual implementation. |

### `/univariate-forest`

| Flag | Action |
|------|--------|
| `recommended_primary="competing-risk"` | ⚠ Warn Cox HR will mix competing events; recommend Fine-Gray SHR (requires manual script). |
| `clustering.detected=true, recommendation="frailty"` | Auto-add `+ cluster(cluster_variable)` to all univariate Cox fits; note in footnote. |
| `clustering.detected=true, recommendation="robust_se"` | Auto-add robust SE (Huber) to each univariate fit. |

### `/multivariate-interaction`

| Flag | Action |
|------|--------|
| `recommended_primary="competing-risk"` | ⚠ Same as forest — suggest Fine-Gray multivariate. |
| `clustering.detected=true` | Prefill `cluster_column` in config (same as forest). |
| `time_varying.detected=true, risk="high"` | ⚠ Block and recommend counting-process reformulation before fitting. |
| `left_truncation.detected=true` | ⚠ Add `entry_column` to Surv() call — this skill doesn't expose the param by default. |

---

## User presentation

When at least one actionable flag fires, show the user a concise summary before proceeding:

```
📊 Survival Diagnostics 偵測到：
  - ✓ Clustering detected (Center_num, ICC=0.037) → 建議加 cluster(Center_num)
  - ✓ Informative censoring (min p<0.001, covariate=age) → manuscript 限制說明一段

[A] 接受建議（自動套用）
[B] 調整後接受
[C] Override 忽略
```

**Default：在 `pipeline_mode=auto` 下自動套用 [A]；在 `hitl` 下暫停問 user。**

---

## Override / skip

If `research_plan.json$.diagnostics.mode = "off"` or the user explicitly said "skip diagnostics", skip the entire read and don't prompt.

Record the decision in `research_plan.json$.pipeline[i].qc_warnings[]` so `biostats-guardian` Role 2 can pick it up later if cross-check is added.

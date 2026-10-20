# Decision Points — Ask User Checklist

These six choices cannot be made silently. The skill must ask and get confirmation before running the R driver.

Source: survival-pipe `AGENTS.md` § "Decision Points (Ask User)", adapted to the user's workflow.

---

## 1. Survival endpoint

**Why:** OS / PFS / DFS / CV death / composite give different time and event columns and can reverse the clinical conclusion.

**How to ask:** "要分析哪個 endpoint？對應哪一組時間/事件欄位？（例：OS → `time_death` + `event_death`）"

Common options:
- OS (overall survival)
- PFS (progression-free survival)
- DFS (disease-free survival)
- CSS / CV death (cause-specific survival)
- Composite (death OR hospitalization)

If composite → confirm how to derive (e.g., `time_composite = min(time_death, time_hosp)`; `event_composite = (event_death | event_hosp)`).

---

## 2. Event coding

**Why:** 0/1 single-event assumes no competing risks; 0/1/2+ implies competing risks. Diagnostic check 1 depends on this.

**How to ask:** "`event_column` 目前的編碼是什麼？0 = censor、1 = event；還是 0 = censor、1 = primary、2+ = competing？"

If competing-coded → confirm:
- Which code is the primary event of interest (default 1)
- Which codes are competing events
- Whether any codes should be re-coded as censor

---

## 3. Subject ID column

**Why:** Required for (a) recurrent-events aggregation (count events per subject), (b) last-row-per-subject reduction in informative-censoring check when data is in counting-process format.

**How to ask:** "每個病人是否有唯一 ID 欄位？若有，欄位名稱是？"

If absent → recurrent-events and (counting-process handling in) informative-censoring checks are skipped with `detected = null`.

---

## 4. Entry time column (optional)

**Why:** Left truncation occurs when subjects enter the risk set at time > 0 (e.g., `age_at_enrollment` with origin = birth). Standard KM/Cox without `Surv(entry, exit, event)` will give biased estimates.

**How to ask:** "資料裡有延遲入組（left truncation / delayed entry）嗎？例如以年齡為時間尺度，病人 60 歲才進入研究。"

If none → check 4 assumes no truncation (`detected = false`).

Typical triggers to ask:
- Age-as-time-scale studies
- Prevalent cohorts
- Registry data with heterogeneous enrollment dates when time origin ≠ enrollment

---

## 5. Cluster variable (optional)

**Why:** Multi-center studies, multi-physician cohorts, repeated measures within family — observations within the same cluster are correlated, and standard SE underestimates variance.

**How to ask:** "資料有叢集結構嗎（多中心、多醫師、多家庭）？若有，欄位名稱是？"

Common columns: `Hospital`, `Center`, `Site`, `Provider`, `Physician`, `Family`, `Ward`.

If none → check 6 skipped.

---

## 6. Time-varying exposure column (optional)

**Why:** If exposure status changes during follow-up (e.g., patient starts therapy mid-study, develops a comorbidity), treating it as baseline creates immortal time bias.

**How to ask:** "暴露（exposure）是基線就固定的，還是在追蹤期間會變動？若會變動，是哪個欄位？"

If yes → data must be in counting-process format (`tstart` + `tstop`, multi-row-per-subject). Confirm the interval columns.

If no → check 3 skipped with `detected = false`.

---

## Additional interview items (not in survival-pipe original, but required for our skill)

### Candidate covariates for informative-censoring test

**Why:** Check 5 compares each listed covariate between censored vs event subjects. Too many → false positives by multiple testing; too few → misses real informative censoring.

**Default:** all columns except time / event / id / entry / cluster / exposure / tstart / tstop.

**Recommendation:** cap at 5–10 key clinical variables the user plans to adjust for anyway (age, sex, disease severity, key comorbidities).

### Data filters

Match `/kaplan-meier` convention: array of `{column, operator, value}` applied before diagnostics run.

### Output directory

All outputs (`diagnostic_report.json`, `diagnostic_report.md`, `figures/`) go here. Place inside the study's analysis folder so `/kaplan-meier` or `/competing-risk` can pick up `diagnostic_report.json` as upstream context.

---
name: survival-diagnostics
description: "survival-diagnostics: pre-flight routing for time-to-event data — 6 checks (competing risks, recurrent events, time-varying exposure, left truncation, informative censoring, clustering) recommend kaplan-meier / competing-risk / Cox / IPW / frailty / robust SE. Trigger: survival diagnostics, survival 資料診斷, 存活資料診斷, 先診斷再分析, diagnostic report, 模型前檢查, 要用 KM 還是 CIF, pre-flight survival, 資料結構檢查 (survival), routing survival, 要怎麼選 survival 模型, check before KM, check before Cox; also before /kaplan-meier or /competing-risk if unsure."
---

# Survival Diagnostics — Pre-flight Routing for Time-to-Event Analyses

Run 6 diagnostic checks on time-to-event data to detect data-structure complications that change the correct model choice, then emit a routing recommendation. The goal: catch competing risks, immortal time bias, left truncation, informative censoring, and clustering **before** running KM/Cox — the three most common reviewer critiques in survival papers.

Design source: htlin222/survival-pipe `sa-diagnostics` (R/Quarto). This skill ports the 6-check logic into a single R driver adapted to xlsx/csv data conventions (upstream: https://github.com/htlin222/survival-pipe, MIT License, © Hsieh-Ting Lin).

**Disambiguation**: if the user is confident about KM or competing-risk directly, do NOT intercept — only run this skill when the user explicitly wants diagnostics or asks routing advice (e.g. "要用 KM 還是 CIF").

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 0: Context Recovery

1. Search working directory (and parent directories up to 2 levels) for `research_plan.json`.
2. If found, extract:
   - `study.data_file` → data file path
   - `population.filters` → filters
   - Primary outcome's `time_column`, `event_column`, `competing_event_column` (if any)
   - `covariates` → candidate columns for informative-censoring test
3. Present the pre-filled config summary and skip to Step 2.
4. If no `research_plan.json`, proceed to Step 1.

### Step 1: Decision Points (Ask-User Checklist) ★ Critical Step

Six items **must be confirmed** before running diagnostics — these are choices the skill cannot make silently (source: `references/decision_points.md`):

1. **Survival endpoint** — OS / PFS / DFS / CV death / composite? Which column pair (`time_*`, `event_*`)?
2. **Event coding** — is `event_column` 0/1 (single event) or 0/1/2+ (multi-coded, competing)? If multi-coded, which codes represent the primary event vs competing events?
3. **Subject ID column** — required for recurrent-events check and for aggregating counting-process data. If absent, recurrent-events and clustering checks will be skipped.
4. **Entry time column** (optional) — if the data has delayed entry (e.g., `age_at_enrollment`, left-truncation), specify `entry_column`. If none, left-truncation is assumed absent.
5. **Cluster variable** (optional) — hospital, center, provider, physician. If specified, clustering check runs.
6. **Time-varying exposure column** (optional) — if the exposure status changes during follow-up (e.g., treatment started after enrollment), specify `exposure_column` and require counting-process data (`tstart` / `tstop`).

Additional:
- **Candidate covariates** for informative-censoring test — list of column names to compare between censored vs event subjects. Default: all columns except structural ones.
- **Data file path**, **filters**, **output directory**.

Present a one-line-per-item table and ask the user to confirm. **Do not proceed to Step 2 until confirmation.**

### Step 2: Validate Data

Before running diagnostics, read the data file and verify:
- File exists and loads (xlsx / csv / parquet via `readxl` / `readr`).
- Specified time, event, id, entry, cluster, exposure columns exist.
- Event column contains expected codes (0 = censor, 1+ = events).
- Print `dim(df)`, `table(event_column)`, and quick summaries for the chosen columns.

```r
df <- if (endsWith(data_file, ".xlsx")) readxl::read_excel(data_file) else readr::read_csv(data_file)
cat("Shape:", nrow(df), "x", ncol(df), "\n")
print(table(df[[event_col]], useNA = "ifany"))
```

### Step 3: Confirm Column Mapping (欄位確認)

Build the mapping table exactly like `/kaplan-meier` Step 3:

| 使用者描述 | 對應欄位名稱 | 資料類型 | 角色 |
|-----------|-------------|---------|------|
| 追蹤時間    | `time_death`     | continuous   | time_column    |
| 死亡事件    | `event_competing`| multi-code   | event_column (0/1/2) |
| 病人 ID    | `PatientID`      | id           | id_column      |
| 收案日期    | (none)           | —            | entry_column (skip left-trunc) |
| 醫院別      | `Hospital`       | categorical  | cluster_column |
| 暴露        | (none)           | —            | exposure_column (skip time-varying) |

Ask user to confirm before Step 4.

### Step 4: Generate JSON Config

Save config alongside the output directory as `diagnostic_config.json`:

```json
{
  "data_file": "/abs/path/to/data.xlsx",
  "filters": [{"column": "HF_type", "operator": "==", "value": 3.0}],
  "time_column": "time_death",
  "event_column": "event_competing",
  "id_column": "PatientID",
  "entry_column": null,
  "cluster_column": "Hospital",
  "exposure_column": null,
  "tstart_column": null,
  "tstop_column": null,
  "candidate_covariates": ["age", "gender", "LVEF", "NYHA"],
  "thresholds_file": null,
  "output_dir": "/abs/path/to/output/diagnostics"
}
```

### Step 5: Run Diagnostics

Execute the single R driver (runs all 6 checks + aggregator):

```bash
Rscript ${CLAUDE_SKILL_DIR}/scripts/survival_diagnostics.R <CONFIG_PATH>
```

This produces in `output_dir/`:
- `diagnostic_report.json` — machine-readable flags + recommendations
- `diagnostic_report.md` — human-readable summary with decision flowchart
- `figures/competing_risks_events.png`, `recurrent_events_histogram.png` (when applicable)

### Step 6: Present Routing Recommendation

Read `diagnostic_report.json` and present a concise summary to the user:

```
Survival Diagnostics 結果
────────────────────────────
✓ competing_risks:         detected (3 event types, CIF-KM divergence 0.082)
  recurrent_events:         not detected
✓ time_varying:             detected (immortal time ratio 0.14, high risk)
  left_truncation:          not detected
  informative_censoring:    not detected (censor rate 14%, all covariate p>0.05)
✓ clustering:               detected (Hospital, 12 clusters, ICC 0.031)

建議路由
────────────────────────────
Primary:      competing-risk（因為 CIF 與 1-KM 偏離 >0.05 且有 ≥2 event types）
Secondary:    kaplan-meier as reference, time-varying Cox if exposure changes
Sensitivity:  landmark analysis（immortal time bias）、frailty model（clustering）
```

Then ask: "要直接呼叫 `/competing-risk` 開跑主要分析嗎，還是先看 `diagnostic_report.md` 詳讀？"

### Step 7: Save Reusable Script

Copy the driver to output dir so future runs don't depend on skill path:

```bash
cp ${CLAUDE_SKILL_DIR}/scripts/survival_diagnostics.R <OUTPUT_DIR>/survival_diagnostics.R
```

Re-run command: `Rscript <OUTPUT_DIR>/survival_diagnostics.R <CONFIG_PATH>`

---

## Routing Logic

`diagnostic_report.json` maps to the skills bundled in this plugin (not survival-pipe's original names):

| Flag detected | Recommended primary skill |
|---------------|---------------------------|
| None | `kaplan-meier` + standard Cox |
| competing_risks | `competing-risk` (takes priority over kaplan-meier) |
| time_varying (only) | extended Cox with `tt()` or counting-process format; no built-in skill — implement manually |
| left_truncation | `kaplan-meier` / `competing-risk` but with delayed-entry `Surv(entry, exit, event)` |
| informative_censoring | IPW / sensitivity analysis — note in manuscript limitations |
| clustering | `kaplan-meier` / `competing-risk` with `+ cluster(hospital)` robust SE, or frailty Cox |
| competing_risks + clustering | `competing-risk` with frailty / robust SE |
| recurrent_events | out of scope (not covered by user's current skills) — flag to user |

Always add `kaplan-meier` as secondary/reference when primary is not KM.

---

## JSON Config Schema

| Field | Required | Description |
|-------|----------|-------------|
| `data_file` | Yes | Absolute path to xlsx or csv |
| `filters` | No | Array of `{column, operator, value}` applied before diagnostics |
| `time_column` | Yes | Follow-up time column |
| `event_column` | Yes | Event indicator column (0 = censor, 1+ = events) |
| `id_column` | No | Subject ID — required for recurrent-events and clustering via subject-level aggregation |
| `entry_column` | No | Delayed-entry time column (left truncation) |
| `cluster_column` | No | Cluster variable (hospital, site) |
| `exposure_column` | No | Time-varying exposure column (requires counting-process) |
| `tstart_column` | No | Counting-process interval start (for time-varying / recurrent) |
| `tstop_column` | No | Counting-process interval end |
| `candidate_covariates` | No | Columns for informative-censoring Wilcoxon / chi-square tests. Default: all non-structural columns |
| `thresholds_file` | No | Override default `config/thresholds.yaml` |
| `output_dir` | Yes | Where to write `diagnostic_report.{json,md}` + figures |

---

## The 6 Diagnostic Checks

### 1. Competing Risks
- Count distinct event codes beyond censoring.
- If ≥ 2, compute CIF (via `cmprsk::cuminc`) for the primary event and compare to `1 − KM(primary)`.
- **Flag**: `n_event_types ≥ 2` AND `max|CIF − (1−KM)| > 0.05`.

### 2. Recurrent Events
- Count events per subject using `id_column`.
- **Flag**: proportion of subjects with ≥ 2 events ≥ 5 %.
- Requires `id_column`; else skipped with `detected = null`.

### 3. Time-Varying Exposure
- Requires counting-process format (`tstart_column`, `tstop_column`).
- Detect binary covariates whose value changes within a subject (0 → 1 switch).
- Compute immortal time ratio = total time before switch / total person-time.
- **Flag**: `immortal_time_ratio > 0.10` OR `% switchers > 5 %`.
- Classify risk as low / medium / high.

### 4. Left Truncation
- If `entry_column` given, compute `pct_truncated = mean(entry > 0)`.
- **Flag**: `pct_truncated ≥ 5 %`.
- Optional: test if entry time is associated with covariates (informative truncation).

### 5. Informative Censoring
- Compare `candidate_covariates` between censored vs event subjects.
- Continuous: Wilcoxon rank-sum; categorical: chi-square.
- **Flag**: any covariate `p < 0.05` AND `censoring_rate ≥ 10 %`.

### 6. Clustering
- Use `cluster_column` (must be provided).
- Estimate ICC via one-way ANOVA on time column (approximate); fallback to `coxme` frailty if installed.
- **Flag**: `ICC > 0.01` AND `n_clusters ≥ 3` AND `avg_cluster_size ≥ 5`.
- Recommendation: `frailty` (if ICC > threshold) or `robust_se`.

All thresholds overridable in `config/thresholds.yaml`.

---

## R Package Dependencies

Required:
- `jsonlite`, `yaml`
- `survival` (base KM / Cox)

Conditional:
- `readxl` (xlsx input)
- `readr` (csv input)
- `cmprsk` (CIF-KM divergence in check 1)
- `coxme` (random-effect ICC in check 6)

Install missing packages with `install.packages(c("..."))` before first run. The driver emits `[DIAG_WARNING]` to stderr for missing optional packages and proceeds.

---

## File Manifest

- `SKILL.md` — this file
- `scripts/survival_diagnostics.R` — single R driver (all 6 checks + report generation)
- `config/thresholds.yaml` — default thresholds (override via `thresholds_file` in config)
- `references/decision_points.md` — Ask-User checklist with full rationale per item
- `references/routing_table.md` — expanded routing flowchart

---

## Pipeline Integration

When called from `research-plan` orchestrator:
- Config pre-generated by `generate_configs.py` at `configs/diagnostics_config.json`.
- Skip Steps 1–4 (interview); go directly to Step 5.
- Exit code 0 = success.
- Emit `[DIAG_FLAG]` to stderr per detected issue for pipeline collection.
- `diagnostic_report.json` consumed by downstream `kaplan-meier` / `competing-risk` skill to decide whether to run.

---

## Example Usage

**User**: "我有一份 HFpEF 的隨訪資料，有心血管死亡跟非心血管死亡兩種事件，而且收了 12 家醫院。該用 KM 還是 CIF？"

**Claude**: Triggers this skill. Step 1 confirms endpoint = CV death (`event_competing == 1`), competing = non-CV death (`== 2`), cluster = `Hospital`, id = `PatientID`. Step 5 runs R driver. Step 6 presents:
- competing_risks: detected (divergence 0.08) → route to `competing-risk`
- clustering: detected (ICC 0.025) → add frailty or `cluster()` robust SE
- Primary: `competing-risk` with frailty
- Secondary: `kaplan-meier` as naive reference (for supplementary)

---

## 不做的事

- ❌ 不執行 KM / Cox / CIF 本身 — 只跑診斷，實際分析由 `/kaplan-meier` / `/competing-risk` 完成
- ❌ 不做 recurrent event 或 multi-state 模型實作 — 使用者目前 skill set 不含
- ❌ 不改寫 `/kaplan-meier` 或 `/competing-risk` — 使用者可選擇忽略本 skill 的建議
- ❌ 不做 PH assumption / Cox convergence 等 **post-execution** QA — 那是 `biostats-guardian` Role 3 (`references/qa_thresholds.md`) 的範圍

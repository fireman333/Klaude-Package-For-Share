---
name: competing-risk
description: "Competing risk analysis. Trigger: competing risk, competing risks, cumulative incidence, CIF, CIF plot, CIF curve, competing event, competing cause, Aalen-Johansen, cause-specific hazard, cumulative incidence curve, competing event analysis, 競爭風險, 競爭風險分析, 累積發生率, CIF圖, 競爭事件, 做CIF, CIF分析, 畫CIF圖, 幫我做competing risk分析, draw CIF curves, 做競爭風險分析, plot cumulative incidence, 做CIF分析."
---

# Competing Risk Analysis — CIF Plot + Cause-Specific Log-Rank

> **Scope (P-7 audit fix, 2026-05-07)**: this Python skill computes CIFs via the Aalen-Johansen estimator and compares groups with **cause-specific log-rank** (`lifelines.multivariate_logrank_test`). It does **NOT** implement Gray's test or Fine-Gray subdistribution hazard regression — those are R-only (`cmprsk::cuminc`, `cmprsk::crr`). For Gray's test or Fine-Gray analyses, use the `ma-meta-analysis` R pipeline or run R `cmprsk` directly. The script aborts with `[FATAL]` if a config requests `fine_gray=true`.
>
> **Skill priority**: this skill takes priority over `kaplan-meier` when competing events are mentioned.

Perform competing risk analysis using the Aalen-Johansen estimator to compute Cumulative Incidence Functions (CIF) for each event type, compare groups with cause-specific log-rank, and generate publication-ready CIF curves. Produces formatted Excel summary and CIF plot.

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 0: Context Recovery

Before gathering requirements, check for existing upstream context:

1. Search the working directory (and parent directories up to 2 levels) for `research_plan.json`
2. If found, read it and extract relevant fields for this skill:
   - `study.data_file` → Data file path
   - `population.filters` → Data filters
   - `grouping` → Grouping variable, group values and labels
   - `outcomes` → Match the outcome with `competing_event_column` to extract: time_column, event_column, competing_event_column, competing_event_labels, time_unit, time_scale, time_points
   - `derived_variables` → Derived variables
3. Present the pre-filled config to the user: "Found research plan — using these settings:" followed by a concise summary
4. Ask user to confirm or modify, then skip to Step 2
5. If no `research_plan.json` found, also check for a `learnings.md` in the working directory — if present, read column mapping corrections and apply them as defaults
6. Check for `diagnostic_report.json` in `{working_dir}/diagnostics/` or `{working_dir}/`. If found, read it and apply the per-skill integration rules in `${CLAUDE_SKILL_DIR}/../survival-diagnostics/references/downstream_integration.md` (`/competing-risk` section). Key actions: warn if `checks.competing_risks.detected=false` (may indicate miscoded events); prefill `cluster_column` if `checks.clustering.detected=true, recommendation="frailty"`; flag time-varying as manual counting-process work if detected.

If no upstream context is found, proceed to Step 1.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Data file path** — xlsx, csv, or other pandas-readable format
2. **Data filters** (optional) — conditions to subset the data before analysis (e.g., `HF_type == 3`)
3. **Derived variables** (optional) — new columns to compute before analysis:
   - `coalesce` type: pick the first non-null from a list of columns
   - `expression` type: compute from existing columns
4. **Grouping variable** — the column name that defines the groups, plus:
   - Value and label for each group (supports 2+ groups)
5. **Composite endpoint** — Ask whether the user wants to analyze a **composite endpoint (time to first event of death OR hospitalization)**. If yes:
   - If the data already has a composite event column (multi-coded: 0=censor, 1=primary event, 2=competing), use it directly.
   - If not, offer to derive composite columns via `derived_variables`:
     - `time_composite`: `expression` type — `np.minimum(time_death, time_hosp)` (takes the earlier of the two)
     - `event_composite`: `expression` type — use appropriate coding (e.g., `np.where(event_death==1, 1, np.where(event_hosp==1, 1, 0))` for a simple composite, or further encode competing events as needed)
   - Always confirm which death and hospitalization columns exist before deriving.
6. **Time column** — the column containing follow-up time
7. **Event column** — the column containing the event indicator:
   - `0` = censored (no event)
   - `1` = primary event of interest (e.g., CV death)
   - `2` = competing event (e.g., non-CV death)
   - Can support additional event codes (3, 4, etc.)
8. **Event labels** — mapping of event codes to labels (e.g., `{"1": "CV death", "2": "Non-CV death"}`)
9. **Primary event** — which event code is the primary event of interest (default: `1`)
10. **Time unit** — "days", "months", or "years" (for axis labeling)
11. **Time scale** (optional) — conversion factor (e.g., 365.25 for days → years)
12. **Time points** — specific time points for CIF reporting (e.g., [1, 3, 5])
13. **Plot settings** (optional) — colors, axis limits, CI shading, figure size
14. ~~**Fine-Gray regression** (optional)~~ — **NOT IMPLEMENTED in this Python skill** (P-7 audit fix). Setting `fine_gray=true` in config triggers `[FATAL]` abort. Use R `cmprsk::crr` for Fine-Gray.
15. **Output file path** (base name; generates `.xlsx` and `.png`)
15. **Table title and subtitle** (optional)
16. **Abbreviations** — full forms of all abbreviations used

### Step 2: Validate Data

Before generating the config, read the data file to confirm:
- The file exists and is readable
- All specified columns exist
- The event column contains the expected values (0, 1, 2, ...)
- The grouping variable contains the expected values

Run a quick Python snippet:
```python
import pandas as pd
df = pd.read_excel("path")  # or read_csv
print(f"Shape: {df.shape}")
print(f"Event values: {df['event_col'].value_counts()}")
print(f"Group values: {df['group_col'].value_counts()}")
```

### Step 3: Confirm Column Mapping (欄位確認)

在產生設定檔之前，先將使用者描述的變數與實際 Excel 欄位名稱整理成對應表，確保沒有對應錯誤。

根據 Steps 1–2 收集到的資訊，建立以下表格：

| 使用者描述 | 對應欄位名稱 | 資料類型 | 角色 |
|-----------|-------------|---------|------|
| 有無 AF    | `AF_hx`          | binary     | 分組變數 (grouping)                              |
| 追蹤時間    | `time_death`     | continuous | 時間變數 (time)                                  |
| 競爭事件    | `event_competing`| multi-code | 事件變數 (0=censor, 1=CV death, 2=Non-CV death)  |
| 只收 HFpEF | `HF_type == 3`  | filter     | 資料篩選 (filter)                                |

*(以上為範例，實際內容依使用者需求填入)*

**規則：**
1. 列出所有使用者提及的變數：分組、時間、事件（含事件編碼說明）、Fine-Gray 共變數、篩選條件、衍生變數
2. 衍生變數顯示推導方式（如 `event_competing ← np.where(...)`）
3. 篩選條件顯示完整條件（如 `HF_type == 3`）
4. 若使用者用口語中文描述（如「心血管死亡」），顯示對應的實際欄位名稱與編碼值
5. 若無法確定對應欄位，列出前 3 個候選欄位請使用者選擇

呈現表格後詢問：

> 以上欄位對應是否正確？如有需要修正請告知，確認後將進入設定檔產生。

**使用者確認前不得進入 Step 4。** 若使用者修正了任何對應，更新後重新呈現確認。

> **Guardian 註記**：若本 skill 由 `research-plan` orchestrator 呼叫且 `research_plan.json$.guardian.mode != "off"`，使用者確認後 orchestrator 會自動派 `biostats-guardian` Role 1 (Column Auditor) subagent 對 config 做獨立稽核（COL-001..011）。直接呼叫本 skill 時不會觸發。

### Step 4: Generate JSON Config

Write a JSON config file **alongside the output file**, using the same base name with `_config.json` suffix (e.g., if `output_file` is `/path/to/CompetingRisk.xlsx`, save config as `/path/to/CompetingRisk_config.json`). This ensures the config persists for future re-runs. The schema is documented below.

### Step 5: Check Missing Data

Run the script in missing-data-check mode:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/competing_risk.py /tmp/competing_risk_config.json --check-missing
```

This prints a report showing missing counts and percentages for time and event columns per group.

### Step 6: Execute Analysis

Run the full script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/competing_risk.py /tmp/competing_risk_config.json
```

This produces:
- CIF plot image (`.png`)
- Excel file (`.xlsx`) with CIF summary, Gray's test results, and optional Fine-Gray regression

### Step 7: Present Results

After execution, tell the user:
- Output file locations (xlsx and png)
- Sample size and event counts per group and event type (minimum 5 events per group required — blocking threshold; < 10 events per group triggers warning)
- Gray's test p-value for each event type
- CIF at specified time points
- Fine-Gray regression results (if requested)

Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory: the directory containing this SKILL.md file.

### Step 8: Save Reusable Script

After presenting results, make the analysis **re-runnable** so the user can modify variables without re-triggering this skill:

1. Copy the Python script to the same directory as the output file:
```bash
cp ${CLAUDE_SKILL_DIR}/scripts/competing_risk.py <OUTPUT_DIR>/competing_risk.py
```

2. The JSON config file (from Step 4) is already saved alongside the output file.

3. Tell the user the following re-run instructions:
   - **Config file**: `<CONFIG_PATH>` (the JSON saved in Step 4)
   - **Script**: `<OUTPUT_DIR>/competing_risk.py`
   - **Re-run command**: `python <OUTPUT_DIR>/competing_risk.py <CONFIG_PATH>`
   - **Common modifications** (edit the config JSON directly):
     - Change event labels: edit `event_labels`
     - Change time points: edit `time_points` array
     - Change grouping: edit the `grouping` object
     - Add/modify Fine-Gray covariates: edit the `fine_gray` object
   - After editing, just ask Claude to run: `python <OUTPUT_DIR>/competing_risk.py <CONFIG_PATH>`

Replace `<OUTPUT_DIR>` with the directory containing the output xlsx file, and `<CONFIG_PATH>` with the actual config file path.

### Step 9: Record Learnings

Silently check whether any corrections occurred during this run:

1. **Column mapping corrections** — Did the user change any column names during Step 3 confirmation?
2. **Config modifications** — Did the user modify the auto-generated config in Step 4?
3. **QC warnings** — Were there any missing data warnings or unexpected data patterns?

If any corrections occurred, append a structured entry to `<OUTPUT_DIR>/learnings.md`:

```
## [YYYY-MM-DD] competing-risk run
- Column correction: "<original>" → "<corrected>" (user specified during mapping)
- Config change: <what was changed>
- QC note: <observation>
```

This file is read by Step 0 (Context Recovery) in future runs to avoid repeating the same corrections.

---

## JSON Config Schema

```json
{
  "data_file": "/absolute/path/to/data.xlsx",
  "filters": [
    {"column": "HF_type", "operator": "==", "value": 3.0}
  ],
  "derived_variables": [],
  "grouping": {
    "column": "AF_hx",
    "groups": [
      {"value": 1.0, "label": "AF"},
      {"value": 0.0, "label": "No AF"}
    ]
  },
  "time_column": "time_death",
  "event_column": "event_competing",
  "event_labels": {
    "1": "CV death",
    "2": "Non-CV death"
  },
  "primary_event": 1,
  "time_unit": "years",
  "time_scale": 365.25,
  "time_points": [1, 3, 5],
  "plot_settings": {
    "confidence_interval": true,
    "colors": null,
    "x_max": null,
    "x_tick_interval": null,
    "y_max": null,
    "figsize": [8, 6],
    "dpi": 300,
    "legend_position": "upper left",
    "plot_mode": "primary_by_group"
  },
  "fine_gray": null,
  "title": "Competing Risk Analysis — CV Death",
  "subtitle": "TSOC HF Registry — HFpEF Cohort",
  "output_file": "/absolute/path/to/CompetingRisk.xlsx",
  "abbreviations": "CIF = cumulative incidence function; CI = confidence interval; CV = cardiovascular",
  "missing_data_handling": "listwise"
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `data_file` | Yes | Absolute path to the data file |
| `filters` | No | Array of filter conditions |
| `derived_variables` | No | Array of new columns to compute |
| `grouping` | Yes | Defines comparison groups |
| `time_column` | Yes | Column for follow-up time |
| `event_column` | Yes | Column for event indicator (0=censor, 1=primary, 2+=competing) |
| `event_labels` | Yes | Mapping of event codes to display labels |
| `primary_event` | No | Event code for primary event of interest (default: `1`) |
| `time_unit` | Yes | Time unit for axis labels |
| `time_scale` | No | Conversion factor for time values (default: `null`) |
| `time_points` | Yes | Time points for CIF reporting |
| `plot_settings` | No | Plot customization |
| `fine_gray` | No | Fine-Gray regression settings (see below) |
| `title` | No | Table/plot title |
| `subtitle` | No | Subtitle text |
| `output_file` | Yes | Output Excel path; PNG uses same base + .png |
| `abbreviations` | Yes | Abbreviation footnote text |

### Plot Settings

| Field | Default | Description |
|-------|---------|-------------|
| `confidence_interval` | `true` | Show 95% CI shading |
| `colors` | auto | Colors for groups/events |
| `x_max` | `null` | Max x-axis value |
| `x_tick_interval` | `null` | X-axis tick interval |
| `y_max` | `null` | Max y-axis value (null = auto) |
| `figsize` | `[8, 6]` | Figure size in inches |
| `dpi` | `300` | Resolution |
| `legend_position` | `"upper left"` | Legend location |
| `plot_mode` | `"primary_by_group"` | `"primary_by_group"`: CIF of primary event by group. `"all_events"`: CIF of all events stacked by group |

### Fine-Gray Regression (optional)

```json
{
  "fine_gray": {
    "covariates": [
      {"label": "Age (per 10 yrs)", "column": "age", "type": "continuous", "scale": 10},
      {"label": "Male sex", "column": "gender", "type": "binary"}
    ]
  }
}
```

### Filter Operators

Supported: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

---

## Statistical Methods

### Cumulative Incidence Function (CIF)
- Computed using the Aalen-Johansen estimator, which properly accounts for competing events.
- Unlike 1 − KM, CIF does not overestimate the probability of the event in the presence of competing risks.
- CIF(t) = Σ [S(tᵢ₋₁) × hₖ(tᵢ)] for all event times tᵢ ≤ t, where S is the overall survival (KM for any event) and hₖ is the cause-specific hazard for event k.

### Gray's Test
- Non-parametric test comparing CIF curves between groups.
- Tests the null hypothesis that CIF curves are identical across groups for a specific event type.
- Based on weighted differences in cause-specific hazard functions.

### Fine-Gray Subdistribution Hazard Model (optional)
- Regression model for the subdistribution hazard of a specific event type.
- Produces subdistribution hazard ratios (SHR) with 95% CI.
- Accounts for competing risks in the regression framework.

### p-value Formatting
- `<0.001` for p < 0.001
- `x.xxx` for p ≥ 0.001

---

## Output Description

### CIF Plot (`.png`)
- CIF curves for the primary event, one curve per group
- Semi-transparent 95% CI shading (when enabled)
- X-axis: "Time ({time_unit})", Y-axis: "Cumulative Incidence"
- Gray's test p-value displayed on the plot
- Legend with group labels
- Publication-ready: 300 DPI, clean fonts

### Excel File (`.xlsx`)

#### Sheet 1: "CIF Summary"
- **Row 1**: Title (dark blue background, white text)
- **Row 2**: Subtitle with total sample size
- **Headers**: Group | N | Events by type | CIF at each time point
- **Data rows**: One per group with alternating shading
- **Footnotes**: Gray's test p-value, abbreviations

#### Sheet 2: "Gray's Test"
- Test statistic, df, p-value for each event type comparison

#### Sheet 3: "Fine-Gray Regression" (if requested)
- Covariate | SHR (95% CI) | p-value

---

## Example Usage

**User**: "I want to do competing risk analysis for HFpEF patients. Data is in TSOC_data_merge.xlsx, filter for HF_type==3. Group by AF_hx (1=AF, 0=No AF). Time variable: time_death (in days, convert to years). Event variable: event_competing (0=censor, 1=CV death, 2=non-CV death). Plot CIF for CV death comparing AF vs No AF. Show 1-year, 3-year, 5-year CIF."

**Claude's response**: Generates the JSON config, runs missing data check, then produces the CIF plot and formatted Excel with Gray's test results.

---

## Pipeline Integration

When called from the `research-plan` orchestrator pipeline:

- Config is pre-generated at `configs/{step_id}_config.json` by `generate_configs.py`
- Skip Steps 1–4 (interactive interview + column confirmation); proceed directly to Step 5 (check missing data) and Step 6 (execute)
- Exit code 0 = success, non-zero = failure (triggers retry then error in pipeline)
- QC warnings are emitted to stderr with `[QC_WARNING]` prefix for pipeline collection
- QC blocking issues are emitted to stderr with `[QC_BLOCKING]` prefix (step marked as error)

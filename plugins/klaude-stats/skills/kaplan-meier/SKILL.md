---
name: kaplan-meier
description: "Publication-ready Kaplan-Meier survival curves w/ log-rank test, number-at-risk table, Excel summary; 2+ groups. Trigger: Kaplan-Meier, KM curve, survival curve, survival analysis, log-rank test, survival plot, time-to-event plot, event-free survival, overall survival curve, KM plot, draw survival curve, 存活曲線, KM分析, 存活分析, 生存曲線, KM圖, 存活率, 對數秩檢定, 畫存活曲線, 做KM, 畫KM圖, 幫我畫KM curve, draw survival curves, 做存活分析, 畫存活曲線."
---

# Kaplan-Meier Survival Curve Generator

Generate publication-ready Kaplan-Meier survival curves with log-rank test, number at risk table below the plot, and a formatted Excel summary including median survival, survival rates at specified time points, and test statistics. Supports 2 or more groups.

**Disambiguation**: if the user also mentions competing risk, competing event, CIF, or cumulative incidence, route to the `competing-risk` skill instead.

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 0: Context Recovery

Before gathering requirements, check for existing upstream context:

1. Search the working directory (and parent directories up to 2 levels) for `research_plan.json`
2. If found, read it and extract relevant fields for this skill:
   - `study.data_file` → Data file path
   - `population.filters` → Data filters
   - `grouping` → Grouping variable, group values and labels
   - `outcomes` → Match the outcome the user wants (primary or secondary) to extract: time_column, event_column, time_unit, time_scale, time_points
   - `derived_variables` → Derived variables (including composite endpoints)
3. Present the pre-filled config to the user: "Found research plan — using these settings:" followed by a concise summary
4. Ask user to confirm or modify, then skip to Step 2
5. If no `research_plan.json` found, also check for a `learnings.md` in the working directory — if present, read column mapping corrections and apply them as defaults
6. Check for `diagnostic_report.json` in `{working_dir}/diagnostics/` or `{working_dir}/`. If found, read it and apply the per-skill integration rules in `${CLAUDE_SKILL_DIR}/../survival-diagnostics/references/downstream_integration.md` (`/kaplan-meier` section). Key actions: warn if `recommended_primary="competing-risk"`; offer stratification if `checks.clustering.detected=true`; flag manuscript limitations for detected left truncation / informative censoring.

If no upstream context is found, proceed to Step 1.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Data file path** — xlsx, csv, or other pandas-readable format
2. **Data filters** (optional) — conditions to subset the data before analysis (e.g., `HF_type == 3`)
3. **Derived variables** (optional) — new columns to compute before analysis:
   - `coalesce` type: pick the first non-null from a list of columns
   - `expression` type: compute from existing columns (e.g., BMI = Weight / (Height/100)^2)
4. **Grouping variable** — the column name that defines the groups, plus:
   - Value and label for each group (supports 2 or more groups)
   - Example: value=1.0, label="AF" and value=0.0, label="No AF"
5. **Composite endpoint** — Ask whether the user wants to analyze a **composite endpoint (time to first event of death OR hospitalization)**. If yes:
   - If the data already has composite columns, use them directly.
   - If not, offer to derive them via `derived_variables`:
     - `time_composite`: `expression` type — `np.minimum(time_death, time_hosp)` (requires both time columns)
     - `event_composite`: `expression` type — `np.where((event_death == 1) | (event_hosp == 1), 1, 0)`
   - Always confirm which death and hospitalization columns exist before deriving.
6. **Time column** — the column containing survival/follow-up time
7. **Event column** — the column containing the event indicator (1=event, 0=censor)
8. **Time unit** — "days", "months", or "years" (for axis labeling)
9. **Time scale** (optional) — conversion factor to apply to raw time values (e.g., 365.25 to convert days → years)
10. **Time points** — specific time points for survival rate reporting (e.g., [1, 3, 5] for 1-year, 3-year, 5-year survival)
11. **Plot settings** (optional) — confidence interval shading, censor marks, colors, axis limits, number at risk table
12. **Output file path** (base name; script generates `.xlsx` and `.png`)
13. **Table title and subtitle** (optional)
14. **Abbreviations** — full forms of all abbreviations used (e.g., "KM = Kaplan-Meier; CI = confidence interval; AF = atrial fibrillation"). This will appear as a footnote at the bottom of the Excel table. Always collect this from the user to ensure the table is publication-ready.

### Step 2: Validate Data

Before generating the config, read the data file to confirm:
- The file exists and is readable
- All specified columns exist
- The grouping variable contains the expected values
- Time and event columns exist and have valid data

Run a quick Python snippet:
```python
import pandas as pd
df = pd.read_excel("path")  # or read_csv
print(f"Shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
print(f"Group column values: {df['group_col'].value_counts()}")
print(f"Event column values: {df['event_col'].value_counts()}")
```

### Step 3: Confirm Column Mapping (欄位確認)

在產生設定檔之前，先將使用者描述的變數與實際 Excel 欄位名稱整理成對應表，確保沒有對應錯誤。

根據 Steps 1–2 收集到的資訊，建立以下表格：

| 使用者描述 | 對應欄位名稱 | 資料類型 | 角色 |
|-----------|-------------|---------|------|
| 有無 AF    | `AF_hx`        | binary     | 分組變數 (grouping) |
| 追蹤時間    | `time_death`   | continuous | 時間變數 (time)     |
| 死亡事件    | `event_death`  | binary     | 事件變數 (event)    |
| 只收 HFpEF | `HF_type == 3` | filter     | 資料篩選 (filter)   |

*(以上為範例，實際內容依使用者需求填入)*

**規則：**
1. 列出所有使用者提及的變數：分組、時間、事件、篩選條件、衍生變數
2. 衍生變數顯示推導方式（如 `time_composite ← np.minimum(time_death, time_hosp)`）
3. 篩選條件顯示完整條件（如 `HF_type == 3`）
4. 若使用者用口語中文描述（如「追蹤時間」），顯示對應的實際欄位名稱（如 `time_death`）
5. 若無法確定對應欄位，列出前 3 個候選欄位請使用者選擇

呈現表格後詢問：

> 以上欄位對應是否正確？如有需要修正請告知，確認後將進入設定檔產生。

**使用者確認前不得進入 Step 4。** 若使用者修正了任何對應，更新後重新呈現確認。

> **Guardian 註記**：若本 skill 由 `research-plan` orchestrator 呼叫且 `research_plan.json$.guardian.mode != "off"`，使用者確認後 orchestrator 會自動派 `biostats-guardian` Role 1 (Column Auditor) subagent 對 config 做獨立稽核（COL-001..011）。直接呼叫本 skill 時不會觸發。

### Step 4: Generate JSON Config

Write a JSON config file **alongside the output file**, using the same base name with `_config.json` suffix (e.g., if `output_file` is `/path/to/KM_Survival.xlsx`, save config as `/path/to/KM_Survival_config.json`). This ensures the config persists for future re-runs. The schema is documented below.

### Step 5: Check Missing Data

Run the script in missing-data-check mode:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/kaplan_meier.py /tmp/kaplan_meier_config.json --check-missing
```

This prints a report showing missing counts and percentages for the time column and event column, per group. Present the report to the user. If there are missing values, ask how they want to handle them:
- **Listwise deletion** (default): exclude any row with missing time or event values
- **Other**: let the user specify

If all variables have zero missing values, report this and proceed.

### Step 6: Execute Analysis

Run the full script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/kaplan_meier.py /tmp/kaplan_meier_config.json
```

This produces:
- Excel file (`.xlsx`) with survival summary and log-rank test results
- KM plot image (`.png`) with number at risk table

### Step 7: Present Results

After execution, tell the user:
- Output file locations (xlsx and png)
- Sample size and event counts per group
- Median survival with 95% CI per group
- Log-rank test p-value
- Survival rates at the specified time points
- Any groups that could not be analyzed (e.g., < 5 events — blocking threshold; < 10 events — warning for insufficient publication-quality data; Ref: Rich et al. 2010)

Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory: the directory containing this SKILL.md file.

### Step 8: Save Reusable Script

After presenting results, make the analysis **re-runnable** so the user can modify variables without re-triggering this skill:

1. Copy the Python script to the same directory as the output file:
```bash
cp ${CLAUDE_SKILL_DIR}/scripts/kaplan_meier.py <OUTPUT_DIR>/kaplan_meier.py
```

2. The JSON config file (from Step 4) is already saved alongside the output file.

3. Tell the user the following re-run instructions:
   - **Config file**: `<CONFIG_PATH>` (the JSON saved in Step 4)
   - **Script**: `<OUTPUT_DIR>/kaplan_meier.py`
   - **Re-run command**: `python <OUTPUT_DIR>/kaplan_meier.py <CONFIG_PATH>`
   - **Common modifications** (edit the config JSON directly):
     - Change time/event columns: edit `time_column`, `event_column`
     - Change time points: edit `time_points` array
     - Change grouping: edit the `grouping` object
     - Adjust plot: edit `plot_settings`
   - After editing, just ask Claude to run: `python <OUTPUT_DIR>/kaplan_meier.py <CONFIG_PATH>`

Replace `<OUTPUT_DIR>` with the directory containing the output xlsx file, and `<CONFIG_PATH>` with the actual config file path.

### Step 9: Record Learnings

Silently check whether any corrections occurred during this run:

1. **Column mapping corrections** — Did the user change any column names during Step 3 confirmation?
2. **Config modifications** — Did the user modify the auto-generated config in Step 4?
3. **QC warnings** — Were there any missing data warnings or unexpected data patterns?

If any corrections occurred, append a structured entry to `<OUTPUT_DIR>/learnings.md`:

```
## [YYYY-MM-DD] kaplan-meier run
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
  "derived_variables": [
    {
      "name": "BMI",
      "type": "expression",
      "expression": "Weight / (Height / 100) ** 2",
      "dependencies": ["Weight", "Height"]
    },
    {
      "name": "SBP",
      "type": "coalesce",
      "columns": ["SBP_Ad", "SBP_opd"]
    }
  ],
  "grouping": {
    "column": "AF_hx",
    "groups": [
      {"value": 1.0, "label": "AF"},
      {"value": 0.0, "label": "No AF"}
    ]
  },
  "time_column": "time_death",
  "event_column": "event_death",
  "time_unit": "years",
  "time_scale": 365.25,
  "time_points": [1, 3, 5],
  "plot_settings": {
    "confidence_interval": true,
    "censor_marks": true,
    "colors": ["#E74C3C", "#3498DB"],
    "x_max": null,
    "x_tick_interval": null,
    "y_min": 0.0,
    "number_at_risk": true,
    "risk_table_times": null,
    "legend_position": "best",
    "figsize": [8, 6],
    "dpi": 300
  },
  "title": "Kaplan-Meier Survival Analysis",
  "subtitle": "TSOC HF Registry — HFpEF Cohort",
  "output_file": "/absolute/path/to/KM_Survival.xlsx",
  "abbreviations": "KM = Kaplan-Meier; CI = confidence interval; AF = atrial fibrillation",
  "missing_data_handling": "listwise"
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `data_file` | Yes | Absolute path to the data file (xlsx or csv) |
| `filters` | No | Array of filter conditions applied before analysis |
| `derived_variables` | No | Array of new columns to compute |
| `grouping` | Yes | Defines the groups to compare (supports 2+ groups) |
| `time_column` | Yes | Column name for survival/follow-up time |
| `event_column` | Yes | Column name for event indicator (1=event, 0=censor) |
| `time_unit` | Yes | Time unit for axis labeling: `"days"`, `"months"`, or `"years"` |
| `time_scale` | No | Conversion factor applied to raw time values (default: `null` = no conversion) |
| `time_points` | Yes | Array of time points for survival rate reporting |
| `plot_settings` | No | Plot customization settings (see below) |
| `title` | No | Table/plot title |
| `subtitle` | No | Subtitle text |
| `output_file` | Yes | Output Excel path (.xlsx); PNG auto-generated with .png extension |
| `abbreviations` | Yes | Abbreviation footnote text |
| `missing_data_handling` | No | `"listwise"` (default) — exclude rows with missing time or event |

### Plot Settings

| Field | Default | Description |
|-------|---------|-------------|
| `confidence_interval` | `true` | Show 95% CI shading around survival curves |
| `censor_marks` | `true` | Show small vertical tick marks at censoring times |
| `colors` | auto | Array of colors for each group (auto-assigned if not specified) |
| `x_max` | `null` | Maximum x-axis value (`null` = auto from data) |
| `x_tick_interval` | `null` | X-axis tick interval (`null` = auto) |
| `y_min` | `0.0` | Minimum y-axis value |
| `number_at_risk` | `true` | Show number at risk table below plot |
| `risk_table_times` | `null` | Specific time points for the at-risk table (`null` = auto from x ticks) |
| `legend_position` | `"best"` | Legend location (matplotlib position string) |
| `figsize` | `[8, 6]` | Figure size in inches `[width, height]` |
| `dpi` | `300` | Plot resolution |

### Filter Operators

Supported: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

---

## Statistical Methods

### Kaplan-Meier Estimator
- Non-parametric estimator of the survival function using `lifelines.KaplanMeierFitter`.
- Survival probability at time t: S(t) = Π(1 − dᵢ/nᵢ) for all event times tᵢ ≤ t, where dᵢ = number of events, nᵢ = number at risk.
- 95% CI computed using the Greenwood formula (default in lifelines).

### Median Survival
- Time at which S(t) = 0.5 (with 95% CI from the survival function CI bands).
- If the survival curve does not cross 0.50, median is reported as "NR" (not reached).

### Survival Rates at Specified Time Points
- S(t) and 95% CI extracted from the KM fit at user-specified time points.
- If a time point exceeds the maximum follow-up time, it is reported as "N/A".

### Log-Rank Test
- For 2 groups: `lifelines.statistics.logrank_test` (standard log-rank / Mantel-Cox test).
- For 3+ groups: `lifelines.statistics.multivariate_logrank_test`.
- Tests the null hypothesis that survival curves are identical across groups.

### p-value Formatting
- `<0.001` for p < 0.001
- `x.xxx` for p ≥ 0.001 (3 decimal places)

---

## Output Description

### KM Plot (`.png`)
- Survival curves for each group with distinct colors and line styles
- Semi-transparent 95% CI shading (when enabled)
- Small vertical tick marks at censoring times (when enabled)
- X-axis: "Time ({time_unit})", Y-axis: "Survival Probability"
- Log-rank test p-value displayed on the plot
- Legend with group labels
- Number at risk table below the plot, aligned with x-axis ticks
- Publication-ready: 300 DPI, clean fonts, proper spacing

### Excel File (`.xlsx`)

#### Sheet 1: "Survival Summary"
- **Row 1**: Title (dark blue background, white text)
- **Row 2**: Subtitle with total sample size
- **Row 3**: Column headers — Group | N | Events (%) | Median Survival (95% CI) | Survival rates at each time point
- **Data rows**: One per group with alternating shading
- **Footnotes**: Log-rank test p-value, abbreviations, statistical method notes

#### Sheet 2: "Log-Rank Test"
- **Row 1**: Title (dark blue background, white text)
- **Row 2**: Comparison details
- **Data**: Test statistic, degrees of freedom, p-value
- **Footnotes**: Method description

---

## Example Usage

**User**: "I want to draw KM survival curves for HFpEF patients comparing AF vs No AF. Data is in TSOC_data_merge.xlsx, filter for HF_type==3, group by AF_hx (1=AF, 0=No AF). Time variable: time_death (in days, convert to years with 365.25). Event variable: event_death. Show 1-year, 3-year, and 5-year survival rates. Include number at risk table."

**Claude's response**: Generates the JSON config, runs missing data check, presents results, then generates the KM plot PNG and formatted Excel with survival summary and log-rank test results.

---

## Pipeline Integration

When called from the `research-plan` orchestrator pipeline:

- Config is pre-generated at `configs/{step_id}_config.json` by `generate_configs.py`
- Skip Steps 1–4 (interactive interview + column confirmation); proceed directly to Step 5 (check missing data) and Step 6 (execute)
- Exit code 0 = success, non-zero = failure (triggers retry then error in pipeline)
- QC warnings are emitted to stderr with `[QC_WARNING]` prefix for pipeline collection
- QC blocking issues are emitted to stderr with `[QC_BLOCKING]` prefix (step marked as error)

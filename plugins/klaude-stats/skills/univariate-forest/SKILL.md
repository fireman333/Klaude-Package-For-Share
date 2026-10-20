---
name: univariate-forest
description: "univariate-forest: runs univariate regression (Cox→HR or Logistic→OR) for Overall/Group X/Group Non-X, outputs a formatted Excel summary + publication-ready forest plot (truncated x-axis). Trigger: univariate analysis, forest plot, HR forest, OR forest, univariate Cox, univariate logistic, unadjusted analysis, crude analysis, univariable, single variable regression, unadjusted HR, unadjusted OR, 單變量分析, 森林圖, 單變量迴歸, 做單變量, 畫森林圖, 未校正分析, 單因子分析, 幫我做單變量分析, draw a forest plot, 做未校正分析."
---

# Univariate Analysis + Forest Plot Generator

Run univariate regression (Cox PH for time-to-event → HR, or logistic for binary outcome → OR) across 3 populations (Overall, Group X, Group Non-X), output a formatted Excel summary table, and generate a publication-ready forest plot.

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 0: Context Recovery

Before gathering requirements, check for existing upstream context:

1. Search the working directory (and parent directories up to 2 levels) for `research_plan.json`
2. If found, read it and extract relevant fields for this skill:
   - `study.data_file` → Data file path
   - `population.filters` → Data filters
   - `grouping` → Grouping variable (Group X and Group Non-X), values and labels
   - `outcomes` → Match the outcome to extract: analysis type (cox/logistic), time_column, event_column, or outcome_column
   - `covariates` → Variable list (name, column, type, scale, scale_label)
   - `derived_variables` → Derived variables (including composite endpoints)
3. Present the pre-filled config to the user: "Found research plan — using these settings:" followed by a concise summary
4. Ask user to confirm or modify, then skip to Step 2
5. If no `research_plan.json` found, also check for a `learnings.md` in the working directory — if present, read column mapping corrections and apply them as defaults
6. Check for `diagnostic_report.json` in `{working_dir}/diagnostics/` or `{working_dir}/`. If found, read it and apply the per-skill integration rules in `${CLAUDE_SKILL_DIR}/../survival-diagnostics/references/downstream_integration.md` (`/univariate-forest` section). Key actions: warn if `recommended_primary="competing-risk"` (HR will mix events); auto-add `+ cluster(cluster_variable)` to Cox fits if `checks.clustering.detected=true`.

If no upstream context is found, proceed to Step 1.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Data file path** — xlsx, csv, or other pandas-readable format
2. **Data filters** (optional) — conditions to subset the data before analysis (e.g., `HF_type == 3`)
3. **Derived variables** (optional) — new columns to compute before analysis:
   - `coalesce` type: pick the first non-null from a list of columns
   - `expression` type: compute from existing columns (e.g., BMI = Weight / (Height/100)^2)
4. **Grouping variable** — the column name that defines the two subgroups, plus:
   - Value and label for Group X (e.g., value=1.0, label="AF")
   - Value and label for Group Non-X (e.g., value=0.0, label="No AF")
5. **Composite endpoint** — If analysis type is `cox`, ask whether the user wants to analyze a **composite endpoint (time to first event of death OR hospitalization)**. If yes:
   - If the data already has composite columns, use them directly as `time_column` and `event_column`.
   - If not, offer to derive them via `derived_variables`:
     - `time_composite`: `expression` type — `np.minimum(time_death, time_hosp)` (takes the earlier of the two)
     - `event_composite`: `expression` type — `np.where((event_death == 1) | (event_hosp == 1), 1, 0)`
   - Always confirm which death and hospitalization columns exist before deriving.
6. **Analysis type**: `"cox"` (time-to-event → HR) or `"logistic"` (binary outcome → OR)
7. **For cox**: `time_column` and `event_column` names
   **For logistic**: `outcome_column` name
8. **Variable list** — organized by section, each variable needs:
   - Display label (e.g., "Age (per 10 yrs)")
   - Column name in the data
   - Type: `continuous` or `binary`
   - For continuous with scaling: `scale` (number) and `scale_label` (string, e.g., "per 10 yrs")
9. **Output file path** (base name; script generates `.xlsx` and `.png`)
10. **Table title and subtitle** (optional)
11. **Abbreviations** — full forms of all abbreviations used in the table (e.g., "HR = hazard ratio; CI = confidence interval; AF = atrial fibrillation"). This will appear as a footnote at the bottom of the Excel table. Always collect this from the user to ensure the table is publication-ready.

### Step 2: Validate Data

Before generating the config, read the data file to confirm:
- The file exists and is readable
- All specified columns exist
- The grouping variable contains the expected values
- For cox mode: time and event columns exist and have valid data

Run a quick Python snippet:
```python
import pandas as pd
df = pd.read_excel("path")  # or read_csv
print(f"Shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
print(f"Group column values: {df['group_col'].value_counts()}")
```

### Step 3: Confirm Column Mapping (欄位確認)

在產生設定檔之前，先將使用者描述的變數與實際 Excel 欄位名稱整理成對應表，確保沒有對應錯誤。

根據 Steps 1–2 收集到的資訊，建立以下表格：

| 使用者描述 | 對應欄位名稱 | 資料類型 | 角色 |
|-----------|-------------|---------|------|
| 有無 AF       | `AF_hx`          | binary     | 分組變數 (grouping)   |
| 追蹤時間       | `time_composite` | continuous | 時間變數 (time)       |
| 複合事件       | `event_composite`| binary     | 事件變數 (event)      |
| 年齡 (每10歲) | `age`            | continuous | 分析變數 (covariate)  |
| 糖尿病        | `DM_hx`          | binary     | 分析變數 (covariate)  |

*(以上為範例，實際內容依使用者需求填入)*

**規則：**
1. 列出所有使用者提及的變數：分組、時間/事件（或結局）、分析變數、篩選條件、衍生變數
2. 衍生變數顯示推導方式（如 `BMI ← Weight/(Height/100)²`）
3. 篩選條件顯示完整條件（如 `HF_type == 3`）
4. 若使用者用口語中文描述（如「糖尿病」），顯示對應的實際欄位名稱（如 `DM_hx`）
5. 若無法確定對應欄位，列出前 3 個候選欄位請使用者選擇

呈現表格後詢問：

> 以上欄位對應是否正確？如有需要修正請告知，確認後將進入設定檔產生。

**使用者確認前不得進入 Step 4。** 若使用者修正了任何對應，更新後重新呈現確認。

> **Guardian 註記**：若本 skill 由 `research-plan` orchestrator 呼叫且 `research_plan.json$.guardian.mode != "off"`，使用者確認後 orchestrator 會自動派 `biostats-guardian` Role 1 (Column Auditor) subagent 對 config 做獨立稽核（COL-001..011）。直接呼叫本 skill 時不會觸發。

### Step 4: Generate JSON Config

Write a JSON config file **alongside the output file**, using the same base name with `_config.json` suffix (e.g., if `output_file` is `/path/to/Univariate_Forest.xlsx`, save config as `/path/to/Univariate_Forest_config.json`). This ensures the config persists for future re-runs. The schema is documented below.

### Step 5: Check Missing Data

Run the script in missing-data-check mode:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/univariate_forest.py /tmp/univariate_forest_config.json --check-missing
```

This prints a report showing missing counts and percentages for every variable across all 3 populations (Overall, Group X, Group Non-X). Present the report to the user. If there are missing values, ask how they want to handle them:
- **Listwise deletion** (default): exclude any row with any missing value across all variables (complete case analysis)
- **Pairwise deletion**: each regression uses all available data for that variable
- **Other**: let the user specify

If all variables have zero missing values, report this and proceed.

### Step 6: Execute Analysis

Run the full script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/univariate_forest.py /tmp/univariate_forest_config.json
```

This produces an Excel file (`.xlsx`) and a forest plot image (`.png`).

### Step 7: Present Results

After execution, tell the user:
- Output file locations (xlsx and png)
- Total sample size and per-group sizes (with event counts for cox)
- Number of statistically significant variables (p < 0.05) per population
- Any variables that could not be analyzed (convergence failures)

Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory: the directory containing this SKILL.md file.

### Step 8: Save Reusable Script

After presenting results, make the analysis **re-runnable** so the user can modify variables without re-triggering this skill:

1. Copy the Python script to the same directory as the output file:
```bash
cp ${CLAUDE_SKILL_DIR}/scripts/univariate_forest.py <OUTPUT_DIR>/univariate_forest.py
```

2. The JSON config file (from Step 4) is already saved alongside the output file.

3. Tell the user the following re-run instructions:
   - **Config file**: `<CONFIG_PATH>` (the JSON saved in Step 4)
   - **Script**: `<OUTPUT_DIR>/univariate_forest.py`
   - **Re-run command**: `python <OUTPUT_DIR>/univariate_forest.py <CONFIG_PATH>`
   - **Common modifications** (edit the config JSON directly):
     - Add/remove variables: edit the `sections` array
     - Change grouping: edit the `grouping` object
     - Change analysis type: edit `analysis_type` and `cox_settings`/`logistic_settings`
     - Change data filters: edit the `filters` array
   - After editing, just ask Claude to run: `python <OUTPUT_DIR>/univariate_forest.py <CONFIG_PATH>`

Replace `<OUTPUT_DIR>` with the directory containing the output xlsx file, and `<CONFIG_PATH>` with the actual config file path.

### Step 9: Record Learnings

Silently check whether any corrections occurred during this run:

1. **Column mapping corrections** — Did the user change any column names during Step 3 confirmation?
2. **Config modifications** — Did the user modify the auto-generated config in Step 4?
3. **QC warnings** — Were there any missing data warnings or unexpected data patterns?

If any corrections occurred, append a structured entry to `<OUTPUT_DIR>/learnings.md`:

```
## [YYYY-MM-DD] univariate-forest run
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
  "analysis_type": "cox",
  "cox_settings": {
    "time_column": "time_composite",
    "event_column": "event_composite",
    "cluster_col": null
  },
  "logistic_settings": {
    "outcome_column": "event_death"
  },
  "sections": [
    {
      "header": "Demographics",
      "variables": [
        {"label": "Age (per 10 yrs)", "column": "age", "type": "continuous", "scale": 10, "scale_label": "per 10 yrs"},
        {"label": "Male sex", "column": "gender", "type": "binary"},
        {"label": "Hypertension", "column": "HTN_hx", "type": "binary"}
      ]
    }
  ],
  "title": "Univariate Cox Regression — HFpEF Cohort",
  "subtitle": "TSOC HF Registry",
  "output_file": "/absolute/path/to/Univariate_Forest.xlsx",
  "abbreviations": "HR = hazard ratio; CI = confidence interval; ...",
  "missing_data_handling": "listwise",
  "forest_plot": {
    "format": "png",
    "dpi": 300,
    "truncation_method": "auto",
    "truncation_range": null
  }
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `data_file` | Yes | Absolute path to the data file (xlsx or csv) |
| `filters` | No | Array of filter conditions applied before analysis |
| `derived_variables` | No | Array of new columns to compute |
| `grouping` | Yes | Defines the two subgroups (Group X and Group Non-X) |
| `analysis_type` | Yes | `"cox"` for HR or `"logistic"` for OR |
| `cox_settings` | If cox | Time and event column names; optional `cluster_col` for cluster-robust SE (P-7 audit fix 2026-05-07) |
| `cox_settings.cluster_col` | No | Column name for clustering (multi-center / family / repeated-measures). When set, fit uses `robust=True, cluster_col=...` for cluster-robust standard errors. Auto-prefilled by `survival-diagnostics` `diagnostic_report.json` when clustering is detected. |
| `logistic_settings` | If logistic | Outcome column name |
| `sections` | Yes | Array of variable sections, each with a header and variables |
| `title` | No | Table title (Row 1 in Excel) |
| `subtitle` | No | Subtitle text (Row 2 in Excel) |
| `output_file` | Yes | Output Excel path (PNG auto-generated with .png extension) |
| `abbreviations` | Yes | Abbreviation footnote text (full forms of all abbreviations) |
| `missing_data_handling` | No | `"listwise"` (default, and the only value the script implements) — global complete-case deletion across all model variables. `"pairwise"` is **not** supported: pairwise deletion in a regression leaves every coefficient with a different N, so the model is not internally consistent. Any other value falls through to available-case behaviour and is not a supported configuration. (`table1`'s default is `"available"` — per-variable available-case, the convention for a baseline table but not for a fitted model.) **Real missing-data handling goes through `/research-plan`'s `missingness` and `mi_{outcome}` steps (multiple imputation); the listwise run here is that step's complete-case comparator, not a substitute for it.** |
| `forest_plot` | No | Forest plot settings (auto truncation by default) |

### Filter Operators

Supported: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

### Variable Types

- **continuous**: Numeric variable. If `scale` is provided, the variable is divided by the scale value before regression (e.g., age/10 → HR per 10 years).
- **binary**: 0/1 or True/False variable. Used as-is in regression.

### Forest Plot Settings

| Field | Default | Description |
|-------|---------|-------------|
| `format` | `"png"` | Output format: `"png"` or `"pdf"` |
| `dpi` | `300` | Resolution for PNG output |
| `truncation_method` | `"auto"` | `"auto"` computes from data; `"manual"` uses `truncation_range` |
| `truncation_range` | `null` | `[lower, upper]` for manual truncation |

---

## Statistical Methods

| Analysis Type | Model | Effect Measure | Interpretation |
|--------------|-------|----------------|----------------|
| Time-to-event (`cox`) | Cox proportional hazards (lifelines) | HR (95% CI) | HR > 1 = higher risk |
| Binary outcome (`logistic`) | Logistic regression (statsmodels) | OR (95% CI) | OR > 1 = higher odds |

**Minimum thresholds**: n ≥ 10 and events ≥ 5, otherwise the variable is marked as "N/A".

**p-value formatting**: `<0.001*` for p < 0.001, `x.xxx*` for p < 0.05, `x.xxx` for p ≥ 0.05.

---

## Output Description

### Excel Table
- **Row 1**: Title (dark blue background)
- **Row 2**: Subtitle with sample sizes
- **Row 3-4**: Column headers — Variable | [N (events) | HR/OR (95% CI) | p-value] × 3 populations
- **Data rows**: Section headers (light blue) followed by variable rows with alternating shading
- **Footnotes**: Abbreviations and statistical notes

### Forest Plot
- Single combined plot with 3 sub-rows per variable
- Overall = blue circle, Group X = orange square, Group Non-X = green triangle
- Log-scale x-axis with reference line at 1.0
- Auto-truncated x-axis with arrow indicators for clipped CIs
- Section headers as bold labels with separator lines
- Legend at top

---

## Example Usage

**User**: "I want to run univariate Cox regression for HFpEF patients, comparing AF vs No AF. Data is in TSOC_data_merge.xlsx, filter for HF_type==3, group by AF_hx. Time variable: time_composite, event: event_composite. Variables: age (per 10 yrs), gender, BMI (per 5), HTN_hx, DM_hx, LVEF. Generate forest plot."

**Claude's response**: Generates the JSON config, runs missing data check, presents results, then generates the formatted Excel table + forest plot PNG.

---

## Pipeline Integration

When called from the `research-plan` orchestrator pipeline:

- Config is pre-generated at `configs/{step_id}_config.json` by `generate_configs.py`
- Skip Steps 1–4 (interactive interview + column confirmation); proceed directly to Step 5 (check missing data) and Step 6 (execute)
- Exit code 0 = success, non-zero = failure (triggers retry then error in pipeline)
- QC warnings are emitted to stderr with `[QC_WARNING]` prefix for pipeline collection
- QC blocking issues are emitted to stderr with `[QC_BLOCKING]` prefix (step marked as error)

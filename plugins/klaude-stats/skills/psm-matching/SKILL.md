---
name: psm-matching
description: "PSM analysis. Trigger: propensity score matching, PSM, matched analysis, propensity score, caliper matching, PS matching, matched cohort analysis, 1:1 matching, propensity matching, love plot, SMD, standardized mean difference, balance assessment, 傾向分數配對, PSM分析, 做PSM, 傾向分數分析, PS配對, PS配對分析, 傾向分數配對分析, 幫我做PSM, run propensity score matching, 做傾向分數配對分析; bare '配對分析' needs context."
---

# Propensity Score Matching (PSM) Analysis

Perform propensity score matching using greedy nearest-neighbor on logit(PS), then analyze outcomes (Cox HR or Logistic OR) on the matched cohort. Produces three outputs: an outcome table, a balance table with SMD, and a Love plot.

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 0: Context Recovery

Before gathering requirements, check for existing upstream context:

1. Search the working directory (and parent directories up to 2 levels) for `research_plan.json`
2. If found, read it and extract relevant fields for this skill:
   - `study.data_file` → Data file path
   - `population.filters` → Data filters
   - `grouping` → Grouping variable (treatment vs control), values and labels
   - `covariates` → Matching variables (name, column, type) — these become both PS estimation variables and balance table variables
   - `outcomes` → Outcomes array for post-matching analysis (each with type, time/event/outcome columns)
   - `derived_variables` → Derived variables (including composite endpoints)
3. Present the pre-filled config to the user: "Found research plan — using these settings:" followed by a concise summary
4. Ask user to confirm or modify, then skip to Step 2
5. If no `research_plan.json` found, also check for a `learnings.md` in the working directory — if present, read column mapping corrections and apply them as defaults

If no upstream context is found, proceed to Step 1.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Data file path** — xlsx, csv, or other pandas-readable format
2. **Data filters** (optional) — conditions to subset the data before analysis (e.g., `HF_type == 3`)
3. **Derived variables** (optional) — new columns to compute before analysis:
   - `coalesce` type: pick the first non-null from a list of columns
   - `expression` type: compute from existing columns (e.g., BMI = Weight / (Height/100)^2)
4. **Grouping variable** — the column name that defines treatment vs. control, plus:
   - Value and label for Group 1 / Treatment (e.g., value=1.0, label="AF")
   - Value and label for Group 2 / Control (e.g., value=0.0, label="No AF")
5. **Matching variables** — organized by section, each variable needs:
   - Display label (e.g., "Age (years)")
   - Column name in the data
   - Type: `continuous` or `binary`
   - These variables are used BOTH for propensity score estimation AND for the balance table
6. **PSM parameters**:
   - Caliper: enabled (boolean, default `true`), width (float, default `0.20`) — applied as width × std(logit_PS)
   - Ratio: integer N for 1:N matching (default `1`)
7. **Analysis type**: `"cox"` (time-to-event → HR) or `"logistic"` (binary outcome → OR)
8. **Composite endpoint** — If analysis type is `cox`, ask whether the user wants to include a **composite endpoint (time to first event of death OR hospitalization)** among the outcomes. If yes:
   - If the data already has composite columns, add them as an outcome directly.
   - If not, offer to derive them via `derived_variables`:
     - `time_composite`: `expression` type — `np.minimum(time_death, time_hosp)` (takes the earlier of the two)
     - `event_composite`: `expression` type — `np.where((event_death == 1) | (event_hosp == 1), 1, 0)`
   - Always confirm which death and hospitalization columns exist before deriving.
9. **Outcomes** — array of outcomes to analyze after matching, each with:
   - Display label (e.g., "All-cause mortality", "Death or HF hospitalization")
   - For cox: `event_column` and `time_column`
   - For logistic: `outcome_column`
10. **Output file path** (base name; script generates .xlsx and _loveplot.png)
11. **Table title and subtitle** (optional)
12. **Abbreviations** (optional) — for the footnote at the bottom of tables

### Step 2: Validate Data

Before generating the config, read the data file to confirm:
- The file exists and is readable
- All specified columns exist
- The grouping variable contains the expected values

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
| 有無 AF        | `AF_hx`                  | binary        | 分組變數 (grouping)  |
| 年齡           | `age`                    | continuous    | 配對變數 (matching)  |
| 糖尿病         | `DM_hx`                  | binary        | 配對變數 (matching)  |
| 全死因死亡      | `event_death`/`time_death`| time-to-event | 結局變數 (outcome)   |

*(以上為範例，實際內容依使用者需求填入)*

**規則：**
1. 列出所有使用者提及的變數：分組、配對變數、結局變數（時間/事件或二元）、篩選條件、衍生變數
2. 衍生變數顯示推導方式（如 `BMI ← Weight/(Height/100)²`）
3. 篩選條件顯示完整條件（如 `HF_type == 3`）
4. 若使用者用口語中文描述（如「糖尿病」），顯示對應的實際欄位名稱（如 `DM_hx`）
5. 若無法確定對應欄位，列出前 3 個候選欄位請使用者選擇

呈現表格後詢問：

> 以上欄位對應是否正確？如有需要修正請告知，確認後將進入設定檔產生。

**使用者確認前不得進入 Step 4。** 若使用者修正了任何對應，更新後重新呈現確認。

> **Guardian 註記**：若本 skill 由 `research-plan` orchestrator 呼叫且 `research_plan.json$.guardian.mode != "off"`，使用者確認後 orchestrator 會自動派 `biostats-guardian` Role 1 (Column Auditor) subagent 對 config 做獨立稽核（COL-001..011）。直接呼叫本 skill 時不會觸發。

### Step 4: Generate JSON Config

Write a JSON config file **alongside the output file**, using the same base name with `_config.json` suffix (e.g., if `output_file` is `/path/to/PSM_Analysis.xlsx`, save config as `/path/to/PSM_Analysis_config.json`). This ensures the config persists for future re-runs. The schema is documented below.

### Step 5: Check Missing Data

Run the script in missing-data-check mode:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/psm_matching.py /tmp/psm_matching_config.json --check-missing
```

This prints a report showing missing counts and percentages for every matching variable and outcome variable, per group. It also reports the **effective sample size after listwise deletion** (rows where all matching variables are non-missing), because PSM requires complete cases across all matching variables simultaneously.

Present the report to the user. If there are missing values, ask how they want to handle them:
- **Listwise deletion** (default): exclude any row with any missing value across all matching variables
- **Other**: let the user specify

If all variables have zero missing values, report this and proceed.

### Step 6: Execute Analysis

Run the full script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/psm_matching.py /tmp/psm_matching_config.json
```

This produces:
- Excel file (`.xlsx`) with two sheets (Outcome Analysis + Balance Assessment)
- Love plot image (`_loveplot.png`)

### Step 7: Present Results

After execution, tell the user:
- Output file locations (xlsx and png)
- Original sample sizes per group (before matching)
- Matched sample sizes per group (after matching)
- Number of unmatched treatment subjects (if any)
- Caliper used (value and whether it was enabled)
- Number of significant outcomes (p < 0.05)
- Any outcomes that could not be analyzed

Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory: the directory containing this SKILL.md file.

### Step 8: Save Reusable Script

After presenting results, make the analysis **re-runnable** so the user can modify variables without re-triggering this skill:

1. Copy the Python script to the same directory as the output file:
```bash
cp ${CLAUDE_SKILL_DIR}/scripts/psm_matching.py <OUTPUT_DIR>/psm_matching.py
```

2. The JSON config file (from Step 4) is already saved alongside the output file.

3. Tell the user the following re-run instructions:
   - **Config file**: `<CONFIG_PATH>` (the JSON saved in Step 4)
   - **Script**: `<OUTPUT_DIR>/psm_matching.py`
   - **Re-run command**: `python <OUTPUT_DIR>/psm_matching.py <CONFIG_PATH>`
   - **Common modifications** (edit the config JSON directly):
     - Add/remove matching variables: edit `matching_variables` sections
     - Add/remove outcomes: edit the `outcomes` array
     - Change caliper/ratio: edit `matching` object
     - Change grouping: edit the `grouping` object
   - After editing, just ask Claude to run: `python <OUTPUT_DIR>/psm_matching.py <CONFIG_PATH>`

Replace `<OUTPUT_DIR>` with the directory containing the output xlsx file, and `<CONFIG_PATH>` with the actual config file path.

### Step 9: Record Learnings

Silently check whether any corrections occurred during this run:

1. **Column mapping corrections** — Did the user change any column names during Step 3 confirmation?
2. **Config modifications** — Did the user modify the auto-generated config in Step 4?
3. **QC warnings** — Were there any missing data warnings or unexpected data patterns?

If any corrections occurred, append a structured entry to `<OUTPUT_DIR>/learnings.md`:

```
## [YYYY-MM-DD] psm-matching run
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
  "matching": {
    "caliper": {
      "enabled": true,
      "width": 0.20
    },
    "ratio": 1
  },
  "matching_variables": [
    {
      "header": "Demographics",
      "variables": [
        {"label": "Age (years)", "column": "age", "type": "continuous"},
        {"label": "Male sex", "column": "gender", "type": "binary"},
        {"label": "Hypertension", "column": "HTN_hx", "type": "binary"}
      ]
    }
  ],
  "analysis_type": "cox",
  "outcomes": [
    {
      "label": "All-cause mortality",
      "event_column": "event_death",
      "time_column": "time_death"
    },
    {
      "label": "Unplanned HF hospitalization",
      "event_column": "event_hf_hosp",
      "time_column": "time_hf_hosp"
    }
  ],
  "title": "Propensity Score Matched Analysis",
  "subtitle": "TSOC HF Registry — HFpEF Cohort",
  "output_file": "/absolute/path/to/PSM_Analysis.xlsx",
  "abbreviations": "PSM = propensity score matching; HR = hazard ratio; CI = confidence interval; SMD = standardized mean difference",
  "missing_data_handling": "listwise"
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `data_file` | Yes | Absolute path to the data file (xlsx or csv) |
| `filters` | No | Array of filter conditions applied before analysis |
| `derived_variables` | No | Array of new columns to compute |
| `grouping` | Yes | Defines treatment (Group 1) vs. control (Group 2) |
| `matching` | No | PSM parameters (caliper and ratio) |
| `matching.caliper.enabled` | No | Whether to use caliper (default: `true`) |
| `matching.caliper.width` | No | Caliper width as multiplier of std(logit_PS) (default: `0.20`) |
| `matching.ratio` | No | N for 1:N matching (default: `1`) |
| `matching_variables` | Yes | Array of variable sections for PS estimation and balance table |
| `analysis_type` | Yes | `"cox"` for HR or `"logistic"` for OR |
| `outcomes` | Yes | Array of outcome definitions |
| `title` | No | Table title (Row 1 in Excel) |
| `subtitle` | No | Subtitle text (Row 2 in Excel) |
| `output_file` | Yes | Output Excel path (.xlsx); Love plot saved as same base + `_loveplot.png` |
| `abbreviations` | No | Abbreviation footnote text |
| `missing_data_handling` | No | `"listwise"` (default) — applied to matching variables |

### Filter Operators

Supported: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

### Variable Types (Matching Variables)

- **continuous**: Numeric variable. Used as-is in logistic regression for PS estimation. Balance reported as mean ± SD with SMD.
- **binary**: 0/1 or True/False. Used as-is in logistic regression for PS estimation. Balance reported as proportion (%) with SMD.

### Outcome Definitions

For `analysis_type: "cox"`:
```json
{"label": "All-cause mortality", "event_column": "event_death", "time_column": "time_death"}
```

For `analysis_type: "logistic"`:
```json
{"label": "In-hospital mortality", "outcome_column": "death_inhosp"}
```

---

## Statistical Methods

### Propensity Score Estimation
- Logistic regression via **statsmodels.api.Logit** (no regularization, default IRLS / Newton-Raphson convergence; standard errors are model-based, not bootstrap or robust). Treatment indicator is the target; all `matching_variables` are features.
- **Convergence**: defaults to `maxiter=35, method='newton'`. Perfect-separation will trigger statsmodels `PerfectSeparationError` — currently not caught (silent NaN in PS column); the audit P-7 fix (2026-05-07) updates this doc to match the actual implementation; convergence-failure handling is a separate open issue.
- Logit transformation: `logit(PS) = log(PS / (1 - PS))` with clipping to [1e-6, 1-1e-6].
- **Why statsmodels (not sklearn)**: statsmodels Logit gives unregularized MLE (sklearn's LogisticRegression defaults to L2 regularization with `C=1.0`, which shrinks coefficients away from MLE). For propensity scores you want the unregularized MLE so the PS is a valid probability conditional on confounders.

### Matching Algorithm
- Greedy nearest-neighbor matching on logit(PS), without replacement.
- Caliper (when enabled): only considers controls within `width × std(logit_PS)` of each treatment subject.
- For 1:N matching: selects up to N nearest controls per treatment subject.
- Assigns a stratum ID to each matched pair/set for subsequent stratified analysis.

### SMD (Standardized Mean Difference)
| Variable Type | Formula |
|--------------|---------|
| Continuous | \|mean_t − mean_c\| / sqrt((var_t + var_c) / 2) |
| Binary | \|prop_t − prop_c\| / sqrt((p_t(1−p_t) + p_c(1−p_c)) / 2) |

SMD < 0.1 is considered good balance.

### Outcome Analysis (Post-Matching)
| Analysis Type | Model | Effect Measure |
|--------------|-------|----------------|
| Time-to-event (`cox`) | Stratified Cox PH (lifelines, strata=matched pair) | HR (95% CI) |
| Binary outcome (`logistic`) | Conditional logistic regression (statsmodels) | OR (95% CI) |

**Minimum thresholds**: n ≥ 10 and events ≥ 5, otherwise the outcome is marked as "N/A".

**p-value formatting**: `<0.001*` for p < 0.001, `x.xxx*` for p < 0.05, `x.xxx` for p ≥ 0.05.

---

## Output Description

### Sheet 1: "Outcome Analysis"
- **Row 1**: Title (dark blue background, white text)
- **Row 2**: Subtitle with matched sample sizes and matching parameters
- **Row 3**: Column headers — Outcome | Treatment N (events) | Control N (events) | HR/OR (95% CI) | p-value
- **Data rows**: One per outcome with alternating shading
- **Footnotes**: Abbreviations and statistical method notes

### Sheet 2: "Balance Assessment"
- **Row 1**: Title (dark blue background, white text)
- **Row 2**: Subtitle with original and matched N per group
- **Row 3-4**: Two-level column headers — Variable | Before Matching (Treatment Mean, Control Mean, SMD) | After Matching (Treatment Mean, Control Mean, SMD)
- **Data rows**: Section headers (light blue) followed by variable rows with alternating shading; SMD ≥ 0.1 in bold red
- **Footnotes**: Abbreviations and SMD threshold note

### Love Plot (`_loveplot.png`)
- X-axis: Absolute Standardized Mean Difference
- Y-axis: Variable labels grouped by section
- Red circles: SMD before matching
- Blue squares: SMD after matching
- Vertical dashed line at SMD = 0.1 (threshold)
- Gray connecting lines between before/after for each variable
- 300 DPI PNG

---

## Example Usage

**User**: "I want to do PSM for HFpEF patients comparing AF vs No AF. Data is in TSOC_data_merge.xlsx, filter for HF_type==3, group by AF_hx (1=AF, 0=No AF). Matching variables: age, gender, BMI, HTN_hx, DM_hx, LVEF. Use caliper 0.20, 1:1 matching. This is time-to-event data — outcomes are all-cause mortality (event_death, time_death) and HF hospitalization (event_hf_hosp, time_hf_hosp)."

**Claude's response**: Generates the JSON config, runs missing data check, presents results, then generates the formatted Excel (outcome table + balance table) and Love plot.

---

## Pipeline Integration

When called from the `research-plan` orchestrator pipeline:

- Config is pre-generated at `configs/{step_id}_config.json` by `generate_configs.py`
- Skip Steps 1–4 (interactive interview + column confirmation); proceed directly to Step 5 (check missing data) and Step 6 (execute)
- Exit code 0 = success, non-zero = failure (triggers retry then error in pipeline)
- QC warnings are emitted to stderr with `[QC_WARNING]` prefix for pipeline collection
- QC blocking issues are emitted to stderr with `[QC_BLOCKING]` prefix (step marked as error)

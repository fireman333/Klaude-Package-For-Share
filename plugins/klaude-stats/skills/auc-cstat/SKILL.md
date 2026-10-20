---
name: auc-cstat
description: "auc-cstat: AUC (logistic, binary) or C-index (Cox PH, time-to-event); discrimination alone + incremental value vs clinical model (delta+p). Trigger: AUC, C-statistics, C-index, c-statistic, concordance index, ROC analysis, ROC AUC, discrimination, incremental discrimination, delta AUC, delta C-index, predictive performance, model discrimination, Harrell C-index, DeLong test, area under curve, AUC分析, C統計量, 預測能力, 區分能力, 做AUC, 做C-index, 鑑別力分析, 預測模型評估, 算C統計量, 幫我算AUC, 做C-statistics分析, compute discrimination, 做AUC分析, 做鑑別力分析."
---

# AUC / C-Statistics Discrimination Analysis

Evaluate the discriminative performance (AUC or C-index) of individual variables, with optional comparison against a baseline clinical model. For binary outcomes, compute AUC via logistic regression with DeLong test for comparison. For time-to-event outcomes, compute C-index via Cox PH with bootstrap comparison.

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 0: Context Recovery

Before gathering requirements, check for existing upstream context:

1. Search the working directory (and parent directories up to 2 levels) for `research_plan.json`
2. If found, read it and extract relevant fields for this skill:
   - `study.data_file` → Data file path
   - `population.filters` → Data filters
   - `outcomes` → Match the outcome to extract: analysis type (cox/logistic), time_column, event_column, or outcome_column
   - `covariates` → Variables to evaluate (name, column, type, scale, scale_label)
   - `derived_variables` → Derived variables
3. Present the pre-filled config to the user: "Found research plan — using these settings:" followed by a concise summary
4. Ask user to confirm or modify, then skip to Step 2
5. If no `research_plan.json` found, also check for a `learnings.md` in the working directory — if present, read column mapping corrections and apply them as defaults

If no upstream context is found, proceed to Step 1.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Data file path** -- xlsx, csv, or other pandas-readable format
2. **Data filters** (optional) -- conditions to subset the data before analysis (e.g., `HF_type == 3`)
3. **Derived variables** (optional) -- new columns to compute before analysis:
   - `coalesce` type: pick the first non-null from a list of columns
   - `expression` type: compute from existing columns (e.g., BMI = Weight / (Height/100)^2)
4. **Analysis type**: `"cox"` (time-to-event → C-index) or `"logistic"` (binary outcome → AUC)
5. **For cox**: `time_column` and `event_column` names
   **For logistic**: `outcome_column` name
6. **Variables to evaluate** -- organized by section, each variable needs:
   - Display label (e.g., "LAVi (per 10 mL/m²)")
   - Column name in the data
   - Type: `continuous` or `binary`
   - For continuous with scaling: `scale` (number) and `scale_label` (string, e.g., "per 10 mL/m²")
7. **Clinical model variables** (optional) -- a set of clinical parameters that form the baseline model for comparison. Each needs: label, column, type, optional scale. If provided, the output table includes columns for clinical model alone, clinical model + variable, delta, and p-value.
8. **Bootstrap settings** (optional, for cox only) -- number of iterations (default: 1000) and random seed (default: 42)
9. **Output file path** (base name; script generates `.xlsx`)
10. **Table title and subtitle** (optional)
11. **Abbreviations** -- full forms of all abbreviations used in the table (e.g., "AUC = area under the receiver operating characteristic curve; C-index = concordance index"). Always collect this from the user to ensure the table is publication-ready.

### Step 2: Validate Data

Before generating the config, read the data file to confirm:
- The file exists and is readable
- All specified columns exist (evaluation variables + clinical model variables + outcome/time columns)
- For cox mode: time and event columns exist and have valid data
- For logistic mode: outcome column exists and is binary

Run a quick Python snippet:
```python
import pandas as pd
df = pd.read_excel("path")  # or read_csv
print(f"Shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
# Check outcome/time columns
```

### Step 3: Confirm Column Mapping (欄位確認)

在產生設定檔之前，先將使用者描述的變數與實際 Excel 欄位名稱整理成對應表，確保沒有對應錯誤。

根據 Steps 1–2 收集到的資訊，建立以下表格：

| 使用者描述 | 對應欄位名稱 | 資料類型 | 角色 |
|-----------|-------------|---------|------|
| 追蹤時間  | `time_composite`  | continuous | 時間變數 (time)              |
| 複合事件  | `event_composite` | binary     | 事件變數 (event)             |
| LAVi     | `LAVi`            | continuous | 評估變數 (evaluation)        |
| 年齡     | `age`             | continuous | 臨床模型變數 (clinical model) |

*(以上為範例，實際內容依使用者需求填入)*

**規則：**
1. 列出所有使用者提及的變數：時間/事件（或結局）、評估變數、臨床模型變數、篩選條件、衍生變數
2. 衍生變數顯示推導方式（如 `BMI ← Weight/(Height/100)²`）
3. 篩選條件顯示完整條件（如 `HF_type == 3`）
4. 若使用者用口語中文描述（如「左心房容積指數」），顯示對應的實際欄位名稱（如 `LAVi`）
5. 若無法確定對應欄位，列出前 3 個候選欄位請使用者選擇

呈現表格後詢問：

> 以上欄位對應是否正確？如有需要修正請告知，確認後將進入設定檔產生。

**使用者確認前不得進入 Step 4。** 若使用者修正了任何對應，更新後重新呈現確認。

> **Guardian 註記**：若本 skill 由 `research-plan` orchestrator 呼叫且 `research_plan.json$.guardian.mode != "off"`，使用者確認後 orchestrator 會自動派 `biostats-guardian` Role 1 (Column Auditor) subagent 對 config 做獨立稽核（COL-001..011）。直接呼叫本 skill 時不會觸發。

### Step 4: Generate JSON Config

Write a JSON config file **alongside the output file**, using the same base name with `_config.json` suffix (e.g., if `output_file` is `/path/to/AUC_Cstat_Analysis.xlsx`, save config as `/path/to/AUC_Cstat_Analysis_config.json`). This ensures the config persists for future re-runs. The schema is documented below.

### Step 5: Check Missing Data

Run the script in missing-data-check mode:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/auc_cstat.py /tmp/auc_cstat_config.json --check-missing
```

This prints a report showing missing counts and percentages for every evaluation variable and clinical model variable. Present the report to the user. If there are missing values, ask how they want to handle them:
- **Listwise deletion** (default): exclude any row with any missing value across all variables (complete case analysis)
- **Pairwise deletion**: each variable's analysis uses all available data for that variable (+ clinical model variables + outcome)
- **Other**: let the user specify

If all variables have zero missing values, report this and proceed.

### Step 6: Execute Analysis

Run the full script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/auc_cstat.py /tmp/auc_cstat_config.json
```

This produces an Excel file (`.xlsx`).

### Step 7: Present Results

After execution, tell the user:
- Output file location
- Total sample size and event count
- Clinical model AUC/C-index (if applicable)
- Best single-variable AUC/C-index and which variable
- Number of variables with significant incremental value (delta p < 0.05, if clinical model provided)
- Any variables that could not be analyzed (convergence failures)

Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory: the directory containing this SKILL.md file.

### Step 8: Save Reusable Script

After presenting results, make the analysis **re-runnable** so the user can modify variables without re-triggering this skill:

1. Copy the Python script to the same directory as the output file:
```bash
cp ${CLAUDE_SKILL_DIR}/scripts/auc_cstat.py <OUTPUT_DIR>/auc_cstat.py
```

2. The JSON config file (from Step 4) is already saved alongside the output file.

3. Tell the user the following re-run instructions:
   - **Config file**: `<CONFIG_PATH>` (the JSON saved in Step 4)
   - **Script**: `<OUTPUT_DIR>/auc_cstat.py`
   - **Re-run command**: `python <OUTPUT_DIR>/auc_cstat.py <CONFIG_PATH>`
   - **Common modifications** (edit the config JSON directly):
     - Add/remove evaluation variables: edit the `sections` array
     - Change clinical model variables: edit `clinical_model.variables`
     - Change analysis type: edit `analysis_type` and `cox_settings`/`logistic_settings`
     - Change bootstrap settings: edit `bootstrap`
   - After editing, just ask Claude to run: `python <OUTPUT_DIR>/auc_cstat.py <CONFIG_PATH>`

Replace `<OUTPUT_DIR>` with the directory containing the output xlsx file, and `<CONFIG_PATH>` with the actual config file path.

### Step 9: Record Learnings

Silently check whether any corrections occurred during this run:

1. **Column mapping corrections** — Did the user change any column names during Step 3 confirmation?
2. **Config modifications** — Did the user modify the auto-generated config in Step 4?
3. **QC warnings** — Were there any missing data warnings or unexpected data patterns?

If any corrections occurred, append a structured entry to `<OUTPUT_DIR>/learnings.md`:

```
## [YYYY-MM-DD] auc-cstat run
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
  "analysis_type": "cox",
  "cox_settings": {
    "time_column": "time_composite",
    "event_column": "event_composite"
  },
  "logistic_settings": {
    "outcome_column": "event_death"
  },
  "clinical_model": {
    "enabled": true,
    "variables": [
      {"label": "Age (per 10 yrs)", "column": "age", "type": "continuous", "scale": 10},
      {"label": "Male sex", "column": "gender", "type": "binary"},
      {"label": "Hypertension", "column": "HTN_hx", "type": "binary"},
      {"label": "DM", "column": "DM_hx", "type": "binary"},
      {"label": "NT-proBNP (per 1000)", "column": "NTproBNP", "type": "continuous", "scale": 1000}
    ]
  },
  "sections": [
    {
      "header": "Echocardiographic Parameters",
      "variables": [
        {"label": "LAVi (per 10 mL/m²)", "column": "LAVi", "type": "continuous", "scale": 10, "scale_label": "per 10 mL/m²"},
        {"label": "PASP (per 10 mmHg)", "column": "PASP", "type": "continuous", "scale": 10, "scale_label": "per 10 mmHg"},
        {"label": "LVEF (per 5%)", "column": "LVEF", "type": "continuous", "scale": 5, "scale_label": "per 5%"},
        {"label": "E/e' > 14", "column": "Ee_high", "type": "binary"}
      ]
    }
  ],
  "bootstrap": {
    "n_iterations": 1000,
    "random_seed": 42
  },
  "title": "Discrimination Analysis — Echocardiographic Parameters",
  "subtitle": "TSOC HF Registry — HFpEF Cohort",
  "output_file": "/absolute/path/to/AUC_Cstat_Analysis.xlsx",
  "abbreviations": "AUC = area under the receiver operating characteristic curve; C-index = concordance index; CI = confidence interval",
  "missing_data_handling": "listwise"
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `data_file` | Yes | Absolute path to the data file (xlsx, csv, tsv, sas7bdat, dta) |
| `filters` | No | Array of filter conditions applied before analysis |
| `derived_variables` | No | Array of new columns to compute |
| `analysis_type` | Yes | `"cox"` for C-index or `"logistic"` for AUC |
| `cox_settings` | If cox | Time and event column names |
| `logistic_settings` | If logistic | Outcome column name |
| `clinical_model` | No | Baseline clinical model for incremental value comparison |
| `clinical_model.enabled` | No | `true`/`false`; defaults to `false` if `clinical_model` is omitted |
| `clinical_model.variables` | If enabled | Array of clinical model covariates (label, column, type, optional scale) |
| `sections` | Yes | Array of variable sections to evaluate |
| `bootstrap` | No | Bootstrap settings for C-index CI and comparison (cox only) |
| `bootstrap.n_iterations` | No | Number of bootstrap samples (default: 1000) |
| `bootstrap.random_seed` | No | Random seed for reproducibility (default: 42) |
| `title` | No | Table title (Row 1 in Excel) |
| `subtitle` | No | Subtitle text (Row 2 in Excel) |
| `output_file` | Yes | Output Excel path |
| `abbreviations` | Yes | Abbreviation footnote text (full forms of all abbreviations) |
| `missing_data_handling` | No | `"listwise"` (default, and the only value the script implements) — global complete-case deletion across all model variables. `"pairwise"` is **not** supported: pairwise deletion in a regression leaves every coefficient with a different N, so the model is not internally consistent. Any other value falls through to available-case behaviour and is not a supported configuration. (`table1`'s default is `"available"` — per-variable available-case, the convention for a baseline table but not for a fitted model.) **Real missing-data handling goes through `/research-plan`'s `missingness` and `mi_{outcome}` steps (multiple imputation); the listwise run here is that step's complete-case comparator, not a substitute for it.** |

### Filter Operators

Supported: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

### Variable Types

- **continuous**: Numeric variable. If `scale` is provided, the variable is divided by the scale value before model fitting (e.g., LAVi/10 → AUC per 10 mL/m²).
- **binary**: 0/1 or True/False variable. Used as-is in regression.

---

## Statistical Methods

### AUC (Binary Outcome, `analysis_type == "logistic"`)

| Component | Method | Details |
|-----------|--------|---------|
| Model | Logistic regression (statsmodels) | `outcome ~ variable` or `outcome ~ clinical_vars + variable` |
| AUC | `sklearn.metrics.roc_auc_score` | From predicted probabilities |
| 95% CI | DeLong variance estimate | Analytic, no bootstrap needed |
| Delta AUC comparison | DeLong test | Tests whether two correlated AUCs are significantly different |

### C-index (Time-to-Event, `analysis_type == "cox"`)

| Component | Method | Details |
|-----------|--------|---------|
| Model | Cox proportional hazards (lifelines) | `time ~ variable` or `time ~ clinical_vars + variable` |
| C-index | Harrell's concordance index | `CoxPHFitter.concordance_index_` |
| 95% CI | Bootstrap (percentile method) | Paired bootstrap resampling |
| Delta C-index comparison | Paired bootstrap | P-value from proportion of bootstrap deltas ≤ 0 |

### Common Rules

**Minimum thresholds**: n ≥ 10 and events ≥ 20 (blocking), otherwise the variable is marked as "N/A". Events ≥ 50 recommended for publication-quality discrimination metrics (warning if < 50). Ref: Riley et al. (2019) Stat Med; Hanczar et al. (2010) Bioinformatics.

**p-value formatting**: `<0.001*` for p < 0.001, `x.xxx*` for p < 0.05, `x.xxx` for p ≥ 0.05.

**AUC/C-index formatting**: `0.xxx (0.xxx–0.xxx)` with three decimal places.

**Delta formatting**: `+0.xxx` or `-0.xxx` with sign prefix.

---

## Output Description

### Excel Table — With Clinical Model (8 columns)

- **Row 1**: Title (dark blue background, white text)
- **Row 2**: Subtitle with sample size (e.g., "n=XXX, events=XXX")
- **Row 3**: Column headers (blue header fill, white bold text)
  - Variable | N | Events | AUC/C-index (variable alone) [95% CI] | AUC/C-index (clinical model) [95% CI] | AUC/C-index (clinical model + variable) [95% CI] | Delta [95% CI] | p-value
- **Data rows**: Section headers (light blue) followed by variable rows with alternating shading
- **Footnotes**:
  - Abbreviations
  - Clinical model composition (e.g., "Clinical model includes: Age, Male sex, HTN, DM, NT-proBNP")
  - Statistical method note (DeLong test or bootstrap)
  - Significance note (`* p < 0.05`)

### Excel Table — Without Clinical Model (4 columns)

- Same title/subtitle rows
- **Column headers**: Variable | N | Events | AUC/C-index [95% CI]
- Simpler footnotes (no clinical model or comparison notes)

---

## Example Usage

**User**: "I want to compute C-statistics for echocardiographic parameters in HFpEF patients. Data is in TSOC_data_merge.xlsx, filter for HF_type==3. This is time-to-event data — time variable: time_composite, event: event_composite. Variables to evaluate: LAVi (per 10), PASP (per 10), LVEF (per 5), E/e' > 14. Clinical model: age (per 10 yrs), gender, HTN_hx, DM_hx, NTproBNP (per 1000). Use 1000 bootstrap iterations."

**Claude's response**: Generates the JSON config, runs missing data check, presents results, then generates the formatted Excel with C-index discrimination analysis including incremental value over the clinical model.

---

## Pipeline Integration

When called from the `research-plan` orchestrator pipeline:

- Config is pre-generated at `configs/{step_id}_config.json` by `generate_configs.py`
- Skip Steps 1–4 (interactive interview + column confirmation); proceed directly to Step 5 (check missing data) and Step 6 (execute)
- Exit code 0 = success, non-zero = failure (triggers retry then error in pipeline)
- QC warnings are emitted to stderr with `[QC_WARNING]` prefix for pipeline collection
- QC blocking issues are emitted to stderr with `[QC_BLOCKING]` prefix (step marked as error)

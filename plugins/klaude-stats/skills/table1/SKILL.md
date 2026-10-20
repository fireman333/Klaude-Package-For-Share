---
name: table1
description: "Publication-ready Table 1: baseline characteristics comparison between two groups with auto statistical tests; Excel + CSV output. Trigger: Table 1, baseline characteristics, baseline table, demographic table, descriptive statistics table, group comparison, cohort comparison, patient characteristics, characteristic comparison, comparing demographics between groups, make a table comparing group A vs B, generate baseline table, 幫我做 Table 1, 基線特徵比較, 基本資料表, 人口學比較, 兩組比較, 幫我做兩組比較, 描述性統計表, 特徵比較表, 基線比較, 做基本資料; or any two-group clinical/demographic comparison."
---

# Table 1 Generator

Generate publication-ready Table 1 (baseline characteristics) comparing two groups, with automatic statistical test selection, missing data validation, and formatted Excel + CSV output.

## Use this skill when

- Comparing **baseline / demographic / clinical characteristics** between exactly **two groups** (cohort vs control, case vs control, treatment vs placebo, exposed vs unexposed)
- Producing the **first table** of a clinical / epidemiological manuscript (Table 1)
- Computing **SMD** (standardized mean difference) for a PSM-matched cohort comparison
- Generating descriptive statistics with appropriate hypothesis tests selected automatically per variable type

## Defer to other skills when

- **≥ 3 groups** to compare → ANOVA / Kruskal-Wallis tools (this skill aborts loudly)
- **Adjusted comparisons** (covariates / confounders) → `multivariate-interaction` or `univariate-forest`
- **Survival / time-to-event** outcomes → `kaplan-meier` / `competing-risk`
- **Outcome / regression modelling** (HR / OR per predictor) → `univariate-forest` / `multivariate-interaction`
- **Discrimination metrics** (AUC, C-statistic) → `auc-cstat`
- **Propensity score matching itself** → `psm-matching` (then `table1` for post-match comparison with SMD)

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 0: Context Recovery

Before gathering requirements, check for existing upstream context:

1. Search the working directory (and parent directories up to 2 levels) for `research_plan.json`
2. If found, read it and extract relevant fields for this skill:
   - `study.data_file` → Data file path
   - `population.filters` → Data filters
   - `grouping` → Grouping variable, group values and labels
   - `covariates` → Variable list (name, column, type, scale, label_map)
   - `derived_variables` → Derived variables
3. Present the pre-filled config to the user: "Found research plan — using these settings:" followed by a concise summary
4. Ask user to confirm or modify, then skip to Step 2
5. If no `research_plan.json` found, also check for a `learnings.md` in the working directory — if present, read column mapping corrections and apply them as defaults

If no upstream context is found, proceed to Step 1.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Data file path** — xlsx, csv, or other pandas-readable format
2. **Data filters** (optional) — conditions to subset the data before analysis (e.g., `HF_type == 3`)
3. **Grouping variable** — the column name that defines the two groups, plus:
   - Value and label for Group 1 (e.g., value=1.0, label="AF")
   - Value and label for Group 2 (e.g., value=0.0, label="No AF")
4. **Derived variables** (optional) — new columns to compute before analysis:
   - `coalesce` type: pick the first non-null from a list of columns (e.g., combine admission + outpatient values)
   - `expression` type: compute from existing columns (e.g., BMI = Weight / (Height/100)^2)
5. **Variable list** — organized by section, each variable needs:
   - Display label (e.g., "Age (years)")
   - Column name in the data
   - Type: `continuous`, `binary`, or `ordinal`
   - For `ordinal`: a label_map mapping values to display labels
6. **Table title and subtitle**
7. **Output file path**
8. **Abbreviations** (optional) — for the footnote

### Step 2: Validate Data

Before generating the config, read the data file to confirm:
- The file exists and is readable
- All specified columns exist
- The grouping variable contains the expected values

Run a quick Python snippet:
```python
import pandas as pd
df = pd.read_excel("path") # or read_csv
print(f"Shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
print(f"Group column values: {df['group_col'].value_counts()}")
```

### Step 3: Confirm Column Mapping (欄位確認)

在產生設定檔之前，先將使用者描述的變數與實際 Excel 欄位名稱整理成對應表，確保沒有對應錯誤。

根據 Steps 1–2 收集到的資訊，建立以下表格：

| 使用者描述 | 對應欄位名稱 | 資料類型 | 角色 |
|-----------|-------------|---------|------|
| 有無 AF    | `AF_hx`               | binary     | 分組變數 (grouping)  |
| 年齡       | `age`                 | continuous | 比較變數 (variable)  |
| 糖尿病     | `DM_hx`               | binary     | 比較變數 (variable)  |
| BMI       | `Weight/(Height/100)²` | derived    | 比較變數 (variable)  |
| 只收 HFpEF | `HF_type == 3`        | filter     | 資料篩選 (filter)    |

*(以上為範例，實際內容依使用者需求填入)*

**規則：**
1. 列出所有使用者提及的變數：分組、比較變數、篩選條件、衍生變數
2. 衍生變數顯示推導方式（如 `BMI ← Weight/(Height/100)²`）
3. 篩選條件顯示完整條件（如 `HF_type == 3`）
4. 若使用者用口語中文描述（如「糖尿病」），顯示對應的實際欄位名稱（如 `DM_hx`）
5. 若無法確定對應欄位，列出前 3 個候選欄位請使用者選擇

呈現表格後詢問：

> 以上欄位對應是否正確？如有需要修正請告知，確認後將進入設定檔產生。

**使用者確認前不得進入 Step 4。** 若使用者修正了任何對應，更新後重新呈現確認。

> **Guardian 註記**：若本 skill 由 `research-plan` orchestrator 呼叫且 `research_plan.json$.guardian.mode != "off"`，使用者確認後 orchestrator 會自動派 `biostats-guardian` Role 1 (Column Auditor) subagent 對 config 做獨立稽核（COL-001..011）。直接呼叫本 skill 時不會觸發。

### Step 4: Generate JSON Config

Write a JSON config file **alongside the output file**, using the same base name with `_config.json` suffix (e.g., if `output_file` is `/path/to/Table1.xlsx`, save config as `/path/to/Table1_config.json`). This ensures the config persists for future re-runs. The schema is documented below.

### Step 5: Check Missing Data

Run the script in missing-data-check mode:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/make_table1.py /tmp/table1_config.json --check-missing
```

This prints a report showing missing counts and percentages for every variable, per group. Present the report to the user. If there are missing values, ask how they want to handle them:
- **Listwise deletion** (default): exclude any row with any missing value across all variables (complete case analysis)
- **Pairwise deletion**: each statistical test uses all available data for that variable
- **Other**: let the user specify

If all variables have zero missing values, report this and proceed.

### Step 6: Generate the Table

Run the full script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/make_table1.py /tmp/table1_config.json
```

This produces both an Excel file and a CSV file (same path with .csv extension).

### Step 7: Present Results

After execution, tell the user:
- Output file locations (xlsx and csv)
- Total sample size and per-group sizes
- Number of statistically significant variables (p < 0.05)
- Any variables that could not be analyzed (e.g., insufficient data)

Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory: the directory containing this SKILL.md file.

### Step 8: Save Reusable Script

After presenting results, make the analysis **re-runnable** so the user can modify variables without re-triggering this skill:

1. Copy the Python script to the same directory as the output file:
```bash
cp ${CLAUDE_SKILL_DIR}/scripts/make_table1.py <OUTPUT_DIR>/make_table1.py
```

2. The JSON config file (from Step 4) is already saved alongside the output file.

3. Tell the user the following re-run instructions:
   - **Config file**: `<CONFIG_PATH>` (the JSON saved in Step 4)
   - **Script**: `<OUTPUT_DIR>/make_table1.py`
   - **Re-run command**: `python <OUTPUT_DIR>/make_table1.py <CONFIG_PATH>`
   - **Common modifications** (edit the config JSON directly):
     - Add/remove variables: edit the `sections` array
     - Change grouping: edit the `grouping` object
     - Change data filters: edit the `filters` array
     - Change output path: edit `output_file`
   - After editing, just ask Claude to run: `python <OUTPUT_DIR>/make_table1.py <CONFIG_PATH>`

Replace `<OUTPUT_DIR>` with the directory containing the output xlsx file, and `<CONFIG_PATH>` with the actual config file path.

### Step 9: Record Learnings

Silently check whether any corrections occurred during this run:

1. **Column mapping corrections** — Did the user change any column names during Step 3 confirmation? (e.g., "DM" → "DM_hx")
2. **Config modifications** — Did the user modify the auto-generated config in Step 4?
3. **QC warnings** — Were there any missing data warnings or unexpected data patterns?

If any corrections occurred, append a structured entry to `<OUTPUT_DIR>/learnings.md`:

```markdown
## [YYYY-MM-DD] table1 run
- Column correction: "DM" → "DM_hx" (user specified during mapping)
- Config change: added derived variable BMI
- QC note: column "SBP" had 15% missing data
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
  "title": "Table 1. Baseline Characteristics of Patients by Group",
  "subtitle": "Study Name or Registry",
  "sections": [
    {
      "header": "Demographics",
      "variables": [
        {"label": "Age (years)", "column": "age", "type": "continuous"},
        {"label": "Male sex, n (%)", "column": "gender", "type": "binary"},
        {
          "label": "NYHA class",
          "column": "NYHA",
          "type": "ordinal",
          "label_map": {
            "1.0": "NYHA I",
            "2.0": "NYHA II",
            "3.0": "NYHA III",
            "4.0": "NYHA IV"
          }
        }
      ]
    }
  ],
  "output_file": "/absolute/path/to/Table1.xlsx",
  "abbreviations": "AF = atrial fibrillation; BMI = body mass index; ...",
  "missing_data_handling": "listwise"
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `data_file` | Yes | Absolute path to the data file (xlsx or csv) |
| `filters` | No | Array of filter conditions applied before analysis |
| `derived_variables` | No | Array of new columns to compute |
| `grouping` | Yes | Defines the two-group comparison |
| `title` | Yes | Table title (Row 1 in Excel) |
| `subtitle` | No | Subtitle text (Row 2 in Excel) |
| `sections` | Yes | Array of variable sections, each with a header and variables |
| `output_file` | Yes | Output Excel path (CSV auto-generated with .csv extension) |
| `abbreviations` | No | Abbreviation footnote text |
| `missing_data_handling` | No | `"available"` (**default for table1**) — per-variable available-case: each variable's n / mean / % is computed on its own non-missing values, the standard convention for a baseline table. Set to `"listwise"` for global complete-case deletion across all table variables (shrinks N and can bias the table; opt-in only). Those are the only two values the script implements — `"pairwise"` is **not** supported, and any other value falls through to available-case behaviour. (The regression skills — `univariate-forest`, `multivariate-interaction`, `auc-cstat` — default to `"listwise"` instead, because a fitted model needs one consistent N.) **Real missing-data handling goes through `/research-plan`'s `missingness` and `mi_{outcome}` steps (multiple imputation); the listwise run here is that step's complete-case comparator, not a substitute for it.** |

### Filter Operators

Supported: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

### Variable Types

- **continuous**: Numeric. Auto-selects mean+/-SD with t-test (if approximately normal) or median[IQR] with Mann-Whitney U (if skewed). Per-group normality is checked separately — both groups must pass for parametric. SMD = Cohen's d (|mean1 − mean2| / pooled SD).
- **binary**: 0/1 (default) or other event coding via `event_value` field. Shows n (%). Uses Chi-square (if all expected cells >= 5 and both groups n >= 30) or Fisher's exact test. SMD = Cohen's h (arcsin transform).
- **ordinal**: Multi-category, ordered (NYHA I-IV, Killip class, etc.). Shows per-category n (%). Overall p-value via Mann-Whitney U on the rank order. Use only when categories have a natural ordering. SMD not reported.
- **categorical**: Multi-category, **nominal / unordered** (race, smoking type, medication class). Shows per-category n (%). Overall p-value via RxC chi-square (Fisher exact for 2x2 sparse cells; chi-square with sparse-cell flag for RxC sparse). SMD not reported. Use this instead of `ordinal` when categories have no natural ordering.

**event_value (binary only)**: when binary encoding is not 0/1, declare per-variable. Example: `{"label": "Death", "column": "death_flag", "type": "binary", "event_value": 2}` for `2=died, 1=alive`. Default `event_value=1` when omitted (backward-compatible).

---

## Statistical Methods

The script automatically selects appropriate tests:

| Variable Type | Normality | Descriptive | Test |
|--------------|-----------|-------------|------|
| Continuous | Normal (skewness < 1) | Mean +/- SD | Welch's t-test |
| Continuous | Non-normal (skewness >= 1) | Median [IQR] | Mann-Whitney U |
| Binary | — | n (%) | Chi-square or Fisher's exact |
| Ordinal | — | n (%) per category | Mann-Whitney U |

**Normality assessment**: Uses skewness-based criterion (absolute skewness < 1) rather than Shapiro-Wilk, because Shapiro-Wilk is overly sensitive for clinical datasets with n > 100 and rejects normality even for practically symmetric distributions.

**p-value formatting**: `<0.001*` for p < 0.001, `x.xxx*` for p < 0.05, `x.xxx` for p >= 0.05.

**SMD (standardized mean difference)**: shown for `continuous` (Cohen's d, |mean1−mean2|/pooled SD) and `binary` (Cohen's h, arcsin transform). SMD ≥ 0.1 is the conventional balance threshold for PSM. Not shown for `ordinal` / `categorical`.

**Multiple comparisons**: Table 1 p-values are reported as **descriptive** (not adjusted for multiple comparisons), per common epidemiological / clinical journal convention. The footnote of every output explicitly states this.

---

## Failure Modes & Edge Cases

| Condition | Behaviour |
|---|---|
| Group count ≠ 2 in config | **Abort** with `[FATAL]`. Use ANOVA / Kruskal-Wallis tools for ≥ 3 groups. |
| Either group n = 0 after split | **Abort** with `[FATAL]`. Likely string-coded grouping with mismatched value, or all rows filtered out. |
| Either group n < 5 after listwise deletion | **Abort** with `[QC_BLOCKING]` before writing artifacts (table1-D-3). |
| Either group n < 30 | Continue, emit `[QC_WARNING]` (small sample). |
| Multi-sheet Excel without `sheet_name` config | **Abort** with `[FATAL]` listing available sheets (table1-R2-2). |
| Binary column has > 2 unique numeric values | Continue, emit `[WARNING]` per variable. Result still computed against `event_value` but data is suspect. |
| Binary `event_value` not present in data | Continue, emit `[WARNING]`. Result will read `0/0 (0.0%)` for that group — check `event_value` config. |
| Non-numeric values in continuous / binary / ordinal column | Continue, emit `[WARNING]` listing first 5 lost values. Coerced to NaN and excluded. |
| All-NA column / single-value column | Returns `n=0` row entries; descriptive only, no p-value. |
| Convergence / numerical failure in scipy test | Falls through `_pval_str(NaN) → "N/A"`; method label preserved. |
| Empty contingency table for `categorical` | Single placeholder row with `–` cells. |

---

## Example Usage

**Natural-language invocation**:

> "I want to create a Table 1 comparing HFpEF patients with and without AF. The data is in TSOC_data_merge.xlsx, filter for HF_type==3, group by AF_hx (1=AF, 0=No AF). Variables: age (continuous), gender (binary), BMI (continuous, derived from Height and Weight), HTN_hx (binary), DM_hx (binary), LVEF (continuous)."

Claude generates the JSON config, runs missing-data check, presents results, then generates the formatted Excel + CSV Table 1.

**Minimal runnable example** (CLI direct, no Claude):

```bash
# Save this as /tmp/example_table1_config.json
cat > /tmp/example_table1_config.json <<'EOF'
{
  "data_file": "/tmp/example_data.csv",
  "filters": [],
  "grouping": {
    "column": "treatment",
    "groups": [
      {"value": 1, "label": "Treatment"},
      {"value": 0, "label": "Control"}
    ]
  },
  "title": "Table 1. Baseline Characteristics",
  "sections": [
    {
      "header": "Demographics",
      "variables": [
        {"label": "Age (years)", "column": "age", "type": "continuous"},
        {"label": "Male, n (%)", "column": "male", "type": "binary"},
        {"label": "Race", "column": "race", "type": "categorical"},
        {"label": "NYHA class", "column": "nyha", "type": "ordinal",
         "label_map": {"1": "I", "2": "II", "3": "III", "4": "IV"}}
      ]
    }
  ],
  "output_file": "/tmp/example_table1.xlsx"
}
EOF

# Run
python ${CLAUDE_SKILL_DIR}/scripts/make_table1.py /tmp/example_table1_config.json

# Check missing data first (optional)
python ${CLAUDE_SKILL_DIR}/scripts/make_table1.py /tmp/example_table1_config.json --check-missing
```

---

## Pipeline Integration

When called from the `research-plan` orchestrator pipeline (table1-D-1 — pipeline mode is structurally distinct from direct-use):

- **Config is pre-generated** at `<output_dir>/<step_id>_config.json` by `generate_configs.py`. The interactive interview (Steps 1, 3) is skipped; the user has already approved the plan and the column mapping at the orchestrator level.
- **Workflow shortcut**: Skip Steps 1, 3 (interactive); proceed directly Step 0 → 2 (validate data, non-interactive) → 5 (`--check-missing`) → 6 (execute) → 7 (present results).
- **Direct-use vs pipeline-use**: in direct-use the user *confirms* the column mapping in Step 3 (interactive); in pipeline-use the orchestrator pre-validated the mapping (no interactive confirmation possible). The orchestrator's `biostats-guardian` Role 1 (Column Auditor) replaces the user's interactive sanity check.
- **Exit codes**: `0` = success; non-zero = failure (triggers retry → error in pipeline).
- **QC warnings**: emitted to stderr with `[QC_WARNING]` prefix; collected by orchestrator. Non-blocking; pipeline continues.
- **QC blocking**: emitted to stderr with `[QC_BLOCKING]` prefix; pipeline marks step as `error`. Includes per-group n < 5 (table1-D-3, pre-write) and abort conditions in `split_groups` / `load_data`.

### Input contract: `research_plan.json` fields consumed

| `research_plan.json` path | table1 field | Notes |
|---|---|---|
| `study.data_file` | `config.data_file` | Absolute path to xlsx/csv |
| `population.filters` | `config.filters` | Pass-through (operators: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`) |
| `grouping.column` | `config.grouping.column` | The 2-group split variable |
| `grouping.groups[*]` | `config.grouping.groups[*]` | Exactly 2 groups required |
| `covariates[*]` | `config.sections[].variables[*]` | Variables grouped into sections by `covariate.section` |
| `derived_variables[*]` | `config.derived_variables[*]` | Computed before analysis |
| `qa_thresholds.smd_max` (optional) | not consumed yet | Reserved for future cohort balance check |

### Output artifacts (canonical paths)

When `output_file = "/path/to/Table1.xlsx"`, the script writes three artifacts (table1-D-2):

| Artifact | Path | Purpose |
|---|---|---|
| Formatted xlsx | `/path/to/Table1.xlsx` | Publication Excel (title / subtitle / merged headers / SMD / p-value / SIG color) |
| CSV | `/path/to/Table1.csv` | Plain CSV (same columns as xlsx, no formatting) |
| Summary JSON | `/path/to/Table1_summary.json` | Machine-readable: n_total, per-group n, total_variables_analyzed, significant_count, skipped_variables, qc_warnings, schema_version |
| Config copy | `/path/to/Table1_config.json` | Verbatim config (Step 4 — for re-run via Step 8) |

`manuscript-results` (downstream skill) reads `Table1_summary.json` to render Methods / Results paragraphs without re-parsing the xlsx.

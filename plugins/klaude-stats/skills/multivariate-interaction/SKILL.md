---
name: multivariate-interaction
description: "multivariate-interaction: one adjusted multivariate model (Cox→HR / Logistic→OR) + p-interaction per covariate between two groups; Excel output. Trigger: multivariate analysis, multivariable regression, interaction analysis, interaction term, p-interaction, subgroup interaction, adjusted model, subgroup analysis, adjusted analysis, adjusted HR, adjusted OR, effect modification, covariates adjustment, multivariable model, multivariate Cox, multivariate logistic, run multivariate with interaction, run subgroup analysis, 多變量分析, 交互作用分析, 多變量迴歸, 校正分析, 亞組分析, 次族群分析, 做多變量, 校正後分析, 多變項分析, 交互項分析, 幫我做多變量分析, 幫我做亞組分析."
---

# Multivariate Analysis + Interaction Analysis

Run multivariate regression (Cox PH for time-to-event -> HR, or logistic for binary outcome -> OR) on the overall population, then run stratified multivariate models in each subgroup and compute p-interaction for every covariate. Output a formatted Excel file with 2 sheets.

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 0: Context Recovery

Before gathering requirements, check for existing upstream context:

1. Search the working directory (and parent directories up to 2 levels) for `research_plan.json`
2. If found, read it and extract relevant fields for this skill:
   - `study.data_file` → Data file path
   - `population.filters` → Data filters
   - `grouping` → Grouping variable (interaction groups), values and labels
   - `outcomes` → Match the outcome to extract: analysis type (cox/logistic), time_column, event_column, or outcome_column
   - `covariates` → Variable list (name, column, type, scale, scale_label) — these become both model covariates and interaction test variables
   - `derived_variables` → Derived variables (including composite endpoints)
3. Present the pre-filled config to the user: "Found research plan — using these settings:" followed by a concise summary
4. Ask user to confirm or modify, then skip to Step 2
5. If no `research_plan.json` found, also check for a `learnings.md` in the working directory — if present, read column mapping corrections and apply them as defaults
6. Check for `diagnostic_report.json` in `{working_dir}/diagnostics/` or `{working_dir}/`. If found, read it and apply the per-skill integration rules in `${CLAUDE_SKILL_DIR}/../survival-diagnostics/references/downstream_integration.md` (`/multivariate-interaction` section). Key actions: warn if `recommended_primary="competing-risk"`; prefill `cluster_column` if clustering detected; **block** if `checks.time_varying.detected=true, risk="high"`; warn if `checks.left_truncation.detected=true` (skill needs `entry_column` added to Surv call).

If no upstream context is found, proceed to Step 1.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Data file path** -- xlsx, csv, or other pandas-readable format
2. **Data filters** (optional) -- conditions to subset the data before analysis (e.g., `HF_type == 3`)
3. **Derived variables** (optional) -- new columns to compute before analysis:
   - `coalesce` type: pick the first non-null from a list of columns
   - `expression` type: compute from existing columns (e.g., BMI = Weight / (Height/100)^2)
4. **Grouping variable** -- the column name that defines the two subgroups for interaction analysis, plus:
   - Value and label for Group 1 (e.g., value=1.0, label="AF")
   - Value and label for Group 2 (e.g., value=0.0, label="No AF")
5. **Composite endpoint** — If analysis type is `cox`, ask whether the user wants to analyze a **composite endpoint (time to first event of death OR hospitalization)**. If yes:
   - If the data already has composite columns, use them directly as `time_column` and `event_column`.
   - If not, offer to derive them via `derived_variables`:
     - `time_composite`: `expression` type — `np.minimum(time_death, time_hosp)` (takes the earlier of the two)
     - `event_composite`: `expression` type — `np.where((event_death == 1) | (event_hosp == 1), 1, 0)`
   - Always confirm which death and hospitalization columns exist before deriving.
6. **Analysis type**: `"cox"` (time-to-event -> HR) or `"logistic"` (binary outcome -> OR)
7. **For cox**: `time_column` and `event_column` names
   **For logistic**: `outcome_column` name
8. **Variable list** -- organized by section, each variable needs:
   - Display label (e.g., "Age (per 10 yrs)")
   - Column name in the data
   - Type: `continuous` or `binary`
   - For continuous with scaling: `scale` (number) and `scale_label` (string, e.g., "per 10 yrs")
8. **Interaction variables** (optional) -- which variables to test for interaction. Default: `"all"` (test all variables)
9. **Output file path** (base name; script generates `.xlsx`)
10. **Table title and subtitle** (optional)
11. **Abbreviations** (optional) -- for the footnote

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
| 年齡 (每10歲) | `age`            | continuous | 校正變數 (covariate)  |
| 糖尿病        | `DM_hx`          | binary     | 校正變數 (covariate)  |

*(以上為範例，實際內容依使用者需求填入)*

**規則：**
1. 列出所有使用者提及的變數：分組、時間/事件（或結局）、校正變數、交互作用變數、篩選條件、衍生變數
2. 衍生變數顯示推導方式（如 `BMI ← Weight/(Height/100)²`）
3. 篩選條件顯示完整條件（如 `HF_type == 3`）
4. 若使用者用口語中文描述（如「糖尿病」），顯示對應的實際欄位名稱（如 `DM_hx`）
5. 若無法確定對應欄位，列出前 3 個候選欄位請使用者選擇

呈現表格後詢問：

> 以上欄位對應是否正確？如有需要修正請告知，確認後將進入設定檔產生。

**使用者確認前不得進入 Step 4。** 若使用者修正了任何對應，更新後重新呈現確認。

> **Guardian 註記**：若本 skill 由 `research-plan` orchestrator 呼叫且 `research_plan.json$.guardian.mode != "off"`，使用者確認後 orchestrator 會自動派 `biostats-guardian` Role 1 (Column Auditor) subagent 對 config 做獨立稽核（COL-001..011）。直接呼叫本 skill 時不會觸發。

### Step 4: Generate JSON Config

Write a JSON config file **alongside the output file**, using the same base name with `_config.json` suffix (e.g., if `output_file` is `/path/to/Multivariate_Interaction.xlsx`, save config as `/path/to/Multivariate_Interaction_config.json`). This ensures the config persists for future re-runs. The schema is documented below.

### Step 5: Check Missing Data

Run the script in missing-data-check mode:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/multivariate_interaction.py /tmp/multivariate_interaction_config.json --check-missing
```

This prints a report showing missing counts and percentages for every variable across Overall, Group 1, and Group 2 populations. It also reports the **effective sample size after listwise deletion** (rows where all variables are non-missing), because multivariate models require complete cases across all variables simultaneously.

Present the report to the user. If there are missing values, ask how they want to handle them:
- **Listwise deletion** (default): exclude any row with any missing value across all analysis variables
- **Pairwise deletion**: each regression uses all available data (interaction models may have different sample sizes per variable)
- **Other**: let the user specify

If all variables have zero missing values, report this and proceed.

### Step 6: Execute Analysis

Run the full script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/multivariate_interaction.py /tmp/multivariate_interaction_config.json
```

This produces an Excel file (`.xlsx`) with two sheets.

### Step 7: Present Results

After execution, tell the user:
- Output file location
- Total sample size and per-group sizes (with event counts for cox)
- Effective sample size after listwise deletion
- Number of statistically significant variables (p < 0.05) in the multivariate model
- Number of significant interactions (p-interaction < 0.05)
- Any variables that could not be analyzed (convergence failures)
- For cox: the proportional hazards result — global Schoenfeld p, any violating covariates, and (if violated) the pre-specified `ph_violation_remedy`. If the run exited 2 because PH was violated with no remedy declared, say so plainly and point at `<output_base>_ph_diagnostics.png`; do not present the Sheet 1 HRs as final.

Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory: the directory containing this SKILL.md file.

### Step 8: Save Reusable Script

After presenting results, make the analysis **re-runnable** so the user can modify variables without re-triggering this skill:

1. Copy the Python script to the same directory as the output file:
```bash
cp ${CLAUDE_SKILL_DIR}/scripts/multivariate_interaction.py <OUTPUT_DIR>/multivariate_interaction.py
```

2. The JSON config file (from Step 4) is already saved alongside the output file.

3. Tell the user the following re-run instructions:
   - **Config file**: `<CONFIG_PATH>` (the JSON saved in Step 4)
   - **Script**: `<OUTPUT_DIR>/multivariate_interaction.py`
   - **Re-run command**: `python <OUTPUT_DIR>/multivariate_interaction.py <CONFIG_PATH>`
   - **Common modifications** (edit the config JSON directly):
     - Add/remove covariates: edit the `sections` array
     - Change interaction variables: edit `interaction_variables`
     - Change grouping: edit the `grouping` object
     - Change data filters: edit the `filters` array
   - After editing, just ask Claude to run: `python <OUTPUT_DIR>/multivariate_interaction.py <CONFIG_PATH>`

Replace `<OUTPUT_DIR>` with the directory containing the output xlsx file, and `<CONFIG_PATH>` with the actual config file path.

### Step 9: Record Learnings

Silently check whether any corrections occurred during this run:

1. **Column mapping corrections** — Did the user change any column names during Step 3 confirmation?
2. **Config modifications** — Did the user modify the auto-generated config in Step 4?
3. **QC warnings** — Were there any missing data warnings or unexpected data patterns?

If any corrections occurred, append a structured entry to `<OUTPUT_DIR>/learnings.md`:

```
## [YYYY-MM-DD] multivariate-interaction run
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
    "event_column": "event_composite"
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
  "interaction_variables": "all",
  "ph_violation_remedy": "stratify",
  "title": "Multivariate Cox Regression with Interaction Analysis",
  "subtitle": "TSOC HF Registry",
  "output_file": "/absolute/path/to/Multivariate_Interaction.xlsx",
  "abbreviations": "HR = hazard ratio; CI = confidence interval; ...",
  "missing_data_handling": "listwise"
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `data_file` | Yes | Absolute path to the data file (xlsx or csv) |
| `filters` | No | Array of filter conditions applied before analysis |
| `derived_variables` | No | Array of new columns to compute |
| `grouping` | Yes | Defines the two subgroups for interaction testing |
| `analysis_type` | Yes | `"cox"` for HR or `"logistic"` for OR |
| `cox_settings` | If cox | Time and event column names |
| `logistic_settings` | If logistic | Outcome column name |
| `sections` | Yes | Array of variable sections, each with a header and variables |
| `interaction_variables` | No | `"all"` (default, test all variables) or array of column names |
| `ph_violation_remedy` | Cox only | **Declared** handling if the proportional hazards assumption is violated: `"stratify"` \| `"time_varying"` \| `"rmst"` \| `"disclose"`. Omit it and a detected violation is **blocking** (exit 2) — see “Proportional Hazards Assumption” below. Must be decided *before* seeing the Schoenfeld result.<br>**Plumbing (wired 2026-08-12):** in a `/research-plan` pipeline this arrives from `research_plan.json` via `generate_configs.gen_multivariate_interaction()`, which calls `_carry_ph_remedy()` to copy it — and `ph_disclose_decision_id` — into the generated config under the same key names.<br>⚠ **It is read from `outcomes[<id>].ph_violation_remedy`, never from the plan's top level. A top-level key is silently ignored, and that placement *is* the enforcement.** The plan fingerprint hashes `outcomes`, so a remedy declared there cannot be back-filled after seeing the Schoenfeld result without changing the fingerprint, invalidating the existing reviewer challenge and forcing a re-run. That is what makes "pre-specified" a checkable claim rather than an assertion. Declared at the top level it changes nothing, silently.<br>⚠ **No remedy is executed by this skill** — a remedy runs as its own step against its own table, so this workbook stays internally consistent instead of carrying a stratified Sheet 1 next to an unstratified Sheet 2 (2026-08-12 adjudication, dispute 5). All three of `stratify` / `time_varying` / `rmst` gained shipped generators on 2026-08-12 (`ph-stratified` / `ph-time-varying` / `ph-rmst` in `research-plan/scripts/`): declaring one makes `_plan_pipeline_changes()` add a step that runs it, writes its own workbook, and emits an evidence sidecar the manuscript gate verifies against **this** step's `*_ph_test.json`. `time_varying` needs `outcomes[<id>].tv_cut_points` and `rmst` needs `rmst_tau` or `rmst_tau_rule` — undeclared they still run, but `ph_remedy_gate.py` blocks the manuscript, because a time window or a tau chosen after seeing the result is not a pre-specification. Sheet 1's HRs stay unremediated in every case: the remedy is a different table, and declaring a remedy is not the same as having done it. |
| `title` | No | Table title (Row 1 in Excel) |
| `subtitle` | No | Subtitle text (Row 2 in Excel) |
| `output_file` | Yes | Output Excel path |
| `abbreviations` | No | Abbreviation footnote text |
| `missing_data_handling` | No | `"listwise"` (default, and the only value the script implements) — global complete-case deletion across all model variables. `"pairwise"` is **not** supported: pairwise deletion in a regression leaves every coefficient with a different N, so the model is not internally consistent. Any other value falls through to available-case behaviour and is not a supported configuration. (`table1`'s default is `"available"` — per-variable available-case, the convention for a baseline table but not for a fitted model.) **Real missing-data handling goes through `/research-plan`'s `missingness` and `mi_{outcome}` steps (multiple imputation); the listwise run here is that step's complete-case comparator, not a substitute for it.** |

### Filter Operators

Supported: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

### Variable Types

- **continuous**: Numeric variable. If `scale` is provided, the variable is divided by the scale value before regression (e.g., age/10 -> HR per 10 years).
- **binary**: 0/1 or True/False variable. Used as-is in regression.

---

## Statistical Methods

### Sheet 1: Multivariate Analysis

A single regression model with ALL covariates entered simultaneously on the overall population.

| Analysis Type | Model | Effect Measure | Interpretation |
|--------------|-------|----------------|----------------|
| Time-to-event (`cox`) | Cox proportional hazards (lifelines) | Adjusted HR (95% CI) | HR > 1 = higher risk after adjustment |
| Binary outcome (`logistic`) | Logistic regression (statsmodels) | Adjusted OR (95% CI) | OR > 1 = higher odds after adjustment |

### Proportional Hazards Assumption（Cox only）

The reviewer question is never “did you test PH?” alone — it is **“was it tested, and what did you do when it was violated? Detecting it is not handling it.”** The skill therefore does both halves.

**Test.** After the multivariate model is fitted, scaled Schoenfeld residuals are computed on the rank-transformed event times:

- **Variable-level**: one chi-square (1 df) per covariate, numerically identical to `lifelines.statistics.proportional_hazard_test`.
- **Global**: the corresponding quadratic form over all covariates, `Q = w' V⁻¹ w / (d · Σx²)` with `p` df — the analogue of R `cox.zph`’s `GLOBAL` row, which lifelines does not expose. Both come from the same residual matrix so they cannot disagree with each other.

**Two thresholds, because blocking and concluding are different questions** (2026-08-12 adjudication):

| | Threshold | What it does |
|---|---|---|
| **Gate** `PH_ALPHA` | p < 0.01, on the pre-specified `rank` transform | Automatic hard gate. Not 0.05: measured at n≈6000, a clinically trivial 7% early departure trips a 0.05 gate 4 times in 15 runs versus once at 0.01 — a gate that fires on trivia only teaches people to override it. |
| **Review band** `PH_ALPHA_REVIEW` | 0.01 ≤ min p < 0.05, minimum over the `rank` **and** `km` transforms | Not blocking, but the run may **not** be described as satisfying proportional hazards. Measured at n≈500, a real and clinically major early-only effect (HR 0.5 → 1.0) lands in this band in 9 of 40 simulations — blocking those would be wrong (precision is poor at that n) and reassuring about them is worse. |

Consequences of a borderline result, all automatic:

- `borderline: true` in `*_ph_test.json`, plus `borderline_variables`
- a `[QC_WARNING]` that `run_pipeline.py`'s `extract_qc_warnings()` collects into `step.qc_warnings[]`, so it reaches the manifest and reviewer-challenge domain 5 rather than dying in scrollback
- **the reassuring sentence is banned.** The footnote never says "No individual covariate violated the assumption" — it says "No covariate crossed alpha = 0.01; minimum Schoenfeld p = 0.011 (borderline 0.01–0.05, see diagnostics plot; the assumption is NOT established)". A p = 0.034 real departure with a reassurance printed next to it is the statistical-wording failure in reverse.
- an **effect size** next to the p-value: `ph_split_hr()` reports the exposure HR before and after a landmark split at the median event time (`hr_early` / `hr_late` in the JSON and the footnote). A Schoenfeld p answers "is there evidence", never "how much", and in the band the magnitude is what a reviewer needs. The split point is data-driven, so it is labelled a **diagnostic** — it must not appear in a manuscript as a pre-specified subgroup effect.

The gate deliberately uses **one** transform. Taking the minimum p over both into the gate would inflate its false-positive rate, which is the thing `PH_ALPHA` exists to prevent.

**Three outcomes, kept distinct.** `ph_test.json` always carries a `status`, because “we could not test it” and “there was nothing to test” are different facts and collapsing them is how a fail-open bug gets in:

| `status` | Means | Gate |
|---|---|---|
| `computed` | The test ran | see the remedy table below |
| `not_computed` | A Cox model fitted but the residuals could not be produced (numerical failure, degenerate event times) | **`[QC_BLOCKING]` → exit 2, unconditionally** — an un-computable PH test is not a passing PH test, and a declared remedy does not rescue it |
| `not_applicable` | No fitted Cox model at all (convergence already failed, which is blocking on its own) | `[QC_WARNING]` |

**Remedy must be pre-specified.** `ph_violation_remedy` is declared in the plan before the test runs:

| Situation | Behaviour |
|---|---|
| No violation | `pass`; the PH numbers still go into the footnote, JSON and plot |
| Violated, **no** `ph_violation_remedy` | `[QC_BLOCKING]` → **exit 2** |
| Violated, remedy = `disclose` | `[QC_WARNING]` — HRs are averaged over follow-up; state it in Limitations **against a decision-log ID** (`ph_disclose_decision_id`). Without that ID the manuscript-stage gate blocks: a zero-cost disclosure is not a remedy |
| Violated, remedy = `stratify` / `time_varying` / `rmst` | `[QC_WARNING]` — this skill does **not** run those analyses; the Sheet 1 HRs are unremediated and must not be reported as the primary estimate until the declared analysis has been run as its own step. all three now have shipped generators and the pipeline adds the step for you; what this skill will not do is compute any of them itself |
| `ph_violation_remedy` set to an unrecognised value | `[QC_BLOCKING]` (typo must not read as a valid pre-specification) |

**"Declared", not "pre-specified".** This script cannot see history, so it does not vouch for a chronology it has no way to verify — the footnote reads `Declared remedy: X (provenance: research_plan.json; see decision log)`. What actually makes the declaration credible lives outside this skill: the remedy is declared in `research_plan.json$.outcomes[]`, which is inside reviewer-challenge's `FINGERPRINT_FIELDS`, so filling it in after seeing the result moves the plan fingerprint and invalidates the existing challenge (measured: `33695bb3116d2343` → `24b2cabc1059aef9`).

**The downgrade is checked later.** `biostats-guardian/scripts/ph_remedy_gate.py` runs before the manuscript and blocks if a declared remedy has no artifact (or a `disclose` has no decision-log ID). Without it, "declared" would be a free pass — which is what it was until 2026-08-12.

**Artefacts** (written next to `output_file`):

- `<output_base>_ph_test.json` — **written for every status**, including the failures: an artifact that records “could not be computed” is what lets a downstream auditor tell that apart from “never ran”. On `computed` it carries global + per-variable chi-square, p, `violating_variables`, threshold, n_events.
- `<output_base>_ph_diagnostics.png` — scaled Schoenfeld residuals vs transformed time, one panel per covariate with a trend line; a slope is the visual counterpart of a small p. Borderline covariates are labelled `[borderline]` and the title carries the band. Only written on `computed`.
- `effect_size` inside the JSON — `hr_early` / `hr_late` / `split_time` / CIs, with `method` stating in words that the cut point is data-driven and diagnostic-only.
- A footnote line on Sheet 1 carrying the global p, the violating covariates and the pre-specified remedy, so the assumption check travels with the table. On a failed test the footnote reads `NOT TESTED (<status>) — <reason>`, never a blank.

Logistic models skip all of the above (no PH assumption to test).

**Time scale.** For a Cox run the skill checks that the outcome declared `time_unit` /
`time_scale` and emits `[QC_WARNING] time_scale_assumed` when it did not. `kaplan-meier`
and `competing-risk` receive those fields from `generate_configs.resolve_time_scale()`
and warn already; the Cox route never received either, so the same undeclared plan was
flagged on one route and silent on the other. The warning states the scope precisely:
**the adjusted HRs are unaffected** — Cox uses only the ordering of event times, so a
constant rescaling cannot move them — but every time-denominated number reported here,
including the PH early/late split point, is in raw column units.

### Sheet 2: Interaction Analysis

For each covariate X:
1. **Stratified models**: fit the FULL multivariate model separately in Group 1 and Group 2 -> report adjusted HR/OR for X in each subgroup
2. **p-interaction**: in the overall dataset, fit a model with all covariates + grouping variable + (grouping x X) interaction term -> extract p-value of the interaction term

This tests whether the prognostic effect of each covariate differs between the two groups.

**Minimum thresholds**: n >= 10 and events >= 5 per subgroup, otherwise the variable is marked as "N/A" for that subgroup.

**p-value formatting**: `<0.001*` for p < 0.001, `x.xxx*` for p < 0.05, `x.xxx` for p >= 0.05.

---

## Output Description

### Sheet 1: "Multivariate Analysis"
- **Row 1**: Title (dark blue background)
- **Row 2**: Subtitle with sample sizes and event counts
- **Row 3-4**: Column headers -- Variable | Coefficient | Adjusted HR/OR (95% CI) | p-value
- **Data rows**: Section headers (light blue) followed by variable rows with alternating shading
- **Footnotes**: Abbreviations and statistical notes

### Sheet 2: "Interaction Analysis"
- **Row 1**: Title (dark blue background)
- **Row 2**: Subtitle with per-group sample sizes
- **Row 3-4**: Column headers -- Variable | [N (events) | Adj. HR/OR (95% CI) | p-value] x 2 groups | p-interaction
- **Data rows**: Section headers (light blue) followed by variable rows with alternating shading
- **Footnotes**: Abbreviations and interaction analysis notes

---

## Example Usage

**User**: "I want to run multivariate Cox regression for HFpEF patients with interaction analysis. Data is in TSOC_data_merge.xlsx, filter for HF_type==3, group by AF_hx (1=AF, 0=No AF). Time variable: time_composite, event: event_composite. Variables: age (per 10 yrs), gender, BMI (per 5), HTN_hx, DM_hx, LVEF, NT-proBNP. Test interaction for all variables."

**Claude's response**: Generates the JSON config, runs missing data check, presents results, then generates the formatted Excel with multivariate analysis + interaction analysis.

---

## Pipeline Integration

When called from the `research-plan` orchestrator pipeline:

- Config is pre-generated at `configs/{step_id}_config.json` by `generate_configs.py`
- Skip Steps 1–4 (interactive interview + column confirmation); proceed directly to Step 5 (check missing data) and Step 6 (execute)
- Exit code 0 = success, non-zero = failure (triggers retry then error in pipeline)
- QC warnings are emitted to stderr with `[QC_WARNING]` prefix for pipeline collection
- QC blocking issues are emitted to stderr with `[QC_BLOCKING]` prefix (step marked as error)

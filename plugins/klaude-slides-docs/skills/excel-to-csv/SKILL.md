---
name: excel-to-csv
description: "Merge a multi-sheet medical research Excel file into one CSV. Trigger: Excel to CSV, merge Excel sheets, combine Excel sheets, flatten workbook, consolidate sheets, merge worksheets, 合併試算表, Excel合併, 多試算表合併, 資料合併成CSV, 合併工作表, Excel轉CSV, 多個sheet合成一個, 把Excel變成CSV, 把多張表合起來, merge multi-sheet Excel, convert Excel to single CSV, 幫我把Excel合併成一個CSV, merge the sheets into one file, 把多個試算表合成一個檔案, 幫我合併工作表."
---

# Excel to CSV: Multi-Sheet Medical Research Data Merger

需求：`pip install pandas openpyxl`。

This skill processes a multi-sheet Excel workbook (typical of clinical registry data) into a single, analysis-ready CSV file. It handles the complexities of longitudinal clinical data: deduplication, baseline extraction, outcome computation, column merging, and derived variable calculation.

## When to use

- The user has a multi-sheet Excel file from a clinical registry or research database
- They want to flatten it into a single CSV with one row per subject
- The data contains a mix of baseline sheets, longitudinal follow-up sheets, and outcome data

## Core workflow

1. **Read** all sheets from the input Excel file
2. **Classify** each sheet as baseline (one row per subject) or longitudinal (multiple visits)
3. **Extract** baseline data (earliest visit or Visit == 1) from longitudinal sheets
4. **Extract** outcome data from Follow Up sheets (death, hospitalization events)
5. **Merge** all sheets on the subject ID column (left join from the master Visit Date sheet)
6. **Merge paired columns** (e.g., admission vs outpatient vitals) into unified columns
7. **Compute derived variables** (date-to-day conversions, echo metrics, midpoint outcomes)
8. **Save** as a single CSV

## Step-by-step instructions

### Step 1: Explore the Excel file

Read the input Excel file and list all sheet names. For each sheet, inspect:
- Column names
- Number of rows and unique subject IDs
- Whether there's a "Visit" column indicating longitudinal data
- Sample rows to understand data types

Print a summary for the user to confirm the structure.

### Step 2: Identify the subject ID column and enrollment date

Look for columns like `Subject_num`, `SubjectID`, `PatientID`, etc. Also identify the enrollment/baseline date column (e.g., `Enrollment_Date`).

The **Visit Date** sheet (or equivalent) is typically the master sheet containing:
- Subject ID
- Enrollment date
- Follow-up visit dates (Follow_up_1_Date, Follow_up_2_Date, ...)

This sheet serves as the base for all left joins.

### Step 3: Process each sheet

Use the bundled script `${CLAUDE_SKILL_DIR}/scripts/merge_excel_to_csv.py`. Run it with:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/merge_excel_to_csv.py "<input_excel>" "<output_csv>"
```

If the script doesn't cover the user's exact data structure (different column names, different sheets), **adapt the script** or write a custom version following the logic below.

### Step 4: Processing logic reference

#### 4a. Baseline sheets (one row per subject)
Sheets like DG_Overall, MH, Etiology, Lab_Admission, Lab_OPD, etc.
- Read the sheet
- Drop helper columns (Center_num, Subject_Is) before merging
- Deduplicate by Subject_num (keep first)
- Left join to the master dataframe on Subject_num

#### 4b. Longitudinal sheets with Visit column
Sheets like ECHO and ECG (Visit_echo), CM_Part I/II (Visit_cm_part_1/2)
- **For baseline data**: filter where Visit == 1 (or the earliest visit number), then treat as baseline
- **For follow-up data**: the user will specify which visit to extract

#### 4c. Follow Up / Outcome sheet
Contains longitudinal outcome data (one row per follow-up visit per subject). Key logic:

**Death outcome:**
- Find the row where `Death_fu == 1` for each subject
- Extract `Date_of_death_fu`
- Compute `Death_Day = Date_of_death_fu - Enrollment_Date` (in days)

**Event outcomes without exact dates (midpoint method):**
For events recorded at follow-up visits (e.g., `Un-planned_HF_hos_fu`):
1. Find the **first** visit where the event == 1 for each subject
2. Get the visit number `x` from the Visit column (e.g., Visit_fu)
3. Calculate:
   - `D1 = Follow_up_{x-1}_Date - Enrollment_Date` (days from enrollment to the visit before the event was recorded)
   - `D0 = Follow_up_{x-2}_Date - Enrollment_Date` (days from enrollment to two visits before). If `Follow_up_{x-2}_Date` doesn't exist, `D0 = 0`
4. `Event_Day = (D0 + D1) / 2`
5. **Constraint**: If `Event_Day >= Death_Day`, then `Event_Day = (D0 + Death_Day) / 2`

#### 4d. Merge paired columns (admission vs outpatient)
When the same measurement exists from two sources (e.g., `HR_Ad` / `HR_opd`):
- Create a unified column (e.g., `HR`) using coalesce: take the admission value first, fall back to outpatient
- Delete the original paired columns

Common pairs: HR, SBP, DBP, Height, Weight, NYHA

#### 4e. Derived clinical variables

The script currently includes the following default formulas (from an example heart-failure registry dataset). These are computed only if source columns exist. Round all derived values to 2 decimal places.

| Variable | Formula |
|----------|---------|
| BSA | sqrt(Height * Weight / 3600) |
| LAVi | LA / BSA |
| RAP | 5 if JVP_over_6cm==0, 10 if JVP_over_6cm==1 |
| PASP | 4 * (TR_vel/100)^2 + RAP |
| E/e' | E_vel / ((Tissue_E_Septal + Tissue_E_Lateral) / 2) |
| LVEF | 100 * (LVEDV - LVESV) / LVEDV |
| RWT | 2 * LVPW / LVEDD |
| LVM | 0.8 * 1.04 * ((IVS/10 + LVEDD/10 + LVPW/10)^3 - (LVEDD/10)^3) + 0.6 |
| LVMi | LVM / BSA |

**⚠️ 重要：以上公式僅適用於 範例 HF registry 資料集，不可直接套用於其他研究資料。**

處理任何 Excel 檔案時，一律遵循以下萬用流程：
1. **先詢問使用者**：「請問這份資料是否為 範例 HF registry 資料集？是否有需要額外計算的衍生欄位？請提供公式（格式：`新欄位名 = 公式`）」
2. **若使用者確認為 範例 HF registry 資料集**：套用上方預設公式，並詢問是否需要新增或修改
3. **若為其他研究資料集**：**不套用上方預設公式**，僅使用使用者提供的自訂公式。修改 `scripts/merge_excel_to_csv.py` 中的 `compute_derived_variables()` 函數，替換為使用者提供的新公式
4. 如果使用者沒有提供任何公式，跳過衍生變數計算步驟即可

### Step 5: Save and verify

- Save the merged dataframe to CSV
- Print summary: total rows, total columns, number of unique subjects
- Print sample of key computed columns for verification
- Flag any subjects with unexpected duplicates

## Important notes

- Always convert dates with `pd.to_datetime(..., errors='coerce')` to handle mixed date formats
- Use `combine_first()` for column merging (coalesce pattern)
- Strip non-breaking spaces (`\xa0`) from column names when matching
- The Follow Up sheet's Visit_fu typically starts at 2 (not 1), because Visit 1 is the enrollment visit
- When computing midpoint outcomes, the visit index mapping is: Visit_fu=2 → Follow_up_1_Date, Visit_fu=3 → Follow_up_2_Date, etc.
- If the user's Excel has a different structure, ask them to confirm sheet names and key columns before proceeding

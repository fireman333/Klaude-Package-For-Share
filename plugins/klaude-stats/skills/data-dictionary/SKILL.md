---
name: data-dictionary
description: "Generate codebook-style Data Dictionary CSV (類別/name/label/values, TTM format) from Excel/CSV. Trigger: data dictionary, codebook, variable list, data dictionary CSV, generate data dictionary, create codebook, variable documentation, 資料字典, 代碼表, 變數清單, 欄位說明, 資料說明表, 做代碼表, 產生資料字典, 建立變數說明, 幫我做資料字典, generate a data dictionary, 建立變數說明表. If clean/encode data too, route to raw-data-processing."
---

# Data Dictionary Generator

Generate a codebook-style CSV documenting all variables in an Excel or CSV file.

**Disambiguation**: if the user wants to clean/encode data AND generate a dictionary together, route to the `raw-data-processing` skill instead.

**Output format** (4 columns, matches `TTM Dictionary.csv`):

| 類別 | name | label | values |
|------|------|-------|--------|
| 病人基本資料 | sex | Sex | `{0, Female}{1, Male}` |
| | age | age | None |

- **類別**: Category/section group — left blank by script, user fills in manually
- **name**: Column name as-is from the data
- **label**: Auto-derived from column name (underscores → spaces)
- **values**: `{v1}{v2}...` for categorical/binary columns; `None` for continuous/date

---

## Workflow

Follow these steps in order every time this skill is triggered.

### Step 1: Gather Requirements

Ask the user for the following (skip items already provided):

1. **Input file path** — `.xlsx`, `.xls`, or `.csv`
2. **Output CSV path** — (optional; default: same folder as input, filename `Data_Dictionary.csv`)
3. **Sheet to process** — for multi-sheet Excel files only (default: first sheet; script will list all available sheets)

### Step 2: Run Script

```bash
python ${CLAUDE_SKILL_DIR}/scripts/generate_data_dictionary.py "INPUT_FILE" "OUTPUT_CSV" [--sheet "SHEET_NAME"]
```

- If the input is a multi-sheet Excel and the user hasn't specified a sheet, first run without `--sheet` to see the sheet list printed by the script, then re-run with the user's choice.
- Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory (the directory containing this SKILL.md file).

### Step 3: Present Results

After the script completes, tell the user:

- **Output file location**
- **Total variables** documented
- **Breakdown**: how many have `values` auto-detected vs `None`
- **Next steps reminder**: the `類別` column is blank — user should fill in category groupings; the `label` column may need Chinese translation or editing.

---

## Notes

- Values are sorted ascending before formatting.
- For numeric codes (0/1, 1/2/3...): output `{0}{1}` or `{1}{2}{3}` — user should add the label text after the comma.
- For text values (Male/Female, Yes/No): output `{Female}{Male}` directly.
- Output CSV uses UTF-8-BOM encoding so it opens correctly in Excel on Mac/Windows.

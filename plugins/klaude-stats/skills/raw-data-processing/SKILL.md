---
name: raw-data-processing
description: "Process raw medical research Excel/CSV data into cleansed data + a data dictionary. Trigger: raw data processing, data cleaning, data cleansing, data dictionary, data preprocessing, codebook, variable encoding, prepare raw data, data wrangling, 資料清理, 代碼表, 原始資料處理, 資料前處理, 資料編碼, 資料字典, 變數編碼, 整理原始資料, 幫我整理資料, 幫我清理資料, process this raw data, 做資料清理和代碼表, 幫我做資料前處理. Merging Excel sheets → excel-to-csv."
---

# Raw Data Processing Assistant

Process raw medical research Excel/CSV files (with metadata rows, verbose headers, text-encoded values) into:
1. **Cleansed Data** (Excel) — headers in row 1, encoded values, clean column names
2. **Data Dictionary** (Excel) — column mappings, variable types, encoding tables, units

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Raw data file path** — xlsx or csv
2. **Output cleansed data file path** — xlsx
3. **Output data dictionary file path** — xlsx
4. **Sheets to skip** (optional) — e.g., Cover, TOC pages (auto-detected during scan)
5. **Special instructions** (optional) — any known column name preferences, encoding conventions, or sheets to combine

### Step 2: Scan Raw Data

Run the script in `--scan` mode to auto-detect structure:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/process_raw_data.py --scan "INPUT_FILE" --scan-output /tmp/raw_data_scan.json
```

This produces a JSON report with per-sheet information:
- Detected header row and data start row
- Metadata text above headers (title, population description)
- All column names with sample unique values (up to 20 per column)
- Auto-suggested variable types (binary, categorical, continuous, date, id, text)
- Flags for duplicate headers, Chinese column names, split-row headers

**Present to the user**: A readable summary showing sheets found, column counts, detected types, and any anomalies. Ask the user to confirm which sheets to process and flag any corrections.

### Step 3: Generate JSON Config

Based on the scan report, propose column name simplifications and encodings. Write the JSON config to `/tmp/raw_data_config.json`.

**Column naming conventions**:
- Strip trailing spaces and non-breaking spaces (`\xa0`)
- Replace remaining spaces with `_`
- Shorten verbose names (e.g., "History of previous heart failure hospitalization" → "HF_hos_hx")
- Disambiguate duplicate column names (e.g., two "Smoking" columns → "Smoking_details" and "Smoking_hx")
- Use lowercase for simplified names where appropriate

**Encoding conventions**:
- Binary text (Yes/No) → 1/0
- Binary text with positive meaning (Inpatient/Outpatient) → 1/0 where the "positive" or "first" value is 1
- Categorical text → integer encoding starting from 1
- Dates → standardize to YYYY-MM-DD format
- Numeric values → keep as-is, classify type in dictionary

### Step 4: User Review

Present the proposed config to the user in a readable per-sheet table format:

| Original Name | New Name | Type | Encoding |
|---|---|---|---|
| Subject Is | Inpatient | binary | 1=Inpatient, 0=Outpatient |
| HF phenotype | HF_type | categorical | 1=HFrEF, 2=HFmrEF, 3=HFpEF |

Ask user to approve or request modifications before proceeding.

### Step 5: Execute Processing

Run the script in processing mode:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/process_raw_data.py /tmp/raw_data_config.json
```

This produces:
- **Cleansed Data Excel**: One sheet per processed sheet, headers in row 1, encoded values
- **Data Dictionary Excel**: Summary sheet + Column_Mapping sheet + Codes sheet + Units sheet (if applicable)

### Step 6: Present Results

After execution, tell the user:
- Output file locations
- Number of sheets processed
- Total rows per sheet
- Number of columns renamed, encoded, and type-classified
- Any warnings (columns with all-null values, unrecognized patterns, unmapped values)

Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory: the directory containing this SKILL.md file.

---

## JSON Config Schema

```json
{
  "input_file": "/absolute/path/to/raw.xlsx",
  "output_data_file": "/absolute/path/to/cleansed.xlsx",
  "output_dict_file": "/absolute/path/to/dictionary.xlsx",
  "skip_sheets": ["Cover"],
  "sheets": {
    "SheetName": {
      "header_row": 5,
      "data_start_row": 6,
      "description": "Section title from metadata rows",
      "metadata_text": "Population: All Subjects in Database",
      "columns": {
        "Original Column Name": {
          "new_name": "clean_name",
          "type": "binary",
          "encoding": {"Yes": 1, "No": 0},
          "description": "Human-readable description for data dictionary"
        },
        "Another Column": {
          "new_name": "another_col",
          "type": "continuous",
          "encoding": null,
          "description": "Continuous measurement"
        }
      }
    }
  }
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `input_file` | Yes | Absolute path to the raw data file (xlsx or csv) |
| `output_data_file` | Yes | Absolute path for the cleansed data output (xlsx) |
| `output_dict_file` | Yes | Absolute path for the data dictionary output (xlsx) |
| `skip_sheets` | No | Array of sheet names to skip (e.g., Cover, TOC) |
| `sheets` | Yes | Object with per-sheet configurations |

### Per-Sheet Config

| Field | Required | Description |
|-------|----------|-------------|
| `header_row` | Yes | 1-indexed row number containing column headers |
| `data_start_row` | Yes | 1-indexed row number where data begins |
| `description` | No | Section title extracted from metadata |
| `metadata_text` | No | Additional metadata text (population, notes) |
| `columns` | Yes | Object mapping original column names to their config |

### Per-Column Config

| Field | Required | Description |
|-------|----------|-------------|
| `new_name` | Yes | Simplified column name for cleansed data |
| `type` | Yes | Variable type: `binary`, `categorical`, `continuous`, `date`, `id`, `text` |
| `encoding` | No | Mapping of original values to encoded integers (null for continuous/date/id) |
| `description` | No | Human-readable description for data dictionary |
| `date_format` | No | Target date format (default: YYYY-MM-DD) |

### Variable Types

- **binary**: Two possible values (Yes/No, Male/Female, 0/1). Encoded as 1/0.
- **categorical**: Multiple discrete categories. Encoded as integers starting from 1.
- **continuous**: Numeric measurements. Kept as-is.
- **date**: Date values. Standardized to YYYY-MM-DD.
- **id**: Identifier columns (Subject No., Center No.). Kept as-is.
- **text**: Free-text fields. Kept as-is or noted in dictionary.

---

## Data Dictionary Output Format

The data dictionary Excel contains these sheets:

### Sheet "Summary"
| Sheet Name | Description | Population | Row Count | Column Count |
|---|---|---|---|---|
| DG_Overall | 2.1 Listing of Demographics (Overall) | All Subjects in Database | 2456 | 18 |

### Sheet "Column_Mapping"
| Sheet | Original_Name | New_Name | Type | Encoding | Description |
|---|---|---|---|---|---|
| DG_Overall | Center No. | Center_num | continuous | | Center number |
| DG_Overall | HF phenotype | HF_type | categorical | 1=HFrEF, 2=HFmrEF, 3=HFpEF | HF phenotype |

### Sheet "Codes" (compact encoding reference)
Grouped by variable, showing value-label pairs in a compact layout.

### Sheet "Units" (if applicable)
Lab units extracted from unit columns or metadata.

---

## Example Usage

**User**: "幫我清理這個原始資料：/path/to/raw_data.xlsx，輸出 cleansed data 和 data dictionary"

**Claude's response**:
1. Runs `--scan` on the raw file
2. Presents sheet/column summary to user
3. Proposes column name simplifications and encodings
4. After user approval, processes the data
5. Reports output file locations and summary statistics

---
name: flowchart
description: "Publication-ready CONSORT flowchart (Figure 1) w/ auto exclusion counts; PNG+Excel. Trigger: flowchart, flow chart, CONSORT diagram, patient selection diagram, inclusion exclusion criteria, study flow, enrollment diagram, patient screening, Figure 1, study enrollment diagram, exclusion diagram, exclusion flowchart, 流程圖, 篩選流程圖, 收案流程, 排除流程, CONSORT圖, 病人篩選, 畫Figure 1, 納入排除流程圖, 畫收案流程, 幫我畫流程圖, make a flowchart, 做篩選流程圖, draw patient selection diagram."
---

# CONSORT-Style Patient Selection Flowchart Generator

Generate a publication-ready CONSORT-style patient selection flowchart (typically used as Figure 1 in clinical research papers). Automatically computes how many patients are excluded at each step by applying filter conditions to the data, producing a vertical flowchart with boxes, arrows, and exclusion annotations. Also outputs an Excel summary of counts at each step.

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Data file path** — xlsx, csv, or other pandas-readable format
2. **Data filters** (optional) — conditions to apply to the raw data before starting the flowchart (e.g., select a specific registry)
3. **Derived variables** (optional) — new columns to compute before exclusion steps:
   - `coalesce` type: pick the first non-null from a list of columns
   - `expression` type: compute from existing columns
4. **Initial box label** — text for the first box (e.g., "Patients in TSOC HFpEF Registry\n(2014–2024)")
5. **Exclusion steps** — ordered array, each with:
   - `label`: exclusion reason text displayed in the side box (e.g., "Missing follow-up data")
   - `condition`: pandas-compatible condition string that identifies rows **to exclude** (e.g., `"follow_up_time.isna()"`)
   - Alternatively, `keep_condition`: condition that identifies rows **to keep** (e.g., `"age >= 18"`)
6. **Final box label** — text for the last box (e.g., "Final study cohort")
7. **Group split** (optional) — at the end, split into subgroups:
   - `column`: grouping column name
   - `groups`: array of `{"value": ..., "label": "..."}` pairs
8. **Plot settings** (optional) — font size, box width, colors, figure size
9. **Output file path** (base name; generates `.png` and `.xlsx`)

### Step 2: Validate Data

Before generating the config, read the data file to confirm:
- The file exists and is readable
- All columns referenced in exclusion conditions exist
- If group split is specified, the grouping column exists with expected values

Run a quick Python snippet:
```python
import pandas as pd
df = pd.read_excel("path")  # or read_csv
print(f"Shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
```

### Step 3: Generate JSON Config

Write a JSON config file **alongside the output file**, using the same base name with `_config.json` suffix (e.g., if `output_file` is `/path/to/Flowchart.xlsx`, save config as `/path/to/Flowchart_config.json`). This ensures the config persists for future re-runs. The schema is documented below.

### Step 4: Check Counts (Preview)

Run the script in preview mode:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/flowchart.py /tmp/flowchart_config.json --preview
```

This prints the patient counts at each step without generating the figure. Present the counts to the user for verification before generating the final flowchart.

### Step 5: Execute

Run the full script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/flowchart.py /tmp/flowchart_config.json
```

This produces:
- Flowchart image (`.png`)
- Excel file (`.xlsx`) with step-by-step counts

### Step 6: Present Results

After execution, tell the user:
- Output file locations (png and xlsx)
- Initial N and final N
- Number of exclusion steps and total excluded
- If group split: N per group

Replace `${CLAUDE_SKILL_DIR}` with the actual path to this skill directory: the directory containing this SKILL.md file.

### Step 7: Save Reusable Script

After presenting results, make the analysis **re-runnable** so the user can modify exclusion criteria without re-triggering this skill:

1. Copy the Python script to the same directory as the output file:
```bash
cp ${CLAUDE_SKILL_DIR}/scripts/flowchart.py <OUTPUT_DIR>/flowchart.py
```

2. The JSON config file (from Step 3) is already saved alongside the output file.

3. Tell the user the following re-run instructions:
   - **Config file**: `<CONFIG_PATH>` (the JSON saved in Step 3)
   - **Script**: `<OUTPUT_DIR>/flowchart.py`
   - **Re-run command**: `python <OUTPUT_DIR>/flowchart.py <CONFIG_PATH>`
   - **Common modifications** (edit the config JSON directly):
     - Add/remove exclusion steps: edit `exclusion_steps` array
     - Change group split: edit `group_split` object
     - Change labels: edit `initial_label`, `final_label`
     - Adjust plot: edit `plot_settings`
   - After editing, just ask Claude to run: `python <OUTPUT_DIR>/flowchart.py <CONFIG_PATH>`

Replace `<OUTPUT_DIR>` with the directory containing the output xlsx file, and `<CONFIG_PATH>` with the actual config file path.

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
    }
  ],
  "initial_label": "Patients in TSOC HFpEF Registry\n(2014–2024)",
  "exclusion_steps": [
    {
      "label": "Age < 20 years",
      "condition": "age < 20"
    },
    {
      "label": "Missing baseline echocardiography",
      "condition": "LVEF.isna()"
    },
    {
      "label": "Follow-up < 30 days",
      "keep_condition": "follow_up_days >= 30"
    }
  ],
  "final_label": "Final study cohort",
  "group_split": {
    "column": "AF_hx",
    "groups": [
      {"value": 1.0, "label": "AF group"},
      {"value": 0.0, "label": "Non-AF group"}
    ]
  },
  "plot_settings": {
    "figsize": [10, 14],
    "dpi": 300,
    "main_box_width": 0.50,
    "main_box_color": "#D6E4F0",
    "exclude_box_color": "#FADBD8",
    "final_box_color": "#D5F5E3",
    "group_box_color": "#D6E4F0",
    "font_size": 10,
    "title_font_size": 11,
    "arrow_color": "#333333",
    "border_color": "#2C3E50"
  },
  "output_file": "/absolute/path/to/Flowchart.xlsx"
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `data_file` | Yes | Absolute path to the data file |
| `filters` | No | Array of filter conditions applied to raw data |
| `derived_variables` | No | Array of new columns to compute |
| `initial_label` | Yes | Text for the first (top) box |
| `exclusion_steps` | Yes | Ordered array of exclusion steps |
| `final_label` | Yes | Text for the final box |
| `group_split` | No | Split the final cohort into subgroups |
| `plot_settings` | No | Visual customization (see below) |
| `output_file` | Yes | Output path (.xlsx); PNG uses same base + .png |

### Exclusion Step Fields

Each exclusion step must have either `condition` or `keep_condition` (not both):

| Field | Description |
|-------|-------------|
| `label` | Text displayed in the exclusion side-box |
| `condition` | Pandas eval/query expression identifying rows **to exclude** |
| `keep_condition` | Pandas eval/query expression identifying rows **to keep** |

**How conditions work:**
- `condition`: rows matching this expression are **removed** (e.g., `"age < 20"` removes patients under 20)
- `keep_condition`: rows matching this expression are **kept** (e.g., `"age >= 20"` keeps patients 20 and older)
- For `.isna()` or `.notna()` checks, the script uses `df.eval()` or `df.query()` with pandas syntax

### Plot Settings

| Field | Default | Description |
|-------|---------|-------------|
| `figsize` | `[10, 14]` | Figure size in inches `[width, height]` |
| `dpi` | `300` | Plot resolution |
| `main_box_width` | `0.50` | Width of main flow boxes (0–1 fraction of figure) |
| `main_box_color` | `"#D6E4F0"` | Light blue for main boxes |
| `exclude_box_color` | `"#FADBD8"` | Light red for exclusion boxes |
| `final_box_color` | `"#D5F5E3"` | Light green for the final box |
| `group_box_color` | `"#D6E4F0"` | Color for group split boxes |
| `font_size` | `10` | Data text font size |
| `title_font_size` | `11` | Box title font size |
| `arrow_color` | `"#333333"` | Arrow color |
| `border_color` | `"#2C3E50"` | Box border color |

### Filter Operators

Supported: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

---

## Output Description

### Flowchart (`.png`)
- Vertical flow: top to bottom
- **Main boxes** (light blue): show remaining patient count after each step
- **Exclusion side-boxes** (light red): branch to the right, showing exclusion reason and count excluded
- **Arrows**: connect boxes vertically (main flow) and horizontally (to exclusion boxes)
- **Final box** (light green): final cohort with total N
- **Group split** (optional): final box branches into 2+ group boxes at the bottom
- Publication-ready: 300 DPI, clean layout, proper spacing, readable text

### Excel File (`.xlsx`)
- **Row 1**: Title (dark blue background, white text)
- **Column headers**: Step | Description | N Excluded | N Remaining
- **Data rows**: One per step with alternating shading
- **Final row**: Final cohort count
- **Group rows** (if applicable): N per group

---

## Example Usage

**User**: "I need a flowchart for my HFpEF study. Data is in TSOC_data_merge.xlsx. Start with all patients (filter HF_type==3). Exclude: age < 20, missing LVEF, missing follow-up data (time_death is NA), follow-up < 30 days. Final cohort splits into AF (AF_hx==1) vs No AF (AF_hx==0)."

**Claude's response**: Generates the JSON config, runs preview to verify counts, then produces the CONSORT-style flowchart PNG and Excel summary.

---

## Pipeline Integration

When called from the `research-plan` orchestrator pipeline:

- Config is pre-generated at `configs/{step_id}_config.json` by `generate_configs.py`
- Skip Steps 1–3 (interactive interview); proceed directly to Step 4 (check missing data) and Step 5 (execute)
- Exit code 0 = success, non-zero = failure (triggers retry then error in pipeline)
- QC warnings are emitted to stderr with `[QC_WARNING]` prefix for pipeline collection
- QC blocking issues are emitted to stderr with `[QC_BLOCKING]` prefix (step marked as error)

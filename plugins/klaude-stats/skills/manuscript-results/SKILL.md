---
name: manuscript-results
description: "Drafts a publication-ready manuscript Results section (.docx) from Excel outputs of table1/univariate-forest/multivariate-interaction/kaplan-meier/competing-risk/psm-matching/auc-cstat, in academic English or Traditional Chinese. Trigger: write results, results section, manuscript results, draft results, compose results, generate text from analysis, convert tables to text, write manuscript, results paragraph, 寫結果, 撰寫結果, Results段落, 論文結果, generate manuscript, write up the analysis, turn results into text, 幫我寫Results, summarize analysis results into manuscript text, 把分析結果寫成文字, 寫論文結果, 把表格寫成文字, 產生Results, 幫我把分析結果寫成Results, draft the results section from these tables, 把這些表格寫成論文, write up these findings, 幫我寫論文結果."
---

# Manuscript Results Section Generator

Read analysis output files (Excel files produced by table1, univariate-forest, multivariate-interaction, kaplan-meier, competing-risk, psm-matching, auc-cstat skills) and generate a structured, publication-ready Results section as a Word document (.docx). Writes flowing academic prose — not just numbers — following STROBE/CONSORT reporting guidelines.

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Analysis output files** — paths to Excel files from each analysis skill that should be included. For each file, identify its type:
   - `table1` — Baseline characteristics table
   - `univariate` — Univariate regression results
   - `multivariate` — Multivariate regression + interaction results
   - `kaplan_meier` — KM survival analysis results
   - `competing_risk` — Competing risk CIF results
   - `psm` — Propensity score matching results
   - `auc` — AUC/C-statistics results
2. **Study design** — `cohort`, `case-control`, `cross-sectional`, or `rct`
3. **Primary outcome** — description of the primary endpoint (e.g., "composite of cardiovascular death and heart failure hospitalization")
4. **Secondary outcomes** (optional) — descriptions of secondary endpoints
5. **Group description** — how to refer to the groups in text (e.g., "patients with AF" vs "patients without AF")
6. **Table/Figure numbering** — mapping of which analysis corresponds to which table/figure number (e.g., Table 1 = baseline, Table 2 = univariate, Figure 1 = KM curve, etc.)
7. **Journal requirements** (optional) — specific formatting preferences (e.g., "Circulation style", word limit)
8. **Language** — `english` (default) or `chinese` (Traditional Chinese, 繁體中文)
9. **Output file path** — where to save the .docx file
10. **Follow-up duration description** (optional) — e.g., "median follow-up of 3.2 years (IQR, 1.8–5.1)"

### Step 2: Extract Data from Analysis Outputs

Run the extraction script to read all Excel files and produce a structured JSON summary:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/extract_data.py /tmp/manuscript_config.json
```

This reads each Excel file, identifies key numbers (sample sizes, effect estimates, p-values, survival rates, etc.), and outputs a JSON file at `/tmp/manuscript_extracted.json`.

Review the extracted data to ensure it looks reasonable before proceeding.

### Step 3: Write the Results Section

This is the core step where you compose the manuscript text. Read the extracted JSON data and the writing guide at `${CLAUDE_SKILL_DIR}/references/writing_guide.md` for standard phrases and structure.

Compose the Results section with these subsections (include only those for which data is available):

#### 3a. Study Population and Baseline Characteristics
Based on Table 1 data. Include:
- Total enrollment, final study cohort size (reference the flowchart if available)
- Group sizes
- Key demographic differences (age, sex)
- Highlight significantly different baseline variables (P < 0.05)
- Summarize that groups were comparable or note important differences

#### 3b. Primary Outcome Analysis
Based on KM, competing risk, univariate, and/or multivariate results. Include:
- Event rates per group
- Unadjusted analysis (KM/CIF with log-rank/Gray's test p-value)
- Adjusted analysis (multivariate HR/OR with 95% CI)
- Reference the survival curve figure

#### 3c. Secondary Outcome Analyses
Same structure as primary, for each secondary outcome.

#### 3d. Subgroup and Interaction Analyses
Based on multivariate interaction results. Include:
- Which interactions were significant (P-interaction < 0.05)
- Direction of effect in each subgroup
- Reference the forest plot figure

#### 3e. Sensitivity Analysis
Based on PSM results. Include:
- Matching method and caliper
- Pre- and post-matching sample sizes
- Balance achieved (max SMD)
- Results in matched cohort (HR/OR with 95% CI)
- Whether results were consistent with the primary analysis

#### 3f. Predictive/Discriminative Performance
Based on AUC/C-statistics results. Include:
- C-index or AUC of the base clinical model
- Incremental value of the variable of interest (delta C-index/AUC with P-value)

### Step 4: Generate Word Document

Run the document generation script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/generate_docx.py /tmp/manuscript_results.md /path/to/output.docx
```

Or write the .docx directly using python-docx in a Python snippet. The document should have:
- Times New Roman, 12pt font
- Double spacing
- Standard margins (1 inch / 2.54 cm)
- "Results" as the section heading
- Subsection headings as bold text
- Table/figure references in brackets: (Table 1), (Figure 2)

### Step 5: Present Results

Tell the user:
- Output file location
- Word count of the Results section
- List of subsections included
- Any [TODO: ...] placeholders that need manual completion
- Suggest reviewing for accuracy — remind that this is a draft
- Next step (suggest, don't auto-run): `/med-write audit` then `revise` on the Results text for claim-strength (NS wording, association vs causation) and LLM-tell cleanup; it never re-drafts Results from scratch and keeps every number. Other sections (Intro/Methods/Discussion) are drafted there too.


---

## JSON Config Schema

```json
{
  "analysis_files": [
    {"type": "table1", "path": "/path/to/Table1.xlsx"},
    {"type": "univariate", "path": "/path/to/Univariate_Forest.xlsx"},
    {"type": "multivariate", "path": "/path/to/Multivariate_Interaction.xlsx"},
    {"type": "kaplan_meier", "path": "/path/to/KM_Survival.xlsx"},
    {"type": "competing_risk", "path": "/path/to/CompetingRisk.xlsx"},
    {"type": "psm", "path": "/path/to/PSM_Results.xlsx"},
    {"type": "auc", "path": "/path/to/AUC_Cstat.xlsx"}
  ],
  "study_design": "cohort",
  "primary_outcome": "composite of cardiovascular death and heart failure hospitalization",
  "secondary_outcomes": ["all-cause mortality", "heart failure hospitalization"],
  "group_description": {
    "group1": "patients with atrial fibrillation",
    "group2": "patients without atrial fibrillation",
    "short1": "AF group",
    "short2": "non-AF group"
  },
  "table_figure_map": {
    "table1": "Table 1",
    "univariate": "Table 2",
    "multivariate": "Table 3",
    "kaplan_meier": "Figure 1",
    "competing_risk": "Figure 2",
    "psm": "Table 4",
    "auc": "Table 5"
  },
  "follow_up_description": "median follow-up of 3.2 years (interquartile range, 1.8–5.1)",
  "language": "english",
  "journal_style": null,
  "output_file": "/path/to/Results_Section.docx"
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `analysis_files` | Yes | Array of analysis output files with type and path |
| `study_design` | Yes | `"cohort"`, `"case-control"`, `"cross-sectional"`, or `"rct"` |
| `primary_outcome` | Yes | Description of the primary endpoint |
| `secondary_outcomes` | No | Array of secondary endpoint descriptions |
| `group_description` | Yes | Full and short names for each group |
| `table_figure_map` | Yes | Mapping of analysis type to table/figure number |
| `follow_up_description` | No | Text describing follow-up duration |
| `language` | No | `"english"` (default) or `"chinese"` |
| `journal_style` | No | Journal-specific formatting notes |
| `output_file` | Yes | Output .docx path |

### Analysis File Types

| Type | Source Skill | Key Data Extracted |
|------|-------------|-------------------|
| `table1` | table1 | Group sizes, significant baseline differences |
| `univariate` | univariate-forest | Significant predictors, unadjusted HR/OR (95% CI) |
| `multivariate` | multivariate-interaction | Independent predictors, adjusted HR/OR, P-interaction |
| `kaplan_meier` | kaplan-meier | Median survival, survival rates, log-rank P |
| `competing_risk` | competing-risk | CIF values, Gray's test P |
| `psm` | psm-matching | Matched N, SMD, post-matching HR/OR |
| `auc` | auc-cstat | C-index/AUC, delta C-index, P-value |

---

## Writing Principles

The Results section should read like a published paper, not a data dump. Read `${CLAUDE_SKILL_DIR}/references/writing_guide.md` for detailed templates and standard phrases. Key principles:

1. **Tell a story**: Start with who was studied, then present findings in logical order
2. **Every number needs context**: Don't just list HR values — explain what they mean
3. **Be precise**: HR 1.45 (95% CI, 1.12–1.88; P = 0.005), not "HR was significant"
4. **Be conservative**: P ≥ 0.05 means "was not significantly associated with", not "showed a trend toward"
5. **Reference tables/figures**: Every finding cites where to find full results
6. **No interpretation in Results**: Save discussion of mechanisms for the Discussion section

---

## Example Usage

**User**: "I've finished all the analyses for my HFpEF AF paper. Here are my output files: Table1.xlsx, Univariate_Forest.xlsx, Multivariate_Interaction.xlsx, KM_Survival.xlsx, PSM_Results.xlsx. Help me write the Results section in English."

**Claude's response**: Gathers remaining details (outcome descriptions, group names, table/figure numbering), extracts data from each Excel file, composes the Results section following the writing guide, and outputs a formatted .docx file.

---

## Pipeline Integration

When called from the `research-plan` orchestrator pipeline:

- Config is pre-generated at `configs/{step_id}_config.json` by `generate_configs.py`
- Skip Steps 1–3 (interactive interview); proceed directly to Step 4 (check missing data) and Step 5 (execute)
- Exit code 0 = success, non-zero = failure (triggers retry then error in pipeline)
- QC warnings are emitted to stderr with `[QC_WARNING]` prefix for pipeline collection
- QC blocking issues are emitted to stderr with `[QC_BLOCKING]` prefix (step marked as error)

---
name: pdf-split-by-outline
description: >
  Split a PDF file into multiple PDFs based on its outline (bookmarks/TOC) structure.
  Use this skill whenever the user wants to split, chunk, or break apart a PDF by its
  bookmarks, table of contents, outline, or chapter structure. Also trigger when the user
  says things like "拆分PDF", "按照outline拆PDF", "PDF書籤拆分", "把PDF按章節拆開",
  or asks to extract chapters/sections from a PDF into separate files.
  This skill handles multi-level outlines with customizable folder and file splitting.
---

# PDF Split by Outline

Split a PDF into separate files based on its outline (bookmark/TOC) hierarchy, with flexible control over how the split is organized.

## Quick Start

Run the bundled script with the PDF path:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/split_pdf_by_outline.py <pdf_path> [options]
```

The script auto-installs `pymupdf` if needed.

## Workflow

### 1. Inspect the outline first

Before splitting, always show the user what the outline looks like so they can choose how to split. Run:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/split_pdf_by_outline.py <pdf_path> --inspect
```

This prints the full TOC hierarchy with levels, page numbers, and entry counts per level. Present this to the user and ask how they want to split if they haven't specified.

### 2. Choose splitting mode

The script supports these options — ask the user or infer from their request:

| Option | Default | Description |
|--------|---------|-------------|
| `--folder-level N` | `1` | Which outline level becomes **folders**. Set to `0` for no folders. |
| `--split-level N` | `2` | Which outline level becomes **individual PDFs**. |
| `--output-dir PATH` | `<input>-拆分/` | Custom output directory. |
| `--no-numbering` | (numbered) | Don't prefix filenames with `01_`, `02_`, etc. |
| `--flatten` | (hierarchical) | No subfolders — all PDFs flat in output dir, filenames include parent hierarchy. |
| `--no-prefix` | (include) | Skip pages before the first bookmark (by default saved as `00_前言.pdf`). |
| `--inspect` | — | Only print the outline, don't split. |

**Common patterns:**

- **L1 → folders, L2 → PDFs** (default): `python3 ${CLAUDE_SKILL_DIR}/scripts/split_pdf_by_outline.py input.pdf`
- **L1 → PDFs only**: `python3 ${CLAUDE_SKILL_DIR}/scripts/split_pdf_by_outline.py input.pdf --folder-level 0 --split-level 1`
- **L2 → folders, L3 → PDFs**: `python3 ${CLAUDE_SKILL_DIR}/scripts/split_pdf_by_outline.py input.pdf --folder-level 2 --split-level 3`
- **All flat by L2**: `python3 ${CLAUDE_SKILL_DIR}/scripts/split_pdf_by_outline.py input.pdf --flatten`
- **Custom output**: `python3 ${CLAUDE_SKILL_DIR}/scripts/split_pdf_by_outline.py input.pdf --output-dir /path/to/output`

### 3. Run the split

Execute the script with the chosen options. The script will:
1. Read the PDF outline via `pymupdf`
2. Build a hierarchy of sections with computed page ranges
3. Create the folder structure
4. Extract each section into a separate PDF
5. Print a summary table of all generated files

### 4. Report results

After splitting, present the user with:
- Total number of files created
- Folder structure overview
- Any warnings (e.g., empty sections, missing outline)

## Edge Cases

- **No outline**: The script exits with a clear error message. Suggest the user provide page ranges manually or use a different tool.
- **Single-level outline**: If user requests `--split-level 2` but only L1 exists, the script falls back to splitting by L1 and warns the user.
- **Entries with same page**: Multiple bookmarks pointing to the same page get 0-page PDFs — the script warns about these and still creates them (they contain just that one page).
- **Pages before first bookmark**: Saved as `00_前言.pdf` by default. Use `--no-prefix` to skip.

## Dependencies

- Python 3.7+
- `pymupdf` (auto-installed by the script if missing)

---
name: marker-pdf-converter
description: >-
  Convert PDF files to high-quality markdown using the best engine for the PDF
  size, with optional chapter-by-chapter splitting based on TOC bookmarks and
  inline image extraction. Use this skill whenever the user wants to: convert
  PDF to markdown, PDF to md, split PDF chapters, extract PDF as text, markdown
  from PDF, textbook to markdown, PDF chapter split, PDF 轉 markdown, PDF 轉 md,
  PDF 轉換, 拆分章節, 轉換 PDF, 擷取 PDF 文字, 教科書轉 markdown, PDF 轉文字,
  分章節轉換, PDF 轉換含圖片. Always use this skill when the user provides a PDF
  and asks for any kind of markdown or text extraction workflow.
---

# marker-pdf-converter

Convert PDFs to markdown with optional chapter splitting and image extraction.
Default engine is **PyMuPDF native** (`get_text("dict")`), which is fast and reliable for all PDF sizes.
Override with `--engine` if needed:

| Engine | Output quality | Speed | When to use |
|--------|----------------|-------|-------------|
| **native** (default) | Heading detection, inline images | ~0.3s/chapter | All text-based PDFs |
| pymupdf4llm | Rich markdown (bold, italic, tables) | ~3s/chapter | When rich formatting is critical |
| marker-pdf | AI OCR, best for image-based PDFs | ~2 min/chapter | Scanned / image-only PDFs |

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 1: Gather Requirements

Ask for the following (skip items already provided):

1. **PDF path** — absolute path to the source PDF
2. **Output directory** — default: `<pdf_stem>-Chapters/` beside the PDF
3. **Split by chapters?** — default: yes if the PDF has TOC bookmarks; no otherwise
4. **Which chapters?** — only ask if splitting; default is all level-1 TOC headings
5. **Include images?** — default: yes (for native engine; auto-skipped for pymupdf4llm)

### Step 2: Validate Environment

```bash
python3 -c "import fitz; print('PyMuPDF ok')"
python3 -c "import pymupdf4llm; print('pymupdf4llm ok')"  # only needed for small PDFs
```

- If **PyMuPDF missing**: `pip3 install pymupdf`
- If **pymupdf4llm missing** (small PDF only): `pip3 install pymupdf4llm`
- Confirm PDF file exists and is readable
- If output directory exists, ask before overwriting

### Step 3: Check PDF Size and TOC

```python
import fitz, os
pdf = "/path/to/file.pdf"
doc = fitz.open(pdf)
size_mb = os.path.getsize(pdf) / 1024 / 1024
toc = [(l, t, p) for l, t, p in doc.get_toc() if l == 1]
print(f"{size_mb:.0f} MB, {doc.page_count} pages, {len(toc)} level-1 TOC entries")
for l, t, p in toc:
    print(f"  page {p}: {t}")
```

- Default → use `native` engine (PyMuPDF, fast and reliable for all sizes)
- If rich formatting needed → use `--engine pymupdf4llm` (slower, richer markdown)
- If scanned/image PDF → use `--engine marker` (AI OCR)
- If **no TOC** → offer whole-PDF conversion (`--all` flag)
- Show TOC to user and confirm which chapters to convert

### Step 4: Execute Conversion

Use the bundled script (handles engine selection, TOC parsing, image extraction, caching):

```bash
# Chapter-split mode — auto engine selection (recommended)
python3 ${CLAUDE_SKILL_DIR}/scripts/convert_pdf.py \
  --pdf "/absolute/path/to/file.pdf" \
  --output-dir "/absolute/path/to/output/" \
  --with-images

# Force specific chapters
python3 ${CLAUDE_SKILL_DIR}/scripts/convert_pdf.py \
  --pdf "/absolute/path/to/file.pdf" \
  --output-dir "/absolute/path/to/output/" \
  --chapters "CARDIOLOGY,PULMONARY,NEPHROLOGY" \
  --with-images

# Whole PDF as single file
python3 ${CLAUDE_SKILL_DIR}/scripts/convert_pdf.py \
  --pdf "/absolute/path/to/file.pdf" \
  --output-dir "/absolute/path/to/output/" \
  --all --with-images

# Force engine override
python3 ${CLAUDE_SKILL_DIR}/scripts/convert_pdf.py \
  --pdf "/path/to/file.pdf" \
  --engine native      # or: pymupdf4llm, marker, auto (default)
  --with-images

# Skip cache (always re-convert)
  --no-cache
```

**For large PDFs with complex section hierarchy** (PART → SECTION → Chapter):
The bundled script handles level-1 TOC entries. If you need deeper splitting (level-2/3 chapters),
adapt `convert_pdf.py` (copy it and change the TOC level filter).

### Step 5: Validate Output

After conversion:

1. Count files: `find <output_dir> -name "*.md" | wc -l`
2. Check images: `find <output_dir> -name "*.png" -o -name "*.jpeg" | wc -l`
3. Flag any `.md` file under **5 KB** as potentially incomplete
4. Show first 15 lines of a sample chapter

### Step 6: Present Results

Summarise in a table:

| File | Size | Images | Pages |
|------|------|--------|-------|
| 01-Cardiology.md | 179 KB | 3 | 19–101 |
| ... | | | |

Offer: `open "<output_dir>"`

---

## Error Handling

| Situation | Action |
|-----------|--------|
| PyMuPDF missing | `pip3 install pymupdf` |
| pymupdf4llm missing | `pip3 install pymupdf4llm` (small PDFs only) |
| marker-pdf missing | `uv tool install marker-pdf --python 3.13`（或 `pip install marker-pdf`），安裝後會提供 `marker_single` 指令 |
| uv missing | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Chapter conversion fails | Log, continue, report at end |
| Output file < 5 KB | Warn user to check that chapter |
| No TOC in PDF | Offer `--all` single-file conversion |
| Output dir exists | Ask before overwriting |
| pymupdf4llm very slow | PDF is probably ≥ 50 MB — switch to `--engine native` |

---

## Dependencies / Install

```bash
pip3 install pymupdf                 # required (native engine, default)
pip3 install pymupdf4llm             # optional (rich markdown, small PDFs)
# optional, only for scanned / image-only PDFs (AI OCR, large download of models, slow on CPU):
brew install uv && uv tool install marker-pdf --python 3.13   # or: pip install marker-pdf
```

License notes: PyMuPDF / pymupdf4llm are AGPL-3.0 (free for personal/research use; commercial redistribution needs a license from Artifex). marker-pdf (https://github.com/datalab-to/marker) code is Apache-2.0 and its model weights use a modified OpenRAIL-M license (free for research / personal use and small startups; check the repo for commercial limits). This skill does not bundle any of them — you install them yourself.

## Notes

### Engine selection rationale
- **Native PyMuPDF** (`get_text("dict")`) is the default. Opens the doc once and processes pages directly. Fast and reliable for all sizes. A 282 MB / 4273-page / 505-chapter textbook: about 143 seconds total, 2725 images embedded.
- **pymupdf4llm** produces richer markdown (bold, italic, tables) but has ~76s overhead per call — use `--engine pymupdf4llm` only when rich formatting is critical.
- **marker-pdf** requires the `marker_single` command on PATH (script also checks `~/.local/bin` and `/usr/local/bin`); MPS (Apple Silicon GPU) not supported for table recognition — runs on CPU. Use only for scanned/image-only PDFs.

### Caching
Cache is stored at `~/.cache/pdf-to-markdown/<sha256_key>/`. Key is based on file size, mtime, and mode. Use `--no-cache` to bypass. Cache is only used by the pymupdf4llm engine path.

### Images (native engine)
Images are saved to `<output_dir>/images/` (or `PART-XX/images/` for hierarchical splits).
Filter: width ≥ 80px AND height ≥ 80px AND size ≥ 4 KB — removes decorative elements.
Images are referenced inline at their correct reading position: `![Figure p.N](images/xxx.jpeg)`.

### Default chapter list (internal medicine textbooks)
`CARDIOLOGY, PULMONARY, GASTROENTEROLOGY, NEPHROLOGY, HEMATOLOGY-ONCOLOGY,`
`INFECTIOUS DISEASES, ENDOCRINOLOGY, RHEUMATOLOGY, NEUROLOGY, CONSULTS`

### Reference scripts
- `${CLAUDE_SKILL_DIR}/scripts/convert_pdf.py` — main unified script

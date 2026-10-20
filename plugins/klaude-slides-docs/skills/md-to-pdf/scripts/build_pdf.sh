#!/bin/bash
# md-to-pdf: merge markdown files into a single PDF via pandoc + typst.
# Usage:
#   build_pdf.sh --dir <path> --title <t> [--style report|handoff|textbook] \
#                [--order readme|alpha|manual] [--files "f1 f2"] [--output <path>] \
#                [--toc-depth N]  (default 2; 0 = no TOC)
#
# Engine: pandoc (md -> typst) + typst compile.
# typst is used instead of Chrome headless because Chrome-printed PDFs have a
# broken text-selection box (selecting one line jumps across lines in Preview /
# PDF Expert). typst produces proper per-line text runs -> clean selection.
# Both the in-document TOC and the side-panel bookmarks (PDF /Outlines) are
# generated natively by typst from headings — no PyMuPDF post-process needed,
# and bookmark page numbers are always exact (no text-matching heuristics).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRESETS_DIR="${SCRIPT_DIR}/presets"

DIR=""
TITLE=""
STYLE="report"
ORDER="readme"
FILES=""
OUTPUT=""
TOC_DEPTH=2

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)       DIR="$2"; shift 2 ;;
    --title)     TITLE="$2"; shift 2 ;;
    --style)     STYLE="$2"; shift 2 ;;
    --order)     ORDER="$2"; shift 2 ;;
    --files)     FILES="$2"; shift 2 ;;
    --output)    OUTPUT="$2"; shift 2 ;;
    --toc-depth) TOC_DEPTH="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -z "$TITLE" ]] && { echo "ERROR: --title required" >&2; exit 2; }
[[ -z "$DIR" && -z "$FILES" ]] && { echo "ERROR: --dir or --files required" >&2; exit 2; }

# Resolve work dir
if [[ -n "$DIR" ]]; then
  WORK_DIR="$(cd "$DIR" && pwd)"
else
  first="$(echo "$FILES" | awk '{print $1}')"
  WORK_DIR="$(cd "$(dirname "$first")" && pwd)"
fi

cd "$WORK_DIR"

# Resolve file list
declare -a FILE_LIST=()
if [[ -n "$FILES" ]]; then
  for f in $FILES; do FILE_LIST+=("$f"); done
elif [[ "$ORDER" == "readme" && -f "README.md" ]]; then
  while IFS= read -r f; do
    [[ -f "$f" ]] && FILE_LIST+=("$f")
  done < <(grep -oE '\([^)]+\.md\)' README.md | sed 's/^(//;s/)$//' | grep -v '^README\.md$')
  if [[ ${#FILE_LIST[@]} -eq 0 ]]; then
    echo "WARN: README.md has no .md links, falling back to alpha order" >&2
    ORDER="alpha"
  fi
fi

if [[ ${#FILE_LIST[@]} -eq 0 && "$ORDER" == "alpha" ]]; then
  while IFS= read -r f; do
    FILE_LIST+=("$f")
  done < <(ls *.md 2>/dev/null | grep -v '^README\.md$' | grep -v '^_merged\.md$' | sort)
fi

[[ ${#FILE_LIST[@]} -eq 0 ]] && { echo "ERROR: no .md files found in $WORK_DIR" >&2; exit 1; }

# Resolve style preset (typst)
PRESET_FILE="${PRESETS_DIR}/${STYLE}.typ"
[[ ! -f "$PRESET_FILE" ]] && { echo "ERROR: style '$STYLE' not found at $PRESET_FILE (available: report|handoff|textbook)" >&2; exit 2; }

# Resolve output
[[ -z "$OUTPUT" ]] && OUTPUT="${WORK_DIR}/${TITLE}.pdf"

# Dependencies
command -v pandoc >/dev/null || { echo "ERROR: pandoc not installed (brew install pandoc)" >&2; exit 1; }
command -v typst  >/dev/null || { echo "ERROR: typst not installed (brew install typst)" >&2; exit 1; }

# python3 with PyMuPDF — for outline-count verification only (not required to build)
PYTHON=""
for candidate in /opt/anaconda3/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
  if [[ -x "$candidate" ]] && "$candidate" -c "import fitz" >/dev/null 2>&1; then
    PYTHON="$candidate"; break
  fi
done

MERGED_MD="${WORK_DIR}/_merged.md"
MERGED_TYP="${WORK_DIR}/_merged.typ"

echo "📄 md-to-pdf (typst engine)"
echo "  workdir:    $WORK_DIR"
echo "  files:      ${#FILE_LIST[@]}"
echo "  style:      $STYLE"
echo "  order:      $ORDER"
echo "  toc-depth:  $TOC_DEPTH"
echo "  output:     $OUTPUT"
echo

# Step 1: build merged markdown
# - No manual TOC; pandoc --toc handles it
# - No leading H1; metadata title becomes the cover via standalone template
# - Each input file gets a page break before its content
{
  for i in "${!FILE_LIST[@]}"; do
    f="${FILE_LIST[$i]}"
    if [[ $i -gt 0 ]]; then
      echo
      echo '```{=typst}'
      echo '#pagebreak()'
      echo '```'
      echo
    fi
    cat "$f"
    echo
  done
} > "$MERGED_MD"

# Step 2: pandoc -> typst
PANDOC_ARGS=(
  -f markdown
  -t typst
  --standalone
  --metadata title="$TITLE"
  --metadata date="$(date +%Y-%m-%d)"
  -V papersize=a4
  -o "$MERGED_TYP"
)
if [[ "$TOC_DEPTH" -gt 0 ]]; then
  PANDOC_ARGS+=(--toc --toc-depth="$TOC_DEPTH")
fi
pandoc "$MERGED_MD" "${PANDOC_ARGS[@]}"

# Step 3: inject preset show-rules + universal CJK/table/outline fixes
python3 "${SCRIPT_DIR}/inject_typst_style.py" "$MERGED_TYP" "$STYLE" "$TOC_DEPTH" "$PRESETS_DIR"

# Step 4: typst compile (native in-doc TOC + side-panel bookmarks)
typst compile --font-path /System/Library/Fonts --font-path /Library/Fonts "$MERGED_TYP" "$OUTPUT"

# Verify
if [[ ! -f "$OUTPUT" ]]; then
  echo "❌ PDF not created" >&2
  exit 1
fi

SIZE=$(stat -f%z "$OUTPUT" 2>/dev/null || stat -c%s "$OUTPUT")
PAGES=""
BOOKMARKS=0
if command -v /opt/homebrew/bin/pdfinfo >/dev/null 2>&1; then
  PAGES=$(/opt/homebrew/bin/pdfinfo "$OUTPUT" 2>/dev/null | awk '/^Pages:/ {print $2}')
fi
# Verify outline count — caller must see this. User has corrected
# silent-no-outline output multiple times. typst generates /Outlines natively.
if [[ -n "$PYTHON" ]]; then
  BOOKMARKS=$("$PYTHON" -c "import fitz; print(len(fitz.open('$OUTPUT').get_toc()))" 2>/dev/null || echo 0)
fi

echo
echo "✅ PDF 完成"
echo "   path:     $OUTPUT"
echo "   size:     $(numfmt --to=iec --suffix=B $SIZE 2>/dev/null || echo "${SIZE} bytes")"
echo "   pages:    ${PAGES:-unknown}"
echo "   outline:  ${BOOKMARKS} entries"

if [[ "$SIZE" -lt 10240 ]]; then
  echo "⚠️  WARN: PDF size < 10 KB, content may be missing" >&2
fi
if [[ -n "$PYTHON" && "$BOOKMARKS" -eq 0 && "$TOC_DEPTH" -gt 0 ]]; then
  echo "⚠️  WARN: outline = 0 entries despite --toc-depth=$TOC_DEPTH. Check that _merged.md has '#'/'##' headings." >&2
fi

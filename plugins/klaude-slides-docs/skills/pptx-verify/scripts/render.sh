#!/usr/bin/env bash
# pptx-verify renderer: pptx → PDF → JPG
# Usage: bash render.sh <path-to-pptx> [dpi]
# Outputs:
#   <pptx-dir>/.pptx-verify/<basename>.pdf
#   <pptx-dir>/.pptx-verify/slide-NN.jpg
# Stdout: absolute paths of all slide jpgs (one per line)

set -euo pipefail

PPTX="${1:-}"
DPI="${2:-130}"

if [ -z "$PPTX" ]; then
  echo "ERROR: usage: $0 <path-to-pptx> [dpi]" >&2
  exit 2
fi
if [ ! -f "$PPTX" ]; then
  echo "ERROR: file not found: $PPTX" >&2
  exit 2
fi

# Resolve to absolute path
PPTX_ABS="$(cd "$(dirname "$PPTX")" && pwd)/$(basename "$PPTX")"
PPTX_DIR="$(dirname "$PPTX_ABS")"
PPTX_BASE="$(basename "$PPTX_ABS" .pptx)"
OUT_DIR="$PPTX_DIR/.pptx-verify"

# Preflight: zip integrity + slide count
if ! unzip -t "$PPTX_ABS" >/dev/null 2>&1; then
  echo "ERROR: pptx is corrupted (zip integrity failed): $PPTX_ABS" >&2
  exit 3
fi
SLIDE_COUNT=$(unzip -l "$PPTX_ABS" 2>/dev/null | grep -cE 'ppt/slides/slide[0-9]+\.xml$' || true)
if [ "$SLIDE_COUNT" -le 0 ]; then
  echo "ERROR: no slides found in pptx" >&2
  exit 3
fi
echo "[render] preflight OK: $SLIDE_COUNT slides" >&2

# Prepare clean output dir
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/slide-*.jpg "$OUT_DIR/$PPTX_BASE.pdf"

# Locate soffice wrapper if present (handles sandbox edge cases)
SOFFICE_WRAPPER=""
for cand in \
  "$HOME/Library/Application Support/Claude/local-agent-mode-sessions"/*/skills-plugin/*/*/skills/pptx/scripts/office/soffice.py \
  ; do
  if [ -f "$cand" ]; then
    SOFFICE_WRAPPER="$cand"
    break
  fi
done

# Convert pptx → pdf
echo "[render] pptx → pdf via soffice ..." >&2
if [ -n "$SOFFICE_WRAPPER" ]; then
  python "$SOFFICE_WRAPPER" --headless --convert-to pdf --outdir "$OUT_DIR" "$PPTX_ABS" >&2
else
  if ! command -v soffice >/dev/null 2>&1; then
    echo "ERROR: soffice not found and wrapper not located. Install LibreOffice." >&2
    exit 4
  fi
  soffice --headless --convert-to pdf --outdir "$OUT_DIR" "$PPTX_ABS" >&2
fi

PDF_PATH="$OUT_DIR/$PPTX_BASE.pdf"
if [ ! -f "$PDF_PATH" ]; then
  echo "ERROR: PDF was not created at $PDF_PATH" >&2
  exit 4
fi

# Convert pdf → jpg per page
echo "[render] pdf → jpg @ ${DPI} dpi via pdftoppm ..." >&2
if ! command -v pdftoppm >/dev/null 2>&1; then
  echo "ERROR: pdftoppm not found. Install poppler (brew install poppler)." >&2
  exit 4
fi
( cd "$OUT_DIR" && pdftoppm -jpeg -r "$DPI" "$PPTX_BASE.pdf" slide ) >&2

# Emit absolute paths of slide jpgs to stdout
ls -1 "$OUT_DIR"/slide-*.jpg | sort

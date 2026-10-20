#!/bin/bash
# Stage 7 — Build single-file PDF from lectures/*.md.
#
# Pipeline: cat markdown → pandoc HTML (+mermaid CDN injection) → Chrome headless PDF.
# Avoids LaTeX (no 100MB basictex install) and handles CJK + mermaid natively.
#
# Inputs:
#   lectures/NN_title.md           (Stage 5 output)
#   README.md (optional cover)
#   .skill-state.json → playlist_title for output filename
#
# Outputs:
#   build/<playlist_title>-lecture-notes.html
#   build/<playlist_title>-lecture-notes.pdf
#   build/combined.md
#   build/style.css (copied from skill defaults if absent)

set -e

ROOT=$(pwd)
BUILD="$ROOT/build"
mkdir -p "$BUILD"

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Derive output filename from .skill-state.json
TITLE=$(python3 -c "
import json, pathlib, re, sys
p = pathlib.Path('.skill-state.json')
if p.exists():
    d = json.loads(p.read_text())
    t = d.get('playlist_title') or d.get('playlist_id') or 'playlist'
else:
    t = 'playlist'
t = re.sub(r'[^A-Za-z0-9_-]+', '_', t).strip('_').lower()[:40]
print(t or 'playlist')
")
OUT_NAME="${TITLE}-lecture-notes"
HTML="$BUILD/$OUT_NAME.html"
PDF="$BUILD/$OUT_NAME.pdf"

# Ensure style.css present
if [ ! -f "$BUILD/style.css" ]; then
    if [ -f "$SKILL_DIR/references/default_style.css" ]; then
        cp "$SKILL_DIR/references/default_style.css" "$BUILD/style.css"
        echo "[info] copied default style.css from skill"
    else
        echo "[warn] no style.css found; pandoc default styling will be used"
    fi
fi

echo "[1/3] Concatenating markdown sources..."
> "$BUILD/combined.md"
if [ -f "$ROOT/README.md" ]; then
    cat "$ROOT/README.md" >> "$BUILD/combined.md"
    echo "" >> "$BUILD/combined.md"
    echo '<hr class="pagebreak"/>' >> "$BUILD/combined.md"
    echo "" >> "$BUILD/combined.md"
fi
LEC_COUNT=0
for f in "$ROOT"/lectures/*.md; do
    [ -f "$f" ] || continue
    cat "$f" >> "$BUILD/combined.md"
    echo "" >> "$BUILD/combined.md"
    echo '<hr class="pagebreak"/>' >> "$BUILD/combined.md"
    echo "" >> "$BUILD/combined.md"
    LEC_COUNT=$((LEC_COUNT+1))
done
echo "  → $LEC_COUNT lectures included"

if [ $LEC_COUNT -eq 0 ]; then
    echo "[error] no lectures/*.md found; run Stage 5 first"
    exit 1
fi

echo "[2/3] Pandoc Markdown → HTML with mermaid..."
STYLE_ARG=""
if [ -f "$BUILD/style.css" ]; then
    STYLE_ARG="--css=$BUILD/style.css"
fi

pandoc "$BUILD/combined.md" \
    --from markdown+raw_html-yaml_metadata_block \
    --to html5 \
    --standalone \
    --toc --toc-depth=3 \
    --mathjax=https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml-full.js \
    --metadata title="$TITLE · 中文教科書級講義" \
    --metadata lang="zh-TW" \
    $STYLE_ARG \
    -o "$HTML"

# Inject mermaid.js (CDN) before </head>
python3 - <<PY
import pathlib
p = pathlib.Path("$HTML")
s = p.read_text()
inject = """
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  // Pandoc emits mermaid fenced blocks as <pre class="mermaid"><code>...</code></pre>.
  // Convert each to <div class="mermaid"> using textContent (auto-decodes HTML entities
  // like --&gt; back to -->) before handing off to mermaid.run().
  // Do NOT rely on startOnLoad:true — by the time initialize() is called inside
  // DOMContentLoaded the browser event has already fired.
  document.addEventListener("DOMContentLoaded", function(){
    document.querySelectorAll('pre.mermaid > code').forEach(function(block){
      var pre = block.parentElement;
      var div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = block.textContent;  // textContent decodes &gt; -> > etc.
      pre.parentElement.replaceChild(div, pre);
    });
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      securityLevel: 'loose'   // allow <br/> HTML in node labels
    });
    mermaid.run();             // explicitly render all .mermaid divs now
  });
</script>
"""
s = s.replace("</head>", inject + "</head>")
p.write_text(s)
print("  mermaid injected")
PY

echo "[3/3] Chrome headless HTML → PDF..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser)"
else
    echo "[error] unsupported OS: $OSTYPE"
    exit 1
fi

if [ ! -x "$CHROME" ]; then
    echo "[error] Chrome not found or not executable: $CHROME"
    exit 1
fi

"$CHROME" \
    --headless \
    --disable-gpu \
    --no-pdf-header-footer \
    --virtual-time-budget=30000 \
    --print-to-pdf-no-header \
    --print-to-pdf="$PDF" \
    "file://$HTML" 2>&1 | grep -v "DevTools\|Gtk\|GLib\|^$" || true

if [ -f "$PDF" ]; then
    SIZE=$(du -h "$PDF" | cut -f1)
    echo ""
    echo "✓ PDF built: $PDF ($SIZE)"
else
    echo "✗ PDF build failed"
    exit 1
fi

echo "[4/4] Injecting PDF outline (bookmarks)..."
if python3 "$SKILL_DIR/scripts/add_pdf_outline.py" "$PDF" "$HTML"; then
    SIZE=$(du -h "$PDF" | cut -f1)
    echo "✓ Outline written: $PDF ($SIZE)"
else
    echo "[warn] Outline injection failed — PDF is still usable without bookmarks"
fi

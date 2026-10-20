#!/bin/bash
# Stage 2 — Fetch playlist metadata + all transcripts via yt-dlp.
#
# Usage:
#   bash fetch_playlist.sh <PLAYLIST_URL>
#   bash fetch_playlist.sh PLrw6a1wE39_tb2fErI4-WkMbsvGQk9_UB  # playlist ID also works
#
# Output:
#   lectures-raw/playlist.json          (metadata: index, video_id, title, duration, url)
#   lectures-raw/NN_title/transcript.vtt
#   lectures-raw/NN_title/transcript.txt  (VTT with timestamps stripped)

set -eu

if [ $# -lt 1 ]; then
    echo "Usage: bash fetch_playlist.sh <PLAYLIST_URL_OR_ID>"
    exit 1
fi

INPUT="$1"

# Normalize: if user gave bare playlist ID, convert to URL
if [[ "$INPUT" =~ ^https?:// ]]; then
    URL="$INPUT"
else
    URL="https://www.youtube.com/playlist?list=$INPUT"
fi

OUT_DIR="lectures-raw"
mkdir -p "$OUT_DIR"

echo "==== Stage 2: Fetch playlist ===="
echo "URL: $URL"
echo ""

# 1. Get playlist metadata
echo "[1/2] Fetching playlist metadata..."
yt-dlp --flat-playlist --print-json "$URL" 2>/dev/null \
    | python3 -c "
import sys, json, re
items = []
for i, line in enumerate(sys.stdin, 1):
    v = json.loads(line)
    items.append({
        'index': i,
        'video_id': v.get('id'),
        'title': v.get('title', '?'),
        'duration': v.get('duration'),
        'url': v.get('url') or f\"https://www.youtube.com/watch?v={v.get('id')}\",
    })
with open('$OUT_DIR/playlist.json', 'w') as f:
    json.dump(items, f, ensure_ascii=False, indent=2)
print(f'  → {len(items)} videos saved to $OUT_DIR/playlist.json')
"

# 2. Fetch transcripts per video
echo ""
echo "[2/2] Fetching transcripts (auto-subs, en)..."

python3 <<'PY'
import json, re, subprocess, sys
from pathlib import Path

playlist = json.loads(Path("lectures-raw/playlist.json").read_text())

def slug(s):
    s = re.sub(r"^(Lecture|Lec|Video)\s+\d+:?\s*", "", s, flags=re.I)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s[:40] or "untitled"

for v in playlist:
    num = v["index"]
    name = f"{num:02d}_{slug(v['title'])}"
    out_dir = Path("lectures-raw") / name
    vtt = out_dir / "transcript.vtt"
    txt = out_dir / "transcript.txt"

    if txt.exists() and txt.stat().st_size > 1000:
        print(f"  [skip] Lec {num:02d}: transcript.txt already present ({txt.stat().st_size} bytes)")
        continue

    out_dir.mkdir(parents=True, exist_ok=True)

    # yt-dlp writes vtt to <template>.en.vtt; we'll move it
    tmp_template = str(out_dir / "transcript")
    cmd = [
        "yt-dlp",
        "--write-auto-subs",
        "--skip-download",
        "--sub-lang", "en",
        "--convert-subs", "vtt",
        "--output", tmp_template,
        v["url"],
    ]
    print(f"  [fetch] Lec {num:02d}: {v['title'][:60]}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    !! yt-dlp failed: {r.stderr.strip()[:200]}")
        continue

    # yt-dlp outputs transcript.en.vtt — rename to transcript.vtt
    produced = list(out_dir.glob("transcript.*.vtt"))
    if not produced:
        print(f"    !! no vtt produced (maybe no auto-caption)")
        continue
    produced[0].rename(vtt)

    # Strip VTT timestamps → plain text
    lines = vtt.read_text().splitlines()
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        if re.match(r"^\d+$", line):  # cue number
            continue
        if "-->" in line:  # timestamp line
            continue
        # Remove inline timestamp tags <00:00:01.000>
        line = re.sub(r"<[\d:.]+>", "", line)
        # Remove speaker/tags like <c>..</c>
        line = re.sub(r"</?c[^>]*>", "", line)
        line = line.strip()
        if line and (not text_lines or text_lines[-1] != line):
            text_lines.append(line)

    txt.write_text("\n".join(text_lines))
    print(f"    → {len(text_lines)} lines, {len(txt.read_text())} chars")

print()
print("✓ Stage 2 complete.")
PY

echo ""
echo "==== Output ===="
echo "  Playlist metadata: $OUT_DIR/playlist.json"
echo "  Transcripts:      $OUT_DIR/*/transcript.txt"
ls -1 "$OUT_DIR" | grep -v "^playlist.json$" | head -5 | sed 's/^/  /'
TOTAL=$(ls -1 "$OUT_DIR" | grep -v "^playlist.json$" | wc -l | tr -d ' ')
echo "  (total $TOTAL lectures)"

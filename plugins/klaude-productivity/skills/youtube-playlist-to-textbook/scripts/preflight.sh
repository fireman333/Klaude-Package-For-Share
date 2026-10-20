#!/bin/bash
# Stage 0 — Preflight check for youtube-playlist-to-textbook skill.
# Verifies all required tools are installed and authenticated.
# Does NOT install anything — just reports what's missing and how to fix.

set -u

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0

check() {
    local name="$1"
    local cmd="$2"
    local fix="$3"

    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $name"
        PASS=$((PASS+1))
    else
        echo -e "  ${RED}✗${NC} $name"
        echo -e "    ${YELLOW}Fix:${NC} $fix"
        FAIL=$((FAIL+1))
    fi
}

echo "==== Preflight: youtube-playlist-to-textbook ===="

echo ""
echo "[1/5] Claude CLI (claude -p headless)"
check "claude CLI installed" "command -v claude" "安裝 Claude Code CLI（generation engine 走 claude -p headless，用你的訂閱額度）"
# Real smoke test exercising the headless print path. `claude -p` reads the prompt
# from stdin and prints only the response. If not authenticated it errors fast.
check "claude -p reachable (smoke test ~20s)" \
    "echo 'reply ok' | claude -p --model haiku > \"\${TMPDIR:-/tmp}/ytt_preflight_claude.out\" 2>&1 && test -s \"\${TMPDIR:-/tmp}/ytt_preflight_claude.out\"" \
    "確認 Claude Code 已登入（一般終端機跑 claude 一次）。generation engine 已從停服的 gemini CLI 改為 claude -p headless"

echo ""
echo "[2/5] NotebookLM (optional)"
# Optional: NotebookLM is only needed for Stage 3 / 6 fact-checking.
if command -v nlm >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} nlm CLI installed (optional)"
    PASS=$((PASS+1))
    if timeout 15 nlm notebook list >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} nlm authenticated"
        PASS=$((PASS+1))
    else
        echo -e "  ${YELLOW}!${NC} nlm 未登入（選用）。若要用事實校對：nlm login"
        WARN=$((WARN+1))
    fi
else
    echo -e "  ${YELLOW}!${NC} nlm 未安裝（選用，只影響 Stage 3/6 事實校對；要裝：uv tool install notebooklm-mcp-cli）"
    WARN=$((WARN+1))
fi

echo ""
echo "[3/5] yt-dlp"
check "yt-dlp installed" "command -v yt-dlp" "pip install yt-dlp 或 brew install yt-dlp"

echo ""
echo "[4/5] pandoc + Python"
check "pandoc installed" "command -v pandoc" "brew install pandoc"
check "python3 installed" "command -v python3" "macOS 通常內建；若無則 brew install python@3.11"

echo ""
echo "[5/5] Chrome（for PDF build）"
if [[ "$OSTYPE" == "darwin"* ]]; then
    check "Chrome (macOS, only for PDF)" "test -x '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'" "https://www.google.com/chrome/ 下載安裝"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    check "google-chrome" "command -v google-chrome" "sudo apt install google-chrome-stable（或對應發行版）"
else
    echo -e "  ${YELLOW}?${NC} 未知 OS（$OSTYPE）— 請手動確認 Chrome 可執行"
    WARN=$((WARN+1))
fi

echo ""
echo "==== Summary ===="
echo -e "${GREEN}PASS${NC}: $PASS  ${RED}FAIL${NC}: $FAIL  ${YELLOW}WARN${NC}: $WARN"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo -e "${RED}→ 請先補齊上述 FAIL 項再往下跑 skill。${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}→ 全數通過，可進 Stage 1（intake）。${NC}"
exit 0

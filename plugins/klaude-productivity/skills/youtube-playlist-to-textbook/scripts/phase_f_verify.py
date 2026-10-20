"""Stage 6 — Phase F verification: cross-check lecture facts against NotebookLM.

For each lecture:
  1. Extract 3-5 factual claims (heuristic: paper/section refs, numeric defaults, "永遠/必定" statements)
  2. For each claim, query the NotebookLM mega-notebook
  3. If answer contradicts → invoke claude -p headless to rewrite the surrounding paragraph
  4. Write a verification report with proposed patches (actual Edit patching done by Claude orchestrator)

Why not auto-patch here?
  Surgical edits need Claude's Edit tool (old_string / new_string precision). This script
  writes proposed patches to .state/phase_f_patches.json; Claude reads it + applies via Edit
  so the user sees diffs and can Ctrl+C abort mid-way.

Usage:
    python3 phase_f_verify.py all
    python3 phase_f_verify.py 3 7 16     # specific lectures
    python3 phase_f_verify.py all --max-facts 3     # limit claims per lecture
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
STATE_PATH = ROOT / ".skill-state.json"
LECTURES_DIR = ROOT / "lectures"
PATCHES_PATH = ROOT / ".state" / "phase_f_patches.json"

# claude is on PATH (Claude Code CLI). `claude -p` reads the prompt from stdin.
CLAUDE = "claude"


def load_state() -> dict:
    if not STATE_PATH.exists():
        sys.exit(".skill-state.json not found. Run Stage 1 first.")
    return json.loads(STATE_PATH.read_text())


def extract_claims(md: str, max_n: int = 5) -> list:
    """Heuristic: pick paragraphs containing verifiable assertions.

    Signals we prefer:
      - paper §X.Y / section X.Y references
      - numeric defaults ("預設 60 秒", "64 MB chunk")
      - 強斷言 ("必定", "絕不", "永遠")
      - 技術步驟 ("1. Client -> Primary ...")
    """
    paragraphs = [p.strip() for p in md.split("\n\n") if p.strip()]
    candidates = []

    patterns = [
        # Distributed-systems style (kept for backward compat)
        (r"paper\s*§?\s*\d", 3),
        (r"§\d+\.\d+", 3),
        (r"\d+\s*(?:MB|GB|KB|ms|secs?|seconds?|minutes?|mins?)\b", 2),
        (r"預設\s*[為是]?\s*\d", 2),
        (r"(?:必定|絕不|永遠|一定)\b", 1),
        (r"(?:Primary|Leader|Master|Coordinator)\s*->", 1),
        # Algorithms / math (added after MIT 6.046J: 28/34 extracted 0 claims)
        (r"(?:O|Θ|Ω|Theta|Omega)\s*\(\s*[nNmMlk].*?\)", 3),
        (r"(?:定理|引理|推論|Corollary|Lemma|Theorem)\s*\d", 2),
        (r"時間複雜度|空間複雜度", 2),
        (r"(?:演算法|algorithm)\s*(?:保證|guarantees?|必須|requires?|ensures?)", 2),
        (r"\b\d+(?:\.\d+)?\s*%", 1),
        # General scientific claim signals (broad applicability)
        (r"(?:收斂|converges?|發散|diverges?)\b", 1),
        (r"(?:最壞|worst[- ]case|平均|average)\b.*(?:O|Θ|複雜|time)", 2),
    ]

    for p in paragraphs:
        if len(p) < 50 or len(p) > 800:
            continue
        if p.startswith(("#", "|", "```", "<")):
            continue
        score = 0
        for pat, w in patterns:
            if re.search(pat, p, re.I):
                score += w
        if score >= 2:
            candidates.append((score, p))

    # Top-N by score
    candidates.sort(key=lambda x: -x[0])
    return [p for _, p in candidates[:max_n]]


def query_notebook(notebook_id: str, question: str) -> str:
    """Call notebook_query via nlm CLI (since we run outside MCP context here)."""
    try:
        r = subprocess.run(
            ["nlm", "notebook", "query", notebook_id, question],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            return f"[ERROR] nlm query failed: {r.stderr.strip()[:300]}"
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return "[ERROR] nlm query timeout (120s)"


def judge_mismatch(claim: str, answer: str) -> tuple:
    """Quick heuristic: does the NotebookLM answer flag the claim as incorrect?

    Returns (is_mismatch, reason_snippet).
    """
    a_lower = answer.lower()
    negative_markers = [
        "不正確", "錯誤", "不符", "incorrect", "wrong", "not accurate",
        "這個敘述不", "應該是", "實際上是", "正確的說法",
    ]
    for m in negative_markers:
        if m in answer:
            # Extract sentence containing the marker
            for sent in re.split(r"[。\n]", answer):
                if m in sent:
                    return True, sent.strip()[:300]
    return False, ""


def llm_rewrite(original_para: str, correction: str, lec_title: str) -> str:
    """Invoke claude -p headless to rewrite the paragraph with the correction."""
    skill_dir = Path(__file__).resolve().parent.parent
    tpl_path = skill_dir / "references" / "phase_f_rewrite_template.md"
    tpl = tpl_path.read_text() if tpl_path.exists() else (
        "請根據以下校對反饋重寫段落，保留原格式，僅修正事實錯誤：\n\n"
        "Lecture: {LEC_TITLE}\n\n"
        "原段落：\n{ORIGINAL}\n\n"
        "NotebookLM 校對反饋：\n{CORRECTION}\n\n"
        "重寫後的段落（直接輸出，不要加前言）："
    )
    prompt = (tpl
              .replace("{LEC_TITLE}", lec_title)
              .replace("{ORIGINAL}", original_para)
              .replace("{CORRECTION}", correction))

    try:
        # `claude -p` reads the prompt from stdin; prints only the response to stdout.
        # The 180s subprocess timeout governs.
        r = subprocess.run(
            [CLAUDE, "-p", "--model", "haiku"],
            input=prompt, capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            return f"[ERROR] claude rewrite failed: {r.stderr.strip()[:200]}"
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return "[ERROR] claude rewrite timeout"


SYSTEMIC_ERROR_THRESHOLD = 5


def detect_systemic_term(md: str, reason: str) -> dict | None:
    """If the correction mentions a wrong term that appears many times in the file,
    propose a global replace instead of (or in addition to) a single paragraph patch.

    Heuristic: extract Chinese/English token pairs of the form 「X」→「Y」 or
    "X is actually Y" from the reason string, then count X in md. If >= threshold,
    emit a global_replace_candidate.
    """
    pair_patterns = [
        r"「([^」]{2,20})」.*?(?:應該是|正確|實際上是|改為)\s*「([^」]{2,20})」",
        r"([A-Za-z\u4e00-\u9fff]{2,20})\s*應該是\s*([A-Za-z\u4e00-\u9fff]{2,20})",
    ]
    for pat in pair_patterns:
        m = re.search(pat, reason)
        if not m:
            continue
        wrong, right = m.group(1).strip(), m.group(2).strip()
        if wrong == right or len(wrong) < 2:
            continue
        count = md.count(wrong)
        if count >= SYSTEMIC_ERROR_THRESHOLD:
            return {"wrong": wrong, "right": right, "count": count}
    return None


def verify_lecture(lec_path: Path, notebook_id: str, max_facts: int) -> list:
    """Verify one lecture. Returns list of proposed patches."""
    print(f"\n[Verify] {lec_path.name}")
    md = lec_path.read_text()
    claims = extract_claims(md, max_n=max_facts)
    print(f"  Extracted {len(claims)} candidate claims")

    patches = []
    for i, claim in enumerate(claims, 1):
        q = (f"請根據來源文件判斷以下敘述是否正確：\n\n「{claim[:500]}」\n\n"
             f"若有錯，請具體指出錯在哪裡、正確答案是什麼，並引用 section 或段落。"
             f"若正確，請回「敘述正確」。")
        print(f"  [Q{i}] {claim[:80]}...")
        ans = query_notebook(notebook_id, q)
        is_mismatch, reason = judge_mismatch(claim, ans)

        if is_mismatch:
            print(f"    ⚠ mismatch: {reason[:100]}")
            new_para = llm_rewrite(claim, reason, lec_path.stem)
            patch = {
                "lecture": lec_path.name,
                "old": claim,
                "new": new_para,
                "reason": reason,
                "notebook_answer": ans[:800],
            }
            # Detect if this is a systemic translation/terminology error → flag as global replace
            systemic = detect_systemic_term(md, reason)
            if systemic:
                patch["global_replace_candidate"] = systemic
                print(
                    f"    ⚠⚠ systemic error: 「{systemic['wrong']}」→「{systemic['right']}」"
                    f" appears {systemic['count']}x (suggest replace_all)"
                )
            patches.append(patch)
        else:
            print(f"    ✓ verified")
        time.sleep(1)  # gentle rate limit

    return patches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lectures", nargs="+", help="Lecture numbers or 'all'")
    ap.add_argument("--max-facts", type=int, default=5)
    args = ap.parse_args()

    state = load_state()
    notebook_id = state.get("notebook_id")
    if not notebook_id:
        sys.exit("No notebook_id in .skill-state.json. Run Stage 3 first.")

    lec_files = sorted(LECTURES_DIR.glob("*.md"))
    if args.lectures != ["all"]:
        nums = set(int(x) for x in args.lectures)
        lec_files = [f for f in lec_files if int(f.name[:2]) in nums]

    all_patches = []
    for f in lec_files:
        patches = verify_lecture(f, notebook_id, args.max_facts)
        all_patches.extend(patches)

    PATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PATCHES_PATH.write_text(json.dumps(all_patches, ensure_ascii=False, indent=2))

    print(f"\n==== Phase F Summary ====")
    print(f"  Total proposed patches: {len(all_patches)}")
    print(f"  Written to: {PATCHES_PATH}")
    print(f"\n→ Claude orchestrator now reads this file and applies Edit patches with diff preview.")


if __name__ == "__main__":
    main()

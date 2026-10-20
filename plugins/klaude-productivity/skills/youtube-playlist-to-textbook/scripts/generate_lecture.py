"""Stage 5 — Generate lecture markdown via claude -p headless (Claude Code subscription).

Two-pass mode per lecture:
  - Part A: §0-§4 (TL;DR / Motivation / Prerequisites / Core Concepts / Deep Dive)
  - Part B: §5-§9 (醫學類比 / Q&A / Pitfalls / 自測題 / Further Reading)

Each part = 1 claude call ~3,500-5,000 Chinese chars. Combined ~7,000-10,000.

Usage:
    python3 generate_lecture.py 1                      # single lecture
    python3 generate_lecture.py 1 2 3 --concurrent 3   # parallel
    python3 generate_lecture.py all --concurrent 3     # all lectures
    python3 generate_lecture.py 1 --force              # re-run even if done
    python3 generate_lecture.py 1 --model sonnet  # override model

State:
    .state/progress.json tracks per-lecture ok / err / cjk_total. Failed lectures
    retry automatically on next run; succeeded ones skip unless --force.

Safety:
    - Uses `claude -p` headless (Claude Code subscription); prompt on stdin so large
      transcripts are never truncated. (Other CLIs' -p modes often truncate large
      argv, so stdin is used.)
    - Each claude call hard-capped at 900s (long Part A prompts can exceed 450s).
    - Transient failures (quota burst / network) retry with backoff.
"""
import argparse
import asyncio
import contextlib
import fcntl
import json
import os
import random
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path.cwd()
SKILL_DIR = Path(__file__).resolve().parent.parent
PLAYLIST_PATH = ROOT / "lectures-raw" / "playlist.json"
STATE_PATH = ROOT / ".skill-state.json"
PROGRESS_PATH = ROOT / ".state" / "progress.json"
PROGRESS_LOCK_PATH = ROOT / ".state" / "progress.json.lock"
PROGRESS_JOURNAL_PATH = ROOT / ".state" / "progress.jsonl"
LECTURES_DIR = ROOT / "lectures"

# claude is on PATH (Claude Code CLI). `claude -p` reads the prompt from stdin.
CLAUDE = "claude"


def count_cjk(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def load_playlist():
    if not PLAYLIST_PATH.exists():
        sys.exit(f"playlist.json not found at {PLAYLIST_PATH}. Run fetch_playlist.sh first.")
    return json.loads(PLAYLIST_PATH.read_text())


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"persona_text": None, "sections": None}


@contextlib.contextmanager
def _progress_lock():
    """Flock-based mutex so concurrent workers don't clobber progress.json."""
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_fp = open(PROGRESS_LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
        lock_fp.close()


def load_progress():
    with _progress_lock():
        if PROGRESS_PATH.exists():
            return json.loads(PROGRESS_PATH.read_text())
        return {}


def save_progress(p):
    """Atomic write via temp-file + rename under flock. Also appends journal."""
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _progress_lock():
        # Merge with on-disk state so concurrent workers don't drop each other's entries
        merged = {}
        if PROGRESS_PATH.exists():
            try:
                merged = json.loads(PROGRESS_PATH.read_text())
            except Exception:
                merged = {}
        merged.update(p)
        payload = json.dumps(merged, ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".progress.", suffix=".tmp", dir=str(PROGRESS_PATH.parent)
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(payload)
            os.replace(tmp_path, PROGRESS_PATH)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        # Append journal entry for each key in this save (tail-friendly audit log)
        with open(PROGRESS_JOURNAL_PATH, "a") as j:
            ts = int(time.time())
            for k, v in p.items():
                j.write(json.dumps({"ts": ts, "key": k, "entry": v}, ensure_ascii=False) + "\n")


def slug(title: str) -> str:
    s = re.sub(r"^(Lecture|Lec|Video)\s+\d+:?\s*", "", title, flags=re.I)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s[:40] or "untitled"


def lecture_dir_name(num: int, title: str) -> str:
    return f"{num:02d}_{slug(title)}"


def load_transcript(num: int, title: str) -> str:
    p = ROOT / "lectures-raw" / lecture_dir_name(num, title) / "transcript.txt"
    if not p.exists():
        return ""
    return p.read_text()


CONFUSION_SUBJECTS = {
    "algorithms", "distributed", "os", "ml", "crypto",
}


def _load_confusion_points(subject: str | None) -> str:
    """Load subject-specific confusion-point block. Fallback to algorithms."""
    key = (subject or "").lower().strip()
    if key not in CONFUSION_SUBJECTS:
        key = "algorithms"
    path = SKILL_DIR / "references" / "confusion_points" / f"{key}.md"
    if path.exists():
        return path.read_text().strip()
    return ""


def load_persona() -> str:
    """Load persona: state override → skill default, with {CONFUSION_POINTS} substitution.

    `.skill-state.json.subject` (e.g. "algorithms", "distributed", "os", "ml", "crypto")
    picks the subject-specific confusion-point block. Unknown / missing → algorithms.
    """
    state = load_state()
    if state.get("persona_text"):
        persona = state["persona_text"]
    else:
        default = SKILL_DIR / "references" / "default_persona.md"
        persona = default.read_text() if default.exists() else ""
    if "{CONFUSION_POINTS}" in persona:
        persona = persona.replace(
            "{CONFUSION_POINTS}", _load_confusion_points(state.get("subject"))
        )
    return persona


def load_sections() -> str:
    """Load section structure: state override → skill default."""
    state = load_state()
    if state.get("sections"):
        # If state has list of section names, reassemble into markdown
        if isinstance(state["sections"], list):
            return "\n".join(f"- {s}" for s in state["sections"])
        return state["sections"]
    default = SKILL_DIR / "references" / "default_sections.md"
    return default.read_text() if default.exists() else ""


def build_prompt(lec: dict, part: str) -> str:
    """Build Part A or B prompt by filling the template."""
    tpl_name = f"prompt_part{part.upper()}.md"
    tpl_path = SKILL_DIR / "references" / tpl_name
    if not tpl_path.exists():
        # Fallback to combined template
        tpl_path = SKILL_DIR / "references" / "prompt_templates.md"
    tpl = tpl_path.read_text()

    transcript = load_transcript(lec["index"], lec["title"])
    persona = load_persona()
    sections = load_sections()

    return (tpl
            .replace("{LEC_NUM}", f"{lec['index']:02d}")
            .replace("{LEC_TITLE}", lec["title"])
            .replace("{VIDEO_URL}", lec["url"])
            .replace("{DURATION}", str(lec.get("duration", "?")))
            .replace("{TRANSCRIPT}", transcript)
            .replace("{PERSONA}", persona)
            .replace("{SECTIONS}", sections))


# Quota / rate-limit signatures → distinct (longer) backoff path
QUOTA_PATTERNS = (
    "429", "quota", "exhausted", "rate limit", "RESOURCE_EXHAUSTED",
)
# Generic transient (network / AbortError) → shorter backoff
RETRYABLE_PATTERNS = (
    "AbortError", "ECONNRESET", "socket hang up", "ETIMEDOUT", "timed out",
)


# Sliding-window RPM limiter (in-process, async-safe).
# Conservative default for nested `claude -p` calls; override via env (YTT_MAX_RPM).
MAX_RPM = int(os.environ.get("YTT_MAX_RPM", "10"))
_rpm_lock: asyncio.Lock | None = None
_rpm_calls: list[float] = []


async def _throttle_rpm():
    """Sleep if issuing a call now would exceed MAX_RPM in the trailing 60s."""
    global _rpm_lock
    if _rpm_lock is None:
        _rpm_lock = asyncio.Lock()
    async with _rpm_lock:
        now = time.time()
        cutoff = now - 60.0
        while _rpm_calls and _rpm_calls[0] < cutoff:
            _rpm_calls.pop(0)
        if len(_rpm_calls) >= MAX_RPM:
            wait = _rpm_calls[0] + 60.0 - now + 0.5
            if wait > 0:
                print(
                    f"    [rpm] {len(_rpm_calls)}/{MAX_RPM} in last 60s → sleep {wait:.1f}s",
                    flush=True,
                )
                await asyncio.sleep(wait)
                now = time.time()
                cutoff = now - 60.0
                while _rpm_calls and _rpm_calls[0] < cutoff:
                    _rpm_calls.pop(0)
        _rpm_calls.append(now)


async def call_llm_with_retry(
    prompt: str, model: str, label: str,
    timeout: float = 900.0, max_retries: int = 4,
) -> str:
    """Wrap call_llm with exponential backoff on transient failures.

    Two backoff tiers:
      - Quota / 429 / RESOURCE_EXHAUSTED → 60s, 120s, 240s (capped 300s)
      - Generic transient (network, AbortError, timeout) → 15s, 30s, 60s (capped 120s)
    Non-retryable (auth cancel, prompt-too-short validation) → raise immediately.
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            return await call_llm(prompt, model, label, timeout)
        except RuntimeError as e:
            last_err = e
            msg = str(e)
            msg_lower = msg.lower()
            is_quota = any(p.lower() in msg_lower for p in QUOTA_PATTERNS)
            is_generic = any(p in msg for p in RETRYABLE_PATTERNS)
            if not (is_quota or is_generic):
                raise
            if attempt == max_retries - 1:
                raise
            if is_quota:
                wait = min(300, 60 * (2 ** attempt) + random.uniform(0, 15))
                tag = "429/quota"
            else:
                wait = min(120, 15 * (2 ** attempt) + random.uniform(0, 10))
                tag = "transient"
            print(
                f"    [{label}] {tag} → sleep {wait:.0f}s "
                f"(attempt {attempt + 1}/{max_retries}): {msg[:120]}",
                flush=True,
            )
            await asyncio.sleep(wait)
    raise last_err


async def call_llm(prompt: str, model: str, label: str, timeout: float = 900.0) -> str:
    """Invoke `claude -p` headless via subprocess (Claude Code subscription).

    Prompt is piped on stdin (`claude -p` reads the prompt from stdin), so large
    transcript prompts are never truncated and no temp file is needed. claude prints
    only the response to stdout, so stdout is the markdown response verbatim. The
    asyncio.wait_for below is the governing time limit.
    Respects the sliding-window RPM limiter before dispatching.
    """
    await _throttle_rpm()
    t0 = time.time()
    proc = await asyncio.create_subprocess_exec(
        CLAUDE, "-p", "--model", model,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"claude call timed out after {timeout}s")

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="ignore")[:500]
        raise RuntimeError(f"claude exited {proc.returncode}: {err}")

    text = stdout.decode("utf-8", errors="ignore")
    dt = time.time() - t0
    print(f"    [{label}] {len(text)} chars, {count_cjk(text)} CJK ({dt:.0f}s)", flush=True)
    return text


FALLBACK_MODEL = "sonnet"
MIN_PART_CJK = 1500


async def _generate_with_model(lec: dict, model: str) -> dict:
    """One attempt at a full 2-pass generation with a specific model."""
    num = lec["index"]
    out_path = LECTURES_DIR / f"{lecture_dir_name(num, lec['title'])}.md"
    t0 = time.time()

    prompt_a = build_prompt(lec, "a")
    text_a = await call_llm_with_retry(prompt_a, model, f"Lec{num:02d}/A[{model}]")
    if count_cjk(text_a) < MIN_PART_CJK:
        return {"ok": False, "err": f"Part A too short ({count_cjk(text_a)} CJK)", "model": model}

    await asyncio.sleep(3)

    prompt_b = build_prompt(lec, "b")
    text_b = await call_llm_with_retry(prompt_b, model, f"Lec{num:02d}/B[{model}]")
    if count_cjk(text_b) < MIN_PART_CJK:
        return {"ok": False, "err": f"Part B too short ({count_cjk(text_b)} CJK)", "model": model}

    combined = text_a.rstrip() + "\n\n" + text_b.lstrip()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(combined)

    dt = time.time() - t0
    cjk_total = count_cjk(combined)
    print(f"[Lec {num:02d}] ✓ {cjk_total} CJK → {out_path.name}  ({dt:.0f}s, {model})", flush=True)
    return {
        "ok": True,
        "chars": len(combined),
        "cjk_total": cjk_total,
        "cjk_a": count_cjk(text_a),
        "cjk_b": count_cjk(text_b),
        "path": str(out_path.relative_to(ROOT)),
        "duration_s": round(dt, 1),
        "model": model,
        "ts": int(time.time()),
    }


async def generate_one(lec: dict, model: str) -> dict:
    """Generate one lecture via 2-pass. On flash under-length, auto-retry once with Pro.

    Failure mode observed on MIT 6.046J: 6/34 lectures (L6, L9, L11, L12, L13, L30)
    returned <MIN_PART_CJK on flash without quota / timeout. Pro succeeded on same
    transcript. Auto-fallback saves a whole manual re-run batch.
    """
    num = lec["index"]
    print(f"\n[Lec {num:02d}] {lec['title']}", flush=True)
    try:
        res = await _generate_with_model(lec, model)
        if res.get("ok"):
            return res
        # Under-length (not an exception) → try the fallback model once if not already on it
        err = res.get("err", "")
        if model != FALLBACK_MODEL and "too short" in err:
            print(
                f"    [Lec {num:02d}] {model} returned short ({err}) → fallback {FALLBACK_MODEL}",
                flush=True,
            )
            res2 = await _generate_with_model(lec, FALLBACK_MODEL)
            if res2.get("ok"):
                res2["fallback_from"] = model
            return res2
        return res
    except Exception as e:
        return {"ok": False, "err": f"{type(e).__name__}: {e}", "model": model}


async def run(lec_nums, concurrent: int, force: bool, model: str):
    playlist = load_playlist()
    index_map = {v["index"]: v for v in playlist}
    progress = load_progress()

    pending = []
    for n in lec_nums:
        if n not in index_map:
            print(f"  !! Lec {n:02d} not in playlist (skip)")
            continue
        key = f"lec_{n:02d}"
        if not force and progress.get(key, {}).get("ok"):
            print(f"  [skip] Lec {n:02d} already done ({progress[key].get('cjk_total')} CJK)")
            continue
        pending.append(index_map[n])

    if not pending:
        print("Nothing to do.")
        return

    # Process in concurrent batches
    for i in range(0, len(pending), concurrent):
        batch = pending[i:i + concurrent]
        print(f"\n========== Batch: {[l['index'] for l in batch]} ==========")
        coros = [generate_one(l, model) for l in batch]
        results = await asyncio.gather(*coros, return_exceptions=True)
        for lec, r in zip(batch, results):
            key = f"lec_{lec['index']:02d}"
            if isinstance(r, Exception):
                progress[key] = {"ok": False, "err": f"exception: {type(r).__name__}: {r}"}
            else:
                progress[key] = r
        save_progress(progress)
        if i + concurrent < len(pending):
            print(f"(sleep 30s before next batch)")
            await asyncio.sleep(30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lectures", nargs="+", help="Lecture numbers (or 'all')")
    ap.add_argument("--concurrent", type=int, default=1)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--model", default="haiku")
    args = ap.parse_args()

    playlist = load_playlist()
    if args.lectures == ["all"]:
        nums = [v["index"] for v in playlist]
    else:
        nums = [int(x) for x in args.lectures]

    asyncio.run(run(nums, args.concurrent, args.force, args.model))


if __name__ == "__main__":
    main()

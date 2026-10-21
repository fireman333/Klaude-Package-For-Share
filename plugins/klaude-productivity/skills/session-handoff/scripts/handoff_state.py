#!/usr/bin/env python3
"""Handoff state helper for the spec skill.

STATE.md is overwritten wholesale at every handoff; log.md keeps every previous
STATE verbatim (append-only, for grep only). This script enforces the rules the
model must not be trusted to follow on its own:

  locate        print where the handoff dir is for a cwd (JSON)
  commit-state  validate a new STATE, append the old one to log.md, swap atomically
  append-auto   append an entry to auto-log.md (for unattended flows; never STATE)

Validation (commit-state refuses to write if any fails):
  - size <= --max-bytes (default 3072)
  - required sections present
  - every open item [O<n>] in the old STATE appears in the new one, either still
    under the open-items section or under the closed-this-session section with
    a reason. Items may be closed, never silently dropped.
  - open-item ids are unique
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
LOOSE_DIRS = [HOME, HOME / "Desktop", HOME / "Downloads"]
SECTIONS = ["## 現在在做什麼", "## 卡住的點", "## 下一步", "## 未結案事項", "## 本次結案", "## 指標"]
OPEN_SEC = "## 未結案事項"
CLOSED_SEC = "## 本次結案"
ITEM_RE = re.compile(r"\[O(\d+)\]")
# An item line is "- [O<n>] text"; ids mentioned in prose elsewhere do not count.
ITEM_LINE_RE = re.compile(r"^\s*[-*]\s*\[O(\d+)\](.*)$")


def git(cwd, *args):
    try:
        out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def domain_truth(root):
    """Stats / MA projects keep their own source of truth; STATE.md only points to it."""
    if (root / "research_plan.json").exists():
        return "research_plan.json (step status lives there; update it, STATE points to the step)"
    if (root / "01_protocol").is_dir() and (root / "09_qa").is_dir():
        return "MA stages 00-10 (stage NOTES / 01_protocol/decision-log.md hold detail; STATE points to them)"
    for base in (root, root / "analysis"):
        if list(base.glob("data/*_stats.json")) and list(base.glob("scripts/[0-9][0-9]_*.py")):
            return f"hand-built stats project at {base} (decision_log rows hold decisions; STATE points to their IDs)"
    return None


def slugify(topic):
    raw = topic.strip()
    s = re.sub(r"[\s/\\:]+", "-", raw).strip("-.")[:60] or "misc"
    # Sanitising can merge distinct topics (a/b vs a:b); disambiguate with a stable hash.
    if s != raw:
        s += "-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
    return s


def locate(cwd, topic=None):
    cwd = Path(cwd).resolve()
    # Home / Desktop / Downloads / ~/.claude have no stable project -> per-topic state.
    loose = cwd in [d.resolve() for d in LOOSE_DIRS] or str(cwd).startswith(str((HOME / ".claude").resolve()))
    toplevel = git(cwd, "rev-parse", "--show-toplevel")
    if loose:
        if not topic:
            return {"kind": "loose", "dir": None, "needs_topic": True,
                    "state_root": str(HOME / ".claude/scratch/state")}
        root_dir = (HOME / ".claude/scratch/state").resolve()
        d = (root_dir / slugify(topic)).resolve()
        if d.parent != root_dir:
            raise SystemExit(f"topic escapes {root_dir}: {topic!r}")
        return {"kind": "loose", "dir": str(d), "git_root": None, **state_info(d)}
    root = cwd
    main_root = None
    if toplevel:
        root = Path(toplevel)
        # Linked worktree -> write to the main checkout so parallel worktrees never
        # each own a STATE that later collides on merge.
        # --git-common-dir without --path-format works on every git; it may be relative to cwd.
        # Bare-backed worktrees (common dir not named .git) keep their own .handoff/.
        common = git(cwd, "rev-parse", "--git-common-dir")
        if common and "\n" not in common:
            common_p = Path(common) if os.path.isabs(common) else (cwd / common)
            common_p = common_p.resolve()
            if common_p.name == ".git":
                main_root = common_p.parent
            if main_root.resolve() != root.resolve():
                root = main_root
    info = {"kind": "project", "dir": str(root / ".handoff"), "git_root": str(root) if toplevel else None,
            "linked_worktree": bool(main_root and toplevel and Path(toplevel).resolve() != main_root.resolve()),
            "has_openspec": (root / "openspec").is_dir(), **state_info(root / ".handoff")}
    r = domain_truth(root)
    if r:
        info["domain_truth"] = r
    return info


def state_info(d):
    s = Path(d) / "STATE.md"
    return {"state_sha": sha(s.read_text(encoding="utf-8")) if s.exists() else None}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def headers(text):
    return [ln.strip() for ln in text.splitlines() if ln.startswith("## ")]


def section_body(text, header):
    out, inside = [], False
    for ln in text.splitlines():
        if ln.startswith("## "):
            inside = ln.strip() == header
            continue
        if inside:
            out.append(ln)
    return "\n".join(out)


def items(text, header):
    """[(id, rest_of_line)] for item lines in a section; error strings for lines with >1 id."""
    found, errs = [], []
    for ln in section_body(text, header).splitlines():
        m = ITEM_LINE_RE.match(ln)
        if not m:
            continue
        if ITEM_RE.search(m.group(2)):
            errs.append(f"one item per line: {ln.strip()}")
        found.append((m.group(1), m.group(2)))
    return found, errs


def validate(new_text, old_text, max_bytes):
    errs = []
    size = len(new_text.encode("utf-8"))
    if size > max_bytes:
        errs.append(f"STATE is {size} bytes > limit {max_bytes}. Move detail into design.md / decisions/ and keep a pointer.")
    hs = headers(new_text)
    for s in SECTIONS:
        n = hs.count(s)
        if n == 0:
            errs.append(f"missing section (exact header line): {s}")
        elif n > 1:
            errs.append(f"duplicate section: {s}")
    open_new, e1 = items(new_text, OPEN_SEC)
    closed_new, e2 = items(new_text, CLOSED_SEC)
    errs += e1 + e2
    ids = [i for i, _ in open_new + closed_new]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        errs.append("duplicate item ids: " + ", ".join(f"O{i}" for i in sorted(dup, key=int)))
    for i, rest in closed_new:
        if len(rest.strip(" ：:-—")) < 2:
            errs.append(f"closed item O{i} has no reason")
    if old_text:
        open_old = {i for i, _ in items(old_text, OPEN_SEC)[0]}
        dropped = open_old - set(ids)
        if dropped:
            errs.append("open items dropped without being closed: " + ", ".join(f"O{i}" for i in sorted(dropped, key=int))
                        + f" — keep them under '{OPEN_SEC}' or close them under '{CLOSED_SEC}' with a reason.")
    return errs, size


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    # mkstemp creates 0600; give the file normal permissions under the current umask.
    umask = os.umask(0)
    os.umask(umask)
    os.chmod(tmp, 0o666 & ~umask)
    os.replace(tmp, path)


def ensure_attrs(d):
    ga = d / ".gitattributes"
    if not ga.exists():
        atomic_write(ga, "log.md merge=union\nauto-log.md merge=union\n")
    gi = d / ".gitignore"
    if not gi.exists():
        atomic_write(gi, ".lock\n")


class Lock:
    """Serialise read->validate->append->swap so two handoffs cannot interleave."""
    def __init__(self, d):
        d.mkdir(parents=True, exist_ok=True)
        self.f = open(d / ".lock", "w")
    def __enter__(self):
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self
    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def commit_state(d, new_file, max_bytes, dry_run, expect_sha):
    d = Path(d)
    state, log = d / "STATE.md", d / "log.md"
    new_text = Path(new_file).read_text(encoding="utf-8")
    if not new_text.endswith("\n"):
        new_text += "\n"
    with Lock(d):
        old_text = state.read_text(encoding="utf-8") if state.exists() else ""
        cur = sha(old_text) if old_text else None
        if expect_sha is not None and expect_sha != (cur or "none"):
            print(json.dumps({"ok": False, "errors": [
                f"STATE.md changed since you read it (expected {expect_sha}, now {cur or 'none'}): another session handed off. "
                "Re-read STATE.md, merge its open items into your draft, and retry with the new --expect-sha."]},
                ensure_ascii=False, indent=1))
            return 1
        errs, size = validate(new_text, old_text, max_bytes)
        if errs:
            print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False, indent=1))
            return 1
        if dry_run:
            print(json.dumps({"ok": True, "dry_run": True, "bytes": size}, ensure_ascii=False))
            return 0
        if old_text:
            prev = log.read_text(encoding="utf-8") if log.exists() else ""
            # A crash between append and swap leaves the old STATE already logged; do not log it twice.
            if not prev.rstrip().endswith(old_text.rstrip()):
                stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
                with open(log, "a", encoding="utf-8") as f:
                    f.write(("\n" if prev else "") + f"<!-- superseded {stamp} sha {cur} -->\n{old_text.rstrip()}\n")
        elif not log.exists():
            atomic_write(log, "# Handoff log — 舊版 STATE 依時間附加於此，只供 grep，resume 不整份讀\n")
        atomic_write(state, new_text)
        ensure_attrs(d)
    print(json.dumps({"ok": True, "bytes": size, "state": str(state), "log": str(log),
                      "first_state": not old_text, "state_sha": sha(new_text)}, ensure_ascii=False))
    return 0


def append_auto(d, title, body_file):
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    ensure_attrs(d)
    body = Path(body_file).read_text(encoding="utf-8").rstrip() if body_file else ""
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(d / "auto-log.md", "a", encoding="utf-8") as f:
        f.write(f"\n## {stamp} — {title}\n\n{body}\n")
    print(str(d / "auto-log.md"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("locate"); p.add_argument("--cwd", default=os.getcwd()); p.add_argument("--topic")
    p = sub.add_parser("commit-state"); p.add_argument("--dir", required=True); p.add_argument("--new", required=True)
    p.add_argument("--max-bytes", type=int, default=3072); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--expect-sha", help="state_sha from locate when you read STATE ('none' if there was none)")
    p = sub.add_parser("append-auto"); p.add_argument("--dir", required=True); p.add_argument("--title", required=True)
    p.add_argument("--body-file")
    a = ap.parse_args()
    if a.cmd == "locate":
        print(json.dumps(locate(a.cwd, a.topic), ensure_ascii=False))
        return 0
    if a.cmd == "commit-state":
        return commit_state(a.dir, a.new, a.max_bytes, a.dry_run, a.expect_sha)
    return append_auto(a.dir, a.title, a.body_file)


if __name__ == "__main__":
    sys.exit(main())

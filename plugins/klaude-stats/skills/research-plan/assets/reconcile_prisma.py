"""PRISMA number reconciliation for meta-analysis projects.

Why this exists
---------------
A PRISMA flow diagram is the one place a systematic review states, as plain integers,
what it actually did. Nothing checks those integers. `prisma_flow.py` (in the
`ma-manuscript-quarto` skill) *generates* a flow summary from artifacts; it never asks
whether the manuscript agrees with it, and it aborts the moment one of its expected
input logs is absent -- which is why, in practice, it does not get run at all.

The failure this catches is not arithmetic. It is that screening gets re-run -- new
framing, new prompts, a second reviewer pass -- and the project ends up holding two
sets of screening decisions. The manuscript then quotes one round while every
downstream artifact was built from the other. Both numbers are individually "real",
so no eyeball catches it, and the flow diagram describes a selection process that
never happened.

Real case (某 MA 專案, 2026-04): the manuscript reported 47 records advancing to full text
(V2 title/abstract screening) while `04_fulltext/fulltext_decisions.csv` holds 185 rows
(V1). Seven of the claimed 47 were never full-text assessed at all, and the 178
full-text exclusions were never reported anywhere in the manuscript.

What it does
------------
1. Counts each PRISMA stage from the actual files on disk -- decision CSVs, record
   tables, exclusion lists, the included bibliography -- discovering columns by name
   rather than assuming a schema.
2. Extracts the PRISMA numbers a project *claims*, from `07_manuscript/*.qmd` and the
   `09_qa/*.md` reports.
3. Reconciles the two and prints every gap as "claimed X / counted Y / delta Z".
4. Fingerprints each screening round (forwarded count, include/maybe split, kappa,
   the actual set of record IDs) and attributes every claim to a round. Claims that
   attribute to different rounds, or to a round the downstream stage never consumed,
   are reported as version mixing.

Usage
-----
    python3 reconcile_prisma.py PROJECT_DIR [--json OUT.json] [--quiet]

Fail-closed
-----------
Every step that reads a file can fail: the file is corrupt, empty, or the column the
step needs got renamed. When that happens this tool must say "I could not read this",
never "the numbers agree". An auditor that reports OK on input it did not understand is
worse than no auditor, because it converts "unchecked" into "passed". So every read
failure, missing expected column, and zero-row count is recorded as a blocker, and one
blocker forces exit 2 -- even when the stages that *did* parse all reconcile.

Exit codes (shared convention across research/ tooling)
    2  cannot check -- not an MA project layout, no screening decisions, no manuscript to
       reconcile against, or any stage that could not be parsed (unreadable file, missing
       adjudicated-decision column, zero rows where rows are required). An unreconcilable
       project is not a passing one.
    1  ran, and found discrepancies, version mixing, or counted-but-never-reported stages
    0  ran, everything parsed, everything reconciles; the summary names every stage checked
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Fail-closed bookkeeping -- 「看不懂」一律要留下紀錄，不准靜默跳過
# ---------------------------------------------------------------------------

# 單一 process 只跑一次對帳，`reconcile()` 進場時清空。用模組層清單是為了讓每個讀檔點
# 都能就地記錄，不必把 collector 一路穿過所有 scan_* 函式（diff 越小越好）。
_BLOCKERS: list[dict] = []


def _blocker(stage: str, detail: str) -> None:
    """記一筆「這個環節無法解析」。只要有一筆，退出碼就是 2，不會變成 0。"""
    entry = {"stage": stage, "detail": detail}
    if entry not in _BLOCKERS:
        _BLOCKERS.append(entry)


def _read_text(path: Path, stage: str) -> str | None:
    """讀純文字檔；讀不到就記 blocker 並回 None，不靜默跳過。"""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        _blocker(stage, f"{path.name} 讀不出來（{exc}）")
        return None


# ---------------------------------------------------------------------------
# Stage counting -- read what is actually on disk
# ---------------------------------------------------------------------------

# A column counts as the adjudicated decision only if it says so. `Reviewer1_Decision`
# and `FT_Reviewer2_Decision` are per-reviewer opinions, not the stage outcome.
_FINAL_EXACT = {"decision", "final_decision", "final decision", "outcome"}
_ID_CANDIDATES = ("pmid", "record_id", "recordid", "id", "doi", "covidence_id", "refid")

_INCLUDE = {"include", "included", "yes", "in"}
_MAYBE = {"maybe", "unclear", "defer", "uncertain"}
_EXCLUDE = {"exclude", "excluded", "no", "out"}


def _is_final_col(name: str) -> bool:
    low = name.strip().lower()
    if low in _FINAL_EXACT:
        return True
    return "final" in low and "decision" in low


def _find_final_col(fieldnames) -> str | None:
    for name in fieldnames or []:
        if _is_final_col(name):
            return name
    return None


def _find_id_col(fieldnames) -> str | None:
    lowered = {(n or "").strip().lower(): n for n in (fieldnames or [])}
    for want in _ID_CANDIDATES:
        if want in lowered:
            return lowered[want]
    return None


def _read_rows(path: Path) -> tuple[list[dict], list[str]]:
    delim = "\t" if path.suffix.lower() in (".tsv", ".tab") else ","
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delim)
        return list(reader), list(reader.fieldnames or [])


def _bucket(value: str) -> str | None:
    low = (value or "").strip().lower()
    if not low:
        return None
    if low in _INCLUDE:
        return "include"
    if low in _MAYBE:
        return "maybe"
    if low in _EXCLUDE:
        return "exclude"
    return "other"


def _version_of(stem: str) -> str:
    """Derive a round label from a filename. `decisions_v2_final` -> v2, else v1."""
    match = re.search(r"_v(\d+)(?![0-9])", stem.lower())
    return f"v{match.group(1)}" if match else "v1"


def _data_row_count(path: Path) -> int | None:
    """存在但讀不出來、或存在但一列資料都沒有，都是「看不懂」，不是「沒有這一關」。"""
    if not path.exists():
        return None
    try:
        rows, _ = _read_rows(path)
    except Exception as exc:
        _blocker("stage counting", f"{path.name} 存在但讀不出來（{exc}）")
        return None
    if not rows:
        _blocker("stage counting", f"{path.name} 存在但清點到 0 筆資料列")
        return None
    return len(rows)


def scan_screening(root: Path) -> dict:
    """Inventory every title/abstract screening decision file, grouped by round."""
    versions: dict[str, dict] = {}
    skipped: list[dict] = []
    # 每個 round label 底下「看到幾個檔 / 其中幾個真的解析成功」。一個 round 在磁碟上存在
    # 卻沒有任何一個檔交得出裁定欄位 = 那一輪根本沒被清點到，這是 blocker，不是跳過。
    seen_labels: dict[str, int] = {}
    for path in sorted(root.glob("03_screening/*/decisions*.csv")):
        label_seen = _version_of(path.stem)
        seen_labels[label_seen] = seen_labels.get(label_seen, 0) + 1
        try:
            rows, fields = _read_rows(path)
        except Exception as exc:  # pragma: no cover - unreadable file
            skipped.append({"file": str(path.relative_to(root)), "reason": f"unreadable: {exc}"})
            _blocker("title/abstract screening", f"{path.name} 讀不出來（{exc}）")
            continue
        final_col = _find_final_col(fields)
        if not final_col:
            skipped.append(
                {
                    "file": str(path.relative_to(root)),
                    "reason": "no adjudicated final-decision column (per-reviewer or pre-adjudication file)",
                }
            )
            continue
        if not rows:
            skipped.append({"file": str(path.relative_to(root)), "reason": "zero data rows"})
            _blocker("title/abstract screening", f"{path.name} 有裁定欄位但清點到 0 筆決策")
            continue
        id_col = _find_id_col(fields)
        counts = {"include": 0, "maybe": 0, "exclude": 0, "other": 0, "blank": 0}
        forwarded: set[str] = set()
        for row in rows:
            bucket = _bucket(row.get(final_col, ""))
            if bucket is None:
                counts["blank"] += 1
                continue
            counts[bucket] += 1
            if bucket in ("include", "maybe") and id_col:
                rid = (row.get(id_col) or "").strip()
                if rid:
                    forwarded.add(rid)
        label = _version_of(path.stem)
        entry = {
            "version": label,
            "file": str(path.relative_to(root)),
            "final_column": final_col,
            "id_column": id_col,
            "n_records": len(rows),
            "counts": {k: v for k, v in counts.items() if v or k in ("include", "maybe", "exclude")},
            "n_forwarded": counts["include"] + counts["maybe"],
            "forwarded_ids": forwarded,
        }
        prev = versions.get(label)
        # Same round, two files (e.g. `decisions_v2.csv` and `decisions_v2_final.csv`):
        # the adjudicated one wins, then the newer one.
        if prev is None:
            versions[label] = entry
        else:
            better = "final" in path.stem.lower() and "final" not in Path(prev["file"]).stem.lower()
            if better or path.stat().st_mtime > (root / prev["file"]).stat().st_mtime:
                versions[label] = entry
    for label, n_files in sorted(seen_labels.items()):
        if label not in versions:
            _blocker(
                "title/abstract screening",
                f"篩選輪次 {label} 在磁碟上有 {n_files} 個 decisions*.csv，"
                f"但沒有任何一個交得出裁定欄位（欄位名可能被改過）——這一輪等於沒被清點",
            )
    return {"versions": versions, "skipped": skipped}


def scan_fulltext(root: Path) -> dict | None:
    """Find the adjudicated full-text decision file and count what it holds."""
    best = None
    n_candidates = 0
    for path in sorted(root.glob("04_fulltext/*decision*.csv")):
        n_candidates += 1
        try:
            rows, fields = _read_rows(path)
        except Exception as exc:
            # 以前這裡是靜默 continue：檔案壞掉 → 全文關卡消失 → 上游宣稱改用寬鬆比對
            # → 錯的數字被蓋章成 OK。現在一律留紀錄。
            _blocker("full text", f"{path.name} 讀不出來（{exc}）")
            continue
        final_col = _find_final_col(fields)
        if not final_col:
            continue
        if not rows:
            _blocker("full text", f"{path.name} 有裁定欄位但清點到 0 筆決策")
            continue
        id_col = _find_id_col(fields)
        counts = {"include": 0, "maybe": 0, "exclude": 0, "other": 0, "blank": 0}
        ids: set[str] = set()
        for row in rows:
            bucket = _bucket(row.get(final_col, ""))
            if bucket is None:
                counts["blank"] += 1
            else:
                counts[bucket] += 1
            if id_col:
                rid = (row.get(id_col) or "").strip()
                if rid:
                    ids.add(rid)
        entry = {
            "file": str(path.relative_to(root)),
            "final_column": final_col,
            "id_column": id_col,
            "n_assessed": len(rows),
            "counts": counts,
            "ids": ids,
            # The upstream label carried into this file, when the pipeline recorded one.
            "upstream_column": next(
                (f for f in fields if "stage3" in (f or "").lower() or "screen" in (f or "").lower()),
                None,
            ),
        }
        if best is None or entry["n_assessed"] > best["n_assessed"]:
            best = entry
    if best is None:
        # 沒有可判讀的全文裁定檔 = 無法知道下游到底吃了哪一輪篩選，
        # 而「哪一輪」正是這支工具唯一能抓到 version mixing 的錨點。
        _blocker(
            "full text",
            f"04_fulltext/ 有 {n_candidates} 個 *decision*.csv，但沒有任何一個交得出裁定欄位"
            if n_candidates
            else "04_fulltext/ 底下找不到任何 *decision*.csv",
        )
    elif not best["ids"]:
        _blocker("full text", f"{Path(best['file']).name} 沒有可辨識的紀錄 ID 欄位，無法比對篩選輪次")
    return best


def _count_bib_entries(path: Path) -> int | None:
    if not path.exists():
        return None
    text = _read_text(path, "included bibliography")
    if text is None:
        return None
    n = len(re.findall(r"^@\w+\s*\{", text, re.M))
    if n == 0:
        _blocker("included bibliography", f"{path.name} 存在但清點到 0 筆書目條目")
        return None
    return n


def scan_stages(root: Path) -> dict:
    """Observed counts for each PRISMA slot, with the file each one came from."""
    observed: dict[str, list[dict]] = {}

    def add(slot: str, value, source: str, version: str | None = None, note: str = ""):
        if value is None:
            return
        observed.setdefault(slot, []).append(
            {"value": int(value), "source": source, "version": version, "note": note}
        )

    # -- identification / dedup ------------------------------------------------
    for path in sorted(root.glob("02_search/*/*records*.tsv")):
        add("records_identified", _data_row_count(path), str(path.relative_to(root)),
            note="records retrieved with metadata from this source")
    for path in sorted(root.glob("02_search/*/log.md")):
        log_text = _read_text(path, "search log")
        if log_text is None:
            continue
        for m in re.finditer(r"(\d[\d,]*)\s+(?:total\s+)?hits\b", log_text, re.I):
            add("records_identified", int(m.group(1).replace(",", "")), str(path.relative_to(root)),
                note="raw hit count declared in the search log (no record file holds it)")
        for m in re.finditer(r"Records identified[^|\n]*\|\s*\*{0,2}(\d[\d,]*)", log_text, re.I):
            add("records_identified", int(m.group(1).replace(",", "")), str(path.relative_to(root)),
                note="declared in the search log's own PRISMA table")
    for path in sorted(root.glob("02_search/*/*ids.txt")):
        id_text = _read_text(path, "search identifier list")
        if id_text is None:
            continue
        hits = len([ln for ln in id_text.splitlines() if ln.strip()])
        if hits == 0:
            _blocker("search identifier list", f"{path.name} 存在但清點到 0 個識別碼")
            continue
        add("records_identified", hits, str(path.relative_to(root)),
            note="raw identifier list (hits before metadata retrieval)")
    for name in ("combined_records.tsv", "combined_records.csv"):
        path = root / "02_search" / name
        add("records_after_dedup", _data_row_count(path), f"02_search/{name}",
            note="merged corpus across search rounds")

    screening = scan_screening(root)
    fulltext = scan_fulltext(root)

    # -- title/abstract screening ---------------------------------------------
    for label, ver in sorted(screening["versions"].items()):
        add("records_screened", ver["n_records"], ver["file"], label)
        add("reports_sought", ver["n_forwarded"], ver["file"], label,
            note=f"{ver['counts'].get('include', 0)} include + {ver['counts'].get('maybe', 0)} maybe")
        add("records_excluded_screening", ver["counts"].get("exclude"), ver["file"], label)
    add("records_excluded_screening", _data_row_count(root / "03_screening" / "round-01" / "exclusions.csv"),
        "03_screening/round-01/exclusions.csv")

    # -- full text -------------------------------------------------------------
    if fulltext:
        add("reports_assessed", fulltext["n_assessed"], fulltext["file"])
        add("fulltext_excluded", fulltext["counts"].get("exclude"), fulltext["file"])
        add("studies_included", fulltext["counts"].get("include"), fulltext["file"],
            note="include decisions = reports, which may exceed unique studies")
    add("fulltext_excluded", _data_row_count(root / "04_fulltext" / "ft_exclusions.csv"),
        "04_fulltext/ft_exclusions.csv")
    add("reports_assessed", _data_row_count(root / "04_fulltext" / "manifest.csv"),
        "04_fulltext/manifest.csv", note="retrieval manifest")

    # -- included set ----------------------------------------------------------
    add("studies_included", _count_bib_entries(root / "04_fulltext" / "included.bib"),
        "04_fulltext/included.bib", note="bib entries = reports")
    add("studies_included", _data_row_count(root / "05_extraction" / "extraction.csv"),
        "05_extraction/extraction.csv", note="extraction rows = unique studies")

    return {"observed": observed, "screening": screening, "fulltext": fulltext}


def scan_kappa(root: Path) -> dict[str, float]:
    """Cohen's kappa per screening round, read from the agreement reports."""
    out: dict[str, float] = {}
    for path in sorted(root.glob("03_screening/*/agreement*.md")):
        text = _read_text(path, "screening agreement report")
        if text is None:
            continue
        match = _KAPPA.search(text)
        if not match:
            continue
        label = _version_of(path.stem)
        # `agreement_pre_adjudication.md` and `agreement.md` are both round 1; keep the first seen.
        out.setdefault(label, float(match.group(1)))
    return out


# ---------------------------------------------------------------------------
# Claim extraction -- what the prose says the numbers were
# ---------------------------------------------------------------------------

_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_NOUN = r"(?:records?|reports?|citations?|references?|articles?|studies|stud(?:y|ies)|trials?|RCTs?|titles?|abstracts?|full[- ]?texts?|hits?)"
_NUM = r"([\d][\d,]*)"

# Each pattern maps to a PRISMA slot. Up to two filler words are allowed between the
# number and its noun so that "107 interventional studies" and "6 unique RCTs" match.
_CLAIM_PATTERNS: list[tuple[str, str]] = [
    ("records_identified", rf"(?:identified|yielded|returned|retrieved)\s+{_NUM}\s+(?:\w+\s+){{0,2}}{_NOUN}"),
    ("records_identified", rf"{_NUM}\s+(?:\w+\s+){{0,2}}{_NOUN}\s+(?:were\s+)?(?:identified|retrieved)"),
    ("records_screened", rf"{_NUM}\s+(?:\w+\s+){{0,2}}{_NOUN}\s+(?:were\s+)?screened"),
    ("records_screened", rf"screened\s+(?:the\s+)?{_NUM}\s+(?:\w+\s+){{0,2}}{_NOUN}"),
    ("reports_sought",
     rf"{_NUM}\s+(?:\w+\s+){{0,2}}{_NOUN}\s+(?:were\s+)?(?:advanced|progressed|proceeded|forwarded|moved|went|carried)\s*(?:on\s+)?(?:to|for|forward)"),
    ("reports_sought", rf"{_NUM}\s+(?:\w+\s+){{0,2}}{_NOUN}\s+(?:were\s+)?sought for retrieval"),
    ("reports_assessed", rf"{_NUM}\s+(?:\w+\s+){{0,2}}{_NOUN}\s+(?:were\s+)?assessed for eligibility"),
    ("fulltext_excluded",
     rf"{_NUM}\s+(?:\w+\s+){{0,2}}(?:{_NOUN}\s+)?(?:were\s+)?excluded\s+(?:at|after|during|in|following|on)\s+(?:the\s+)?full[- ]?text"),
    ("fulltext_excluded", rf"{_NUM}\s+full[- ]?text exclusions?"),
    ("studies_included",
     rf"{_NUM}\s+(?:\w+\s+){{0,3}}?(?:{_NOUN})\s+(?:\w+\s+){{0,4}}?(?:met (?:the )?(?:eligibility|inclusion)|were included|fulfilled|satisfied)"),
]
# Word-number variant of the "N trials met eligibility" claim ("Six RCTs ... met eligibility").
_WORD_INCLUDED = re.compile(
    rf"\b({'|'.join(_WORD_NUM)})\s+(?:\w+\s+){{0,3}}?{_NOUN}\s+(?:\w+\s+){{0,4}}?(?:met (?:the )?(?:eligibility|inclusion)|were included)",
    re.I,
)
# The include/maybe split behind a forwarding claim -- the strongest round fingerprint.
_SPLIT = re.compile(r"(\d+)\s+includes?d?\s*(?:,|\+)\s*(\d+)\s+maybes?\b", re.I)
_KAPPA = re.compile(r"(?:kappa|\u03ba)\s*[:=]\s*([0-9]*\.?[0-9]+)", re.I)


def _sentence_at(text: str, pos: int) -> str:
    start = max(text.rfind(". ", 0, pos), text.rfind("\n", 0, pos)) + 1
    end = text.find(". ", pos)
    end = len(text) if end == -1 else end + 1
    return " ".join(text[start:end].split())[:300]


def extract_claims(root: Path) -> list[dict]:
    """Pull PRISMA numbers out of the manuscript and the QA reports."""
    claims: list[dict] = []
    targets = sorted(root.glob("07_manuscript/*.qmd")) + sorted(root.glob("09_qa/*.md"))
    for path in targets:
        text = _read_text(path, "claim extraction")
        if text is None:
            continue
        rel = str(path.relative_to(root))
        doc = "manuscript" if rel.startswith("07_manuscript") else "qa"

        def line_of(pos: int) -> int:
            return text.count("\n", 0, pos) + 1

        for slot, pattern in _CLAIM_PATTERNS:
            for m in re.finditer(pattern, text, re.I):
                claims.append({
                    "slot": slot,
                    "value": int(m.group(1).replace(",", "")),
                    "file": rel, "doc": doc, "line": line_of(m.start()),
                    "quote": _sentence_at(text, m.start()),
                })
        for m in _WORD_INCLUDED.finditer(text):
            claims.append({
                "slot": "studies_included", "value": _WORD_NUM[m.group(1).lower()],
                "file": rel, "doc": doc, "line": line_of(m.start()),
                "quote": _sentence_at(text, m.start()),
            })
        for m in _SPLIT.finditer(text):
            claims.append({
                "slot": "screening_split",
                "value": int(m.group(1)) + int(m.group(2)),
                "split": [int(m.group(1)), int(m.group(2))],
                "file": rel, "doc": doc, "line": line_of(m.start()),
                "quote": _sentence_at(text, m.start()),
            })
        for m in _KAPPA.finditer(text):
            claims.append({
                "slot": "screening_kappa", "value": None, "kappa": float(m.group(1)),
                "file": rel, "doc": doc, "line": line_of(m.start()),
                "quote": _sentence_at(text, m.start()),
            })

    # Same number, same slot, same line asserted by two overlapping patterns -> keep one.
    seen, unique = set(), []
    for claim in claims:
        key = (claim["slot"], claim.get("value"), claim.get("kappa"), claim["file"], claim["line"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(claim)
    return unique


# ---------------------------------------------------------------------------
# Round attribution and version-mixing detection
# ---------------------------------------------------------------------------

def build_signatures(screening: dict, kappa: dict[str, float]) -> dict[str, dict]:
    """One numeric fingerprint per screening round, for attributing claims back to it."""
    sigs: dict[str, dict] = {}
    for label, ver in screening["versions"].items():
        counts = ver["counts"]
        sigs[label] = {
            "reports_sought": ver["n_forwarded"],
            "screening_split": ver["n_forwarded"],
            "split": [counts.get("include", 0), counts.get("maybe", 0)],
            "records_screened": ver["n_records"],
            "records_excluded_screening": counts.get("exclude", 0),
            "kappa": kappa.get(label),
            "file": ver["file"],
        }
    return sigs


def attribute(claim: dict, sigs: dict[str, dict]) -> list[str]:
    """Which screening round(s) is this claim numerically consistent with?"""
    hits = []
    for label, sig in sigs.items():
        if claim["slot"] == "screening_kappa":
            k = sig.get("kappa")
            if k is not None and round(k, 2) == round(claim["kappa"], 2):
                hits.append(label)
            continue
        if claim["slot"] == "screening_split":
            if claim.get("split") == sig["split"]:
                hits.append(label)
            continue
        expected = sig.get(claim["slot"])
        if expected is not None and expected == claim["value"]:
            hits.append(label)
    return hits


def consumed_version(screening: dict, fulltext: dict | None) -> dict:
    """Which screening round did the full-text stage actually take as input?"""
    if not fulltext or not fulltext.get("ids"):
        return {"version": None, "basis": "no full-text record ids available"}
    ft_ids = fulltext["ids"]
    best, best_score = None, -1.0
    detail = {}
    for label, ver in screening["versions"].items():
        fwd = ver["forwarded_ids"]
        if not fwd:
            continue
        inter = len(fwd & ft_ids)
        union = len(fwd | ft_ids) or 1
        jacc = inter / union
        detail[label] = {
            "forwarded": len(fwd), "overlap": inter,
            "jaccard": round(jacc, 4), "exact_set_match": fwd == ft_ids,
            "forwarded_never_assessed": sorted(fwd - ft_ids),
        }
        if jacc > best_score:
            best, best_score = label, jacc
    if best is not None and best_score <= 0:
        # 每一輪的重疊都是 0，`best` 只是迴圈順序的平手結果，不是證據。拿它當錨點會讓
        # 整張對帳表建立在一個憑空指定的輪次上——這正是要防的「看不懂卻照樣宣告」。
        _blocker(
            "round attribution",
            "全文裁定檔的紀錄 ID 與任何一輪篩選都沒有交集（可能是檔案損毀或 ID 欄位對不上），"
            "無法判定下游實際吃了哪一輪",
        )
    return {"version": best, "basis": "record-id set comparison against the full-text file", "per_version": detail}


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

_SLOT_LABEL = {
    "records_identified": "Records identified",
    "records_after_dedup": "Records after dedup / merge",
    "records_screened": "Records screened (title/abstract)",
    "records_excluded_screening": "Excluded at title/abstract",
    "reports_sought": "Advanced to full text",
    "reports_assessed": "Full texts assessed",
    "fulltext_excluded": "Excluded at full text",
    "studies_included": "Included in synthesis",
}
# Slots a PRISMA 2020 flow diagram must state. Counted but unreported = item 16 gap.
_MUST_REPORT = ("reports_sought", "fulltext_excluded", "studies_included")
# Counts that belong to one screening round. A claim here must match the round the
# downstream stage actually consumed; matching any other round is version mixing.
_VERSIONED_SLOTS = ("records_screened", "reports_sought", "records_excluded_screening")


def reconcile(root: Path) -> dict:
    _BLOCKERS.clear()
    stages = scan_stages(root)
    observed = stages["observed"]
    screening = stages["screening"]
    fulltext = stages["fulltext"]
    kappa = scan_kappa(root)
    sigs = build_signatures(screening, kappa)
    claims = extract_claims(root)
    consumed = consumed_version(screening, fulltext)

    # 有兩輪以上篩選卻認不出下游吃了哪一輪 → 版本比對只能退回寬鬆模式，
    # 而寬鬆模式下「任何一輪對得上就算 OK」正是把錯數字蓋章的那條路。
    if len(screening["versions"]) > 1 and not consumed.get("version"):
        _blocker(
            "round attribution",
            f"磁碟上有 {len(screening['versions'])} 輪篩選，但無法判定全文階段實際吃了哪一輪"
            f"（{consumed.get('basis', '無依據')}）——版本混用無法判定",
        )

    for claim in claims:
        claim["attributed_versions"] = attribute(claim, sigs)

    findings: list[dict] = []
    rows: list[dict] = []

    # -- slot-by-slot comparison ----------------------------------------------
    for slot in _SLOT_LABEL:
        cands = observed.get(slot, [])
        slot_claims = [c for c in claims if c["slot"] == slot]
        counted_values = sorted({c["value"] for c in cands})
        if slot_claims and cands:
            # Identification counts legitimately come from several sources (raw hit list,
            # each database's record table), so any candidate may match. Screening counts
            # do not: only one round can be the one the project actually ran on, and
            # matching a different round is the defect, not a pass.
            strict_version = consumed.get("version") if slot in _VERSIONED_SLOTS else None
            for claim in slot_claims:
                if strict_version:
                    anchor = _anchor_value(slot, cands, strict_version)
                    if claim["value"] == anchor["value"]:
                        rows.append({"slot": slot, "claimed": claim["value"], "counted": anchor["value"],
                                     "delta": 0, "status": "OK", "claim": claim,
                                     "counted_from": anchor["source"]})
                        continue
                    other_round = next((c for c in cands
                                        if c["value"] == claim["value"] and c.get("version")), None)
                else:
                    matches = [c for c in cands if c["value"] == claim["value"]]
                    if matches:
                        rows.append({"slot": slot, "claimed": claim["value"], "counted": claim["value"],
                                     "delta": 0, "status": "OK", "claim": claim,
                                     "counted_from": matches[0]["source"]})
                        continue
                    anchor = _anchor_value(slot, cands, consumed.get("version"))
                    other_round = None

                delta = claim["value"] - anchor["value"]
                rows.append({"slot": slot, "claimed": claim["value"], "counted": anchor["value"],
                             "delta": delta, "status": "MISMATCH",
                             "claim": claim, "counted_from": anchor["source"],
                             "other_counted": counted_values})
                if other_round:
                    message = (f"{_SLOT_LABEL[slot]}: {claim['file']}:{claim['line']} claims "
                               f"{claim['value']}, which is the {other_round['version']} screening round "
                               f"({other_round['source']}). The full-text stage was run on "
                               f"{strict_version}, which counts {anchor['value']} "
                               f"({anchor['source']}); delta {delta:+d}.")
                    kind = "wrong_screening_round"
                else:
                    message = (f"{_SLOT_LABEL[slot]}: {claim['file']}:{claim['line']} claims "
                               f"{claim['value']}, the files count {anchor['value']} "
                               f"({anchor['source']}); delta {delta:+d}")
                    kind = "claim_vs_count"
                findings.append({
                    "severity": "P1",
                    "kind": kind,
                    "slot": slot,
                    "message": message,
                    "claim": {k: claim[k] for k in ("file", "line", "quote", "value", "attributed_versions")},
                    "counted_candidates": [{k: c[k] for k in ("value", "source", "version", "note")} for c in cands],
                })
        elif cands and not slot_claims and slot in _MUST_REPORT:
            anchor = _anchor_value(slot, cands, consumed.get("version"))
            rows.append({"slot": slot, "claimed": None, "counted": anchor["value"], "delta": None,
                         "status": "NOT IN PAPER", "claim": None, "counted_from": anchor["source"]})
            findings.append({
                "severity": "P2",
                "kind": "counted_but_never_reported",
                "slot": slot,
                "message": (f"{_SLOT_LABEL[slot]}: counted {anchor['value']} in {anchor['source']}, "
                            + (f"stated only in the QA reports ({', '.join(sorted({c['file'] for c in slot_claims}))})"
                               if slot_claims else "stated nowhere")
                            + " — it never appears in 07_manuscript/, which PRISMA 2020 item 16 requires."),
            })
        elif cands:
            anchor = _anchor_value(slot, cands, consumed.get("version"))
            rows.append({"slot": slot, "claimed": None, "counted": anchor["value"], "delta": None,
                         "status": "counted only", "claim": None, "counted_from": anchor["source"]})

    # -- PRISMA 2020 item 16 is a requirement on the manuscript, not on the QA folder --
    for slot in _MUST_REPORT:
        cands = observed.get(slot, [])
        slot_claims = [c for c in claims if c["slot"] == slot]
        if not cands or not slot_claims:
            continue
        if any(c["doc"] == "manuscript" for c in slot_claims):
            continue
        anchor = _anchor_value(slot, cands, consumed.get("version"))
        elsewhere = sorted({c["file"] for c in slot_claims})
        for row in rows:
            if row["slot"] == slot and row["status"] == "OK":
                row["status"] = "QA ONLY"
        findings.append({
            "severity": "P2",
            "kind": "not_reported_in_manuscript",
            "slot": slot,
            "message": (f"{_SLOT_LABEL[slot]}: {anchor['value']} counted in {anchor['source']} and "
                        f"stated in {', '.join(elsewhere)}, but the number appears nowhere in "
                        f"07_manuscript/ — PRISMA 2020 item 16 requires it in the flow diagram."),
        })

    # -- version mixing --------------------------------------------------------
    mixing = _detect_mixing(claims, sigs, consumed, screening, fulltext)
    findings.extend(mixing["findings"])

    return {
        "project": str(root),
        "screening_versions": {
            label: {k: v for k, v in ver.items() if k != "forwarded_ids"}
            for label, ver in screening["versions"].items()
        },
        "screening_files_skipped": screening["skipped"],
        "screening_kappa": kappa,
        "fulltext_stage": ({k: v for k, v in fulltext.items() if k != "ids"} if fulltext else None),
        "observed_counts": observed,
        "claims": claims,
        "consumed_version": consumed,
        "version_mixing": mixing["summary"],
        "table": rows,
        "findings": findings,
        "generator_tooling": _generator_status(root),
        # 最後才收，_generator_status() 也會往裡面加。
        "blockers": list(_BLOCKERS),
    }


def _anchor_value(slot: str, cands: list[dict], consumed: str | None) -> dict:
    """The counted value to reconcile against: prefer the round downstream actually used."""
    if consumed:
        for c in cands:
            if c.get("version") == consumed:
                return c
    for c in cands:
        if c.get("version") is None:
            return c
    return cands[0]


def _detect_mixing(claims, sigs, consumed, screening, fulltext) -> dict:
    findings, per_doc = [], {}
    attributed = [c for c in claims if c.get("attributed_versions")]
    for claim in attributed:
        # Only claims that pin down exactly one round carry version information.
        if len(claim["attributed_versions"]) == 1:
            per_doc.setdefault(claim["doc"], {}).setdefault(claim["attributed_versions"][0], []).append(claim)

    doc_versions = {doc: sorted(vs) for doc, vs in per_doc.items()}
    all_versions = sorted({v for vs in doc_versions.values() for v in vs})
    used = consumed.get("version")

    for doc, versions in doc_versions.items():
        if len(versions) > 1:
            findings.append({
                "severity": "P1", "kind": "version_mixing_within_document",
                "message": (f"The {doc} quotes numbers from {len(versions)} different screening rounds "
                            f"({', '.join(versions)}) — its flow diagram describes no single real selection process."),
                "evidence": {v: [f"{c['file']}:{c['line']} {c['slot']}="
                                 f"{c.get('value') if c.get('value') is not None else c.get('kappa')}"
                                 for c in per_doc[doc][v]] for v in versions},
            })

    if len(all_versions) > 1:
        findings.append({
            "severity": "P1", "kind": "version_mixing_across_project",
            "message": ("This project mixes two rounds of screening results: "
                        + "; ".join(f"{doc} quotes {'/'.join(vs)}" for doc, vs in sorted(doc_versions.items()))
                        + f". The full-text stage actually consumed {used or 'an unidentified round'}."),
            "evidence": doc_versions,
        })

    if used:
        for doc, versions in doc_versions.items():
            orphans = [v for v in versions if v != used]
            if not orphans:
                continue
            detail = consumed.get("per_version", {})
            never = detail.get(orphans[0], {}).get("forwarded_never_assessed", [])
            findings.append({
                "severity": "P1", "kind": "claims_an_unconsumed_version",
                "message": (f"The {doc} reports the {'/'.join(orphans)} screening round, but the full-text "
                            f"stage was run on {used}. Those {'/'.join(orphans)} decisions were never read "
                            f"downstream" + (f"; {len(never)} of the records it says advanced to full text "
                                             f"were never full-text assessed." if never else ".")),
                "evidence": {"consumed_version": used, "claimed_versions": orphans,
                             "records_never_assessed": never[:20],
                             "n_records_never_assessed": len(never)},
            })

    return {"findings": findings,
            "summary": {"per_document": doc_versions, "consumed_by_fulltext": used,
                        "mixed": len(all_versions) > 1}}


def _generator_status(root: Path) -> dict:
    """Why the existing PRISMA generator has not been producing these numbers."""
    needed = {
        "02_search/round-01/db_counts.csv": "prisma_flow.py: records identified",
        "02_search/round-01/dedupe.log": "prisma_flow.py: records after dedup (strict mode aborts without it)",
        "02_search/round-01/search_audit.json": "run_robustness_checks.py: hard precondition, raises SystemExit if absent",
    }
    missing = {p: why for p, why in needed.items() if not (root / p).exists()}
    # 「檔案存在」不等於「檔案讀得懂」。存在但壞掉的 audit 檔會讓這裡印出
    # 「generator inputs present」——又是一句把未檢查說成已通過的話。
    audit = root / "02_search/round-01/search_audit.json"
    if audit.exists():
        try:
            json.loads(audit.read_text(encoding="utf-8"))
        except Exception as exc:
            _blocker("search audit", f"search_audit.json 存在但解析失敗（{exc}）")
    return {
        "prisma_flow_md_present": (root / "07_manuscript" / "prisma_flow.md").exists(),
        "missing_generator_inputs": missing,
        "note": ("prisma_flow.py / run_robustness_checks.py cannot run here until these exist; "
                 "that is why the flow numbers in the prose were hand-written and never "
                 "cross-checked." if missing else "generator inputs present"),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(report: dict) -> str:
    out: list[str] = []
    add = out.append
    add("=" * 92)
    add("PRISMA reconciliation — " + report["project"])
    add("=" * 92)

    add("")
    add("SCREENING ROUNDS FOUND ON DISK")
    if not report["screening_versions"]:
        add("  (none)")
    for label, ver in sorted(report["screening_versions"].items()):
        counts = ver["counts"]
        k = report["screening_kappa"].get(label)
        add(f"  {label}  {ver['file']}")
        add(f"        n={ver['n_records']}  include={counts.get('include', 0)}  "
            f"maybe={counts.get('maybe', 0)}  exclude={counts.get('exclude', 0)}  "
            f"-> forwarded {ver['n_forwarded']}" + (f"   kappa={k}" if k is not None else ""))
    ft = report["fulltext_stage"]
    if ft:
        add(f"  full text  {ft['file']}")
        add(f"        assessed={ft['n_assessed']}  include={ft['counts'].get('include', 0)}  "
            f"exclude={ft['counts'].get('exclude', 0)}")
    consumed = report["consumed_version"]
    if consumed.get("per_version"):
        add("")
        add("WHICH ROUND DID THE FULL-TEXT STAGE ACTUALLY CONSUME?")
        for label, d in sorted(consumed["per_version"].items()):
            mark = "  <== consumed" if label == consumed.get("version") else ""
            add(f"  {label}: forwarded {d['forwarded']}, overlap with full-text file {d['overlap']}, "
                f"Jaccard {d['jaccard']}, exact set match {d['exact_set_match']}{mark}")
            if d["forwarded_never_assessed"]:
                ids = ", ".join(d["forwarded_never_assessed"][:10])
                more = "" if len(d["forwarded_never_assessed"]) <= 10 else " ..."
                add(f"        {len(d['forwarded_never_assessed'])} forwarded records never full-text assessed: {ids}{more}")

    add("")
    add("RECONCILIATION TABLE")
    add(f"  {'PRISMA stage':<34} {'claimed':>9} {'counted':>9} {'delta':>7}  status        source")
    add("  " + "-" * 88)
    for row in report["table"]:
        claimed = "-" if row["claimed"] is None else str(row["claimed"])
        delta = "" if row["delta"] is None else f"{row['delta']:+d}"
        add(f"  {_SLOT_LABEL[row['slot']]:<34} {claimed:>9} {row['counted']:>9} {delta:>7}  "
            f"{row['status']:<13} {row['counted_from']}")
        if row["status"] == "MISMATCH" and row.get("claim"):
            c = row["claim"]
            add(f"        claimed at {c['file']}:{c['line']}"
                + (f"  [matches screening round {'/'.join(c['attributed_versions'])}]"
                   if c.get("attributed_versions") else ""))
            add(f'        "{c["quote"][:200]}"')
            if row.get("other_counted"):
                add(f"        other counted values for this stage: {row['other_counted']}")

    add("")
    add("VERSION ATTRIBUTION OF CLAIMS")
    per_doc = report["version_mixing"]["per_document"]
    if not per_doc:
        add("  (no claim could be pinned to a specific screening round)")
    for doc, versions in sorted(per_doc.items()):
        add(f"  {doc}: {', '.join(versions)}")
    add(f"  full-text stage consumed: {report['version_mixing']['consumed_by_fulltext'] or 'unknown'}")

    findings = report["findings"]
    add("")
    add(f"FINDINGS ({len(findings)})")
    if not findings:
        # 有 blocker 時不准說「都對得上」——沒對到的東西是「沒看懂」，不是「沒問題」。
        add("  none among the stages that could be parsed — see CANNOT CHECK below."
            if report.get("blockers") else
            "  none — every claimed PRISMA number matches a counted one.")
    for i, f in enumerate(findings, 1):
        add(f"  [{i}] {f['severity']} {f['kind']}")
        for line in _wrap(f["message"], 86):
            add(f"      {line}")

    if report.get("blockers"):
        add("")
        add(f"CANNOT CHECK ({len(report['blockers'])}) — 下列環節無法解析，本次對帳不構成任何保證")
        for i, b in enumerate(report["blockers"], 1):
            add(f"  [{i}] {b['stage']}: {b['detail']}")

    gen = report["generator_tooling"]
    if gen["missing_generator_inputs"]:
        add("")
        add("WHY THE EXISTING GENERATOR NEVER RAN")
        for path, why in gen["missing_generator_inputs"].items():
            add(f"  missing {path}")
            add(f"          needed by {why}")
        add("  " + gen["note"])

    return "\n".join(out)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile a meta-analysis manuscript's PRISMA numbers against the files on disk.")
    parser.add_argument("project", nargs="?", default=".", help="MA project root (has 01_protocol/ .. 09_qa/)")
    parser.add_argument("--json", dest="json_out", default=None, help="write the full report as JSON")
    parser.add_argument("--quiet", action="store_true", help="suppress the human table; exit code only")
    args = parser.parse_args()

    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        print(f"[reconcile_prisma] cannot check: {root} is not a directory", file=sys.stderr)
        return 2
    if not (root / "03_screening").is_dir() or not (root / "04_fulltext").is_dir():
        print(f"[reconcile_prisma] cannot check: {root} has no 03_screening/ + 04_fulltext/ "
              f"(not a meta-analysis project layout)", file=sys.stderr)
        return 2

    report = reconcile(root)

    if not report["screening_versions"]:
        print("[reconcile_prisma] cannot check: no adjudicated screening decision file found under "
              "03_screening/*/decisions*.csv", file=sys.stderr)
        return 2
    if not report["claims"]:
        print("[reconcile_prisma] cannot check: no PRISMA numbers found in 07_manuscript/*.qmd or "
              "09_qa/*.md — nothing to reconcile against", file=sys.stderr)
        return 2

    if args.json_out:
        out_path = Path(args.json_out).expanduser()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=list), encoding="utf-8")
        except Exception as exc:
            print(f"[reconcile_prisma] cannot check: 寫不出 JSON 報告 {out_path}（{exc}）", file=sys.stderr)
            return 2

    if not args.quiet:
        print(render(report))

    checked = [_SLOT_LABEL[r["slot"]] for r in report["table"]]

    # Fail-closed：只要有任何一個環節看不懂，就不准輸出「對得起來」。已經抓到的 findings
    # 照樣印出來（真陽性不能因為 fail-closed 而消失），但退出碼是 2 =「檢查無法進行」。
    if report["blockers"]:
        stages = ", ".join(sorted({b["stage"] for b in report["blockers"]}))
        print(f"\n[reconcile_prisma] CANNOT CHECK — {len(report['blockers'])} 個環節無法解析"
              f"（{stages}）。已列出的 {len(report['findings'])} 項 finding 仍然成立，"
              f"但「沒問題」在本次執行中無法主張。", file=sys.stderr)
        for b in report["blockers"]:
            print(f"  - {b['stage']}: {b['detail']}", file=sys.stderr)
        return 2

    if report["findings"]:
        n1 = sum(1 for f in report["findings"] if f["severity"] == "P1")
        print(f"\n[reconcile_prisma] FAIL — {len(report['findings'])} finding(s), {n1} at P1. "
              f"Stages checked: {', '.join(checked)}.")
        return 1

    print(f"\n[reconcile_prisma] PASS — every claimed PRISMA number matches the files. "
          f"Stages checked: {', '.join(checked)}. "
          f"Stages with no counted artifact (skipped): "
          f"{', '.join(label for slot, label in _SLOT_LABEL.items() if slot not in {r['slot'] for r in report['table']}) or 'none'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

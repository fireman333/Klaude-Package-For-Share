"""Maintain ~/PageIndex/library/ + ~/PageIndex/indexes/ — list, locate, classify PDFs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

PAGEINDEX_HOME = Path.home() / "PageIndex"
LIBRARY_DIR = PAGEINDEX_HOME / "library"
INDEXES_DIR = PAGEINDEX_HOME / "indexes"
META_FILE = INDEXES_DIR / "_meta.json"

KNOWN_TOPICS = ("cardio", "exam", "nccn", "physics_chem", "misc")


def ensure_dirs() -> None:
    for sub in KNOWN_TOPICS:
        (LIBRARY_DIR / sub).mkdir(parents=True, exist_ok=True)
    INDEXES_DIR.mkdir(parents=True, exist_ok=True)


def list_indexed() -> dict[str, dict]:
    """Return doc_id -> meta entry from PageIndex workspace."""
    if not META_FILE.exists():
        return {}
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def find_doc_id(query: str) -> tuple[str, dict] | None:
    """Fuzzy-find a doc_id by partial filename / doc_name match. Returns (doc_id, entry) or None."""
    meta = list_indexed()
    if not meta:
        return None
    q = query.lower().strip()
    # Exact path match first
    for doc_id, entry in meta.items():
        if Path(entry.get("path", "")).name.lower() == q or doc_id == query:
            return doc_id, entry
    # Substring match on doc_name or filename
    candidates: list[tuple[str, dict]] = []
    for doc_id, entry in meta.items():
        haystack = " ".join(
            [
                entry.get("doc_name", ""),
                Path(entry.get("path", "")).stem,
            ]
        ).lower()
        if q in haystack:
            candidates.append((doc_id, entry))
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Prefer shortest (most specific) match
        candidates.sort(key=lambda x: len(x[1].get("doc_name", "") + Path(x[1].get("path", "")).stem))
        return candidates[0]
    return None


def classify_topic(pdf_path: Path) -> str:
    """Best-effort classification by parent dir or filename heuristic."""
    parts = [p.lower() for p in pdf_path.parts]
    for topic in KNOWN_TOPICS:
        if topic in parts:
            return topic
    name = pdf_path.stem.lower()
    if any(k in name for k in ("hf", "heart", "ttm", "esc", "cardiac", "aha")):
        return "cardio"
    if any(k in name for k in ("nccn",)):
        return "nccn"
    if any(k in name for k in ("證照", "考古", "exam", "harrison")):
        return "exam"
    if any(k in name for k in ("物理", "化學", "physics", "chem")):
        return "physics_chem"
    return "misc"


def stash_pdf(src: Path, topic: str | None = None) -> Path:
    """Copy PDF into library/<topic>/ if not already there. Returns destination path."""
    src = src.resolve()
    if str(src).startswith(str(LIBRARY_DIR)):
        return src
    topic = topic or classify_topic(src)
    dst = LIBRARY_DIR / topic / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    return dst


def remove_doc(doc_id: str) -> bool:
    """Remove indexed JSON + meta entry. Library PDF is left in place."""
    meta = list_indexed()
    if doc_id not in meta:
        return False
    json_file = INDEXES_DIR / f"{doc_id}.json"
    if json_file.exists():
        json_file.unlink()
    meta.pop(doc_id, None)
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def topic_summary() -> dict[str, list[str]]:
    """Return {topic: [pdf_filename, ...]} from library/ on disk (not from index meta)."""
    out: dict[str, list[str]] = {}
    for topic in KNOWN_TOPICS:
        topic_dir = LIBRARY_DIR / topic
        if topic_dir.exists():
            out[topic] = sorted(p.name for p in topic_dir.glob("*.pdf"))
    return out

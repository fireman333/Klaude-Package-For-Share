"""
Protect-first date shifting for Taiwan clinical text.

The pipeline:
    1. Protect pass — replace every clinical time token (POD#3, q8h, HH:MM, ...)
       with a Unicode Private Use Area placeholder so subsequent date regex
       cannot touch it.
    2. Date pass — match calendar dates (西元 and 民國), shift each by the session's
       offset (signed integer days), format back in the original style.
    3. Restore pass — swap placeholders back.

Shifting is symmetric: `apply(text, offset)` and `apply(shifted, -offset)` are
inverses for any text that only contains well-formed dates and protected tokens.

Dates recognized:
    - YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD  (year must be 19xx or 20xx)
    - 民國XXX年MM月DD日 / XXX年MM月DD日       (3-digit ROC year)
    - 民國XX年MM月DD日 / XX年MM月DD日          (2-digit ROC year 1-130)

Dates NOT shifted (by design, logged to warnings):
    - Bare MM/DD without a year anchor within 30 characters — ambiguous
    - 8-digit compact dates like 20240315 — too easy to confuse with IDs
    - ISO 8601 with time attached (time component is preserved via the protect pass)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import regex as re

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Unicode Private Use Area markers for protected tokens
_PROTECT_START = "\ue000"
_PROTECT_END = "\ue001"


# ---------- Protect pass ----------

def _load_protect_patterns() -> list[re.Pattern]:
    """Load regex patterns from clinical_time_tokens.txt."""
    patterns: list[re.Pattern] = []
    with (DATA_DIR / "clinical_time_tokens.txt").open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            patterns.append(re.compile(line))
    return patterns


def _protect(text: str, patterns: list[re.Pattern]) -> tuple[str, list[str]]:
    """Replace every clinical time token with a placeholder. Return (text, originals)."""
    originals: list[str] = []

    def sub_fn(m: re.Match) -> str:
        idx = len(originals)
        originals.append(m.group(0))
        return f"{_PROTECT_START}{idx}{_PROTECT_END}"

    # Apply each pattern. We do multiple passes so that if one pattern's token
    # contains substrings matching another pattern, the first match wins. We
    # sort patterns by match breadth — but in practice passing sequentially
    # works because the placeholder (Private Use Area) won't match any pattern.
    for pat in patterns:
        text = pat.sub(sub_fn, text)
    return text, originals


def _restore(text: str, originals: list[str]) -> str:
    """Reverse of _protect — swap placeholders back to originals."""
    def sub_fn(m: re.Match) -> str:
        return originals[int(m.group(1))]
    return re.sub(rf"{_PROTECT_START}(\d+){_PROTECT_END}", sub_fn, text)


# ---------- Date regex + shift ----------

@dataclass
class DateShift:
    start: int
    end: int
    original: str
    shifted: str


def _shift_date(y: int, m: int, d: int, offset_days: int) -> tuple[int, int, int]:
    dt = date(y, m, d) + timedelta(days=offset_days)
    return dt.year, dt.month, dt.day


def _try_parse_and_shift(
    raw: str,
    offset_days: int,
) -> str | None:
    """Given a raw date string, parse, shift, format back in the same style.

    Supports:
        "2024-03-15", "2024/03/15", "2024.03.15"
        "民國113年3月15日", "113年03月15日", "民國113-3-15"
    Returns None if unparseable.
    """
    # Western: YYYY sep M sep D
    m = re.fullmatch(r"(?P<y>(?:19|20)\d{2})(?P<s1>[-/.])(?P<m>\d{1,2})(?P<s2>[-/.])(?P<d>\d{1,2})", raw)
    if m:
        try:
            ny, nm, nd = _shift_date(int(m["y"]), int(m["m"]), int(m["d"]), offset_days)
        except ValueError:
            return None
        # Preserve zero-padding style from original
        m_width = len(m["m"])
        d_width = len(m["d"])
        return f"{ny:04d}{m['s1']}{nm:0{m_width}d}{m['s2']}{nd:0{d_width}d}"

    # ROC: 民國?XXX年MM月DD日
    m = re.fullmatch(
        r"(?P<prefix>民國\s*)?(?P<y>\d{2,3})年\s*(?P<m>\d{1,2})月\s*(?P<d>\d{1,2})日?",
        raw,
    )
    if m:
        roc_y = int(m["y"])
        # ROC year -> AD year
        ad_y = roc_y + 1911
        if ad_y < 1912 or ad_y > 2100:
            return None
        try:
            ny, nm, nd = _shift_date(ad_y, int(m["m"]), int(m["d"]), offset_days)
        except ValueError:
            return None
        new_roc = ny - 1911
        prefix = m["prefix"] or ""
        m_width = len(m["m"])
        d_width = len(m["d"])
        return f"{prefix}{new_roc}年{nm:0{m_width}d}月{nd:0{d_width}d}日"

    # ROC with hyphen/slash: 113-03-15
    m = re.fullmatch(
        r"(?P<prefix>民國\s*)(?P<y>\d{2,3})(?P<s1>[-/])(?P<m>\d{1,2})(?P<s2>[-/])(?P<d>\d{1,2})",
        raw,
    )
    if m:
        roc_y = int(m["y"])
        ad_y = roc_y + 1911
        try:
            ny, nm, nd = _shift_date(ad_y, int(m["m"]), int(m["d"]), offset_days)
        except ValueError:
            return None
        new_roc = ny - 1911
        m_width = len(m["m"])
        d_width = len(m["d"])
        return f"{m['prefix']}{new_roc}{m['s1']}{nm:0{m_width}d}{m['s2']}{nd:0{d_width}d}"

    return None


# Date regexes (all require explicit year anchor to avoid MM/DD false positives)
_DATE_PATTERNS: list[re.Pattern] = [
    # Western: 2024-03-15 / 2024/03/15 / 2024.03.15
    re.compile(r"(?<![\d])(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}(?!\d)"),
    # 民國 prefixed with hyphen/slash: 民國113-3-15 or 民國 113/3/15
    re.compile(r"民國\s*\d{2,3}[-/]\d{1,2}[-/]\d{1,2}"),
    # 民國 prefixed Chinese: 民國113年3月15日
    re.compile(r"民國\s*\d{2,3}年\s*\d{1,2}月\s*\d{1,2}日?"),
    # Bare Chinese ROC: 113年3月15日 (year 2 or 3 digits only — exclude 2024年...)
    re.compile(r"(?<!\d)(?<!20)(?<!19)\d{2,3}年\s*\d{1,2}月\s*\d{1,2}日"),
]

# Year anchor used for ambiguous-date logging
_YEAR_ANCHOR_RE = re.compile(r"(?:19|20)\d{2}|民國\s*\d{2,3}")


# ---------- Public API ----------

def apply_shift(
    text: str,
    offset_days: int,
    protect_patterns: list[re.Pattern] | None = None,
) -> tuple[str, list[DateShift], list[str]]:
    """Shift all dates in text by offset_days. Return (new_text, shifts, warnings).

    warnings is a list of human-readable messages (e.g., ambiguous MM/DD skipped).
    """
    if protect_patterns is None:
        protect_patterns = _load_protect_patterns()

    protected, originals = _protect(text, protect_patterns)
    shifts: list[DateShift] = []
    warnings: list[str] = []

    # Walk the text position by position so we can do non-overlapping replacements.
    pieces: list[str] = []
    cursor = 0
    while cursor < len(protected):
        earliest: tuple[int, int, str] | None = None
        for pat in _DATE_PATTERNS:
            m = pat.search(protected, cursor)
            if m is None:
                continue
            if earliest is None or m.start() < earliest[0]:
                earliest = (m.start(), m.end(), m.group(0))
        if earliest is None:
            pieces.append(protected[cursor:])
            break
        start, end, original = earliest
        pieces.append(protected[cursor:start])
        shifted = _try_parse_and_shift(original, offset_days)
        if shifted is None:
            # Parse failure — leave date untouched, record warning
            warnings.append(f"Unparseable date left unchanged: {original!r}")
            pieces.append(original)
        else:
            shifts.append(DateShift(start=start, end=end, original=original, shifted=shifted))
            pieces.append(shifted)
        cursor = end

    result = "".join(pieces)

    # Detect ambiguous MM/DD patterns and warn (but do not shift).
    for m in re.finditer(r"(?<!\d)\d{1,2}/\d{1,2}(?!\d)", result):
        # If a year anchor is within 30 chars, we could have caught it. If not,
        # note it for manual review.
        lo = max(0, m.start() - 30)
        hi = min(len(result), m.end() + 30)
        if not _YEAR_ANCHOR_RE.search(result[lo:hi]):
            warnings.append(
                f"Ambiguous MM/DD {m.group(0)!r} at offset {m.start()} — no year anchor within 30 chars, not shifted"
            )

    restored = _restore(result, originals)
    return restored, shifts, warnings


def reverse_shift(
    text: str,
    offset_days: int,
    protect_patterns: list[re.Pattern] | None = None,
) -> tuple[str, list[DateShift], list[str]]:
    """Undo apply_shift — equivalent to apply_shift(text, -offset_days)."""
    return apply_shift(text, -offset_days, protect_patterns)


# ---------- Quick self-test (run this module directly to sanity-check) ----------

def _self_test() -> None:
    samples = [
        # (input, offset, expected)
        ("入院日 2024-03-15", 42, "入院日 2024-04-26"),
        ("手術日 2024/03/15 23:45 至 24:30", 42, "手術日 2024/04/26 23:45 至 24:30"),
        ("POD#3, q8h 給藥", 42, "POD#3, q8h 給藥"),
        ("住院第5天開始發燒", 42, "住院第5天開始發燒"),
        ("民國113年3月15日入院", 100, "民國113年6月23日入院"),
        ("2024.03.15 vs 2024.04.26", -42, "2024.02.02 vs 2024.03.15"),
    ]
    for text, offset, expected in samples:
        out, shifts, warnings = apply_shift(text, offset)
        status = "OK" if out == expected else "FAIL"
        print(f"[{status}] offset={offset:+d} {text!r}")
        if out != expected:
            print(f"       expected {expected!r}")
            print(f"       got      {out!r}")
        for w in warnings:
            print(f"       warn: {w}")


if __name__ == "__main__":
    _self_test()

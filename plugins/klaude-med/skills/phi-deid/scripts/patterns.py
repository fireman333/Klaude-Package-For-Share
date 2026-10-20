"""
Regex detectors and lexicon-based name matching for Taiwan medical records.

Exports:
    Detection: named record (category, text, start, end, role_hint)
    normalize(text): character variant normalization (身份→身分, 臺→台 etc.)
    find_regex_phi(text): all structured PHI matches (ID, MRN, phone, email, ...)
    find_name_candidates(text): surname+title context matches
    merge_detections(detections): resolve overlaps (keep longest)

Does NOT include CKIP NER — that lives in ner_ckip.py and is merged at deid.py level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import regex as re

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Detection:
    category: str
    text: str
    start: int
    end: int
    role_hint: str | None = None  # e.g. "patient", "family", "doctor", "nurse"

    def __len__(self) -> int:
        return self.end - self.start


# ---------- Character normalization ----------

# Common Taiwan clinical variants that don't change meaning but break regex matching.
# We do NOT use opencc here because we only need to normalize a handful of
# characters; importing opencc adds ~80MB and a native dependency.
_CHAR_MAP = {
    "份": "分",   # 身份 -> 身分
    "臺": "台",   # normalize variant character
    "齢": "齡",   # 年齢 -> 年齡
}


def normalize(text: str) -> str:
    """Normalize character variants. Returns same-length string so offsets are preserved."""
    return text.translate(str.maketrans(_CHAR_MAP))


# ---------- Structured PHI regex ----------

# Notes on design:
# - Taiwan ID: [A-Z][12]\d{8} — the second char is 1 (male) or 2 (female).
#   Foreign residents used to be [A-Z][A-D]\d{8}; new format since 2020 is [A-Z][89]\d{8}.
# - Phone mobile: 09 + 8 digits, with optional hyphens/spaces.
# - Phone landline: 0[2-8] + 7-8 digits.
# - NHI card number: 12 digits. Require explicit context keyword ("健保卡號"/"IC卡")
#   because bare 12-digit runs collide with accession numbers.
# - MRN / admission no / pathology no / accession no / lab no: contextual prefix
#   ("病歷號"/"Chart No") required — bare alphanumeric tokens are too ambiguous.
# - Bed number: contextual prefix required ("床號"/"Bed"/"Rm").
# - Addresses: require a Taiwan county/city as anchor.

REGEX_DETECTORS: dict[str, re.Pattern] = {
    "NATIONAL_ID": re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?![A-Za-z0-9])"),
    "UI_NUMBER": re.compile(r"(?<![A-Za-z0-9])[A-Z](?:[89]|[A-D])\d{8}(?![A-Za-z0-9])"),
    "PHONE_MOBILE": re.compile(r"(?<!\d)09\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)"),
    "PHONE_LANDLINE": re.compile(r"(?<!\d)0[2-8][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)"),
    "EMAIL": re.compile(r"\b[\w.+\-]+@[\w\-]+\.[\w.\-]+\b"),
    "PLATE_TW": re.compile(
        r"(?<![A-Za-z0-9])(?:[A-Z]{2,3}-\d{3,4}|\d{3,4}-[A-Z]{2,3})(?![A-Za-z0-9])"
    ),
    "LINE_ID": re.compile(r"(?i)\bLINE(?:\s*ID)?[:：]\s*[A-Za-z0-9_.\-]{3,}"),
    "NHI_CARD": re.compile(
        r"(?:健保卡號|健保\s*IC\s*卡?|(?i:\bNHI\s*card\s*no\.?))[:：#\s]+(\d{12})"
    ),
    "MRN": re.compile(
        r"(?:病歷號|(?i:\bChart\s*No\.?|\bMRN\b|\bHN\b))[:：#\s]+([A-Z0-9\-]{5,14})"
    ),
    "ADMISSION_NO": re.compile(
        r"(?:住院號|(?i:\bAdmission\s*No\.?|\bAdm\s*No\.?))[:：#\s]+([A-Z0-9\-]{5,14})"
    ),
    "PATHOLOGY_NO": re.compile(
        r"(?:病理號|(?i:\bPath(?:ology)?\s*No\.?|\bSurgical\s*Path\s*No\.?))[:：#\s]+([A-Z0-9\-]{4,14})"
    ),
    "ACCESSION_NO": re.compile(
        r"(?:影像號|(?i:\bAccession\s*No\.?|\bImage\s*No\.?))[:：#\s]+([A-Z0-9\-]{5,16})"
    ),
    "LAB_NO": re.compile(
        r"(?:檢驗單號|(?i:\bLab\s*No\.?|\bSpecimen\s*No\.?))[:：#\s]+([A-Z0-9\-]{5,16})"
    ),
    "BED": re.compile(
        r"(?:床號|(?i:\bBed\b|\bRm\b|\bRoom\b))[:：#\s]+([A-Z0-9]{1,5}[-\s]?\d{1,3})"
    ),
    # Addresses: Taiwan county/city + district + road + (number/floor)
    "ADDRESS": re.compile(
        r"(?:臺北市|台北市|新北市|桃園市|臺中市|台中市|臺南市|台南市|高雄市|"
        r"基隆市|新竹市|新竹縣|苗栗縣|彰化縣|南投縣|雲林縣|嘉義市|嘉義縣|"
        r"屏東縣|宜蘭縣|花蓮縣|臺東縣|台東縣|澎湖縣|金門縣|連江縣)"
        r"[\p{Han}]{1,8}?(?:區|鄉|鎮|市)"
        r"(?:[\p{Han}\d]{1,20}?(?:路|街|大道|巷))?"
        r"(?:[\p{Han}\d]{1,10})?"
        r"(?:\d+(?:[-之]\d+)?號)?"
        r"(?:\d+樓)?"
        r"(?:之\d+)?"
    ),
}


def find_regex_phi(text: str) -> list[Detection]:
    """Run all regex detectors over text. Returns non-deduplicated list."""
    detections: list[Detection] = []
    for category, pat in REGEX_DETECTORS.items():
        for m in pat.finditer(text):
            # For contextual patterns (MRN, NHI_CARD, etc.) we redact the whole
            # match (keyword + value) to avoid leaving 病歷號: [MRN_01] which
            # still tells a reader it's an MRN field. Actually we want to keep
            # the label for readability but redact only the value. Use group(1)
            # when present.
            if m.groups():
                detections.append(
                    Detection(
                        category=category,
                        text=m.group(1),
                        start=m.start(1),
                        end=m.end(1),
                    )
                )
            else:
                detections.append(
                    Detection(
                        category=category,
                        text=m.group(0),
                        start=m.start(),
                        end=m.end(),
                    )
                )
    return detections


# ---------- Lexicon loaders ----------

def _load_token_file(path: Path) -> list[str]:
    tokens: list[str] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            tokens.append(line)
    return tokens


def load_surnames() -> set[str]:
    return set(_load_token_file(DATA_DIR / "surnames_zh.txt"))


def load_titles() -> list[tuple[str, str]]:
    """Return list of (title, role_category)."""
    result: list[tuple[str, str]] = []
    with (DATA_DIR / "titles.txt").open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) != 2:
                continue
            result.append((parts[0], parts[1]))
    # Longer titles first so "主治醫師" matches before "醫師"
    result.sort(key=lambda x: -len(x[0]))
    return result


def load_hospitals() -> list[str]:
    items = _load_token_file(DATA_DIR / "hospitals_tw.txt")
    return sorted(items, key=lambda x: -len(x))  # longer first


# ---------- Name candidate detection ----------

# Role mapping from titles.txt categories → pseudonym prefix
ROLE_TO_CATEGORY = {
    "patient": "PATIENT_NAME",
    "family": "FAMILY_NAME",
    "doctor": "DOCTOR_NAME",
    "nurse": "NURSE_NAME",
    "staff": "STAFF_NAME",
    "other": "PERSON_NAME",
}


def _is_han(ch: str) -> bool:
    return bool(re.match(r"\p{Han}", ch))


def find_name_candidates(
    text: str,
    surnames: set[str] | None = None,
    titles: list[tuple[str, str]] | None = None,
) -> list[Detection]:
    """Detect Chinese names using surname+title adjacency heuristic.

    Three patterns:
        A. {surname}{given 0-2 chars}{title}           e.g. 王小明先生, 張醫師
        B. {title}[：: \\s]{surname}{given 0-2 chars}    e.g. 主治醫師：陳大衛, R2 黃小華
        C. {relation-title}{surname}{given 0-2 chars}   e.g. 個案之母林女士 → captures 林女士 as family

    Returns Detections with role_hint set from the title's role category.
    """
    if surnames is None:
        surnames = load_surnames()
    if titles is None:
        titles = load_titles()

    detections: list[Detection] = []

    # Two-char surnames (e.g. 歐陽) should be tried before one-char
    two_char_surnames = {s for s in surnames if len(s) == 2}
    one_char_surnames = {s for s in surnames if len(s) == 1}

    # --- Pattern A: name + title ---
    # Anchor on title; look backward up to 4 chars for surname+given
    title_alt = "|".join(re.escape(t) for t, _ in titles)
    pat_a = re.compile(rf"(?P<name>\p{{Han}}{{1,4}})(?P<title>{title_alt})")
    for m in pat_a.finditer(text):
        name = m.group("name")
        title = m.group("title")
        # Name must start with a known surname
        surname = None
        if len(name) >= 2 and name[:2] in two_char_surnames:
            surname = name[:2]
        elif name[0] in one_char_surnames:
            surname = name[0]
        if surname is None:
            continue
        role = next((r for t, r in titles if t == title), "other")
        category = ROLE_TO_CATEGORY.get(role, "PERSON_NAME")
        detections.append(
            Detection(
                category=category,
                text=name,
                start=m.start("name"),
                end=m.end("name"),
                role_hint=role,
            )
        )

    # --- Pattern B: title + separator + name ---
    # e.g. 主治醫師：陳大衛 / Dr. 張小華
    #
    # Edge case: greedy \p{Han}{2,4} may eat the first char of a trailing title
    # (e.g. "病人：王小明先生" → name captures "王小明先", leaving "生"). We trim
    # the name if its tail + following text forms a known title.
    pat_b = re.compile(
        rf"(?P<title>{title_alt})(?P<sep>[:：]\s*|\s+)(?P<name>\p{{Han}}{{2,4}})"
    )
    title_strings = [t for t, _ in titles]
    for m in pat_b.finditer(text):
        name = m.group("name")
        title = m.group("title")
        name_end = m.end("name")
        # Trim trailing title chars: iteratively drop last char of name if
        # last_char + text_after[: title_len - 1] forms a known title.
        while len(name) > 2:
            matched_title = None
            for t in title_strings:
                if t and name.endswith(t[0]) and text[name_end - 1 : name_end - 1 + len(t)] == t:
                    matched_title = t
                    break
            if matched_title is None:
                break
            name = name[:-1]
            name_end -= 1

        surname = None
        if len(name) >= 2 and name[:2] in two_char_surnames:
            surname = name[:2]
        elif name[0] in one_char_surnames:
            surname = name[0]
        if surname is None:
            continue
        role = next((r for t, r in titles if t == title), "other")
        category = ROLE_TO_CATEGORY.get(role, "PERSON_NAME")
        detections.append(
            Detection(
                category=category,
                text=name,
                start=m.start("name"),
                end=name_end,
                role_hint=role,
            )
        )

    # --- Pattern C: English physician titles ---
    # Dr. Chang / Dr Wang / R2 陳某 / CR 黃某
    pat_english_dr = re.compile(
        r"(?i)\b(?:Dr\.?|Attending|Fellow|CR|Chief\s+Resident)\s+(?P<name>[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20})?)\b"
    )
    for m in pat_english_dr.finditer(text):
        detections.append(
            Detection(
                category="DOCTOR_NAME",
                text=m.group("name"),
                start=m.start("name"),
                end=m.end("name"),
                role_hint="doctor",
            )
        )

    pat_resident_zh = re.compile(
        r"\b(?:R[1-5]|CR|PGY[1-3]?|Intern|Clerk)\s+(?P<name>\p{Han}{2,4})\b"
    )
    for m in pat_resident_zh.finditer(text):
        name = m.group("name")
        if name[0] in one_char_surnames or (len(name) >= 2 and name[:2] in two_char_surnames):
            detections.append(
                Detection(
                    category="DOCTOR_NAME",
                    text=name,
                    start=m.start("name"),
                    end=m.end("name"),
                    role_hint="doctor",
                )
            )

    return detections


# ---------- Hospital / location detection ----------

def find_hospitals(text: str, hospitals: list[str] | None = None) -> list[Detection]:
    if hospitals is None:
        hospitals = load_hospitals()
    detections: list[Detection] = []
    # Use longest-first to prevent "醫院" from swallowing longer hospital names
    for h in hospitals:
        # Skip generic tokens that would match too broadly
        if h in {"醫院", "診所", "衛生所"}:
            continue
        start = 0
        while True:
            idx = text.find(h, start)
            if idx < 0:
                break
            detections.append(
                Detection(
                    category="HOSPITAL",
                    text=h,
                    start=idx,
                    end=idx + len(h),
                )
            )
            start = idx + len(h)
    return detections


# ---------- Overlap resolution ----------

def merge_detections(detections: Iterable[Detection]) -> list[Detection]:
    """Resolve overlapping detections.

    Strategy: sort by (start, -length). Walk forward; drop any detection whose
    range overlaps with a kept detection unless it strictly contains a kept one
    (in which case we swap). Net effect: keep the longest non-overlapping set.
    """
    items = sorted(detections, key=lambda d: (d.start, -(d.end - d.start)))
    kept: list[Detection] = []
    for d in items:
        if not kept:
            kept.append(d)
            continue
        last = kept[-1]
        # Non-overlapping
        if d.start >= last.end:
            kept.append(d)
            continue
        # Overlap: keep the longer one. If tie, keep higher priority category.
        if len(d) > len(last):
            kept[-1] = d
    return kept


# ---------- Combined entry point ----------

def find_all_phi(text: str) -> list[Detection]:
    """Run all rule-based detectors (regex + lexicon names + hospitals).

    Does NOT run CKIP — caller should merge CKIP results and call merge_detections.
    """
    all_dets: list[Detection] = []
    all_dets.extend(find_regex_phi(text))
    all_dets.extend(find_name_candidates(text))
    all_dets.extend(find_hospitals(text))
    return merge_detections(all_dets)

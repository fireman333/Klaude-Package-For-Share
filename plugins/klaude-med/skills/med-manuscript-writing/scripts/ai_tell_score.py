"""Deterministic LLM-style "tell" scorer for manuscript prose.

Usage: python ai_tell_score.py file1.md [file2.md ...] [--json]
Lower score = reads less like default LLM output. Not a detector of
statistical watermarks; it measures stylistic fingerprints.
"""
import json
import re
import statistics
import sys
import unicodedata

TELL_WORDS = [
    "delve", "delves", "delving", "underscore", "underscores", "underscoring",
    "pivotal", "intricate", "intricacies", "multifaceted", "nuanced", "tapestry",
    "landscape", "realm", "paramount", "crucial", "crucially", "furthermore",
    "moreover", "notably", "noteworthy", "comprehensive", "robust", "holistic",
    "leverage", "leveraging", "harness", "harnessing", "foster", "fostering",
    "shed light", "sheds light", "pave the way", "paves the way", "a testament",
    "in conclusion", "it is important to note", "it is worth noting",
    "plays a crucial role", "plays a pivotal role", "in the realm of",
    "novel", "groundbreaking", "unprecedented", "seamless", "seamlessly",
    "meticulous", "meticulously", "commendable", "invaluable", "elucidate",
    "elucidating", "navigate", "navigating", "ever-evolving", "dynamic interplay",
    "interplay", "showcase", "showcases", "bolster", "bolsters", "garner",
    "underpin", "underpins", "additionally", "overall,", "in summary",
    "valuable insights", "key insights", "critical insights",
]
INVISIBLE = {"​", "‌", "‍", "⁠", "﻿", "­", " ", "⁢", "⁣"}


def sentences(text):
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", text)
    return [p for p in parts if len(p.split()) >= 3]


def score(text):
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    n = max(len(words), 1)
    low = text.lower()
    tell_hits = {w: len(re.findall(r"\b" + re.escape(w) + r"\b", low)) for w in TELL_WORDS}
    tell_hits = {k: v for k, v in tell_hits.items() if v}
    tell_per_1k = 1000 * sum(tell_hits.values()) / n
    em_dash_per_1k = 1000 * (text.count("—") + text.count(" -- ")) / n
    sents = sentences(text)
    lens = [len(s.split()) for s in sents] or [0]
    mean_len = statistics.mean(lens)
    cv = statistics.pstdev(lens) / mean_len if mean_len else 0  # burstiness
    triplets = len(re.findall(r"\b\w+(?:\s\w+)?,\s\w+(?:\s\w+)?,\s(?:and|or)\s\w+", text))
    triplet_per_1k = 1000 * triplets / n
    not_only = len(re.findall(r"\bnot only\b.*?\bbut also\b", low))
    colon_heads = len(re.findall(r"^\s*\*\*[^*]+:\*\*", text, re.M))
    invisible = sum(1 for ch in text if ch in INVISIBLE or unicodedata.category(ch) == "Cf")
    sent_start_transition = sum(
        1 for s in sents if re.match(r"(Furthermore|Moreover|Additionally|Notably|Importantly|Overall|Crucially|In addition),", s)
    ) / max(len(sents), 1)

    # composite 0-100 (heuristic weights)
    composite = (
        min(tell_per_1k, 30) * 1.5          # up to 45
        + min(em_dash_per_1k, 10) * 1.5     # up to 15
        + max(0, 0.45 - cv) * 40            # low burstiness, up to ~18
        + min(triplet_per_1k, 10) * 1.0     # up to 10
        + min(sent_start_transition, 0.3) * 30  # up to 9
        + min(not_only, 3) * 1.0
        + (5 if invisible else 0)
    )
    return {
        "words": n,
        "sentences": len(sents),
        "composite_0_100": round(composite, 1),
        "tell_words_per_1k": round(tell_per_1k, 2),
        "tell_hits": tell_hits,
        "em_dash_per_1k": round(em_dash_per_1k, 2),
        "mean_sentence_len": round(mean_len, 1),
        "sentence_len_cv": round(cv, 3),
        "triplets_per_1k": round(triplet_per_1k, 2),
        "transition_opener_ratio": round(sent_start_transition, 3),
        "not_only_but_also": not_only,
        "bold_colon_headers": colon_heads,
        "invisible_chars": invisible,
    }


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = {p: score(open(p, encoding="utf-8").read()) for p in args}
    if "--json" in sys.argv:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        for p, r in out.items():
            print(f"{p}: composite={r['composite_0_100']} tell/1k={r['tell_words_per_1k']} "
                  f"emdash/1k={r['em_dash_per_1k']} CV={r['sentence_len_cv']} "
                  f"triplets/1k={r['triplets_per_1k']} trans_open={r['transition_opener_ratio']} "
                  f"invisible={r['invisible_chars']}")
            print("   hits:", r["tell_hits"])

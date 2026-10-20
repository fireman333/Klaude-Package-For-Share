#!/usr/bin/env python3
"""
Compare citations across three sources: OE positive, OE negative, PubMed direct.

Matches by DOI (preferred) or PMID (fallback). If neither available, falls back
to normalized title fuzzy match (>= 85% similarity).

Output: markdown comparison report with four buckets:
  - shared_all (in all 3 sources)
  - oe_both (in both OE queries but not PubMed)
  - oe_positive_only
  - oe_negative_only
  - pubmed_only    (candidate stale-retrieval blind spots)
"""
import argparse
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


def normalize_doi(doi):
    if not doi:
        return None
    doi = str(doi).strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi or None


def normalize_pmid(pmid):
    if not pmid:
        return None
    pmid = str(pmid).strip()
    return pmid if pmid.isdigit() else None


def normalize_title(title):
    if not title:
        return ""
    t = str(title).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def record_key(rec):
    """Preferred key: doi → pmid → None (then fall back to fuzzy title)."""
    doi = normalize_doi(rec.get("doi"))
    if doi:
        return ("doi", doi)
    pmid = normalize_pmid(rec.get("pmid"))
    if pmid:
        return ("pmid", pmid)
    return (None, None)


def load_oe_citations(path):
    """OE citations.json is a list of dicts with key, doi, pmid, title, journal, published."""
    try:
        data = json.load(open(path))
    except Exception as e:
        print(f"[warn] Could not load {path}: {e}", file=sys.stderr)
        return []
    if isinstance(data, dict) and "citations" in data:
        data = data["citations"]
    if not isinstance(data, list):
        return []
    out = []
    for c in data:
        if not isinstance(c, dict):
            continue
        out.append({
            "doi": c.get("doi"),
            "pmid": c.get("pmid"),
            "title": c.get("title"),
            "journal": c.get("journal"),
            "year": extract_year(c.get("published") or c.get("publicationInfo")),
            "authors": c.get("authors"),
            "source_key": c.get("key"),
        })
    return out


def load_pubmed_results(path):
    """PubMed MCP results can come in various shapes; we handle the common ones."""
    try:
        data = json.load(open(path))
    except Exception as e:
        print(f"[warn] Could not load {path}: {e}", file=sys.stderr)
        return []
    records = []
    # Shape 1: {"articles": [...]}
    if isinstance(data, dict):
        for k in ("articles", "results", "items", "records"):
            if k in data and isinstance(data[k], list):
                records = data[k]
                break
        if not records and "esearchresult" in data:
            # eutils esearch: just ids. Convert to minimal records.
            ids = data["esearchresult"].get("idlist", []) or []
            records = [{"pmid": i} for i in ids]
    elif isinstance(data, list):
        records = data
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue
        out.append({
            "doi": r.get("doi") or r.get("DOI"),
            "pmid": r.get("pmid") or r.get("PMID") or r.get("uid"),
            "title": r.get("title") or r.get("Title"),
            "journal": r.get("journal") or r.get("fulljournalname") or r.get("source"),
            "year": extract_year(r.get("pubdate") or r.get("date") or r.get("year")),
            "authors": r.get("authors") or r.get("author_list"),
            "source_key": None,
        })
    return out


def extract_year(s):
    if not s:
        return None
    m = re.search(r"(19|20)\d{2}", str(s))
    return int(m.group()) if m else None


def fuzzy_match(title_a, title_b, threshold=0.85):
    a, b = normalize_title(title_a), normalize_title(title_b)
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() >= threshold


def bucket_records(pos, neg, pm):
    """
    Build a single dedup'd set of records with membership flags in {pos, neg, pm}.
    """
    index = {}  # key → {rec, sources}

    def add(rec, source):
        k = record_key(rec)
        if k[0] is not None:
            if k in index:
                index[k]["sources"].add(source)
                # Prefer filled-in title if current is missing
                if not index[k]["rec"].get("title") and rec.get("title"):
                    index[k]["rec"]["title"] = rec["title"]
            else:
                index[k] = {"rec": dict(rec), "sources": {source}}
        else:
            # No hard key — try fuzzy match against existing
            matched = False
            for k2, entry in index.items():
                if fuzzy_match(rec.get("title"), entry["rec"].get("title")):
                    entry["sources"].add(source)
                    matched = True
                    break
            if not matched:
                # Use title as fallback key
                tkey = ("title", normalize_title(rec.get("title") or f"anon-{len(index)}"))
                index[tkey] = {"rec": dict(rec), "sources": {source}}

    for r in pos:
        add(r, "pos")
    for r in neg:
        add(r, "neg")
    for r in pm:
        add(r, "pm")

    buckets = {
        "shared_all": [],
        "oe_both": [],
        "oe_positive_only": [],
        "oe_negative_only": [],
        "pubmed_only": [],
        "pm_and_one_oe": [],  # rare but possible
    }
    for entry in index.values():
        s = entry["sources"]
        rec = entry["rec"]
        if s == {"pos", "neg", "pm"}:
            buckets["shared_all"].append(rec)
        elif s == {"pos", "neg"}:
            buckets["oe_both"].append(rec)
        elif s == {"pos"}:
            buckets["oe_positive_only"].append(rec)
        elif s == {"neg"}:
            buckets["oe_negative_only"].append(rec)
        elif s == {"pm"}:
            buckets["pubmed_only"].append(rec)
        else:
            buckets["pm_and_one_oe"].append(rec)
    return buckets


def year_histogram(recs):
    years = [r.get("year") for r in recs if r.get("year")]
    return Counter(years)


def fmt_rec(rec):
    """Short human-readable line for a record."""
    title = rec.get("title") or "(no title)"
    if len(title) > 110:
        title = title[:107] + "..."
    yr = rec.get("year") or "?"
    journal = rec.get("journal") or "?"
    ids = []
    if rec.get("doi"):
        ids.append(f"DOI:{rec['doi']}")
    if rec.get("pmid"):
        ids.append(f"PMID:{rec['pmid']}")
    id_str = " ".join(ids) if ids else "no-id"
    return f"- **{yr}** {title} _({journal})_ — {id_str}"


def render_report(buckets, pos_total, neg_total, pm_total, topic=None):
    lines = []
    lines.append("# Triangulation Comparison Report")
    if topic:
        lines.append(f"\n**Topic:** {topic}")
    lines.append("")

    total_unique = sum(len(v) for v in buckets.values())
    lines.append("## Summary")
    lines.append("")
    lines.append("| Source | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| OE positive | {pos_total} |")
    lines.append(f"| OE negative | {neg_total} |")
    lines.append(f"| PubMed direct | {pm_total} |")
    lines.append(f"| Total unique (after dedup) | {total_unique} |")
    lines.append("")

    lines.append("## Bucket distribution")
    lines.append("")
    lines.append("| Bucket | Count | Meaning |")
    lines.append("|--------|-------|---------|")
    lines.append(f"| Shared (all 3) | {len(buckets['shared_all'])} | 三路共識核心 |")
    lines.append(f"| OE both only | {len(buckets['oe_both'])} | OE retrieval 認識但 PubMed 直接搜沒命中（可能是 sub-speciality keyword 組合） |")
    lines.append(f"| OE positive only | {len(buckets['oe_positive_only'])} | 正問 retrieval 偏好 |")
    lines.append(f"| OE negative only | {len(buckets['oe_negative_only'])} | 反問 retrieval 補出來，**正問盲區** |")
    lines.append(f"| PubMed only | {len(buckets['pubmed_only'])} | OE 池完全沒 index，**retrieval stale / bias 盲區** |")
    lines.append(f"| PubMed + 1 OE | {len(buckets['pm_and_one_oe'])} | 三路部分 overlap |")
    lines.append("")

    # Stale signal
    pm_recent = [r for r in buckets["pubmed_only"] if r.get("year") and r["year"] >= 2024]
    lines.append("## Stale-retrieval signal")
    lines.append("")
    if len(pm_recent) >= 3:
        lines.append(f"⚠️ **STALE**: PubMed-only 有 {len(pm_recent)} 篇 ≥ 2024 的新 paper，OE 兩側完全沒引 → OE retrieval 池對這題的新證據有盲區。")
    elif len(pm_recent) >= 1:
        lines.append(f"🟡 NOTE: PubMed-only 有 {len(pm_recent)} 篇 ≥ 2024 新 paper，量不大但值得掃一眼。")
    else:
        lines.append("✅ PubMed-only 桶裡沒顯著新 paper，OE retrieval 對這題時間涵蓋尚可。")
    lines.append("")

    # Year histograms. Large buckets are truncated (newest-first) with a
    # "... 以下省略 N 篇" footer so report.md stays readable.
    MAX_ROWS_PER_BUCKET = 25
    for bucket_name, label in [
        ("shared_all", "Shared (all 3)"),
        ("oe_both", "OE both only"),
        ("oe_positive_only", "OE positive only"),
        ("oe_negative_only", "OE negative only"),
        ("pubmed_only", "PubMed only"),
    ]:
        recs = buckets[bucket_name]
        if not recs:
            continue
        hist = year_histogram(recs)
        hist_str = ", ".join(f"{y}: {c}" for y, c in sorted(hist.items())) if hist else "(no year data)"
        lines.append(f"### {label} — {len(recs)} paper(s)")
        lines.append(f"Year distribution: {hist_str}")
        lines.append("")
        sorted_recs = sorted(recs, key=lambda x: (-(x.get("year") or 0),))
        shown = sorted_recs[:MAX_ROWS_PER_BUCKET]
        for r in shown:
            lines.append(fmt_rec(r))
        if len(sorted_recs) > MAX_ROWS_PER_BUCKET:
            hidden = len(sorted_recs) - MAX_ROWS_PER_BUCKET
            lines.append(f"- _... 以下省略 {hidden} 篇（依年份新→舊排序，完整清單見 JSON artifact）_")
        lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--positive", required=True, help="OE positive citations.json path")
    ap.add_argument("--negative", required=True, help="OE negative citations.json path")
    ap.add_argument("--pubmed", required=True, help="PubMed results JSON path")
    ap.add_argument("--out", required=True, help="Output comparison.md path")
    ap.add_argument("--topic", default=None, help="Optional topic label for the report header")
    args = ap.parse_args()

    pos = load_oe_citations(args.positive)
    neg = load_oe_citations(args.negative)
    pm = load_pubmed_results(args.pubmed)

    if not pos and not neg and not pm:
        print("ERROR: all three inputs empty or unreadable.", file=sys.stderr)
        return 2

    buckets = bucket_records(pos, neg, pm)
    report = render_report(buckets, len(pos), len(neg), len(pm), topic=args.topic)
    Path(args.out).write_text(report)
    print(f"Wrote {args.out}")
    print(f"  shared_all={len(buckets['shared_all'])}  "
          f"oe_both={len(buckets['oe_both'])}  "
          f"pos_only={len(buckets['oe_positive_only'])}  "
          f"neg_only={len(buckets['oe_negative_only'])}  "
          f"pm_only={len(buckets['pubmed_only'])}  "
          f"pm+one_oe={len(buckets['pm_and_one_oe'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

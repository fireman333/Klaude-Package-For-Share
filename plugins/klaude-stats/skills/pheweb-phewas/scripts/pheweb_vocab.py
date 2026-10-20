#!/usr/bin/env python3
"""Dump the phenotype vocabulary of a downloaded PheWeb result set.

  python3 pheweb_vocab.py --raw ./raw                  # every trait, grouped by category
  python3 pheweb_vocab.py --raw ./raw --pcut 1e-3      # only traits that reach the cut-off
  python3 pheweb_vocab.py --raw ./raw --grep "cholesterol|diabet"

Run this BEFORE writing the mapping config. Each PheWeb instance has its own phenotype
vocabulary — UK Biobank (Neale) has no serum-biomarker GWAS at all, BioBank Japan has
LDL / HDL / TG / HbA1c / BMI as first-class traits — so the target-domain mapping cannot
be reused across instances and must be authored against the vocabulary printed here.
"""
import argparse, collections, glob, json, os, re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--pcut", type=float, default=None,
                    help="only list traits reaching this p-value in at least one SNP")
    ap.add_argument("--grep", default=None, help="regex filter on the phenotype name")
    a = ap.parse_args()

    vocab, hits = {}, collections.defaultdict(list)
    n_snp = 0
    for f in sorted(glob.glob(os.path.join(a.raw, "*.json"))):
        d = json.load(open(f))
        if "phenos" not in d:
            print(f"# {d.get('_rsid', f)}: ABSENT from this PheWeb")
            continue
        n_snp += 1
        for p in d["phenos"]:
            vocab[p["phenocode"]] = (p.get("category", ""), p["phenostring"])
            if a.pcut and p["pval"] < a.pcut:
                hits[p["phenocode"]].append((d["_rsid"], p["pval"]))

    keys = list(hits) if a.pcut else list(vocab)
    if a.grep:
        rx = re.compile(a.grep, re.I)
        keys = [k for k in keys if rx.search(vocab[k][1]) or rx.search(k)]

    bycat = collections.defaultdict(list)
    for k in keys:
        bycat[vocab[k][0]].append(k)
    for cat in sorted(bycat):
        print(f"\n### {cat or '(no category)'}")
        for k in sorted(bycat[cat], key=lambda x: vocab[x][1]):
            extra = ""
            if a.pcut:
                best = min(hits[k], key=lambda t: t[1])
                extra = f"   <- {len(hits[k])} SNP(s), best {best[0]} p={best[1]:.1e}"
            print(f"    {k:<40}| {vocab[k][1]}{extra}")

    print(f"\n# {n_snp} SNP(s) with data, {len(vocab)} distinct phenotype codes"
          + (f", {len(hits)} reaching p < {a.pcut:g}" if a.pcut else ""))


if __name__ == "__main__":
    main()

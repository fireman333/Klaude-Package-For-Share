#!/usr/bin/env python3
"""Prove that the PheWeb REST API returns exactly what the web page shows.

  python3 pheweb_verify.py --site https://pheweb.jp --raw ./raw --out verification.json

Why this exists: a reviewer will ask "did you only read the first page of the table?".
A PheWeb variant page is server-rendered — the entire result set is embedded in the page
HTML as `window.variant = {...}`, and the First / Previous / Next / Last controls only
re-paginate that object client-side (no further network request). This script downloads
the HTML for every SNP, extracts the embedded object and compares it row-by-row with the
API response, so the claim is evidenced rather than asserted.
"""
import argparse, json, os, re, time, urllib.request

UA = {"User-Agent": "Mozilla/5.0 pheweb-phewas-skill"}


def fetch_html(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read().decode("utf-8", "replace")


def embedded(html):
    m = re.search(r"window\.variant\s*=\s*(\{.*?\});\s*\n", html, re.S)
    return json.loads(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sleep", type=float, default=2.0)
    a = ap.parse_args()
    site = a.site.rstrip("/")

    report = []
    for fn in sorted(os.listdir(a.raw)):
        if not fn.endswith(".json"):
            continue
        api = json.load(open(os.path.join(a.raw, fn)))
        rsid = api.get("_rsid", fn[:-5])
        if "phenos" not in api:
            report.append({"snp": rsid, "variant": "-", "api_rows": "n/a", "web_rows": "n/a",
                           "result": "SKIPPED — variant absent from this PheWeb"})
            continue
        vid = api["_variant"]
        web = embedded(fetch_html(f"{site}/variant/{vid}"))
        time.sleep(a.sleep)
        if web is None:
            report.append({"snp": rsid, "variant": vid, "api_rows": len(api["phenos"]),
                           "web_rows": "?", "result": "FAILED — could not parse embedded data"})
            continue
        key = lambda ph: sorted((p["phenocode"], p["pval"], p.get("beta"), p.get("num_samples")) for p in ph)
        same = key(api["phenos"]) == key(web["phenos"])
        report.append({"snp": rsid, "variant": vid, "api_rows": len(api["phenos"]),
                       "web_rows": len(web["phenos"]),
                       "result": "IDENTICAL" if same else "*** MISMATCH ***"})

    w = "{:<14}{:<22}{:>10}{:>10}   {}"
    print(w.format("SNP", "Variant", "API rows", "Web rows", "Comparison"))
    for r in report:
        print(w.format(r["snp"], str(r["variant"]), str(r["api_rows"]), str(r["web_rows"]), r["result"]))
    json.dump(report, open(a.out, "w"), indent=1)
    print("\nwrote", a.out)


if __name__ == "__main__":
    main()

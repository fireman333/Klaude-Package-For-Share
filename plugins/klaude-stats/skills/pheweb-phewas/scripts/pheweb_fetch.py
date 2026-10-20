#!/usr/bin/env python3
"""Download the complete PheWAS result for a list of rsIDs from any PheWeb instance.

  python3 pheweb_fetch.py --site https://pheweb.jp --snps rs671,rs11207982 --out ./raw
  python3 pheweb_fetch.py --site https://pheweb.org/UKB-Neale --snps snps.txt --out ./raw

Notes that matter:
  * PheWeb's /api/autocomplete does PREFIX matching — querying rs11207982 also returns
    rs112079820. This script only accepts the exact rsID, never merely the first hit.
  * A variant the instance does not carry returns `null` from /api/variant. When
    autocomplete finds nothing, the script falls back to the Ensembl GRCh37 coordinate
    and probes every allele pair before declaring the variant absent.
  * One request every --sleep seconds (default 2). Do not remove this.
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

UA = {"User-Agent": "Mozilla/5.0 pheweb-phewas-skill"}
ALLELES = ["C-T", "T-C", "A-G", "G-A", "C-A", "A-C", "C-G", "G-C", "T-A", "A-T", "T-G", "G-T"]


def get(url, as_json=True):
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180)
    body = raw.read().decode("utf-8", "replace")
    return json.loads(body) if as_json else body


def grch37(rsid):
    """Ensembl GRCh37 coordinate for an rsID, or None."""
    try:
        d = get(f"https://grch37.rest.ensembl.org/variation/human/{rsid}?content-type=application/json")
        for m in d.get("mappings", []):
            if m.get("assembly_name") == "GRCh37":
                return f"{m['seq_region_name']}:{m['start']}"
    except Exception:
        pass
    return None


def resolve(site, rsid, sleep):
    """rsID -> PheWeb variant id, or None."""
    try:
        for hit in get(f"{site}/api/autocomplete?query={rsid}"):
            if hit.get("display", "").startswith(f"{rsid} ("):
                return hit["value"]
    except Exception as e:
        print(f"  autocomplete failed: {e}", file=sys.stderr)
    pos = grch37(rsid)
    if not pos:
        return None
    print(f"  autocomplete miss — probing GRCh37 {pos}")
    for a in ALLELES:
        try:
            if get(f"{site}/api/variant/{pos}-{a}"):
                return f"{pos}-{a}"
        except urllib.error.HTTPError:
            pass
        time.sleep(sleep)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="PheWeb base URL, e.g. https://pheweb.jp")
    ap.add_argument("--snps", required=True, help="comma-separated rsIDs, or a file with one per line")
    ap.add_argument("--out", required=True, help="output directory for the raw JSON files")
    ap.add_argument("--sleep", type=float, default=2.0)
    a = ap.parse_args()

    site = a.site.rstrip("/")
    snps = ([l.strip() for l in open(a.snps) if l.strip() and not l.startswith("#")]
            if os.path.exists(a.snps) else [x.strip() for x in a.snps.split(",") if x.strip()])
    os.makedirs(a.out, exist_ok=True)

    for s in snps:
        f = os.path.join(a.out, f"{s}.json")
        if os.path.exists(f):
            print(s, "cached")
            continue
        print(s, "...")
        try:
            vid = resolve(site, s, a.sleep)
            if not vid:
                print(f"  {s} NOT FOUND in {site}")
                json.dump({"error": "not found", "_rsid": s, "_site": site}, open(f, "w"))
                continue
            d = get(f"{site}/api/variant/{vid}")
            if not d:
                print(f"  {s} {vid} returned null")
                json.dump({"error": "null response", "_rsid": s, "_variant": vid, "_site": site}, open(f, "w"))
                continue
            d["_rsid"], d["_variant"], d["_site"] = s, vid, site
            json.dump(d, open(f, "w"))
            print(f"  {s}  {vid}  phenos={len(d.get('phenos', []))}  gene={d.get('nearest_genes')}")
        except Exception as e:
            print(f"  {s} ERROR {e}", file=sys.stderr)
        time.sleep(a.sleep)


if __name__ == "__main__":
    main()

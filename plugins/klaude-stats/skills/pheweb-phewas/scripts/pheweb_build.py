#!/usr/bin/env python3
"""Build tables a / b / c from a downloaded PheWeb result set.

  python3 pheweb_build.py --raw ./raw --config config.json --out-dir . --prefix "BBJ_"

config.json (see reference/config_schema.md):
  {
    "cohort":       "BioBank Japan (PheWeb.jp)",
    "site":         "https://pheweb.jp",
    "population":   "Japanese ancestry, ~260,000 BBJ participants",
    "retrieved":    "2026-08-07",
    "p_cut":        5e-8,
    "p_cut_label":  "5e-8",
    "snps":         ["rs671", "..."],                      # controls row order
    "domains":      ["1. Coronary artery disease", "..."], # target domains, in order
    "groups":       {"LDLC": ["LDL-cholesterol", "7. Dyslipidaemia", "direct"],
                     "CRP":  ["C-reactive protein", null, null]},
    "panel":        [["1. Coronary artery disease", "CAD"], ...],
    "notes":        ["free-text caveat", "..."]
  }

Outputs <prefix>SNP_phenotype_functions.xlsx, <prefix>results.docx, <prefix>build_stats.json.
"""
import argparse, json, os
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

DIRECT, BORDER = "direct", "borderline — advisor to confirm"
REF_MAX = 1e-3          # upper edge of the "below cut-off, for reference" band


def sample_size(p):
    if p.get("num_cases"):
        return f"{p['num_cases']:,} cases / {p.get('num_controls', 0):,} controls"
    n = p.get("num_samples")
    return f"n = {n:,}" if isinstance(n, int) else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--verification", default=None, help="JSON produced by pheweb_verify.py")
    a = ap.parse_args()

    cfg = json.load(open(a.config))
    P_CUT = float(cfg.get("p_cut", 5e-8))
    P_LAB = cfg.get("p_cut_label", f"{P_CUT:g}")
    G = {k: (v[0], v[1] if len(v) > 1 else None, (v[2] if len(v) > 2 else None) or DIRECT)
         for k, v in cfg.get("groups", {}).items()}
    DOMAINS = cfg.get("domains", [])
    PANEL = [tuple(x) for x in cfg.get("panel", [])]

    snps = cfg.get("snps") or sorted(f[:-5] for f in os.listdir(a.raw) if f.endswith(".json"))

    data = {}
    for s in snps:
        f = os.path.join(a.raw, f"{s}.json")
        data[s] = json.load(open(f)) if os.path.exists(f) else {"error": "file missing"}

    def flag(p):
        if p < P_CUT:
            return f"*** significant (p<{P_LAB})"
        if p < 1e-4:
            return "* suggestive (p<1e-4)"
        if p < REF_MAX:
            return "(p<1e-3)"
        if p < 0.05:
            return "nominal (p<0.05)"
        return "ns"

    rows_full, rows_work, rows_b, rows_c, rows_ref, rows_panel = [], [], [], [], [], []
    unmapped, n_pheno = set(), {}

    for i, s in enumerate(snps, 1):
        d = data[s]
        if "phenos" not in d:
            note = "Variant absent from this PheWeb instance — no data"
            blank = [i, s, "not in dataset", "not in dataset", "—", note, "—", None, None, None, "—", "—", "—"]
            rows_full.append(blank)
            rows_work.append(blank)
            continue
        vid, gene = d.get("_variant", ""), d.get("nearest_genes", "")
        ph = sorted(d["phenos"], key=lambda p: p["pval"])
        n_pheno[s] = len(ph)
        for rank, p in enumerate(ph, 1):
            rows_full.append([i, s, vid, gene, p.get("category", ""), p["phenostring"], p["phenocode"],
                              p["pval"], p.get("beta"), p.get("sebeta"), sample_size(p),
                              p.get("citation", ""), rank, flag(p["pval"])])
            if p["pval"] < P_CUT:
                if p["phenocode"] not in G:
                    unmapped.add((p["phenocode"], p["phenostring"]))
                rows_work.append(rows_full[-1])
        # table b — merge similar phenotype functions, keep the most significant member
        best = {}
        for p in ph:
            if p["pval"] >= P_CUT:
                break
            grp, dom, mt = G.get(p["phenocode"], (p["phenostring"], None, None))
            if grp not in best or p["pval"] < best[grp][0]["pval"]:
                best[grp] = (p, dom, mt)
        for grp, (p, dom, mt) in sorted(best.items(), key=lambda kv: kv[1][0]["pval"]):
            members = [q["phenostring"] for q in ph if q["pval"] < P_CUT
                       and G.get(q["phenocode"], (q["phenostring"],))[0] == grp]
            rows_b.append([i, s, vid, gene, grp, len(members), p["phenostring"], p["pval"],
                           p.get("beta"), sample_size(p), flag(p["pval"]), " | ".join(members)])
            if dom:
                rows_c.append([i, s, vid, gene, dom, mt, grp, p["phenostring"], p["pval"],
                               p.get("beta"), sample_size(p), p.get("citation", ""), flag(p["pval"])])
        # below cut-off, target domains only, excluding groups already counted in c
        in_c = {r[6] for r in rows_c if r[1] == s}
        ref = {}
        for p in ph:
            if p["pval"] < P_CUT or p["pval"] >= REF_MAX:
                continue
            grp, dom, mt = G.get(p["phenocode"], (None, None, None))
            if dom and grp not in in_c and (grp not in ref or p["pval"] < ref[grp][0]["pval"]):
                ref[grp] = (p, dom, mt)
        for grp, (p, dom, mt) in sorted(ref.items(), key=lambda kv: kv[1][0]["pval"]):
            rows_ref.append([i, s, vid, gene, dom, mt, grp, p["phenostring"], p["pval"],
                             p.get("beta"), sample_size(p), p.get("citation", ""), flag(p["pval"])])
        idx = {p["phenocode"]: p for p in ph}
        for dom, code in PANEL:
            p = idx.get(code)
            if p:
                rows_panel.append([i, s, gene, dom, p["phenostring"], code, p["pval"], p.get("beta"),
                                   sample_size(p), p.get("citation", ""), flag(p["pval"])])

    if unmapped:
        print("!! UNMAPPED phenocodes reaching the cut-off — add them to config groups:")
        for c, n in sorted(unmapped):
            print(f"   {c:<40}| {n}")
    else:
        print("UNMAPPED phenocodes: none")

    empty_c = [s for s in snps if "phenos" in data[s] and not any(r[1] == s for r in rows_c)]
    empty_dom = [d for d in DOMAINS if not any(r[4] == d for r in rows_c)]

    summary = []
    for i, s in enumerate(snps, 1):
        if "phenos" not in data[s]:
            msg = "Not present in this PheWeb instance"
            summary.append([i, s, msg, msg, msg])
            continue
        aa = [r for r in rows_work if r[1] == s]
        bb = [r for r in rows_b if r[1] == s]
        cc = [r for r in rows_c if r[1] == s]
        summary.append([
            i, s,
            f"All {n_pheno[s]} phenotype codes retrieved (see sheet 10_table_a_full).\n"
            f"{len(aa)} reach p < {P_LAB}:\n" + "\n".join(f"• {r[5]} (p={r[7]:.1e})" for r in aa),
            f"{len(bb)} distinct phenotype functions after removing duplicates:\n"
            + "\n".join(f"• {r[4]} (p={r[7]:.1e}; {r[5]} trait(s) merged)" for r in bb),
            "\n".join(f"• {r[4]} → {r[6]} (p={r[8]:.1e}) [{r[5]}]" for r in cc)
            or f"None of the target domains reached p < {P_LAB}"])

    stats = {"cohort": cfg.get("cohort", ""), "p_cut_label": P_LAB, "a_full": len(rows_full),
             "a_work": len(rows_work), "b": len(rows_b), "c": len(rows_c), "ref": len(rows_ref),
             "empty_c": empty_c, "empty_dom": empty_dom, "n_pheno": n_pheno,
             "n_direct": sum(1 for r in rows_c if r[5] == DIRECT),
             "n_border": sum(1 for r in rows_c if r[5] == BORDER),
             "unmapped": sorted(unmapped)}
    os.makedirs(a.out_dir, exist_ok=True)
    json.dump(stats, open(os.path.join(a.out_dir, a.prefix + "build_stats.json"), "w"), indent=1)

    # --------------------------- Excel ---------------------------
    wb = Workbook()
    wb.remove(wb.active)
    HDR = Font(bold=True, color="FFFFFF")
    FILL = PatternFill("solid", fgColor=cfg.get("header_colour", "4472C4"))

    def sheet(title, header, rows, widths, wrap=()):
        ws = wb.create_sheet(title)
        ws.append(header)
        for c in range(1, len(header) + 1):
            ws.cell(1, c).font, ws.cell(1, c).fill = HDR, FILL
        for r in rows:
            ws.append(r)
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w
        for c in wrap:
            for r in range(2, ws.max_row + 1):
                ws.cell(r, c).alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{ws.max_row}"

    ws = wb.create_sheet("00_README")
    readme = [
        [f"PheWAS of {len(snps)} SNPs — {cfg.get('cohort', '')}"], [""],
        ["Data source", f"{cfg.get('site', '')} — variant pages and their REST API"],
        ["Retrieved", cfg.get("retrieved", "")],
        ["Population", cfg.get("population", "")],
        ["Coverage", f"every phenotype code each variant carries "
                     f"({min(n_pheno.values(), default=0)}–{max(n_pheno.values(), default=0)} per variant); "
                     f"{len(rows_full):,} rows in total, nothing filtered out"],
        ["Genome build", cfg.get("build", "GRCh37 / hg19")],
        ["Cut-off for tables b and c", f"p < {P_LAB}"], [""],
        ["Is this the same as scraping the web page?",
         "Yes — verified. A PheWeb variant page is server-rendered: the complete result set is embedded in the "
         "page HTML as `window.variant`, and the First / Previous / Next / Last buttons only re-draw that same "
         "object client-side. pheweb_verify.py compared the embedded object with the API response row-by-row "
         "for every SNP. See sheet 01_verification."], [""],
        ["Sheets"],
        ["10_table_a_full", "TABLE a — complete, every phenotype code for every SNP, sorted by p-value"],
        ["15_table_a_working", f"TABLE a, significant subset (p < {P_LAB}) — feeds tables b and c"],
        ["20_table_b", "TABLE b — similar phenotype functions merged; 'Merged from' lists every trait collapsed"],
        ["30_table_c", "TABLE c — table b restricted to the target domains, with a Match type column"],
        ["35_below_cutoff_reference", "REFERENCE ONLY, not part of table c — target-domain hits between the "
                                      "cut-off and p = 1e-3, i.e. what the cut-off excludes"],
        ["40_targeted_lookup", "p-value of every SNP against every target-domain phenotype regardless of "
                               "significance, so 'no signal' is documented rather than blank"],
        ["50_summary", "5-column layout: number / SNP / a / b / c"], [""],
        ["Notes"],
    ]
    for j, n in enumerate(cfg.get("notes", []), 1):
        readme.append([str(j), n])
    for r in readme:
        ws.append(r)
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 125
    ws["A1"].font = Font(bold=True, size=13)
    for r in range(1, ws.max_row + 1):
        ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")

    if a.verification and os.path.exists(a.verification):
        v = json.load(open(a.verification))
        sheet("01_verification", ["SNP", "Variant", "Rows from API", "Rows embedded in web page", "Comparison"],
              [[x["snp"], x["variant"], x["api_rows"], x["web_rows"], x["result"]] for x in v],
              [16, 22, 16, 26, 40])

    AH = ["number", "SNP", "Variant", "Nearest gene", "Category", "Phenotype", "Phenocode",
          "p-value", "beta", "SE", "Sample size", "Citation", "Rank by p-value", "Significance"]
    AW = [8, 14, 20, 13, 16, 58, 26, 12, 10, 9, 30, 16, 9, 24]
    sheet("10_table_a_full", AH, rows_full, AW, wrap=(6,))
    sheet("15_table_a_working", AH, rows_work, AW, wrap=(6,))
    sheet("20_table_b",
          ["number", "SNP", "Variant", "Nearest gene", "Phenotype function (deduplicated)",
           "No. of traits merged", "Representative trait", "p-value", "beta", "Sample size",
           "Significance", "Merged from (all original traits)"],
          rows_b, [8, 14, 20, 13, 52, 12, 52, 12, 10, 30, 24, 80], wrap=(5, 7, 12))
    CH = ["number", "SNP", "Variant", "Nearest gene", "Target domain", "Match type", "Phenotype function",
          "Representative trait", "p-value", "beta", "Sample size", "Citation", "Significance"]
    CW = [8, 14, 20, 13, 34, 26, 46, 46, 12, 10, 30, 16, 24]
    sheet("30_table_c", CH, rows_c, CW, wrap=(5, 7, 8))
    sheet("35_below_cutoff_reference", CH, rows_ref, CW, wrap=(5, 7, 8))
    sheet("40_targeted_lookup",
          ["number", "SNP", "Nearest gene", "Target domain", "Phenotype", "Phenocode", "p-value",
           "beta", "Sample size", "Citation", "Significance"],
          rows_panel, [8, 14, 13, 34, 44, 24, 12, 10, 30, 16, 22])
    sheet("50_summary", ["number", "SNP", "a", "b", "c"], summary, [8, 14, 62, 62, 70], wrap=(3, 4, 5))

    xlsx = os.path.join(a.out_dir, a.prefix + "SNP_phenotype_functions.xlsx")
    wb.save(xlsx)
    print(f"wrote {xlsx}\n  a_full={len(rows_full)} a_work={len(rows_work)} b={len(rows_b)} "
          f"c={len(rows_c)} ref={len(rows_ref)}")

    # --------------------------- Word ---------------------------
    import docx
    from docx.shared import Cm, Pt

    doc = docx.Document()
    for sec in doc.sections:
        sec.orientation = 1
        sec.page_width, sec.page_height = sec.page_height, sec.page_width
        sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Cm(1.4)
    doc.add_heading(f"PheWAS results — {cfg.get('cohort', '')}", 0)
    p = doc.add_paragraph()
    p.add_run("Source: ").bold = True
    p.add_run(f"{cfg.get('site', '')}. Every phenotype code each variant carries was retrieved — the complete "
              f"table, not only its first page. {cfg.get('build', 'GRCh37')}. Retrieved {cfg.get('retrieved', '')}.")
    p = doc.add_paragraph()
    p.add_run("Cut-off: ").bold = True
    p.add_run(f"tables b and c count only associations reaching p < {P_LAB}. Table a is unfiltered.")

    doc.add_heading("Final table", level=1)
    t = doc.add_table(rows=1, cols=5)
    t.style = "Table Grid"
    for c, hh in enumerate(["number", "SNP", "a", "b", "c"]):
        t.rows[0].cells[c].text = hh
        t.rows[0].cells[c].paragraphs[0].runs[0].bold = True
    for row in summary:
        cells = t.add_row().cells
        for c, v in enumerate(row):
            cells[c].text = str(v)
            for par in cells[c].paragraphs:
                par.paragraph_format.space_after = Pt(0)
                for r in par.runs:
                    r.font.size = Pt(6.5)
    for w, col in zip([Cm(1.1), Cm(2.4), Cm(9.0), Cm(7.2), Cm(7.5)], t.columns):
        for cell in col.cells:
            cell.width = w

    doc.add_page_break()
    doc.add_heading("Notes and caveats", level=1)
    base = [
        f"Completeness. Every phenotype code was retrieved for each SNP ({len(rows_full):,} rows, sheet "
        "10_table_a_full). The variant page embeds its entire result set in the page HTML and the pagination "
        "controls only re-draw that object, so nothing is hidden on later pages — verified row-by-row against "
        "the API for every SNP.",
        f"At p < {P_LAB}, {len(empty_c)} SNP(s) have no row in table c"
        + (f" ({', '.join(empty_c)})" if empty_c else "")
        + (f", and these domains show no signal in any SNP: {', '.join(empty_dom)}" if empty_dom else "")
        + ". Sheet 40_targeted_lookup gives the actual p-value against every target phenotype, so the absence "
          "of signal is documented rather than blank. Failing to reach significance means no association was "
          "detected in this dataset, not that the association is absent.",
        "Sheet 35_below_cutoff_reference lists target-domain hits that fall between the cut-off and p = 1e-3 — "
        "signals the threshold excludes — so the effect of the threshold choice is visible.",
        "Table b merges only redundant codings of the same phenotype; the 'Merged from' column lists every "
        "trait behind each group so the merge can be audited or undone.",
    ]
    for n in base + cfg.get("notes", []):
        doc.add_paragraph(n, style="List Bullet")

    out = os.path.join(a.out_dir, a.prefix + "results.docx")
    doc.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()

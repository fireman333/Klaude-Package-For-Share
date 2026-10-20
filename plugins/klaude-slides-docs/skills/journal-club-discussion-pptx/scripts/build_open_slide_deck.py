#!/usr/bin/env python3
"""
journal-club-discussion-pptx → open-slide React deck builder.

Thin orchestrator over `open_slide_builder` (shared package bundled in `../notebooklm-pptx/lib/`).
Provides per-skill renderers for jc-pptx's paper-route slide types
(paper_meta / pico / methods / results / literature_evidence / references);
inherits cover / outline / section_divider / background / case_* /
discussion_question / takeaway / blank_teacher from COMMON_RENDERERS.

Usage:
    python3 build_open_slide_deck.py <data.py> <output_parent_dir>

Output: <output_parent>/<slug>/ React/Vite scaffold with slides/journal-club/
        index.tsx populated from DATA. Auto-runs `pnpm build` to verify TS.

Other pptx skills wanting open-slide output: import from open_slide_builder
the same way + provide their own per-skill render_<type> functions.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Put the sibling skill notebooklm-pptx/lib on sys.path so `import open_slide_builder` works
_SKILL_DIR = Path(__file__).resolve().parent.parent
_COMMON_DIR = _SKILL_DIR.parent / "notebooklm-pptx" / "lib"
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from open_slide_builder import (
    # orchestrator
    build,
    load_data,
    # JSX utilities (used by per-skill renderers below)
    _page_chrome,
    _bullet_jsx,
    js_string,
    jsx_text,
)


# ─── jc-pptx specific slide renderers ─────────────────────────────────────────


def render_paper_meta(component_name: str, spec: dict, theme: dict) -> str:
    rows = [
        ("Journal", f'{spec.get("journal","")} ({spec.get("year","")})'),
        ("Authors", spec.get("authors_short", "")),
        ("DOI", spec.get("doi", "")),
        ("PMID", spec.get("pmid", "")),
        ("Design", spec.get("design", "")),
        ("Funding", spec.get("funding", "")),
        ("Main finding", spec.get("main_finding", "")),
    ]
    kv_block = "\n".join(
        f"          <KV k={{{js_string(k)}}} v={{{js_string(v)}}} />" for k, v in rows if v
    )
    body = f"""        <Card style={{{{ flex: 1 }}}}>\n{kv_block}\n        </Card>"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='Paper', header_title=spec.get('title','Paper at a Glance'))}\n);\n"


def render_pico(component_name: str, spec: dict, theme: dict) -> str:
    cells = [
        ("Population", spec.get("population", "")),
        ("Intervention", spec.get("intervention", "")),
        ("Comparator", spec.get("comparator", "")),
        ("Outcome", spec.get("outcome", "")),
    ]
    cells_jsx = ""
    for label, text in cells:
        cells_jsx += (
            f"            <Card>\n"
            f"              <div style={{{{ fontFamily: fontMono, fontSize: 22, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 12 }}}}>{jsx_text(label)}</div>\n"
            f"              <div style={{{{ fontSize: 26, lineHeight: 1.5, color: 'var(--osd-text)' }}}}>{jsx_text(text)}</div>\n"
            f"            </Card>\n"
        )
    secondary = spec.get("secondary_outcomes", []) or []
    secondary_block = ""
    if secondary:
        items_array = "[" + ", ".join(js_string(s) for s in secondary) + "]"
        secondary_block = (
            f'\n          <div style={{{{ marginTop: 24, fontSize: 24, color: palette.textSoft }}}}>\n'
            f'            <strong>Secondary outcomes:</strong> {{ {items_array}.join(" · ") }}\n'
            f"          </div>"
        )
    body = (
        f'        <div style={{{{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, flex: 1 }}}}>\n'
        + cells_jsx
        + "          </div>"
        + secondary_block
    )
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='PICO', header_title=spec.get('title','PICO'))}\n);\n"


def render_methods(component_name: str, spec: dict, theme: dict) -> str:
    incl = spec.get("key_inclusion", []) or []
    excl = spec.get("key_exclusion", []) or []
    rows = [
        ("Design", spec.get("design", "")),
        ("N", str(spec.get("n_total", "")) if spec.get("n_total") else ""),
        ("Primary endpoint", spec.get("primary_endpoint", "")),
        ("Stats", spec.get("stats_method", "")),
        ("Follow-up", spec.get("follow_up", "")),
    ]
    kv_block = "\n".join(
        f"            <KV k={{{js_string(k)}}} v={{{js_string(v)}}} />"
        for k, v in rows if v
    )
    incl_jsx = _bullet_jsx(incl, indent="              ")
    excl_jsx = _bullet_jsx(excl, indent="              ")
    body = f"""        <div style={{{{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 24, flex: 1 }}}}>
          <Card>
{kv_block}
          </Card>
          <div style={{{{ display: "flex", flexDirection: "column", gap: 16 }}}}>
            <Card>
              <div style={{{{ fontFamily: fontMono, fontSize: 18, letterSpacing: "0.12em", textTransform: "uppercase", color: 'var(--osd-accent)', marginBottom: 10 }}}}>Inclusion</div>
{incl_jsx}
            </Card>
            <Card>
              <div style={{{{ fontFamily: fontMono, fontSize: 18, letterSpacing: "0.12em", textTransform: "uppercase", color: 'var(--osd-accent)', marginBottom: 10 }}}}>Exclusion</div>
{excl_jsx}
            </Card>
          </div>
        </div>"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='Methods', header_title='Methods')}\n);\n"


def render_results(component_name: str, spec: dict, theme: dict) -> str:
    title = spec.get("title", "Results")
    kn = spec.get("key_numbers", []) or []
    fig = spec.get("figure_caption", "")
    table_rows = ""
    for r in kn:
        table_rows += (
            "            <tr>\n"
            f'              <td style={{{{ padding: "12px 16px", fontSize: 24, color: "var(--osd-text)", fontWeight: 500 }}}}>{jsx_text(r.get("metric",""))}</td>\n'
            f'              <td style={{{{ padding: "12px 16px", fontSize: 28, color: "var(--osd-accent)", fontWeight: 700, fontFamily: fontMono }}}}>{jsx_text(r.get("value",""))}</td>\n'
            f'              <td style={{{{ padding: "12px 16px", fontSize: 22, color: palette.textSoft, fontFamily: fontMono }}}}>{jsx_text(r.get("ci",""))}</td>\n'
            f'              <td style={{{{ padding: "12px 16px", fontSize: 22, color: palette.textSoft, fontFamily: fontMono }}}}>{jsx_text(r.get("p",""))}</td>\n'
            "            </tr>\n"
        )
    figure_slot = ""
    caption_block = ""
    if fig:
        # ImagePlaceholder reserves a slot for user to drag-drop the real KM /
        # forest plot figure. User uploads via inspector + clicks Replace; JSX
        # auto-rewrites to <img src=...>. Hint should describe content, not role.
        fig_hint = jsx_text(fig)[:80]
        figure_slot = (
            f'\n        <div style={{{{ marginTop: 20 }}}}>\n'
            f'          <ImagePlaceholder hint={js_string(fig_hint)} width={{1100}} height={{420}} />\n'
            f"        </div>"
        )
        caption_block = (
            f'\n        <p style={{{{ marginTop: 16, fontSize: 22, fontStyle: "italic", color: palette.textSoft, lineHeight: 1.5, textAlign: "center" }}}}>\n'
            f"          {jsx_text(fig)}\n"
            "        </p>"
        )
    body = f"""        <Card>
          <table style={{{{ width: "100%", borderCollapse: "collapse" }}}}>
            <thead>
              <tr style={{{{ borderBottom: `2px solid ${{palette.rule}}` }}}}>
                <th style={{{{ padding: "10px 16px", textAlign: "left", fontSize: 18, letterSpacing: "0.1em", textTransform: "uppercase", color: palette.textSoft }}}}>Metric</th>
                <th style={{{{ padding: "10px 16px", textAlign: "left", fontSize: 18, letterSpacing: "0.1em", textTransform: "uppercase", color: palette.textSoft }}}}>Value</th>
                <th style={{{{ padding: "10px 16px", textAlign: "left", fontSize: 18, letterSpacing: "0.1em", textTransform: "uppercase", color: palette.textSoft }}}}>95% CI</th>
                <th style={{{{ padding: "10px 16px", textAlign: "left", fontSize: 18, letterSpacing: "0.1em", textTransform: "uppercase", color: palette.textSoft }}}}>P</th>
              </tr>
            </thead>
            <tbody>
{table_rows}            </tbody>
          </table>
        </Card>{figure_slot}{caption_block}"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='Results', header_title=title)}\n);\n"


def render_literature_evidence(component_name: str, spec: dict, theme: dict) -> str:
    q_num = spec.get("q_num", "")
    summary = jsx_text(spec.get("evidence_summary_en", ""))
    citations = spec.get("citations", []) or []
    rows = ""
    for c in citations:
        rows += (
            f"            <tr style={{{{ borderTop: `1px solid ${{palette.rule}}` }}}}>\n"
            f'              <td style={{{{ padding: "10px 14px", fontSize: 22, color: "var(--osd-text)", fontWeight: 500 }}}}>{jsx_text(c.get("author_year",""))}</td>\n'
            f'              <td style={{{{ padding: "10px 14px", fontSize: 22, color: palette.textSoft }}}}>{jsx_text(c.get("study_type",""))}</td>\n'
            f'              <td style={{{{ padding: "10px 14px", fontSize: 22, color: palette.textSoft }}}}>{jsx_text(c.get("country",""))}</td>\n'
            f'              <td style={{{{ padding: "10px 14px", fontSize: 22, color: palette.textSoft }}}}>n={jsx_text(c.get("n",""))}</td>\n'
            f'              <td style={{{{ padding: "10px 14px", fontSize: 22, color: "var(--osd-text)" }}}}>{jsx_text(c.get("take_home",""))}</td>\n'
            "            </tr>\n"
        )
    body = f"""        <p style={{{{ fontSize: 28, lineHeight: 1.55, color: 'var(--osd-text)', marginBottom: 24 }}}}>
          {summary}
        </p>
        <Card>
          <table style={{{{ width: "100%", borderCollapse: "collapse" }}}}>
            <thead>
              <tr>
                <th style={{{{ padding: "8px 14px", textAlign: "left", fontSize: 16, letterSpacing: "0.1em", textTransform: "uppercase", color: palette.textSoft }}}}>Source</th>
                <th style={{{{ padding: "8px 14px", textAlign: "left", fontSize: 16, letterSpacing: "0.1em", textTransform: "uppercase", color: palette.textSoft }}}}>Type</th>
                <th style={{{{ padding: "8px 14px", textAlign: "left", fontSize: 16, letterSpacing: "0.1em", textTransform: "uppercase", color: palette.textSoft }}}}>Country</th>
                <th style={{{{ padding: "8px 14px", textAlign: "left", fontSize: 16, letterSpacing: "0.1em", textTransform: "uppercase", color: palette.textSoft }}}}>N</th>
                <th style={{{{ padding: "8px 14px", textAlign: "left", fontSize: 16, letterSpacing: "0.1em", textTransform: "uppercase", color: palette.textSoft }}}}>Take-home</th>
              </tr>
            </thead>
            <tbody>
{rows}            </tbody>
          </table>
        </Card>"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow=f'Evidence · Q{q_num}', header_title='Literature Synthesis')}\n);\n"


def render_references(component_name: str, spec: dict, theme: dict) -> str:
    citations = spec.get("citations", []) or []
    n = len(citations)
    font_size = 18 if n >= 10 else (20 if n >= 7 else 22)
    rows = ""
    for i, c in enumerate(citations):
        authors = jsx_text(c.get("full_author_list", ""))
        ttl = jsx_text(c.get("title", ""))
        journal = jsx_text(c.get("journal", ""))
        year = jsx_text(c.get("year", ""))
        vol = jsx_text(c.get("volume", ""))
        iss = jsx_text(c.get("issue", ""))
        pages = jsx_text(c.get("pages", ""))
        pmid = jsx_text(c.get("pmid", ""))
        rows += (
            f"            <li style={{{{ fontSize: {font_size}, lineHeight: 1.45, marginBottom: 10, color: 'var(--osd-text)' }}}}>\n"
            f"              {i+1}. {authors} <em>{ttl}</em>. {journal}. {year};{vol}({iss}):{pages}. "
            f"<span style={{{{ fontFamily: fontMono, color: palette.textSoft }}}}>PMID: {pmid}</span>\n"
            "            </li>\n"
        )
    body = f"""        <ol style={{{{ listStyle: "none", padding: 0, margin: 0 }}}}>
{rows}        </ol>"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='References', header_title=spec.get('title','References'))}\n);\n"


# ─── Skill renderer registry ──────────────────────────────────────────────────


JC_RENDERERS = {
    "paper_meta": render_paper_meta,
    "pico": render_pico,
    "methods": render_methods,
    "results": render_results,
    "literature_evidence": render_literature_evidence,
    "references": render_references,
}


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    data_path = Path(sys.argv[1]).expanduser().resolve()
    output_parent = Path(sys.argv[2]).expanduser().resolve()
    if not data_path.exists():
        sys.exit(f"data.py not found: {data_path}")

    data = load_data(str(data_path))
    build(
        data=data,
        output_parent=output_parent,
        skill_renderers=JC_RENDERERS,
        slide_id="journal-club",
    )


if __name__ == "__main__":
    main()

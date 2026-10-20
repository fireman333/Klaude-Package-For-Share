#!/usr/bin/env python3
"""
notebooklm-pptx → open-slide React deck builder.

Reads the JS `CONTENT` object that drives the .pptx generator and emits an
open-slide deck. The CONTENT schema overlaps heavily with
the generic deck schema (cases / analysis cards / discussion questions /
summary), so we reuse the bundled `lib/open_slide_builder` infra and include
case_story / question / analysis renderers below. Also adds
notebooklm-specific renderers: objectives (numbered cards) and summary_grid
(4-card with icon names).

Usage:
    python3 build_open_slide_deck.py <runner.js> <output_parent_dir>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# open_slide_builder is bundled in this skill's lib/ folder
_SKILL_DIR = Path(__file__).resolve().parent.parent
_LIB_DIR = _SKILL_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from open_slide_builder import (  # noqa: E402
    build,
    _page_chrome,
    _bullet_jsx,
    js_string,
    jsx_text,
)


# ─── Node bridge ──────────────────────────────────────────────────────────────


def extract_content_from_js(js_path: Path) -> dict:
    js_abs = str(js_path.resolve())
    code = f"process.stdout.write(JSON.stringify(require({json.dumps(js_abs)})));"
    res = subprocess.run(
        ["node", "-e", code], capture_output=True, text=True, timeout=30,
    )
    if res.returncode != 0 or not res.stdout.strip().startswith("{") or res.stdout.strip() == "{}":
        # If runner doesn't export CONTENT, try a fallback: load via vm sandbox
        # with a `globalThis.CONTENT = CONTENT;` epilogue appended so the
        # `const` binding becomes reachable from outside the script.
        fallback = (
            "const fs = require('fs'); const vm = require('vm');"
            f"let src = fs.readFileSync({json.dumps(js_abs)}, 'utf8');"
            "const st = src.indexOf('const CONTENT'); const en = st < 0 ? -1 : src.indexOf('\\n};', st);"
            "src = en < 0 ? src + '\\n;globalThis.CONTENT = CONTENT;' : src.slice(0, en + 4) + '\\nglobalThis.CONTENT = CONTENT;' + src.slice(en + 4);"
            "const sandbox = { require: () => new Proxy({}, {get: () => ()=>({})}),"
            " module: { exports: {} }, exports: {},"
            " console: { log: () => {}, error: () => {} },"
            " React: { createElement: () => ({}) },"
            " ReactDOMServer: { renderToStaticMarkup: () => '' },"
            " process: { exit: () => {}, argv: [] } };"
            "vm.createContext(sandbox);"
            "try { vm.runInContext(src, sandbox); } catch (e) {}"
            "process.stdout.write(JSON.stringify(sandbox.CONTENT || {}));"
        )
        res = subprocess.run(
            ["node", "-e", fallback], capture_output=True, text=True, timeout=30,
        )
        if res.returncode != 0:
            raise SystemExit(
                f"\n[content extract FAIL] node returned {res.returncode}\n"
                f"stderr:\n{res.stderr}"
            )
    out = res.stdout[res.stdout.index("{"):] if "{" in res.stdout else "{}"
    return json.loads(out)


# ─── Renderers ────────────────────────────────────────────────────────────────


def render_case_story(component_name: str, spec: dict, theme: dict) -> str:
    case_label = spec.get("case_label", "")
    case_title = spec.get("case_title", "")
    background = spec.get("background", "")
    events = spec.get("events", []) or []
    conflict = spec.get("conflict", "")
    events_jsx = _bullet_jsx(events, indent="              ")
    conflict_block = ""
    if conflict:
        conflict_block = (
            "\n        <div style={{ marginTop: 18, padding: '14px 22px',"
            " background: 'var(--osd-accent)', color: '#fff', borderRadius:"
            " 'var(--osd-radius)', fontSize: 24, fontWeight: 600 }}>"
            f"⚡ {jsx_text(conflict)}</div>"
        )
    body = (
        "        <div style={{ fontSize: 22, lineHeight: 1.5,"
        " color: 'var(--osd-text)', marginBottom: 18, whiteSpace: 'pre-wrap' }}>"
        f"{jsx_text(background)}</div>\n"
        "        <Card>\n"
        "          <div style={{ fontFamily: fontMono, fontSize: 16,"
        " letterSpacing: '0.12em', textTransform: 'uppercase',"
        " color: 'var(--osd-accent)', marginBottom: 10 }}>Events</div>\n"
        f"{events_jsx}\n"
        "        </Card>"
        f"{conflict_block}"
    )
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow=case_label, header_title=case_title)}\n"
        f");\n"
    )


def render_question(component_name: str, spec: dict, theme: dict) -> str:
    case_label = spec.get("case_label", "")
    case_title = spec.get("case_title", "")
    questions = spec.get("questions", []) or []
    minutes = spec.get("suggested_minutes", "")
    rows = ""
    for i, q in enumerate(questions):
        rows += (
            "          <div style={{ display: 'grid',"
            " gridTemplateColumns: '60px 1fr', gap: 18,"
            " alignItems: 'baseline', marginBottom: 16 }}>\n"
            f"            <div style={{{{ fontFamily: fontMono, fontSize: 30,"
            f" fontWeight: 700, color: 'var(--osd-accent)' }}}}>Q{i+1}</div>\n"
            "            <div style={{ fontSize: 28, lineHeight: 1.45,"
            f" color: 'var(--osd-text)' }}}}>{jsx_text(q)}</div>\n"
            "          </div>\n"
        )
    minutes_block = ""
    if minutes:
        minutes_block = (
            "\n        <div style={{ marginTop: 12, fontFamily: fontMono,"
            " fontSize: 22, color: palette.textSoft }}>"
            f"建議討論時間：{jsx_text(str(minutes))} 分鐘</div>"
        )
    body = (
        '        <div style={{ display: "flex", flexDirection: "column",'
        ' justifyContent: "center", flex: 1 }}>\n'
        + rows
        + "        </div>"
        + minutes_block
    )
    eyebrow = f"{case_label} · 討論" if case_label else "Discussion"
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow=eyebrow, header_title=case_title)}\n"
        f");\n"
    )


def render_analysis(component_name: str, spec: dict, theme: dict) -> str:
    """analysis cards grid (1-4) + cp_points panel (side panel)."""
    four = spec.get("four_principles", []) or []
    cp_points = spec.get("cp_points", []) or []
    cp_header = spec.get("cp_header", "")
    cp_subheader = spec.get("cp_subheader", "")
    grid = ""
    for tup in four:
        name, desc = (list(tup) + ["", ""])[:2]
        grid += (
            "            <Card style={{ padding: '16px 22px' }}>\n"
            "              <div style={{ fontSize: 24, fontWeight: 600,"
            f" color: 'var(--osd-text)', marginBottom: 8 }}}}>{jsx_text(name)}</div>\n"
            "              <div style={{ fontSize: 20, lineHeight: 1.45,"
            f" color: palette.textSoft }}}}>{jsx_text(desc)}</div>\n"
            "            </Card>\n"
        )
    cp_jsx = _bullet_jsx(cp_points, indent="              ")
    body = (
        '        <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr",'
        " gap: 22, flex: 1 }}>\n"
        '          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr",'
        " gap: 14 }}>\n"
        f"{grid}          </div>\n"
        "          <Card style={{ background: 'var(--osd-text)', color: '#fff' }}>\n"
        "            <div style={{ fontFamily: fontMono, fontSize: 18,"
        " letterSpacing: '0.1em', color: 'var(--osd-accent)', marginBottom: 6 }}>"
        f"{jsx_text(cp_header)}</div>\n"
        "            <div style={{ fontSize: 20, color: '#fff',"
        f" marginBottom: 14, fontStyle: 'italic' }}}}>{jsx_text(cp_subheader)}</div>\n"
        "            <div style={{ color: '#fff' }}>\n"
        f"{cp_jsx}\n"
        "            </div>\n"
        "          </Card>\n"
        "        </div>"
    )
    title = spec.get("title", "")
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Analysis', header_title=title)}\n"
        f");\n"
    )





def render_objectives(component_name: str, spec: dict, theme: dict) -> str:
    """Learning objectives as numbered cards (1..N)."""
    items = spec.get("items", []) or []
    rows = ""
    for i, it in enumerate(items):
        rows += (
            "          <div style={{ display: 'grid',"
            " gridTemplateColumns: '64px 1fr', gap: 22, alignItems: 'baseline',"
            f" marginBottom: 18 }}}}>\n"
            "            <div style={{ fontFamily: fontMono, fontSize: 36,"
            f" fontWeight: 700, color: 'var(--osd-accent)' }}}}>{i+1:02d}</div>\n"
            "            <div style={{ fontSize: 28, lineHeight: 1.45,"
            f" color: 'var(--osd-text)' }}}}>{jsx_text(it)}</div>\n"
            "          </div>\n"
        )
    body = (
        '        <div style={{ display: "flex", flexDirection: "column",'
        ' justifyContent: "center", flex: 1 }}>\n'
        + rows
        + "        </div>"
    )
    title = spec.get("title", "Learning Objectives")
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Objectives', header_title=title)}\n"
        f");\n"
    )


def render_summary_grid(component_name: str, spec: dict, theme: dict) -> str:
    """Summary principles — 4 cards with title + desc (icon name dropped)."""
    items = spec.get("items", []) or []
    cards = ""
    for it in items:
        title_p = it.get("title", "") if isinstance(it, dict) else (it[0] if isinstance(it, (list, tuple)) else "")
        desc = it.get("desc", "") if isinstance(it, dict) else (it[1] if isinstance(it, (list, tuple)) and len(it) > 1 else "")
        cards += (
            "          <Card style={{ padding: '18px 24px' }}>\n"
            "            <div style={{ fontSize: 24, fontWeight: 600,"
            f" color: 'var(--osd-text)', marginBottom: 10 }}}}>{jsx_text(title_p)}</div>\n"
            "            <div style={{ fontSize: 20, lineHeight: 1.45,"
            f" color: palette.textSoft }}}}>{jsx_text(desc)}</div>\n"
            "          </Card>\n"
        )
    n = len(items)
    if n <= 2:
        grid_cols = "1fr 1fr"
    elif n <= 4:
        grid_cols = "1fr 1fr"  # 2x2
    else:
        grid_cols = "1fr 1fr 1fr"
    body = (
        f'        <div style={{{{ display: "grid", gridTemplateColumns: "{grid_cols}",'
        " gap: 16, flex: 1 }}>\n"
        f"{cards}        </div>"
    )
    title = spec.get("title", "Summary Principles")
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Summary', header_title=title)}\n"
        f");\n"
    )


def render_guidelines(component_name: str, spec: dict, theme: dict) -> str:
    items = spec.get("items", []) or []
    rows = ""
    for i, it in enumerate(items):
        rows += (
            "          <div style={{ display: 'grid',"
            " gridTemplateColumns: '50px 1fr', gap: 18, alignItems: 'baseline',"
            f" padding: '10px 0', borderTop: `1px solid ${{palette.rule}}` }}}}>\n"
            "            <div style={{ fontFamily: fontMono, fontSize: 24,"
            f" fontWeight: 600, color: 'var(--osd-accent)' }}}}>{i+1}.</div>\n"
            "            <div style={{ fontSize: 22, lineHeight: 1.5,"
            f" color: 'var(--osd-text)' }}}}>{jsx_text(it)}</div>\n"
            "          </div>\n"
        )
    footnote = spec.get("footnote", "")
    foot_block = ""
    if footnote:
        foot_block = (
            "\n        <div style={{ marginTop: 18, padding: '12px 18px',"
            " background: palette.cardBg, border: `1px solid ${palette.rule}`,"
            " borderRadius: 'var(--osd-radius)', fontSize: 20, fontStyle: 'italic',"
            f" color: palette.textSoft }}}}>{jsx_text(footnote)}</div>"
        )
    body = (
        f"        <Card>\n{rows}        </Card>"
        f"{foot_block}"
    )
    title = spec.get("title", "Guidelines")
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Guidelines', header_title=title)}\n"
        f");\n"
    )


def render_references_simple(component_name: str, spec: dict, theme: dict) -> str:
    refs = spec.get("references", []) or []
    n = len(refs)
    font = 16 if n >= 10 else (18 if n >= 6 else 20)
    rows = "\n".join(
        f"          <li style={{{{ fontSize: {font}, lineHeight: 1.45,"
        f" marginBottom: 8, color: 'var(--osd-text)' }}}}>{i+1}. {jsx_text(r)}</li>"
        for i, r in enumerate(refs)
    )
    body = (
        f"        <ol style={{{{ listStyle: 'none', padding: 0, margin: 0 }}}}>\n"
        f"{rows}\n"
        "        </ol>"
    )
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='References', header_title='References')}\n"
        f");\n"
    )


# Map each open-slide slide type to a renderer. case_story / question / analysis
# are defined above.
NLM_RENDERERS = {
    "objectives": render_objectives,
    "case_story": render_case_story,
    "question": render_question,
    "analysis": render_analysis,
    "summary_grid": render_summary_grid,
    "guidelines": render_guidelines,
    "references": render_references_simple,
}


# ─── CONTENT → DATA transform ────────────────────────────────────────────────


def content_to_data(content: dict) -> dict:
    title_str = content.get("title", "Discussion Class")
    subtitle = content.get("subtitle", "")
    cover = {
        "label": content.get("footer", "Discussion Class"),
        "title": title_str,
        "subtitle": subtitle,
        "caption_en": "",
        "caption_sub": "",
        "presenter": content.get("author", ""),
        "date": "",
        "course_tag": "",
    }

    slides = [{"type": "cover"}]

    objectives = content.get("objectives", []) or []
    if objectives:
        slides.append({
            "type": "objectives",
            "title": "Learning Objectives",
            "items": objectives,
        })

    # Each case → case_story + question + analysis + suggestion(takeaway)
    cases = content.get("cases", []) or []
    for case in cases:
        ctitle = case.get("title", "")
        csubtitle = case.get("subtitle", "")
        description = case.get("description", []) or []
        if isinstance(description, str):
            description = [description]
        core_issue = case.get("coreIssue") or case.get("core_issue") or ""
        # case_story expects: case_label / case_title / background / events / conflict
        slides.append({
            "type": "case_story",
            "case_label": csubtitle or "Case",
            "case_title": ctitle,
            "background": "",
            "events": description,
            "conflict": core_issue,
        })
        # Discussion questions
        qs = case.get("discussionQuestions") or case.get("discussion_questions") or []
        if qs:
            slides.append({
                "type": "question",
                "case_label": csubtitle or "Case",
                "case_title": ctitle,
                "questions": qs,
                "suggested_minutes": "",
            })
        # Optional analysis cards: new `analysis: [{label,text}]` or legacy `principles` dict
        four = []
        for it in (case.get("analysis") or [])[:4]:
            if it.get("text"):
                four.append((it.get("label", ""), it["text"]))
        principles = case.get("principles", {}) or {}
        if not four and principles:
            label_map = {
                "beneficence": "行善 Beneficence",
                "nonmaleficence": "不傷害 Non-maleficence",
                "autonomy": "自主 Autonomy",
                "justice": "公正 Justice",
            }
            for key in ("beneficence", "nonmaleficence", "autonomy", "justice"):
                if principles.get(key):
                    four.append((label_map[key], principles[key]))
        if four:
            suggestion = case.get("suggestion", "")
            slides.append({
                "type": "analysis",
                "title": f"{ctitle}｜{content.get('analysisTitle') or '分析'}",
                "four_principles": four,
                "cp_points": [suggestion] if suggestion else [],
                "cp_header": "建議",
                "cp_subheader": "Recommended action",
            })

    # Summary principles slide
    summary = content.get("summaryPrinciples") or content.get("summary_principles") or []
    if summary:
        slides.append({
            "type": "summary_grid",
            "title": "Summary",
            "items": summary,
        })

    # Guidelines (optional)
    guidelines = content.get("guidelines", []) or []
    if guidelines:
        slides.append({
            "type": "guidelines",
            "title": content.get("guidelinesTitle") or content.get("guidelines_title") or "Guidelines",
            "items": guidelines,
            "footnote": content.get("guidelinesFootnote") or content.get("guidelines_footnote") or "",
        })

    # References
    refs = content.get("references", []) or []
    if refs:
        slides.append({"type": "references", "references": refs})

    slides.append({
        "type": "blank_teacher",
        "closing_main": "Discussion",
        "closing_sub": "— Thank you —",
    })

    return {
        "meta": {
            "topic_title": title_str,
            "theme": "journal_classic",
            "locale": "zh-TW",
        },
        "cover": cover,
        "outline_items": [],
        "slides": slides,
    }


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    runner_js = Path(sys.argv[1]).expanduser().resolve()
    output_parent = Path(sys.argv[2]).expanduser().resolve()
    if not runner_js.exists():
        sys.exit(f"runner.js not found: {runner_js}")
    content = extract_content_from_js(runner_js)
    data = content_to_data(content)
    print(f"[content] {len(data['slides'])} slides (topic: {data['meta']['topic_title']})")
    build(
        data=data,
        output_parent=output_parent,
        skill_renderers=NLM_RENDERERS,
        slide_id="discussion",
    )


if __name__ == "__main__":
    main()

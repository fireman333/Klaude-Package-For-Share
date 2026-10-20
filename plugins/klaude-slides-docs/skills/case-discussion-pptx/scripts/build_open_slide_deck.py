#!/usr/bin/env python3
"""
case-discussion-pptx → open-slide React deck builder.

Reads the JS `CONTENT` object that drives the .pptx generator and emits a
fully-typed open-slide deck under <output_parent>/<slug>/. Reuses
`notebooklm-pptx/lib/open_slide_builder` infrastructure (themes / cover / outline /
case_profile / case_timeline / case_dx_mgmt / discussion_question /
takeaway / blank_teacher) and adds case-discussion-specific renderers
(admission / imaging / image-placeholder / pathology / 4 rotation-profile
slide types).

Usage:
    python3 build_open_slide_deck.py <runner.js> <output_parent_dir>

The runner.js is any file whose top-level `module.exports = CONTENT;`
(matches templates/example_case.js + the runner the skill writes in Step 5).
A node subprocess does the actual import + JSON.stringify; Python takes it
from there.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Put the sibling skill notebooklm-pptx/lib (open_slide_builder) on sys.path so `import open_slide_builder` works
_SKILL_DIR = Path(__file__).resolve().parent.parent
_COMMON_DIR = _SKILL_DIR.parent / "notebooklm-pptx" / "lib"
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from open_slide_builder import (  # noqa: E402
    build,
    _page_chrome,
    _bullet_jsx,
    js_string,
    jsx_text,
)

# Modalities that benefit from a screenshot placeholder slide between Imaging
# and Pathology. Matches Step 3 Q8 in the SKILL.md.
IMAGE_MODALITY_REGEX = re.compile(
    r"\b(CXR|CT|MRI|Echo|EKG|ECG|US|sono|sonography|endoscopy|colonoscopy|"
    r"PET[-]?CT|PET|EGD|gastroscopy|cystoscopy|bronchoscopy|angio)\b",
    re.I,
)


# ─── Node bridge: load JS runner, dump CONTENT as JSON ────────────────────────


def extract_content_from_js(js_path: Path) -> dict:
    """Use node to `require(js_path)` and emit JSON. Trusts that the runner has
    `module.exports = CONTENT;` at the bottom (matches all templates/example_*.js
    and the file the skill writes in Step 5)."""
    js_abs = str(js_path.resolve())
    code = f"process.stdout.write(JSON.stringify(require({json.dumps(js_abs)})));"
    res = subprocess.run(
        ["node", "-e", code],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if res.returncode != 0:
        raise SystemExit(
            f"\n[content extract FAIL] node returned {res.returncode}\n"
            f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}\n"
            f"Hint: ensure {js_path.name} ends with `module.exports = CONTENT;`."
        )
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise SystemExit(f"\n[content extract FAIL] node output not valid JSON: {e}\nFirst 500 chars:\n{res.stdout[:500]}")


# ─── Skill-specific slide renderers ───────────────────────────────────────────


def render_case_admission(component_name: str, spec: dict, theme: dict) -> str:
    """Slide 4 — three columns: Symptoms / Physical Exam / Laboratory.

    Override of COMMON_RENDERERS.case_findings, which uses pe/lab/image/path
    columns; admission slide uses symptoms/pe/lab instead."""
    cols = []
    for key, label in [
        ("symptoms", "Symptoms"),
        ("pe", "Physical Exam"),
        ("lab", "Laboratory"),
    ]:
        items = spec.get(key, []) or []
        if not items:
            continue
        bullet_jsx = _bullet_jsx(items, indent="            ")
        cols.append(
            "          <Card>\n"
            "            <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
            " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>"
            f"{jsx_text(label)}</div>\n"
            f"{bullet_jsx}\n"
            "          </Card>"
        )
    n = len(cols)
    grid_cols = {0: "1fr", 1: "1fr", 2: "1fr 1fr", 3: "1fr 1fr 1fr"}[n]
    cols_jsx = "\n".join(cols) if cols else "          <BulletList />"
    body = (
        f'        <div style={{{{ display: "grid", gridTemplateColumns: "{grid_cols}",'
        f' gap: 20, flex: 1 }}}}>\n{cols_jsx}\n        </div>'
    )
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Admission', header_title='Findings on Admission')}\n"
        f");\n"
    )


def render_case_imaging(component_name: str, spec: dict, theme: dict) -> str:
    """Slide 5 (one slide per study) — modality + date + findings list +
    impression card."""
    modality = spec.get("modality", "Imaging")
    date = spec.get("date", "")
    findings = spec.get("findings", []) or []
    impression = spec.get("impression", "")
    findings_jsx = _bullet_jsx(findings, indent="              ")
    impression_block = ""
    if impression:
        impression_block = (
            "\n          <Card style={{ marginTop: 16 }}>\n"
            "            <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
            " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>"
            "Impression</div>\n"
            "            <div style={{ fontSize: 26, lineHeight: 1.5, color: 'var(--osd-text)' }}>"
            f"{jsx_text(impression)}</div>\n"
            "          </Card>"
        )
    body = (
        "        <div style={{ fontFamily: fontMono, fontSize: 22, color: palette.textSoft,"
        " marginBottom: 16 }}>\n"
        f"          {jsx_text(date)}\n"
        "        </div>\n"
        "        <Card>\n"
        "            <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
        " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>Findings</div>\n"
        f"{findings_jsx}\n"
        "          </Card>"
        f"{impression_block}"
    )
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Imaging', header_title=modality)}\n"
        f");\n"
    )


def render_case_image_placeholder(component_name: str, spec: dict, theme: dict) -> str:
    """Reserved slot for screenshot from PACS/EMR before the talk.

    Layout budget (canvas 1080 − PADDING*2 − FOOTER_RESERVE = 740, minus header
    ~156 = ~580 for body). Date row ~30 + ImagePlaceholder 520 + caption ~50 +
    margins ≈ 600. Tight; impression text capped at 1–2 lines via fontSize 20."""
    modality = spec.get("modality", "Imaging")
    date = spec.get("date", "")
    impression = spec.get("impression", "")
    hint = spec.get("hint") or f"{modality} screenshot from PACS / EMR"
    impression_block = ""
    if impression:
        impression_block = (
            '\n        <p style={{ marginTop: 12, fontSize: 20, fontStyle: "italic",'
            " color: palette.textSoft, lineHeight: 1.4, textAlign: 'center' }}>\n"
            f"          {jsx_text(impression)}\n"
            "        </p>"
        )
    body = (
        "        <div style={{ fontFamily: fontMono, fontSize: 20, color: palette.textSoft,"
        " marginBottom: 12 }}>\n"
        f"          {jsx_text(date)}\n"
        "        </div>\n"
        f"        <ImagePlaceholder hint={{{js_string(hint)}}} width={{1500}} height={{520}} />"
        f"{impression_block}"
    )
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Image', header_title=modality)}\n"
        f");\n"
    )


def render_case_pathology(component_name: str, spec: dict, theme: dict) -> str:
    rows = [
        ("Date", spec.get("date", "")),
        ("Specimen", spec.get("specimen", "")),
        ("Description", spec.get("description", "")),
        ("Diagnosis", spec.get("diagnosis", "")),
    ]
    kv_block = "\n".join(
        f"          <KV k={{{js_string(k)}}} v={{{js_string(v)}}} />" for k, v in rows if v
    )
    body = f"        <Card style={{{{ flex: 1 }}}}>\n{kv_block}\n        </Card>"
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Pathology', header_title='Pathology Report')}\n"
        f");\n"
    )


def render_operative_procedure(component_name: str, spec: dict, theme: dict) -> str:
    rows = [
        ("Indication", spec.get("indication", "")),
        ("Approach", spec.get("approach", "")),
        ("Reconstruction", spec.get("reconstruction", "")),
    ]
    kv_block = "\n".join(
        f"            <KV k={{{js_string(k)}}} v={{{js_string(v)}}} />" for k, v in rows if v
    )
    key_steps = spec.get("keySteps") or spec.get("key_steps") or []
    intraop = spec.get("intraopFindings") or spec.get("intraop_findings") or ""
    steps_jsx = _bullet_jsx(key_steps, indent="              ")
    intraop_block = ""
    if intraop:
        intraop_block = (
            "\n        <Card style={{ marginTop: 16 }}>\n"
            "          <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
            " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>"
            "Intraoperative findings</div>\n"
            "          <div style={{ fontSize: 26, lineHeight: 1.5, color: 'var(--osd-text)' }}>"
            f"{jsx_text(intraop)}</div>\n"
            "        </Card>"
        )
    body = (
        '        <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr",'
        " gap: 20 }}>\n"
        "          <Card>\n"
        f"{kv_block}\n"
        "          </Card>\n"
        "          <Card>\n"
        "            <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
        " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>Key steps</div>\n"
        f"{steps_jsx}\n"
        "          </Card>\n"
        "        </div>"
        f"{intraop_block}"
    )
    title = spec.get("title", "Operative Procedure")
    subtitle = spec.get("subtitle", "") or "Procedure"
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow=subtitle, header_title=title)}\n"
        f");\n"
    )


def render_operative_photo_placeholder(component_name: str, spec: dict, theme: dict) -> str:
    label = spec.get("label") or "Intraoperative photo from OR display"
    title = spec.get("title", "Operative Photograph")
    body = (
        f"        <ImagePlaceholder hint={{{js_string(label)}}} width={{1500}} height={{720}} />"
    )
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Intraop', header_title=title)}\n"
        f");\n"
    )


def render_postop_course(component_name: str, spec: dict, theme: dict) -> str:
    icu = spec.get("icuDays") or spec.get("icu_days")
    rows = []
    if icu not in (None, ""):
        rows.append(("ICU days", str(icu)))
    ove = spec.get("outcomeVsExpected") or spec.get("outcome_vs_expected") or ""
    if ove:
        rows.append(("Outcome vs expected", ove))
    kv_block = "\n".join(
        f"            <KV k={{{js_string(k)}}} v={{{js_string(v)}}} />" for k, v in rows
    )
    outcome = spec.get("outcome") or []
    if isinstance(outcome, str):
        outcome = [outcome]
    complications = spec.get("complications") or []
    if isinstance(complications, str):
        complications = [complications]
    outcome_jsx = _bullet_jsx(outcome, indent="              ")
    compl_jsx = _bullet_jsx(complications, indent="              ")
    body = (
        '        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr",'
        " gap: 20, flex: 1 }}>\n"
        "          <Card>\n"
        f"{kv_block}\n"
        "          </Card>\n"
        '          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>\n'
        "            <Card>\n"
        "              <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
        " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>Hospital course</div>\n"
        f"{outcome_jsx}\n"
        "            </Card>\n"
        "            <Card>\n"
        "              <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
        " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>Complications</div>\n"
        f"{compl_jsx}\n"
        "            </Card>\n"
        "          </div>\n"
        "        </div>"
    )
    title = spec.get("title", "Postoperative Course")
    subtitle = spec.get("subtitle", "") or "Postop"
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow=subtitle, header_title=title)}\n"
        f");\n"
    )


def render_back_to_patient(component_name: str, spec: dict, theme: dict) -> str:
    alternatives = spec.get("alternatives") or []
    if isinstance(alternatives, str):
        alternatives = [alternatives]
    reflection = spec.get("reflection", "")
    lessons = spec.get("lessons") or []
    if isinstance(lessons, str):
        lessons = [lessons]
    alt_jsx = _bullet_jsx(alternatives, indent="              ")
    less_jsx = _bullet_jsx(lessons, indent="              ")
    refl_block = ""
    if reflection:
        refl_block = (
            '\n        <Card style={{ marginTop: 16 }}>\n'
            "          <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
            " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>Reflection</div>\n"
            '          <div style={{ fontSize: 26, lineHeight: 1.55, color: "var(--osd-text)",'
            ' fontStyle: "italic" }}>'
            f"{jsx_text(reflection)}</div>\n"
            "        </Card>"
        )
    body = (
        '        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr",'
        " gap: 20 }}>\n"
        "          <Card>\n"
        "            <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
        " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>"
        "Alternatives considered</div>\n"
        f"{alt_jsx}\n"
        "          </Card>\n"
        "          <Card>\n"
        "            <div style={{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em',"
        " textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}>Lessons</div>\n"
        f"{less_jsx}\n"
        "          </Card>\n"
        "        </div>"
        f"{refl_block}"
    )
    title = spec.get("title", "Back to the Patient")
    subtitle = spec.get("subtitle", "") or "Reflection"
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow=subtitle, header_title=title)}\n"
        f");\n"
    )


def render_take_home_summary(component_name: str, spec: dict, theme: dict) -> str:
    bullets = spec.get("bullets") or []
    rows = ""
    for i, b in enumerate(bullets):
        rows += (
            "          <div style={{ display: 'grid', gridTemplateColumns: '64px 1fr',"
            " gap: 24, alignItems: 'baseline' }}>\n"
            "            <div style={{ fontFamily: fontMono, fontSize: 36, fontWeight: 700,"
            " color: 'var(--osd-accent)' }}>"
            f"{i+1:02d}"
            "</div>\n"
            "            <div style={{ fontSize: 30, fontWeight: 500, color: 'var(--osd-text)',"
            " lineHeight: 1.4 }}>"
            f"{jsx_text(b)}"
            "</div>\n"
            "          </div>\n"
        )
    body = (
        '        <div style={{ display: "flex", flexDirection: "column", gap: 24,'
        ' justifyContent: "center", flex: 1 }}>\n'
        f"{rows}        </div>"
    )
    title = spec.get("title", "Take-Home Summary")
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Take-home', header_title=title)}\n"
        f");\n"
    )


def render_case_timeline_dense(component_name: str, spec: dict, theme: dict) -> str:
    """Override of COMMON_RENDERERS.case_timeline — case discussions routinely
    have 8–12 events; default 26pt event font + 14px padding overflows past 8
    events. Drop to 22pt + 10px padding (~42 px / row) to fit ~13 events."""
    events = spec.get("events", []) or []
    rows = ""
    for ev in events:
        date_txt = jsx_text(ev.get("date", ""))
        event_txt = jsx_text(ev.get("event_en") or ev.get("event", ""))
        rows += (
            "            <div style={{ display: 'grid', gridTemplateColumns: '170px 1fr',"
            " gap: 22, padding: '10px 0', borderTop: `1px solid ${palette.rule}` }}>\n"
            "              <div style={{ fontFamily: fontMono, fontSize: 20,"
            f" color: 'var(--osd-accent)' }}}}>{date_txt}</div>\n"
            "              <div style={{ fontSize: 22, lineHeight: 1.4,"
            f" color: 'var(--osd-text)' }}}}>{event_txt}</div>\n"
            "            </div>\n"
        )
    body = "        <Card style={{ flex: 1, padding: '16px 28px' }}>\n" + rows + "        </Card>"
    title = spec.get("title", "Clinical Timeline")
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow='Course', header_title=title)}\n"
        f");\n"
    )


def render_case_dx_mgmt_stacked(component_name: str, spec: dict, theme: dict) -> str:
    """Override of COMMON_RENDERERS.case_dx_mgmt — 2×2 grid + long bullets blows
    out vertical budget (seen 500+ px overflow in dogfood). Stacks the 4 cards
    full-width with denser font (22pt bullets, 16px card padding) — long
    bullets wrap once at most across full canvas width.

    When `_only` is "dx" or "mgmt", suppresses the empty quadrants and uses a
    larger 26pt body font (only 2 cards to fit, so density isn't tight)."""
    only = spec.get("_only")
    if only == "dx":
        quadrants = [
            ("Active Problems", spec.get("active", []) or []),
            ("Underlying", spec.get("underlying", []) or []),
        ]
        header_eyebrow = "Plan"
        header_title = "Tentative Diagnosis"
        body_font = 26
    elif only == "mgmt":
        quadrants = [
            ("Orders", spec.get("orders", []) or []),
            ("Goals", spec.get("goals", []) or []),
        ]
        header_eyebrow = "Plan"
        header_title = "Management"
        body_font = 26
    else:
        quadrants = [
            ("Active Problems", spec.get("active", []) or []),
            ("Underlying", spec.get("underlying", []) or []),
            ("Orders", spec.get("orders", []) or []),
            ("Goals", spec.get("goals", []) or []),
        ]
        header_eyebrow = "Plan"
        header_title = "Diagnosis & Management"
        body_font = 22
    cells = ""
    for label, items in quadrants:
        if not items:
            continue
        bullets = "\n".join(
            "              <li style={{ display: 'flex', gap: 10, alignItems: 'baseline',"
            f" fontSize: {body_font}, lineHeight: 1.4, color: 'var(--osd-text)', marginBottom: 6 }}}}>"
            f"<span style={{{{ color: 'var(--osd-accent)', fontSize: {body_font - 4} }}}}>▸</span>"
            f"<span>{jsx_text(i)}</span></li>"
            for i in items
        )
        cells += (
            "          <Card style={{ padding: '16px 24px' }}>\n"
            "            <div style={{ fontFamily: fontMono, fontSize: 16,"
            " letterSpacing: '0.12em', textTransform: 'uppercase',"
            " color: 'var(--osd-accent)', marginBottom: 10 }}>"
            f"{jsx_text(label)}</div>\n"
            "            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>\n"
            f"{bullets}\n"
            "            </ul>\n"
            "          </Card>\n"
        )
    body = (
        '        <div style={{ display: "flex", flexDirection: "column", gap: 14,'
        " flex: 1 }}>\n"
        f"{cells}        </div>"
    )
    return (
        f"const {component_name}: Page = () => (\n"
        f"{_page_chrome(body, header_eyebrow=header_eyebrow, header_title=header_title)}\n"
        f");\n"
    )


CASE_RENDERERS = {
    "case_admission": render_case_admission,
    "case_imaging": render_case_imaging,
    "case_image_placeholder": render_case_image_placeholder,
    "case_pathology": render_case_pathology,
    # Overrides of COMMON_RENDERERS — denser layout for case-discussion content
    # density (8–12 timeline events, long Active Problems descriptions).
    "case_timeline": render_case_timeline_dense,
    "case_dx_mgmt": render_case_dx_mgmt_stacked,
    "operative_procedure": render_operative_procedure,
    "operative_photo_placeholder": render_operative_photo_placeholder,
    "postop_course": render_postop_course,
    "back_to_patient": render_back_to_patient,
    "take_home_summary": render_take_home_summary,
}


# ─── CONTENT (JS-style) → DATA (open-slide) transform ─────────────────────────


def _join(x, sep="; ") -> str:
    if isinstance(x, list):
        return sep.join(str(i) for i in x if i)
    return str(x or "")


def content_to_data(content: dict) -> dict:
    """Transform the skill's CONTENT dict into the DATA dict consumed by
    `open_slide_builder.build()`. Layout follows the 9-slide architecture
    described in SKILL.md (cover → profile → timeline → admission → imaging
    [+ placeholders] → pathology → dx/management → discussion → optional
    rotation slides → optional take-home)."""
    age = content.get("age", "")
    sex = content.get("sex", "")
    cc = content.get("chiefComplaint") or content.get("chief_complaint") or ""
    reporter = content.get("reporter", "")
    report_date = content.get("reportDate") or content.get("report_date") or ""
    chart_no = content.get("chartNo") or content.get("chart_no") or ""

    # Topic title goes in the footer of every slide.
    topic_short = cc[:70] + ("…" if len(cc) > 70 else "")
    topic_title = f"Case Discussion · {topic_short}" if cc else "Case Discussion"

    cover = {
        "label": "Case Discussion",
        "title": f"{age} y/o {sex}".strip(" y/o "),
        "subtitle": cc,
        "caption_en": f"Chart No. {chart_no}" if chart_no else "",
        "caption_sub": "",
        "presenter": reporter,
        "date": report_date,
        "course_tag": content.get("institution") or "Clinical Case Discussion",
    }

    slides: list[dict] = [{"type": "cover"}]

    # Slide 2: Profile
    profile = content.get("profile", {}) or {}
    family_hx = profile.get("familyHx") or profile.get("family_hx") or ""
    substance = profile.get("substance") or ""
    note_extras = []
    if substance:
        note_extras.append(f"Substance: {substance}")
    if family_hx:
        note_extras.append(f"Family Hx: {family_hx}")
    slides.append({
        "type": "case_profile",
        "age": age,
        "sex": sex,
        "chief_complaint": cc,
        "underlying": _join(profile.get("underlying", [])),
        "tocc": profile.get("tocc", ""),
        "medication": _join(profile.get("medication", [])),
        "notes": " · ".join(note_extras) if note_extras else None,
    })

    # Slide 3: Timeline
    timeline = content.get("timeline", []) or []
    if timeline:
        slides.append({
            "type": "case_timeline",
            "title": "Clinical Timeline",
            "events": [
                {"date": ev.get("date", ""), "event_en": ev.get("event", "") or ev.get("event_en", "")}
                for ev in timeline
            ],
        })

    # Slide 4: Admission (custom 3-col Symptoms / PE / Lab)
    admission = content.get("admission", {}) or {}
    if any(admission.get(k) for k in ("symptoms", "pe", "lab")):
        slides.append({
            "type": "case_admission",
            "symptoms": admission.get("symptoms", []) or [],
            "pe": admission.get("pe", []) or [],
            "lab": admission.get("lab", []) or [],
        })

    # Slide 5: Imaging (one slide per study)
    imaging = content.get("imaging", []) or []
    for img in imaging:
        slides.append({
            "type": "case_imaging",
            "modality": img.get("modality", "Imaging"),
            "date": img.get("date", ""),
            "findings": img.get("findings", []) or [],
            "impression": img.get("impression", ""),
        })

    # Examination Report (when ChatLayout chose separate_slide; we render
    # same as case_imaging if present + non-empty)
    examination = content.get("examination", []) or []
    for ex in examination:
        slides.append({
            "type": "case_imaging",  # same renderer
            "modality": ex.get("type", "Examination"),
            "date": ex.get("date", ""),
            "findings": ex.get("findings", []) or [],
            "impression": ex.get("impression", ""),
        })

    # Slide 5a-n: image placeholders (auto-derived unless explicit array / false)
    image_slots = content.get("imageSlots")
    if image_slots is False or image_slots == 0:
        pass  # skip all
    elif isinstance(image_slots, list):
        for slot in image_slots:
            slides.append({
                "type": "case_image_placeholder",
                "modality": slot.get("modality", "Imaging"),
                "date": slot.get("date", ""),
                "impression": slot.get("impression", ""),
                "hint": slot.get("hint"),
            })
    else:
        # Auto: one placeholder per imaging-able study
        for img in imaging + examination:
            mod = img.get("modality") or img.get("type") or ""
            if IMAGE_MODALITY_REGEX.search(mod):
                slides.append({
                    "type": "case_image_placeholder",
                    "modality": mod,
                    "date": img.get("date", ""),
                    "impression": img.get("impression", ""),
                    "hint": f"{mod} screenshot from PACS / EMR",
                })

    # Slide 6: Pathology
    pathology = content.get("pathology", {}) or {}
    if any(pathology.values()):
        slides.append({
            "type": "case_pathology",
            "date": pathology.get("date", ""),
            "specimen": pathology.get("specimen", ""),
            "description": pathology.get("description", ""),
            "diagnosis": pathology.get("diagnosis", ""),
        })

    # Slides 7 + 8: Tentative Dx (active + underlying) and Management (orders +
    # goals). Originally collapsed into one 2×2 dx_mgmt slide, but typical
    # Case content has 4–5 long bullets per quadrant → 200–500 px overflow
    # on a single slide. Per slide-authoring §"Splitting is always the right
    # answer", emit two stacked-card slides instead.
    tdx = content.get("tentativeDx") or content.get("tentative_dx") or {}
    mgmt = content.get("management") or {}
    if tdx.get("active") or tdx.get("underlying"):
        slides.append({
            "type": "case_dx_mgmt",
            "_only": "dx",
            "active": tdx.get("active", []) or [],
            "underlying": tdx.get("underlying", []) or [],
            "orders": [],
            "goals": [],
        })
    if mgmt.get("orders") or mgmt.get("goals"):
        slides.append({
            "type": "case_dx_mgmt",
            "_only": "mgmt",
            "active": [],
            "underlying": [],
            "orders": mgmt.get("orders", []) or [],
            "goals": mgmt.get("goals", []) or [],
        })

    # Slide 9: Discussion (one slide per question)
    questions = content.get("discussionQuestions") or content.get("discussion_questions") or []
    trail = content.get("discussionTrail") or content.get("discussion_trail") or []
    for i, q in enumerate(questions):
        notes = None
        if i < len(trail):
            t = trail[i]
            synth = t.get("synthesis", "")
            cits = t.get("citations", []) or []
            note_lines = []
            if synth:
                note_lines.append(synth)
            if cits:
                note_lines.append("")
                note_lines.append("Citations:")
                note_lines.extend(f"  {c}" for c in cits[:3])
            notes = "\n".join(note_lines) if note_lines else None
        slides.append({
            "type": "discussion_question",
            "q_num": i + 1,
            "q_text_en": q,
            "suggested_minutes": "",
            "prompts_for_audience": [],
            "notes": notes,
        })

    # ─── Rotation profile slides (CVS et al.) ────────────────────────────────

    op = content.get("operativeProcedure") or content.get("operative_procedure")
    if op:
        slides.append({"type": "operative_procedure", **op})
        photo_slots = op.get("photoSlots") or op.get("photo_slots") or 0
        for i in range(int(photo_slots) if photo_slots else 0):
            slides.append({
                "type": "operative_photo_placeholder",
                "label": f"Intraoperative photo #{i+1}",
            })

    pc = content.get("postopCourse") or content.get("postop_course")
    if pc:
        slides.append({"type": "postop_course", **pc})

    btp = content.get("backToPatient") or content.get("back_to_patient")
    if btp:
        slides.append({"type": "back_to_patient", **btp})

    ths = content.get("takeHomeSummary") or content.get("take_home_summary")
    if ths:
        slides.append({"type": "take_home_summary", **ths})

    # Closing slide (floor open)
    slides.append({
        "type": "blank_teacher",
        "closing_main": "Discussion",
        "closing_sub": "— Thank you for listening —",
    })

    return {
        "meta": {
            "topic_title": topic_title,
            "theme": content.get("theme", "grand_rounds_warm"),
            "locale": "zh-TW",
        },
        "cover": cover,
        "outline_items": [],
        "slides": slides,
    }


# ─── Entry point ──────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    runner_js = Path(sys.argv[1]).expanduser().resolve()
    output_parent = Path(sys.argv[2]).expanduser().resolve()
    if not runner_js.exists():
        sys.exit(f"runner.js not found: {runner_js}")

    print(f"[content] extracting CONTENT from {runner_js.name} via node bridge...")
    content = extract_content_from_js(runner_js)
    data = content_to_data(content)
    print(f"[content] → {len(data['slides'])} slides (theme={data['meta']['theme']})")
    build(
        data=data,
        output_parent=output_parent,
        skill_renderers=CASE_RENDERERS,
        slide_id="case-discussion",
    )


if __name__ == "__main__":
    main()

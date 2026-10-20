"""
journal-club-discussion-pptx builder — slide layout functions for journal club /
case discussion pptx, theme-aware.

Forked from an earlier discussion-deck builder, but
retargeted for:
- paper-centered slides (paper_meta, pico, methods, results)
- case-centered slides (case_profile, case_timeline, case_findings, case_dx_mgmt)
- research-augmented slides (discussion_question, literature_evidence, references)

Theme system: call set_theme(theme_dict) once per presentation before dispatching
layouts (render.py does this from DATA["meta"]["theme"]).

Design rules (enforced upstream by scripts/rule1_check.py):
- Slide body text must be English only (Rule 1 — academic-slide-conventions)
- Bilingual speaker notes go via the notes attribute handled by render.py
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from lxml import etree

from templates.themes import get_theme, DEFAULT_THEME


# ---------- theme state ----------
_T = get_theme(DEFAULT_THEME)


def set_theme(theme_dict: dict) -> None:
    """Rebind module-level theme. Called by render.py before slide dispatch."""
    global _T
    _T = theme_dict


SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


# ---------- font sizing v2 (2026-05-07) ----------
# Hard gate: build raises AssertionError when body < MIN_BODY_PT or title < MIN_TITLE_PT.
# Forked from an earlier discussion-deck builder (v2 refactor).
MIN_TITLE_PT = 28
MIN_BODY_PT = 14

SIZE_TITLE_HERO = 40       # section_divider title
SIZE_TITLE_LARGE = 32      # cover hero title, blank_teacher heading
SIZE_TITLE_STANDARD = 28   # internal slide_title
SIZE_SUBTITLE = 20         # cover topic_num, paper_meta heading
SIZE_BODY_LARGE = 18       # outline bullet (large state), takeaway point heading
SIZE_BODY_STANDARD = 16    # default body — bullets, events, principle name
SIZE_BODY_TIGHT = 14       # minimum compliant body — paper meta, dense panels
SIZE_CAPTION = 12          # captions / top_note — gate exempt
SIZE_FOOTER = 9            # footer — gate exempt
SIZE_WATERMARK = 140       # decorative chapter number on dividers — gate exempt
SIZE_COVER_BIG = 48        # cover dual-color hero — gate exempt

EXEMPT_PURPOSES = {
    "footer",
    "watermark",
    "caption",
    "cover_big",
    "cover_caption_en",
    "decorative_number",
    "spacer",
    "table_micro",   # dense table cells where 14pt would overflow (uses 11-12pt)
    "ref_micro",     # references list compressed display
}


# ---------- helpers ----------

def set_eastasia(run, font_name):
    rPr = run._r.get_or_add_rPr()
    for ea in rPr.findall(qn("a:ea")):
        rPr.remove(ea)
    ea = etree.SubElement(rPr, qn("a:ea"))
    ea.set("typeface", font_name)


def _gate_check(size, text, purpose):
    """Hard gate: raises AssertionError if size violates floor for its class.

    Classification heuristic when purpose is None:
      size >= 24 -> title class (gate at MIN_TITLE_PT = 28)
      size <  24 -> body class  (gate at MIN_BODY_PT  = 14)
    Purposes in EXEMPT_PURPOSES bypass the gate.
    """
    if purpose in EXEMPT_PURPOSES:
        return
    if purpose is not None and purpose not in EXEMPT_PURPOSES:
        raise AssertionError(
            f"Unknown purpose={purpose!r}; add to EXEMPT_PURPOSES if intentional"
        )
    if size >= 24:
        if size < MIN_TITLE_PT:
            raise AssertionError(
                f"Title font {size}pt < MIN_TITLE_PT={MIN_TITLE_PT} (text={text[:30]!r})"
            )
    else:
        if size < MIN_BODY_PT:
            raise AssertionError(
                f"Body font {size}pt < MIN_BODY_PT={MIN_BODY_PT} (text={text[:30]!r})"
            )


def add_text(tf, text, *, size=14, bold=False, color=None, align=PP_ALIGN.LEFT,
             font=None, italic=False, purpose=None):
    _gate_check(size, text, purpose)
    if color is None:
        color = _T["text"]
    if font is None:
        font = _T["body_font"]
    if tf.paragraphs and not tf.paragraphs[0].runs:
        p = tf.paragraphs[0]
    else:
        p = tf.add_paragraph()
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    set_eastasia(run, font)
    return p


def add_run(paragraph, text, *, size=14, bold=False, color=None, font=None,
            italic=False, purpose=None):
    _gate_check(size, text, purpose)
    if color is None:
        color = _T["text"]
    if font is None:
        font = _T["body_font"]
    run = paragraph.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    set_eastasia(run, font)
    return run


def add_rect(slide, left, top, width, height, fill, line=None):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.5)
    shp.text_frame.text = ""
    return shp


def add_text_box(slide, left, top, width, height, *, fill=None, line=None):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.1)
    tf.margin_right = Inches(0.1)
    tf.margin_top = Inches(0.05)
    tf.margin_bottom = Inches(0.05)
    if fill is not None:
        tb.fill.solid()
        tb.fill.fore_color.rgb = fill
    if line is not None:
        tb.line.color.rgb = line
        tb.line.width = Pt(0.75)
    tf.clear()
    return tb, tf


def strip_leading_empty_paragraphs(prs):
    """Walk every shape on every slide; remove leading <a:p> elements that have
    no runs (empty placeholder paragraphs left over from tf.clear() when a
    layout function added subsequent paragraphs via tf.add_paragraph() instead
    of populating paragraphs[0]). Stops at the first paragraph with content,
    so intentional in-body spacers (which have at least one whitespace run)
    are preserved."""
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            txBody = shape.text_frame._txBody
            for p in list(txBody.findall(qn("a:p"))):
                if p.findall(qn("a:r")):
                    break
                txBody.remove(p)


def add_thin_accent_bar(slide, left, top, width):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, Emu(32000))
    bar.fill.solid()
    bar.fill.fore_color.rgb = _T["accent"]
    bar.line.fill.background()
    return bar


def add_footer(slide, page_num, topic_title, *, total=None):
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(6.92),
                                   Inches(12.33), Emu(6000))
    line.fill.solid()
    line.fill.fore_color.rgb = _T["accent"]
    line.line.fill.background()
    tb, tf = add_text_box(slide, Inches(0.5), Inches(6.97), Inches(9), Inches(0.3))
    add_text(tf, topic_title, size=SIZE_FOOTER, color=_T["text_light"],
             align=PP_ALIGN.LEFT, purpose="footer")
    tb2, tf2 = add_text_box(slide, Inches(11.2), Inches(6.97), Inches(1.63),
                             Inches(0.3))
    txt = f"{page_num}" if total is None else f"{page_num} / {total}"
    add_text(tf2, txt, size=SIZE_FOOTER, color=_T["text_light"],
             align=PP_ALIGN.RIGHT, purpose="footer")


def slide_title(slide, title):
    tb, tf = add_text_box(slide, Inches(0.6), Inches(0.32), Inches(12),
                           Inches(0.78))
    add_text(tf, title, size=SIZE_TITLE_STANDARD, color=_T["primary"], bold=True,
             font=_T["head_font"])
    add_thin_accent_bar(slide, Inches(0.6), Inches(1.18), Inches(0.8))


# ---------- slide layouts ----------

def slide_cover(prs, *, label, title, subtitle, big_word_primary, big_word_accent,
                caption_en, caption_sub, presenter="Presenter", date="",
                course_tag=""):
    """Journal club or case discussion cover.
    label: eg "Journal Club" / "Case Discussion" / "書報討論"
    caption_en: small subtitle (English mandatory per Rule 1)
    caption_sub: italic subtitle
    """
    s = prs.slides.add_slide(prs.slide_layouts[6])
    # left band = primary, thin accent rule between
    add_rect(s, 0, 0, Inches(5.33), SLIDE_H, _T["primary"])
    add_rect(s, Inches(5.33), 0, Emu(40000), SLIDE_H, _T["accent"])
    # right side background fill
    add_rect(s, Inches(5.35), 0, Inches(7.99), SLIDE_H, _T["bg"])

    tb, tf = add_text_box(s, Inches(0.6), Inches(1.2), Inches(4.3), Inches(0.6))
    add_text(tf, label, size=SIZE_BODY_TIGHT, color=_T["accent"], font=_T["head_font"])

    tb, tf = add_text_box(s, Inches(0.6), Inches(1.9), Inches(4.5), Inches(3.5))
    add_text(tf, title, size=SIZE_TITLE_STANDARD, color=WHITE, font=_T["head_font"], bold=True)

    tb2, tf2 = add_text_box(s, Inches(0.6), Inches(5.2), Inches(4.5), Inches(0.8))
    add_text(tf2, subtitle, size=SIZE_CAPTION, color=_T["accent"], italic=True, purpose="caption")

    tb3, tf3 = add_text_box(s, Inches(0.6), Inches(6.2), Inches(4.5), Inches(0.6))
    add_text(tf3, f"Presenter | {presenter}", size=SIZE_CAPTION, color=WHITE, purpose="caption")
    add_text(tf3, f"{course_tag}  {date}".strip(), size=SIZE_CAPTION,
             color=_T["accent"], purpose="caption")

    tb, tf = add_text_box(s, Inches(6.2), Inches(2.6), Inches(6.5), Inches(2.5))
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    add_run(p, big_word_primary + "\n", size=SIZE_COVER_BIG, color=_T["primary"], bold=True,
            font=_T["head_font"], purpose="cover_big")
    add_run(p, big_word_accent, size=SIZE_COVER_BIG, color=_T["accent"], bold=True,
            font=_T["head_font"], purpose="cover_big")

    tb, tf = add_text_box(s, Inches(6.2), Inches(4.5), Inches(6.5), Inches(1.2))
    add_text(tf, caption_en, size=SIZE_SUBTITLE, color=_T["primary"], font=_T["head_font"])
    if caption_sub:
        add_text(tf, caption_sub, size=SIZE_CAPTION, color=_T["text_light"],
                 italic=True, purpose="cover_caption_en")


def slide_outline(prs, *, items, page, topic_title, heading="Outline"):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    tb, tf = add_text_box(s, Inches(0.6), Inches(0.4), Inches(12), Inches(0.8))
    add_text(tf, heading, size=SIZE_TITLE_LARGE, color=_T["primary"], bold=True,
             font=_T["head_font"])
    add_thin_accent_bar(s, Inches(0.6), Inches(1.15), Inches(1.2))

    n = max(1, len(items))
    top_y = 1.45
    bottom_y = 7.05  # leave room for footer
    avail = bottom_y - top_y
    # cap at 1.05" per row so 5-item decks stay roomy; auto-shrink for 6+
    row_h_in = min(1.05, avail / n)
    bullet_size = SIZE_BODY_LARGE if row_h_in >= 0.95 else SIZE_BODY_STANDARD
    desc_size = SIZE_BODY_TIGHT  # fixed at 14pt floor
    num_h_in = min(0.7, row_h_in - 0.18)
    top = Inches(top_y)
    row_h = Inches(row_h_in)
    for i, item in enumerate(items):
        num, title, meta, desc = item
        y = top + i * row_h
        num_shape = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.6), y,
                                        Inches(num_h_in), Inches(num_h_in))
        num_shape.fill.solid()
        num_shape.fill.fore_color.rgb = _T["primary"]
        num_shape.line.fill.background()
        ntf = num_shape.text_frame
        ntf.margin_left = ntf.margin_right = Inches(0)
        ntf.margin_top = ntf.margin_bottom = Inches(0)
        ntf.vertical_anchor = MSO_ANCHOR.MIDDLE
        ntf.paragraphs[0].alignment = PP_ALIGN.CENTER
        r = ntf.paragraphs[0].add_run()
        r.text = num
        r.font.bold = True
        r.font.size = Pt(14)
        r.font.color.rgb = _T["accent"]
        r.font.name = "Helvetica"

        # SINGLE textbox per item — title (line 1) + desc (line 2) in one
        # text_frame so paragraph spacing is deterministic. Two-textbox layout
        # had the desc visually drift toward the NEXT item's title under
        # LibreOffice rendering even when the box geometry said otherwise.
        tb, tf = add_text_box(s, Inches(1.55), y - Inches(0.05), Inches(10.5),
                               Inches(row_h_in - 0.05))
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        add_run(p, title, size=bullet_size, color=_T["primary"], bold=True,
                font=_T["head_font"])
        add_run(p, "    " + meta, size=desc_size, color=_T["accent"],
                font=_T["head_font"])
        # desc on its own paragraph keeps it visually attached to title
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.LEFT
        add_run(p2, desc, size=desc_size, color=_T["text_light"])
    add_footer(s, page, topic_title)


def slide_section_divider(prs, *, chapter, title, lead, page, topic_title):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["card_bg"])
    tb, tf = add_text_box(s, Inches(0.5), Inches(0.7), Inches(6), Inches(3.5))
    p = tf.paragraphs[0]
    add_run(p, chapter, size=SIZE_WATERMARK, color=_T["watermark"], bold=True,
            font="Helvetica", purpose="watermark")
    tb, tf = add_text_box(s, Inches(0.7), Inches(4.0), Inches(12), Inches(1.2))
    add_text(tf, title, size=SIZE_TITLE_HERO, color=_T["primary"], bold=True,
             font=_T["head_font"])
    add_thin_accent_bar(s, Inches(0.7), Inches(5.1), Inches(0.8))
    tb, tf = add_text_box(s, Inches(0.7), Inches(5.4), Inches(12), Inches(1.3))
    add_text(tf, lead, size=SIZE_BODY_STANDARD, color=_T["text"])
    add_footer(s, page, topic_title)


def slide_background(prs, *, title, bullets, page, topic_title, subtitle=""):
    """Generic intro / background slide with bullet list."""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)
    y = Inches(1.55)
    if subtitle:
        tb, tf = add_text_box(s, Inches(0.6), y, Inches(12.2), Inches(0.45))
        add_text(tf, subtitle, size=SIZE_BODY_TIGHT, color=_T["text_light"], italic=True)
        y = Inches(2.05)
    tb, tf = add_text_box(s, Inches(0.8), y, Inches(11.8), Inches(5.0))
    for b in bullets:
        add_text(tf, "• " + b, size=SIZE_BODY_STANDARD, color=_T["text"])
    add_footer(s, page, topic_title)


def slide_paper_meta(prs, *, title, journal, year, authors_short, doi, pmid,
                     design, funding, main_finding, page, topic_title):
    """Paper metadata slide — journal club slide 3."""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, "Paper at a Glance")

    # big title block
    tb, tf = add_text_box(s, Inches(0.6), Inches(1.45), Inches(12.2), Inches(1.3))
    add_text(tf, title, size=SIZE_SUBTITLE, color=_T["primary"], bold=True,
             font=_T["head_font"])

    # citation line
    tb, tf = add_text_box(s, Inches(0.6), Inches(2.85), Inches(12.2), Inches(0.45))
    cite = f"{authors_short} · {journal} · {year}"
    add_text(tf, cite, size=SIZE_BODY_TIGHT, color=_T["accent"], italic=True)

    # 2x2 grid: design / funding / PMID / DOI
    grid_items = [
        ("Design", design),
        ("Funding", funding or "N/A"),
        ("PMID", pmid or "N/A"),
        ("DOI", doi or "N/A"),
    ]
    grid_x0 = Inches(0.6)
    grid_y0 = Inches(3.45)
    cell_w = Inches(6.0)
    cell_h = Inches(1.0)
    gap = Inches(0.15)
    for idx, (k, v) in enumerate(grid_items):
        r, c = idx // 2, idx % 2
        x = grid_x0 + c * (cell_w + gap)
        y = grid_y0 + r * (cell_h + gap)
        box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, cell_w, cell_h)
        box.fill.solid(); box.fill.fore_color.rgb = _T["card_bg"]
        box.line.color.rgb = _T["rule"]; box.line.width = Pt(0.5)
        tf = box.text_frame
        tf.margin_left = Inches(0.2); tf.margin_top = Inches(0.12)
        p = tf.paragraphs[0]
        add_run(p, k, size=SIZE_CAPTION, color=_T["accent"], bold=True,
                font=_T["head_font"], purpose="caption")
        p2 = tf.add_paragraph()
        add_run(p2, str(v), size=SIZE_BODY_TIGHT, color=_T["text"])

    # main finding callout
    cbox = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(5.75),
                               Inches(12.15), Inches(1.0))
    cbox.fill.solid(); cbox.fill.fore_color.rgb = _T["primary"]
    cbox.line.fill.background()
    tf = cbox.text_frame
    tf.margin_left = Inches(0.3); tf.margin_top = Inches(0.15)
    tf.word_wrap = True
    p = tf.paragraphs[0]
    add_run(p, "Main Finding", size=SIZE_CAPTION, color=_T["accent"], bold=True,
            font=_T["head_font"], purpose="caption")
    p2 = tf.add_paragraph()
    add_run(p2, main_finding, size=SIZE_BODY_TIGHT, color=WHITE)
    add_footer(s, page, topic_title)


def slide_pico(prs, *, population, intervention, comparator, outcome,
               secondary_outcomes, page, topic_title, title="PICO"):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)
    items = [
        ("P — Population", population),
        ("I — Intervention", intervention),
        ("C — Comparator", comparator),
        ("O — Primary Outcome", outcome),
    ]
    grid_x0 = Inches(0.6)
    grid_y0 = Inches(1.45)
    cell_w = Inches(6.0)
    cell_h = Inches(1.85)
    gap = Inches(0.15)
    for idx, (k, v) in enumerate(items):
        r, c = idx // 2, idx % 2
        x = grid_x0 + c * (cell_w + gap)
        y = grid_y0 + r * (cell_h + gap)
        box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, cell_w, cell_h)
        box.fill.solid(); box.fill.fore_color.rgb = _T["card_bg"]
        box.line.color.rgb = _T["rule"]; box.line.width = Pt(0.5)
        tf = box.text_frame
        tf.margin_left = Inches(0.2); tf.margin_top = Inches(0.15)
        tf.margin_right = Inches(0.2); tf.word_wrap = True
        p = tf.paragraphs[0]
        add_run(p, k, size=SIZE_BODY_TIGHT, color=_T["accent"], bold=True,
                font=_T["head_font"])
        p2 = tf.add_paragraph()
        add_run(p2, v, size=SIZE_BODY_TIGHT, color=_T["text"])

    if secondary_outcomes:
        tb, tf = add_text_box(s, Inches(0.6), Inches(5.4), Inches(12.15),
                               Inches(1.3))
        add_text(tf, "Secondary outcomes:", size=SIZE_BODY_TIGHT, color=_T["accent"],
                 bold=True, font=_T["head_font"])
        for so in secondary_outcomes:
            add_text(tf, "• " + so, size=SIZE_BODY_TIGHT, color=_T["text"])
    add_footer(s, page, topic_title)


def slide_methods(prs, *, design, n_total, key_inclusion, key_exclusion,
                  primary_endpoint, stats_method, follow_up, page, topic_title,
                  title="Methods"):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)

    items = [
        ("Design", design),
        ("Sample size (n)", str(n_total)),
        ("Primary endpoint", primary_endpoint),
        ("Statistical method", stats_method),
        ("Follow-up", follow_up),
    ]
    y = Inches(1.5)
    for k, v in items:
        tb, tf = add_text_box(s, Inches(0.6), y, Inches(12.2), Inches(0.45))
        p = tf.paragraphs[0]
        add_run(p, f"{k}: ", size=SIZE_BODY_TIGHT, color=_T["accent"], bold=True,
                font=_T["head_font"])
        add_run(p, v, size=SIZE_BODY_TIGHT, color=_T["text"])
        y += Inches(0.55)

    # inclusion / exclusion two-column
    y = Inches(4.4)
    tb, tf = add_text_box(s, Inches(0.6), y, Inches(6.0), Inches(0.4))
    add_text(tf, "Key inclusion", size=SIZE_BODY_TIGHT, color=_T["accent"], bold=True,
             font=_T["head_font"])
    tb, tf = add_text_box(s, Inches(0.6), y + Inches(0.4), Inches(6.0),
                           Inches(2.0))
    for it in key_inclusion:
        add_text(tf, "• " + it, size=SIZE_BODY_TIGHT, color=_T["text"])
    tb, tf = add_text_box(s, Inches(6.95), y, Inches(6.0), Inches(0.4))
    add_text(tf, "Key exclusion", size=SIZE_BODY_TIGHT, color=_T["accent"], bold=True,
             font=_T["head_font"])
    tb, tf = add_text_box(s, Inches(6.95), y + Inches(0.4), Inches(6.0),
                           Inches(2.0))
    for it in key_exclusion:
        add_text(tf, "• " + it, size=SIZE_BODY_TIGHT, color=_T["text"])
    add_footer(s, page, topic_title)


def slide_results(prs, *, title, key_numbers, figure_caption, page, topic_title):
    """key_numbers: list[dict{metric, value, ci, p}]"""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)

    # table-like key numbers — 4 columns, rows
    y = Inches(1.5)
    headers = ["Metric", "Value", "95% CI", "p"]
    col_w = [Inches(4.5), Inches(2.8), Inches(2.5), Inches(2.35)]
    col_x = [Inches(0.6)]
    for w in col_w[:-1]:
        col_x.append(col_x[-1] + w)

    # header row
    for i, h in enumerate(headers):
        tb, tf = add_text_box(s, col_x[i], y, col_w[i], Inches(0.4))
        add_text(tf, h, size=SIZE_BODY_TIGHT, color=_T["accent"], bold=True,
                 font=_T["head_font"])
    y += Inches(0.45)

    for kn in key_numbers:
        vals = [kn.get("metric", ""), kn.get("value", ""),
                kn.get("ci", ""), kn.get("p", "")]
        for i, v in enumerate(vals):
            tb, tf = add_text_box(s, col_x[i], y, col_w[i], Inches(0.5))
            add_text(tf, str(v), size=SIZE_BODY_TIGHT, color=_T["text"])
        y += Inches(0.5)
        if y > Inches(5.5):
            break

    if figure_caption:
        tb, tf = add_text_box(s, Inches(0.6), Inches(6.0), Inches(12.2),
                               Inches(0.8))
        add_text(tf, "Figure note: " + figure_caption, size=SIZE_CAPTION,
                 color=_T["text_light"], italic=True, purpose="caption")
    add_footer(s, page, topic_title)


def slide_case_profile(prs, *, age, sex, chief_complaint, underlying, tocc,
                       medication, page, topic_title, title="Case Profile"):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)

    cc_box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.45),
                                 Inches(12.15), Inches(1.2))
    cc_box.fill.solid(); cc_box.fill.fore_color.rgb = _T["primary"]
    cc_box.line.fill.background()
    tf = cc_box.text_frame
    tf.margin_left = Inches(0.3); tf.margin_top = Inches(0.18)
    tf.word_wrap = True
    p = tf.paragraphs[0]
    add_run(p, "Chief Complaint", size=SIZE_CAPTION, color=_T["accent"], bold=True,
            font=_T["head_font"], purpose="caption")
    p2 = tf.add_paragraph()
    add_run(p2, chief_complaint, size=SIZE_BODY_STANDARD, color=WHITE, bold=True)

    items = [
        ("Age / Sex", f"{age} y / {sex}"),
        ("Underlying", underlying or "None known"),
        ("TOCC", tocc or "N/A"),
        ("Current medication", medication or "N/A"),
    ]
    y = Inches(2.85)
    for k, v in items:
        tb, tf = add_text_box(s, Inches(0.6), y, Inches(12.2), Inches(0.85))
        p = tf.paragraphs[0]
        add_run(p, f"{k}: ", size=SIZE_BODY_TIGHT, color=_T["accent"], bold=True,
                font=_T["head_font"])
        add_run(p, v, size=SIZE_BODY_TIGHT, color=_T["text"])
        y += Inches(0.95)
    add_footer(s, page, topic_title)


def slide_case_timeline(prs, *, events, page, topic_title, title="Timeline"):
    """events = list[dict{date, event_en}]. Row height adapts to text length so
    long events get more room and the marker dot stays aligned with the first
    line of the event text."""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)

    n_ev = max(1, len(events))
    top_y = 1.55
    bottom_y = 7.05
    avail = bottom_y - top_y
    # Estimate lines per event based on text length (event column ≈ 9.3" wide,
    # ~95 chars per line at 13pt). Each event gets row_h proportional to its
    # text length, with a hard min so single-line events don't squeeze together
    # and break the timeline rhythm (visual dot mis-alignment).
    chars_per_line = 95
    line_units = []
    for ev in events:
        chars = len(ev.get("event_en", ""))
        lu = max(1, -(-chars // chars_per_line))
        line_units.append(lu)

    line_h = 0.30  # height per text line including small leading
    min_row_h = 0.85  # hard floor so dots stay evenly spaced

    desired = [max(min_row_h, lu * line_h + 0.35) for lu in line_units]
    total_desired = sum(desired)
    if total_desired > avail and total_desired > 0:
        scale = avail / total_desired
        # scale down but keep min floor (events with the longest text shrink
        # proportionally; single-line events stay at min_row_h)
        row_heights = [max(min_row_h * scale, d * scale) for d in desired]
    else:
        # extra slack distributed evenly
        slack = (avail - total_desired) / n_ev
        row_heights = [d + slack for d in desired]

    body_size = SIZE_BODY_TIGHT  # fixed at 14pt floor; was 13/11 in v1
    date_size = SIZE_BODY_TIGHT

    y = Inches(top_y)
    for ev, row_h_in in zip(events, row_heights):
        date = ev.get("date", "")
        etext = ev.get("event_en", "")
        row_h = Inches(row_h_in)
        # date column
        tb, tf = add_text_box(s, Inches(0.6), y, Inches(2.4), Inches(0.4))
        add_text(tf, date, size=date_size, color=_T["accent"], bold=True,
                 font=_T["head_font"])
        # dot — aligned with the vertical center of the first text line
        dot_size = 0.20
        first_line_center = 0.13  # ~half of 13pt line height
        dot = s.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(3.1),
            y + Inches(first_line_center - dot_size / 2),
            Inches(dot_size), Inches(dot_size),
        )
        dot.fill.solid(); dot.fill.fore_color.rgb = _T["primary"]
        dot.line.fill.background()
        # event text — height grows with line count
        text_h = max(0.45, row_h_in - 0.05)
        tb, tf = add_text_box(s, Inches(3.45), y - Inches(0.04), Inches(9.5),
                               Inches(text_h))
        tf.word_wrap = True
        add_text(tf, etext, size=body_size, color=_T["text"])
        y += row_h
    add_footer(s, page, topic_title)


def slide_case_findings(prs, *, pe, lab, image, path, page, topic_title,
                        title="Admission Findings"):
    """4-column or 3-column findings."""
    cols = []
    if pe:
        cols.append(("Physical Exam", pe))
    if lab:
        cols.append(("Lab", lab))
    if image:
        cols.append(("Imaging", image))
    if path:
        cols.append(("Pathology", path))
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)

    n_cols = len(cols)
    if n_cols == 0:
        return
    col_w = Inches((12.15 - 0.15 * (n_cols - 1)) / n_cols)
    start = Inches(0.6)
    gap = Inches(0.15)
    for i, (h, items) in enumerate(cols):
        x = start + i * (col_w + gap)
        band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, Inches(1.45), col_w,
                                   Inches(0.6))
        band.fill.solid(); band.fill.fore_color.rgb = _T["primary"]
        band.line.fill.background()
        tf = band.text_frame
        tf.margin_left = Inches(0.2); tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        add_run(p, h, size=SIZE_BODY_TIGHT, color=WHITE, bold=True, font=_T["head_font"])

        tb, tf = add_text_box(s, x, Inches(2.15), col_w, Inches(4.85))
        # v2: fixed at 14pt floor (was 11/12 conditional in v1).
        # If many items overflow, condense data instead of shrinking font.
        body_size = SIZE_BODY_TIGHT
        for b in items:
            # strip a single leading "- " so users can paste raw-markdown lists
            # without producing "• -" double-marker artifacts (slide-05 fix)
            clean = b.lstrip()
            if clean.startswith("- "):
                clean = clean[2:]
            add_text(tf, "• " + clean, size=body_size, color=_T["text"])
    add_footer(s, page, topic_title)


def slide_case_dx_mgmt(prs, *, active, underlying, orders, goals, page,
                       topic_title, title="Tentative Diagnosis & Management"):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)

    # 2x2
    items = [
        ("Active problems", active),
        ("Underlying", underlying),
        ("Orders / Plan", orders),
        ("Goals", goals),
    ]
    grid_x0 = Inches(0.6)
    grid_y0 = Inches(1.45)
    cell_w = Inches(6.0)
    cell_h = Inches(2.6)
    gap = Inches(0.15)
    for idx, (k, v) in enumerate(items):
        r, c = idx // 2, idx % 2
        x = grid_x0 + c * (cell_w + gap)
        y = grid_y0 + r * (cell_h + gap)
        box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, cell_w, cell_h)
        box.fill.solid(); box.fill.fore_color.rgb = _T["card_bg"]
        box.line.color.rgb = _T["rule"]; box.line.width = Pt(0.5)
        tf = box.text_frame
        tf.margin_left = Inches(0.2); tf.margin_top = Inches(0.15)
        tf.word_wrap = True
        p = tf.paragraphs[0]
        add_run(p, k, size=SIZE_BODY_TIGHT, color=_T["accent"], bold=True,
                font=_T["head_font"])
        if isinstance(v, list):
            it_size = SIZE_BODY_TIGHT  # v2 floor; condense data if it overflows
            for it in v:
                p2 = tf.add_paragraph()
                add_run(p2, "• " + it, size=it_size, color=_T["text"])
        else:
            p2 = tf.add_paragraph()
            add_run(p2, str(v), size=SIZE_BODY_TIGHT, color=_T["text"])
    add_footer(s, page, topic_title)


def slide_discussion_question(prs, *, q_num, q_text_en, suggested_minutes,
                              prompts_for_audience, page, topic_title):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    # header strip — banner bg uses _T["primary"]; for clinical_modern theme
    # accent == primary, so the small "Discussion · Q{n}" label was invisible
    # against the banner. Force WHITE for readability across all themes.
    add_rect(s, 0, 0, SLIDE_W, Inches(1.15), _T["primary"])
    tb, tf = add_text_box(s, Inches(0.6), Inches(0.18), Inches(5), Inches(0.32))
    add_text(tf, f"Discussion · Q{q_num}", size=SIZE_CAPTION, color=WHITE,
             font=_T["head_font"], purpose="caption")
    tb, tf = add_text_box(s, Inches(0.6), Inches(0.55), Inches(11.5),
                           Inches(0.55))
    add_text(tf, f"Question {q_num}", size=SIZE_SUBTITLE, color=WHITE, bold=True,
             font=_T["head_font"])

    # main question
    tb, tf = add_text_box(s, Inches(0.8), Inches(1.7), Inches(11.5), Inches(1.8))
    p = tf.paragraphs[0]
    add_run(p, f"Q{q_num}. ", size=SIZE_TITLE_STANDARD, color=_T["accent"], bold=True,
            font=_T["head_font"])
    add_run(p, q_text_en, size=SIZE_TITLE_STANDARD, color=_T["text"], font=_T["head_font"])

    # prompts for audience (smaller bullets, English)
    if prompts_for_audience:
        tb, tf = add_text_box(s, Inches(0.8), Inches(3.8), Inches(11.5),
                               Inches(2.5))
        add_text(tf, "Prompts for the floor:", size=SIZE_BODY_TIGHT, color=_T["accent"],
                 bold=True, font=_T["head_font"])
        for pr in prompts_for_audience:
            add_text(tf, "• " + pr, size=SIZE_BODY_TIGHT, color=_T["text"])

    # duration badge
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(9.5),
                              Inches(6.1), Inches(3.3), Inches(0.7))
    box.fill.solid(); box.fill.fore_color.rgb = _T["accent"]
    box.line.fill.background()
    tf = box.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Inches(0.2); tf.margin_right = Inches(0.2)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    add_run(p, f"Suggested  {suggested_minutes} min", size=SIZE_BODY_TIGHT, color=WHITE,
            bold=True, font=_T["head_font"])
    add_footer(s, page, topic_title)


def slide_literature_evidence(prs, *, q_num, evidence_summary_en, citations,
                              page, topic_title, title_prefix="Evidence"):
    """
    citations: list[dict{author_year, study_type, country, n, pmid, take_home}]
    Displays a summary paragraph at top, then a citation table below.

    Layout adapts to summary length and citation count so the table never
    overflows the slide. For long summaries the box grows; for many citations
    row height shrinks (and font drops to 10pt) so all rows fit.
    """
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, f"{title_prefix} · Q{q_num}")

    # ----- summary block: size adapts to text length -----
    sum_chars = len(evidence_summary_en or "")
    # 12.15" wide × 13pt ≈ ~110 chars/line; estimate lines (cap at 7)
    sum_lines = min(7, max(2, -(-sum_chars // 110)))
    sum_size = SIZE_BODY_TIGHT  # v2 floor; was 12/13 conditional
    sum_h_in = max(1.0, sum_lines * 0.24 + 0.15)
    sum_top = 1.45
    tb, tf = add_text_box(s, Inches(0.6), Inches(sum_top), Inches(12.15),
                           Inches(sum_h_in))
    tf.word_wrap = True
    add_text(tf, evidence_summary_en, size=sum_size, color=_T["text"])

    # ----- citation table — start right under summary -----
    table_top = sum_top + sum_h_in + 0.2
    # leave 0.2" buffer above footer divider so the last row never collides
    # with the page-number band (caught on slide-10 visual QA pre-patch)
    table_bottom = 6.85
    table_h = max(2.0, table_bottom - table_top)
    n_cit = max(1, len(citations))
    headers = ["Source", "Design", "Country", "n", "Take-home"]
    col_w = [Inches(1.9), Inches(1.9), Inches(1.1), Inches(0.7), Inches(6.55)]
    col_x = [Inches(0.6)]
    for w in col_w[:-1]:
        col_x.append(col_x[-1] + w)

    header_h = 0.42
    header_gap = 0.18  # bigger gap header→rule→body so first row never crowds
    rule_h_in = 0.04
    body_h = table_h - header_h - header_gap - rule_h_in
    # Goal: all citations fit. Take-home wraps to 2 lines for ≥80-char strings,
    # so row_h must accommodate 2 lines at the chosen body font.
    #   11pt: 2 lines + margin ≈ 0.46"
    #   10pt: 2 lines + margin ≈ 0.42"
    # Compute even share, then pick body font that fits.
    row_h_in_raw = body_h / n_cit
    row_h_in = max(0.42, min(0.85, row_h_in_raw))
    # v2: dense citation tables exempt for table_micro purpose; keep 11pt floor
    # because 14pt would force breaking the table or omitting columns.
    body_size = 12 if row_h_in >= 0.50 else 11
    header_size = SIZE_CAPTION

    y = Inches(table_top)
    for i, h in enumerate(headers):
        tb, tf = add_text_box(s, col_x[i], y, col_w[i], Inches(header_h))
        add_text(tf, h, size=header_size, color=_T["accent"], bold=True,
                 font=_T["head_font"], purpose="table_micro")
    y += Inches(header_h + header_gap - rule_h_in)

    rule = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), y,
                               Inches(12.1), Emu(4000))
    rule.fill.solid(); rule.fill.fore_color.rgb = _T["rule"]
    rule.line.fill.background()
    y += Inches(rule_h_in)

    row_h = Inches(row_h_in)
    table_bottom_emu = Inches(table_bottom)
    for c in citations:
        # break BEFORE drawing the row if it would extend past the footer
        # band (row 6 was rendering past the divider before this guard).
        if y + row_h > table_bottom_emu:
            break
        vals = [
            c.get("author_year", ""),
            c.get("study_type", ""),
            c.get("country", ""),
            str(c.get("n", "")),
            c.get("take_home", ""),
        ]
        for i, v in enumerate(vals):
            tb, tf = add_text_box(s, col_x[i], y, col_w[i], row_h)
            tf.word_wrap = True
            # table_micro exempt: dense citation rows where 14pt would force
            # column truncation or row breaks
            add_text(tf, str(v), size=body_size, color=_T["text"], purpose="table_micro")
        y += row_h
    add_footer(s, page, topic_title)


def slide_takeaway(prs, *, title, points, page, topic_title):
    """points = list of (heading, desc). Up to 3 numbered rows."""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)
    y = Inches(1.55)
    row_h = Inches(1.72)
    for i, (pt, desc) in enumerate(points, 1):
        numbox = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), y,
                                     Inches(1.2), row_h - Inches(0.1))
        numbox.fill.solid(); numbox.fill.fore_color.rgb = _T["primary"]
        numbox.line.fill.background()
        tfn = numbox.text_frame
        tfn.vertical_anchor = MSO_ANCHOR.MIDDLE
        tfn.paragraphs[0].alignment = PP_ALIGN.CENTER
        rr = tfn.paragraphs[0].add_run()
        rr.text = f"0{i}"; rr.font.size = Pt(34); rr.font.bold = True  # decorative number
        rr.font.color.rgb = _T["accent"]; rr.font.name = "Helvetica"
        body = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.85), y,
                                   Inches(10.9), row_h - Inches(0.1))
        body.fill.solid(); body.fill.fore_color.rgb = _T["card_bg"]
        body.line.color.rgb = _T["rule"]; body.line.width = Pt(0.5)
        tf = body.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE  # vertical centering
        tf.margin_left = Inches(0.3); tf.margin_right = Inches(0.3)
        tf.margin_top = Inches(0.18); tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT  # explicit; shape default is CENTER
        add_run(p, pt, size=SIZE_BODY_LARGE, color=_T["primary"], bold=True,
                font=_T["head_font"])
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.LEFT
        add_run(p2, desc, size=SIZE_BODY_STANDARD, color=_T["text"])
        y += row_h
    add_footer(s, page, topic_title)


def slide_references(prs, *, citations, page, topic_title,
                     title="References", style="vancouver"):
    """
    citations: list[dict] — output of refs_format.py or DATA literal.
    Each citation dict expected keys:
      full_author_list, title, journal, year, volume, pages, pmid, doi
    """
    from scripts.refs_format import format_citation  # lazy to avoid circular
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    slide_title(s, title)

    n = len(citations)
    # v2: dense reference list uses ref_micro exempt (10-12pt) since 14pt
    # would overflow even at 6 citations. Bibliographic refs are typically
    # printed at small size in published papers too.
    if n <= 6:
        size = 12
    elif n <= 9:
        size = 11
    else:
        size = 10

    tb, tf = add_text_box(s, Inches(0.6), Inches(1.5), Inches(12.2),
                           Inches(5.3))
    for i, c in enumerate(citations, 1):
        line = f"{i}. " + format_citation(c, style=style)
        add_text(tf, line, size=size, color=_T["text"], purpose="ref_micro")
    add_footer(s, page, topic_title)


def slide_blank_teacher(prs, page, topic_title,
                         closing_main="Open floor for comments",
                         closing_sub="— Thank you —"):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, _T["bg"])
    add_rect(s, 0, 0, SLIDE_W, Inches(1.5), _T["primary"])
    tb, tf = add_text_box(s, Inches(0.6), Inches(0.4), Inches(12), Inches(0.85))
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
    add_run(p, "Discussion / Q&A", size=SIZE_TITLE_STANDARD, color=WHITE, bold=True,
            font=_T["head_font"])
    add_run(p, "    Floor is open", size=SIZE_BODY_TIGHT, color=_T["accent"], italic=True)
    tb, tf = add_text_box(s, Inches(1.2), Inches(3.0), Inches(11), Inches(1.2))
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    add_run(p, closing_main, size=SIZE_BODY_LARGE, color=_T["text_light"],
            font=_T["head_font"])
    tb, tf = add_text_box(s, Inches(1.2), Inches(4.2), Inches(11), Inches(0.5))
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    add_run(p, closing_sub, size=SIZE_BODY_TIGHT, color=_T["accent"], italic=True,
            font=_T["head_font"])
    add_footer(s, page, topic_title)


# ---------- dispatch ----------

LAYOUTS = {
    "cover": slide_cover,
    "outline": slide_outline,
    "section_divider": slide_section_divider,
    "background": slide_background,
    "paper_meta": slide_paper_meta,
    "pico": slide_pico,
    "methods": slide_methods,
    "results": slide_results,
    "case_profile": slide_case_profile,
    "case_timeline": slide_case_timeline,
    "case_findings": slide_case_findings,
    "case_dx_mgmt": slide_case_dx_mgmt,
    "discussion_question": slide_discussion_question,
    "literature_evidence": slide_literature_evidence,
    "takeaway": slide_takeaway,
    "references": slide_references,
    "blank_teacher": slide_blank_teacher,
}


def new_presentation():
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs

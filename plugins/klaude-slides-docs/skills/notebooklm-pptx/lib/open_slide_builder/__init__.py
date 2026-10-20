"""
open_slide_builder — Shared infrastructure for emitting open-slide React decks
from a generic DATA dict. Consumed by per-skill builders (e.g. journal-club-discussion-pptx).

Consumer pattern:
    from open_slide_builder import build, COMMON_RENDERERS, _page_chrome, _bullet_jsx

    def render_paper_meta(cname, spec, theme): ...   # skill-specific
    def render_pico(cname, spec, theme): ...         # skill-specific

    if __name__ == "__main__":
        build(
            data=load_data(sys.argv[1]),
            output_parent=Path(sys.argv[2]),
            skill_renderers={
                "paper_meta": render_paper_meta,
                "pico": render_pico,
                # ... per-skill types
            },
            slide_id="journal-club",
        )

What this package provides:
    - 3 academic theme bundles (journal-classic / grand-rounds-warm /
      clinical-modern) in themes/, mapped from pptx names via
      PPTX_TO_OPEN_SLIDE_THEME.
    - COMMON_RENDERERS: built-in renderers for slide types every academic deck
      needs (cover / outline / section_divider / background / takeaway /
      blank_teacher / discussion_question). Skill renderers override these.
    - Pipeline helpers: scaffold_deck / copy_themes / cleanup_demo /
      verify_build (post-build TS strict pass).
    - Layout discipline (slide-authoring §, see the 11 pitfalls note below):
      SlideTransition presets RISE/SETTLE/BREATH at module level + per-page
      overrides; `var(--osd-*)` CSS vars for Design panel; explicit `<Bullet>`
      JSX instances via `_bullet_jsx`; vertical budget warner.
    - JSX utilities: js_string / jsx_text / slugify / load_data /
      _page_chrome / _bullet_jsx / _warn_vertical_budget.

This module is the canonical infrastructure for open-slide deck generation.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Theme bundles ────────────────────────────────────────────────────────────
# Mirror of templates/themes.py + open-slide-themes/<id>.md design tokens.
# Inlined here so the generated TSX is self-contained without runtime imports.

PPTX_TO_OPEN_SLIDE_THEME = {
    "journal_classic": "journal-classic",
    "grand_rounds_warm": "grand-rounds-warm",
    "clinical_modern": "clinical-modern",
}

THEMES: dict[str, dict[str, Any]] = {
    "journal-classic": {
        "name": "Journal Classic",
        "palette": {
            "bg": "#FFFFFF",
            "text": "#1A1A1A",
            "textSoft": "#5B5B5B",
            "accent": "#A51C30",
            "primary": "#1E3A5F",
            "cardBg": "#F8F8F8",
            "rule": "#CCCCCC",
            "watermark": "#ECECEC",
        },
        "fontDisplay": 'Georgia, "Source Serif Pro", "Times New Roman", serif',
        "fontBody": 'Georgia, "Source Serif Pro", "Times New Roman", serif',
        "fontMono": '"JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace',
        "design_hero": 132,
        "design_body": 32,
        "design_radius": 0,
        "padding_px": 120,
        "footer_left": "Journal Club",
        "footer_left_small_caps": True,
        "anim_prefix": "jc",
    },
    "grand-rounds-warm": {
        "name": "Grand Rounds Warm",
        "palette": {
            "bg": "#F5F1EA",
            "text": "#2B2318",
            "textSoft": "#6E5B43",
            "accent": "#8B1A1A",
            "accent2": "#B87333",
            "cardBg": "#FCFAF5",
            "rule": "#D9C8A9",
            "watermark": "#E8DFC8",
        },
        "fontDisplay": 'Georgia, "Source Serif Pro", "Times New Roman", serif',
        "fontBody": '"Calibri", "Open Sans", "Inter", system-ui, sans-serif',
        "fontMono": '"JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace',
        "design_hero": 144,
        "design_body": 32,
        "design_radius": 4,
        "padding_px": 120,
        "footer_left": "Grand Rounds",
        "footer_left_small_caps": True,
        "anim_prefix": "gr",
    },
    "clinical-modern": {
        "name": "Clinical Modern",
        "palette": {
            "bg": "#FAFAFA",
            "text": "#1A1A1A",
            "textSoft": "#595959",
            "accent": "#C0392B",
            "primary": "#0E5E6F",
            "primarySoft": "#4A8C99",
            "cardBg": "#FFFFFF",
            "rule": "#E5E5E5",
            "watermark": "#EEEEEE",
        },
        "fontDisplay": '"Calibri", "Open Sans", "Inter", system-ui, sans-serif',
        "fontBody": '"Calibri", "Open Sans", "Inter", system-ui, sans-serif',
        "fontMono": '"JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace',
        "design_hero": 128,
        "design_body": 30,
        "design_radius": 8,
        "padding_px": 96,
        "footer_left": "Clinical Update · 2026",
        "footer_left_small_caps": False,  # already uppercased via CSS
        "anim_prefix": "cm",
    },
}

THEME_BUNDLE_DIR = Path(__file__).resolve().parent / "themes"


# ─── Utilities ────────────────────────────────────────────────────────────────


def load_data(data_path: str) -> dict:
    spec = importlib.util.spec_from_file_location("jc_data", data_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "DATA"):
        raise ValueError(f"{data_path} must define a module-level DATA dict")
    return mod.DATA


def slugify(s: str, fallback: str = "journal-club") -> str:
    if not s:
        return fallback
    s = s.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    s = re.sub(r"-+", "-", s)
    return s[:50] or fallback


def js_string(s: Any) -> str:
    """Quote any Python value as a safe JS string literal (single quotes,
    escaped backslash/quote/newline). Used everywhere we inject user data into
    JSX text or string-typed JS values."""
    if s is None:
        return "''"
    text = str(s)
    text = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{text}'"


def jsx_text(s: Any) -> str:
    """Escape user text for safe insertion inside JSX text nodes ({} / < / > /
    & / curly quotes left intact for typography)."""
    if s is None:
        return ""
    text = str(s)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("{", "&#123;")
        .replace("}", "&#125;")
    )


# ─── TSX fragments ────────────────────────────────────────────────────────────


def render_preamble(theme: dict, deck_title: str, created_at_iso: str, theme_id: str) -> str:
    p = theme["palette"]
    palette_lines = ",\n  ".join(f"{k}: '{v}'" for k, v in p.items())
    return f"""import {{ type Page, type SlideMeta, type DesignSystem, type SlideTransition, useSlidePageNumber, ImagePlaceholder }} from '@open-slide/core';

export const meta: SlideMeta = {{
  title: {js_string(deck_title)},
  theme: '{theme_id}',
  createdAt: '{created_at_iso}',
}};

// Design panel reads this — bg / text / accent + 2 fonts + 2 sizes + radius are
// the panel-tweakable tokens (slide-authoring §Design system). Use `var(--osd-*)`
// in inline styles below so the panel sliders update live without HMR.
export const design: DesignSystem = {{
  palette: {{
    bg: '{p["bg"]}',
    text: '{p["text"]}',
    accent: '{p["accent"]}',
  }},
  fonts: {{
    display: {js_string(theme["fontDisplay"])},
    body: {js_string(theme["fontBody"])},
  }},
  typeScale: {{
    hero: {theme["design_hero"]},
    body: {theme["design_body"]},
  }},
  radius: {theme["design_radius"]},
}};

// Non-tweakable secondary colors stay as plain consts (per slide-authoring rule
// "anything outside DesignSystem belongs as plain hard-coded constants").
const palette = {{
  {palette_lines},
}};

const fontMono = {js_string(theme["fontMono"])};
const PADDING = {theme["padding_px"]};
// Bottom reserve above PADDING for the absolute-positioned Footer (bottom:60 +
// ~24px text + visual buffer). _page_chrome adds this to paddingBottom so
// flex:1 body Cards never clip into the footer line.
const FOOTER_RESERVE = 100;

// ─── SlideTransition presets (slide-authoring §Page transitions) ─────────────
// "One DNA, hold across deck" — same duration band, same easing pair, same
// stagger. Module default = RISE; Cover / Take-home override to SETTLE; section
// dividers override to BREATH. Per-element animationDelay / fadeUp removed —
// page transitions handle entry consistently.
const EASE_OUT = 'cubic-bezier(0, 0, 0.2, 1)';
const EASE_IN = 'cubic-bezier(0.4, 0, 1, 1)';

const RISE: SlideTransition = {{
  duration: 200,
  exit: {{ duration: 140, easing: EASE_IN, keyframes: [
    {{ opacity: 1, transform: 'translateY(0)' }},
    {{ opacity: 0, transform: 'translateY(-4px)' }},
  ]}},
  enter: {{ duration: 200, delay: 80, easing: EASE_OUT, keyframes: [
    {{ opacity: 0, transform: 'translateY(6px)' }},
    {{ opacity: 1, transform: 'translateY(0)' }},
  ]}},
}};

const SETTLE: SlideTransition = {{
  duration: 280,
  exit: {{ duration: 160, easing: EASE_IN, keyframes: [
    {{ opacity: 1, transform: 'translateY(0)' }},
    {{ opacity: 0, transform: 'translateY(-6px)' }},
  ]}},
  enter: {{ duration: 280, delay: 100, easing: EASE_OUT, keyframes: [
    {{ opacity: 0, transform: 'translateY(12px)', filter: 'blur(4px)' }},
    {{ opacity: 1, transform: 'translateY(0)', filter: 'blur(0)' }},
  ]}},
}};

const BREATH: SlideTransition = {{
  duration: 460,
  exit: {{ duration: 180, easing: EASE_IN, keyframes: [{{ opacity: 1 }}, {{ opacity: 0 }}] }},
  enter: {{ duration: 240, delay: 300, easing: EASE_OUT, keyframes: [
    {{ opacity: 0, transform: 'translateY(8px)' }},
    {{ opacity: 1, transform: 'translateY(0)' }},
  ]}},
}};

export const transition: SlideTransition = RISE;

// ─── Shared styles (use var(--osd-*) for Design panel live updates) ──────────
const fill: React.CSSProperties = {{
  width: '100%',
  height: '100%',
  background: 'var(--osd-bg)',
  color: 'var(--osd-text)',
  fontFamily: 'var(--osd-font-body)',
  position: 'relative',
}};

const Title = ({{ children, style }}: {{ children: React.ReactNode; style?: React.CSSProperties }}) => (
  <h1
    style={{{{
      fontFamily: 'var(--osd-font-display)',
      fontSize: 'var(--osd-size-hero)',
      fontWeight: 600,
      lineHeight: 1.05,
      letterSpacing: '-0.015em',
      margin: 0,
      color: 'var(--osd-text)',
      ...style,
    }}}}
  >
    {{children}}
  </h1>
);

const SectionTitle = ({{ children, style }}: {{ children: React.ReactNode; style?: React.CSSProperties }}) => (
  <h2
    style={{{{
      fontFamily: 'var(--osd-font-display)',
      fontSize: 84,
      fontWeight: 600,
      lineHeight: 1.1,
      letterSpacing: '-0.015em',
      margin: 0,
      color: 'var(--osd-text)',
      ...style,
    }}}}
  >
    {{children}}
  </h2>
);

const Eyebrow = ({{ children, style }}: {{ children: React.ReactNode; style?: React.CSSProperties }}) => (
  <div
    style={{{{
      fontFamily: 'var(--osd-font-display)',
      fontSize: 24,
      letterSpacing: '0.22em',
      textTransform: 'uppercase',
      color: 'var(--osd-accent)',
      fontWeight: 600,
      ...style,
    }}}}
  >
    {{children}}
  </div>
);

const Footer = ({{ topicTitle }}: {{ topicTitle?: string }}) => {{
  const {{ current, total }} = useSlidePageNumber();
  return (
    <div
      style={{{{
        position: 'absolute',
        left: PADDING,
        right: PADDING,
        bottom: 60,
        display: 'flex',
        justifyContent: 'space-between',
        fontFamily: 'var(--osd-font-body)',
        fontSize: 22,
        color: palette.textSoft,
        letterSpacing: '0.04em',
      }}}}
    >
      <span style={{{{ fontVariant: {js_string("small-caps" if theme["footer_left_small_caps"] else "normal")} }}}}>
        {{topicTitle || {js_string(theme["footer_left"])}}}
      </span>
      <span style={{{{ fontFamily: fontMono }}}}>{{current}} / {{total}}</span>
    </div>
  );
}};

// Bullet = single explicit instance. Builder emits per-item <Bullet>... so the
// inspector can edit each bullet independently (slide-authoring §Repeated
// elements: never use array.map for visually-repeated items).
const Bullet = ({{ children }}: {{ children: React.ReactNode }}) => (
  <li style={{{{ display: 'flex', gap: 14, alignItems: 'baseline', fontSize: 26, lineHeight: 1.5, color: 'var(--osd-text)' }}}}>
    <span style={{{{ color: 'var(--osd-accent)', fontSize: 22, lineHeight: 1.5 }}}}>▸</span>
    <span>{{children}}</span>
  </li>
);

const BulletList = ({{ children, style }}: {{ children: React.ReactNode; style?: React.CSSProperties }}) => (
  <ul style={{{{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 12, ...style }}}}>
    {{children}}
  </ul>
);

const Card = ({{ children, style }}: {{ children: React.ReactNode; style?: React.CSSProperties }}) => (
  <div
    style={{{{
      background: palette.cardBg,
      border: `1px solid ${{palette.rule}}`,
      borderRadius: 'var(--osd-radius)',
      padding: '24px 32px',
      ...style,
    }}}}
  >
    {{children}}
  </div>
);

const KV = ({{ k, v }}: {{ k: string; v: string }}) => (
  <div style={{{{ display: 'flex', gap: 16, marginBottom: 10, fontSize: 24, lineHeight: 1.45 }}}}>
    <span style={{{{ minWidth: 200, color: palette.textSoft, fontWeight: 500 }}}}>{{k}}</span>
    <span style={{{{ flex: 1, color: 'var(--osd-text)' }}}}>{{v}}</span>
  </div>
);

const TOPIC_TITLE = TOPIC_TITLE_LITERAL;
"""


# ─── Per-slide renderers ──────────────────────────────────────────────────────


def _safe(s: Any, default: str = "") -> str:
    return jsx_text(s if s is not None else default)


def _str(s: Any, default: str = "") -> str:
    return s if isinstance(s, str) and s else default


def _warn_vertical_budget(stype: str, idx: int, spec: dict) -> None:
    """Per-type rough vertical-budget check. Estimates body height in canvas px
    for the most-likely-to-overflow slide types and prints a stderr warning if
    > 800px (out of ~780-800 body budget after header / footer / padding).

    Conservative estimates — better to warn-and-let-through than to over-strict.
    Per slide-authoring official guidance, splitting is the proper fix for
    overflow; this warner gives the user a heads-up to consider splitting."""
    est = 0
    if stype == "background":
        bullets = spec.get("bullets", []) or []
        # Each bullet ~ 39 + 12 gap; subtitle ~ 60 if present; card padding 48
        est = 48 + len(bullets) * 51 + (60 if spec.get("subtitle") else 0)
    elif stype == "methods":
        incl_n = len(spec.get("key_inclusion", []) or [])
        excl_n = len(spec.get("key_exclusion", []) or [])
        kv_n = sum(1 for k in ("design", "n_total", "primary_endpoint", "stats_method", "follow_up") if spec.get(k))
        # Right column = (header+pad) + bullets*51 — taller of incl/excl decides
        right_card_h = lambda n: 48 + 38 + n * 51
        est = max(48 + kv_n * 45, right_card_h(incl_n) + 16 + right_card_h(excl_n))
    elif stype == "results":
        n = len(spec.get("key_numbers", []) or [])
        est = 48 + 56 + n * 52 + (90 if spec.get("figure_caption") else 0)
    elif stype == "literature_evidence":
        n = len(spec.get("citations", []) or [])
        est = 100 + 48 + 38 + n * 50  # summary + card + header + rows
    elif stype == "references":
        n = len(spec.get("citations", []) or [])
        font = 18 if n >= 10 else (20 if n >= 7 else 22)
        est = n * int(font * 1.45 + 10)
    elif stype == "case_findings":
        max_col = max(len(spec.get(k, []) or []) for k in ("pe", "lab", "image", "path"))
        est = 48 + 38 + max_col * 51
    elif stype == "case_dx_mgmt":
        # 2x2 grid — row height = max(top 2 quadrants); total = 2 rows + gap
        row_h = lambda q1, q2: max(48 + 38 + len(q1) * 51, 48 + 38 + len(q2) * 51)
        active = spec.get("active", []) or []
        underlying = spec.get("underlying", []) or []
        orders = spec.get("orders", []) or []
        goals = spec.get("goals", []) or []
        est = row_h(active, underlying) + 20 + row_h(orders, goals)
    else:
        return  # No estimator for this type

    if est > 800:
        print(
            f"[budget WARNING] slide {idx} ({stype}): estimated body height {est}px exceeds "
            f"~800px budget — content may clip into footer. Consider splitting into two slides "
            f"(per slide-authoring §'Splitting is always the right answer when budget is tight').",
            file=sys.stderr,
        )


def _bullet_jsx(items: list, indent: str = "          ") -> str:
    """Emit explicit `<BulletList><Bullet>x</Bullet><Bullet>y</Bullet></BulletList>`
    JSX — one Bullet element per item. Per slide-authoring §Repeated elements,
    inspector edits source JSX in place; an array.map body shares one source
    location across all rendered items, so editing one bullet would mutate all.
    Explicit-instance JSX gives each bullet its own editable node."""
    if not items:
        return f"{indent}<BulletList />"
    bullets = "\n".join(f"{indent}  <Bullet>{jsx_text(x)}</Bullet>" for x in items)
    return f"{indent}<BulletList>\n{bullets}\n{indent}</BulletList>"


def render_cover_simple(component_name: str, cover_data: dict, theme: dict) -> str:
    """Cover slide. 2-column grid when big_word is set (left=text / right=big
    word stack), else single column centered. No more absolute-positioned big
    word that overlaps the title."""
    label = jsx_text(cover_data.get("label", "Journal Club"))
    title_lines = _str(cover_data.get("title", "")).split("\n")
    subtitle = jsx_text(cover_data.get("subtitle", ""))
    big1 = jsx_text(cover_data.get("big_word_primary", ""))
    big2 = jsx_text(cover_data.get("big_word_accent", ""))
    caption = jsx_text(cover_data.get("caption_en", ""))
    caption_sub = jsx_text(cover_data.get("caption_sub", ""))
    presenter = jsx_text(cover_data.get("presenter", ""))
    date = jsx_text(cover_data.get("date", ""))
    course = jsx_text(cover_data.get("course_tag", ""))

    title_jsx_inner = ""
    for i, ln in enumerate(title_lines):
        title_jsx_inner += jsx_text(ln)
        if i < len(title_lines) - 1:
            title_jsx_inner += "<br />"

    has_big = bool(big1 or big2)
    grid_template = "'1.7fr 1fr'" if has_big else "'1fr'"
    # Reduce hero font on cover to keep title to 2-3 lines in the narrower left
    # column (theme hero is sized for full-width content slides).
    title_size_px = 96 if has_big else 124

    course_chip = ""
    if course:
        course_chip = (
            "          <span style={{ margin: '0 16px', opacity: 0.5 }}>·</span>\n"
            f"          <span>{course}</span>\n"
        )

    # Big word block scaled to fit ~700px column at fontSize 200 with weight 700
    big_block = ""
    if has_big:
        big_block = (
            f"""      <div style={{{{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'flex-end', minWidth: 0, fontFamily: 'var(--osd-font-display)', fontWeight: 700, lineHeight: 0.92, letterSpacing: '-0.04em', textAlign: 'right' }}}}>
        <div style={{{{ fontSize: 200, color: 'var(--osd-text)', opacity: 0.92 }}}}>{big1}</div>
        <div style={{{{ fontSize: 200, color: 'var(--osd-accent)' }}}}>{big2}</div>
      </div>"""
        )

    return f"""const {component_name}: Page = () => (
  <div style={{fill}}>
    <div style={{{{ position: 'absolute', inset: 0, padding: PADDING, display: 'grid', gridTemplateColumns: {grid_template}, gap: 48, alignItems: 'center' }}}}>
      <div style={{{{ display: 'flex', flexDirection: 'column', justifyContent: 'center', minWidth: 0 }}}}>
        <div>
          <Eyebrow>{label}</Eyebrow>
        </div>
        <div style={{{{ marginTop: 24 }}}}>
          <Title style={{{{ fontSize: {title_size_px}, lineHeight: 1.08 }}}}>{title_jsx_inner}</Title>
        </div>
        <p style={{{{ fontFamily: 'var(--osd-font-body)', fontSize: 36, color: palette.textSoft, marginTop: 32, lineHeight: 1.4 }}}}>
          {subtitle}
        </p>
        <div style={{{{ marginTop: 40, fontFamily: 'var(--osd-font-body)', fontSize: 28, color: palette.textSoft }}}}>
          <div>{caption}</div>
          <div style={{{{ fontStyle: 'italic', marginTop: 6 }}}}>{caption_sub}</div>
        </div>
        <div style={{{{ marginTop: 48, fontFamily: fontMono, fontSize: 24, color: palette.textSoft }}}}>
          <span>{presenter}</span>
          <span style={{{{ margin: '0 16px', opacity: 0.5 }}}}>·</span>
          <span>{date}</span>
{course_chip}        </div>
      </div>
{big_block}
    </div>
  </div>
);
"""


def _page_chrome(body_jsx: str, header_eyebrow: str = "", header_title: str = "") -> str:
    """Generic content slide wrapper: Eyebrow + SectionTitle + body.

    Footer is absolutely positioned at `bottom: 60` from canvas edge with body
    text ~22px, occupying roughly bottom 100px. To prevent any body Card / table
    border from clipping into the Footer line, outer container reserves an
    extra `FOOTER_RESERVE` (60px) of padding on top of the standard PADDING.
    Total padding-bottom = PADDING + FOOTER_RESERVE.
    """
    header_block = ""
    if header_eyebrow or header_title:
        header_block = (
            f"      <div>\n"
            + (f"        <Eyebrow>{jsx_text(header_eyebrow)}</Eyebrow>\n" if header_eyebrow else "")
            + (f"        <SectionTitle style={{{{ marginTop: 20 }}}}>{jsx_text(header_title)}</SectionTitle>\n" if header_title else "")
            + "      </div>\n"
        )
    return f"""  <div style={{fill}}>
    <div style={{{{ position: 'absolute', inset: 0, paddingTop: PADDING, paddingLeft: PADDING, paddingRight: PADDING, paddingBottom: PADDING + FOOTER_RESERVE, display: 'flex', flexDirection: 'column', gap: 28 }}}}>
{header_block}      <div style={{{{ flex: 1, minHeight: 0 }}}}>
{body_jsx}
      </div>
    </div>
    <Footer topicTitle={{TOPIC_TITLE}} />
  </div>"""


def render_outline(component_name: str, items: list[tuple], theme: dict) -> str:
    rows = ""
    for tup in items:
        # tup = (num, title, meta, desc)
        num, ttl, mt, desc = (tup + ("",) * 4)[:4]
        rows += (
            f"          <div style={{{{ display: 'grid', gridTemplateColumns: '64px 1fr 120px', gap: 24, padding: '20px 0', borderTop: `1px solid ${{palette.rule}}` }}}}>\n"
            f"            <div style={{{{ fontFamily: fontMono, fontSize: 28, color: 'var(--osd-accent)' }}}}>{jsx_text(num)}</div>\n"
            f"            <div>\n"
            f"              <div style={{{{ fontSize: 32, fontWeight: 600, color: 'var(--osd-text)' }}}}>{jsx_text(ttl)}</div>\n"
            f"              <div style={{{{ fontSize: 22, color: palette.textSoft, marginTop: 4 }}}}>{jsx_text(desc)}</div>\n"
            f"            </div>\n"
            f"            <div style={{{{ fontFamily: fontMono, fontSize: 22, color: palette.textSoft, textAlign: 'right' }}}}>{jsx_text(mt)}</div>\n"
            f"          </div>\n"
        )
    body = f'        <div style={{{{ marginTop: 8 }}}}>\n{rows}        </div>'
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='Outline')}\n);\n"


def render_section_divider(component_name: str, spec: dict, theme: dict) -> str:
    chapter = jsx_text(spec.get("chapter", ""))
    title = jsx_text(spec.get("title", ""))
    lead = jsx_text(spec.get("lead", ""))
    return f"""const {component_name}: Page = () => (
  <div style={{fill}}>
    <div style={{{{ position: 'absolute', right: PADDING, top: PADDING, fontFamily: 'var(--osd-font-display)', fontSize: 420, fontWeight: 700, color: palette.watermark, lineHeight: 1, pointerEvents: 'none' }}}}>
      {chapter}
    </div>
    <div style={{{{ position: 'absolute', inset: 0, padding: PADDING, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}}}>
      <div>
        <Eyebrow>Chapter {chapter}</Eyebrow>
      </div>
      <Title style={{{{ marginTop: 24, fontSize: 156 }}}}>{title}</Title>
      <p style={{{{ marginTop: 32, fontFamily: 'var(--osd-font-body)', fontSize: 36, color: palette.textSoft, maxWidth: 1400, lineHeight: 1.45 }}}}>
        {lead}
      </p>
    </div>
    <Footer topicTitle={{TOPIC_TITLE}} />
  </div>
);
"""


def render_background(component_name: str, spec: dict, theme: dict) -> str:
    title = spec.get("title", "Background")
    subtitle = spec.get("subtitle", "")
    bullets = spec.get("bullets", []) or []
    body = _bullet_jsx(bullets, indent="        ")
    if subtitle:
        body = f'        <div style={{{{ fontStyle: "italic", color: palette.textSoft, fontSize: 28, marginBottom: 24 }}}}>{jsx_text(subtitle)}</div>\n{body}'
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_title=title)}\n);\n"




def render_case_profile(component_name: str, spec: dict, theme: dict) -> str:
    rows = [
        ("Age / Sex", f'{spec.get("age","")} / {spec.get("sex","")}'),
        ("Chief complaint", spec.get("chief_complaint", "")),
        ("Underlying", spec.get("underlying", "")),
        ("TOCC", spec.get("tocc", "")),
        ("Medication", spec.get("medication", "")),
    ]
    kv_block = "\n".join(
        f"          <KV k={{{js_string(k)}}} v={{{js_string(v)}}} />"
        for k, v in rows if v and v != " / "
    )
    body = f"""        <Card style={{{{ flex: 1 }}}}>\n{kv_block}\n        </Card>"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='Patient', header_title='Case Profile')}\n);\n"


def render_case_timeline(component_name: str, spec: dict, theme: dict) -> str:
    events = spec.get("events", []) or []
    rows = ""
    for ev in events:
        rows += (
            "            <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: 24, padding: '14px 0', borderTop: `1px solid ${palette.rule}` }}>\n"
            f"              <div style={{{{ fontFamily: fontMono, fontSize: 22, color: 'var(--osd-accent)' }}}}>{jsx_text(ev.get('date',''))}</div>\n"
            f"              <div style={{{{ fontSize: 26, lineHeight: 1.5, color: 'var(--osd-text)' }}}}>{jsx_text(ev.get('event_en',''))}</div>\n"
            "            </div>\n"
        )
    body = f"""        <Card style={{{{ flex: 1 }}}}>\n{rows}        </Card>"""
    title = spec.get("title", "Timeline")
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='Course', header_title=title)}\n);\n"


def render_case_findings(component_name: str, spec: dict, theme: dict) -> str:
    cols = []
    for label_key, label_name in [("pe", "Physical Exam"), ("lab", "Laboratory"), ("image", "Imaging"), ("path", "Pathology")]:
        items = spec.get(label_key, []) or []
        if not items:
            continue
        bullet_jsx = _bullet_jsx(items, indent="            ")
        cols.append(
            f"          <Card>\n"
            f"            <div style={{{{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}}}>{jsx_text(label_name)}</div>\n"
            f"{bullet_jsx}\n"
            f"          </Card>"
        )
    n = len(cols)
    if n == 0:
        return render_background(component_name, {"title": "Findings", "bullets": ["No findings recorded."]}, theme)
    grid_cols = {1: "1fr", 2: "1fr 1fr", 3: "1fr 1fr 1fr", 4: "1fr 1fr 1fr 1fr"}[n]
    cols_jsx = "\n".join(cols)
    body = f"""        <div style={{{{ display: "grid", gridTemplateColumns: "{grid_cols}", gap: 20, flex: 1 }}}}>
{cols_jsx}
        </div>"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='Findings', header_title='Clinical Findings')}\n);\n"


def render_case_dx_mgmt(component_name: str, spec: dict, theme: dict) -> str:
    quadrants = [
        ("Active Problems", spec.get("active", []) or []),
        ("Underlying", spec.get("underlying", []) or []),
        ("Orders", spec.get("orders", []) or []),
        ("Goals", spec.get("goals", []) or []),
    ]
    cells = ""
    for label, items in quadrants:
        bullet_jsx = _bullet_jsx(items, indent="            ")
        cells += (
            f"          <Card>\n"
            f"            <div style={{{{ fontFamily: fontMono, fontSize: 18, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--osd-accent)', marginBottom: 10 }}}}>{jsx_text(label)}</div>\n"
            f"{bullet_jsx}\n"
            f"          </Card>\n"
        )
    body = f"""        <div style={{{{ display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 20, flex: 1 }}}}>
{cells}        </div>"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='Plan', header_title='Diagnosis & Management')}\n);\n"


def render_discussion_question(component_name: str, spec: dict, theme: dict) -> str:
    q_num = spec.get("q_num", "")
    q_text = jsx_text(spec.get("q_text_en", ""))
    minutes = spec.get("suggested_minutes", "")
    prompts = spec.get("prompts_for_audience", []) or []
    prompts_jsx = _bullet_jsx(prompts, indent="            ")
    minutes_block = ""
    if minutes:
        minutes_block = (
            f'        <div style={{{{ marginTop: 16, fontFamily: fontMono, fontSize: 22, color: palette.textSoft }}}}>\n'
            f"          Suggested time: {minutes} min\n"
            "        </div>\n"
        )
    body = f"""        <div style={{{{ display: "flex", flexDirection: "column", justifyContent: "center", flex: 1 }}}}>
          <SectionTitle style={{{{ fontSize: 64, lineHeight: 1.15 }}}}>{q_text}</SectionTitle>
{minutes_block}          <div style={{{{ marginTop: 32 }}}}>
            <div style={{{{ fontFamily: fontMono, fontSize: 18, letterSpacing: "0.12em", textTransform: "uppercase", color: 'var(--osd-accent)', marginBottom: 12 }}}}>Prompts for Audience</div>
{prompts_jsx}
          </div>
        </div>"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow=f'Discussion · Q{q_num}')}\n);\n"



def render_takeaway(component_name: str, spec: dict, theme: dict) -> str:
    title = spec.get("title", "Clinical Takeaways")
    points = spec.get("points", []) or []
    rows = ""
    for i, p in enumerate(points):
        head, desc = (p + ("",) * 2)[:2] if isinstance(p, (list, tuple)) else (str(p), "")
        rows += (
            "          <div style={{ display: 'grid', gridTemplateColumns: '64px 1fr', gap: 24, alignItems: 'baseline' }}>\n"
            f"            <div style={{{{ fontFamily: fontMono, fontSize: 36, fontWeight: 700, color: 'var(--osd-accent)' }}}}>0{i+1}</div>\n"
            f"            <div>\n"
            f"              <div style={{{{ fontSize: 36, fontWeight: 600, color: 'var(--osd-text)' }}}}>{jsx_text(head)}</div>\n"
            f"              <div style={{{{ fontSize: 26, color: palette.textSoft, marginTop: 6, lineHeight: 1.5 }}}}>{jsx_text(desc)}</div>\n"
            "            </div>\n"
            "          </div>\n"
        )
    body = f"""        <div style={{{{ display: "flex", flexDirection: "column", gap: 32, justifyContent: "center", flex: 1 }}}}>
{rows}        </div>"""
    return f"const {component_name}: Page = () => (\n{_page_chrome(body, header_eyebrow='Take-home', header_title=title)}\n);\n"



def render_blank_teacher(component_name: str, spec: dict, theme: dict) -> str:
    main = jsx_text(spec.get("closing_main", "Floor is open"))
    sub = jsx_text(spec.get("closing_sub", "— Thank you —"))
    return f"""const {component_name}: Page = () => (
  <div style={{fill}}>
    <div style={{{{ position: 'absolute', inset: 0, padding: PADDING, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center' }}}}>
      <Title style={{{{ fontSize: 120, color: 'var(--osd-accent)' }}}}>{main}</Title>
      <div style={{{{ marginTop: 48, fontFamily: 'var(--osd-font-body)', fontSize: 36, fontStyle: 'italic', color: palette.textSoft }}}}>
        {sub}
      </div>
    </div>
    <Footer topicTitle={{TOPIC_TITLE}} />
  </div>
);
"""


# Map slide type → renderer. Skill-specific renderers (e.g. paper_meta, pico
# for journal-club-discussion-pptx) merge in via build()'s `skill_renderers` arg and OVERRIDE
# matching keys here (use case: skill wants custom case_findings layout).
COMMON_RENDERERS = {
    "outline": render_outline,
    "section_divider": render_section_divider,
    "background": render_background,
    "case_profile": render_case_profile,
    "case_timeline": render_case_timeline,
    "case_findings": render_case_findings,
    "case_dx_mgmt": render_case_dx_mgmt,
    "discussion_question": render_discussion_question,
    "takeaway": render_takeaway,
    "blank_teacher": render_blank_teacher,
}


# ─── Builder orchestrator ─────────────────────────────────────────────────────


def render_deck(
    data: dict,
    deck_dir: Path,
    slide_id: str,
    skill_renderers: dict | None = None,
) -> None:
    """Render the full slides/<slide_id>/index.tsx from DATA.

    Args:
        data: DATA dict (meta, cover, outline_items, slides).
        deck_dir: Path to scaffolded open-slide deck root.
        slide_id: kebab-case folder name under slides/ (e.g. 'journal-club').
        skill_renderers: per-skill renderer dict (e.g. {"paper_meta": ...}).
            Merged with COMMON_RENDERERS — skill overrides common on conflict.
    """
    meta = data.get("meta", {})
    pptx_theme = meta.get("theme", "journal_classic")
    theme_id = PPTX_TO_OPEN_SLIDE_THEME.get(pptx_theme, "journal-classic")
    theme = THEMES[theme_id]
    topic_title = meta.get("topic_title", "Journal Club Discussion")

    cover = data.get("cover", {})
    outline_items = data.get("outline_items", [])
    slides = data.get("slides", [])

    renderers = {**COMMON_RENDERERS, **(skill_renderers or {})}

    components: list[str] = []
    component_names: list[str] = []
    notes_list: list[str | None] = []
    transition_overrides: list[str] = []
    # Per slide-authoring §Page transitions:
    #   cover / take-home → SETTLE (heavier, blur on enter, 280ms)
    #   section_divider / blank_teacher → BREATH (full fade between chapters)
    #   everything else → RISE (module default, 200ms / 6px Y)
    TRANSITION_BY_TYPE = {
        "cover": "SETTLE",
        "takeaway": "SETTLE",
        "section_divider": "BREATH",
        "blank_teacher": "BREATH",
    }

    for i, spec in enumerate(slides):
        stype = spec["type"]
        cname = f"Slide{i+1}"
        component_names.append(cname)

        if stype == "cover":
            components.append(render_cover_simple(cname, cover, theme))
        elif stype == "outline":
            components.append(render_outline(cname, outline_items, theme))
        elif stype in renderers:
            components.append(renderers[stype](cname, spec, theme))
        else:
            print(
                f"[warning] slide {i+1}: unknown type '{stype}' — fallback to background bullet list. "
                f"Add a renderer for this type to skill_renderers or COMMON_RENDERERS.",
                file=sys.stderr,
            )
            components.append(
                render_background(
                    cname,
                    {"title": stype, "bullets": [f"Unknown slide type: {stype}"]},
                    theme,
                )
            )

        if stype in TRANSITION_BY_TYPE:
            transition_overrides.append(f"{cname}.transition = {TRANSITION_BY_TYPE[stype]};")

        notes_list.append(spec.get("notes"))
        _warn_vertical_budget(stype, i + 1, spec)

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    preamble = render_preamble(theme, topic_title, created_at, theme_id)
    preamble = preamble.replace("TOPIC_TITLE_LITERAL", js_string(topic_title))

    body = "\n\n".join(components)

    notes_array_lines = []
    for n in notes_list:
        if n is None:
            notes_array_lines.append("  undefined,")
        else:
            notes_array_lines.append(f"  {js_string(n)},")
    notes_array = "[\n" + "\n".join(notes_array_lines) + "\n]"

    default_array = "[" + ", ".join(component_names) + "]"

    transition_lines = "\n".join(transition_overrides)
    transition_block = f"\n\n// Per-page transition overrides (slide-authoring §Page transitions DNA).\n{transition_lines}\n" if transition_overrides else ""

    tail = f"""{transition_block}
export const notes: (string | undefined)[] = {notes_array};

export default {default_array} satisfies Page[];
"""

    full = preamble + "\n" + body + tail

    slide_dir = deck_dir / "slides" / slide_id
    slide_dir.mkdir(parents=True, exist_ok=True)
    (slide_dir / "index.tsx").write_text(full, encoding="utf-8")


def scaffold_deck(parent_dir: Path, slug: str, locale: str = "zh-TW") -> Path:
    """Scaffold a new open-slide deck. Prefers the globally-installed
    `open-slide` CLI (npm i -g @open-slide/cli) for speed and pnpm support;
    falls back to `npx --yes @open-slide/cli@latest` when global isn't there.

    Flags:
        --use-pnpm: keep deck dependency manager consistent (avoids npm/pnpm
          lockfile mismatch with rest of vibe-coding workflow).
        --locale: deck UI language (home page, present mode menu, inspector
          labels). Defaults to 'zh-TW' for the user's primary locale; overridable
          per-deck via DATA.meta.locale.
    """
    parent_dir.mkdir(parents=True, exist_ok=True)
    deck_dir = parent_dir / slug
    if deck_dir.exists():
        raise SystemExit(
            f"\nDeck folder already exists: {deck_dir}\n"
            "Either rm -rf it first, or pick a different slug."
        )
    global_cli = shutil.which("open-slide")
    base_args = ["init", slug, "--use-pnpm", "--locale", locale]
    if global_cli:
        cmd = [global_cli, *base_args]
        print(f"[scaffold] {global_cli} {' '.join(base_args)} in {parent_dir}")
    else:
        cmd = ["npx", "--yes", "@open-slide/cli@latest", *base_args]
        print(
            f"[scaffold] (global open-slide not found; falling back to npx)\n"
            f"[scaffold] npx --yes @open-slide/cli@latest {' '.join(base_args)}"
        )
    res = subprocess.run(
        cmd,
        cwd=str(parent_dir),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if res.returncode != 0:
        raise SystemExit(
            f"\n[scaffold FAIL] open-slide init returned {res.returncode}\n"
            f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        )
    return deck_dir


def copy_themes(deck_dir: Path) -> None:
    target = deck_dir / "themes"
    target.mkdir(exist_ok=True)
    if not THEME_BUNDLE_DIR.exists():
        raise SystemExit(f"\nTheme bundle dir missing: {THEME_BUNDLE_DIR}")
    copied = 0
    for f in THEME_BUNDLE_DIR.iterdir():
        if f.name.endswith(".md") or f.name.endswith(".demo.tsx"):
            shutil.copy(f, target / f.name)
            copied += 1
    print(f"[themes] copied {copied} files into {target}")


def cleanup_demo(deck_dir: Path) -> None:
    demo = deck_dir / "slides" / "getting-started"
    if demo.exists():
        shutil.rmtree(demo)
        print(f"[cleanup] removed scaffold demo: {demo}")


def verify_build(deck_dir: Path) -> bool:
    """Run `pnpm build` in deck dir to catch TS strict / Vite errors at
    builder-time rather than letting user discover them at handoff. Returns
    True if build pass, False otherwise. Print summary line either way."""
    print(f"[verify] pnpm build (TS strict + Vite) — this catches typos in generated TSX...")
    res = subprocess.run(
        ["pnpm", "build"],
        cwd=str(deck_dir),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if res.returncode != 0:
        print(f"[verify FAIL] pnpm build returned {res.returncode}", file=sys.stderr)
        # Show last 30 lines of stderr (likely the TS / Vite error)
        for line in (res.stderr.strip() or res.stdout.strip()).splitlines()[-30:]:
            print(f"  {line}", file=sys.stderr)
        return False
    # Extract `✓ built in Xs` line if present
    last = [ln for ln in res.stdout.splitlines() if "built in" in ln]
    print(f"[verify] {last[-1].strip()}" if last else "[verify] OK")
    return True


def build(
    data: dict,
    output_parent: Path,
    skill_renderers: dict | None = None,
    slide_id: str = "deck",
    locale: str | None = None,
) -> Path:
    """One-shot orchestrator for per-skill builders.

    Args:
        data: DATA dict (meta / cover / outline_items / slides).
        output_parent: parent dir where <slug>/ scaffold lives.
        skill_renderers: per-skill renderer overrides for slide types beyond
            COMMON_RENDERERS (e.g. paper_meta, pico for journal-club-discussion-pptx).
        slide_id: kebab-case folder name under slides/ (default 'deck';
            journal-club-discussion-pptx uses 'journal-club', case-discussion-pptx may use
            'case-discussion', etc.).
        locale: open-slide UI locale. None → use DATA.meta.locale or 'zh-TW'.

    Returns:
        Path to the built deck directory. Exits with code 1 if build verify
        fails (TS strict / Vite error in generated TSX).
    """
    meta = data.get("meta", {})
    topic_title = meta.get("topic_title", "Open-slide Deck")
    locale = locale or meta.get("locale", "zh-TW")
    slug = slugify(topic_title)

    deck_dir = scaffold_deck(output_parent, slug, locale=locale)
    copy_themes(deck_dir)
    render_deck(data, deck_dir, slide_id=slide_id, skill_renderers=skill_renderers)
    cleanup_demo(deck_dir)
    build_ok = verify_build(deck_dir)

    print()
    if build_ok:
        print(f"✓ Open-slide deck built + verified at: {deck_dir}")
    else:
        print(f"⚠ Deck scaffolded at {deck_dir} but BUILD FAILED — fix above before dev.")
    print()
    print("Next steps:")
    print(f"  cd {deck_dir}")
    print(f"  pnpm dev       # → http://localhost:5173/s/{slide_id}")
    print(f"  pnpm build     # → dist/ static HTML for deploy ({'already passed' if build_ok else 'currently FAILING — fix first'})")
    print()
    print("Workflow tips:")
    print("  - Drag/drop figure files onto <ImagePlaceholder> slots")
    print("  - 'D' opens Design panel — drag color/font/size sliders to tweak live")
    print("  - 'I' opens Inspector — click any element to comment, then /apply-comments")
    print("  - Right-click slide thumbnail → Duplicate to use as template for next deck")
    print()

    if not build_ok:
        sys.exit(1)

    return deck_dir

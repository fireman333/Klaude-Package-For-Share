"""
Three journal club / case discussion pptx themes, ported from
case-discussion-pptx/scripts/generate_case_pptx.js

Each theme is a flat dict of RGBColor + font-name strings. builder.py reads the
active theme via `get_theme(name)`; render.py passes the choice from
DATA["meta"]["theme"].

Keys:
    primary      — main dark color for section headers, title bars
    accent       — journal identity accent (crimson / teal)
    accent2      — secondary accent (copper / navy / coral)
    bg           — slide background
    card_bg      — inner panel / box background
    text         — primary body text
    text_light   — captions, metadata, secondary text
    rule         — thin border / separator lines
    watermark    — faint background numeral on section dividers
    head_font    — title / heading font family
    body_font    — paragraph / bullet font family
"""
from pptx.dml.color import RGBColor


def _rgb(hex_str: str) -> RGBColor:
    h = hex_str.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


THEMES = {
    "grand_rounds_warm": {
        "name": "Grand Rounds Warm (Harvard / Notion editorial)",
        "primary": _rgb("2B2318"),
        "accent": _rgb("8B1A1A"),
        "accent2": _rgb("B87333"),
        "bg": _rgb("F5F1EA"),
        "card_bg": _rgb("FCFAF5"),
        "text": _rgb("2B2318"),
        "text_light": _rgb("6E5B43"),
        "rule": _rgb("D9C8A9"),
        "watermark": _rgb("E8DFC8"),
        "head_font": "Georgia",
        "body_font": "Calibri",
    },
    "journal_classic": {
        "name": "Journal Classic (NEJM / Lancet)",
        "primary": _rgb("1E3A5F"),
        "accent": _rgb("A51C30"),
        "accent2": _rgb("1E3A5F"),
        "bg": _rgb("FFFFFF"),
        "card_bg": _rgb("F8F8F8"),
        "text": _rgb("1A1A1A"),
        "text_light": _rgb("5B5B5B"),
        "rule": _rgb("CCCCCC"),
        "watermark": _rgb("ECECEC"),
        "head_font": "Georgia",
        "body_font": "Georgia",
    },
    "clinical_modern": {
        "name": "Clinical Modern (JAMA / Stripe)",
        "primary": _rgb("0E5E6F"),
        "accent": _rgb("0E5E6F"),
        "accent2": _rgb("C0392B"),
        "bg": _rgb("FAFAFA"),
        "card_bg": _rgb("FFFFFF"),
        "text": _rgb("1A1A1A"),
        "text_light": _rgb("595959"),
        "rule": _rgb("E5E5E5"),
        "watermark": _rgb("EEEEEE"),
        "head_font": "Calibri",
        "body_font": "Calibri",
    },
}


DEFAULT_THEME = "journal_classic"


def get_theme(name: str = DEFAULT_THEME) -> dict:
    if name not in THEMES:
        raise ValueError(
            f"Unknown theme '{name}'. Available: {', '.join(THEMES.keys())}"
        )
    theme = THEMES[name]
    # Invariant: accent and primary must differ. If they collide, any builder
    # call setting text color = accent on a primary-bg shape silently renders
    # invisible text (caught 2026-04-27 on clinical_modern banner sublabel).
    # Warn loudly so the bug surfaces; builder code should also avoid the
    # accent-on-primary pattern, but this is a backstop.
    import sys
    if theme["accent"] == theme["primary"]:
        print(
            f"[themes.py] WARNING: theme '{name}' has accent == primary "
            f"({theme['accent']}). Any 'text color = accent on primary bg' "
            f"render will be invisible. Either pick distinct colors or use "
            f"WHITE for text on primary backgrounds.",
            file=sys.stderr,
        )
    return theme

#!/usr/bin/env python3
"""
journal-club-discussion-pptx orchestrator.

Usage:
    python3 render.py <data.py> <output.pptx> [--skip-rule1-check]

data.py must define module-level DATA dict (see data_schema.md).

Page numbering:
- Slide 1 (cover) has no footer, no page number.
- Slide 2+ gets page = 2, 3, ... auto-incremented.
- DATA["meta"]["topic_title"] goes into every footer.

Theme selection:
- DATA["meta"]["theme"] (one of grand_rounds_warm | journal_classic |
  clinical_modern). Defaults to journal_classic.

Pre-flight checks (Rule 1):
- Before rendering, all slide body text is scanned for CJK characters.
  Found → abort (unless --skip-rule1-check).
- Use --skip-rule1-check only for intentional cover/case-profile that embeds
  a proper noun (e.g. Taiwanese 人名 case label).
"""
import importlib.util
import os
import sys

# allow "from scripts.refs_format import format_citation" (builder.py does lazy
# import at runtime) — put skill dir on sys.path
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)
# bundled helpers live in the sibling skill case-discussion-pptx/lib
_COMMON_DIR = os.path.join(_SKILL_DIR, "..", "case-discussion-pptx", "lib")
if _COMMON_DIR not in sys.path:
    sys.path.insert(0, _COMMON_DIR)

from builder import LAYOUTS, new_presentation, set_theme, strip_leading_empty_paragraphs
from pptx_launder import launder_metadata
from templates.themes import get_theme


def load_data(data_path: str) -> dict:
    spec = importlib.util.spec_from_file_location("jc_data", data_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "DATA"):
        raise ValueError(f"{data_path} must define a module-level DATA dict")
    return mod.DATA


def _collect_body_text(spec: dict) -> list[str]:
    """Extract all string fields from a slide spec EXCEPT 'notes'.
    Returned list is later scanned by rule1 check."""
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k == "notes":
                    continue
                walk(x)

    for k, v in spec.items():
        if k in ("type", "notes"):
            continue
        walk(v)
    return out


def rule1_preflight(slides: list[dict]) -> list[tuple[int, str, str]]:
    """Return list of (slide_index, field_preview, matched_cjk_sample) for
    slide body text containing CJK characters. Notes field excluded.
    Returns empty list on pass."""
    import re
    cjk = re.compile(r"[\u3400-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF]")
    offenders = []
    for i, spec in enumerate(slides):
        for s in _collect_body_text(spec):
            m = cjk.search(s)
            if m:
                preview = s[:80]
                sample = s[max(0, m.start() - 5): m.end() + 5]
                offenders.append((i + 1, preview, sample))
                break  # one per slide is enough
    return offenders


def build(data: dict, output_path: str, skip_rule1: bool = False) -> None:
    meta = data.get("meta", {})
    topic_title = meta.get("topic_title", "Journal Club Discussion")
    theme_name = meta.get("theme", "journal_classic")

    set_theme(get_theme(theme_name))

    slides = data["slides"]

    # Rule 1 pre-flight
    if not skip_rule1:
        offenders = rule1_preflight(slides)
        if offenders:
            msg = [
                "\n[Rule 1 FAIL] slide body contains CJK characters "
                "(中文不應出現在 body，僅可在 notes):",
            ]
            for idx, preview, sample in offenders:
                msg.append(f"  slide {idx}: ...{sample}... (in: {preview!r})")
            msg.append("\nAbort. Fix data file or pass --skip-rule1-check.")
            raise SystemExit("\n".join(msg))

    prs = new_presentation()

    page = 1
    for spec in slides:
        slide_type = spec["type"]
        layout_fn = LAYOUTS[slide_type]

        kwargs = {k: v for k, v in spec.items() if k not in ("type", "notes")}
        note = spec.get("notes")

        if slide_type == "cover":
            cover_kwargs = data.get("cover", {})
            layout_fn(prs, **{**cover_kwargs, **kwargs})
        elif slide_type == "outline":
            items = data.get("outline_items", [])
            layout_fn(prs, items=items, page=page, topic_title=topic_title,
                      **kwargs)
        else:
            layout_fn(prs, page=page, topic_title=topic_title, **kwargs)

        if note:
            prs.slides[-1].notes_slide.notes_text_frame.text = note

        page += 1

    strip_leading_empty_paragraphs(prs)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    prs.save(output_path)
    launder_metadata(output_path, len(prs.slides))
    print(f"Saved: {output_path}")
    print(f"Total slides: {len(prs.slides)}")
    print(f"Theme: {theme_name}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    data_path, output_path = args
    skip_rule1 = "--skip-rule1-check" in flags
    data = load_data(os.path.abspath(data_path))
    build(data, os.path.abspath(output_path), skip_rule1=skip_rule1)


if __name__ == "__main__":
    main()

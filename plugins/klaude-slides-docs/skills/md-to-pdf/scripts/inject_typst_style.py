#!/usr/bin/env python3
"""Inject preset typst show-rules + universal fixes into pandoc-generated .typ.

Why: pandoc -t typst produces a styleless document. We inject a preset's
show-rules (heading look, table borders, CJK font/lang) right before the
#outline() call, plus universal fixes that pandoc's typst writer gets wrong
for CJK + our layout:
  - table wrapped in align(center) -> align(left)
  - outline/TOC title localized to Traditional Chinese 「目錄」
  - bookmark depth bounded to toc-depth (deeper headings: outlined: false)

Usage:
  inject_typst_style.py <merged.typ> <preset-name> <toc-depth> <presets-dir>
"""
import re
import sys
from pathlib import Path

# CJK chars (漢字 + CJK 標點 + 全形標點/符號) for the hard-wrap space fix.
_CJK = r"一-鿿㐀-䶿　-〿＀-￯"

# pandoc's typst writer emits a broken `divider` polyfill whenever the markdown
# contains a horizontal rule (`---`) and typst is older than 0.15. Verified on
# pandoc 3.10.1 + typst 0.14.2 (2026-08-17):
#
#   #let horizontalrule = line(start: (25%,0%), end: (75%,0%))   <- lowercase r
#   #let divider = if "divider" in std { divider } else { horizontalRule }
#                                                         ^^^^^^^^^^^^^^ capital R
#   ...
#   #divider()                                                   <- called as a function
#
# Two defects in one line: the casing does not match the definition above it
# (=> "unknown variable: horizontalRule"), and even once the name is fixed,
# `horizontalrule` is *content*, not a function, so `#divider()` fails with
# "expected function, found content". Replacing the else-branch with a thunk
# fixes both. The pattern only matches the broken form, so this becomes a no-op
# once pandoc ships a fix or typst >= 0.15 makes `divider` a std builtin.
_BROKEN_DIVIDER_POLYFILL = re.compile(
    r'#let\s+divider\s*=\s*if\s+"divider"\s+in\s+std\s*\{\s*divider\s*\}'
    r'\s*else\s*\{\s*horizontalRule\s*\}'
)
_FIXED_DIVIDER_POLYFILL = (
    '#let divider = if "divider" in std { divider } else { () => horizontalrule }'
)


def _strip_cjk_wrap_spaces(s: str) -> str:
    """Remove spaces / single newlines BETWEEN two CJK chars.

    pandoc turns a markdown hard-wrap (line break inside a CJK paragraph) into a
    literal space, and its default --wrap=auto re-wraps long lines mid-paragraph.
    typst renders both as a visible space -> 中文字 之間 有空格. lang:"zh" does NOT
    fix this (it only governs automatic line-breaking, not pre-existing spaces).

    Safe because typst syntax (show-rules, function calls) is ASCII — a
    CJK-space-CJK run only occurs in body text. Paragraph breaks (\\n\\n) are
    untouched: the lookahead after a single \\n sees the second \\n (non-CJK).
    """
    s = re.sub(rf"(?<=[{_CJK}])[ \t]*\n[ \t]*(?=[{_CJK}])", "", s)
    s = re.sub(rf"(?<=[{_CJK}])[ \t]+(?=[{_CJK}])", "", s)
    return s


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: inject_typst_style.py <merged.typ> <preset> <toc-depth> <presets-dir>", file=sys.stderr)
        return 2
    typ_path = Path(sys.argv[1])
    preset = sys.argv[2]
    toc_depth = int(sys.argv[3])
    presets_dir = Path(sys.argv[4])

    preset_file = presets_dir / f"{preset}.typ"
    if not preset_file.is_file():
        print(f"ERROR: preset '{preset}' not found at {preset_file}", file=sys.stderr)
        return 2

    style = preset_file.read_text(encoding="utf-8")

    # Bound PDF bookmarks to toc-depth: deeper headings stay in body but leave outline.
    depth_caps = "".join(
        f"#show heading.where(level: {lv}): set heading(outlined: false)\n"
        for lv in range(toc_depth + 1, 7)
    )

    block = (
        "\n// ===== md-to-pdf injected style (typst engine) =====\n"
        + style
        + "\n"
        + depth_caps
        + "// ===== end injected style =====\n\n"
    )

    s = typ_path.read_text(encoding="utf-8")

    # Insert before #outline( so heading show-rules + outlined caps apply to the TOC too.
    idx = s.find("#outline(")
    if idx < 0:
        # no TOC: insert before first content after the conf() call
        marker = "\n)\n"
        pos = s.find(marker)
        idx = (pos + len(marker)) if pos >= 0 else 0
    s = s[:idx] + block + s[idx:]

    # Universal fixes
    s = s.replace("align(center)[#table(", "align(left)[#table(")
    s = s.replace("title: auto,", "title: [目錄],")
    s, n_divider = _BROKEN_DIVIDER_POLYFILL.subn(_FIXED_DIVIDER_POLYFILL, s)
    s = _strip_cjk_wrap_spaces(s)

    typ_path.write_text(s, encoding="utf-8")
    divider_note = (
        f", divider polyfill repaired ({n_divider})" if n_divider else ""
    )
    print(f"  injected preset '{preset}', bookmark depth ≤ {toc_depth}, "
          f"{s.count('align(left)[#table(')} table(s) left-aligned, "
          f"CJK wrap-spaces stripped{divider_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

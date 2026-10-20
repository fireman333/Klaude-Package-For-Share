#!/usr/bin/env python3
"""
add_pdf_outline.py — Inject a bookmark outline into a Chrome-headless PDF.

Strategy: Chrome preserves HTML anchor id= attributes as named PDF destinations
(link annotations with 'nameddest' field). We parse the HTML to extract headings
with their id attributes, then map those IDs to page numbers via the PDF links.
This is 100% reliable — no text-search heuristics needed.

Fallback: if the HTML is not available, falls back to text-search of the PDF.

Usage:
    python3 add_pdf_outline.py <pdf_path> [<html_path>]

    <html_path> defaults to <pdf_path_stem>.html in the same directory.

Requires: PyMuPDF (fitz) ≥ 1.18, html.parser (stdlib).
"""

import html.parser
import re
import sys
from pathlib import Path
from urllib.parse import unquote

try:
    import fitz
except ImportError:
    print("[outline] ERROR: PyMuPDF not found. Run: pip install pymupdf", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# HTML heading extractor
# ---------------------------------------------------------------------------

class _HeadingParser(html.parser.HTMLParser):
    """Collect (level, id, text) for h1/h2/h3 tags."""

    def __init__(self):
        super().__init__()
        self.headings: list[tuple[int, str, str]] = []   # (level, id, text)
        self._cur_level: int | None = None
        self._cur_id: str = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        m = re.match(r'^h([123])$', tag)
        if m:
            self._cur_level = int(m.group(1))
            self._cur_id = dict(attrs).get("id", "")
            self._buf = []

    def handle_endtag(self, tag):
        if self._cur_level and re.match(r'^h([123])$', tag):
            text = "".join(self._buf).strip()
            # Strip any ¶ pilcrow or § anchor link text that pandoc adds
            text = re.sub(r'\s*[¶§]$', '', text).strip()
            if text and self._cur_id:
                self.headings.append((self._cur_level, self._cur_id, text))
            self._cur_level = None
            self._cur_id = ""
            self._buf = []

    def handle_data(self, data):
        if self._cur_level is not None:
            self._buf.append(data)

    def handle_entityref(self, name):
        if self._cur_level is not None:
            self._buf.append(html.unescape(f"&{name};"))

    def handle_charref(self, name):
        if self._cur_level is not None:
            self._buf.append(html.unescape(f"&#{name};"))


def parse_html_headings(html_text: str) -> list[tuple[int, str, str]]:
    """Return [(level, id, text), ...] for h1/h2/h3 with id attributes."""
    p = _HeadingParser()
    p.feed(html_text)
    return p.headings


# ---------------------------------------------------------------------------
# Build nameddest → page map from PDF links
# ---------------------------------------------------------------------------

def build_dest_map(doc: fitz.Document) -> dict[str, int]:
    """
    Scan every page for link annotations that have a 'nameddest' key.

    Returns two parallel dicts bundled in a tuple:
      raw_map:     {raw_nameddest: 1-indexed-page}   (URL-encoded as Chrome stores it)
      decoded_map: {decoded_nameddest: 1-indexed-page}

    Chrome truncates long nameddest strings (CJK anchors overflow the limit),
    so long IDs may appear as partial percent-sequences like '...%E8%AA%AA'.
    We keep both forms to support prefix matching during lookup.
    """
    raw_map: dict[str, int] = {}
    decoded_map: dict[str, int] = {}
    for page_num in range(len(doc)):
        for lnk in doc[page_num].get_links():
            nd = lnk.get("nameddest", "")
            if nd:
                target_page = lnk.get("page", page_num) + 1  # 0-indexed → 1-indexed
                raw_map[nd] = target_page
                decoded_map[unquote(nd)] = target_page
    return raw_map, decoded_map


# ---------------------------------------------------------------------------
# Hierarchy normalisation
# ---------------------------------------------------------------------------

def normalize_levels(toc: list[list]) -> list[list]:
    """Clamp level jumps to at most +1 (PyMuPDF requirement)."""
    if not toc:
        return toc
    result = []
    prev = 0
    for level, title, page in toc:
        level = max(1, min(level, prev + 1))
        result.append([level, title, page])
        prev = level
    return result


# ---------------------------------------------------------------------------
# Fallback: text-search in PDF
# ---------------------------------------------------------------------------

_MD_FMT = re.compile(r'\*+|`([^`]+)`|\[([^\]]+)\]\([^)]+\)')

def _clean_md(title: str) -> str:
    def _r(m): return m.group(1) or m.group(2) or ""
    return _MD_FMT.sub(_r, title).strip()


def parse_md_headings(md_text: str) -> list[tuple[int, str]]:
    headings = []
    in_fence = False
    for line in md_text.splitlines():
        if re.match(r'^```', line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r'^(#{1,3})\s+(.*\S)', line)
        if m:
            t = _clean_md(m.group(2))
            if t:
                headings.append((len(m.group(1)), t))
    return headings


def _find_page_text(doc, title, start_page=0):
    snippets = [title[:50].strip()]
    if len(title) > 20:
        snippets.append(title[:25].strip())
    cjk = re.findall(r'[一-鿿]{4,}', title)
    if cjk:
        snippets.append(cjk[0][:20])
    for snippet in snippets:
        for i in range(start_page, len(doc)):
            if doc[i].search_for(snippet):
                return i + 1
    return None


def build_toc_from_text(doc, md_path):
    headings = parse_md_headings(Path(md_path).read_text())
    toc, last = [], 0
    for level, title in headings:
        p = _find_page_text(doc, title, start_page=max(0, last - 1))
        if p:
            toc.append([level, title, p])
            last = p
    return normalize_levels(toc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <pdf_path> [<html_path>]", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    html_path = (Path(sys.argv[2]) if len(sys.argv) >= 3
                 else pdf_path.with_suffix(".html"))

    if not pdf_path.exists():
        print(f"[outline] ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"  opening PDF ({pdf_path.stat().st_size // 1024} KB)...")
    doc = fitz.open(str(pdf_path))

    toc: list[list] = []

    # --- Primary path: HTML anchor → named destination ---
    if html_path.exists():
        print(f"  parsing HTML headings from {html_path.name}...")
        headings = parse_html_headings(html_path.read_text(encoding="utf-8"))
        print(f"  found {len(headings)} headings with id attributes")

        print(f"  building named-destination map from {len(doc)} PDF pages...")
        raw_map, decoded_map = build_dest_map(doc)
        print(f"  found {len(raw_map)} named destinations in PDF")

        from urllib.parse import quote as url_quote

        def lookup_dest(hid: str) -> int | None:
            # 1. Exact decoded match
            if hid in decoded_map:
                return decoded_map[hid]
            # 2. Chrome truncates long CJK IDs mid-percent-sequence.
            #    URL-encode the full HTML id and check if any raw dest is a
            #    prefix of it (both using uppercase %XX for comparability).
            encoded_id = url_quote(hid, safe="-_.~")
            for raw_dest, page in raw_map.items():
                # Strip trailing incomplete percent-sequence from raw dest
                clean_raw = re.sub(r'%[0-9A-Fa-f]{0,1}$', '', raw_dest)
                if encoded_id.upper().startswith(clean_raw.upper()) and len(clean_raw) > 8:
                    return page
            return None

        for level, hid, text in headings:
            # Collapse any stray newlines/spaces in heading text
            text = re.sub(r'\s+', ' ', text).strip()
            page = lookup_dest(hid)
            if page is None:
                print(f"  [outline] skip (no dest): {text[:55]}", file=sys.stderr)
            else:
                toc.append([level, text, page])

        toc = normalize_levels(toc)
        print(f"  matched {len(toc)}/{len(headings)} headings via HTML anchors")

    # --- Fallback: text search ---
    else:
        md_path = pdf_path.parent / "combined.md"
        print(f"  HTML not found; falling back to text search in PDF...", file=sys.stderr)
        if md_path.exists():
            toc = build_toc_from_text(doc, md_path)
            print(f"  matched {len(toc)} headings via text search")
        else:
            print(f"[outline] ERROR: neither {html_path} nor {md_path} found", file=sys.stderr)
            doc.close()
            sys.exit(1)

    if not toc:
        print("[outline] WARN: no headings matched — outline not written", file=sys.stderr)
        doc.close()
        return

    doc.set_toc(toc)
    doc.save(str(pdf_path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    doc.close()
    print(f"  outline written in-place ({len(toc)} bookmarks): {pdf_path.name}")


if __name__ == "__main__":
    main()

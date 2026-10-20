#!/usr/bin/env python3
"""
convert_pdf.py — Convert PDF chapters to markdown with images.

Engine auto-selection (based on PDF file size):
  < 50 MB  → pymupdf4llm   (rich markdown: bold, italic, tables)
  ≥ 50 MB  → PyMuPDF native get_text("dict")  (fast: ~150s for 4273 pages)
  scanned  → marker-pdf    (needs: uv tool install marker-pdf --python 3.13)

Caching: SHA256 of (file_size + mtime + mode) → ~/.cache/pdf-to-markdown/
  Skips re-conversion for unchanged PDFs. Use --no-cache to bypass.

Usage:
  python convert_pdf.py --pdf <path> [--output-dir <dir>] [--chapters <list>]
  python convert_pdf.py --pdf <path> --all
  python convert_pdf.py --pdf <path> --engine native   # force native engine
  python convert_pdf.py --pdf <path> --with-images     # include images (native engine only)
  python convert_pdf.py --pdf <path> --no-cache        # skip cache
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import fitz
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip3 install pymupdf")
    sys.exit(1)

LARGE_PDF_THRESHOLD_MB = 50
CACHE_DIR = Path.home() / ".cache" / "pdf-to-markdown"
CACHE_VERSION = "1.0"

# Default chapter names for Pocket Medicine / internal medicine textbooks
TARGET_CHAPTERS = [
    "CARDIOLOGY", "PULMONARY", "GASTROENTEROLOGY", "NEPHROLOGY",
    "HEMATOLOGY-ONCOLOGY", "INFECTIOUS DISEASES", "ENDOCRINOLOGY",
    "RHEUMATOLOGY", "NEUROLOGY", "CONSULTS",
]

# Image filter thresholds (native engine)
MIN_IMG_PX = 80   # min width AND height in pixels
MIN_IMG_KB = 4    # min file size in KB


# ─── Cache helpers ────────────────────────────────────────────────────────────

def cache_key(pdf_path: Path, mode: str) -> str:
    stat = pdf_path.stat()
    raw = f"{stat.st_size}|{stat.st_mtime}|{mode}|{CACHE_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cache_load(pdf_path: Path, mode: str):
    """Return cached markdown string + images_dir, or (None, None)."""
    key = cache_key(pdf_path, mode)
    cache_path = CACHE_DIR / key
    meta = cache_path / "metadata.json"
    if not meta.exists():
        return None, None
    md_file = cache_path / "output.md"
    if not md_file.exists():
        return None, None
    print(f"  [cache hit] {key}", flush=True)
    return md_file.read_text(encoding="utf-8"), cache_path / "images"


def cache_save(pdf_path: Path, mode: str, md: str, images_src: Path = None):
    key = cache_key(pdf_path, mode)
    cache_path = CACHE_DIR / key
    cache_path.mkdir(parents=True, exist_ok=True)
    (cache_path / "output.md").write_text(md, encoding="utf-8")
    (cache_path / "metadata.json").write_text(
        json.dumps({"pdf": str(pdf_path), "mode": mode, "version": CACHE_VERSION}),
        encoding="utf-8",
    )
    if images_src and images_src.exists():
        img_dst = cache_path / "images"
        if img_dst.exists():
            shutil.rmtree(img_dst)
        shutil.copytree(images_src, img_dst)


# ─── TOC helpers ──────────────────────────────────────────────────────────────

def get_chapter_ranges(pdf_path: Path, target: list[str]) -> list[tuple[str, int, int]]:
    """Return [(chapter_name, start_0indexed, end_0indexed), ...]."""
    doc = fitz.open(str(pdf_path))
    total = doc.page_count
    toc = doc.get_toc()
    level1 = [(title, page) for level, title, page in toc if level == 1]
    target_upper = [c.upper() for c in target]
    chapters = []
    for i, (title, start_page) in enumerate(level1):
        if title.upper() in target_upper:
            end_page = level1[i + 1][1] - 1 if i + 1 < len(level1) else total
            chapters.append((title, start_page - 1, end_page - 1))
    return chapters


# ─── pymupdf4llm engine (small PDFs < 50 MB) ─────────────────────────────────

def convert_chapter_pymupdf4llm(
    pdf_path: Path, chapter_name: str, start: int, end: int, output_file: Path,
    use_cache: bool = True,
) -> bool:
    try:
        import pymupdf4llm
    except ImportError:
        print("ERROR: pymupdf4llm not installed. Run: pip3 install pymupdf4llm")
        return False

    mode = f"pymupdf4llm|{start}-{end}"
    if use_cache:
        cached_md, _ = cache_load(pdf_path, mode)
        if cached_md:
            output_file.write_text(cached_md, encoding="utf-8")
            print(f"  Done (cached, {output_file.stat().st_size//1024}KB)", flush=True)
            return True

    pages = list(range(start, end + 1))
    print(f"  Converting pages {start}–{end} ({len(pages)} pages) → {output_file.name}", flush=True)
    md = pymupdf4llm.to_markdown(str(pdf_path), pages=pages)
    final = f"# {chapter_name.title()}\n\n{md}"
    output_file.write_text(final, encoding="utf-8")

    if use_cache:
        cache_save(pdf_path, mode, final)

    size_kb = output_file.stat().st_size // 1024
    print(f"  Done ({size_kb}KB)", flush=True)
    if size_kb < 5:
        print(f"  WARNING: suspiciously small — check output quality", flush=True)
    return True


def convert_single_pymupdf4llm(pdf_path: Path, output_dir: Path) -> bool:
    try:
        import pymupdf4llm
    except ImportError:
        print("ERROR: pymupdf4llm not installed. Run: pip3 install pymupdf4llm")
        return False
    print(f"Converting entire PDF: {pdf_path.name}", flush=True)
    md = pymupdf4llm.to_markdown(str(pdf_path))
    out = output_dir / f"{pdf_path.stem}.md"
    out.write_text(md, encoding="utf-8")
    print(f"Done → {out} ({out.stat().st_size//1024}KB)", flush=True)
    return True


# ─── Native PyMuPDF engine (large PDFs ≥ 50 MB) ──────────────────────────────

def _process_block_native(block, images_dir: Path, ch_num: int, page_num: int, block_idx: int):
    """Return markdown string for one block, or None to skip."""
    if block["type"] == 0:
        lines = []
        for line in block["lines"]:
            spans = line["spans"]
            if not spans:
                continue
            max_size = max(s["size"] for s in spans)
            is_bold = any(s["flags"] & (1 << 4) for s in spans)
            text = "".join(s["text"] for s in spans).strip()
            if not text:
                continue
            if max_size >= 14 and is_bold:
                lines.append(f"\n## {text}\n")
            elif max_size >= 12 and is_bold:
                lines.append(f"\n### {text}\n")
            else:
                lines.append(text)
        content = "\n".join(lines).strip()
        return content if content else None

    elif block["type"] == 1 and images_dir:
        w   = block.get("width", 0)
        h   = block.get("height", 0)
        raw = block.get("image", b"")
        ext = block.get("ext", "png")
        size_kb = len(raw) // 1024
        if w < MIN_IMG_PX or h < MIN_IMG_PX or size_kb < MIN_IMG_KB:
            return None
        fname = f"Ch{ch_num:03d}_p{page_num+1:04d}_b{block_idx:02d}.{ext}"
        (images_dir / fname).write_bytes(raw)
        return f"\n![Figure p.{page_num+1}](images/{fname})\n"

    return None


def convert_chapter_native(
    doc: fitz.Document, chapter_name: str, ch_num: int,
    start: int, end: int, output_file: Path,
    with_images: bool = True,
) -> bool:
    """Convert one chapter using PyMuPDF native get_text("dict")."""
    images_dir = None
    if with_images:
        images_dir = output_file.parent / "images"
        images_dir.mkdir(exist_ok=True)

    parts = [f"# {chapter_name}\n"]
    for pn in range(start, end + 1):
        page_parts = []
        for idx, block in enumerate(doc[pn].get_text("dict")["blocks"]):
            md = _process_block_native(block, images_dir, ch_num, pn, idx)
            if md:
                page_parts.append(md)
        if page_parts:
            parts.append("\n".join(page_parts))

    output_file.write_text("\n\n".join(parts), encoding="utf-8")
    return True


def convert_whole_pdf_native(doc: fitz.Document, pdf_path: Path, output_dir: Path, with_images: bool) -> bool:
    """Convert entire PDF as one file using native engine."""
    images_dir = None
    if with_images:
        images_dir = output_dir / "images"
        images_dir.mkdir(exist_ok=True)

    parts = []
    for pn in range(doc.page_count):
        page_parts = []
        for idx, block in enumerate(doc[pn].get_text("dict")["blocks"]):
            md = _process_block_native(block, images_dir, 0, pn, idx)
            if md:
                page_parts.append(md)
        if page_parts:
            parts.append("\n".join(page_parts))

    out = output_dir / f"{pdf_path.stem}.md"
    out.write_text("\n\n".join(parts), encoding="utf-8")
    print(f"Done → {out} ({out.stat().st_size//1024}KB)", flush=True)
    return True


# ─── marker engine (scanned PDFs) ────────────────────────────────────────────

def find_marker_single() -> str:
    from shutil import which
    for p in [Path.home() / ".local/bin/marker_single", Path("/usr/local/bin/marker_single")]:
        if p.exists():
            return str(p)
    return which("marker_single") or "marker_single"


def convert_chapter_marker(
    pdf_path: Path, chapter_name: str, start: int, end: int, output_file: Path,
) -> bool:
    marker_bin = find_marker_single()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [marker_bin, str(pdf_path), "--output_format", "markdown",
             "--output_dir", tmpdir, "--page_range", f"{start}-{end}",
             "--disable_image_extraction"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  ERROR: marker_single failed:\n{result.stderr[-500:]}", flush=True)
            return False
        md_files = list(Path(tmpdir).rglob("*.md"))
        if not md_files:
            print(f"  ERROR: No .md file produced for {chapter_name}", flush=True)
            return False
        content = md_files[0].read_text(encoding="utf-8")
        output_file.write_text(f"# {chapter_name.title()}\n\n{content}", encoding="utf-8")
        return True


# ─── main ─────────────────────────────────────────────────────────────────────

def detect_engine(pdf_path: Path, requested: str) -> str:
    """Auto-select engine based on PDF size if not explicitly set."""
    if requested != "auto":
        return requested
    size_mb = pdf_path.stat().st_size / (1024 * 1024)
    print(f"  PDF is {size_mb:.0f} MB → using native PyMuPDF engine (default)", flush=True)
    return "native"


def main():
    parser = argparse.ArgumentParser(description="Convert PDF to markdown (with images)")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--chapters", help="Comma-separated chapter names")
    parser.add_argument("--all", action="store_true", dest="convert_all")
    parser.add_argument("--engine",
                        choices=["auto", "pymupdf4llm", "native", "marker"],
                        default="auto",
                        help="auto (default): choose by file size; native: PyMuPDF dict; marker: for scanned PDFs")
    parser.add_argument("--with-images", action="store_true", dest="with_images",
                        help="Extract and embed images (native engine only)")
    parser.add_argument("--no-cache", action="store_true", dest="no_cache",
                        help="Skip cache, always re-convert")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir \
        else pdf_path.parent / f"{pdf_path.stem}-Chapters"
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = detect_engine(pdf_path, args.engine)
    use_cache = not args.no_cache
    print(f"Engine: {engine}  |  Images: {args.with_images}  |  Cache: {use_cache}\n", flush=True)

    # ── Whole-PDF mode ─────────────────────────────────────────────────────────
    if args.convert_all:
        if engine == "native":
            doc = fitz.open(str(pdf_path))
            convert_whole_pdf_native(doc, pdf_path, output_dir, args.with_images)
            doc.close()
        elif engine == "pymupdf4llm":
            convert_single_pymupdf4llm(pdf_path, output_dir)
        else:
            print("Use marker_single directly for whole-PDF marker conversion.")
            sys.exit(1)
        sys.exit(0)

    # ── Chapter-split mode ─────────────────────────────────────────────────────
    target = [c.strip() for c in args.chapters.split(",")] if args.chapters else TARGET_CHAPTERS
    chapters = get_chapter_ranges(pdf_path, target)

    if not chapters:
        print("ERROR: No matching chapters found. Available level-1 TOC entries:")
        doc = fitz.open(str(pdf_path))
        for l, t, p in doc.get_toc():
            if l == 1:
                print(f"  page {p}: {t}")
        sys.exit(1)

    print(f"Converting {len(chapters)} chapters → {output_dir}\n", flush=True)
    failures = []

    # For native engine, open doc once
    doc = fitz.open(str(pdf_path)) if engine == "native" else None

    for idx, (name, start, end) in enumerate(chapters, 1):
        import re
        safe_name = re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '-')
        safe_name = re.sub(r'-+', '-', safe_name)[:60]
        output_file = output_dir / f"{idx:02d}-{safe_name.title()}.md"
        pages = end - start + 1
        print(f"[{idx}/{len(chapters)}] {name}  ({pages} pages)", flush=True)

        if engine == "pymupdf4llm":
            ok = convert_chapter_pymupdf4llm(pdf_path, name, start, end, output_file, use_cache)
        elif engine == "native":
            ok = convert_chapter_native(doc, name, idx, start, end, output_file, args.with_images)
            if ok:
                size_kb = output_file.stat().st_size // 1024
                print(f"  Done ({size_kb}KB)", flush=True)
        elif engine == "marker":
            ok = convert_chapter_marker(pdf_path, name, start, end, output_file)
        else:
            ok = False

        if not ok:
            failures.append(name)

    if doc:
        doc.close()

    print(f"\n{'='*50}", flush=True)
    print(f"Completed: {len(chapters) - len(failures)}/{len(chapters)} chapters", flush=True)
    if failures:
        print(f"Failed: {', '.join(failures)}", flush=True)
    else:
        print("All chapters converted successfully.", flush=True)
        for f in sorted(output_dir.glob("*.md")):
            print(f"  {f.name} ({f.stat().st_size//1024}KB)", flush=True)


if __name__ == "__main__":
    main()

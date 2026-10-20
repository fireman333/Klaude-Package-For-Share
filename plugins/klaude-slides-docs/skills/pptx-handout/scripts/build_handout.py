#!/usr/bin/env python3
"""
pptx-handout — Build A4 portrait handout PDF from any .pptx with speaker notes.

Layout per page:
  Header: "Slide N / total  <Title>" + crimson rule line
  Body:   slide thumbnail (top ~45%) + Speaker Notes (bottom ~50%)

Usage:
  python3 build_handout.py --pptx <abs.pptx> [--output <abs.pdf>]
                           [--layout portrait|landscape]
                           [--font <ttf-path>]
                           [--no-notes-message "(blank)"]

Default output: <same folder as pptx>/handout_<pptx-stem>.pdf

CJK-safe: auto-registers macOS PingFang/STHeiti, falls back to STSong-Light CID.

Exit codes:
  0 success
  1 input file missing
  2 missing dependency (reportlab / python-pptx / PIL)
  3 soffice render failed
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build A4 handout PDF from a .pptx")
    ap.add_argument("--pptx", required=True, help="Absolute path to source .pptx")
    ap.add_argument("--output", help="Absolute path for output PDF (default: handout_<stem>.pdf next to pptx)")
    ap.add_argument("--layout", default="portrait", choices=["portrait", "landscape"],
                    help="Page orientation (default: portrait)")
    ap.add_argument("--font", help="Absolute path to TTF/TTC font (override CJK auto-detect)")
    ap.add_argument("--no-notes-message", default="(此頁無備忘稿)",
                    help='String to print when a slide has no notes (default: "(此頁無備忘稿)")')
    return ap.parse_args()


def ensure_deps() -> None:
    missing = []
    try:
        import pptx  # noqa: F401
    except ImportError:
        missing.append("python-pptx")
    try:
        import reportlab  # noqa: F401
    except ImportError:
        missing.append("reportlab")
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("Pillow")
    if missing:
        log(f"Missing deps: {missing}. Install with: pip install {' '.join(missing)}")
        sys.exit(2)


def render_slides_to_jpg(pptx_path: Path, tmpdir: Path, dpi: int = 100) -> list[Path]:
    """Convert pptx → PDF → JPG via soffice + pdftoppm. Returns sorted list of JPG paths."""
    log(f"  soffice convert: {pptx_path.name} → PDF")
    res = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf",
         str(pptx_path), "--outdir", str(tmpdir)],
        capture_output=True, text=True, timeout=120,
    )
    if res.returncode != 0:
        log(f"soffice failed: {res.stderr}")
        sys.exit(3)
    pdf_path = tmpdir / f"{pptx_path.stem}.pdf"
    if not pdf_path.exists():
        log(f"Expected PDF not found: {pdf_path}")
        sys.exit(3)

    log(f"  pdftoppm: PDF → JPGs @ {dpi} dpi")
    subprocess.run(
        ["pdftoppm", "-jpeg", "-r", str(dpi), str(pdf_path), str(tmpdir / "s")],
        check=True, capture_output=True,
    )
    jpgs = sorted(tmpdir.glob("s-*.jpg"))
    log(f"  rendered {len(jpgs)} slides")
    return jpgs


def register_font(font_override: str | None) -> str:
    """Register a CJK-capable font. Returns the registered font name."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    if font_override:
        try:
            pdfmetrics.registerFont(TTFont("CJK", font_override, subfontIndex=0))
            log(f"✓ Registered override font: {font_override}")
            return "CJK"
        except Exception as e:
            log(f"  override font failed ({e}), falling back to auto-detect")

    for fp in [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("CJK", fp, subfontIndex=0))
                log(f"✓ Using TTF: {fp}")
                return "CJK"
            except Exception:
                continue

    # CID fallback (always available in reportlab)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    log("✓ Using CID font STSong-Light (TTF unavailable)")
    return "STSong-Light"


def extract_slide_data(pptx_path: Path) -> list[dict]:
    """Read pptx → list of {num, title, notes}."""
    from pptx import Presentation
    p = Presentation(str(pptx_path))
    out = []
    for i, sl in enumerate(p.slides, 1):
        title = ""
        for sh in sl.shapes:
            if sh.has_text_frame and sh.text_frame.text:
                title = sh.text_frame.text.split("\n")[0][:80]
                break
        notes = sl.notes_slide.notes_text_frame.text.strip() if sl.has_notes_slide else ""
        out.append({"num": i, "title": title, "notes": notes})
    return out


def build_pdf(slides: list[dict], jpgs: list[Path], out_pdf: Path,
              font_name: str, layout: str, no_notes_msg: str) -> None:
    """Build the A4 handout PDF."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib import colors
    from reportlab.platypus import (
        Paragraph, Image, Spacer, PageBreak, Frame, PageTemplate, BaseDocTemplate,
    )
    from PIL import Image as PILImage

    pagesize = landscape(A4) if layout == "landscape" else A4
    PAGE_W, PAGE_H = pagesize

    MARGIN_X = 12 * mm
    MARGIN_Y = 10 * mm
    HEADER_H = 9 * mm

    doc = BaseDocTemplate(
        str(out_pdf), pagesize=pagesize,
        leftMargin=MARGIN_X, rightMargin=MARGIN_X,
        topMargin=MARGIN_Y + HEADER_H, bottomMargin=MARGIN_Y,
    )

    content_frame = Frame(
        MARGIN_X, MARGIN_Y,
        PAGE_W - 2 * MARGIN_X, PAGE_H - 2 * MARGIN_Y - HEADER_H,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        showBoundary=0,
    )

    current_idx = [0]

    def on_page(canvas, doc_):
        sd = slides[current_idx[0]]
        canvas.saveState()
        canvas.setFont(font_name, 10)
        canvas.setFillColorRGB(0.55, 0.10, 0.10)
        canvas.drawString(MARGIN_X, PAGE_H - MARGIN_Y - 4,
                          f"Slide {sd['num']} / {len(slides)}")
        canvas.setFont(font_name, 10)
        canvas.setFillColorRGB(0.16, 0.13, 0.10)
        canvas.drawString(MARGIN_X + 28 * mm, PAGE_H - MARGIN_Y - 4, sd["title"][:70])
        canvas.setStrokeColorRGB(0.55, 0.10, 0.10)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_X, PAGE_H - MARGIN_Y - 7, PAGE_W - MARGIN_X, PAGE_H - MARGIN_Y - 7)
        canvas.restoreState()
        current_idx[0] += 1

    doc.addPageTemplates([PageTemplate(id="main", frames=[content_frame], onPage=on_page)])

    style_section = ParagraphStyle(
        "section", fontName=font_name, fontSize=9,
        textColor=colors.HexColor("#8B1A1A"), spaceAfter=2,
    )
    style_notes = ParagraphStyle(
        "notes", fontName=font_name, fontSize=9.5, leading=14,
        textColor=colors.HexColor("#2B2318"), spaceAfter=4,
        alignment=TA_LEFT, wordWrap="CJK",
    )

    AVAIL_W = PAGE_W - 2 * MARGIN_X
    AVAIL_H = PAGE_H - 2 * MARGIN_Y - HEADER_H
    # Portrait: image ~45% / notes ~50%
    # Landscape: image ~50% / notes ~45% (wider, less notes height)
    img_pct = 0.45 if layout == "portrait" else 0.55
    IMG_MAX_H = AVAIL_H * img_pct
    IMG_MAX_W = AVAIL_W

    story = []
    for idx, sd in enumerate(slides):
        # Match by index — jpgs list parallels slides list
        if idx < len(jpgs) and jpgs[idx].exists():
            try:
                pil = PILImage.open(jpgs[idx])
                iw, ih = pil.size
                ratio = iw / ih
                if IMG_MAX_W / ratio <= IMG_MAX_H:
                    disp_w, disp_h = IMG_MAX_W, IMG_MAX_W / ratio
                else:
                    disp_h, disp_w = IMG_MAX_H, IMG_MAX_H * ratio
                img = Image(str(jpgs[idx]), width=disp_w, height=disp_h)
                img.hAlign = "CENTER"
                story.append(img)
            except Exception as e:
                story.append(Paragraph(f"[Image error: {e}]", style_notes))

        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("SPEAKER NOTES", style_section))
        story.append(Spacer(1, 1 * mm))

        notes = sd["notes"] or no_notes_msg
        notes_html = (notes
                      .replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;")
                      .replace("\n", "<br/>"))
        story.append(Paragraph(notes_html, style_notes))

        if idx < len(slides) - 1:
            story.append(PageBreak())

    doc.build(story)


def main() -> None:
    args = parse_args()
    pptx_path = Path(args.pptx).resolve()
    if not pptx_path.exists():
        log(f"✗ pptx not found: {pptx_path}")
        sys.exit(1)
    if pptx_path.suffix.lower() != ".pptx":
        log(f"✗ not a .pptx: {pptx_path}")
        sys.exit(1)

    ensure_deps()

    out_pdf = Path(args.output).resolve() if args.output else pptx_path.parent / f"handout_{pptx_path.stem}.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    log(f"→ pptx: {pptx_path}")
    log(f"→ out:  {out_pdf}")
    log(f"→ layout: {args.layout}")

    font_name = register_font(args.font)

    with tempfile.TemporaryDirectory(prefix="pptx_handout_") as tmp:
        tmpdir = Path(tmp)
        jpgs = render_slides_to_jpg(pptx_path, tmpdir)
        slides = extract_slide_data(pptx_path)
        if len(jpgs) != len(slides):
            log(f"⚠ slide count mismatch (jpgs={len(jpgs)} slides={len(slides)}) — will trim to min")
        build_pdf(slides[:len(jpgs)], jpgs[:len(slides)], out_pdf, font_name, args.layout, args.no_notes_message)

    log(f"✓ handout written: {out_pdf} ({out_pdf.stat().st_size // 1024} KB, {len(slides)} pages)")
    # stdout = output path (for caller capture)
    print(str(out_pdf))


if __name__ == "__main__":
    main()

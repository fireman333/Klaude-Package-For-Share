"""Launder python-pptx output metadata so PowerPoint Mac doesn't flag the file
as "corrupt → recover" on first open.

Root cause: python-pptx ships fixed defaults in docProps/{core,app}.xml —
`cp:lastModifiedBy: Steve Canny`, 2013 dates, `<Slides>0</Slides>`, and
`Application: Microsoft Macintosh PowerPoint`. PowerPoint Mac's strict
validator + first-open Protected View treats this fingerprint as untrusted
and sets a sticky `com.apple.quarantine` xattr, after which every open shows
the corrupt-recover dialog.

This module rewrites the two docProps XMLs in-place after `prs.save()`,
preserving every slide / notes / layout part byte-for-byte.

Usage:
    from pptx_launder import launder_metadata
    prs.save(output_path)
    launder_metadata(output_path, len(prs.slides))

Intentional non-goals:
- Does NOT touch slide / notes / layout XML
- Does NOT remove com.apple.quarantine xattr (only PowerPoint adds it post-hoc;
  at build time the file has no quarantine flag)
- Does NOT validate the rest of the OOXML structure
"""
from __future__ import annotations

import re
import shutil
import zipfile
from datetime import datetime, timezone


def launder_metadata(pptx_path: str, n_slides: int) -> None:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    titles = "".join(f"<vt:lpstr>Slide {i}</vt:lpstr>" for i in range(1, n_slides + 1))
    new_heading = (
        '<HeadingPairs><vt:vector size="4" baseType="variant">'
        "<vt:variant><vt:lpstr>Theme</vt:lpstr></vt:variant>"
        "<vt:variant><vt:i4>1</vt:i4></vt:variant>"
        "<vt:variant><vt:lpstr>Slide Titles</vt:lpstr></vt:variant>"
        f"<vt:variant><vt:i4>{n_slides}</vt:i4></vt:variant>"
        "</vt:vector></HeadingPairs>"
    )
    new_titles = (
        f'<TitlesOfParts><vt:vector size="{n_slides + 1}" baseType="lpstr">'
        "<vt:lpstr>Office Theme</vt:lpstr>"
        f"{titles}"
        "</vt:vector></TitlesOfParts>"
    )

    tmp = pptx_path + ".tmp"
    with zipfile.ZipFile(pptx_path, "r") as zin:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "docProps/core.xml":
                    xml = data.decode("utf-8")
                    xml = re.sub(
                        r"<cp:lastModifiedBy>[^<]*</cp:lastModifiedBy>",
                        "<cp:lastModifiedBy></cp:lastModifiedBy>",
                        xml,
                    )
                    xml = re.sub(
                        r'<dcterms:created xsi:type="dcterms:W3CDTF">[^<]+</dcterms:created>',
                        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now_utc}</dcterms:created>',
                        xml,
                    )
                    xml = re.sub(
                        r'<dcterms:modified xsi:type="dcterms:W3CDTF">[^<]+</dcterms:modified>',
                        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now_utc}</dcterms:modified>',
                        xml,
                    )
                    data = xml.encode("utf-8")
                elif item.filename == "docProps/app.xml":
                    xml = data.decode("utf-8")
                    xml = re.sub(r"<Slides>\d+</Slides>", f"<Slides>{n_slides}</Slides>", xml)
                    xml = re.sub(r"<Notes>\d+</Notes>", f"<Notes>{n_slides}</Notes>", xml)
                    xml = re.sub(
                        r"<Application>[^<]*</Application>",
                        "<Application>Microsoft PowerPoint</Application>",
                        xml,
                    )
                    xml = re.sub(
                        r"<HeadingPairs>.*?</HeadingPairs>", new_heading, xml, flags=re.DOTALL
                    )
                    xml = re.sub(
                        r"<TitlesOfParts>.*?</TitlesOfParts>", new_titles, xml, flags=re.DOTALL
                    )
                    data = xml.encode("utf-8")
                zout.writestr(item, data)
    shutil.move(tmp, pptx_path)

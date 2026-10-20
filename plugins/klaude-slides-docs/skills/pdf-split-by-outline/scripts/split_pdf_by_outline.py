#!/usr/bin/env python3
"""Split a PDF by its outline (bookmarks/TOC) into separate files and folders.

Usage:
    python3 split_pdf_by_outline.py input.pdf [options]

Options:
    --inspect           Only print the outline structure, don't split
    --folder-level N    Outline level for folders (default: 1, 0 = no folders)
    --split-level N     Outline level for individual PDFs (default: 2)
    --output-dir PATH   Output directory (default: <input>-拆分/)
    --no-numbering      Don't prefix filenames with sequential numbers
    --flatten           No subfolders, all PDFs flat with hierarchy in filename
    --no-prefix         Skip pages before the first bookmark
"""

import argparse
import os
import re
import sys
import subprocess


def ensure_pymupdf():
    try:
        import fitz  # noqa: F401
    except ImportError:
        print("Installing pymupdf...", file=sys.stderr)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pymupdf", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def sanitize_filename(name: str, max_len: int = 80) -> str:
    name = name.strip()
    name = re.sub(r'[/\\:*?"<>|]', '_', name)
    name = re.sub(r'\s+', ' ', name)
    if len(name) > max_len:
        name = name[:max_len]
    return name


def inspect_outline(pdf_path: str):
    import fitz

    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    print(f"File: {os.path.basename(pdf_path)}")
    print(f"Total pages: {doc.page_count}")
    print(f"Total outline entries: {len(toc)}")

    if not toc:
        print("\n⚠️  This PDF has no outline/bookmarks.")
        doc.close()
        return

    # Count entries per level
    level_counts = {}
    for level, _, _ in toc:
        level_counts[level] = level_counts.get(level, 0) + 1

    print("\nEntries per level:")
    for lvl in sorted(level_counts):
        print(f"  Level {lvl}: {level_counts[lvl]} entries")

    print("\nOutline structure:")
    for level, title, page in toc:
        indent = "  " * (level - 1)
        print(f"  {indent}[L{level}] p.{page}: {title}")

    doc.close()


def build_page_ranges(toc, total_pages):
    """For each TOC entry, compute (level, title, start_page_1indexed, end_page_1indexed).

    An entry's page range extends until the next entry at the same or a parent level
    (level number <= this entry's level). This ensures that child entries are included
    within their parent's range. For example, an L1 entry spans all its L2 children.
    """
    entries = []
    for i, (level, title, page) in enumerate(toc):
        end_page = total_pages
        for j in range(i + 1, len(toc)):
            next_level, _, next_page = toc[j]
            # Only end at a sibling or parent (same or higher-priority level)
            if next_level <= level and next_page > page:
                end_page = next_page - 1
                break
            elif next_level <= level and next_page == page:
                # Same level, same page — this entry gets just this page
                end_page = page
                continue
        entries.append((level, title.strip(), page, end_page))
    return entries


def split_pdf(pdf_path: str, folder_level: int, split_level: int,
              output_dir: str, numbering: bool, flatten: bool,
              include_prefix: bool):
    import fitz

    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    total_pages = doc.page_count

    if not toc:
        print("⚠️  This PDF has no outline/bookmarks. Cannot split.")
        doc.close()
        sys.exit(1)

    # Check if requested split_level exists
    available_levels = sorted(set(lvl for lvl, _, _ in toc))
    if split_level not in available_levels:
        max_level = max(available_levels)
        if split_level > max_level:
            print(f"⚠️  Outline only has levels {available_levels}. "
                  f"Falling back to split-level {max_level}.")
            split_level = max_level
            if folder_level >= split_level:
                folder_level = 0

    entries_with_ranges = build_page_ranges(toc, total_pages)

    # Build hierarchy: group split-level entries under their folder-level parents
    # Structure: [(folder_name, [(file_title, start, end), ...])]
    sections = []
    current_folder = None
    current_files = []

    # Handle prefix pages (before first bookmark)
    first_page = toc[0][2]
    prefix_pages = None
    if include_prefix and first_page > 1:
        prefix_pages = (1, first_page - 1)

    for level, title, start, end in entries_with_ranges:
        if folder_level > 0 and level == folder_level:
            if current_folder is not None or current_files:
                sections.append((current_folder, current_files))
            current_folder = title
            current_files = []
            # If folder_level == split_level, each folder-level entry is also a PDF
            if folder_level == split_level:
                current_files.append((title, start, end))
        elif level == split_level:
            current_files.append((title, start, end))

    # Don't forget the last section
    if current_folder is not None or current_files:
        sections.append((current_folder, current_files))

    # If no folder level, wrap everything in a single None-folder
    if folder_level == 0 and not sections:
        all_split = [(t, s, e) for lv, t, s, e in entries_with_ranges if lv == split_level]
        sections = [(None, all_split)]

    os.makedirs(output_dir, exist_ok=True)

    file_count = 0
    summary = []

    # Save prefix pages
    if prefix_pages:
        ps, pe = prefix_pages
        prefix_name = "00_前言.pdf" if numbering else "前言.pdf"
        if flatten or folder_level == 0:
            prefix_path = os.path.join(output_dir, prefix_name)
        else:
            # Put in root of output dir
            prefix_path = os.path.join(output_dir, prefix_name)

        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=ps - 1, to_page=pe - 1)
        new_doc.save(prefix_path)
        new_doc.close()
        file_count += 1
        summary.append(f"  📄 {prefix_name} ({pe - ps + 1} pages, p.{ps}-{pe})")

    for folder_idx, (folder_name, files) in enumerate(sections):
        if folder_name and not flatten:
            folder_safe = sanitize_filename(folder_name)
            if numbering:
                folder_dir_name = f"{folder_idx + 1:02d}_{folder_safe}"
            else:
                folder_dir_name = folder_safe
            folder_path = os.path.join(output_dir, folder_dir_name)
            os.makedirs(folder_path, exist_ok=True)
            summary.append(f"\n📁 {folder_dir_name}/")
        else:
            folder_path = output_dir
            folder_dir_name = None
            if folder_name and flatten:
                # We'll use folder name as prefix in flat mode
                pass

        for file_idx, (file_title, start, end) in enumerate(files):
            file_safe = sanitize_filename(file_title)

            if flatten and folder_name:
                folder_safe = sanitize_filename(folder_name)
                if numbering:
                    filename = f"{folder_idx + 1:02d}-{file_idx + 1:02d}_{folder_safe}_{file_safe}.pdf"
                else:
                    filename = f"{folder_safe}_{file_safe}.pdf"
            else:
                if numbering:
                    filename = f"{file_idx + 1:02d}_{file_safe}.pdf"
                else:
                    filename = f"{file_safe}.pdf"

            filepath = os.path.join(folder_path, filename)

            # Extract pages (fitz is 0-indexed)
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
            new_doc.save(filepath)
            new_doc.close()

            page_count = end - start + 1
            file_count += 1
            summary.append(f"  📄 {filename} ({page_count} pages, p.{start}-{end})")

    doc.close()

    # Print summary
    print(f"\n✅ Split complete! {file_count} files created.")
    print(f"📂 Output: {output_dir}\n")
    for line in summary:
        print(line)


def main():
    parser = argparse.ArgumentParser(
        description="Split a PDF by its outline (bookmarks/TOC)."
    )
    parser.add_argument("pdf_path", help="Path to the input PDF file")
    parser.add_argument("--inspect", action="store_true",
                        help="Only print the outline structure, don't split")
    parser.add_argument("--folder-level", type=int, default=1,
                        help="Outline level for folders (default: 1, 0 = no folders)")
    parser.add_argument("--split-level", type=int, default=2,
                        help="Outline level for individual PDFs (default: 2)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: <input>-拆分/)")
    parser.add_argument("--no-numbering", action="store_true",
                        help="Don't prefix filenames with sequential numbers")
    parser.add_argument("--flatten", action="store_true",
                        help="No subfolders, all PDFs flat with hierarchy in filename")
    parser.add_argument("--no-prefix", action="store_true",
                        help="Skip pages before the first bookmark")

    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"Error: File not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    ensure_pymupdf()

    if args.inspect:
        inspect_outline(args.pdf_path)
        return

    # Default output dir
    if args.output_dir is None:
        base = os.path.splitext(args.pdf_path)[0]
        args.output_dir = base + "-拆分"

    # Validate levels
    if args.folder_level < 0:
        print("Error: --folder-level must be >= 0", file=sys.stderr)
        sys.exit(1)
    if args.split_level < 1:
        print("Error: --split-level must be >= 1", file=sys.stderr)
        sys.exit(1)
    if args.folder_level > 0 and args.folder_level >= args.split_level:
        print("Error: --folder-level must be less than --split-level (or 0 for no folders)",
              file=sys.stderr)
        sys.exit(1)

    split_pdf(
        pdf_path=args.pdf_path,
        folder_level=args.folder_level,
        split_level=args.split_level,
        output_dir=args.output_dir,
        numbering=not args.no_numbering,
        flatten=args.flatten,
        include_prefix=not args.no_prefix,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Extract advisor feedback from .docx to .md for token-efficient reading."""

import argparse
import glob as glob_mod
import json
import os
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime


# Word XML namespace
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def get_text_from_element(elem):
    """Recursively extract all text from w:t and w:delText elements."""
    texts = []
    for child in elem.iter():
        if child.tag == f"{W_NS}t" or child.tag == f"{W_NS}delText":
            if child.text:
                texts.append(child.text)
    return "".join(texts)


def get_run_text(elem):
    """Extract text only from w:t elements (not delText)."""
    texts = []
    for t in elem.iter(f"{W_NS}t"):
        if t.text:
            texts.append(t.text)
    return "".join(texts)


def extract_tracked_changes(doc_root):
    """Extract insertions and deletions from tracked changes."""
    insertions = []
    deletions = []

    for ins in doc_root.iter(f"{W_NS}ins"):
        author = ins.get(f"{W_NS}author", "Unknown")
        date = ins.get(f"{W_NS}date", "")
        text = get_run_text(ins)
        if text.strip():
            insertions.append({
                "author": author,
                "date": date[:10] if date else "",
                "text": text.strip(),
            })

    for dele in doc_root.iter(f"{W_NS}del"):
        author = dele.get(f"{W_NS}author", "Unknown")
        date = dele.get(f"{W_NS}date", "")
        text = get_text_from_element(dele)
        if text.strip():
            deletions.append({
                "author": author,
                "date": date[:10] if date else "",
                "text": text.strip(),
            })

    return insertions, deletions


def extract_comments(zip_file):
    """Extract comments from word/comments.xml."""
    comments = {}
    try:
        with zip_file.open("word/comments.xml") as f:
            tree = ET.parse(f)
            root = tree.getroot()
            for comment in root.iter(f"{W_NS}comment"):
                cid = comment.get(f"{W_NS}id", "")
                author = comment.get(f"{W_NS}author", "Unknown")
                date = comment.get(f"{W_NS}date", "")
                text = get_run_text(comment)
                if text.strip():
                    comments[cid] = {
                        "author": author,
                        "date": date[:10] if date else "",
                        "text": text.strip(),
                        "context": "",
                    }
    except KeyError:
        pass  # No comments.xml

    return comments


def extract_comment_contexts(doc_root, comments):
    """Find the text that each comment refers to."""
    # Build a map of comment range starts/ends
    body = doc_root.find(f"{W_NS}body")
    if body is None:
        return

    # Walk through paragraphs to find comment ranges
    for para in body.iter(f"{W_NS}p"):
        para_text = get_run_text(para)
        # Check if this paragraph contains any comment markers
        for start in para.iter(f"{W_NS}commentRangeStart"):
            cid = start.get(f"{W_NS}id", "")
            if cid in comments:
                # Use the paragraph text as context (simplified approach)
                context = para_text.strip()
                if context and len(context) > 80:
                    context = context[:80] + "..."
                comments[cid]["context"] = context


def extract_plain_text(doc_root):
    """Extract plain paragraph text (excluding tracked changes content)."""
    paragraphs = []
    body = doc_root.find(f"{W_NS}body")
    if body is None:
        return paragraphs

    for para in body.findall(f"{W_NS}p"):
        # Skip paragraphs that are entirely inside tracked changes
        has_normal_text = False
        text_parts = []
        for run in para.findall(f"{W_NS}r"):
            # ElementTree gives no parent pointer, so a run cannot be tested
            # for being inside an ins/del directly; the paragraph-level check
            # below is what actually excludes tracked-change text.
            run_text = get_run_text(run)
            if run_text.strip():
                text_parts.append(run_text)
                has_normal_text = True

        if has_normal_text:
            full_text = "".join(text_parts).strip()
            if full_text:
                paragraphs.append(full_text)

    return paragraphs


def write_structured_json(docx_path, insertions, deletions, comments, paragraphs, output_path, plan_version=None):
    """Write structured JSON for machine-readable feedback processing."""
    json_path = output_path.replace('.md', '_structured.json')

    items = []
    item_id = 1

    for ins in insertions:
        items.append({
            "id": f"FB-{item_id:03d}",
            "source": "insertion",
            "raw_text": ins["text"],
            "context": "",
            "author": ins["author"],
            "date": ins["date"],
            "category": None,
            "affected_steps": [],
            "priority": None,
            "config_changes": [],
            "resolution": None
        })
        item_id += 1

    for dele in deletions:
        items.append({
            "id": f"FB-{item_id:03d}",
            "source": "deletion",
            "raw_text": dele["text"],
            "context": "",
            "author": dele["author"],
            "date": dele["date"],
            "category": None,
            "affected_steps": [],
            "priority": None,
            "config_changes": [],
            "resolution": None
        })
        item_id += 1

    for cid, comment in comments.items():
        items.append({
            "id": f"FB-{item_id:03d}",
            "source": "comment",
            "raw_text": comment["text"],
            "context": comment.get("context", ""),
            "author": comment["author"],
            "date": comment["date"],
            "category": None,
            "affected_steps": [],
            "priority": None,
            "config_changes": [],
            "resolution": None
        })
        item_id += 1

    for para in paragraphs:
        if len(para.strip()) > 10:  # Skip very short fragments
            items.append({
                "id": f"FB-{item_id:03d}",
                "source": "text",
                "raw_text": para.strip(),
                "context": "",
                "author": "Unknown",
                "date": "",
                "category": None,
                "affected_steps": [],
                "priority": None,
                "config_changes": [],
                "resolution": None
            })
            item_id += 1

    structured = {
        "version": plan_version,
        "feedback_file": os.path.basename(docx_path),
        "extracted_at": datetime.now().isoformat(),
        "plan_version_at_extraction": None,  # Will be filled by Claude
        "items": items,
        "summary": {
            "total_items": len(items),
            "by_source": {
                "comment": sum(1 for i in items if i["source"] == "comment"),
                "insertion": sum(1 for i in items if i["source"] == "insertion"),
                "deletion": sum(1 for i in items if i["source"] == "deletion"),
                "text": sum(1 for i in items if i["source"] == "text"),
            },
            "by_category": {}
        }
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False)

    print(f"Structured JSON: {json_path}")
    return json_path


def backup_version(plan_path):
    """Backup current plan and outputs before feedback modification, then bump the version.

    The version bump is what makes this safe to call more than once. Before
    2026-08-11 the plan version was never incremented, so a second feedback round
    found `research_plan_v1.json` and `v1/` already present and **silently skipped
    the backup entirely** — the round-1 state was reported as saved but was not.
    """
    if not os.path.exists(plan_path):
        return None

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    version = plan.get("version", 1)
    output_dir = plan.get("output_dir", "")

    if not output_dir or not os.path.isdir(output_dir):
        print(f"Warning: output_dir not found: {output_dir}")
        return version

    # Backup plan file. An existing snapshot for this version means a previous
    # backup at the same version never got bumped — refuse rather than skip
    # silently, because "skipped" reads as "already safe" and it is not.
    backup_plan = os.path.join(os.path.dirname(plan_path), f"research_plan_v{version}.json")
    if os.path.exists(backup_plan):
        print(f"ERROR: {backup_plan} already exists but the plan is still at version {version}.")
        print(f"       Refusing to overwrite a previous snapshot. Inspect the v{version} backup,")
        print(f"       then set \"version\" in {plan_path} to the correct number and re-run.")
        sys.exit(3)
    shutil.copy2(plan_path, backup_plan)
    print(f"  Plan backup: {backup_plan}")

    # Backup output files
    backup_dir = os.path.join(output_dir, f"v{version}")
    if not os.path.isdir(backup_dir):
        os.makedirs(backup_dir, exist_ok=True)
        # Copy all output files
        for ext in ["*.xlsx", "*.png", "*.docx", "*.csv"]:
            for fpath in glob_mod.glob(os.path.join(output_dir, ext)):
                dest = os.path.join(backup_dir, os.path.basename(fpath))
                shutil.copy2(fpath, dest)
        # Backup configs
        config_dir = os.path.join(output_dir, "configs")
        if os.path.isdir(config_dir):
            backup_config_dir = os.path.join(backup_dir, "configs")
            os.makedirs(backup_config_dir, exist_ok=True)
            for fpath in glob_mod.glob(os.path.join(config_dir, "*.json")):
                shutil.copy2(fpath, os.path.join(backup_config_dir, os.path.basename(fpath)))

        n_files = len(os.listdir(backup_dir))
        print(f"  Output backup: {backup_dir} ({n_files} files)")

    # Bump the version and record it, so the next round backs up to v{N+1}
    # instead of colliding with this one.
    plan["version"] = version + 1
    plan.setdefault("version_history", []).append({
        "version": version + 1,
        "created_at": datetime.now().isoformat(),
        "reason": "advisor feedback round",
        "backed_up_from": f"v{version}",
    })
    plan["pipeline_state"] = "feedback"
    tmp = plan_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    os.replace(tmp, plan_path)
    print(f"  Plan version: v{version} → v{version + 1} (pipeline_state=feedback)")

    return version


def process_feedback(docx_path, output_path, plan_path=None):
    """Main function to process .docx feedback into .md."""
    # Validate input
    if not os.path.exists(docx_path):
        print(f"Error: File not found: {docx_path}")
        sys.exit(1)

    if not zipfile.is_zipfile(docx_path):
        print(f"Error: Not a valid .docx file: {docx_path}")
        sys.exit(1)

    try:
        zf = zipfile.ZipFile(docx_path, "r")
    except zipfile.BadZipFile:
        print(f"Error: Cannot open .docx file: {docx_path}")
        sys.exit(1)

    # Check for document.xml
    if "word/document.xml" not in zf.namelist():
        print(f"Error: Missing word/document.xml in {docx_path}")
        zf.close()
        sys.exit(1)

    # Parse document.xml
    with zf.open("word/document.xml") as f:
        doc_tree = ET.parse(f)
        doc_root = doc_tree.getroot()

    # Extract all components
    insertions, deletions = extract_tracked_changes(doc_root)
    comments = extract_comments(zf)
    extract_comment_contexts(doc_root, comments)
    paragraphs = extract_plain_text(doc_root)

    zf.close()

    # Build markdown output
    filename = os.path.basename(docx_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"# Advisor Feedback — {filename}")
    lines.append(f"Extracted: {now}")
    lines.append("")

    # Tracked Changes
    lines.append("## Tracked Changes")
    lines.append("")
    lines.append("### Insertions")
    if insertions:
        for item in insertions:
            date_str = f", {item['date']}" if item["date"] else ""
            lines.append(f'- **[{item["author"]}{date_str}]**: "{item["text"]}"')
    else:
        lines.append("None found.")
    lines.append("")

    lines.append("### Deletions")
    if deletions:
        for item in deletions:
            date_str = f", {item['date']}" if item["date"] else ""
            lines.append(f'- **[{item["author"]}{date_str}]**: ~~{item["text"]}~~')
    else:
        lines.append("None found.")
    lines.append("")

    # Comments
    lines.append("## Comments")
    lines.append("")
    if comments:
        for i, (cid, comment) in enumerate(comments.items(), 1):
            ctx = f' (on "{comment["context"]}")' if comment["context"] else ""
            lines.append(f'{i}. **[{comment["author"]}]**{ctx}: {comment["text"]}')
    else:
        lines.append("None found.")
    lines.append("")

    # Text Feedback
    lines.append("## Text Feedback")
    lines.append("")
    if paragraphs:
        for para in paragraphs:
            lines.append(f"> {para}")
            lines.append(">")
    else:
        lines.append("None found.")
    lines.append("")

    # Write output
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Feedback extracted to: {output_path}")
    print(f"  Insertions: {len(insertions)}")
    print(f"  Deletions: {len(deletions)}")
    print(f"  Comments: {len(comments)}")
    print(f"  Text paragraphs: {len(paragraphs)}")

    # Write structured JSON alongside the .md file
    plan_version = None
    if plan_path and os.path.exists(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
            plan_version = plan_data.get("version", None)
        except (json.JSONDecodeError, IOError):
            pass

    write_structured_json(docx_path, insertions, deletions, comments, paragraphs, output_path, plan_version=plan_version)

    # Feedback round summary
    if plan_path and os.path.exists(plan_path):
        print(f"\n  Feedback round summary:")
        print(f"  Items extracted: {len(insertions)} insertions, {len(deletions)} deletions, {len(comments)} comments")
        print(f"  Ready for classification (Step B of Feedback Audit Protocol)")


def main():
    parser = argparse.ArgumentParser(description="Extract advisor feedback from .docx to .md")
    parser.add_argument("docx_path", help="Path to the .docx feedback file")
    parser.add_argument("--output", "-o", required=True, help="Output .md file path")
    parser.add_argument("--plan-path", help="Path to research_plan.json for version backup")
    parser.add_argument("--backup", action="store_true", help="Backup current version before processing")
    args = parser.parse_args()

    # Backup current version if requested
    if args.backup and args.plan_path:
        backup_version(args.plan_path)

    process_feedback(args.docx_path, args.output, plan_path=args.plan_path)


if __name__ == "__main__":
    main()

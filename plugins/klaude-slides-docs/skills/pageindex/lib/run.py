"""CLI dispatcher for /pageindex skill commands.

Subcommands:
  index <pdf-path>            — build tree index + cache in ~/PageIndex/indexes/
  ask <pdf-name> <question>   — locate-then-answer via 2-pass LLM Q&A
  list [<topic>]              — list indexed docs (optionally filter by topic)
  search <keyword>            — find sections matching keyword across all indexed docs
  remove <pdf-name>           — drop index + meta entry
  switch-llm <oauth|api>      — flip ~/PageIndex/.env between OAuth bridge and Anthropic API key
  doctor                      — diagnose env (claude CLI, venv, deps, .env settings)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path

from dotenv import load_dotenv

PAGEINDEX_HOME = Path.home() / "PageIndex"
ENV_FILE = PAGEINDEX_HOME / ".env"
REPO_DIR = PAGEINDEX_HOME / "repo"
VENV_PYTHON = PAGEINDEX_HOME / ".venv" / "bin" / "python"

sys.path.insert(0, str(Path(__file__).parent))
import library  # noqa: E402

# Load .env so model overrides apply.
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

DEFAULT_INDEX_MODEL = os.environ.get("PAGEINDEX_MODEL", "claude-code/haiku")
DEFAULT_RETRIEVE_MODEL = os.environ.get("PAGEINDEX_RETRIEVE_MODEL", DEFAULT_INDEX_MODEL)


def _ensure_venv() -> None:
    """Re-exec under the PageIndex venv if not already there."""
    if sys.executable == str(VENV_PYTHON):
        return
    if not VENV_PYTHON.exists():
        print(
            f"ERROR: PageIndex venv not found at {VENV_PYTHON}. "
            f"Re-run install: python3 -m venv {PAGEINDEX_HOME}/.venv && "
            f"{PAGEINDEX_HOME}/.venv/bin/pip install -r {REPO_DIR}/requirements.txt",
            file=sys.stderr,
        )
        sys.exit(2)
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]])


def _register_bridge() -> None:
    """Register the claude-code litellm provider so an unpatched upstream PageIndex works."""
    os.environ.setdefault("OPENAI_API_KEY", "claude-code-bridge")  # litellm sentinel; not a real key
    try:
        from claude_code_provider import register_claude_code

        register_claude_code()
    except Exception as exc:  # pragma: no cover
        print(f"WARN: claude-code provider registration failed: {exc}", file=sys.stderr)


def _client():
    sys.path.insert(0, str(REPO_DIR))
    from pageindex import PageIndexClient  # noqa: E402

    library.ensure_dirs()
    return PageIndexClient(
        workspace=str(library.INDEXES_DIR),
        model=DEFAULT_INDEX_MODEL,
        retrieve_model=DEFAULT_RETRIEVE_MODEL,
    )


def cmd_index(args: argparse.Namespace) -> int:
    src = Path(args.pdf_path).expanduser().resolve()
    if not src.exists():
        print(f"ERROR: file not found: {src}", file=sys.stderr)
        return 1
    if src.suffix.lower() not in {".pdf", ".md", ".markdown"}:
        print(f"ERROR: only .pdf and .md/.markdown supported, got {src.suffix}", file=sys.stderr)
        return 1

    topic = args.topic or library.classify_topic(src)
    stashed = library.stash_pdf(src, topic=topic)
    print(f"Topic: {topic}")
    print(f"Library copy: {stashed}")
    print(f"Model: {DEFAULT_INDEX_MODEL}")
    print(f"Indexing... (this may take several minutes for long PDFs)")

    client = _client()
    doc_id = client.index(str(stashed))
    print(f"\n✓ Indexed. doc_id: {doc_id}")
    print(f"Cached at: {library.INDEXES_DIR / f'{doc_id}.json'}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    library.ensure_dirs()
    indexed = library.list_indexed()
    on_disk = library.topic_summary()

    if not indexed and not any(on_disk.values()):
        print("Library is empty. Drop PDFs into ~/PageIndex/library/<topic>/ then run /pageindex index <path>.")
        return 0

    if args.topic:
        filt = args.topic
        on_disk = {filt: on_disk.get(filt, [])}

    print("=== Indexed (queryable) ===")
    if indexed:
        for doc_id, entry in indexed.items():
            name = entry.get("doc_name") or Path(entry.get("path", "?")).name
            pages = entry.get("page_count") or entry.get("line_count", "?")
            print(f"  [{doc_id[:8]}] {name}  ({pages} pages)")
            desc = entry.get("doc_description", "")
            if desc:
                print(f"           {textwrap.shorten(desc, width=100)}")
    else:
        print("  (none)")

    print("\n=== Library files (on disk) ===")
    for topic, files in sorted(on_disk.items()):
        if not files:
            continue
        print(f"  {topic}/  ({len(files)} files)")
        for f in files:
            print(f"    - {f}")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    found = library.find_doc_id(args.pdf_name)
    if not found:
        print(f"ERROR: no indexed doc matches '{args.pdf_name}'. Run /pageindex list to see options.", file=sys.stderr)
        return 1
    doc_id, entry = found
    print(f"Doc: {entry.get('doc_name', 'unknown')}  (id={doc_id[:8]}, pages={entry.get('page_count', '?')})")

    client = _client()
    structure_json = client.get_document_structure(doc_id)
    structure = json.loads(structure_json)

    sys.path.insert(0, str(REPO_DIR))
    import litellm  # noqa: E402

    locate_prompt = textwrap.dedent(
        f"""\
        You will help locate the most relevant section(s) of a document for a user question.

        Document tree (titles + page indexes only):
        {json.dumps(_strip_to_titles(structure), ensure_ascii=False, indent=1)[:8000]}

        User question: {args.question}

        Reply with strict JSON only, no markdown fence:
        {{"pages": "<single page or comma list or range like 5-9>", "rationale": "<one short sentence>"}}
        """
    )
    print("[1/2] locating relevant pages...", flush=True)
    locate_resp = litellm.completion(
        model=DEFAULT_RETRIEVE_MODEL.removeprefix("litellm/"),
        messages=[{"role": "user", "content": locate_prompt}],
        temperature=0,
    )
    raw = locate_resp.choices[0].message.content.strip()
    pages, rationale = _parse_locate(raw)
    print(f"      → pages={pages}  ({rationale})")

    content = client.get_page_content(doc_id, pages)
    answer_prompt = textwrap.dedent(
        f"""\
        Answer the user question using ONLY the provided document excerpt. Cite page numbers in [p.X] format.

        Excerpt (pages {pages}):
        ---
        {content[:60000]}
        ---

        Question: {args.question}

        Answer concisely. If the excerpt does not contain the answer, say so.
        """
    )
    print("[2/2] answering...", flush=True)
    answer_resp = litellm.completion(
        model=DEFAULT_RETRIEVE_MODEL.removeprefix("litellm/"),
        messages=[{"role": "user", "content": answer_prompt}],
        temperature=0,
    )
    print("\n" + "=" * 60)
    print(answer_resp.choices[0].message.content)
    print("=" * 60)
    print(f"Source: {entry.get('doc_name', '')} pages {pages}")
    return 0


def _strip_to_titles(node):
    """Recursively keep only title + start_index/end_index — drop text/summary to fit prompt."""
    if isinstance(node, list):
        return [_strip_to_titles(n) for n in node]
    if isinstance(node, dict):
        out = {k: node[k] for k in ("title", "start_index", "end_index", "node_id") if k in node}
        if node.get("nodes"):
            out["nodes"] = _strip_to_titles(node["nodes"])
        return out
    return node


def _parse_locate(raw: str) -> tuple[str, str]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        parsed = json.loads(raw)
        return str(parsed.get("pages", "1")), str(parsed.get("rationale", ""))
    except json.JSONDecodeError:
        # Fallback: try to grab a number range
        import re

        match = re.search(r"\d+(?:[-,]\d+)*", raw)
        return (match.group(0) if match else "1"), "(parse fallback)"


def cmd_search(args: argparse.Namespace) -> int:
    library.ensure_dirs()
    indexed = library.list_indexed()
    if not indexed:
        print("No indexed docs. Index something first.")
        return 0
    keyword = args.keyword.lower()
    hits: list[tuple[str, str, str]] = []
    for doc_id, entry in indexed.items():
        full = library.INDEXES_DIR / f"{doc_id}.json"
        if not full.exists():
            continue
        try:
            doc = json.loads(full.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for node in _flatten(doc.get("structure", [])):
            haystack = " ".join(
                str(node.get(k, "")) for k in ("title", "summary", "prefix_summary")
            ).lower()
            if keyword in haystack:
                hits.append(
                    (
                        entry.get("doc_name", doc_id[:8]),
                        f"p.{node.get('start_index', '?')}-{node.get('end_index', '?')}",
                        node.get("title", ""),
                    )
                )
    if not hits:
        print(f"No matches for '{args.keyword}'.")
        return 0
    print(f"=== {len(hits)} matches for '{args.keyword}' ===")
    for doc_name, page_range, title in hits:
        print(f"  [{doc_name}]  {page_range}  {title}")
    return 0


def _flatten(structure):
    if isinstance(structure, list):
        for item in structure:
            yield from _flatten(item)
    elif isinstance(structure, dict):
        yield structure
        if "nodes" in structure and structure["nodes"]:
            yield from _flatten(structure["nodes"])


def cmd_remove(args: argparse.Namespace) -> int:
    found = library.find_doc_id(args.pdf_name)
    if not found:
        print(f"ERROR: no indexed doc matches '{args.pdf_name}'.", file=sys.stderr)
        return 1
    doc_id, entry = found
    if library.remove_doc(doc_id):
        print(f"Removed index for '{entry.get('doc_name')}' (doc_id {doc_id[:8]}).")
        print(f"Library PDF still at: {entry.get('path', '?')}")
        return 0
    return 1


def cmd_switch_llm(args: argparse.Namespace) -> int:
    if args.target == "oauth":
        new_env = textwrap.dedent(
            """\
            # PageIndex LLM auth — Claude Code OAuth bridge (default)
            PAGEINDEX_MODEL=claude-code/haiku
            PAGEINDEX_RETRIEVE_MODEL=claude-code/haiku
            """
        )
        print("Switched to OAuth bridge (claude-code/haiku, no API key needed).")
    elif args.target == "api":
        existing_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not existing_key:
            print(
                "WARN: ANTHROPIC_API_KEY not set in current shell. "
                "Edit ~/PageIndex/.env after this command and add: ANTHROPIC_API_KEY=sk-ant-...",
                file=sys.stderr,
            )
        new_env = textwrap.dedent(
            f"""\
            # PageIndex LLM auth — Anthropic API key
            ANTHROPIC_API_KEY={existing_key or 'sk-ant-REPLACE-ME'}
            PAGEINDEX_MODEL=anthropic/claude-haiku-5-5
            PAGEINDEX_RETRIEVE_MODEL=anthropic/claude-haiku-5-5
            """
        )
        print("Switched to Anthropic API key (anthropic/claude-haiku-5-5).")
    else:
        print(f"Unknown target: {args.target}. Use 'oauth' or 'api'.", file=sys.stderr)
        return 1
    ENV_FILE.write_text(new_env, encoding="utf-8")
    print(f"Updated {ENV_FILE}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import subprocess

    print("=== PageIndex environment doctor ===")
    print(f"PageIndex home: {PAGEINDEX_HOME}  exists={PAGEINDEX_HOME.exists()}")
    print(f"venv python:    {VENV_PYTHON}  exists={VENV_PYTHON.exists()}")
    print(f"repo:           {REPO_DIR}  exists={REPO_DIR.exists()}")
    print(f".env:           {ENV_FILE}  exists={ENV_FILE.exists()}")
    print(f"\nIndex model:    {DEFAULT_INDEX_MODEL}")
    print(f"Retrieve model: {DEFAULT_RETRIEVE_MODEL}")

    print("\n--- claude CLI ---")
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10)
        print(f"  version: {out.stdout.strip() or out.stderr.strip()}")
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"  ERROR: {exc}")

    print("\n--- venv deps ---")
    if VENV_PYTHON.exists():
        out = subprocess.run(
            [str(VENV_PYTHON), "-c", "import litellm, pymupdf, PyPDF2; print('OK')"],
            capture_output=True,
            text=True,
        )
        print(f"  {out.stdout.strip() or out.stderr.strip()}")
    print("\n--- library counts ---")
    for topic, files in library.topic_summary().items():
        print(f"  {topic}: {len(files)} files")
    indexed = library.list_indexed()
    print(f"  indexed total: {len(indexed)}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pageindex")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="Index a PDF/Markdown")
    p.add_argument("pdf_path")
    p.add_argument("--topic", choices=library.KNOWN_TOPICS, default=None)

    p = sub.add_parser("ask", help="Ask a question about an indexed doc")
    p.add_argument("pdf_name")
    p.add_argument("question", nargs="+")

    p = sub.add_parser("list", help="List indexed docs and library files")
    p.add_argument("topic", nargs="?", default=None, choices=library.KNOWN_TOPICS)

    p = sub.add_parser("search", help="Keyword search across indexed docs")
    p.add_argument("keyword")

    p = sub.add_parser("remove", help="Drop index + meta entry for a doc")
    p.add_argument("pdf_name")

    p = sub.add_parser("switch-llm", help="Toggle OAuth bridge vs API key")
    p.add_argument("target", choices=["oauth", "api"])

    sub.add_parser("doctor", help="Diagnose environment")

    args = parser.parse_args(argv)
    if hasattr(args, "question"):
        args.question = " ".join(args.question)

    handlers = {
        "index": cmd_index,
        "ask": cmd_ask,
        "list": cmd_list,
        "search": cmd_search,
        "remove": cmd_remove,
        "switch-llm": cmd_switch_llm,
        "doctor": cmd_doctor,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    if not sys.argv[1:] or sys.argv[1] != "doctor":
        _ensure_venv()
        _register_bridge()
    sys.exit(main(sys.argv[1:]))

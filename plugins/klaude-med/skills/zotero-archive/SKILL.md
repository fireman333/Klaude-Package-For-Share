---
name: zotero-archive
description: "zotero-archive: standalone Zotero reference-pool ops hub. Subcommands: `archive` (file an existing report's cited literature into Zotero without re-running its source skill), `tidy` (dedupe, missing-DOI report, re-index), `export` (pull a collection out as .bib/bibliography.json). Wraps per-skill adapters + lib/zotero_archive/EXECUTION.md + zotero MCP. Trigger: archive to Zotero, 歸檔到 Zotero, 補歸檔, 把這份報告丟進 Zotero, tidy Zotero, 清理 Zotero 重複, dedupe Zotero, export Zotero collection, Zotero 匯出 bib, /zotero-archive, /zo."
---

# zotero-archive — Zotero reference-pool operations hub

Standalone hub over the report-skill adapters + the shared
`lib/zotero_archive/` core and **execution playbook**
(`${CLAUDE_SKILL_DIR}/lib/zotero_archive/EXECUTION.md`) + the `zotero` MCP
（選用：需要 Zotero 桌面版 + zotero MCP server；沒有就無法使用本 skill，請先安裝）。
Curator-style: never deletes anything without showing it first; archiving always
goes through the show→confirm gate.

**Precondition (all subcommands):** the `zotero` MCP must be connected AND the
**Zotero desktop app must be running** (the 54yyyu server reads via the local API
on `localhost:23119`; if it's closed you get `Connection refused`). If a call
returns connection-refused, tell the user to open Zotero and stop — do not work
around it.

## Subcommands

| Invocation | Does |
|---|---|
| `/zotero-archive archive [<dir>]` | detect the report artifact in `<dir>` (default cwd) → run its adapter → file into Zotero |
| `/zotero-archive tidy [<collection>]` | find/merge duplicates, report missing DOIs, re-index |
| `/zotero-archive export <collection> [--format bib\|json]` | dump a collection as `.bib` / `bibliography.json` |

Natural language: 「補歸檔這份報告」「把這個 SR 丟進 Zotero」→ `archive`;
「清理 Zotero 重複」「Zotero 去重」→ `tidy`; 「把這個 collection 匯出成 bib」→ `export`.

---

## Subcommand 1 — `archive [<dir>]`

Archive the cited literature of an **already-produced** report without re-running
its source skill. The per-skill steps (journal-club-discussion-pptx, deep-research SR step,
case-discussion-pptx) call the same adapters + playbook
— this subcommand is the ad-hoc / retroactive entry.

1. **Detect the artifact**:
   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/detect_artifact.py <dir>
   ```
   It prints the exact adapter command for the artifact it finds (journal club / SR / case). **Ambiguous** (multiple artifacts) → it lists all
   and STOPs; ask the user which report. **None** → it exits non-zero with the
   expected-files list; tell the user no recognized artifact is present.
2. **Run the printed adapter command** (fill in the `--topic` placeholder; add
   `--date YYYY-MM` only if you don't want the current month). It writes the plan
   JSON to `/tmp/zotero_plan.json`. Deterministic; does not touch Zotero.
   - For case the adapter needs an agent-built input
     (`discussion_trail.json`) — if the
     dir only has raw artifacts, build that input first per the source skill's step.
3. **Execute the plan** by following
   **`${CLAUDE_SKILL_DIR}/lib/zotero_archive/EXECUTION.md`** verbatim
   (create-or-reuse parent → show→confirm HARD GATE → lookup-before-add filing →
   `zotero_update_search_database`). The plan's `parent` field names the top-level
   collection.

## Subcommand 2 — `tidy [<collection>]`

Keep the growing reference pool clean. All read-first; merges only after the user
confirms the keeper.

1. **Find duplicates**: `zotero_find_duplicates(method="doi"[, collection_key=...])`
   — `doi` is the safest method for review. Whole-library scans refuse > 5,000
   items, so pass a `collection_key` (resolve via `zotero_search_collections`) on
   large libraries.
2. **Show the groups** (keys + titles + DOIs + dateAdded) and let the user pick
   the keeper per group. **Do not merge without confirmation** — merging is
   destructive.
3. **Merge confirmed groups**: `zotero_merge_duplicates(keeper_key=...,
   duplicate_keys=[...])` per group.
4. **Missing-DOI report**: list items in scope whose DOI is empty (helps the user
   run the DOI Manager / shortDOI plugin or fix by hand). Read-only — just report.
5. **Re-index**: `zotero_update_search_database` (incremental) so the semantic DB
   reflects the merges.

## Subcommand 3 — `export <collection> [--format bib|json]`

Pull a collection back out as structured references — to seed a new manuscript /
JC, or to feed `/endnote-import`. Closes the archive → reuse loop.

1. Resolve the collection key: `zotero_search_collections(<name>)` (exact name; if
   ≥2 match, ask which).
2. List item keys: `zotero_get_collection_items(collection_key=..., detail="keys_only")`.
   (The default markdown listing omits DOI — always go item-by-item via
   `zotero_get_item_metadata` for export, which IS the structured source.)
3. For each item key, call `zotero_get_item_metadata(item_key, format=...)` and assemble:
   - `--format bib` (default; for `/endnote-import` or seeding a new report) →
     `format="bibtex"` returns a complete entry (DOI / journal / volume / pages +
     a Better-BibTeX citation key). Concatenate the entries into `references.bib`
     — no hand-rolled BibTeX needed.
   - `--format json` → `format="json"` returns the raw Zotero record; map each to
     the canonical `bibliography.json` schema (`entries[]` with `bib_key` / `pmid`
     / `doi` / `title` / `authors` / `year`) for feeding deep-research.
4. Hand off as the user asked (e.g. `/endnote-import references.bib --project <name>`).

The per-item loop is agent-driven (MCP calls); for a large collection, iterate in
batches. Verified live 2026-06-07: `format="bibtex"` yields clean, DOI-bearing
entries ready to write straight into a `.bib`.

---

## What this skill does NOT do

- Does not delete or merge anything without showing it and getting confirmation.
- Does not re-run the source report skill — it operates on already-produced artifacts / existing collections.
- Does not duplicate the archiving discipline — it points at `lib/zotero_archive/EXECUTION.md` (single source of truth).
- Does not touch EndNote (that's `/endnote-import`); `export` can produce the `.bib` that feeds it.

## Reference files

- `scripts/detect_artifact.py` — artifact → adapter-command detector (archive)
- `lib/zotero_archive/__init__.py` — the plan-building core
- `lib/zotero_archive/EXECUTION.md` — the shared execution playbook

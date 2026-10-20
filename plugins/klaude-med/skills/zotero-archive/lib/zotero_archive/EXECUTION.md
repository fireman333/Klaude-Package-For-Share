# Zotero Archiving — Shared Execution Playbook

The agent-facing half of `zotero-archive/lib/zotero_archive`. The Python core (`__init__.py`)
turns a per-skill adapter spec into a **plan JSON**; this file is how the agent
**executes** that plan against the `zotero` MCP tools. Every report/SR/MA skill's
"Zotero Archiving" step points here so the discipline lives in one place.

A skill's own step only declares the **skill-specific bits**:
- `parent` collection name (Journal Club / Systematic Review / Meta-analysis / Manuscripts)
- which adapter to run (`scripts/zotero_plan*.py …`) → the plan JSON
- what a "section" means (discussion question / synthesis theme / comparison▸theme / IMRaD section)
- whether an EndNote handoff follows (Word/manuscript skills only)

Everything below is identical across skills.

---

## Precondition / skip

`zotero` MCP not connected **OR** the user said "don't archive to Zotero / skip
zotero" → print `[Zotero] skipped` and stop. Not an error. (Delegated invocations
inherit the caller's choice.)

## 0. Build the plan (deterministic, does not touch Zotero)

Run the skill's adapter to produce the plan JSON. Plan shape (from the core):
`parent` / `report_collection` (`<YYYY-MM> <topic>`) / `primary_paper` (may be
`null`) / `sections[]` (`section_id` + `subfolder` + `papers[]`, plus an optional
`group` for 2-level nesting) / `doi_less[]` / `orphan_sections[]` / `stats`.

## 1. Create-or-reuse collections (No Silent Errors)

1. `zotero_get_collections` → find the **root-level** collection whose name is
   **exactly** `parent`. 0 → `zotero_create_collection(name=parent)`; 1 → use its
   key; **≥2 → STOP and ask the user which one** (Zotero allows same-named
   collections on different branches; never guess the parent).
2. Under that parent, find `report_collection` by exact name. exactly 1 → **reuse**
   (re-runs don't rebuild); 0 → `zotero_create_collection(name=report_collection,
   parent_collection=<parent key>)`; ≥2 → STOP and ask.
3. For each section:
   - **No `group`** (single-level) → find a same-named `subfolder` child collection
     directly under `report_collection` (reuse) / else create it.
   - **Has `group`** (2-level, e.g. MA comparison ▸ theme) → first create-or-reuse
     the `group` collection under `report_collection` (same 0/1/≥2 rule), then
     create-or-reuse `subfolder` under that group. Distinct `group` values become
     the mid-level collections; sections sharing a group nest under the same one.

## 2. Confirm before filing (HARD GATE — show→confirm)

Render the plan as one `section → papers` table (primary_paper → 母夾;
each section's paper list; flag `doi_less` rows). Show it **once** for the user to
edit/move/drop. **Do not write until confirmed.** (Auto-classification mis-files;
this family has caught single-center studies mislabeled as registries only via
PubMed cross-check.)

- **`orphan_sections` non-empty** → list them above the table (a citation's
  section reference points to a section that doesn't exist = upstream data
  anomaly). Let the user fold them into a real section or drop them — **never
  silently dump into an `(orphan)` folder**.
- **A title shows as an author string / PMID / `(missing from bibliography: …)`**
  rather than a real title → before confirming, enrich with
  `pubmed_fetch_articles(pmids=[…])` so the user can see what's being filed.

## 3. File each paper (after confirm) — lookup-before-add (idempotent re-runs)

Target collection = `primary_paper` → 母夾; each section's papers → that section's
subfolder (the `group ▸ subfolder` leaf when the section has a `group`). For
every paper:

1. **Look up first**: `zotero_search_items(query=<doi or title>)`, match on
   DOI/PMID → **already in library** → `zotero_manage_collections(item_keys=[existing
   key], add_to=[target_key])` (add the existing item to the collection; don't
   re-create).
2. **Not in library** → in order:
   - has doi → `zotero_add_by_doi(doi, collections=[target_key], attach_mode="auto")`
     (OA full text auto-attached)
   - no doi → `pubmed_convert_ids(pmids=[pmid])` to get a doi → if found, add_by_doi;
     still none → `zotero_add_by_url(url="https://pubmed.ncbi.nlm.nih.gov/<pmid>/",
     collections=[target_key])`
   - no pmid either → record on the skip list and report (never swallow silently)
3. A paper in multiple sections → file in each (multi-membership is normal in Zotero).

**Why lookup-before-add**: collection reuse in step 1 does NOT make item filing
idempotent; without the lookup, re-runs pile up duplicate items. Mop up any
residual duplicates with DOI Manager / `zotero_find_duplicates`.

## 4. Index + wrap up

`zotero_update_search_database` (incremental) → print the collection tree + the
skip list + the no-full-text list.

> **Read-after-write lag (hybrid mode):** writes go to the Zotero web API but
> `zotero_get_collections` reads the local desktop DB, which can lag a few
> minutes until the app syncs — a just-created/deleted collection may not show
> yet. Verify writes with `zotero_search_collections` / `zotero_search_items`
> (fresh scans) rather than treating a stale `get_collections` tree as failure.
> Same caveat applies to step 3's lookup-before-add on a re-run seconds after a
> prior run: the duplicate backstop is `zotero_find_duplicates` (see
> `/zotero-archive tidy`).

## 5. Full-text top-up (optional)

Non-OA cited papers with no full text → offer the `get-paper` skill (Unpaywall first, then your institution's access) to batch-fetch;
only run on the user's go-ahead.

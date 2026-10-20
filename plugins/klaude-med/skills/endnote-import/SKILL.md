---
name: endnote-import
description: "Drop a .bib file (and optionally .enw) into a centralized inbox folder so the user can import it into macOS EndNote 21 manually. Bridges literature pipeline outputs (deep-research / pubmed-search / any tool that exports .bib) to EndNote without GUI automation. Also archives a .bib snapshot under the project for reproducibility. Use this skill whenever the user mentions: import to EndNote, push bib to EndNote, EndNote 灌進去, 餵到 EndNote, bib 進 EndNote, /endnote-import, save references to EndNote, archive references for SR/MA."
intervention: fire-forget
---

# endnote-import — .bib → EndNote inbox drop zone

Take a `.bib` file produced by any literature skill, drop it (plus an EndNote-native `.enw` if bibutils is installed) into a centralized inbox folder, archive an immutable snapshot under the project, log the operation, and print clear manual EndNote 21 import instructions.

**Why no GUI automation:** earlier versions of this skill drove EndNote via AppleScript (File → Import → File…, plus auto-creating Group Sets and Groups). The Group creation step was unreliable on EndNote 21.5 Mac due to a focus race after `Create Group Set` — keystrokes for the new Group's name field landed in the wrong UI element, leaving an unnamed dangling group. Rather than ship flaky automation, v2 surfaces the file in a known location and lets the user do the 3-click manual import inside EndNote.

---

## Workflow

### Step 1: Gather Requirements

Ask for (skip if provided):

1. **Bib path** — absolute path to the `.bib` file
2. **Project identifier** — short kebab-case name (e.g. `ma-ttm-2026`); used in inbox filename + suggested Group Set name
3. *(Optional)* **Inbox folder** — defaults to `~/Documents/EndNote_inbox/`
4. *(Optional)* **Archive directory** — defaults to `<bib-parent>/endnote_archive/`

### Step 2: Preflight

- Bib path exists, readable, has at least one `@` entry
- Detect bibutils via `which bib2xml xml2end`. If absent, inform user with `brew install bibutils` hint (skill still works without it — just no .enw conversion).

### Step 3: Execute

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/import_bib.py \
  <bib-path> --project <name> [--inbox <dir>] [--archive-dir <dir>]
```

What it does:

1. Counts `@` entries in the .bib for the log
2. Copies .bib to `<inbox>/<YYYYMMDD>_<project>__<basename>.bib`
3. If bibutils installed: also writes `.enw` (EndNote Refer-tagged format) next to it
4. Copies the source .bib to `<project>/endnote_archive/<timestamp>_<basename>.bib` (immutable provenance)
5. Appends JSON record to `endnote_import_log.json`
6. Prints a 3-step manual import recipe (open EndNote → File → Import → pick file → Import Option → Import)

### Step 4: Validate Output

After the script returns, verify:

- Script exit code is `0`
- Inbox file exists at the printed path
- Archive `.bib` exists
- `endnote_import_log.json` has the new record
- The 5-step manual recipe printed to stdout (so the user has it inline)

### Step 5: Present Results

In your reply, surface:

- Path of the inbox file (so the user can `open` it from Finder if they want)
- Number of entries
- Archive path
- The literal manual import recipe (don't paraphrase — paste the printed block)

---

## Error Handling

- **Bib path missing/unreadable** → abort, ask for correct path
- **bibutils missing** → don't abort; warn, only `.bib` lands in inbox (BibTeX import filter must be set in EndNote)
- **Inbox / archive write fails** (disk full, permission) → abort with stderr; user fixes path
- **Two simultaneous imports** → log appender re-reads JSON each time; races possible but rare for one user

## Common Rationalizations

| Rationalization | Rebuttal |
|---|---|
| "Just print the .bib path and let the user `open` it" | The inbox folder is the Schelling point — one place to look for "stuff to feed EndNote". Printing a path scattered across project trees defeats the centralization. |
| "Skip the .enw conversion, .bib is enough" | EndNote's BibTeX filter is OFF by default; if user hasn't set it once via UI, .bib import silently does nothing. .enw uses EndNote's built-in Refer Import filter that always works. Always write both when bibutils is available. |
| "Skip the archive — the .bib is in the project tree" | The bib in the project tree is mutable (next dedupe pass overwrites it). The archive snapshot is the immutable provenance for what was actually dropped + when. Keeps the JSON log meaningful. |
| "Just one file, skip the log" | The log is the only durable record connecting inbox files ↔ project archives. One missing entry means lost reproducibility forever. |

## Boundaries

- **Always**:
  - Validate `.bib` path before any copy
  - Copy to inbox AND archive (two destinations, separate purposes)
  - Append JSON log
  - Print the 5-step manual import recipe to stdout
- **Ask first**:
  - Overwriting an existing inbox file with same name (rare; same-day duplicate import) — default behaviour is `shutil.copy2` which overwrites silently; if matters, surface it
  - Importing the same `.bib` twice in one day under same project (same inbox basename collision)
- **Never**:
  - Drive EndNote via AppleScript / GUI scripting (was tried in v1, abandoned)
  - Modify or delete the source `.bib`
  - Touch `.enl` (EndNote library) directly via filesystem
  - Auto-install bibutils (suggest `brew install bibutils`, don't run it)
  - Push citations into `.docx` (out of scope; EndNote CWYW handles that in Word)

---

## Prerequisites (one-time setup)

1. **EndNote 21** at `/Applications/EndNote 21/`
2. **bibutils** *(strongly recommended)*: `brew install bibutils` — gives you the more reliable `.enw` import path
3. **(Only if not using bibutils)** Set BibTeX import filter as default once: EndNote → `File → Import → File → Import Option: BibTeX → set as default`. Without this, `.bib` import silently does nothing.

---

## Inputs / Outputs

**Input**: a `.bib` from any of:
- `lit-review` Stage 5
- `ma-search-bibliography` (`results.bib`, `dedupe.bib`)
- `deep-research` (`references.bib`)
- `pubmed-search` (`.bib` companion to the Excel output)
- Hand-curated

**Output**:
- `~/Documents/EndNote_inbox/<YYYYMMDD>_<project>__<basename>.bib`
- `~/Documents/EndNote_inbox/<YYYYMMDD>_<project>__<basename>.enw` *(if bibutils)*
- `<project>/endnote_archive/<timestamp>_<basename>.bib`
- `<project>/endnote_archive/endnote_import_log.json` (append-only JSON array)
- stdout: 5-step manual import recipe + suggested EndNote Group Set name

**Side effects**:
- Creates inbox / archive folders if missing
- **Does NOT** open or activate EndNote 21

---

## Trigger phrases

- `/endnote-import`, `/en-import`
- "import this bib to EndNote", "灌進 EndNote", "餵到 EndNote", "bib 丟進 EndNote inbox"
- After any literature skill produces a `.bib` and the user wants to ferry it to EndNote

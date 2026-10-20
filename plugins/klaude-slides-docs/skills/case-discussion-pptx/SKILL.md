---
name: case-discussion-pptx
description: "Generate a clinical case discussion PowerPoint (hospital morning-report / case-conference style, neutral branding) (.pptx) from structured case data (chief complaint, patient profile, timeline, admission findings, imaging, pathology, tentative diagnosis, management, discussion questions). Use this skill whenever the user mentions: case discussion pptx, case discussion 投影片, case discussion 報告, 把病歷做成 pptx, 病例討論投影片, clinical case presentation slides, build case discussion deck, /case-discussion-pptx, /case-pptx."
---

# Clinical Case Discussion PPTX Generator

> **中文臨床語氣**：寫中文內容（speaker notes、書面報告）前先讀 `${CLAUDE_SKILL_DIR}/references/clinical_writing_tone.md`（客觀保守措辭、禁用詞表），交付前 grep 禁用詞。

Produce a clinical case discussion presentation (9 base slides = Title · Patient Profile · Timeline · Admission Course · Imaging · Pathology · Tentative Dx · Management · Discussion Questions — Dx and Management are two separate slides; plus 1 placeholder slide per image-able study, plus optional Slide 10 / rotation-profile slides; Pathology is omitted when `pathology: null`) in the format commonly used at Taiwanese hospital daily case discussion / morning report sessions. Hospital, department and presenter name are **user-filled fields** (`CONTENT.institution`, `CONTENT.reporter`); the default look is neutral "Case Discussion". Input = structured case data (typed, pasted note, or file). Output = `.pptx` saved to a user-specified path.

> **看範例最快**：完整填寫後的 CONTENT 參考 `templates/example_case.js`（虛構的 sigmoid adenocarcinoma 教學案例，10-slide 版含 extra academic-review）。新手先看本檔再動手改 `case_content_template.js`。

**This skill is generic** — the 9 input sections map directly to the standard Taiwanese hospital 病歷 (chart) architecture:
`C.C. / History / Review of Systems / Physical Examinations / Lab / Image / Pathology / Tentative diagnosis / SOAP`.
Any case following this architecture (not just one specific case) can be fed in; the skill **does not hardcode any patient, diagnosis, or specialty**. Missing sections are rendered as `N/A`.

## When to Use

- User has a chart they want to turn into a case discussion deck
- User is preparing a morning report / case conference / grand rounds presentation
- User pastes a note, `.md` file, or free text containing: C.C., History, Review of Systems, Physical Examination, Lab, Image, Pathology, Tentative diagnosis, SOAP
- User types `/case-discussion-pptx` or `/case-pptx`

## Slide Conventions

This skill conforms to the shared academic slide rules — see **`${CLAUDE_SKILL_DIR}/references/slide_conventions.md`** for the canonical spec:

- **Rule 1**: Slide body English-only; Chinese (including `=== 縮寫全稱 ===` block) goes in speaker notes — write it in `CONTENT.slideNotes` (keyed by slide kind, see Step 4); the generator attaches it to the right slides.
- **Rule 2**: Citation metadata must include three fields (study type / country / n).
- **Rule 3**: Audit verdict (🟢/🟡/🔴) never in slide body; only in speaker notes `=== Audit ===` or hidden appendix slide.
- **Rule 4**: Speaker notes bilingual (English body + 中文 notes).

**Hard requirement, not optional.** The `CONTENT.language` option formerly allowed `all-English` vs mixed modes; this has been replaced: the default is now "English body + Chinese speaker notes" per Rule 1. Override only if the user explicitly requests (e.g., 衛教 slide, 中英對照 demo).

Pre-flight: scan slide body (not notes) for CJK characters before save; if any, stop and fix. Abbreviation glossary block required on every slide that shows an English abbreviation.

## Themes (visual style)

The generator supports 3 baked-in academic themes. Set via `CONTENT.theme`:

| Key | Style | Palette |
|---|---|---|
| `grand_rounds_warm` **(default)** | Harvard / Notion editorial — warm cream bg, Georgia titles | cream `#F5F1EA`, Harvard crimson `#8B1A1A`, copper `#B87333` |
| `journal_classic` | NEJM / Lancet — white bg, full serif | white, NEJM crimson `#A51C30`, navy `#1E3A5F` |
| `clinical_modern` | JAMA / Stripe — light grey bg, sans-serif | grey `#FAFAFA`, deep teal `#0E5E6F`, coral `#C0392B` |

## Rotation Profiles

Different rotations (CVS / Neurosurgery / GI / OB-GYN…) have their own case discussion conventions. A **rotation profile** is a markdown file with YAML frontmatter that tells the skill which extra slides to insert, which intake questions to ask, and which phrases to bold in the imaging slide.

**Built-in profiles** (under `profiles/`):

| Key | Rotation | Adds slides |
|---|---|---|
| `cvs` | Cardiovascular surgery rotation | Operative Procedure + 3 intraop photo placeholders + Postoperative Course + Back to the Patient + Take-Home Summary; imaging emphasis on valve / coronary / aortic phrases |

**Calling convention** — set `CONTENT.rotationProfile`:
- `"cvs"` → loads `profiles/cvs.md`
- `"/absolute/path/to/my_profile.md"` → loads a one-off external profile (e.g., a teacher's spec saved anywhere on your machine)
- `undefined` (default) → standard 9-slide default, zero behavior change

**Source-of-truth pointer**: a profile's frontmatter can include `source: /path/to/teacher_spec.md`. Step 2.4 reads the source file as LLM context, so the teacher's original `.md` stays the single source of truth — when teacher updates the spec, the skill picks up changes on next run.

### Authoring a new profile

Use when a new rotation (e.g., Neurosurgery, GI, OB-GYN) requires its own conventions.

1. Copy `profiles/_profile_template.md` → `profiles/<key>.md` (lowercase, alphanumeric+underscore key)
2. Fill the YAML frontmatter:
   - `key`, `name`, `rotation_display`, `aliases[]` for fuzzy specialty matching
   - `slides.*.enabled` toggles for the 4 rotation slides (operative_procedure / postop_course / back_to_patient / take_home_summary)
   - `imaging_emphasis[]` phrases for Slide 5 bolding
   - `intake_extras[]` for rotation-specific intake questions (run in a second AskUserQuestion round after the canonical 6 questions)
   - Optional `source:` pointer to a teacher's spec file
3. Add an entry to `profiles/_index.json` with the same key + aliases so Step 2.4 can fuzzy-match the user's specialty
4. (Optional) Drop the teacher's spec into the body of `profiles/<key>.md`, or set `source:` to an external path
5. Smoke test: run the skill with a fake case + `rotationProfile: "<key>"` and visually verify the new slides render correctly

If the new rotation needs a brand-new slide type not covered by the existing 4 (operative / postop / back-to-patient / take-home), open `scripts/generate_case_pptx.js` and add a new conditional block — mirror the existing `if (CONTENT.<field>) { ... }` pattern. Profiles that just toggle the existing 4 require **no generator code changes**.

## Workflow

### Step 1: Gather case content

Accept one of these inputs (ask user which):
1. **Pasted text / file path** — read directly (markdown exported from any note app works)
2. **Free-form chart** — ask user to paste sections one at a time

Required sections (flag as `N/A` if missing, **never fabricate**):
- Chief complaint
- History (HPI + past medical history + TOCC + substance use + family history + current medications)
- Review of systems (optional — used to enrich admission symptoms)
- Physical examination
- Lab
- Image (if any)
- Pathology (if any)
- Tentative diagnosis
- SOAP (Plan is critical — goes on management slide)

### Step 2: PHI pre-flight

Scan the gathered content for real patient identifiers (real name, full national ID, chart/MRN number typed as digits). If any found, stop and delegate to `phi-deid` skill. After de-identification, continue.

Note: Chart number (病歷號) is **expected** to be provided separately by the user as a placeholder on the slide — do not demand it in the content itself.

### Step 2.4: Rotation profile detection

Before the clinical intake, decide whether a rotation profile applies. This step is **silent** when no profile matches — only surfaces an AskUserQuestion when there's a real match to confirm.

1. **Already provided?** If the caller (or the user) already set `CONTENT.rotationProfile`, skip detection — load it directly.

2. **Read the profile registry**: `profiles/_index.json` lists `[{ key, name, file, aliases[] }]`.

3. **Match against Step 2.5 intake** (run intake first if not yet done): take `clinicalContext.specialty` answer, lowercase + strip whitespace, fuzzy-match against each profile's `aliases[]`. Any substring match counts (e.g., "心臟外科 — 鄭X瑞 team" matches alias "心臟外科").

4. **On match**, confirm with the user via `AskUserQuestion`:
   ```
   偵測到 {profile.name}，套用該 rotation profile？
   - yes (推薦) — 加 N 張 rotation 專屬 slide + 跑 {intake_extras.length} 題額外問題
   - no — 走標準 9-slide 流程
   - custom path — 改用其他 .md profile 路徑
   ```

5. **On `yes`**:
   a. Read the profile's `.md` file. If frontmatter has `source: /path/...`, read that file's content too and use it as LLM context (prepend the user's full teacher spec to the body so Claude can read it).
   b. Parse frontmatter (use a minimal YAML parser — supports the schema in `profiles/_profile_template.md`). On parse error, log a warning, fall back to "no profile" mode, continue.
   c. Run a second `AskUserQuestion` round with the profile's `intake_extras[]` prompts. Each `id` becomes a key in a local `extras` object.
   d. Map the resolved profile + extras into `CONTENT` per Step 4 "Profile field mapping" subsection.

6. **On `custom path`**: ask user for absolute `.md` path. Parse frontmatter the same way. If path doesn't exist or YAML is malformed, fall back to no-profile mode + warn in Step 7 report.

7. **No match found**: silent fall-through to Step 2.5 (default flow).

**Slide-count warning**: after profile mapping, if the projected total slide count > 15, surface a one-line warning in Step 7's final report ("⚠ 14 張 slide @ 10-min talk = 43s/slide — consider trimming bullets").

### Step 2.5: Clinical intake (**必問，放在生產選項之前**)

完整 6 題 intake spec、`clinicalContext` schema、Slide 9 / 10 觸發條件、caseType → Slide 10 模板對照表，**統一在 `${CLAUDE_SKILL_DIR}/references/clinical_intake.md`**。本 skill 不重複定義。

執行要點：
- 用 `AskUserQuestion` 一次出 6 題（一輪 round-trip）
- 聽眾固定為師長，不另問
- 答案寫進 `CONTENT.clinicalContext`
- 依答案自動決定 Slide 9 內容（討論問題）與是否產 Slide 10
- **若 `CONTENT.clinicalContext` 已由上游步驟填好**，跳過此步驟

### Step 3: Confirm options with user

Ask via `AskUserQuestion`:
1. **Language style** — `all-English` (common case discussion convention, default) / `English primary + 中文 first mention` / `English body + 繁中 section headers`
2. **Chart number** — user types (goes into slide 2 title)
3. **Reporter name + report date** — default to today's date; presenter name is a user-filled field (placeholder `（你的名字）` if unknown — never guess). Optionally ask for hospital · department (`CONTENT.institution`, hidden when empty)
4. **Output path** — default `case_discussion_<slug>_<YYYYMMDD>.pptx` in the current working directory
5. **Theme** — `grand_rounds_warm` (default) / `journal_classic` / `clinical_modern`
6. **Imaging / Pathology layout** — `separate slides` (default) / `merged into Investigations` / `inline in Timeline`
7. **Examination Report layout** (when input markdown contains `## Examination Report` section) — `merged_into_labs` (default) / `separate_slide` / `skip`. Examination Report = 非影像 / 非實驗室 的檢查：EKG、NCV、肺功能、UGI / lower GI endoscopy 等。若該 section 不存在或為空，跳過此問題
8. **Image placeholder slides** (`yes` default / `no` / `key only`) — for each image-able study (CXR / CT / MRI / Echo / EKG / endoscopy / sono / PET) auto-insert a **blank slide with reserved space** between Imaging and Pathology so the presenter can paste a screenshot from PACS / EMR before the talk. Default `yes`; if `imaging[] + image-able examination[]` total ≥ 6 studies, auto-prompt "全部 N 張會太多嗎？" with `key only` (impression flagged abnormal/critical) as alternative. `imageSlots` field on CONTENT controls; explicit array overrides auto-derivation, `false` skips entirely.
9. **Discussion questions slide** — inferred from Step 2.5 answers (`yes` if highlights or caseType requires)
10. **Discussion question reasoning trail** (`oe` default / `full` / `no`) — for each Slide 9 question, run external knowledge sources to capture the evidence trail behind the answer:
    - `oe` (default; **選用：需要 OpenEvidence MCP，沒有則自動降為 `full` 的 PubMed 路徑**) — query OpenEvidence per question; one query per Q
    - `full` — OE + parallel PubMed (last 5 yr) + (選用：只有裝了 NotebookLM MCP 才用) NotebookLM if the user has a relevant notebook id
    - `no` — skip; Slide 9 ships without speaker-note backing
    Output: companion `<output>.discussion_trail.md` (full Q + queries + citations + synthesis) **AND** Slide 9 speaker notes carrying 1-2 sentence synthesis + top citation per Q. See Step 3.5 for execution.
11. **書面報告 docx companion** (`no` default / `yes`) — also produce a long-form Chinese 書面報告 `.docx` written in a first-person, flowing-prose style, with inline `[N]` citations and Vancouver References derived from the discussionTrail. Use when the case is for a discussion class / rotation submission that needs a written report alongside the deck. `yes` chains to `case-discussion-docx` after Step 6 verify; output filename defaults to `書面報告_<slug>_<date>.docx` in the same folder. **Hard prerequisite**: Step 3 Q10 must be `oe` or `full` (i.e. discussionTrail non-empty) — if Q10 = `no` and user picks Q11 = `yes`, warn the user that the docx will have no citations and ask whether to switch Q10 to `oe`.
12. **A4 handout PDF companion** (`no` default / `yes`) — also produce an A4 portrait handout PDF (slide thumbnail on top + speaker notes on bottom, one page per slide) for live presenter cue cards. Use when the user wants to print 1-page-per-slide reference (or save as electronic cue card). `yes` chains to `pptx-handout` after Step 6 verify (and after Step 6.5 docx chain if both opted in). Output filename defaults to `handout_<output-stem>.pdf` in the same folder. **Soft prerequisite**: speaker notes should be non-empty on most slides (otherwise the handout's bottom half is mostly blank). If most slides lack notes, warn the user once and ask whether to proceed anyway.
13. **Take-home summary bullets** (only when active profile sets `take_home_summary.enabled: true`) — ask user for 3–5 take-home bullets to render on the final slide. If profile's `intake_extras[]` already included a `takeHomeBullets` prompt (e.g., CVS), reuse those answers and skip this question.

### Step 3.5: Build discussion trail (only if Step 3 Q10 ≠ `no`)

For each entry in `discussionQuestions[]`, run the chosen knowledge source(s) and capture the trail before populating CONTENT in Step 4. Two parallelism modes:

**`oe` mode (default, ~20-40s for 3 Qs)**:
1. For each question, call `mcp__openevidence__oe_ask` with the question reformulated to be a clinical query (drop "如何", strip Chinese-only phrasing → English clinical question). Send all questions in parallel via separate tool calls in one assistant message.
2. From the response: capture `synthesis` (2-3 sentences distilled from OE's answer), `citations` (top 2-3 from OE's bibliography, formatted as `"[N] PMID 12345 — first author. journal year"`), and `queries[]` with `{ source: "OE", query: "<rewritten>", verdict: "<one-line OE stance>" }`.
3. If a question is fundamentally non-evidence (e.g., "What's your differential reasoning?") skip OE and write `synthesis: "Open-ended discussion — no single evidentiary anchor"`.

**`full` mode (~1-3 min for 3 Qs)**:
1. Same as `oe` mode for OpenEvidence.
2. **In parallel**, for each question call `mcp__pubmed__pubmed_search_articles` with `dateRange.minDate` = (current year - 5), `maxResults: 5`, `summaryCount: 5`. Capture top 1-2 PMIDs as additional citations.
3. **If the user has a relevant NotebookLM notebook** (ask once if not specified), call `mcp__notebooklm__notebook_query` with the question. Append findings to synthesis with `(NotebookLM:)` prefix.
4. Merge into a single `discussionTrail[]` entry per question: synthesis = consolidated answer, citations = de-duplicated [OE + PubMed], queries[] = all attempted sources.

**Common rules** (both modes):
- **PHI**: Never send patient identifiers in the query. Strip name / chart no / specific dates → use age/sex/diagnosis only. E.g., NOT "70 y/o male 病歷號 1234567 ..." → "70 y/o male with newly diagnosed sigmoid adenocarcinoma cT3N0 ...".
- **Citations format**: `"[N] PMID 12345 — Last AB. JournalAbbr Year;Vol(Issue):Pages"`. Strip emoji / verdict markers from OE response before storing.
- **Failures**: If OE/PubMed errors out for a Q, store `synthesis: "Trail unavailable (OE/PubMed error)"` + `queries: [{ source: "OE", query: "...", verdict: "ERROR: <message>" }]`. Don't abort the whole trail — partial trails ship.
- **Audience**: Match `clinicalContext.audience` ("attending"); synthesis depth assumes attending-level reader (no need to define basic terms in synthesis).

**Output**: populate `CONTENT.discussionTrail = [...]` (one entry per question, same index order). Step 5's generator will:
- Render slide 9 speaker notes (1-2 line synthesis + top citation per Q + path to .md)
- Write companion `<output>.discussion_trail.md` (full Q + queries + citations + synthesis)

### Step 4.0: Clinical content decision rules (apply before writing CONTENT)

These rules settle content questions the source chart does not answer. Apply them silently; list each one you used in the Step 7 report.

1. **Discussion question count = number of intake highlights (1–3).** Do not invent extra questions to reach 3. If the intake gives 0 highlights, use the placeholder question per `references/clinical_intake.md`. For this skill, this rule overrides the fixed three-question count in `references/clinical_intake.md`. Write each question without a `Q1.` prefix, because the generator adds the label itself.
2. **No named trials or guidelines without a discussion trail.** If Step 3 Q10 = `no` (or the trail is empty) and Slide 10 asks for landmark trials or guideline anchors, write each bullet as the *question to verify*, e.g. `[To verify] RCT evidence on preoperative biliary drainage before neoadjuvant therapy`. Do not write trial names, years, n, or effect sizes from memory. If the caseType is `academic-review`, recommend Q10 = `oe` in Step 3.
3. **`merged_into_labs` means:** each examination entry goes into the `admission.lab` column as one line with an `[EKG]` / `[EGD]` style prefix. **Keep `examination[]` populated anyway**, so Q8 still creates the image placeholders. Seeing the same study in both places is expected: the lab column carries the text, the placeholder carries the picture.
4. **Missing dates.** If the chart has only relative timing, use `HD1 / HD2 …` for in-hospital events and `D-3 PTA` style for pre-admission ones, in both the timeline labels and the study headers, and keep one convention across the whole deck. If a study has no date, leave it out of the slide header. Never write `N/A` as a date.
5. **Missing sections.**
   - If the supplied records contain no pathology report, set `pathology: null` (the slide is skipped) and add `Pathology report not in supplied records` to `slideNotes.dx`. Write `No tissue diagnosis` only when the source says so explicitly.
   - If an imaging impression is missing, omit the impression line. Do not paraphrase findings into an impression.
   - If management goals are absent, derive at most 3 goals that restate the Plan's targets (e.g. `MAP ≥ 65`). Do not add new interventions.
6. **Language.** Step 3 Q1 `all-English` applies to the slide body only. The `=== 縮寫全稱 ===` glossary in `slideNotes` stays bilingual as Rule 1 requires.

### Step 4: Parse into CONTENT schema

Populate this JS object (see `templates/case_content_template.js` for an empty scaffold with field comments):

```js
const CONTENT = {
  // Slide 1: Title — [age, sex, C.C.] centered, reporter + date below
  age: 70,                    // integer
  sex: "male",                // "male" | "female"
  chiefComplaint: "...",      // one sentence
  reportDate: "2026/04/20",   // user-facing date
  reporter: "（你的名字）",    // presenter name (user-filled)
  institution: "",            // optional "<hospital> · <department>", hidden when empty

  // Slide 2: Patient Profile: [chartNo]
  chartNo: "[病歷號]",         // placeholder string is OK
  profile: {
    underlying: ["HTN", "..."],
    tocc: "...",
    substance: "...",
    familyHx: "...",
    medication: ["...", "..."],
  },

  // Slide 3: Clinical Timeline (oldest → newest)
  timeline: [
    { date: "2 years ago", event: "..." },
    { date: "2026/04/07", event: "..." },
  ],

  // Slide 4: Admission Course — 3 columns (Symptoms / PE / Lab)
  admission: {
    symptoms: ["...", "..."],   // positive + denied
    pe: ["vital signs ...", "abdomen ...", "..."],
    lab: ["2026/04/07 WBC ...", "..."],
  },

  // Slide 5: Imaging (list — one card per study)
  imaging: [
    { date: "2026/03/03", modality: "CT abdomen", findings: ["..."], impression: "..." },
  ],

  // Examination Report (EKG / NCV / 肺功能 / endoscopy 等非影像非 Lab 的檢查)
  // Structure mirrors imaging[]. Rendered per Step 3 Q7 choice:
  //   merged_into_labs → appended to admission.lab[] with "[檢查類型]" prefix
  //   separate_slide   → rendered as a standalone slide between Imaging and Pathology
  //   skip             → dropped (not on slide, still in source markdown)
  // Only populate if input markdown has `## Examination Report` section AND user chose non-skip.
  examination: [
    { date: "2026/04/05", type: "EKG", findings: ["sinus rhythm", "..."], impression: "..." },
    { date: "2026/04/08", type: "Pulmonary function test", findings: ["..."], impression: "..." },
  ],

  // Slides 5a-5n: Image / EKG placeholder slides (auto-derived; see Step 3 Q8)
  // - undefined/null → auto-derive: 1 placeholder per imaging[] + image-able examination[]
  //                    (CXR/CT/MRI/Echo/EKG/endoscopy/sono/PET — see IMAGE_MODALITY_REGEX)
  // - false          → skip all placeholders
  // - explicit array → override; same shape as { modality, date, impression, findings, source }
  imageSlots: undefined,

  // Slide 6: Pathology (single block)
  pathology: {
    date: "2026/03/30",
    specimen: "...",
    description: "...",
    diagnosis: "...",
  },

  // Slide 7: Tentative Diagnosis
  tentativeDx: {
    active: ["..."],
    underlying: ["HTN", "..."],
  },

  // Slide 8: Management (P from SOAP)
  management: {
    orders: ["...", "..."],
    goals: ["..."],
  },

  // Slide 9: Discussion Questions (template)
  discussionQuestions: ["Q1 ...", "Q2 ...", "Q3 ..."],

  // Slide 9 speaker-note backing (Step 3.5 trail) — same index as discussionQuestions
  // Companion file <output>.discussion_trail.md auto-written when non-empty
  discussionTrail: [
    {
      question: "Q1 ...",
      synthesis: "1-3 sentence answer summary",
      queries: [{ source: "OE", query: "<rewritten clinical question>", verdict: "supports / contradicts / mixed" }],
      citations: ["[1] PMID 12345 — ...", "[2] DOI ..."],
      notes: "optional caveats / contradictions",
    },
  ],

  // Optional per-slide speaker notes (Rule 1 abbreviation glossary / 中文 notes).
  // Key = slide KIND (not page number, so placeholder slides never shift it).
  // Kinds: title, profile, timeline, admission, imaging, imagingPlaceholder (applies to
  // every placeholder slide), pathology, operative, operativePhoto, dx, management,
  // postop, discussion, extra, backToPatient, takeHome. Value = string or string[];
  // appended after the generator's own notes for that slide (or creates the notes).
  slideNotes: {
    // management: "=== 縮寫全稱 ===\nCRT: chemoradiotherapy ...",
  },

  // Output
  outputPath: "case_discussion_<slug>.pptx",
};
```

`CONTENT` must be exportable: save it as `case_content_<slug>.js` ending with `module.exports = CONTENT;` (Step 5.A feeds it to the generator's `--content` flag).

#### Profile field mapping (only when Step 2.4 selected a rotation profile)

If Step 2.4 resolved a profile (e.g., CVS), map the frontmatter flags + `intake_extras[]` answers into CONTENT before generating. **Deterministic map**:

| Profile frontmatter / intake_extras | → CONTENT field |
|---|---|
| `slides.imaging_emphasis[]` | `CONTENT.imagingEmphasis` (verbatim copy) |
| `slides.operative_procedure.enabled: true` + extras `surgicalIndication` / `operativeApproach` | `CONTENT.operativeProcedure = { title, subtitle, indication: extras.surgicalIndication, approach: extras.operativeApproach.split('\n')[0], keySteps: extras.operativeApproach.split('\n').slice(1).filter(Boolean), reconstruction, photoSlots: slides.operative_procedure.photo_slots, intraopFindings }` |
| `slides.postop_course.enabled: true` + extras `postopOutcome` | `CONTENT.postopCourse = { title, subtitle, icuDays, outcome: extras.postopOutcome.split(/[;\n]/).filter(Boolean), complications, outcomeVsExpected }` |
| `slides.back_to_patient.enabled: true` + extras `alternativePlans` | `CONTENT.backToPatient = { title, subtitle, alternatives: [extras.alternativePlans], reflection, lessons }` |
| `slides.take_home_summary.enabled: true` + extras `takeHomeBullets` (Step 3 Q12 fallback) | `CONTENT.takeHomeSummary = { title, bullets: extras.takeHomeBullets.split(/\n/).filter(Boolean) }` |
| `slides.intro_section_dividers` | `CONTENT.sectionDividers` (boolean; **not yet rendered** by generator — reserved for v2) |
| `rotation_display` | Reserved — currently unused on slide body (display field for future revision) |

**Free-form intake answers**: when the user gives a single big paragraph for "approach + key steps" combined, split on `\n` or `;` heuristically. If the split looks suspicious (only 1 step found despite multi-sentence answer), prompt the user once to verify.

**Profile + extraSlide co-existence**: if `clinicalContext.caseType` triggers `extraSlide` (e.g., `mnm`) AND the profile sets `back_to_patient.enabled: true`, both render. Order is fixed: Discussion → extraSlide → Back to Patient → Take-Home Summary.

### Step 5.0: Output mode — `.pptx` vs open-slide React deck

Before generating, ask via `AskUserQuestion`:

> 輸出格式選哪個？
> - **`.pptx`（傳統可分享）** — 一個 .pptx 檔，丟給 Keynote / PowerPoint / Google Slides 都能開、可寄出去、PHI 風險低。**這是預設**。
> - **open-slide React deck（高質感 motion / web 部署）** — 一份 React/Vite 靜態網站（1920×1080 canvas，每張 slide = 一個 React component，可 deploy 到 Vercel / CF Pages / GitHub Pages）。有 motion transition、design panel 即時調色、inspector inline 註解。**Trade-off**：要 dev server iteration、要部署 hosting、不能直接寄 .pptx 檔。

**委派模式預設鎖 `.pptx`**：當本 skill 被其他 skill chain 進來時，直接走 5.A，不問 5.0。

對 5.A `.pptx` 走原本流程；對 5.B `open-slide` 走下面新流程。

### Step 5.A: Generate the PPTX (default)

1. Write the populated CONTENT object from Step 4 to `<output folder>/case_content_<slug>.js` (ends with `module.exports = CONTENT;`)
2. Run the generator directly (no copying / block replacement needed):
   `NODE_PATH="$(npm root -g)" node ${CLAUDE_SKILL_DIR}/scripts/generate_case_pptx.js --content <case_content_<slug>.js> --out <deck.pptx>`
   (`--out` overrides `CONTENT.outputPath`; with no flags the script falls back to its built-in CONTENT block, the legacy behavior)
3. The script writes the `.pptx` (and `<deck>.discussion_trail.md` when a trail exists) to the `--out` path

### Step 5.B: Generate the open-slide React deck

1. **Write the populated CONTENT to a Node runner file** (`case_content_<slug>.js`) using the same shape as Step 5.A — top-level `const CONTENT = {...}` + `module.exports = CONTENT;` at the bottom.

2. **Run the open-slide builder**:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/build_open_slide_deck.py \
       /path/to/case_content_<slug>.js \
       /path/to/output_parent_dir/
   ```

3. The builder:
   - Uses `node` to `require()` the runner and extract `CONTENT` as JSON
   - Transforms CONTENT → DATA dict (9-slide arch → open-slide slide types: cover / case_profile / case_timeline / case_admission / case_imaging × N / case_image_placeholder × M / case_pathology / case_dx / case_mgmt / discussion_question × K / blank_teacher; plus rotation profile slides if present)
   - Scaffolds an open-slide project (`open-slide init <slug> --use-pnpm --locale zh-TW`) under `<output_parent_dir>/<slug>/`
   - Copies 3 academic themes (journal-classic / grand-rounds-warm / clinical-modern; theme name in `CONTENT.theme` maps via underscore→kebab)
   - Renders `slides/case-discussion/index.tsx` (~16 slides)
   - Runs `pnpm build` to verify TS strict + Vite (deck **must** pass build before declaring success)

4. Output: handoff message tells the user `cd <deck>/ && pnpm dev` → `http://localhost:5173/s/case-discussion` (port may shift if 5173 is taken).

**Hard prerequisite**: Node 18+ globally + open-slide CLI installed (`npm i -g @open-slide/cli`) + pnpm. If any missing, scaffold step throws clear error and lists missing tools.

**Schema differences from `.pptx` path**:
- Open-slide deck splits Tentative Dx + Management into 2 slides (not 1 combined as in pptx) — long bullets overflow a 2×2 grid in canvas 1080.
- Imaging placeholders use `<ImagePlaceholder>` slots (drag/drop JPG at runtime, no PACS export needed for the deck build).
- Speaker notes (slide-level) populated from `discussionTrail` synthesis + citations; presenter view shows them with `N` key.
- No `.discussion_trail.md` companion (the trail data is in `notes[]` already + accessible via inspector).

### Step 6.B: Verify open-slide deck (only when Step 5.0 = open-slide)

For open-slide output, Step 6.A (markitdown + pdf+JPG visual QA) doesn't apply — open-slide isn't a .pptx. Use a **browser visual QA** instead (built-in Browser pane, or Chrome MCP if you have it; 選用 — 兩者都沒有就跳過視覺 QA，只依賴 `pnpm build` 通過並請使用者自行開瀏覽器檢查).

> 此 QA 不需登入（localhost dev server）→ 優先用內建 Browser（deck 必須經 dev server 服務，不能 `file://`）；以下 Chrome MCP 流程為 fallback。

1. **Build verify (auto)** — `pnpm build` already ran in Step 5.B. If `verify_build` returned False, the builder exited non-zero; fix TS errors before continuing.

2. **Start dev server**:
   ```bash
   cd <deck>/ && pnpm dev > case-dev.log 2>&1 &
   sleep 4 && grep "Local:" case-dev.log  # find the actual port
   ```

3. **Browser preflight** — use the built-in Browser pane; if using Chrome MCP, confirm a browser is connected (ask the user to open the Chrome extension if not).

4. **Iterate slides + measure overflow** — navigate to each `?p=N` (1-indexed) → wait 3-4s for transition → query main canvas geometry:

   ```js
   // Inside javascript_tool, get the on-screen slide canvas (NOT thumbnails)
   const canvases = [...document.querySelectorAll('div')]
     .filter(d => /1920px/.test(d.getAttribute('style')||''))
     .filter(c => c.getBoundingClientRect().height > 500);
   const main = canvases[canvases.length - 1];  // last 1080-tall canvas
   const r = main.getBoundingClientRect();
   const scale = r.height / 1080;
   const footer = main.querySelector('div[style*="bottom: 60px"]');
   const footerTop = footer ? (footer.getBoundingClientRect().top - r.top) / scale : null;
   const bodyContainer = main.querySelector('div[style*="flex: 1"][style*="min-height: 0px"]');
   // ... compute max overflow of any body child past footerTop
   ```

5. **Pass criteria**:
   - **P1 (must fix)**: any slide with overflow > 30 canvas px (content clipping into footer text area)
   - **P2 (should fix)**: overflow 10-30 px (1 line edge clipping)
   - **P3 (acceptable)**: < 10 px overflow

6. **Fix loop**: for each P1/P2 overflow, either:
   - Shrink the offending element's font (e.g., timeline events 26pt→22pt, dx_mgmt bullets 26pt→18pt)
   - Override the COMMON renderer in `CASE_RENDERERS` with denser layout
   - **Split content across 2 slides** (preferred per slide-authoring §"Splitting is always the right answer") — e.g., tentativeDx + management → 2 slides, not 1

7. **Re-render** (`rm -rf <deck>/ && python3 build_open_slide_deck.py ...`) and re-verify until all slides ≤ P2 threshold.

**Console / network smoke**:
```js
// Confirm no error in console (React Router future-flag warnings are harmless)
read_console_messages(pattern: "Error|Failed|TypeError", onlyErrors: true)
```

After all clean, kill dev server (`pkill -f "open-slide dev"`) and report deck path + `pnpm dev` command to user.

**Known overflow patterns + fixes** (from 2026-05-28 dogfood with example_case.js, 10 timeline events + 15-bullet dx_mgmt):

| Slide type | Symptom | Fix |
|---|---|---|
| case_timeline (≥ 8 events) | Footer collision | `render_case_timeline_dense` override (22pt + 10px padding) |
| case_dx_mgmt (4 quadrants, long bullets) | 500+ px overflow on 2×2 grid | Split into 2 slides (`_only: dx` / `_only: mgmt`), stacked-card layout |
| case_image_placeholder (with impression) | Caption clips | ImagePlaceholder height 620→520, caption fontSize 22→20 |

### Step 6: Verify output（**Hard gate — 不准跳過**）

(Applies to the `.pptx` path; for open-slide see Step 6.B above.)

**為什麼這步是 hard gate**: `python -m markitdown <pptx>` 只看得到文字，**完全看不到版面**。實際渲染常見的 row overflow / column 溢位 / dot mis-align / footer collision / centered-vs-left 對齊衝突 / `• -` 雙標記，純文字檢查全部抓不到。**沒跑這步就回報「完成」= 把驗證責任推給使用者**，違反 verify-after-write 原則。

**必跑流程**（任一未跑禁止回報任務完成）：

0. **Generator WARN lines**: if Step 5.A printed `WARN: … exceeds card space`, inspect that slide first in the visual check and trim the content (the generator does not paginate).

1. **Text-level 抽查**:
   - `python3 -m markitdown <output.pptx>` — check slide count = 9 base slides (listed in the opening description; minus Pathology if `pathology: null`) + N image placeholders + (optional) Slide 10 / profile slides, all with content, no empty cards
   - grep for expected strings: C.C., reporter name, chartNo placeholder, tentative diagnosis, key lab value
   - 若 source 是 redacted markdown，grep 確認 `[PATIENT_NN]` / `[DATE_NN]` token 進到 pptx，無真實 PHI 殘留
   - **Image placeholder slides** (only when `imageSlots !== false`): 用 `python-pptx` 確認每個 image-able study (CXR/CT/MRI/Echo/EKG/endoscopy) 都生出對應的 placeholder slide，header 含 modality + date，body 有虛線框 + impression caption
   - **Discussion trail .md** (only when Step 3 Q10 ≠ `no`): 確認 `<output>.discussion_trail.md` 存在、含每個 Q 的 synthesis + citations 區塊；slide 9 speaker notes 非空且每個 Q 都有 1-2 line synthesis
   - **Rotation profile slides** (only when Step 2.4 applied a profile):
     - Operative Procedure slide: header + ≥2 labeled blocks (indication / approach / key steps / reconstruction)
     - Intraop photo placeholder slides: count = `operativeProcedure.photoSlots`, each with dashed box
     - Postoperative Course slide: ≥2 labeled blocks (hospital course / complications / outcome vs expected)
     - Back to the Patient slide: ≥1 of (alternatives / reflection / lessons)
     - Take-Home Summary slide: numbered bullets count matches `takeHomeSummary.bullets[]` length
     - Imaging emphasis: grep slide 5 markitdown output for the emphasis phrases — they should appear (bold styling is lost in markitdown but presence is verifiable)
   - **Backwards compat smoke**: also re-run `templates/example_case.js` (standard 9-slide default) and confirm slide count + structure unchanged from pre-profile baseline. Run before declaring any profile work complete.

2. **Visual-level（必做）**:
   ```bash
   D="<output folder>"   # per-deck render dir avoids parallel runs overwriting each other
   rm -rf "$D/render" && mkdir -p "$D/render"
   soffice --headless --convert-to pdf --outdir "$D/render" "<output.pptx>"
   pdftoppm -jpeg -r 110 "$D/render/<output-stem>.pdf" "$D/render/slide"
   ```
   （不要用 `rm -f slide-*.jpg`：zsh 在 glob 無符合時會中斷整串 `&&`。）
   - **Claude 主執行緒親自 Read** cover / 任何 case_findings (4-col) / 任何 tentative_dx_mgmt 卡片 — 最易爆版的張數
   - **環境不能派 subagent 時**：主執行緒自己把全部 JPG 看完（同樣 6 項檢查）
   - **派 1 個 general-purpose subagent**（Agent tool `model: sonnet`；版面細節 Haiku 易漏判）把剩下 JPG 一次看完，檢查 6 項缺陷：
     1. Overflow（文字跑出 footer / 邊界 / card 邊框）
     2. Cropping（字句被 box 切斷）
     3. Mis-alignment（dot/marker 沒對到字、column 寬度不齊）
     4. Excessive whitespace（>1" 死區 → 字可放大）
     5. Font too small（< 10pt body）
     6. Markdown artifact（`• -` 雙標記、`**bold**` 沒解）

3. **如果 ≥ 1 張有 P1/P2 缺陷**：回到 Step 4 改 CONTENT 或修 generate_case_pptx.js，re-render → re-QA → re-render 直到通過。**不准把缺陷推給使用者**「自己開檔調」。

**反例（不可重蹈）**: 2026-04-27 jc-pptx run 跳過 visual QA、只看 markitdown → user 開檔才看到 slide 2 outline 6 items 溢位、slide 4 timeline dot 偏移、slide 8/10/12 table 撞 footer、slide 5 Pathology `• -` 雙標記。第二輪才補做 visual QA 並修。同類問題 case-discussion-pptx 也會中。

### Step 6.5: Chain to `case-discussion-docx` (only if Step 3 Q11 = `yes`)

After Step 6 visual QA passes, hand off to `case-discussion-docx` to render the 書面報告 companion:

1. Pipe inputs (no re-prompt — sister skill skips Step 3 questions when `delegated_from` is present):
   ```json
   {
     "delegated_from": "/case-pptx",
     "case_content": <Step 4 CONTENT object>,
     "discussion_trail_md": "<output>.discussion_trail.md",
     "clinical_context": <Step 2.5 clinicalContext>,
     "pptx_output_path": "<Step 5 .pptx path>",
     "preferred_docx_output_path": "<same folder>/書面報告_<slug>_<date>.docx",
     "skip_step3_questions": true
   }
   ```
2. Invoke `Skill(case-discussion-docx)` with the pipe payload as args
3. Sister skill returns docx_output_path + citation summary; report both pptx and docx in Step 7

### Step 6.6: Chain to `pptx-handout` (only if Step 3 Q12 = `yes`)

After Step 6 verify (and Step 6.5 docx chain if both opted in), hand off to `pptx-handout` to render the A4 cue-card PDF:

1. Pre-check: count slides with non-empty speaker notes. If < 50% have notes, surface one-line warning ("⚠ 只有 N/M slide 有 speaker notes，handout 下半會大半留白") and ask whether to proceed (`yes` / `skip`).

2. Pipe inputs (no re-prompt — sister skill skips Step 1/3 when `delegated_from` is present):
   ```json
   {
     "delegated_from": "/case-pptx",
     "pptx_path": "<Step 5 .pptx path>",
     "preferred_output_path": "<same folder>/handout_<output-stem>.pdf",
     "layout": "portrait",
     "skip_user_questions": true
   }
   ```

3. Invoke via Bash:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../pptx-handout/scripts/build_handout.py \
       --pptx "<pptx_path>" \
       --output "<preferred_output_path>" \
       --layout portrait
   ```

4. Sister skill returns handout_pdf_path on stdout (last line); report path + size + page count in Step 7.

### Step 6.7: Zotero archiving (only if Step 3 Q10 ≠ `no`; default-on, skippable)

File the discussion's cited literature into Zotero — a per-case collection under a `Case Discussions` parent, one subfolder per discussion question (Q1, Q2, …). Pure Zotero, no EndNote downstream (a case discussion is not a co-edited Word manuscript).

**選用（只有你裝了 Zotero MCP 才跑）。Skip** if `zotero` MCP not connected, the user said "don't archive to Zotero", or the discussionTrail is empty (Q10 = `no`).

1. Dump `CONTENT.discussionTrail` to JSON (it is plain data): write the array to `<output folder>/<slug>_trail.json`.
2. Run the adapter (it regex-extracts pmid/doi from the prose `"[N] PMID … / DOI …"` citation strings; a citation with neither is still archived under its question, surfaced at confirm):
   ```
   python3 ${CLAUDE_SKILL_DIR}/scripts/zotero_plan_case.py <output folder>/<slug>_trail.json \
       --topic "<case title / slug>" [--date <YYYY-MM>] --out <output folder>/<slug>_zotero_plan.json
   ```
3. Follow the shared execution playbook **`${CLAUDE_SKILL_DIR}/lib/zotero_archive/EXECUTION.md`** (create-or-reuse parent `Case Discussions` → show→confirm → lookup-before-add filing → index). A citation with no pmid/doi lands on the skip list there (not dropped).

(`case-discussion-docx` reuses this same adapter on the same discussionTrail — archive once per case.)

### Step 7: Report

Tell the user:
- Output path (clickable)
- How to edit chartNo / reporter / dates (open the `.pptx` in Keynote / PowerPoint, or edit the `.js` runner and re-run)
- **Image placeholder slides**: list the N modalities + dates that got blank slides; remind to open PACS / EMR before the talk and paste screenshots into the dashed box
- **Discussion trail .md** (when generated): clickable path to `<output>.discussion_trail.md`; remind that Slide 9 speaker notes hold the 1-2 line synthesis per Q for in-talk reference, full trail is the .md file
- **書面報告 .docx** (when Step 3 Q11 = `yes`): clickable path; report inline citation count + reference count + any citation warnings from `case-discussion-docx` Step 8
- **A4 handout .pdf** (when Step 3 Q12 = `yes`): clickable path; report total page count + size; remind user it is for live presenter cue cards (slide + notes per page, A4 portrait)
- Suggestion to write discussion questions themselves (Slide 9 has placeholder bullets if Step 3.5 was skipped)

## Error Handling

| Failure mode | Mitigation |
|---|---|
| Missing required section (e.g., no Physical Examination) | Render `N/A` on that slide's field; do NOT fabricate. Warn user at end. |
| Node module not found | Run `npm install -g pptxgenjs react react-dom react-icons sharp` then retry |
| `NODE_PATH` not set on user's machine | Use `NODE_PATH="$(npm root -g)"` |
| User's source has real patient name / ID | Stop, delegate to `phi-deid`, resume only after de-identified copy available |
| Output path not writable | Ask user for alternate path |
| pptxgenjs shadow mutation bug | Script uses `makeCardShadow()` factory (create fresh each call) |
| Discussion questions missing | If Step 3 chose "yes", render 3 empty placeholder bullets (`[Discussion question 1]` etc.) |

## Scripts

- `scripts/build_open_slide_deck.py` — open-slide React deck builder (Step 5.B). Uses `${CLAUDE_SKILL_DIR}/../notebooklm-pptx/lib/open_slide_builder` shared infra (same plugin). Reads a CONTENT runner.js via node bridge → transforms to DATA dict (9-slide arch + rotation profile slides) → scaffolds open-slide CLI → renders `slides/case-discussion/index.tsx` → runs `pnpm build` to verify TS. 9 case-specific renderers (admission / imaging / image-placeholder / pathology / operative_procedure / operative_photo / postop_course / back_to_patient / take_home_summary) + 2 overrides of COMMON_RENDERERS (case_timeline denser, case_dx_mgmt split + stacked).
- `scripts/generate_case_pptx.js` — self-contained PptxGenJS generator. CONTENT block at top; helpers `addHeader`, `addLabeledBlock`, `buildImageSlots` (auto-derive image-able placeholder slides), `buildOperativePhotoSlots` (intraop photo placeholders), `buildEmphasisRuns` (imaging emphasis rich-text), `renderTrailMd` (companion .md writer for `discussionTrail`). Run with `NODE_PATH="$(npm root -g)" node <path>`. When `discussionTrail` is non-empty, also writes `<output>.discussion_trail.md`.
- `templates/case_content_template.js` — empty `CONTENT` schema with field comments. Includes `examination[]`, `imageSlots`, `discussionTrail[]`, and rotation-profile fields (`rotationProfile`, `imagingEmphasis`, `operativeProcedure`, `postopCourse`, `backToPatient`, `takeHomeSummary`).
- `templates/example_case.js` — filled 9-slide example (fabricated sigmoid adenocarcinoma teaching case, also serves as backwards-compat smoke baseline).
- `templates/example_case_cvs.js` — filled CVS rotation example (de-identified mitral valve repair case) demonstrating all rotation-profile fields populated.
- `templates/discussion_only_template.js` — **standalone sister generator** for a 「discussion-only」 deck (N slides, one per question — NOT a full case discussion). Self-contained: copy the file, edit `QUESTIONS` array + `OUTPUT_PATH`, run `NODE_PATH="$(npm root -g)" node <path>`. Format: Q-number merged into title (e.g. "Q1. <title>"), no separate badge above; 2-3 labeled cards per slide with crimson/copper/taupe accent bars + full border; references at slide bottom 6pt Calibri left-aligned, ONE per line. Use when assignment is a focused Q&A block (student-report discussion block, journal-club Q discussion, M&M questions) instead of full case write-up. Cap: 3 sections × ≤3 bullets × ≤95 chars/bullet; ≤4 refs/slide.
- `profiles/cvs.md` — CVS (cardiovascular surgery) example rotation profile. Frontmatter sets imaging emphasis + 4 extra slide flags; body explains the three-act structure. `source:` is optional (commented out) — point it at your teacher's spec file.
- `references/` — `slide_conventions.md`, `clinical_intake.md`, `clinical_writing_tone.md` (bundled copies of the shared rules).
- `lib/` — bundled `zotero_archive/` and `pptx_launder.py` (also used by `journal-club-discussion-pptx`). The open-slide builder is taken from the sibling skill `notebooklm-pptx/lib/open_slide_builder`.
- `profiles/_profile_template.md` — copy as starting point for new rotation profiles (Neurosurgery, GI, OB-GYN, …).
- `profiles/_index.json` — registry consumed by Step 2.4 alias matching.

## Design

- 16:9 (10" × 5.625")
- Branding: neutral by default; hospital/department appear only if `CONTENT.institution` is set.
- Colors: BG `1B3A4B` (dark slides 1 only), primary `065A82`, teal `1C7293`, light BG `F0F5F9`, coral `D94F5C` (alerts), green `2B8A6E` (plan), gold `D4A843` (discussion)
- Fonts: Georgia for titles, Calibri for body
- Slide-1 title slide: dark BG, centered `[age, sex, C.C.]` in 32pt Georgia white, `Report date: ...` + `Reporter: ...` in 14pt Calibri teal below

## Dependencies

```bash
npm install -g pptxgenjs react react-dom react-icons sharp
pip install "markitdown[pptx]"  # verification only
pip install python-pptx            # Step 6 placeholder / notes checks (do not run these checks with `python3 -I`: isolated mode drops site-packages)
```

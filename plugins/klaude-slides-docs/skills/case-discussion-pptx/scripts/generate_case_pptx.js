#!/usr/bin/env node
// ============================================================
// Case Discussion PPTX Generator (9 slides)
// ============================================================
// Usage: NODE_PATH="$(npm root -g)" node generate_case_pptx.js \
//          --content <content.js (module.exports = CONTENT)> --out <deck.pptx>
//
// With no arguments the built-in CONTENT block below is used (legacy mode:
// copy this file and replace the CONTENT block).
//
// Theme: set CONTENT.theme to one of:
//   "grand_rounds_warm" (default — Harvard/Notion editorial, warm cream bg)
//   "journal_classic"   (NEJM/Lancet — white bg, serif throughout)
//   "clinical_modern"   (JAMA/Stripe — light grey bg, sans-serif)
// ============================================================
// v2 font sizing (2026-05-07, tiered after visual QA) — fork of
// medical-ethics-discussion-pptx v2 refactor. Body fontSize floor = 14pt for
// readable contexts (slide titles, profile values, timeline events, big-text
// labels), 12pt for dense card-internal bullets where 14pt would overflow
// fixed-coord card boxes. Title-slide hero (chief complaint = 34pt; age/sex
// preamble = 20pt) and section header (24pt) preserve hierarchy.
//
// v1 had body at 10.5pt which was unreadable from the back of a teaching
// room. Initial v2 bulk-bumped everything to 14, but visual QA on
// example_case.js showed 7/12 slides had card overflow (slides 04, 05, 08,
// 10) or title-line wrap collisions (06, 07, 12). Tiered fix:
//
//   - Section header (addHeader title): 24pt — long imaging titles
//     ("CT ABDOMEN/PELVIS WITH IV CONTRAST · DATE") wrap at 28pt;
//   - Section subtitle (addHeader subtitle): 14pt;
//   - Slide-1 hero (chief complaint): 34pt;
//   - Slide-1 age/sex preamble: 20pt italic;
//   - Slide-2 profile labels + values: 14pt (rows fit at 0.7" each);
//   - Slide-3 timeline date + event: 14pt;
//   - Card LABEL uppercase (addLabeledBlock): 14pt bold;
//   - Card body bullets (addLabeledBlock textItems, slide-5 imaging
//     findings/impression): 12pt — 14pt would overflow fixed-h cards
//     when bullet count ≥4. Reduce CONTENT to ≤5 short bullets per card
//     for best legibility; fewer items will display at the parent box's
//     intrinsic size.
//
// If you add new slide.addText() calls:
//   - Default body in normal contexts: fontSize: 14
//   - Card-internal dense bullets: fontSize: 12 (will fit ≥5 bullets)
//   - Slide section header: fontSize: 24
//   - Cover hero / chief complaint: fontSize: 28+
//
// Slide 4 (Admission) and Slide 8 (Management) cards use adaptive heights
// (estimateLines × 0.30 + 0.55 header) capped at slide-bottom budget. If
// you have a column / card with very long content (≥5 multi-line items at
// 12pt body in 2.87" col, or ≥7 items in slide-8 Orders), the LAST item may
// still clip — physical limit of 12pt × N-lines vs slide H 5.625. Fix at
// the data layer: split long prose items, or move the column to its own
// slide. Going below 12pt body is discouraged (back-of-room readability).
// ============================================================

const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

// ============================================================
// CONTENT — Replace this block with the case's data
// ============================================================
let CONTENT = {
  // Theme: "grand_rounds_warm" | "journal_classic" | "clinical_modern"
  theme: "grand_rounds_warm",

  // Slide 1 — Title
  age: 0,
  sex: "male",                      // "male" | "female"
  chiefComplaint: "[Chief complaint]",
  reportDate: "[YYYY/MM/DD]",
  reporter: "[Reporter]",
  institution: "",                  // optional: "<hospital> · <department>" shown on the title slide; empty = hidden

  // Slide 2 — Patient Profile: [chartNo]
  chartNo: "[病歷號]",
  profile: {
    underlying: ["[Underlying disease]"],
    tocc: "[Travel/Occupation/Contact/Cluster]",
    substance: "[Alcohol / betel nuts / cigarettes]",
    familyHx: "[Family history]",
    medication: ["[Medication]"],
  },

  // Slide 3 — Clinical Timeline
  timeline: [
    { date: "[date]", event: "[event]" },
  ],

  // Slide 4 — Admission Course
  admission: {
    symptoms: ["[admission symptom]"],
    pe: ["[PE finding]"],
    lab: ["[lab]"],
  },

  // Slide 5 — Imaging (one card per study)
  imaging: [
    { date: "[date]", modality: "[modality]", findings: ["[finding]"], impression: "[impression]" },
  ],

  // Slide 5b — Examination Report (EKG / NCV / 肺功能 / endoscopy 等非影像非 Lab)
  // Mirrors imaging[] schema. Used both for image-placeholder generation
  // (EKG / Echo / endoscopy = image-able) and for downstream lab merging
  // by the upstream skill (admission-to-case-pptx Stage 3).
  examination: [
    // { date: "[date]", type: "EKG", findings: ["[finding]"], impression: "[impression]" },
  ],

  // Image placeholder slides — auto-derived from imaging[] + examination[]
  // when not set explicitly. Set to false to skip all placeholders.
  // Set to an explicit array to override auto-derivation:
  //   imageSlots: [{ modality: "CXR", date: "2026/04/05", impression: "..." }]
  imageSlots: undefined,

  // Slide 6 — Pathology
  pathology: {
    date: "[date]",
    specimen: "[specimen description]",
    description: "[micro description]",
    diagnosis: "[pathological diagnosis]",
  },

  // Slide 7 — Tentative Diagnosis
  tentativeDx: {
    active: ["[active problem]"],
    underlying: ["[underlying]"],
  },

  // Slide 8 — Management (Plan)
  management: {
    orders: ["[order]"],
    goals: ["[goal]"],
  },

  // Slide 9 — Discussion Questions (template)
  discussionQuestions: [
    "[Discussion question 1]",
    "[Discussion question 2]",
    "[Discussion question 3]",
  ],
  includeDiscussion: true,

  // Slide 9 speaker-note backing — populated by Step 3.5 / Stage 3.5 when
  // the user opts in to OE / NotebookLM / PubMed query trail. Each item
  // matches one discussionQuestions[] entry. Full long-form trail is also
  // written to <outputPath>.discussion_trail.md (companion file).
  // Schema:
  //   { question: "...",  // mirrors discussionQuestions[i]
  //     synthesis: "...",  // 1-3 sentence answer summary
  //     queries:   [{ source: "OE"|"NotebookLM"|"PubMed", query: "...", verdict: "..." }],
  //     citations: ["[1] PMID 12345 — ...", "[2] DOI ..."],
  //     notes:     "optional caveats / contradictions" }
  discussionTrail: [],

  // Slide 10 — Optional extra discussion slide (populated by intake Stage 0.5/2.5
  // when caseType triggers it: mnm / academic-review / diagnostic-challenge /
  // management-dilemma / teaching with ≥20 min or >3 highlights or multi-select).
  // Omit or set to null to skip Slide 10.
  extraSlide: null,
  // Example:
  // extraSlide: {
  //   title: "Complication Analysis",
  //   subtitle: "M&M review",
  //   bullets: ["Root cause: ...", "Timeline: ...", "System factor: ...",
  //             "Preventability: ...", "Action items: ..."],
  // },

  // Clinical intake context (optional — populated by Stage 0.5/2.5 intake).
  // Not directly rendered; used by the upstream LLM step to drive bold
  // keywords, timeline anchors, and Slide 9 question phrasing.
  clinicalContext: null,
  // Example:
  // clinicalContext: {
  //   specialty: "GI / Colorectal surgery",
  //   primaryIssue: "Newly dx sigmoid CA, preop workup",
  //   highlights: ["preop staging", "LAR vs APR", "neoadjuvant indication"],
  //   notes: "",
  //   duration: "20",                         // "10" | "15" | "20" | "30"
  //   caseType: ["academic-review"],          // may be multi-select
  //   audience: "attending",                  // fixed
  // },

  // Output
  outputPath: "case_discussion.pptx",   // relative to the current working directory
};

// ============================================================
// THEMES
// ============================================================
const THEMES = {
  grand_rounds_warm: {
    name: "Grand Rounds Warm (Harvard / Notion editorial)",
    bg: "F5F1EA",
    cardBg: "FCFAF5",
    text: "2B2318",
    textLight: "6E5B43",
    accent: "8B1A1A",      // Harvard crimson
    accent2: "B87333",      // warm copper
    accent3: "8B7355",      // warm taupe
    rule: "D9C8A9",
    headerFont: "Georgia",
    bodyFont: "Calibri",
    titleSlideBg: "F5F1EA",
    titleSlideText: "2B2318",
    titleSlideAccent: "8B1A1A",
    titleSlideSubtle: "6E5B43",
    showBorders: true,
  },
  journal_classic: {
    name: "Journal Classic (NEJM / Lancet)",
    bg: "FFFFFF",
    cardBg: "FFFFFF",
    text: "1A1A1A",
    textLight: "5B5B5B",
    accent: "A51C30",       // NEJM crimson
    accent2: "1E3A5F",      // deep navy
    accent3: "8E8E8E",      // muted grey
    rule: "CCCCCC",
    headerFont: "Georgia",
    bodyFont: "Georgia",
    titleSlideBg: "FFFFFF",
    titleSlideText: "1A1A1A",
    titleSlideAccent: "A51C30",
    titleSlideSubtle: "5B5B5B",
    showBorders: false,
  },
  clinical_modern: {
    name: "Clinical Modern (JAMA / Stripe)",
    bg: "FAFAFA",
    cardBg: "FFFFFF",
    text: "1A1A1A",
    textLight: "595959",
    accent: "0E5E6F",       // deep teal
    accent2: "C0392B",      // accent coral
    accent3: "7F8C8D",      // slate
    rule: "E5E5E5",
    headerFont: "Calibri",
    bodyFont: "Calibri",
    titleSlideBg: "FAFAFA",
    titleSlideText: "1A1A1A",
    titleSlideAccent: "0E5E6F",
    titleSlideSubtle: "595959",
    showBorders: true,
  },
};

// ============================================================
// HELPERS
// ============================================================
function naIfEmpty(v) {
  if (v === undefined || v === null) return "N/A";
  if (Array.isArray(v) && v.length === 0) return "N/A";
  if (typeof v === "string" && v.trim() === "") return "N/A";
  return v;
}

// Image-able modality detection — used both to auto-derive imageSlots[]
// and to decide whether an examination[] entry deserves its own placeholder.
const IMAGE_MODALITY_REGEX = /\b(CXR|x[- ]?ray|chest film|KUB|CT|MRI|MR(?!N)|MRA|MRV|MRCP|echo(?:cardio\w*)?|EKG|ECG|US|sono(?:gra\w*)?|ultrasound|ultrasono\w*|PET|angio(?:gra\w*)?|fluoroscop\w*|endoscop\w*|gastroscop\w*|colonoscop\w*|sigmoidoscop\w*|EGD|ERCP|EUS|bronchoscop\w*|cystoscop\w*|mammogra\w*|venogra\w*|arteriogra\w*|DSA|cardiac MR)\b/i;

function buildImageSlots(content) {
  if (Array.isArray(content.imageSlots)) return content.imageSlots;
  if (content.imageSlots === false) return [];
  const slots = [];
  (content.imaging || []).forEach((img) => {
    if (!img || !img.modality) return;
    slots.push({
      modality: String(img.modality),
      date: img.date || "",
      impression: img.impression || "",
      findings: Array.isArray(img.findings) ? img.findings : (img.findings ? [img.findings] : []),
      source: "imaging",
    });
  });
  (content.examination || []).forEach((ex) => {
    if (!ex || !ex.type) return;
    if (!IMAGE_MODALITY_REGEX.test(ex.type)) return;
    slots.push({
      modality: String(ex.type),
      date: ex.date || "",
      impression: ex.impression || "",
      findings: Array.isArray(ex.findings) ? ex.findings : (ex.findings ? [ex.findings] : []),
      source: "examination",
    });
  });
  return slots;
}

// ------------------------------------------------------------
// Rotation profile helpers (consumed by Operative Procedure /
// Postoperative Course / Back to Patient / Take-Home Summary /
// Section Divider slides + Slide 5 imaging emphasis).
//
// All helpers are pure — they read CONTENT, return data /
// PptxGenJS-shaped objects, and do not mutate global state.
// They are no-ops when the relevant CONTENT field is absent,
// preserving 9-slide backwards compat.
// ------------------------------------------------------------

// Body-font step-down shared by the Admission and Management slides: try each
// size until the cards fit. Line pitch scales with font size and with the
// tighter line spacing used below 12pt (see addLabeledBlock).
const BODY_FONT_STEPS = [12, 11, 10.5, 10];
const lineSpacingFor = (fs) => (fs < 12 ? 1.1 : 1.25);
const linePitchScale = (fs) => (fs / 12) * (lineSpacingFor(fs) / 1.25);
// " · 2026/04/20"-style suffix only when a date exists (Step 4.0 rule 4: never print N/A / — as a date).
const withDate = (label, date, fmt = (d) => `  ·  ${d}`) => (date ? label + fmt(date) : label);

function estimateLabeledBlockHeight(value) {
  // Wrap-aware height estimator for addLabeledBlock card. Matches
  // Slide 8 Management's pattern (line-count × line-height + header).
  // Used by the 3 rotation-profile slides (Operative Procedure /
  // Postoperative Course / Back to the Patient) to avoid clipping
  // when bullet content wraps to multiple lines.
  //
  //   - 8.8" wide card, 0.4" padding → 8.4" effective text width
  //   - 12pt body at 1.25× lineSpacing → ~0.30" per line
  //   - ~95 chars/line at 12pt in that effective width
  //   - 0.55" for label header + top padding
  const items = Array.isArray(value) ? value : [value || ""];
  let lines = 0;
  items.forEach((item) => {
    const chars = String(item).length;
    lines += Math.max(1, Math.ceil(chars / 95));
  });
  return Math.max(0.95, 0.55 + lines * 0.30);
}

function buildOperativePhotoSlots(content) {
  // Generate N intraop photo placeholder slots from
  // CONTENT.operativeProcedure.photoSlots (number). Each slot
  // becomes a dedicated blank-canvas slide with a dashed box for
  // the presenter to paste a camera photo. Returns [] when 0 or
  // unset.
  const op = content.operativeProcedure;
  if (!op || !op.photoSlots) return [];
  const n = Math.min(Math.max(parseInt(op.photoSlots, 10) || 0, 0), 6);
  const slots = [];
  for (let i = 1; i <= n; i++) {
    slots.push({
      index: i,
      total: n,
      title: op.title || "Operative Procedure",
      caption: op.reconstruction || op.approach || "",
    });
  }
  return slots;
}

function buildEmphasisRuns(text, phrases, accentColor, baseColor) {
  // Build a pptxgenjs rich-text run array from `text` with all
  // case-insensitive substring matches of `phrases[]` bolded +
  // accentColor. Returns null when no match — caller should
  // fall back to plain s.addText(string). Overlapping matches
  // are merged. baseColor / accentColor are hex strings.
  if (!text || !Array.isArray(phrases) || phrases.length === 0) return null;
  const lowerText = String(text).toLowerCase();
  const matches = [];
  phrases.forEach((p) => {
    if (!p) return;
    const lp = String(p).toLowerCase();
    if (!lp) return;
    let idx = 0;
    while ((idx = lowerText.indexOf(lp, idx)) !== -1) {
      matches.push({ start: idx, end: idx + lp.length });
      idx += lp.length;
    }
  });
  if (matches.length === 0) return null;
  matches.sort((a, b) => a.start - b.start);
  const merged = [];
  matches.forEach((m) => {
    const last = merged[merged.length - 1];
    if (last && m.start <= last.end) {
      last.end = Math.max(last.end, m.end);
    } else {
      merged.push({ ...m });
    }
  });
  const runs = [];
  let cursor = 0;
  merged.forEach((m) => {
    if (m.start > cursor) {
      runs.push({ text: String(text).substring(cursor, m.start), bold: false, color: baseColor });
    }
    runs.push({ text: String(text).substring(m.start, m.end), bold: true, color: accentColor });
    cursor = m.end;
  });
  if (cursor < String(text).length) {
    runs.push({ text: String(text).substring(cursor), bold: false, color: baseColor });
  }
  return runs;
}

function renderTrailMd(content) {
  const trail = Array.isArray(content.discussionTrail) ? content.discussionTrail : [];
  const lines = [];
  const slug = path.basename(content.outputPath || "case.pptx", ".pptx");
  const today = new Date().toISOString().split("T")[0];
  lines.push(`# Discussion Trail — ${slug}`);
  lines.push("");
  const ageSex = `${naIfEmpty(content.age)}-year-old ${content.sex || "—"}`;
  lines.push(`**Case**: ${ageSex} with ${naIfEmpty(content.chiefComplaint)}`);
  lines.push(`**Reporter**: ${content.reporter || "—"}`);
  lines.push(`**Report date**: ${content.reportDate || "—"}`);
  lines.push(`**Trail generated**: ${today}`);
  lines.push("");
  lines.push("> 本檔記錄產生 Slide 9 (Discussion Questions) 時 Claude 向外部知識來源（OpenEvidence / NotebookLM / PubMed）的查詢、回傳結果與整合過程。供報告者準備時 sanity-check 引用、補強 talking points。");
  lines.push("");
  if (trail.length === 0) {
    lines.push("_(no trail recorded — set CONTENT.discussionTrail to populate)_");
    return lines.join("\n");
  }
  trail.forEach((t, i) => {
    lines.push("---");
    lines.push("");
    lines.push(`## Q${i + 1}: ${t.question || ""}`);
    lines.push("");
    if (Array.isArray(t.queries) && t.queries.length > 0) {
      lines.push("### Queries");
      t.queries.forEach((q) => {
        lines.push(`- **${q.source || "?"}**: \`${q.query || ""}\``);
        if (q.verdict) lines.push(`  - Verdict: ${q.verdict}`);
      });
      lines.push("");
    }
    if (Array.isArray(t.citations) && t.citations.length > 0) {
      lines.push("### Citations");
      t.citations.forEach((c, j) => {
        lines.push(`${j + 1}. ${c}`);
      });
      lines.push("");
    }
    if (t.synthesis) {
      lines.push("### Synthesis");
      lines.push(t.synthesis);
      lines.push("");
    }
    if (t.notes) {
      lines.push("### Notes");
      lines.push(t.notes);
      lines.push("");
    }
  });
  return lines.join("\n");
}

// ============================================================
// BUILD
// ============================================================
async function buildPresentation() {
  const themeKey = CONTENT.theme && THEMES[CONTENT.theme] ? CONTENT.theme : "grand_rounds_warm";
  const T = THEMES[themeKey];

  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = CONTENT.reporter || "Case Discussion";
  pres.title = `Case Discussion — ${CONTENT.chiefComplaint || ""}`;

  // Per-slide-kind speaker notes: CONTENT.slideNotes = { <kind>: string | string[] }.
  // Kinds: title, profile, timeline, admission, imaging, imagingPlaceholder,
  // pathology, operative, operativePhoto, dx, management, postop, discussion,
  // extra, backToPatient, takeHome. Appended after any notes the generator
  // already writes for that slide. addNotes calls are collected and flushed once
  // (pptxgenjs would otherwise keep only one notes block per slide).
  const slideRegistry = [];
  function addSlideOf(kind) {
    const slide = pres.addSlide();
    const parts = [];
    const origAddNotes = slide.addNotes.bind(slide);
    slide.addNotes = (t) => { parts.push(String(t)); return slide; };
    slideRegistry.push({ kind, slide, parts, origAddNotes });
    return slide;
  }
  function flushSlideNotes() {
    const extra = CONTENT.slideNotes || {};
    slideRegistry.forEach(({ kind, parts, origAddNotes }) => {
      const add = extra[kind];
      if (add !== undefined && add !== null && add !== "") {
        parts.push(Array.isArray(add) ? add.join("\n") : String(add));
      }
      if (parts.length > 0) origAddNotes(parts.join("\n\n"));
    });
  }

  function addHeader(slide, title, subtitle, opts) {
    // opts.titleSize lets callers override title font for long titles
    // (placeholder slides + extraSlide). Default 24pt fits all standard
    // section titles ("Patient Profile", "Admission Course", "Pathology",
    // "Management", etc.) in the 8.8" wide title box. Long titles
    // (≥35 chars) like "CT ABDOMEN/PELVIS WITH IV CONTRAST · DATE" should
    // pass titleSize: 20 to avoid line wrap and subtitle collision.
    const titleSize = (opts && opts.titleSize) ? opts.titleSize : 24;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: 0.35, w: 8.8, h: 0.02,
      fill: { color: T.accent }, line: { width: 0 }
    });
    slide.addText(title, {
      x: 0.6, y: 0.45, w: 8.8, h: 0.55,
      fontSize: titleSize, fontFace: T.headerFont, bold: true, color: T.text, margin: 0
    });
    if (subtitle) {
      slide.addText(subtitle, {
        x: 0.6, y: 0.95, w: 8.8, h: 0.3,
        fontSize: 14, fontFace: T.bodyFont, italic: true, color: T.textLight, margin: 0
      });
    }
    slide.addShape(pres.shapes.LINE, {
      x: 0.6, y: subtitle ? 1.3 : 1.05, w: 8.8, h: 0,
      line: { color: T.rule, width: 0.75 }
    });
  }

  function addLabeledBlock(slide, label, points, x, y, w, h, accentColor, bodySize) {
    if (T.showBorders) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x, y, w, h,
        fill: { color: T.cardBg },
        line: { color: T.rule, width: 0.75 },
      });
    }
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.04, h,
      fill: { color: accentColor || T.accent }, line: { width: 0 }
    });
    slide.addText(String(label).toUpperCase(), {
      x: x + 0.18, y: y + 0.1, w: w - 0.3, h: 0.28,
      fontSize: 14, fontFace: T.headerFont, bold: true,
      color: accentColor || T.accent, charSpacing: 2, margin: 0,
    });
    const items = (Array.isArray(points) ? points : [String(points)])
      .filter(p => p !== undefined && p !== null && String(p).trim() !== "");
    const safe = items.length > 0 ? items : ["N/A"];
    const textItems = safe.map((p, i) => ({
      text: String(p),
      // Card-internal dense bullets use 12pt — 14pt overflowed cards
      // (slides 04 / 08 / 10 had 5+ bullets each). 12pt is a compromise
      // between v1's 10.5pt (too small) and 14pt (won't fit in fixed cards).
      // For better readability, condense bullets in CONTENT.{admission,management}
      // to ≤5 short items per card; fewer items will display larger.
      options: { bullet: { code: "2022" }, breakLine: i < safe.length - 1, fontSize: bodySize || 12, color: T.text }
    }));
    slide.addText(textItems, {
      x: x + 0.18, y: y + 0.45, w: w - 0.3, h: h - 0.55,
      fontFace: T.bodyFont, lineSpacingMultiple: lineSpacingFor(bodySize || 12), valign: "top"
    });
  }

  // ========== SLIDE 1: Title ==========
  {
    const s = addSlideOf("title");
    s.background = { color: T.titleSlideBg };
    s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.04, fill: { color: T.titleSlideAccent }, line: { width: 0 } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.585, w: 10, h: 0.04, fill: { color: T.titleSlideAccent }, line: { width: 0 } });

    if (CONTENT.institution) {
      s.addText(String(CONTENT.institution), {
        x: 0.5, y: 0.45, w: 9, h: 0.35,
        fontSize: 12, fontFace: T.bodyFont, color: T.titleSlideSubtle,
        align: "center", margin: 0
      });
    }
    s.addText("CASE DISCUSSION", {
      x: 0.5, y: 0.9, w: 9, h: 0.35,
      fontSize: 14, fontFace: T.headerFont, bold: true, color: T.titleSlideAccent,
      align: "center", charSpacing: 4, margin: 0
    });

    const age = naIfEmpty(CONTENT.age);
    const sex = CONTENT.sex === "female" ? "woman"
      : (CONTENT.sex === "male" ? "man" : naIfEmpty(CONTENT.sex));
    s.addText(`${age}-year-old ${sex} with`, {
      x: 0.5, y: 1.55, w: 9, h: 0.5,
      fontSize: 20, fontFace: T.headerFont, italic: true, color: T.titleSlideSubtle,
      align: "center", margin: 0
    });

    s.addText(String(naIfEmpty(CONTENT.chiefComplaint)), {
      x: 0.5, y: 2.15, w: 9, h: 1.6,
      fontSize: 34, fontFace: T.headerFont, bold: true, color: T.titleSlideText,
      align: "center", valign: "middle", margin: 0
    });

    s.addShape(pres.shapes.LINE, { x: 4.25, y: 4.0, w: 1.5, h: 0, line: { color: T.titleSlideAccent, width: 1 } });

    s.addText(`Report date: ${naIfEmpty(CONTENT.reportDate)}`, {
      x: 0.5, y: 4.2, w: 9, h: 0.35,
      fontSize: 14, fontFace: T.bodyFont, color: T.titleSlideSubtle,
      align: "center", margin: 0
    });
    s.addText(`Reporter: ${naIfEmpty(CONTENT.reporter)}`, {
      x: 0.5, y: 4.6, w: 9, h: 0.35,
      fontSize: 14, fontFace: T.bodyFont, color: T.titleSlideSubtle,
      align: "center", margin: 0
    });
  }

  // ========== SLIDE 2: Patient Profile ==========
  {
    const s = addSlideOf("profile");
    s.background = { color: T.bg };
    addHeader(s, `Patient Profile: ${naIfEmpty(CONTENT.chartNo)}`, null);

    const p = CONTENT.profile || {};
    const rowH = 0.7, startY = 1.45;
    const rows = [
      { label: "Underlying disease", value: p.underlying },
      { label: "TOCC", value: p.tocc },
      { label: "Substance use", value: p.substance },
      { label: "Family history", value: p.familyHx },
      { label: "Medication", value: p.medication },
    ];
    rows.forEach((r, i) => {
      const y = startY + i * (rowH + 0.05);
      s.addText(r.label.toUpperCase(), {
        x: 0.6, y, w: 2.2, h: rowH,
        fontSize: 14, fontFace: T.headerFont, bold: true, color: T.accent,
        charSpacing: 2, valign: "middle", margin: 0
      });
      let valueText;
      if (Array.isArray(r.value)) {
        const clean = r.value.filter(v => v && String(v).trim() !== "");
        valueText = clean.length > 0 ? clean.join("; ") : "N/A";
      } else {
        valueText = naIfEmpty(r.value);
      }
      s.addText(String(valueText), {
        x: 2.9, y, w: 6.5, h: rowH,
        fontSize: 14, fontFace: T.bodyFont, color: T.text,
        valign: "middle", margin: 0
      });
      if (i < rows.length - 1) {
        s.addShape(pres.shapes.LINE, {
          x: 0.6, y: y + rowH + 0.02, w: 8.8, h: 0,
          line: { color: T.rule, width: 0.5 }
        });
      }
    });
  }

  // ========== SLIDE 3: Clinical Timeline ==========
  {
    const s = addSlideOf("timeline");
    s.background = { color: T.bg };
    addHeader(s, "Clinical Timeline", "Symptom onset → prior workup → admission");

    const tl = (CONTENT.timeline || []).filter(t => t && (t.date || t.event));
    if (tl.length === 0) {
      s.addText("N/A", {
        x: 0.6, y: 2.5, w: 8.8, h: 0.5,
        fontSize: 14, fontFace: T.bodyFont, color: T.textLight, align: "center"
      });
    } else {
      const startY = 1.55;
      const rowH = Math.min(0.5, (5.3 - startY) / tl.length);
      tl.forEach((t, i) => {
        const y = startY + i * rowH;
        s.addShape(pres.shapes.LINE, {
          x: 2.3, y, w: 0, h: rowH,
          line: { color: T.rule, width: 0.75 }
        });
        s.addShape(pres.shapes.OVAL, {
          x: 2.22, y: y + rowH / 2 - 0.08, w: 0.16, h: 0.16,
          fill: { color: T.accent }, line: { width: 0 }
        });
        s.addText(String(t.date || "—"), {
          x: 0.6, y, w: 1.55, h: rowH,
          fontSize: 14, fontFace: T.headerFont, bold: true, color: T.accent,
          align: "right", valign: "middle", margin: 0
        });
        s.addText(String(t.event || "—"), {
          x: 2.5, y, w: 6.9, h: rowH,
          fontSize: 14, fontFace: T.bodyFont, color: T.text,
          valign: "middle", margin: 0
        });
      });
    }
  }

  // ========== SLIDE 4: Admission Course ==========
  {
    const s = addSlideOf("admission");
    s.background = { color: T.bg };
    addHeader(s, "Admission Course", "Symptoms · Physical Examination · Lab");

    const a = CONTENT.admission || {};
    const colW = 2.87, gap = 0.09, startX = 0.6, startY = 1.5;
    const cols = [
      { label: "Symptoms", value: a.symptoms, color: T.accent },
      { label: "Physical Exam", value: a.pe, color: T.accent2 },
      { label: "Lab", value: a.lab, color: T.accent3 },
    ];
    // Adaptive cardH — fixed 4.0 was too short under LibreOffice rendering
    // when any column had a long-prose item that wrapped to 3+ lines (the
    // last item would clip past the slide bottom). Estimate each column's
    // needed height from char count, then use the max so all 3 cards align.
    // Conservative line-fit estimate (calibrated against 2026-05-07 visual
    // QA where PE column overflowed):
    //   ~26 chars per line (12pt body in 2.87" col after bullet indent)
    //   ~0.30" per line (LibreOffice line-height inc. leading)
    //   +0.55" for label header + top padding
    //   +0.20" bottom buffer per item for inter-bullet gap
    // Cap = slide H 5.625 - startY(1.5) - footer margin 0.4 = 3.725" (was 4.5,
    // which overflowed the slide bottom because it ignored startY).
    const capH = 5.625 - startY - 0.4;
    // Estimate card height at a given body font size (12pt calibration scales
    // linearly: smaller font -> more chars per line, shorter line pitch).
    const estCols = (fs) => cols.map((c) => {
      const items = Array.isArray(c.value) ? c.value : [c.value || ""];
      const cpl = Math.floor(26 * 12 / fs);
      let need = 0.55; // header + top pad
      items.forEach((item) => {
        const lines = Math.max(1, Math.ceil(String(item).length / cpl));
        need += lines * 0.30 * linePitchScale(fs);
      });
      return Math.max(1.5, need);
    });
    // Shrink body font (12 -> 11 -> 10.5 -> 10) until the tallest column fits.
    let bodyFs = 12, colHs = estCols(bodyFs);
    for (const fs of BODY_FONT_STEPS.slice(1)) {
      if (Math.max(...colHs) <= capH) break;
      bodyFs = fs; colHs = estCols(fs);
    }
    if (Math.max(...colHs) > 1.3 * capH) console.warn("WARN: Admission Course content likely exceeds card space even at 10pt; trim PE/Lab bullets and check visual QA.");
    colHs = colHs.map((h) => Math.min(capH, h));
    const cardH = Math.max(...colHs);
    cols.forEach((c, i) => {
      const x = startX + i * (colW + gap);
      addLabeledBlock(s, c.label, c.value, x, startY, colW, cardH, c.color, bodyFs);
    });
  }

  // ========== SLIDE 5: Imaging ==========
  {
    const s = addSlideOf("imaging");
    s.background = { color: T.bg };
    addHeader(s, "Imaging", "Radiology findings & impression");

    const imgs = (CONTENT.imaging || []).filter(i => i && (i.modality || i.findings || i.impression));
    if (imgs.length === 0) {
      s.addText("N/A", {
        x: 0.6, y: 2.5, w: 8.8, h: 0.5,
        fontSize: 14, fontFace: T.bodyFont, color: T.textLight, align: "center"
      });
    } else {
      const startY = 1.5, availableH = 4.0;
      const cardH = Math.min(1.95, availableH / imgs.length - 0.1);
      imgs.forEach((img, i) => {
        const y = startY + i * (cardH + 0.1);
        if (T.showBorders) {
          s.addShape(pres.shapes.RECTANGLE, {
            x: 0.6, y, w: 8.8, h: cardH,
            fill: { color: T.cardBg }, line: { color: T.rule, width: 0.75 }
          });
        }
        s.addShape(pres.shapes.RECTANGLE, {
          x: 0.6, y, w: 0.04, h: cardH, fill: { color: T.accent }, line: { width: 0 }
        });
        s.addText(withDate((img.modality || "—").toUpperCase(), img.date), {
          x: 0.8, y: y + 0.1, w: 8.5, h: 0.3,
          fontSize: 14, fontFace: T.headerFont, bold: true, color: T.accent, charSpacing: 2, margin: 0
        });
        const findings = Array.isArray(img.findings)
          ? img.findings.filter(f => f && String(f).trim() !== "")
          : [img.findings].filter(f => f && String(f).trim() !== "");
        // Rotation-profile imagingEmphasis: when set, build rich-text
        // runs so matched phrases (e.g. "valve disease", "coronary
        // lesion" for CVS) are bolded in accent color. Falls back to
        // plain-text path when emphasis unset or no phrase matches.
        const emphPhrases = Array.isArray(CONTENT.imagingEmphasis) ? CONTENT.imagingEmphasis : [];
        if (emphPhrases.length > 0 && findings.length > 0) {
          const textItems = [];
          findings.forEach((f, fi) => {
            const lineText = `• ${f}`;
            const runs = buildEmphasisRuns(lineText, emphPhrases, T.accent, T.text);
            if (runs) {
              runs.forEach((r, ri) => {
                textItems.push({
                  text: r.text,
                  options: {
                    fontSize: 12,
                    color: r.color,
                    bold: r.bold,
                    breakLine: ri === runs.length - 1 && fi < findings.length - 1,
                  },
                });
              });
            } else {
              textItems.push({
                text: lineText,
                options: { fontSize: 12, color: T.text, breakLine: fi < findings.length - 1 },
              });
            }
          });
          s.addText(textItems, {
            x: 0.8, y: y + 0.42, w: 8.5, h: cardH - 0.8,
            fontFace: T.bodyFont, valign: "top", margin: 0,
          });
        } else {
          const findingsText = findings.length > 0 ? findings.map(f => `• ${f}`).join("\n") : "• N/A";
          s.addText(findingsText, {
            x: 0.8, y: y + 0.42, w: 8.5, h: cardH - 0.8,
            // 12pt for imaging findings — 14pt overflowed when ≥4 bullets
            // and the impression line below collided. 12pt fits typical 5-bullet
            // imaging reports cleanly.
            fontSize: 12, fontFace: T.bodyFont, color: T.text, valign: "top", margin: 0
          });
        }
        if (img.impression) {
          s.addText(`Impression: ${img.impression}`, {
            x: 0.8, y: y + cardH - 0.35, w: 8.5, h: 0.3,
            // 12pt italic — at 14pt this line crashed into the last finding bullet
            fontSize: 12, fontFace: T.bodyFont, italic: true, bold: true, color: T.accent, margin: 0
          });
        }
      });
    }
  }

  // ========== SLIDE 5a-5n: Image / EKG placeholders ==========
  // One blank-canvas slide per image-able study (CT/MRI/CXR/Echo/EKG/endoscopy/...)
  // so the presenter can paste a screenshot from PACS / EMR before the talk.
  const slots = buildImageSlots(CONTENT);
  slots.forEach((slot) => {
    const s = addSlideOf("imagingPlaceholder");
    s.background = { color: T.bg };
    // Long modality + date strings overflow at 24pt; pass titleSize: 20 so
    // single-line titles fit. Date into subtitle keeps title concise.
    addHeader(
      s,
      String(slot.modality).toUpperCase(),
      withDate("", slot.date, (d) => `${d} · `) + "Insert image from PACS / EMR",
      { titleSize: 20 },
    );

    // Big dashed placeholder rectangle
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: 1.5, w: 8.8, h: 3.3,
      fill: { color: T.cardBg },
      line: { color: T.accent2, width: 1, dashType: "dash" },
    });
    s.addText("Paste image here  ·  screenshot from PACS / EMR", {
      x: 0.6, y: 2.95, w: 8.8, h: 0.4,
      fontSize: 14, fontFace: T.bodyFont, italic: true, color: T.textLight,
      align: "center", valign: "middle", margin: 0
    });

    // Impression caption below placeholder (as a small reminder)
    if (slot.impression) {
      s.addText(`Impression: ${slot.impression}`, {
        x: 0.6, y: 4.95, w: 8.8, h: 0.5,
        fontSize: 14, fontFace: T.bodyFont, italic: true, color: T.accent,
        align: "center", margin: 0
      });
    }

    // Speaker notes — full findings + impression for offline reference
    const noteLines = [
      withDate(`Image placeholder for ${slot.modality}`, slot.date, (d) => ` (${d})`) + ".",
      "",
      "Workflow: open PACS / EMR → screenshot the key view(s) → paste into the dashed box on this slide. Resize to fit.",
      "",
    ];
    if (slot.findings && slot.findings.length > 0) {
      noteLines.push("Findings (from extracted note):");
      slot.findings.forEach((f) => noteLines.push(`  • ${f}`));
      noteLines.push("");
    }
    if (slot.impression) {
      noteLines.push(`Impression: ${slot.impression}`);
      noteLines.push("");
    }
    noteLines.push("中文：開 PACS / EMR 截圖貼到虛線框內。完整 findings 已抄在此備忘稿，報告時不必背誦。");
    s.addNotes(noteLines.join("\n"));
  });

  // ========== SLIDE 6: Pathology ==========
  // pathology: null -> skip the slide entirely; {} or missing -> "N/A" slide (legacy)
  if (CONTENT.pathology !== null) {
    const s = addSlideOf("pathology");
    s.background = { color: T.bg };
    addHeader(s, "Pathology", "Histopathology report");

    const p = CONTENT.pathology || {};
    const hasAny = p.specimen || p.description || p.diagnosis;
    if (!hasAny) {
      s.addText("N/A", {
        x: 0.6, y: 2.5, w: 8.8, h: 0.5,
        fontSize: 14, fontFace: T.bodyFont, color: T.textLight, align: "center"
      });
    } else {
      if (p.date) {
        s.addText(String(p.date), {
          x: 0.6, y: 1.5, w: 3, h: 0.3,
          fontSize: 14, fontFace: T.headerFont, bold: true, color: T.accent,
          charSpacing: 2, margin: 0
        });
      }
      // Adaptive heights — microscopic description is long prose (often
      // 200+ chars), specimen and diagnosis are typically one line. Fixed
      // rowH=1.05 left microscopic content overflowing into the diagnosis
      // card. Estimate height from char count: 1 line ≈ 0.85" inc header,
      // each extra ~80 chars adds ~0.25".
      const sections = [
        { label: "Specimen", value: p.specimen, color: T.accent2 },
        { label: "Microscopic Description", value: p.description, color: T.accent3 },
        { label: "Pathological Diagnosis", value: p.diagnosis, color: T.accent },
      ];
      const heights = sections.map((sec) => {
        const len = String(sec.value || "").length;
        if (len <= 80) return 0.85;
        if (len <= 200) return 1.4;
        return 2.0;
      });
      let y = 1.9;
      sections.forEach((sec, i) => {
        addLabeledBlock(s, sec.label, sec.value, 0.6, y, 8.8, heights[i], sec.color);
        y += heights[i] + 0.08;
      });
    }
  }

  // ========== SLIDE 6.5: Operative Procedure (rotation profile) ==========
  // Conditional — populated by rotation profiles that set
  // CONTENT.operativeProcedure (e.g. CVS rotation). Sister slides:
  // intraop photo placeholders right after (one per photoSlots).
  if (CONTENT.operativeProcedure) {
    const op = CONTENT.operativeProcedure;
    const hasContent = op.title || op.approach || op.indication || op.reconstruction
      || (Array.isArray(op.keySteps) && op.keySteps.length > 0);
    if (hasContent) {
      const s = addSlideOf("operative");
      s.background = { color: T.bg };
      addHeader(
        s,
        op.title || "Operative Procedure",
        op.subtitle || "Approach · Key Steps · Reconstruction",
      );

      const sections = [];
      if (op.indication) sections.push({ label: "Indication", value: op.indication, color: T.accent2 });
      if (op.approach) sections.push({ label: "Approach", value: op.approach, color: T.accent });
      if (Array.isArray(op.keySteps) && op.keySteps.length > 0) {
        sections.push({ label: "Key Steps", value: op.keySteps, color: T.accent });
      }
      if (op.reconstruction) sections.push({ label: "Reconstruction / Result", value: op.reconstruction, color: T.accent3 });

      // Wrap-aware heights via shared helper — avoids clipping when
      // bullet content wraps to multiple lines (visual QA 2026-05-11).
      const heights = sections.map((sec) => estimateLabeledBlockHeight(sec.value));
      const totalAvail = 4.0;
      const totalNeed = heights.reduce((a, b) => a + b + 0.08, 0);
      const scale = totalNeed > totalAvail ? totalAvail / totalNeed : 1;
      let y = 1.5;
      sections.forEach((sec, i) => {
        const h = heights[i] * scale;
        addLabeledBlock(s, sec.label, sec.value, 0.6, y, 8.8, h, sec.color);
        y += h + 0.08;
      });

      // Speaker notes — intraop findings (long form, doesn't fit on slide)
      if (Array.isArray(op.intraopFindings) && op.intraopFindings.length > 0) {
        const noteLines = ["=== Intraoperative Findings ==="];
        op.intraopFindings.forEach((f) => noteLines.push(`• ${f}`));
        noteLines.push("");
        noteLines.push("中文：完整 intraop findings 已抄在備忘稿，slide 只放手術核心步驟。");
        s.addNotes(noteLines.join("\n"));
      }
    }
  }

  // ========== SLIDE 6.5a-n: Intraop photo placeholders ==========
  // One blank-canvas slide per photoSlots so the presenter can paste
  // intraop camera photos before the talk. Auto-derived from
  // CONTENT.operativeProcedure.photoSlots (max 6).
  const opPhotoSlots = buildOperativePhotoSlots(CONTENT);
  opPhotoSlots.forEach((slot) => {
    const s = addSlideOf("operativePhoto");
    s.background = { color: T.bg };
    addHeader(
      s,
      `Intraop Photo ${slot.index} / ${slot.total}`,
      "Insert photo from intraop camera roll",
      { titleSize: 20 },
    );
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: 1.5, w: 8.8, h: 3.3,
      fill: { color: T.cardBg },
      line: { color: T.accent2, width: 1, dashType: "dash" },
    });
    s.addText("Paste intraop photo here  ·  術中照片貼到此處", {
      x: 0.6, y: 2.95, w: 8.8, h: 0.4,
      fontSize: 14, fontFace: T.bodyFont, italic: true, color: T.textLight,
      align: "center", valign: "middle", margin: 0,
    });
    if (slot.caption) {
      s.addText(slot.caption, {
        x: 0.6, y: 4.95, w: 8.8, h: 0.5,
        fontSize: 14, fontFace: T.bodyFont, italic: true, color: T.accent,
        align: "center", margin: 0,
      });
    }
    s.addNotes([
      `Intraop photo placeholder ${slot.index} of ${slot.total} for "${slot.title}".`,
      "",
      "Workflow: 從相機 / 手機相簿選一張 representative intraop 照片，貼到虛線框內，resize 對齊。報告時口頭描述照片內容。",
    ].join("\n"));
  });

  // ========== SLIDE 7: Tentative Diagnosis ==========
  {
    const s = addSlideOf("dx");
    s.background = { color: T.bg };
    addHeader(s, "Tentative Diagnosis", null);
    const dx = CONTENT.tentativeDx || {};
    addLabeledBlock(s, "Active Problems", dx.active, 0.6, 1.5, 8.8, 1.9, T.accent);
    addLabeledBlock(s, "Underlying", dx.underlying, 0.6, 3.55, 8.8, 1.8, T.accent2);
  }

  // ========== SLIDE 8: Management ==========
  {
    const s = addSlideOf("management");
    s.background = { color: T.bg };
    addHeader(s, "Management", "Plan (from SOAP)");
    const m = CONTENT.management || {};
    // Adaptive heights — fixed (Orders=2.4, Goals=1.3) clipped the last item
    // when Orders had ≥6 entries or Goals last item wrapped to 2+ lines.
    // 8.8" wide → ~95 chars per line at 12pt; +0.45" header.
    const estimateH = (value, fs) => {
      const items = Array.isArray(value) ? value : [value || ""];
      const cpl = Math.floor(95 * 12 / fs);
      const lines = items.reduce((sum, item) => {
        const chars = String(item).length;
        return sum + Math.max(1, Math.ceil(chars / cpl));
      }, 0);
      return Math.max(1.0, 0.60 + lines * 0.29 * linePitchScale(fs));
    };
    // Vertical layout: Orders at y=1.5, Goals after with 0.15 gap; total
    // budget = 3.85" for both cards. Shrink body font 12 -> 11 -> 10.5 -> 10
    // before falling back to proportional scaling (which clipped bullets).
    const totalAvail = 3.85;
    let mFs = 12, ordersH, goalsH;
    for (const fs of BODY_FONT_STEPS) {
      mFs = fs;
      const oNeed = estimateH(m.orders, fs), gNeed = estimateH(m.goals, fs);
      ordersH = Math.min(2.7, oNeed);
      goalsH = Math.min(2.0, gNeed);
      // estimateH is conservative (renders show ~20-30% slack), so a need slightly
      // over a cap still fits; only a need >30% over its cap is real overflow
      // that capping would hide (e.g. 20 short orders).
      const grossOver = oNeed > 1.3 * 2.7 || gNeed > 1.3 * 2.0;
      if (!grossOver && ordersH + goalsH + 0.15 <= totalAvail) break;
      if (fs === 10 && grossOver) console.warn("WARN: Management content likely exceeds card space even at 10pt; trim orders/goals and check visual QA.");
    }
    const totalNeed = ordersH + goalsH + 0.15;
    let oH = ordersH, gH = goalsH;
    if (totalNeed > totalAvail) {
      // Scale both down proportionally; rare case if user data is huge.
      const scale = (totalAvail - 0.15) / (ordersH + goalsH);
      oH = ordersH * scale;
      gH = goalsH * scale;
    }
    addLabeledBlock(s, "Orders", m.orders, 0.6, 1.5, 8.8, oH, T.accent, mFs);
    addLabeledBlock(s, "Treatment Goals", m.goals, 0.6, 1.5 + oH + 0.15, 8.8, gH, T.accent2, mFs);
  }

  // ========== SLIDE 8.5: Postoperative Course (rotation profile) ==========
  // Conditional — populated by rotation profiles that set
  // CONTENT.postopCourse (e.g. CVS rotation).
  if (CONTENT.postopCourse) {
    const po = CONTENT.postopCourse;
    const hasContent = (Array.isArray(po.outcome) && po.outcome.length > 0)
      || (Array.isArray(po.complications) && po.complications.length > 0)
      || po.outcomeVsExpected;
    if (hasContent) {
      const s = addSlideOf("postop");
      s.background = { color: T.bg };
      addHeader(
        s,
        po.title || "Postoperative Course",
        po.subtitle || "ICU / Ward · Outcome vs Expected · Complications",
      );

      const sections = [];
      const courseLabel = po.icuDays != null ? `Hospital Course (ICU ${po.icuDays}d)` : "Hospital Course";
      sections.push({
        label: courseLabel,
        value: Array.isArray(po.outcome) && po.outcome.length > 0 ? po.outcome : ["N/A"],
        color: T.accent,
      });
      sections.push({
        label: "Complications",
        value: Array.isArray(po.complications) && po.complications.length > 0 ? po.complications : ["None"],
        color: T.accent2,
      });
      if (po.outcomeVsExpected) {
        sections.push({
          label: "Outcome vs Expected",
          value: po.outcomeVsExpected,
          color: T.accent3,
        });
      }

      const heights = sections.map((sec) => estimateLabeledBlockHeight(sec.value));
      const totalAvail = 4.0;
      const totalNeed = heights.reduce((a, b) => a + b + 0.08, 0);
      const scale = totalNeed > totalAvail ? totalAvail / totalNeed : 1;
      let y = 1.5;
      sections.forEach((sec, i) => {
        const h = heights[i] * scale;
        addLabeledBlock(s, sec.label, sec.value, 0.6, y, 8.8, h, sec.color);
        y += h + 0.08;
      });
    }
  }

  // ========== SLIDE 9: Discussion Questions ==========
  if (CONTENT.includeDiscussion !== false) {
    const s = addSlideOf("discussion");
    s.background = { color: T.bg };
    addHeader(s, "Discussion Questions", "For group discussion");

    const qs = (CONTENT.discussionQuestions && CONTENT.discussionQuestions.length > 0)
      ? CONTENT.discussionQuestions
      : ["[Discussion question 1]", "[Discussion question 2]", "[Discussion question 3]"];
    const startY = 1.6;
    qs.forEach((q, i) => {
      const y = startY + i * 1.1;
      s.addText(`Q${i + 1}`, {
        x: 0.6, y, w: 0.8, h: 0.4,
        fontSize: 14, fontFace: T.headerFont, bold: true, color: T.accent,
        charSpacing: 2, margin: 0
      });
      // Generator already prints the "Qn" label; strip a duplicated "Q1." prefix from content
      s.addText(String(q).replace(/^\s*Q\d+\s*[.:)]\s*/i, ""), {
        x: 1.4, y, w: 8.0, h: 0.9,
        fontSize: 14, fontFace: T.bodyFont, color: T.text,
        valign: "top", margin: 0
      });
      if (i < qs.length - 1) {
        s.addShape(pres.shapes.LINE, {
          x: 0.6, y: y + 0.95, w: 8.8, h: 0,
          line: { color: T.rule, width: 0.5 }
        });
      }
    });

    // Speaker notes — short trail summary per Q + pointer to companion .md
    const trail = Array.isArray(CONTENT.discussionTrail) ? CONTENT.discussionTrail : [];
    if (trail.length > 0) {
      const trailMdName = path.basename(
        (CONTENT.outputPath || "case.pptx").replace(/\.pptx$/, ".discussion_trail.md")
      );
      const noteLines = ["=== Discussion Trail (summary) ==="];
      qs.forEach((q, i) => {
        noteLines.push("");
        noteLines.push(`Q${i + 1}: ${q}`);
        const t = trail[i];
        if (!t) {
          noteLines.push("  (no trail entry)");
          return;
        }
        if (t.synthesis) noteLines.push(`  Synthesis: ${t.synthesis}`);
        if (Array.isArray(t.citations) && t.citations.length > 0) {
          noteLines.push(`  Top citation: ${t.citations[0]}`);
        }
        if (Array.isArray(t.queries) && t.queries.length > 0) {
          const sources = [...new Set(t.queries.map(qq => qq.source).filter(Boolean))];
          if (sources.length > 0) noteLines.push(`  Sources: ${sources.join(", ")}`);
        }
      });
      noteLines.push("");
      noteLines.push(`Full trail (queries + citations + synthesis): ${trailMdName}`);
      noteLines.push("");
      noteLines.push("中文：完整查詢脈絡（OE / NotebookLM / PubMed 問答 + 引用）見同目錄 .discussion_trail.md，本備忘稿只放 1-2 句 synthesis 與首要 citation。");
      s.addNotes(noteLines.join("\n"));
    }
  }

  // ========== SLIDE 10: Extra discussion (conditional) ==========
  if (CONTENT.extraSlide && CONTENT.extraSlide.title) {
    const x = CONTENT.extraSlide;
    const s = addSlideOf("extra");
    s.background = { color: T.bg };
    // Long extraSlide titles like "Academic Review — cT3N0 colon cancer
    // adjuvant therapy evidence" overflow at 24pt. Auto-detect length and
    // shrink to 20pt for titles ≥35 chars.
    const longTitle = String(x.title).length >= 35;
    addHeader(
      s,
      x.title,
      x.subtitle || "Extended discussion",
      longTitle ? { titleSize: 20 } : undefined,
    );
    const bullets = Array.isArray(x.bullets) ? x.bullets : [];
    const startY = 1.6;
    const rowH = bullets.length <= 3 ? 1.1 : (bullets.length <= 4 ? 0.85 : 0.7);
    bullets.forEach((b, i) => {
      const y = startY + i * rowH;
      s.addText("•", {
        x: 0.6, y, w: 0.4, h: rowH - 0.1,
        fontSize: 18, fontFace: T.headerFont, bold: true, color: T.accent2,
        valign: "top", margin: 0
      });
      s.addText(String(b), {
        x: 1.0, y, w: 8.4, h: rowH - 0.05,
        fontSize: 14, fontFace: T.bodyFont, color: T.text,
        valign: "top", margin: 0
      });
      if (i < bullets.length - 1) {
        s.addShape(pres.shapes.LINE, {
          x: 0.6, y: y + rowH - 0.08, w: 8.8, h: 0,
          line: { color: T.rule, width: 0.5 }
        });
      }
    });
  }

  // ========== SLIDE 11: Back to the Patient (rotation profile) ==========
  // Conditional — populated by rotation profiles that set
  // CONTENT.backToPatient (e.g. CVS rotation Stage 3).
  // Always renders after extraSlide so the structural flow is
  // Discussion → extraSlide → Back to Patient → Take-Home.
  if (CONTENT.backToPatient) {
    const btp = CONTENT.backToPatient;
    const hasContent = (Array.isArray(btp.alternatives) && btp.alternatives.length > 0)
      || (Array.isArray(btp.reflection) && btp.reflection.length > 0)
      || (Array.isArray(btp.lessons) && btp.lessons.length > 0);
    if (hasContent) {
      const s = addSlideOf("backToPatient");
      s.background = { color: T.bg };
      addHeader(
        s,
        btp.title || "Back to the Patient",
        btp.subtitle || "Alternative plans · Reflection · Lessons",
      );

      const sections = [];
      if (Array.isArray(btp.alternatives) && btp.alternatives.length > 0) {
        sections.push({ label: "Alternative Plans", value: btp.alternatives, color: T.accent });
      }
      if (Array.isArray(btp.reflection) && btp.reflection.length > 0) {
        sections.push({ label: "Reflection", value: btp.reflection, color: T.accent2 });
      }
      if (Array.isArray(btp.lessons) && btp.lessons.length > 0) {
        sections.push({ label: "Lessons Learned", value: btp.lessons, color: T.accent3 });
      }
      const heights = sections.map((sec) => estimateLabeledBlockHeight(sec.value));
      const totalAvail = 4.0;
      const totalNeed = heights.reduce((a, b) => a + b + 0.08, 0);
      const scale = totalNeed > totalAvail ? totalAvail / totalNeed : 1;
      let y = 1.5;
      sections.forEach((sec, i) => {
        const h = heights[i] * scale;
        addLabeledBlock(s, sec.label, sec.value, 0.6, y, 8.8, h, sec.color);
        y += h + 0.08;
      });
    }
  }

  // ========== SLIDE 12: Take-Home Summary (rotation profile) ==========
  // Always the LAST slide. Conditional — populated by rotation
  // profiles that set CONTENT.takeHomeSummary.bullets[]. Large
  // numbered bullets, sized for back-of-room legibility.
  if (CONTENT.takeHomeSummary
      && Array.isArray(CONTENT.takeHomeSummary.bullets)
      && CONTENT.takeHomeSummary.bullets.length > 0) {
    const ths = CONTENT.takeHomeSummary;
    const s = addSlideOf("takeHome");
    s.background = { color: T.bg };
    addHeader(s, ths.title || "Take-Home Summary", "Key messages to remember");

    const bullets = ths.bullets.filter((b) => b && String(b).trim() !== "");
    const startY = 1.55;
    const availableH = 4.0;
    // Cap rowH at 0.95"; with 3-4 bullets there's plenty of vertical
    // room for 18pt body. With ≥5 bullets we shrink to 16pt to fit.
    const rowH = Math.min(0.95, availableH / Math.max(bullets.length, 1));
    const bulletFont = bullets.length <= 4 ? 18 : 16;
    bullets.forEach((b, i) => {
      const y = startY + i * rowH;
      // Numbered circle
      s.addShape(pres.shapes.OVAL, {
        x: 0.6, y: y + rowH / 2 - 0.22, w: 0.44, h: 0.44,
        fill: { color: T.accent }, line: { width: 0 },
      });
      s.addText(String(i + 1), {
        x: 0.6, y: y + rowH / 2 - 0.22, w: 0.44, h: 0.44,
        fontSize: 14, fontFace: T.headerFont, bold: true, color: "FFFFFF",
        align: "center", valign: "middle", margin: 0,
      });
      s.addText(String(b), {
        x: 1.2, y, w: 8.2, h: rowH,
        fontSize: bulletFont, fontFace: T.bodyFont, color: T.text,
        valign: "middle", margin: 0,
      });
    });
  }

  flushSlideNotes();
  const outPath = CONTENT.outputPath || "case_discussion.pptx";
  await pres.writeFile({ fileName: outPath });
  console.log(`\n✓ PPTX written (${T.name}) to: ${outPath}`);

  // Companion file: discussion trail .md (only if any trail entry exists)
  if (Array.isArray(CONTENT.discussionTrail) && CONTENT.discussionTrail.length > 0) {
    const trailPath = outPath.replace(/\.pptx$/i, ".discussion_trail.md");
    fs.writeFileSync(trailPath, renderTrailMd(CONTENT));
    console.log(`✓ Discussion trail written to: ${trailPath}`);
  }
  console.log("");
}

// ---- CLI: --content <file.js> --out <deck.pptx> (optional; legacy mode if absent) ----
(function parseCli() {
  const argv = process.argv.slice(2);
  if (argv.length === 0) return; // legacy mode: CONTENT block above
  const die = (msg) => {
    console.error("ERROR (CLI): " + msg);
    console.error("Usage: node generate_case_pptx.js [--content <content.js>] [--out <deck.pptx>]");
    process.exit(2);
  };
  let contentPath = null, outArg = null;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a !== "--content" && a !== "--out") die(`unknown argument: ${a}`);
    const v = argv[i + 1];
    if (!v || v.startsWith("--")) die(`${a} needs a value`);
    if (a === "--content") contentPath = v; else outArg = v;
    i++;
  }
  if (contentPath) {
    let loaded;
    try { loaded = require(path.resolve(contentPath)); }
    catch (e) { die(`cannot load ${contentPath}: ${e.message}`); }
    const c = loaded && loaded.CONTENT ? loaded.CONTENT : loaded;
    if (!c || typeof c !== "object" || Array.isArray(c) || Object.keys(c).length === 0) {
      die(`${contentPath} must export a non-empty CONTENT object (module.exports = CONTENT)`);
    }
    CONTENT = c;
  }
  if (outArg) CONTENT.outputPath = path.resolve(outArg);
})();

buildPresentation().catch(err => {
  console.error("ERROR generating PPTX:", err);
  process.exit(1);
});

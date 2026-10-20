#!/usr/bin/env node
// ============================================================
// Discussion-Only PPTX Template
// ============================================================
// One self-contained generator that produces a standalone deck of
// N discussion-question slides — sister to the main case-discussion
// pptx (use this when the assignment is a focused Q&A block, e.g.
// 學生報告 discussion 段、Journal-club Q discussion, M&M questions).
//
// Format conventions (locked):
//   - Q-number lives IN the title (e.g. "Q1. <title>"); no separate
//     "Q1 · Discussion Question" badge above title.
//   - 3 sections per slide max, each rendered as a labeled card with
//     full border + accent left-bar (matches main case-discussion style).
//   - References at slide bottom, 6pt Calibri, left-aligned, ONE per line.
//   - Theme = grand_rounds_warm (Harvard/Notion editorial — warm cream).
//   - 16:9 (10" × 5.625").
//   - Speaker notes pre-populated with full bullet content + refs.
//
// Run:
//   1. cp this file → /tmp/<name>.js (or anywhere)
//   2. Edit `QUESTIONS` array + `OUTPUT_PATH` constant
//   3. NODE_PATH="$(npm root -g)" node /tmp/<name>.js
//
// Constraints (avoid layout overflow):
//   - Each section ≤ 3 bullets, each bullet ≤ ~95 chars (1 line at 11pt)
//   - Title ≤ ~65 chars at 20pt (wraps to 2 lines max)
//   - Refs ≤ 4 per slide (more = drops below slide edge)
// ============================================================

const pptxgen = require("pptxgenjs");

const T = {
  bg: "F5F1EA",
  cardBg: "FCFAF5",
  text: "2B2318",
  textLight: "6E5B43",
  accent: "8B1A1A",       // Harvard crimson
  accent2: "B87333",       // warm copper
  accent3: "8B7355",       // warm taupe
  rule: "D9C8A9",
  headerFont: "Georgia",
  bodyFont: "Calibri",
};

// EDIT ME — output path
const OUTPUT_PATH = "discussion_only.pptx";

// ============================================================
// EDIT ME — populate one entry per discussion question.
// Schema:
//   qNum     — "Q1" / "Q2" / "Q3" ... rendered as title prefix
//   title    — short question (≤ 65 chars, wraps 2 lines max at 20pt)
//   subtitle — one-line italic context under title
//   sections — array of { label, bullets[] }; 2-3 sections per slide,
//              each bullet ends with "[N]" pointing to a ref
//   refs     — array of "[N] Author et al. Title. Journal Year." strings
// ============================================================
const QUESTIONS = [
  {
    qNum: "Q1",
    title: "[Question title — short, ≤ 65 chars]",
    subtitle: "[One-line italic context]",
    sections: [
      {
        label: "[Section 1 label]",
        bullets: [
          "[Bullet 1 with citation reference] [1]",
          "[Bullet 2 with citation reference] [2]",
          "[Bullet 3 ≤ 95 chars] [3]",
        ],
      },
      {
        label: "[Section 2 label]",
        bullets: [
          "[Bullet 1] [4]",
          "[Bullet 2] [1]",
        ],
      },
      {
        label: "[Section 3 label — typically 'Apply to This Patient']",
        bullets: [
          "[Synthesis bullet — how the evidence applies to this case]",
        ],
      },
    ],
    refs: [
      "[1] FirstAuthor LB et al. Title. Journal Year;Vol(Issue):Pages.",
      "[2] FirstAuthor LB et al. Title. Journal Year;Vol(Issue):Pages.",
      "[3] FirstAuthor LB et al. Title. Journal Year;Vol(Issue):Pages.",
      "[4] FirstAuthor LB et al. Title. Journal Year;Vol(Issue):Pages.",
    ],
  },
  // duplicate the above object for Q2, Q3, ... as needed
];

// ============================================================
async function build() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9"; // 10" × 5.625"
  pres.title = "Discussion Questions";

  QUESTIONS.forEach((q) => {
    const s = pres.addSlide();
    s.background = { color: T.bg };

    // ---- Header (Q-number merged into title; no separate badge) ----
    s.addShape(pres.shapes.LINE, {
      x: 0.6, y: 0.3, w: 8.8, h: 0,
      line: { color: T.accent, width: 1.5 },
    });
    // Title with Q# prefix (e.g. "Q1. <title>")
    s.addText(`${q.qNum}. ${q.title}`, {
      x: 0.6, y: 0.38, w: 8.8, h: 0.75,
      fontSize: 20, fontFace: T.headerFont, bold: true,
      color: T.text, margin: 0,
    });
    // Subtitle
    s.addText(q.subtitle, {
      x: 0.6, y: 1.18, w: 8.8, h: 0.28,
      fontSize: 11, fontFace: T.bodyFont, italic: true,
      color: T.textLight, margin: 0,
    });
    // Rule line under header
    s.addShape(pres.shapes.LINE, {
      x: 0.6, y: 1.50, w: 8.8, h: 0,
      line: { color: T.rule, width: 0.75 },
    });

    // ---- Body sections ----
    const sectionsArr = q.sections;
    const startY = 1.58;
    const availH = 3.32; // body 1.58 → 4.90 (refs start at 4.95)
    const sectColors = [T.accent, T.accent2, T.accent3];

    // Wrap-aware height estimator (11pt body in 8.4" wide card ≈ 95 chars/line)
    const estH = (bullets) => 0.45 + bullets.reduce((sum, b) => {
      const lines = Math.max(1, Math.ceil(String(b).length / 95));
      return sum + lines * 0.30;
    }, 0) + 0.10;

    const heights = sectionsArr.map((s) => estH(s.bullets));
    const totalNeed = heights.reduce((a, b) => a + b + 0.08, 0);
    const scale = totalNeed > availH ? availH / totalNeed : 1;

    let y = startY;
    sectionsArr.forEach((sect, i) => {
      const h = heights[i] * scale;
      const color = sectColors[i % 3];
      // Card background + border
      s.addShape(pres.shapes.RECTANGLE, {
        x: 0.6, y, w: 8.8, h,
        fill: { color: T.cardBg },
        line: { color: T.rule, width: 0.75 },
      });
      // Left accent bar
      s.addShape(pres.shapes.RECTANGLE, {
        x: 0.6, y, w: 0.06, h, fill: { color }, line: { width: 0 },
      });
      // Section label
      s.addText(sect.label.toUpperCase(), {
        x: 0.8, y: y + 0.04, w: 8.55, h: 0.3,
        fontSize: 11, fontFace: T.headerFont, bold: true,
        color, charSpacing: 2, margin: 0,
      });
      // Bullets
      const bulletRuns = sect.bullets.map((b, bi) => ({
        text: String(b),
        options: {
          bullet: { code: "2022" },
          breakLine: bi < sect.bullets.length - 1,
          fontSize: 11, color: T.text,
        },
      }));
      s.addText(bulletRuns, {
        x: 0.9, y: y + 0.36, w: 8.4, h: h - 0.4,
        fontFace: T.bodyFont, lineSpacingMultiple: 1.2,
        valign: "top", margin: 0,
      });
      y += h + 0.08;
    });

    // ---- Footer: References (6pt, ONE per line, left-aligned) ----
    const refY = 4.95;
    const refRuns = q.refs.map((r, ri) => ({
      text: String(r),
      options: { fontSize: 6, color: T.textLight, breakLine: ri < q.refs.length - 1 },
    }));
    s.addText(refRuns, {
      x: 0.6, y: refY, w: 8.8, h: 0.60,
      fontFace: T.bodyFont, align: "left", valign: "top", margin: 0,
      lineSpacingMultiple: 1.05,
    });

    // ---- Speaker notes — full content for presenter ----
    const noteLines = [
      `${q.qNum}: ${q.title}`,
      "",
      ...sectionsArr.flatMap((sect) => [
        `— ${sect.label} —`,
        ...sect.bullets.map((b) => `  • ${b}`),
        "",
      ]),
      "References:",
      ...q.refs.map((r) => `  ${r}`),
    ];
    s.addNotes(noteLines.join("\n"));
  });

  await pres.writeFile({ fileName: OUTPUT_PATH });
  console.log(`✓ Discussion-only PPTX written to: ${OUTPUT_PATH}`);
}

build().catch((err) => {
  console.error("ERROR:", err);
  process.exit(1);
});

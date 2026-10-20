#!/usr/bin/env node
// ============================================================
// Topic-agnostic PPTX Generator (cases / discussion / analysis)
// ============================================================
// Usage: NODE_PATH="$(npm root -g)" node generate_pptx.js [output.pptx]
//
// Adapt the CONTENT object below with your actual content,
// then run the script to generate the PPTX.
// ============================================================
// v2 font sizing (2026-05-07)
// refactor. Body fontSize floor = 14pt; section header floor = 28pt; title-
// slide hero / cover keeps larger sizes (40, 20). Previously body sizes
// ranged 10.5-13pt, unreadable from the back of a teaching room. fontSize: 9
// for source citations is exempt (caption-class, intentionally small).
// If you add new slide.addText() calls, use:
//   - fontSize: 14 (default body)
//   - fontSize: 16 (preferred body / objectives / list items)
//   - fontSize: 28 (slide header)
//   - fontSize: 40 (cover hero)
// ============================================================

const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");

// Import icons — add or swap as needed for your topic
const {
  FaBalanceScale, FaBullhorn, FaShieldAlt, FaUsers, FaBookOpen,
  FaHeart, FaQuestionCircle, FaHandshake, FaStethoscope,
  FaLightbulb, FaGavel, FaClipboardCheck
} = require("react-icons/fa");

// ============================================================
// CONTENT — Replace this with your actual content
// ============================================================
const CONTENT = {
  // --- Metadata ---
  title: "範例主題：如何做好交班",
  subtitle: "Example topic: how to do a good handover",
  footer: "範例討論課",
  author: "Example Author",
  // Default: ./output.pptx in the current directory; override with 2nd CLI arg
  outputPath: require("path").resolve(process.argv[2] || "output.pptx"),

  // --- Learning Objectives ---
  objectives: [
    "說明交班時最容易遺漏的資訊類型",
    "討論交班資訊不完整時可能產生的後果",
    "練習使用結構化格式進行簡短而完整的交班",
  ],

  // --- Cases ---
  // Each case generates 2-3 slides: description, discussion, analysis
  cases: [
    {
      title: "案例一：夜班交班遺漏待辦事項",
      subtitle: "A Missed To-Do Item at Night Handover",
      description: [
        "小明是日班的新進成員，下班前口頭交班給夜班同事",
        "交班時只講了目前狀況，沒有提到下午已排定、需要夜間追蹤的事項",
        "夜班同事以為沒有待辦事項，直到隔天早上才發現遺漏",
        "所幸沒有造成嚴重後果，但團隊因此多花了半天時間補救",
      ],
      coreIssue: "核心議題：口頭交班缺乏固定格式，容易遺漏待辦事項",
      source: "【自編範例案例，僅供示範格式，非真實事件】",
      discussionQuestions: [
        "這次遺漏最可能發生在交班流程的哪一個環節？",
        "如果你是小明，交班前可以先做哪些準備？",
        "團隊可以建立什麼樣的固定格式來降低遺漏風險？",
      ],
      // Optional analysis cards (1-4 items, any labels you choose; omit to skip the slide)
      analysis: [
        { label: "背景", text: "交班是團隊延續工作品質的關鍵環節" },
        { label: "風險", text: "口頭交班缺乏固定格式，待辦事項容易遺漏" },
        { label: "做法", text: "使用結構化格式，並請接手者複述重點" },
        { label: "結果", text: "遺漏減少，團隊不必事後補救" },
      ],
      suggestion: "處理建議：使用結構化交班格式（如 SBAR）→ 交班時當面確認重點 → 書面紀錄待辦事項",
    },
    // Add more cases here following the same structure...
  ],

  // --- Summary Principles ---
  summaryPrinciples: [
    { title: "先講最重要的事", desc: "交班從風險最高、最需要接手追蹤的資訊開始說起", iconName: "heart" },
    { title: "使用固定格式", desc: "結構化格式能減少遺漏，也讓接手的人容易抓重點", iconName: "bullhorn" },
    { title: "確認對方聽懂", desc: "請接手的人複述重點，確認訊息已正確傳達", iconName: "users" },
    { title: "團隊共同負責", desc: "交班品質是整個團隊的責任，而非單一個人的事", iconName: "handshake" },
  ],

  // --- Guidelines (optional) ---
  guidelines: [
    "交班前先整理重點，避免臨時想到什麼講什麼",
    "待辦事項與時間點要明確說出",
    "不確定的資訊要標示為「待確認」",
    "交班後留下書面紀錄，方便事後查閱",
    "發現遺漏時，立即聯絡原交班者補充",
  ],
  guidelinesTitle: "交班實務指引",
  guidelinesSubtitle: "Practical Handover Guidelines",
  analysisTitle: "分析",          // title suffix for the analysis slide
  analysisSubtitle: "Analysis",
  guidelinesFootnote: "以上為自編範例內容，請替換成你自己的主題與資料",

  // --- References ---
  references: [
    "範例參考資料一：請替換成你自己的文獻或資料來源",
    "範例參考資料二：請替換成你自己的文獻或資料來源",
  ],
};

// ============================================================
// COLOR PALETTE
// ============================================================
const C = {
  darkBg: "1B3A4B",
  primary: "065A82",
  teal: "1C7293",
  lightBg: "F0F5F9",
  white: "FFFFFF",
  offWhite: "E8EEF2",
  text: "2D3748",
  textLight: "718096",
  accent: "D94F5C",
  accentGreen: "2B8A6E",
  accentGold: "D4A843",
};

// ============================================================
// ANALYSIS CARD COLORS — cycled across the analysis items
// ============================================================
const ANALYSIS_COLORS = [C.accentGreen, C.accent, C.primary, C.accentGold];

// Accept new `analysis: [{label,text}]` or legacy `principles: {key: text}` objects
function getAnalysisItems(cs) {
  if (Array.isArray(cs.analysis) && cs.analysis.length) return cs.analysis.slice(0, 4);
  if (cs.principles) {
    const legacy = { beneficence: "行善", nonmaleficence: "不傷害", autonomy: "自主", justice: "公正" };
    return Object.keys(legacy).filter(k => cs.principles[k]).map(k => ({ label: legacy[k], text: cs.principles[k] }));
  }
  return [];
}

// ============================================================
// ICON MAP — maps string names to react-icon components
// ============================================================
const ICON_MAP = {
  balance: FaBalanceScale, bullhorn: FaBullhorn, shield: FaShieldAlt,
  users: FaUsers, book: FaBookOpen, heart: FaHeart,
  question: FaQuestionCircle, handshake: FaHandshake,
  stethoscope: FaStethoscope, lightbulb: FaLightbulb,
  gavel: FaGavel, clipboard: FaClipboardCheck,
};

// ============================================================
// ICON HELPERS
// ============================================================
function renderIconSvg(IconComponent, color = "#000000", size = 256) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
}

async function iconToBase64Png(IconComponent, color, size = 256) {
  const svg = renderIconSvg(IconComponent, color, size);
  const pngBuffer = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + pngBuffer.toString("base64");
}

// ============================================================
// FACTORY FUNCTIONS (PptxGenJS mutates options — always create fresh)
// ============================================================
const makeShadow = () => ({ type: "outer", blur: 6, offset: 2, angle: 135, color: "000000", opacity: 0.12 });
const makeCardShadow = () => ({ type: "outer", blur: 4, offset: 1, angle: 135, color: "000000", opacity: 0.08 });

// ============================================================
// SLIDE COMPONENT HELPERS
// ============================================================
let pres; // will be set in buildPresentation()

function addHeader(slide, title, subtitle) {
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: C.primary } });
  slide.addText(title, {
    x: 0.6, y: 0.2, w: 8.8, h: 0.55,
    fontSize: 28, fontFace: "Georgia", bold: true, color: C.darkBg, margin: 0
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.6, y: 0.72, w: 8.8, h: 0.32,
      fontSize: 14, fontFace: "Calibri", color: C.textLight, italic: true, margin: 0
    });
  }
  slide.addShape(pres.shapes.LINE, {
    x: 0.6, y: subtitle ? 1.05 : 0.82, w: 8.8, h: 0,
    line: { color: C.offWhite, width: 1.5 }
  });
}

function addCaseCard(slide, points, startY, height) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: startY, w: 8.8, h: height,
    fill: { color: C.white }, shadow: makeCardShadow(),
    line: { color: C.offWhite, width: 0.5 }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: startY, w: 0.06, h: height,
    fill: { color: C.teal }
  });
  const textItems = points.map((p, i) => ({
    text: p,
    options: { bullet: true, breakLine: i < points.length - 1, fontSize: 14, color: C.text }
  }));
  slide.addText(textItems, {
    x: 0.9, y: startY + 0.1, w: 8.2, h: height - 0.2,
    fontFace: "Calibri", lineSpacingMultiple: 1.3, valign: "top"
  });
}

function addDiscussionBox(slide, questions, startY, height) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: startY, w: 8.8, h: height,
    fill: { color: "FFF8F0" },
    line: { color: C.accentGold, width: 1 }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: startY, w: 0.06, h: height,
    fill: { color: C.accentGold }
  });
  const textItems = questions.map((q, i) => ({
    text: q,
    options: { bullet: true, breakLine: i < questions.length - 1, fontSize: 14, color: C.text }
  }));
  slide.addText(textItems, {
    x: 0.9, y: startY + 0.1, w: 8.2, h: height - 0.2,
    fontFace: "Calibri", lineSpacingMultiple: 1.3, valign: "top"
  });
}

function addAnalysisCards(slide, items, startY) {
  const n = Math.max(1, items.length);
  const gap = 0.07;
  const totalW = 8.8;
  const colW = (totalW - gap * (n - 1)) / n;
  const startX = 0.6;
  items.forEach((item, i) => {
    const color = ANALYSIS_COLORS[i % ANALYSIS_COLORS.length];
    const x = startX + i * (colW + gap);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: startY, w: colW, h: 1.65,
      fill: { color: C.white }, shadow: makeCardShadow(),
      line: { color: C.offWhite, width: 0.5 }
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: startY, w: colW, h: 0.05,
      fill: { color }
    });
    slide.addText(item.label || "", {
      x, y: startY + 0.12, w: colW, h: 0.3,
      fontSize: 14, fontFace: "Georgia", bold: true, color, align: "center", margin: 0
    });
    slide.addText(item.text || "", {
      x: x + 0.1, y: startY + 0.42, w: colW - 0.2, h: 1.15,
      fontSize: 14, fontFace: "Calibri", color: C.text, valign: "top", margin: 0
    });
  });
}

function addSuggestionBox(slide, text, startY) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: startY, w: 8.8, h: 0.55,
    fill: { color: "EDF7ED" },
    line: { color: C.accentGreen, width: 0.8 }
  });
  slide.addText(text, {
    x: 0.85, y: startY + 0.02, w: 8.3, h: 0.5,
    fontSize: 14, fontFace: "Calibri", color: C.accentGreen, bold: true, valign: "middle", margin: 0
  });
}

function addIssueCallout(slide, text, startY) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: startY, w: 8.8, h: 0.7,
    fill: { color: "FFF0F0" }, line: { color: C.accent, width: 0.8 }
  });
  slide.addText(text, {
    x: 0.85, y: startY + 0.03, w: 8.3, h: 0.64,
    fontSize: 14, fontFace: "Calibri", color: C.accent, bold: true, valign: "middle", margin: 0
  });
}

// ============================================================
// MAIN BUILD FUNCTION
// ============================================================
async function buildPresentation() {
  pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = CONTENT.author || "Discussion Class";
  pres.title = CONTENT.title;

  // Pre-render icons
  const iconWhite = async (name) => iconToBase64Png(ICON_MAP[name] || FaBalanceScale, "#FFFFFF", 256);
  const iconBalance = await iconToBase64Png(FaBalanceScale, "#FFFFFF", 256);
  const iconBook = await iconToBase64Png(FaBookOpen, "#FFFFFF", 256);

  // Pre-render summary icons
  const summaryIcons = {};
  for (const p of CONTENT.summaryPrinciples) {
    if (!summaryIcons[p.iconName]) {
      summaryIcons[p.iconName] = await iconWhite(p.iconName);
    }
  }

  // ========== SLIDE: Title ==========
  const s1 = pres.addSlide();
  s1.background = { color: C.darkBg };
  s1.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.12, fill: { color: C.teal } });
  s1.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.505, w: 10, h: 0.12, fill: { color: C.teal } });
  s1.addShape(pres.shapes.OVAL, { x: 4.3, y: 0.6, w: 1.4, h: 1.4, fill: { color: C.primary } });
  s1.addImage({ data: iconBalance, x: 4.55, y: 0.85, w: 0.9, h: 0.9 });
  s1.addText(CONTENT.title, {
    x: 0.5, y: 2.2, w: 9, h: 0.9,
    fontSize: 40, fontFace: "Georgia", bold: true, color: C.white, align: "center", margin: 0
  });
  s1.addText(CONTENT.subtitle, {
    x: 0.5, y: 3.1, w: 9, h: 0.5,
    fontSize: 16, fontFace: "Calibri", color: C.teal, align: "center", italic: true, margin: 0
  });
  s1.addShape(pres.shapes.LINE, { x: 3, y: 3.8, w: 4, h: 0, line: { color: C.teal, width: 1.5 } });
  if (CONTENT.footer) {
    s1.addText(CONTENT.footer, {
      x: 0.5, y: 4.1, w: 9, h: 0.45,
      fontSize: 15, fontFace: "Calibri", color: C.textLight, align: "center", margin: 0
    });
  }

  // ========== SLIDE: Learning Objectives ==========
  if (CONTENT.objectives && CONTENT.objectives.length > 0) {
    const s2 = pres.addSlide();
    s2.background = { color: C.lightBg };
    addHeader(s2, "學習目標", "Learning Objectives");
    CONTENT.objectives.forEach((text, i) => {
      const y = 1.3 + i * 1.35;
      const num = String(i + 1).padStart(2, "0");
      s2.addShape(pres.shapes.RECTANGLE, {
        x: 0.6, y, w: 8.8, h: 1.1,
        fill: { color: C.white }, shadow: makeCardShadow()
      });
      s2.addShape(pres.shapes.OVAL, { x: 0.85, y: y + 0.18, w: 0.74, h: 0.74, fill: { color: C.primary } });
      s2.addText(num, {
        x: 0.85, y: y + 0.18, w: 0.74, h: 0.74,
        fontSize: 20, fontFace: "Georgia", bold: true, color: C.white, align: "center", valign: "middle", margin: 0
      });
      s2.addText(text, {
        x: 1.85, y: y + 0.1, w: 7.3, h: 0.9,
        fontSize: 16, fontFace: "Calibri", color: C.text, valign: "middle", margin: 0
      });
    });
  }

  // ========== SLIDES: Cases ==========
  for (const cs of CONTENT.cases) {
    // --- Case Description ---
    const sd = pres.addSlide();
    sd.background = { color: C.lightBg };
    addHeader(sd, cs.title, cs.subtitle);
    const cardH = Math.max(1.5, cs.description.length * 0.42);
    addCaseCard(sd, cs.description, 1.15, cardH);
    if (cs.coreIssue) {
      addIssueCallout(sd, cs.coreIssue, 1.15 + cardH + 0.2);
    }
    if (cs.source) {
      sd.addText(cs.source, {
        x: 0.6, y: 4.7, w: 8.8, h: 0.3,
        fontSize: 9, fontFace: "Calibri", color: C.textLight, italic: true, margin: 0
      });
    }

    // --- Discussion Questions ---
    if (cs.discussionQuestions && cs.discussionQuestions.length > 0) {
      const sq = pres.addSlide();
      sq.background = { color: C.lightBg };
      addHeader(sq, cs.title.split("：")[0] + "：討論問題", "Discussion Questions");
      const boxH = Math.max(1.0, cs.discussionQuestions.length * 0.4);
      addDiscussionBox(sq, cs.discussionQuestions, 1.15, boxH);
    }

    // --- Analysis cards (optional) ---
    const analysisItems = getAnalysisItems(cs);
    if (analysisItems.length) {
      const sa = pres.addSlide();
      sa.background = { color: C.lightBg };
      addHeader(sa, cs.title.split("：")[0] + "：" + (CONTENT.analysisTitle || "分析"), CONTENT.analysisSubtitle || "Analysis");
      addAnalysisCards(sa, analysisItems, 1.15);
      if (cs.suggestion) {
        addSuggestionBox(sa, cs.suggestion, 3.05);
      }
    }
  }

  // ========== SLIDE: Summary Principles ==========
  if (CONTENT.summaryPrinciples && CONTENT.summaryPrinciples.length > 0) {
    const ss = pres.addSlide();
    ss.background = { color: C.darkBg };
    ss.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: C.teal } });
    ss.addText("核心原則總整理", {
      x: 0.6, y: 0.25, w: 8.8, h: 0.55,
      fontSize: 28, fontFace: "Georgia", bold: true, color: C.white, margin: 0
    });
    const principleColors = [C.accent, C.accentGold, C.teal, C.accentGreen, C.primary];
    CONTENT.summaryPrinciples.forEach((p, i) => {
      const y = 1.05 + i * 1.1;
      const pColor = principleColors[i % principleColors.length];
      ss.addShape(pres.shapes.RECTANGLE, {
        x: 0.6, y, w: 8.8, h: 0.9,
        fill: { color: C.darkBg }, line: { color: "2A5065", width: 0.8 }
      });
      ss.addShape(pres.shapes.RECTANGLE, {
        x: 0.6, y, w: 0.06, h: 0.9, fill: { color: pColor }
      });
      ss.addShape(pres.shapes.OVAL, { x: 0.9, y: y + 0.15, w: 0.6, h: 0.6, fill: { color: pColor } });
      if (summaryIcons[p.iconName]) {
        ss.addImage({ data: summaryIcons[p.iconName], x: 1.0, y: y + 0.25, w: 0.4, h: 0.4 });
      }
      ss.addText(p.title, {
        x: 1.7, y: y + 0.08, w: 7.5, h: 0.35,
        fontSize: 15, fontFace: "Georgia", bold: true, color: C.white, margin: 0
      });
      ss.addText(p.desc, {
        x: 1.7, y: y + 0.45, w: 7.5, h: 0.35,
        fontSize: 14, fontFace: "Calibri", color: C.textLight, margin: 0
      });
    });
  }

  // ========== SLIDE: Guidelines ==========
  if (CONTENT.guidelines && CONTENT.guidelines.length > 0) {
    const sg = pres.addSlide();
    sg.background = { color: C.lightBg };
    addHeader(sg, CONTENT.guidelinesTitle || "指引", CONTENT.guidelinesSubtitle);
    CONTENT.guidelines.forEach((text, i) => {
      const y = 1.2 + i * 0.72;
      sg.addShape(pres.shapes.OVAL, { x: 0.75, y: y + 0.05, w: 0.52, h: 0.52, fill: { color: C.primary } });
      sg.addText(String(i + 1), {
        x: 0.75, y: y + 0.05, w: 0.52, h: 0.52,
        fontSize: 16, fontFace: "Georgia", bold: true, color: C.white, align: "center", valign: "middle", margin: 0
      });
      sg.addText(text, {
        x: 1.5, y, w: 8, h: 0.62,
        fontSize: 14, fontFace: "Calibri", color: C.text, valign: "middle", margin: 0
      });
      if (i < CONTENT.guidelines.length - 1) {
        sg.addShape(pres.shapes.LINE, {
          x: 1.5, y: y + 0.66, w: 7.5, h: 0,
          line: { color: C.offWhite, width: 0.8 }
        });
      }
    });
    if (CONTENT.guidelinesFootnote) {
      const footY = 1.2 + CONTENT.guidelines.length * 0.72 + 0.15;
      sg.addShape(pres.shapes.RECTANGLE, {
        x: 0.6, y: footY, w: 8.8, h: 0.55,
        fill: { color: "EDF7ED" }, line: { color: C.accentGreen, width: 0.8 }
      });
      sg.addText(CONTENT.guidelinesFootnote, {
        x: 0.85, y: footY + 0.03, w: 8.3, h: 0.49,
        fontSize: 14, fontFace: "Calibri", color: C.accentGreen, bold: true, valign: "middle", margin: 0
      });
    }
  }

  // ========== SLIDE: References ==========
  if (CONTENT.references && CONTENT.references.length > 0) {
    const sr = pres.addSlide();
    sr.background = { color: C.darkBg };
    sr.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: C.teal } });
    sr.addShape(pres.shapes.OVAL, { x: 4.3, y: 0.3, w: 1.4, h: 1.4, fill: { color: C.primary } });
    sr.addImage({ data: iconBook, x: 4.55, y: 0.55, w: 0.9, h: 0.9 });
    sr.addText("延伸閱讀", {
      x: 0.5, y: 1.85, w: 9, h: 0.5,
      fontSize: 28, fontFace: "Georgia", bold: true, color: C.white, align: "center", margin: 0
    });
    const refItems = CONTENT.references.map((r, i) => ({
      text: `${i + 1}. ${r}`,
      options: { breakLine: i < CONTENT.references.length - 1, fontSize: 14, color: "A0B4C4" }
    }));
    sr.addText(refItems, {
      x: 0.8, y: 2.55, w: 8.4, h: 2.8,
      fontFace: "Calibri", valign: "top", lineSpacingMultiple: 1.4, margin: 0
    });
    sr.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.505, w: 10, h: 0.12, fill: { color: C.teal } });
  }

  // ========== WRITE FILE ==========
  await pres.writeFile({ fileName: CONTENT.outputPath });
  console.log("PPTX created: " + CONTENT.outputPath);
}

buildPresentation().catch(err => {
  console.error("Error:", err);
  process.exit(1);
});

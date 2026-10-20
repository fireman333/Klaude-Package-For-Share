// ============================================================
// EXAMPLE — 完整填寫後的 CONTENT（可直接跑生成）
// ============================================================
// 用途：給使用者看「塞滿真實資料後的 CONTENT 長什麼樣」。複製 case_content_template.js
// 不確定某欄位怎麼寫時，對照本檔同欄位的格式。
//
// 本例為**完全虛構的教學案例**（distal sigmoid adenocarcinoma, cT3N0M0），
// 所有內容皆為編造，絕不可當真實病歷使用。
// ============================================================

const CONTENT = {
  // ---- Theme ----
  theme: "grand_rounds_warm",

  // ---- Slide 1: Title ----
  age: 68,
  sex: "male",
  chiefComplaint: "Change in bowel habit with hematochezia for 2 months",
  reportDate: "2026/04/22",
  reporter: "（報告者姓名）",
  institution: "範例醫院 · 範例科別",

  // ---- Slide 2: Patient Profile ----
  chartNo: "1234567",   // 在簡報頁面自行遮罩或不顯示全碼
  profile: {
    underlying: [
      "Hypertension, on amlodipine 5 mg QD × 10 yrs",
      "Type 2 diabetes mellitus, on metformin 500 mg BID × 6 yrs, HbA1c 6.8%",
      "Dyslipidemia, on atorvastatin 20 mg QHS",
    ],
    tocc:
      "Retired civil servant; no recent travel; no sick contact; no cluster.",
    substance:
      "Alcohol: social only (<1 drink/week). Betel nut: none. Cigarette: 20 pack-year, quit 8 years ago.",
    familyHx:
      "Father died of gastric cancer at 72; no first-degree relative with colorectal cancer.",
    medication: [
      "Amlodipine 5 mg PO QD",
      "Metformin 500 mg PO BID",
      "Atorvastatin 20 mg PO QHS",
      "Aspirin 100 mg PO QD (for primary prevention; held 7 days before OP)",
    ],
  },

  // ---- Slide 3: Clinical Timeline (oldest → newest) ----
  timeline: [
    { date: "2 months ago", event: "Onset of change in bowel habit — alternating diarrhea & constipation, caliber decreased" },
    { date: "6 weeks ago", event: "Intermittent bright-red blood mixed with stool; denied abdominal pain" },
    { date: "2026/03/28", event: "Clinic visit → FOBT positive; referred for colonoscopy" },
    { date: "2026/04/05", event: "Colonoscopy: fungating mass at distal sigmoid, ~35 cm from anal verge; biopsy obtained" },
    { date: "2026/04/08", event: "Pathology: moderately differentiated adenocarcinoma" },
    { date: "2026/04/12", event: "Staging CT abdomen/pelvis with contrast: T3 lesion, no regional LN enlargement, no distant metastasis" },
    { date: "2026/04/15", event: "Staging CT chest: no pulmonary metastasis" },
    { date: "2026/04/18", event: "CEA 5.8 ng/mL (slightly elevated)" },
    { date: "2026/04/20", event: "Admitted for elective low anterior resection (LAR)" },
    { date: "2026/04/22", event: "Case discussion (today)" },
  ],

  // ---- Slide 4: Admission Course ----
  admission: {
    symptoms: [
      "(+) Change in bowel habit × 2 months",
      "(+) Intermittent hematochezia × 6 weeks",
      "(+) Mild fatigue, weight loss 3 kg / 2 months",
      "(−) Abdominal pain, nausea, vomiting",
      "(−) Fever, night sweat",
      "(−) Tenesmus, urgency",
    ],
    pe: [
      "Vitals: BP 132/78 mmHg, HR 76/min, RR 16/min, BT 36.6°C, SpO₂ 98% on room air",
      "General: alert, well-nourished, no pallor",
      "HEENT: no icterus, no lymphadenopathy",
      "Chest: clear breath sounds, regular heart rhythm, no murmur",
      "Abdomen: soft, non-tender, no palpable mass, no hepatosplenomegaly, bowel sounds normoactive",
      "DRE: no palpable mass, no blood on examining finger",
      "Extremities: no edema, peripheral pulses 2+",
    ],
    lab: [
      "2026/04/20: WBC 6.8 k/μL, Hb 12.4 g/dL, MCV 82 fL, Plt 245 k/μL",
      "2026/04/20: Na 139, K 4.1, Cl 102, BUN 14, Cr 0.9, eGFR 85",
      "2026/04/20: ALT 22, AST 24, T-bil 0.6, Alb 3.9",
      "2026/04/20: PT 11.2 s (INR 1.0), aPTT 30 s",
      "2026/04/20: CEA 5.8 ng/mL (↑), CA 19-9 18 U/mL",
      "2026/04/20: Glucose 118 mg/dL, HbA1c 6.8%",
    ],
  },

  // ---- Slide 5: Imaging (one object per study) ----
  imaging: [
    {
      date: "2026/04/12",
      modality: "CT abdomen/pelvis with IV contrast",
      findings: [
        "Circumferential wall thickening at distal sigmoid colon, ~4.2 cm in length",
        "Infiltration through muscularis propria into pericolic fat — consistent with T3",
        "No enlarged regional lymph node (all <8 mm in short axis)",
        "Liver: no focal lesion; no ascites",
        "No peritoneal carcinomatosis",
      ],
      impression:
        "Distal sigmoid colon malignancy, clinical T3N0M0; no distant metastasis on abdominal imaging.",
    },
    {
      date: "2026/04/15",
      modality: "CT chest without contrast",
      findings: [
        "No pulmonary nodule",
        "No mediastinal lymphadenopathy",
        "No pleural effusion",
      ],
      impression: "No evidence of thoracic metastasis.",
    },
  ],

  // ---- Slide 6: Pathology ----
  pathology: {
    date: "2026/04/08",
    specimen: "Colonoscopic biopsy × 4, distal sigmoid mass at 35 cm from anal verge",
    description:
      "Fragments of colonic mucosa showing glandular proliferation with cribriform architecture, loss of polarity, nuclear enlargement with prominent nucleoli, and desmoplastic stromal reaction. No definite lymphovascular invasion identified in the biopsy fragments.",
    diagnosis: "Moderately differentiated adenocarcinoma, sigmoid colon",
  },

  // ---- Slide 7: Tentative Diagnosis ----
  tentativeDx: {
    active: [
      "Distal sigmoid colon adenocarcinoma, cT3N0M0 (clinical stage IIA per AJCC 8th)",
    ],
    underlying: [
      "Hypertension",
      "Type 2 diabetes mellitus, well controlled",
      "Dyslipidemia",
    ],
  },

  // ---- Slide 8: Management ----
  management: {
    orders: [
      "2026/04/22 Elective low anterior resection (LAR) with primary anastomosis",
      "Pre-op bowel prep: polyethylene glycol (PEG) electrolyte solution 4 L PO the evening before",
      "Pre-op oral antibiotics: neomycin 1 g + metronidazole 500 mg PO × 3 doses",
      "IV antibiotic prophylaxis: cefmetazole 1 g IV 30 min before incision",
      "Aspirin held 7 days pre-op; restart POD 3 per surgical team",
      "VTE prophylaxis: enoxaparin 40 mg SC QD starting POD 1",
      "Glycemic control: sliding-scale insulin peri-op; resume metformin when eating resumes",
    ],
    goals: [
      "Achieve R0 resection of sigmoid mass",
      "Preserve continence via LAR (above peritoneal reflection)",
      "Complete pathologic staging → decide adjuvant therapy",
      "Early ambulation POD 1, resume PO POD 2-3 per ERAS protocol",
      "Follow-up plan: surveillance CEA + CT + colonoscopy per NCCN",
    ],
  },

  // ---- Slide 9: Discussion Questions ----
  discussionQuestions: [
    "如何判斷此例為 T3 vs T4？影像學上 muscularis propria 穿透的徵象有哪些？",
    "本例 CEA 5.8 輕微上升，術前是否需加做 PET-CT？證據為何？",
    "cT3N0 sigmoid cancer 術後是否建議 adjuvant chemotherapy？high-risk stage II 定義為何？",
    "若術後病理發現 MSI-H，後續 surveillance 與 genetic counseling 要如何調整？",
  ],
  includeDiscussion: true,

  // ---- Slide 10 (optional) — teaching case 可帶 academic-review 補充 ----
  extraSlide: {
    title: "Academic Review — cT3N0 colon cancer adjuvant therapy evidence",
    subtitle: "本次報告選的教學延伸",
    bullets: [
      "MOSAIC trial (2004): FOLFOX 優於 5-FU/LV 的 DFS 僅在 stage III，stage II 爭議",
      "IDEA collaboration (2018): 3 vs 6 months CAPOX for stage III，3 months 非劣效（低風險組）",
      "NCCN v3.2025 stage II high-risk 標準：T4、<12 LN harvested、LVI、PNI、obstruction、perforation、margin close",
      "MSI-H stage II：不建議 5-FU monotherapy（無 DFS benefit），考慮 observation 或 FOLFOX",
      "本例無 high-risk 特徵，傾向 observation + 密集 surveillance；等待最終病理 + MMR/MSI 再定案",
    ],
  },

  // ---- Clinical intake context ----
  clinicalContext: {
    specialty: "General Surgery / Colorectal",
    primaryIssue:
      "教學用 stage II colon cancer 決策案例，重點在影像 T stage 判讀 + adjuvant 決策",
    highlights: [
      "cT3 vs cT4 的影像辨識",
      "Stage II high-risk 定義",
      "MSI status 對 adjuvant 決策的影響",
    ],
    notes:
      "本 case 為虛構教學範例，非真實病人。報告對象為 attending + 同儕。",
    duration: "20",
    caseType: ["teaching", "academic-review"],
    audience: "attending",
  },

  // ---- Output ----
  outputPath: "example_case_discussion.pptx",
};

module.exports = CONTENT;

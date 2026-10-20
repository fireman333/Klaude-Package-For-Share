// ============================================================
// Example CVS profile — Mitral Valve Repair (degenerative MR)
// ============================================================
// Sister to example_case.js (9-slide default). Demonstrates
// the rotation profile system: rotationProfile: "cvs" pulls in
// imaging emphasis + 4 extra slides (Operative Procedure, 3
// intraop photo placeholders, Postoperative Course, Back to the
// Patient, Take-Home Summary).
//
// Run:
//   1. Copy this file to the same folder as scripts/generate_case_pptx.js
//      (or any folder, just adjust the require path below)
//   2. Open scripts/generate_case_pptx.js, replace the top-level CONTENT
//      block with the export from this file (or paste content inline)
//   3. NODE_PATH="$(npm root -g)" node generate_case_pptx.js
//
// Or one-shot:
//   cp <skill-dir>/scripts/generate_case_pptx.js /tmp/runner.js
//   # edit /tmp/runner.js's CONTENT to match below
//   NODE_PATH="$(npm root -g)" node /tmp/runner.js
//
// De-identified teaching case — all patient identifiers fabricated.
// ============================================================

const CONTENT = {
  theme: "grand_rounds_warm",

  // ---- Slide 1: Title ----
  age: 58,
  sex: "male",
  chiefComplaint: "Progressive exertional dyspnea for 6 months",
  reportDate: "2026/05/14",
  reporter: "（報告者姓名）",
  institution: "範例醫院 · 範例科別",

  // ---- Slide 2: Patient Profile ----
  chartNo: "[病歷號]",
  profile: {
    underlying: ["Hypertension (10 y, on amlodipine 5 mg QD)", "Hyperlipidemia"],
    tocc: "Office worker · no recent travel · no animal contact · no cluster",
    substance: "Social alcohol (1–2 beers / week) · denies smoking / betel nut",
    familyHx: "Father — CABG age 65 for triple-vessel CAD",
    medication: ["Amlodipine 5 mg PO QD", "Atorvastatin 20 mg PO QHS"],
  },

  // ---- Slide 3: Clinical Timeline ----
  timeline: [
    { date: "6 months ago", event: "Exertional dyspnea on climbing 2 flights of stairs (NYHA II)" },
    { date: "3 months ago", event: "Progressive — dyspnea on flat-ground walking (NYHA III)" },
    { date: "2026/04/12", event: "LMD echo → severe MR with P2 prolapse, LV dilation" },
    { date: "2026/04/20", event: "Outpatient cardiology consult at Example Hospital — TEE confirmed degenerative MR" },
    { date: "2026/05/05", event: "Admission for elective mitral valve repair" },
    { date: "2026/05/07", event: "OR: median sternotomy + on-pump mitral valve repair" },
    { date: "2026/05/14", event: "Discharge POD7 on ASA + warfarin (3 months)" },
  ],

  // ---- Slide 4: Admission Course ----
  admission: {
    symptoms: [
      "Exertional dyspnea NYHA III",
      "Orthopnea — sleeps with 2 pillows × 2 months",
      "Denied chest pain, syncope, palpitation, PND",
      "Denied lower extremity edema, weight gain",
    ],
    pe: [
      "Vitals: BP 132/78, HR 78 sinus, RR 16, SpO2 98% RA, T 36.5",
      "JVP 8 cm H2O · lungs clear bilaterally",
      "Cor: RRR, hyperdynamic apex, holosystolic murmur 3/6 at apex radiating to axilla",
      "Abdomen soft · no organomegaly · no lower limb edema",
    ],
    lab: [
      "2026/05/05 CBC: WBC 6.2 k/μL · Hb 13.8 g/dL · Plt 245 k/μL",
      "BUN 14 / Cr 0.9 · eGFR 92 · Na 140 · K 4.1",
      "BNP 285 pg/mL (↑) · troponin I < 0.01 (negative)",
      "PT 11.2s INR 1.0 · aPTT 28s · type & screen done",
    ],
  },

  // ---- Slide 5: Imaging ----
  imaging: [
    {
      date: "2026/04/20",
      modality: "Transthoracic echocardiogram (TTE)",
      findings: [
        "Severe mitral regurgitation with eccentric posteriorly-directed jet",
        "P2 prolapse with flail leaflet — suspected chordal rupture",
        "LV dilation: LVEDD 6.2 cm, LVEDV 168 mL · LVEF 62% (preserved)",
        "LA dilation: LA volume index 52 mL/m²",
        "RVSP 38 mmHg (mild pulmonary hypertension)",
      ],
      impression: "Severe degenerative MR with P2 prolapse, LV dilation, preserved LVEF — surgical candidate",
    },
    {
      date: "2026/04/22",
      modality: "Transesophageal echocardiogram (TEE)",
      findings: [
        "Confirmed P2 prolapse with ruptured chordae tendineae",
        "Coaptation gap 8 mm at A2-P2",
        "Posterior annulus dilated to 38 mm",
        "No leaflet calcification — favorable repair candidate (Carpentier IIIa)",
      ],
      impression: "Repairable degenerative MR — recommend mitral valve repair (not replacement)",
    },
    {
      date: "2026/04/28",
      modality: "Coronary angiography",
      findings: [
        "LM: no significant stenosis",
        "LAD: 30% stenosis at proximal segment (non-flow-limiting)",
        "LCX, RCA: no significant stenosis",
      ],
      impression: "Non-obstructive CAD — no concomitant CABG indicated",
    },
  ],

  examination: [
    {
      date: "2026/05/05",
      type: "12-lead EKG",
      findings: ["NSR rate 78 bpm", "Left atrial enlargement (P mitrale)", "No ischemic changes"],
      impression: "NSR with LAE",
    },
  ],

  // ---- Slide 6: Pathology ----
  pathology: {
    date: "2026/05/07",
    specimen: "Mitral valve P2 segment (triangular resection)",
    description: "Myxomatous degeneration with elongation and rupture of chordae tendineae. Fibroelastic deficiency.",
    diagnosis: "Degenerative mitral valve disease — Barlow-spectrum / fibroelastic deficiency",
  },

  // ---- Slide 7: Tentative Diagnosis ----
  tentativeDx: {
    active: [
      "Severe degenerative mitral regurgitation with P2 prolapse and chordal rupture",
      "Heart failure NYHA III (LV dilation, preserved LVEF)",
      "Mild pulmonary hypertension (RVSP 38)",
    ],
    underlying: ["Hypertension", "Hyperlipidemia"],
  },

  // ---- Slide 8: Management ----
  management: {
    orders: [
      "2026/05/07 OR: Median sternotomy + on-pump mitral valve repair",
      "Preop: Hold amlodipine morning of surgery · ASA hold ×5 days",
      "Postop ICU: invasive monitoring · IV milrinone PRN · target MAP > 65",
      "Anticoagulation: warfarin × 3 months (INR 2.0–3.0) then ASA lifelong",
      "Echo follow-up: TTE POD5, then 1 month, 3 months, annually",
    ],
    goals: [
      "Successful valve repair without conversion to replacement",
      "Extubation < 24 h, ICU stay < 48 h",
      "Discharge POD7 on optimized HF + AC regimen",
    ],
  },

  // ---- Slide 9: Discussion Questions ----
  discussionQuestions: [
    "When should we repair vs replace a degenerative mitral valve? What features predict durable repair?",
    "Is there a role for transcatheter edge-to-edge repair (e.g. MitraClip) in this patient, given his low surgical risk profile?",
    "Should asymptomatic severe MR with preserved LVEF undergo early surgery, per the latest ACC/AHA and ESC guidelines?",
  ],
  includeDiscussion: true,
  discussionTrail: [
    {
      question: "When should we repair vs replace a degenerative mitral valve?",
      synthesis: "Repair is preferred over replacement for degenerative MR when feasible — Class I recommendation (ACC/AHA 2020, ESC 2021). Predictors of durable repair: posterior leaflet prolapse (this patient), non-calcified leaflets, experienced surgeon (repair rate > 80%), no extensive annular calcification. Long-term survival and freedom from reoperation are superior with repair.",
      queries: [
        { source: "OE", query: "mitral valve repair vs replacement degenerative MR outcomes", verdict: "strongly supports repair when feasible" },
      ],
      citations: [
        "[1] Otto CM et al. 2020 ACC/AHA Guideline for the Management of Patients With Valvular Heart Disease. Circulation 2021;143:e72-e227",
        "[2] Suri RM et al. Survival advantage with mitral repair vs replacement. JTCVS 2016;152:1006",
      ],
    },
    {
      question: "Is there a role for transcatheter edge-to-edge repair (MitraClip) here?",
      synthesis: "TEER is Class IIa for primary MR ONLY when surgical risk is high (STS PROM > 8% or prohibitive). This patient is low surgical risk (no major comorbidity, preserved LVEF, age 58) — surgical repair is preferred. TEER outcomes for degenerative MR remain inferior to surgical repair in low-risk patients.",
      queries: [
        { source: "OE", query: "MitraClip TEER vs surgery primary degenerative MR low surgical risk", verdict: "surgery preferred when low-risk" },
      ],
      citations: [
        "[3] Feldman T et al. EVEREST II trial 5-year. JACC 2015;66:2844",
      ],
    },
    {
      question: "Should asymptomatic severe MR with preserved LVEF undergo early surgery?",
      synthesis: "Symptomatic patients (this patient — NYHA III) have a Class I indication for surgery. Even asymptomatic patients with severe primary MR + LV dilation (LVEDD ≥ 40 mm, LVESD ≥ 40 mm) OR atrial fibrillation OR pulmonary hypertension (RVSP > 50) qualify for Class IIa early surgical intervention to prevent irreversible LV remodeling.",
      queries: [
        { source: "OE", query: "early surgery asymptomatic severe mitral regurgitation watchful waiting", verdict: "early surgery favored with LV dilation" },
      ],
      citations: [
        "[4] Kang DH et al. Early surgery vs conservative management for asymptomatic severe MR. Circulation 2009;119:797",
      ],
    },
  ],

  // ---- Clinical Context (intake) ----
  clinicalContext: {
    specialty: "Cardiovascular surgery (CVS)",
    primaryIssue: "Severe degenerative MR with P2 prolapse — surgical repair vs replacement decision",
    highlights: ["Valve repair vs replacement", "Timing of surgery", "TEER alternative"],
    notes: "Educational example case for the CVS profile — emphasize echo → indication → surgical decision flow.",
    duration: "10",
    caseType: ["teaching", "academic-review"],
    audience: "attending",
  },

  // ============================================================
  // ---- Rotation profile fields (CVS) -------------------------
  // ============================================================
  rotationProfile: "cvs",

  imagingEmphasis: [
    "valve disease", "coronary lesion", "aortic size", "ascending aorta",
    "calcification", "regurgitation", "stenosis", "ejection fraction", "EF",
    "prolapse", "chordal rupture", "annulus",
  ],

  operativeProcedure: {
    title: "Operative Procedure",
    subtitle: "Approach · Key Steps · Reconstruction",
    indication: "Severe degenerative MR + LV dilation + NYHA III → Class I surgical indication",
    approach: "Median sternotomy · on-pump CPB · LA approach via Sondergaard's groove",
    keySteps: [
      "Left atriotomy → mitral valve exposure",
      "P2 prolapse with ruptured chordae confirmed",
      "Triangular resection of P2 (~1.5 cm)",
      "Neochord (Gore-Tex CV-5, ×2) + annuloplasty ring (Physio II, 34 mm)",
    ],
    reconstruction: "Saline test: trace central jet, A2-P2 coaptation 8 mm, no residual MR on TEE",
    intraopFindings: [
      "LV function preserved post-CPB",
      "Aortic valve competent · no peri-procedural arrhythmia",
      "CPB time 95 min · cross-clamp 72 min",
    ],
    photoSlots: 3,
  },

  postopCourse: {
    title: "Postoperative Course",
    subtitle: "ICU / Ward · Outcome vs Expected · Complications",
    icuDays: 2,
    outcome: [
      "Extubated POD0 evening (8 h post-op)",
      "Off vasopressor POD1 — hemodynamics stable",
      "Transferred to ward POD2",
      "Chest tube removed POD3 · ambulation started POD3",
      "Discharge POD7 on ASA + warfarin (target INR 2.0–3.0 × 3 months)",
    ],
    complications: [
      "Transient atrial fibrillation POD2 — converted with amiodarone IV, maintained NSR",
      "No major bleeding, infection, or stroke",
    ],
    outcomeVsExpected: "On expected trajectory — typical postop AF managed without sequelae. Discharge TTE: trivial central MR, normal LVEF 60%, LV dimensions improving.",
  },

  backToPatient: {
    title: "Back to the Patient",
    subtitle: "Alternative plans · Reflection · Lessons",
    alternatives: [
      "TEER (MitraClip) — Class IIa only for high surgical risk; excluded (low-risk patient)",
      "Mitral valve replacement — would require lifelong AC or limited bioprosthesis durability",
      "Watchful waiting — rejected; symptomatic + LV dilation = Class I surgical indication",
    ],
    reflection: [
      "Repair (not replace) supported by anatomy + durability data",
      "Preop TEE was decisive — TTE alone underestimated repair feasibility",
      "Heart team consensus confirmed surgical (not TEER) approach",
    ],
    lessons: [
      "Coaptation gap + leaflet anatomy on TEE predict repair success",
      "Anticipate postop AF (~30%) with amiodarone protocol",
      "Gore-Tex CV-5 neochord is current standard",
    ],
  },

  takeHomeSummary: {
    title: "Take-Home Summary",
    bullets: [
      "Severe degenerative MR with symptoms or LV dilation → Class I surgical indication",
      "Repair > replacement when anatomy is favorable (posterior prolapse, no calcification)",
      "TEER (MitraClip) reserved for high surgical risk; surgery is gold-standard for low-risk primary MR",
      "Postop AF is common (~30%) — anticipate with amiodarone protocol",
      "Echo (TTE + TEE) is the single most important preop study guiding repair feasibility",
    ],
  },

  outputPath: "case_discussion_cvs_mitral_repair_demo.pptx",
};

module.exports = CONTENT;

// ============================================================
// Case Discussion CONTENT Template
// ============================================================
// Copy this block into generate_case_pptx.js, replacing the CONTENT const.
// Leave fields as empty string / empty array / null if unavailable —
// the generator will render "N/A" instead of crashing.
// NEVER fabricate clinical data.
// ============================================================

const CONTENT = {
  // ---- Theme ----
  // "grand_rounds_warm" (default) | "journal_classic" | "clinical_modern"
  theme: "grand_rounds_warm",

  // ---- Slide 1: Title ----
  age: 0,                        // integer, e.g. 70
  sex: "male",                   // "male" | "female"
  chiefComplaint: "",            // one-sentence C.C., e.g. "Chest pain for 2 hours"
  reportDate: "YYYY/MM/DD",      // e.g. "2026/04/20"
  reporter: "（你的名字）",       // presenter name, e.g. "王小明"
  institution: "",               // optional: "<hospital> · <department>"; empty = hidden on title slide

  // ---- Slide 2: Patient Profile ----
  chartNo: "[病歷號]",             // can leave as placeholder; user types real value into slide later
  profile: {
    underlying: [],              // e.g. ["HTN", "DM", "dyslipidemia"]
    tocc: "",                    // occupation / travel / contact / cluster single-line
    substance: "",               // alcohol / betel nut / cigarette single-line
    familyHx: "",                // e.g. "no first-degree relative with CRC"
    medication: [],              // e.g. ["Metformin 500 mg BID", "Atorvastatin 20 mg QHS"]
  },

  // ---- Slide 3: Clinical Timeline (oldest → newest) ----
  timeline: [
    // { date: "2 years ago", event: "onset of easy fatigability" },
    // { date: "2026/03/03", event: "CT abdomen → distal sigmoid mass" },
  ],

  // ---- Slide 4: Admission Course ----
  admission: {
    symptoms: [],                // positive + denied at admission
    pe: [],                      // vitals + system findings
    lab: [],                     // formatted strings, e.g. "2026/04/07: WBC 7.84 k/μL, HB 13.7 g/dL"
  },

  // ---- Slide 5: Imaging (one object per study) ----
  imaging: [
    // {
    //   date: "2026/03/03",
    //   modality: "CT abdomen/pelvis with contrast",
    //   findings: ["finding 1", "finding 2"],
    //   impression: "impression line",
    // },
  ],

  // ---- Slide 5b: Examination Report (EKG / Echo / endoscopy / 肺功能 / NCV 等) ----
  // Mirrors imaging[] schema. Auto-feeds image-placeholder generation
  // (image-able types only — see IMAGE_MODALITY_REGEX in generate_case_pptx.js).
  examination: [
    // { date: "2026/04/05", type: "EKG", findings: ["sinus rhythm"], impression: "Normal." },
    // { date: "2026/04/08", type: "Pulmonary function test", findings: [...], impression: "..." },
  ],

  // ---- Image placeholder slides (CXR / CT / MRI / Echo / EKG / endoscopy 等) ----
  // Auto-derived from imaging[] + image-able examination[] entries when
  // unset. One blank slide per study for the presenter to paste a screenshot
  // from PACS / EMR before the talk.
  //   undefined / null  → auto-derive (default — recommended)
  //   false             → skip all image placeholders
  //   [{...}]           → explicit override; same shape as auto-derived slot
  imageSlots: undefined,
  // imageSlots: [
  //   { modality: "CXR", date: "2026/05/04", impression: "No acute process." },
  // ],

  // ---- Slide 6: Pathology ----
  pathology: {
    date: "",
    specimen: "",
    description: "",
    diagnosis: "",
  },

  // ---- Slide 7: Tentative Diagnosis ----
  tentativeDx: {
    active: [],                  // e.g. ["Distal sigmoid colon adenocarcinoma, cT3N0M0"]
    underlying: [],              // e.g. ["HTN", "Dyslipidemia"]
  },

  // ---- Slide 8: Management ----
  management: {
    orders: [],                  // e.g. ["04/22 OP: LAR", "Bowel prep: neomycin + metronidazole"]
    goals: [],                   // e.g. ["Complete LAR without major complications"]
  },

  // ---- Slide 9: Discussion Questions (template) ----
  discussionQuestions: [
    "[Discussion question 1]",
    "[Discussion question 2]",
    "[Discussion question 3]",
  ],
  includeDiscussion: true,       // set to false to skip slide 9

  // ---- Slide 9 speaker-note backing (Step 3.5 / Stage 3.5 trail) ----
  // Populated when the user opts in to OE / NotebookLM / PubMed query trail.
  // Each entry maps to the same-index discussionQuestions[] item.
  // Companion file <output>.discussion_trail.md is auto-written when non-empty.
  // Schema:
  //   { question: "...",
  //     synthesis: "1-3 sentence answer summary",
  //     queries:   [{ source: "OE"|"NotebookLM"|"PubMed", query: "...", verdict: "..." }],
  //     citations: ["[1] PMID 12345 — ...", "[2] DOI ..."],
  //     notes:     "optional caveats / contradictions" }
  discussionTrail: [],
  // discussionTrail: [
  //   {
  //     question: "How to differentiate T3 vs T4 colon cancer on CT?",
  //     synthesis: "T3 = invasion through muscularis propria into pericolic fat without serosal/peritoneal involvement; T4 implies serosal penetration or adjacent organ invasion.",
  //     queries: [
  //       { source: "OE", query: "CT staging T3 vs T4 colon cancer muscularis propria", verdict: "supports" },
  //     ],
  //     citations: ["[1] Beets-Tan RGH. Eur Radiol 2018"],
  //     notes: "MRI superior for rectal but limited utility in colon T-staging.",
  //   },
  // ],

  // ---- Slide 10 (optional — conditional on intake) ----
  // Populated by Stage 0.5/2.5 intake when caseType triggers extra discussion:
  //   mnm / academic-review / diagnostic-challenge / management-dilemma / teaching
  //   with ≥20 min OR >3 highlights OR multi-select caseType.
  extraSlide: null,
  // extraSlide: {
  //   title: "Complication Analysis",                 // pick per caseType
  //   subtitle: "M&M review",
  //   bullets: ["Root cause: ...", "Timeline: ...", "System factor: ...",
  //             "Preventability: ...", "Action items: ..."],
  // },

  // ---- Clinical intake context (Stage 0.5/2.5) ----
  // Drives Slide 9 question phrasing, bold keywords, timeline anchors.
  // Not itself rendered as a slide — metadata only.
  clinicalContext: null,
  // clinicalContext: {
  //   specialty: "",           // Q1 — free text
  //   primaryIssue: "",        // Q2 — free text
  //   highlights: [],          // Q3 — 1-3 themes to emphasize
  //   notes: "",               // Q4 — free text (optional)
  //   duration: "15",          // Q5 — "10" | "15" | "20" | "30"
  //   caseType: [],            // Q6 — multi-select:
  //                            //   "teaching" | "diagnostic-challenge" |
  //                            //   "mnm" | "academic-review" | "management-dilemma"
  //   audience: "attending",   // fixed — affects term-expansion depth
  // },

  // ============================================================
  // ---- Rotation profile fields (optional) --------------------
  // ============================================================
  // Lets the skill mirror rotation-specific case discussion specs
  // (e.g. CVS / Neurosurgery / GI). See profiles/_profile_template.md
  // for how to author a new profile, and profiles/_index.json for
  // built-in profiles.

  // Profile spec — built-in key OR absolute path to a custom profile .md.
  // SKILL.md Step 2.4 reads this, parses YAML frontmatter, and populates
  // the resolved flags below.
  //   "cvs"                        → loads profiles/cvs.md
  //   "/abs/path/to/my_profile.md" → loads that file as a one-off profile
  //   undefined                    → no profile (9-slide default)
  rotationProfile: undefined,

  // === Resolved profile flags (populated by Step 2.4) ===
  // Generator consumes these directly; you typically do NOT set them by
  // hand unless you want to bypass profile resolution.

  // Boolean — insert 3 full-bleed section dividers (Patient Data /
  // Case Discussion / Back to the Patient). Defaults off; CVS profile
  // also defaults off (10-min talk is tight on slides).
  sectionDividers: undefined,

  // string[] — phrases to bold in Slide 5 imaging cards. CVS profile
  // sets this to valve / coronary / aortic / EF / etc. Case-insensitive
  // substring match; matched runs become bold+darker colored.
  imagingEmphasis: undefined,
  // imagingEmphasis: ["valve disease", "coronary lesion", "aortic size"],

  // Operative Procedure slide (inserted after Pathology).
  // Required: title + (approach OR keySteps).
  operativeProcedure: undefined,
  // operativeProcedure: {
  //   title: "Operative Procedure",
  //   subtitle: "Approach · Key Steps · Reconstruction",
  //   indication: "Severe MR with LV dilation, sx HF NYHA III",
  //   approach: "Median sternotomy, on-pump CPB, antegrade cold blood cardioplegia",
  //   keySteps: [
  //     "Left atriotomy via Sondergaard's groove",
  //     "P2 prolapse with chordal rupture identified",
  //     "Triangular resection of P2 + neochord (Gore-Tex CV-5) to PM",
  //     "True-sized annuloplasty ring (Carpentier-Edwards Physio II, 34 mm)",
  //   ],
  //   reconstruction: "Saline test: trace central jet, A2-P2 coaptation 8 mm",
  //   intraopFindings: ["LV preserved", "AV competent", "no peri-procedural events"],
  //   photoSlots: 3,                  // 0-4 dashed photo placeholders
  // },

  // Postoperative Course slide (inserted after Management).
  postopCourse: undefined,
  // postopCourse: {
  //   title: "Postoperative Course",
  //   subtitle: "ICU / Ward · Outcome vs Expected · Complications",
  //   icuDays: 2,
  //   outcome: [
  //     "Extubated POD0 evening",
  //     "Off inotropes POD1, transferred to ward POD2",
  //     "Discharge POD7 on ASA + warfarin (3 months)",
  //   ],
  //   complications: ["Transient AF POD2, converted with amiodarone"],
  //   outcomeVsExpected: "On expected trajectory — no major complications",
  // },

  // Back to the Patient slide (inserted after Discussion / extraSlide).
  backToPatient: undefined,
  // backToPatient: {
  //   title: "Back to the Patient",
  //   subtitle: "Alternative plans · Reflection · Lessons",
  //   alternatives: [
  //     "Transcatheter edge-to-edge repair (MitraClip) — guideline class IIa for high surgical risk; this patient was low risk so surgery preferred",
  //   ],
  //   reflection: [
  //     "Decision to repair (not replace) supported by valve anatomy + low op risk",
  //   ],
  //   lessons: [
  //     "Echo's regurgitant jet eccentricity predicted P2 prolapse — confirmed intraop",
  //   ],
  // },

  // Take-Home Summary slide (always the very last slide).
  takeHomeSummary: undefined,
  // takeHomeSummary: {
  //   title: "Take-Home Summary",
  //   bullets: [
  //     "Severe degenerative MR → repair > replace when feasible",
  //     "P2 prolapse + chordal rupture is the prototypical repairable lesion",
  //     "Annuloplasty ring required to durability",
  //     "Postop AF is common (~30%) — anticipate with amiodarone protocol",
  //   ],
  // },

  // ---- Output ----
  outputPath: "case_discussion.pptx",
};

module.exports = CONTENT;

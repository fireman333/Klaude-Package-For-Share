"""
Example DATA module for the paper / journal-club route.

Content is a MOCK based on the published DAPA-HF trial (McMurray et al., NEJM
2019) — used here purely as a smoke-test fixture to exercise every slide type
introduced by this skill. Numbers and citations are simplified / paraphrased and
NOT suitable for actual teaching use without re-extraction from source.

Render:
    cd <this skill's folder>
    python3 render.py templates/example_paper_data.py example_jc.pptx
"""

DATA = {
    "meta": {
        "topic_title": "Journal Club — Dapagliflozin in HFrEF",
        "theme": "journal_classic",
        "input_type": "paper",
        "citation_style": "vancouver",
    },

    "cover": {
        "label": "Journal Club",
        "title": "Dapagliflozin in\nHeart Failure with\nReduced EF",
        "subtitle": "DAPA-HF trial — design, results, translation",
        "big_word_primary": "DAPA",
        "big_word_accent": "-HF",
        "caption_en": "SGLT2 inhibition beyond glycemic control",
        "caption_sub": "A landmark RCT in HFrEF",
        "presenter": "__________",
        "date": "2026-04-23",
        "course_tag": "Cardiology RA — Journal Club",
    },

    "outline_items": [
        ("01", "Background & Clinical Question", "5 min",
         "HFrEF burden, SGLT2i mechanism, knowledge gap before DAPA-HF."),
        ("02", "Paper at a Glance & PICO", "5 min",
         "Design, population, intervention, comparator, primary outcome."),
        ("03", "Methods & Results", "15 min",
         "Inclusion / exclusion, statistical plan, key numbers."),
        ("04", "Discussion Questions", "20 min",
         "External validity, mechanism, next-step studies — Q1–Q3."),
        ("05", "Takeaways & Q&A", "5 min",
         "Three clinical lessons and floor discussion."),
    ],

    "slides": [
        # 1
        {"type": "cover"},

        # 2
        {"type": "outline",
         "notes":
            "=== Abbreviations ===\n"
            "HFrEF | heart failure with reduced ejection fraction | 射出分率降低之心衰竭\n"
            "SGLT2i | sodium–glucose cotransporter 2 inhibitor | 鈉葡萄糖共同轉運蛋白 2 抑制劑\n"
            "RCT | randomized controlled trial | 隨機對照試驗\n\n"
            "=== 核心論點 ===\n"
            "介紹今日 journal club 的節奏：五段式，約 50 分鐘。先花 5 分鐘鋪 HFrEF 的\n"
            "臨床背景與 pre-DAPA-HF 的 guideline gap，再進入文章本體。\n\n"
            "=== 可預期提問 ===\n"
            "主治可能問：為什麼先挑這一篇而不是 EMPEROR-Reduced？\n"
            "→ 回答：DAPA-HF 是首篇跨糖尿病狀態的 HFrEF 大型 SGLT2i RCT，做為 SGLT2i 類\n"
            "的 turning-point paper，適合作為 journal club 入門。\n\n"
            "=== 補充數據 ===\n"
            "DAPA-HF primary reference: McMurray JJV et al. NEJM 2019; 381:1995-2008.\n"
            "(RCT, multinational, n=4744)"
         },

        # 3 background
        {"type": "background",
         "title": "Clinical Context — HFrEF before 2019",
         "subtitle": "Why another HFrEF trial?",
         "bullets": [
            "HFrEF mortality remains ~20% at 1 year despite optimal GDMT.",
            "Prior SGLT2i trials (EMPA-REG, CANVAS, DECLARE) enrolled T2DM populations.",
            "Signal of HF hospitalization reduction opened a cardiology hypothesis.",
            "Question: does dapagliflozin benefit HFrEF irrespective of diabetes status?",
         ],
         "notes":
            "=== Abbreviations ===\n"
            "GDMT | guideline-directed medical therapy | 指引建議的藥物治療\n"
            "T2DM | type 2 diabetes mellitus | 第二型糖尿病\n"
            "HF | heart failure | 心衰竭\n\n"
            "=== 核心論點 ===\n"
            "帶聽眾建立 pre-DAPA-HF 的 knowledge state：GDMT 四大類（ACEi/ARB/ARNI、\n"
            "β-blocker、MRA、loop diuretic）下 1-year mortality 仍在 15–20%；SGLT2i 的\n"
            "cardio-signal 最早是 EMPA-REG 的 secondary outcome。\n\n"
            "=== 可預期提問 ===\n"
            "為什麼不是做 HFpEF？→ DAPA-HF 選 HFrEF 是 power consideration — HFrEF 有\n"
            "明確 endpoint definition，招募相對容易；HFpEF 後來才由 DELIVER 補足。\n\n"
            "=== 補充數據 ===\n"
            "Zinman 2015 (EMPA-REG OUTCOME) — RCT, global, n=7020; empagliflozin cut\n"
            "CV mortality 38% in T2DM with established CVD. PMID: 26378978."
         },

        # 4 paper_meta
        {"type": "paper_meta",
         "title": "Dapagliflozin in Patients with Heart Failure and Reduced Ejection Fraction",
         "journal": "N Engl J Med",
         "year": 2019,
         "authors_short": "McMurray JJV, Solomon SD, Inzucchi SE, et al. (DAPA-HF Committee)",
         "doi": "10.1056/NEJMoa1911303",
         "pmid": "31535829",
         "design": "Multinational, double-blind, placebo-controlled RCT",
         "funding": "AstraZeneca",
         "main_finding":
            "Dapagliflozin 10 mg daily reduced the composite of worsening HF or "
            "CV death vs placebo (HR 0.74; 95% CI 0.65–0.85; p<0.001), with benefit "
            "independent of diabetes status.",
         "notes":
            "=== Abbreviations ===\n"
            "HR | hazard ratio | 風險比\n"
            "CI | confidence interval | 信賴區間\n"
            "CV | cardiovascular | 心血管\n\n"
            "=== 核心論點 ===\n"
            "NEJM 2019 — 當年 late-breaking trial at ESC 2019 首發。AstraZeneca 贊助，\n"
            "但 steering committee 為 academic-led。重點是 primary composite 的\n"
            "HR 0.74 (0.65–0.85)，全因死亡 HR 0.83 (0.71–0.97) 也達顯著。\n\n"
            "=== 可預期提問 ===\n"
            "Funding 是 AstraZeneca 會不會有 bias？→ 說明 adjudication committee 是\n"
            "blinded academic committee，且 data lock 獨立統計中心執行。\n\n"
            "=== 補充數據 ===\n"
            "McMurray 2019 — RCT multinational, n=4744; primary HR 0.74 (0.65–0.85),\n"
            "p<0.001. PMID: 31535829."
         },

        # 5 pico
        {"type": "pico",
         "population": "Adults with HFrEF (LVEF ≤40%), NYHA II–IV, NT-proBNP ≥ 600 pg/mL.",
         "intervention": "Dapagliflozin 10 mg PO daily, on top of standard HF therapy.",
         "comparator": "Matching placebo, on top of standard HF therapy.",
         "outcome":
            "Composite of worsening HF (hospitalization or urgent visit with IV therapy) "
            "or cardiovascular death.",
         "secondary_outcomes": [
            "All-cause mortality",
            "KCCQ total symptom score change at 8 months",
            "First worsening HF event (hospitalization or urgent visit)",
         ],
         "notes":
            "=== Abbreviations ===\n"
            "LVEF | left ventricular ejection fraction | 左心室射出分率\n"
            "NYHA | New York Heart Association functional class | 紐約心臟學會功能分級\n"
            "NT-proBNP | N-terminal pro-B-type natriuretic peptide | N 端前體腦鈉肽\n"
            "KCCQ | Kansas City Cardiomyopathy Questionnaire | 堪薩斯心衰問卷\n\n"
            "=== 核心論點 ===\n"
            "PICO 是 journal club 的硬骨頭 — 務必要讓聽眾記得 DAPA-HF 的 P 不是只有\n"
            "糖友，是 HFrEF + NYHA II–IV + NT-proBNP ≥600。這個 NT-proBNP 門檻決定了\n"
            "外推性。\n\n"
            "=== 可預期提問 ===\n"
            "NYHA IV 比例多少？→ 很少（<1%），絕大多數是 NYHA II–III，外推到 advanced\n"
            "HF 要小心。\n\n"
            "=== 補充數據 ===\n"
            "McMurray 2019 Methods — LVEF eligibility ≤40%, AF 允許時 NT-proBNP 門檻\n"
            "提高到 ≥900 pg/mL。"
         },

        # 6 methods
        {"type": "methods",
         "design": "1:1 randomization, double-blind, placebo-controlled, event-driven RCT",
         "n_total": 4744,
         "key_inclusion": [
            "Age ≥ 18, NYHA II–IV, LVEF ≤ 40%",
            "NT-proBNP ≥ 600 pg/mL (≥ 900 if AF / atrial flutter)",
            "On stable HF therapy ≥ 4 weeks",
         ],
         "key_exclusion": [
            "Symptomatic hypotension or SBP < 95 mmHg",
            "eGFR < 30 mL/min/1.73 m2",
            "Type 1 diabetes mellitus",
         ],
         "primary_endpoint": "Composite of worsening HF or CV death (time to first event)",
         "stats_method":
            "Cox proportional-hazards, stratified by DM status and NT-proBNP; ITT.",
         "follow_up": "Median 18.2 months",
         "notes":
            "=== Abbreviations ===\n"
            "AF | atrial fibrillation | 心房顫動\n"
            "SBP | systolic blood pressure | 收縮壓\n"
            "eGFR | estimated glomerular filtration rate | 估計腎絲球過濾率\n"
            "ITT | intention-to-treat | 意向性分析\n"
            "Cox PH | Cox proportional hazards regression | Cox 比例風險迴歸\n\n"
            "=== 核心論點 ===\n"
            "Event-driven design — 本來預計 844 events，實際 684 events 時達預設邊界\n"
            "提前揭盲。stratification 是 DM status 與 NT-proBNP 分位。\n\n"
            "=== 可預期提問 ===\n"
            "為什麼 eGFR < 30 排除？→ dapagliflozin 當時在 eGFR <30 的 efficacy data 不足\n"
            "（後續 DAPA-CKD 才擴大到 eGFR ≥ 25）。\n\n"
            "=== 補充數據 ===\n"
            "Sample size justification targets 80% power for HR 0.80 at α=0.05,\n"
            "assuming 16% annual event rate in placebo arm."
         },

        # 7 results
        {"type": "results",
         "title": "Primary and Key Secondary Results",
         "key_numbers": [
            {"metric": "Primary composite (worsening HF or CV death)",
             "value": "HR 0.74", "ci": "0.65–0.85", "p": "< 0.001"},
            {"metric": "Worsening HF event",
             "value": "HR 0.70", "ci": "0.59–0.83", "p": "< 0.001"},
            {"metric": "CV death",
             "value": "HR 0.82", "ci": "0.69–0.98", "p": "0.029"},
            {"metric": "All-cause mortality",
             "value": "HR 0.83", "ci": "0.71–0.97", "p": "0.022"},
            {"metric": "Mean KCCQ-TSS change at 8 mo",
             "value": "+2.8 pts", "ci": "+1.6 to +4.0", "p": "< 0.001"},
         ],
         "figure_caption":
            "Kaplan–Meier curves separated within 4 weeks and remained divergent "
            "through 18-month follow-up; heterogeneity of treatment effect by DM "
            "status p = 0.80 (no interaction).",
         "notes":
            "=== Abbreviations ===\n"
            "KCCQ-TSS | Kansas City Cardiomyopathy Questionnaire total symptom score | 堪薩斯心衰問卷總症狀分數\n\n"
            "=== 核心論點 ===\n"
            "核心觀察：(1) HR 0.74 consistent across DM subgroups；(2) early separation\n"
            "於 4 週內，示意 mechanism 可能非糖代謝；(3) NNT ≈ 21 for primary composite\n"
            "在 18 個月內。\n\n"
            "=== 可預期提問 ===\n"
            "為什麼 KCCQ 只差 2.8 分？→ 2.8 pts 是 clinically meaningful 的臨界；KCCQ\n"
            "MCID 一般視為 5 分，但 meta 分析顯示 ≥3 分有生存關聯。\n\n"
            "=== 補充數據 ===\n"
            "NNT calculation: 26.5% placebo event rate vs 21.6% dapagliflozin over\n"
            "median 18.2 months → ARR 4.9%, NNT ≈ 21."
         },

        # 8 discussion_question Q1
        {"type": "discussion_question",
         "q_num": 1,
         "q_text_en":
            "Does the benefit of dapagliflozin generalize to our Taiwanese HFrEF "
            "population, given enrollment biases and BMI / body-size differences?",
         "suggested_minutes": 7,
         "prompts_for_audience": [
            "What proportion of DAPA-HF came from East Asia?",
            "Are there dose or pharmacokinetic concerns specific to lower BMI?",
            "Any Taiwan-specific RCT or registry data (TSOC HF registry)?",
         ],
         "notes":
            "=== Abbreviations ===\n"
            "TSOC | Taiwan Society of Cardiology | 台灣心臟學會\n"
            "BMI | body mass index | 身體質量指數\n\n"
            "=== 核心論點 ===\n"
            "External validity 是 journal club 常見第一題。DAPA-HF 亞裔比例約 24%，\n"
            "屬同類 trial 中偏高。但 Taiwanese 特定 subgroup 未做 pre-specified analysis。\n\n"
            "=== 可預期提問 ===\n"
            "有沒有 Taiwanese post-hoc analysis？→ 目前未見 formal pub，但 TSOC-HF\n"
            "registry 有觀察性 real-world 資料可對照。\n\n"
            "=== 補充數據 ===\n"
            "DAPA-HF subgroup East Asia: RCT, multinational subset, n≈1145; HR 0.73\n"
            "(0.54–0.99)."
         },

        # 9 literature_evidence Q1
        {"type": "literature_evidence",
         "q_num": 1,
         "evidence_summary_en":
            "East-Asian subgroup analyses of DAPA-HF and EMPEROR-Reduced "
            "consistently show point estimates similar to the overall population, "
            "though CIs widen. Taiwan-specific observational data from TSOC-HF "
            "suggest comparable relative risk reduction in real-world use.",
         "citations": [
            {"author_year": "Docherty 2020",
             "study_type": "RCT subgroup", "country": "Multinational", "n": 1145,
             "take_home": "East Asian subset mirrored main result (HR 0.73)."},
            {"author_year": "Hsieh 2022",
             "study_type": "Prospective registry", "country": "Taiwan", "n": 1578,
             "take_home": "Real-world SGLT2i use associated with 29% lower HF hosp."},
            {"author_year": "Packer 2020",
             "study_type": "RCT (EMPEROR-Reduced)", "country": "Multinational", "n": 3730,
             "take_home": "Empagliflozin cut primary composite by 25%, consistent."},
         ],
         "notes":
            "=== Abbreviations ===\n"
            "HR | hazard ratio | 風險比\n\n"
            "=== 核心論點 ===\n"
            "三筆文獻佐證 external validity：DAPA-HF East Asian subgroup (point estimate\n"
            "一致) + TSOC real-world (29% HF hosp 降低) + EMPEROR-Reduced 平行驗證。\n\n"
            "=== 可預期提問 ===\n"
            "為什麼不放 EMPA-REG？→ EMPA-REG 是 T2DM + CVD，人群不同，外推性反而弱。\n\n"
            "=== Audit ===\n"
            "OE citations verified (mock): 3/3 pass; no contradicted claims."
         },

        # 10 discussion_question Q2
        {"type": "discussion_question",
         "q_num": 2,
         "q_text_en":
            "What is the best current mechanistic explanation for early (< 4 week) "
            "separation of event curves — is it natriuresis, cardiac energetics, or "
            "something else?",
         "suggested_minutes": 7,
         "prompts_for_audience": [
            "Which biomarker changes track the earliest benefit?",
            "How do ketone body and hematocrit shifts fit in?",
            "Implications for patients already on loop diuretics?",
         ],
         "notes":
            "=== Abbreviations ===\n"
            "NT-proBNP | N-terminal pro-B-type natriuretic peptide | 同上\n\n"
            "=== 核心論點 ===\n"
            "Mechanism question — 目前主流三說：(1) natriuresis / plasma volume 減少；\n"
            "(2) ketone body 作為 alternative cardiac fuel；(3) direct cardiac reverse\n"
            "remodeling。多數現行證據傾向前兩者為 early effect 的主體。\n\n"
            "=== 可預期提問 ===\n"
            "有沒有直接 CMR 影像？→ SUGAR-DM, EMPA-TROPISM 顯示 LV mass 減少但要 6+ 月。\n\n"
            "=== 補充數據 ===\n"
            "Lopaschuk 2020 mechanism review — narrative review, global; proposes\n"
            "metabolic shift + natriuresis combined model."
         },

        # 11 literature_evidence Q2
        {"type": "literature_evidence",
         "q_num": 2,
         "evidence_summary_en":
            "Multiple mechanistic studies converge on a combined natriuretic + "
            "metabolic-substrate shift model. Early-event-curve separation most "
            "closely tracks plasma volume and hematocrit changes, while later "
            "benefit correlates with cardiac reverse remodeling on CMR.",
         "citations": [
            {"author_year": "Lopaschuk 2020",
             "study_type": "Mechanism review", "country": "Global", "n": "N/A",
             "take_home": "Ketone-body oxidation + natriuresis combined model."},
            {"author_year": "Santos-Gallego 2021",
             "study_type": "RCT (EMPA-TROPISM)", "country": "Spain", "n": 84,
             "take_home": "LV mass reduced significantly at 6 months on CMR."},
            {"author_year": "Lee 2020",
             "study_type": "RCT (SUGAR-DM)", "country": "UK", "n": 105,
             "take_home": "Empagliflozin lowered LVEDV / LVESV vs placebo."},
         ],
         "notes":
            "=== Abbreviations ===\n"
            "CMR | cardiac magnetic resonance | 心臟磁振造影\n"
            "LVEDV | left ventricular end-diastolic volume | 左心室舒張末期容積\n"
            "LVESV | left ventricular end-systolic volume | 左心室收縮末期容積\n\n"
            "=== 核心論點 ===\n"
            "EMPA-TROPISM / SUGAR-DM 用 CMR 驗證 reverse remodeling，Lopaschuk review 提供\n"
            "metabolic 機轉敘事。\n\n"
            "=== 可預期提問 ===\n"
            "為什麼早期 curve separation 發生在 4 週？→ plasma volume 降低在 2-4 週\n"
            "已經穩定，KCCQ 分數也在 4 週內有小改善。\n\n"
            "=== Audit ===\n"
            "OE citations verified (mock): 3/3 pass."
         },

        # 12 discussion_question Q3
        {"type": "discussion_question",
         "q_num": 3,
         "q_text_en":
            "Beyond DAPA-HF, what has changed in SGLT2i use for HF post-2019 — "
            "should we be using them across the LVEF spectrum, including HFpEF?",
         "suggested_minutes": 6,
         "prompts_for_audience": [
            "What did EMPEROR-Preserved and DELIVER add?",
            "Any updated 2023 ESC / 2022 AHA guideline statements?",
            "Cost-effectiveness in Taiwan NHI context?",
         ],
         "notes":
            "=== Abbreviations ===\n"
            "HFpEF | heart failure with preserved ejection fraction | 射出分率保留之心衰竭\n"
            "NHI | National Health Insurance | 全民健保\n"
            "ESC | European Society of Cardiology | 歐洲心臟學會\n"
            "AHA | American Heart Association | 美國心臟學會\n\n"
            "=== 核心論點 ===\n"
            "2021 EMPEROR-Preserved 和 2022 DELIVER 將 SGLT2i 的適應症擴展到 HFpEF。\n"
            "2022 AHA / 2023 ESC 指引已將 SGLT2i 列為 Class I 建議，適用於整個 LVEF\n"
            "spectrum。\n\n"
            "=== 可預期提問 ===\n"
            "Taiwan NHI 覆蓋多少？→ 目前 HFrEF 已給付，HFpEF 尚未（2025 年資料）。\n\n"
            "=== 補充數據 ===\n"
            "Solomon 2022 (DELIVER) — RCT multinational, n=6263; HR 0.82 (0.73–0.92)\n"
            "primary composite in HFpEF. PMID: 36027570."
         },

        # 13 literature_evidence Q3
        {"type": "literature_evidence",
         "q_num": 3,
         "evidence_summary_en":
            "Post-2019 evidence extends SGLT2i benefit across the entire LVEF "
            "spectrum. EMPEROR-Preserved (2021) and DELIVER (2022) showed "
            "consistent reduction in the primary composite in HFpEF. Current "
            "ESC 2023 and AHA 2022 guidelines recommend SGLT2i as Class I in HF "
            "regardless of LVEF.",
         "citations": [
            {"author_year": "Anker 2021",
             "study_type": "RCT (EMPEROR-Preserved)", "country": "Multinational", "n": 5988,
             "take_home": "Empagliflozin cut composite by 21% in HFpEF."},
            {"author_year": "Solomon 2022",
             "study_type": "RCT (DELIVER)", "country": "Multinational", "n": 6263,
             "take_home": "Dapagliflozin cut composite 18% across LVEF."},
            {"author_year": "McDonagh 2023",
             "study_type": "Guideline", "country": "Europe (ESC)", "n": "N/A",
             "take_home": "SGLT2i Class I recommendation across full LVEF spectrum."},
         ],
         "notes":
            "=== Abbreviations ===\n"
            "LVEF | left ventricular ejection fraction | 左心室射出分率\n\n"
            "=== 核心論點 ===\n"
            "三筆代表性文獻 — 兩個大 RCT + 最新 guideline。連同 DAPA-HF 四個 trial 合\n"
            "起來，完整覆蓋 LVEF 全光譜的證據。\n\n"
            "=== 可預期提問 ===\n"
            "HFpEF 數據是否 as strong as HFrEF？→ CI 更寬，point estimate 相近但 absolute\n"
            "risk reduction 較小。\n\n"
            "=== Audit ===\n"
            "OE citations verified (mock): 3/3 pass."
         },

        # 14 takeaway
        {"type": "takeaway",
         "title": "Clinical Takeaways",
         "points": [
            ("Add SGLT2i early",
             "For any HFrEF patient with LVEF ≤ 40% and no contraindication, "
             "consider adding dapagliflozin or empagliflozin early on top of "
             "GDMT — do not wait for titration completion."),
            ("Benefit is independent of diabetes",
             "DAPA-HF proved the cardio-effect is not glucose-lowering-driven; "
             "skip the old habit of restricting SGLT2i to T2DM patients."),
            ("Check eGFR and volume status",
             "Exclude eGFR < 25 mL/min/1.73m2 and symptomatic hypotension. "
             "Counsel euvolemic initiation; reduce loop diuretic if needed."),
         ],
         "notes":
            "=== Abbreviations ===\n"
            "GDMT | guideline-directed medical therapy | 指引建議的藥物治療\n"
            "eGFR | estimated glomerular filtration rate | 估計腎絲球過濾率\n\n"
            "=== 核心論點 ===\n"
            "三句話收尾：早加、不用選糖友、注意 eGFR 與容積。這三點是主治最希望學生\n"
            "記得的臨床轉譯。\n\n"
            "=== 可預期提問 ===\n"
            "SGLT2i 與 ACEi/ARNI 排序？→ 並列 Class I，通常先 ARNI 或 SGLT2i 擇一起手，\n"
            "另一個在 2–4 週後加上。\n\n"
            "=== 補充數據 ===\n"
            "McDonagh 2023 ESC HF Guidelines — 已採 four-pillar 同步起手概念，\n"
            "一週內同時導入 4 類藥物 (ARNI / BB / MRA / SGLT2i)。"
         },

        # 15 references
        {"type": "references",
         "title": "References",
         "style": "vancouver",
         "citations": [
            {"full_author_list": "McMurray JJV, Solomon SD, Inzucchi SE, et al.",
             "title":
                "Dapagliflozin in patients with heart failure and reduced ejection fraction",
             "journal": "N Engl J Med", "year": 2019, "volume": "381", "issue": "21",
             "pages": "1995-2008", "pmid": "31535829",
             "doi": "10.1056/NEJMoa1911303"},
            {"full_author_list": "Zinman B, Wanner C, Lachin JM, et al.",
             "title":
                "Empagliflozin, cardiovascular outcomes, and mortality in type 2 diabetes",
             "journal": "N Engl J Med", "year": 2015, "volume": "373", "issue": "22",
             "pages": "2117-2128", "pmid": "26378978",
             "doi": "10.1056/NEJMoa1504720"},
            {"full_author_list": "Packer M, Anker SD, Butler J, et al.",
             "title": "Cardiovascular and renal outcomes with empagliflozin in heart failure",
             "journal": "N Engl J Med", "year": 2020, "volume": "383", "issue": "15",
             "pages": "1413-1424", "pmid": "32865377",
             "doi": "10.1056/NEJMoa2022190"},
            {"full_author_list": "Anker SD, Butler J, Filippatos G, et al.",
             "title":
                "Empagliflozin in heart failure with a preserved ejection fraction",
             "journal": "N Engl J Med", "year": 2021, "volume": "385", "issue": "16",
             "pages": "1451-1461", "pmid": "34449189",
             "doi": "10.1056/NEJMoa2107038"},
            {"full_author_list": "Solomon SD, McMurray JJV, Claggett B, et al.",
             "title": "Dapagliflozin in heart failure with mildly reduced or preserved ejection fraction",
             "journal": "N Engl J Med", "year": 2022, "volume": "387", "issue": "12",
             "pages": "1089-1098", "pmid": "36027570",
             "doi": "10.1056/NEJMoa2206286"},
            {"full_author_list": "McDonagh TA, Metra M, Adamo M, et al.",
             "title":
                "2023 focused update of the 2021 ESC guidelines for the diagnosis and treatment of acute and chronic heart failure",
             "journal": "Eur Heart J", "year": 2023, "volume": "44", "issue": "37",
             "pages": "3627-3639", "pmid": "37622666",
             "doi": "10.1093/eurheartj/ehad195"},
         ],
         "notes":
            "=== 核心論點 ===\n"
            "6 篇 key references — 主文獻 DAPA-HF (NEJM 2019) + 佐證 trial × 3 + guideline\n"
            "× 1 + mechanism precursor EMPA-REG × 1。\n\n"
            "=== 補充數據 ===\n"
            "Full reference list managed in research_findings.json by research_synth.py;\n"
            "slide here is a curated top-6."
         },

        # 16 blank_teacher
        {"type": "blank_teacher",
         "closing_main": "Floor is open — your critique welcome",
         "closing_sub": "— Thank you —",
         "notes":
            "=== 核心論點 ===\n"
            "最後一張留給主治 / fellow 講評。不要預設 3 分鐘內會結束，結束前記得回收\n"
            "三個 takeaway 給大家複誦。\n"
         },
    ],
}

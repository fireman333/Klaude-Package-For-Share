---
pack: academic-medical
triggers: [journal club, JC, 書報討論, 期刊報告, paper 報告, 報這篇, EBM, evidence-based, 實證醫學, 文獻評讀, critical appraisal, case discussion, case 討論, 案例討論, 病例討論, case 簡報, case presentation, M&M, mortality and morbidity, morbidity conference, /journal-club-discussion-pptx, /journal-club-pptx, /case-discussion-pptx, /case-discussion-pptx, morning report, grand rounds, tumor board, CPC, clinicopathological conference, 晨會, 跨科討論]
applicable_modes: [quick, deep]
default_callers: [使用者直接呼叫，pre-write 階段 for /journal-club-discussion-pptx / /case-discussion-pptx]
---

# Academic Medical Presentation Facet Pack

對學術醫學簡報的「動筆前」階段。場景：
- **Journal Club / 期刊評讀**（JC）：報一篇 paper 給同 / 跨領域聽
- **Clinical case discussion**：報一個 case 給 attending + residents 討論
- **M&M / morbidity-mortality**：複盤 adverse outcome
- **Grand rounds / tumor board / CPC**：跨科討論複雜決策

重點：在開 `/journal-club-discussion-pptx` / `/case-discussion-pptx` 之前先把 **聽眾 / 最強 claim / 證據強度 / devil's advocate / 想引發的辯論** 釘下來。沒釘好就動手 = 投影片寫完才發現「方向不對 / 沒 take-home / attending 一問就垮」。

---

## Step 0: Subtype 分流（Quick + Deep 都跑）

先確認 subtype，facet 抽法不同：

| Subtype | 觸發詞 | Facet |
|---|---|---|
| **JC** | journal club, 書報討論, 評讀, paper 報告 | F1-F5 + F6-F10_JC |
| **Case** | case discussion, 案例討論, 病例討論, M&M | F1-F5 + F6-F10_Case |
| **Mixed** | grand rounds, tumor board, CPC, 跨科討論 | F1-F5 + 從 JC + Case 各挑 2-3 |

模糊時用 AskUserQuestion 確認，**不要用猜的**。

---

## Shared Facets（JC / Case 共用）

### F1: Audience（聽眾光譜 + 誰會質詢）

**Why it matters**: 聽眾決定 vocabulary、引用密度、可以省多少 background、討論深度。

**Baseline questions**:
- 主要聽眾光譜：(a) 同次專科 attending + fellow（深）；(b) 跨次專科 / 內外科混合（中）；(c) 住院醫師 + 醫學生（淺）；(d) 跨領域（病理 / 生統 / 護理 / 社工）；(e) 多 tier 混合
- 對 topic 既有熟悉度：完全外行 / 看過不精 / 同行 / 第一線專家
- **誰 hostile / 誰會質詢**：哪位 attending / fellow 會問最尖銳？問什麼？

**Follow-up triggers**:
- 答「多 tier 混合」→「background 該對誰寫？default 第二低 tier（不放棄 residents、不浪費 attending）」
- 答「同行專家」→「他們已知的能不能跳掉、只留 added value？」
- 答不出誰會質詢 →「先列 3 個最可能挑戰的 attending + 他們的 hobby horse 議題」

---

### F2: Take-home（聽眾走出 room 記得的 1 句）

**Why it matters**: 一週後聽眾只記得 1 件事，你想要那件事是什麼。

**Baseline questions**:
- 一句話 take-home（**限 30 字**，禁用「了解 / 認識 / 知道」這種空動詞）
- 對象：聽眾應該「想 / 做 / 改」什麼？
- Monday morning 行為改變：**具體**是什麼？（不是「會更注意 X」這種 weasel）

**Follow-up triggers**:
- 30 字寫不出來 →「先去想，投影片寫完才發現沒 take-home 是 worst case」
- 答「了解 X 重要性」→ 直接 surface：「vague animation，請改成行為 / 決策 / 預期變化」
- Take-home 跟 paper / case 結論不一樣 →「你是要 report 還是 critique？哪個主軸？」

---

### F3: Strongest Claim + Evidence Tier（最強論點 + 證據強度）

**Why it matters**: JC 精華 = 你的批判；case 精華 = 你的決策邏輯。兩者都靠 evidence 撐。

**Baseline questions**:
- 你想 push 的最強 claim（1 句話）
- Evidence tier：
  - **Tier A**: 大型 RCT / MA / 國際 guideline 一致
  - **Tier B**: 單一 RCT / 大型 cohort / 多 guideline 一致
  - **Tier C**: 小型 RCT / 中型 cohort / case-control / guideline 分歧
  - **Tier D**: case series / qualitative / mechanism / animal / expert opinion
- 關鍵 reference 數量 + 年份分布（5 年內幾篇 / 10 年內幾篇 / 更早幾篇）

**Follow-up triggers**:
- Tier C/D claim 但寫「應該 / 必須 / 強烈建議」→「降級成『可考慮 / 提示 / 值得進一步研究』，否則攻擊面太大」（語氣保守客觀；統計 NS 不寫成「降低 X%」或「沒差」）
- 全 5 年外 →「找一篇近 3 年的補上，否則『沒 follow 最新文獻』會被打」
- Reference < 5 + Tier A claim →「Tier A 通常需近期 MA / guideline 撐，否則 reviewer 質疑」

---

### F4: Devil's Advocate（弱點 + 防禦）

**Why it matters**: 預想不到的攻擊 = 報告當下被當眾撕。

**Baseline questions**:
- 列 **3 個** 聽眾最可能打你的角度（具體，不是「方法論」這種 vague）
- 每個角度打算怎麼防：(a) 預先在 slide 自打 / (b) 留 Q&A 才回 / (c) 承認 limitation 不防
- **最沒把握的弱點**：____

**Follow-up triggers**:
- 列不出 3 個 →「找 senior 5 分鐘走過 outline，自己想不到的攻擊面就是盲區」
- 全選 (c) →「take-home 太弱，聽眾沒理由聽你」
- 全選 (a) →「投影片變超防禦性、失焦；挑 1-2 個最重要的預打就好」
- 最沒把握的弱點 = take-home 基礎 → red flag：「重想 take-home，主論點站不住」

---

### F5: Discussion Spark（想引發什麼辯論）

**Why it matters**: 好的 JC / case discussion 不是 monologue，是引發 attending 之間吵架；吵得起來代表選了真議題。

**Baseline questions**:
- Q&A 階段你預想會吵什麼：(a) 治療策略；(b) 適應症 / 病人選擇；(c) 方法論 / 證據強度；(d) 跨科界線；(e) 倫理 / SDM；(f) 教學重點
- Prepare 了幾題 discussion question？品質（open-ended vs yes/no）？
- 現場 silence 怎麼辦？（fallback prompting question）

**Follow-up triggers**:
- 沒 prepare discussion question →「至少 prepare 3 題，每題針對不同 attending hobby」
- 全 yes/no →「改 open-ended，否則 5 秒結束 dead air」
- 答不出 fallback →「現場 silence 要有 1 句 ice-breaker，例如『如果這位病人是你家人 / 你當住院醫師時你會怎麼做』」

---

### F6: Background Setup（聽眾 primer + 為什麼是現在）

**Why it matters**: 報告開場 5 分鐘 background 沒鋪好，後面 25 分鐘全白費 — 聽眾還在追主題、跟不上你的論點。Background 不是「我懂所以要展示」，是「為了懂這 paper / case，聽眾**最少需要知道哪 3 件事**」。同時這也是 take-home (F2) 的 framing context — 沒 framing claim 就是孤立的。

**Baseline questions**:
- 聽眾走進來時對 topic 的既有 knowledge state（1 句話）：____
- 為了懂這 paper / case，他們**最少需要哪 3 件事**？(vocabulary / prior landmark trial / current guideline / disease epi / anatomy refresher / 過去 5 年改 practice 的事件)
- 這個 topic 的**當下熱點 / 為什麼是現在**：(a) 剛出的 guideline update；(b) 剛收的 landmark RCT 結果；(c) 公共輿論 / FDA action / 衛福部公告；(d) 該領域 controversy 正在發酵；(e) 沒熱點，純 routine 學術討論
- Controversy / camps：這個 topic 有幾派立場？分別 push 什麼？你打算偏哪邊？

**Follow-up triggers**:
- 列不出聽眾「最少需要知道的 3 件事」→「就是 background slide 內容沒釘穩 — 寫出來就是 slide 3 的 bullets。寫不出來代表自己也沒搞清，先補功課」
- 答「沒熱點」→「真的沒？grep 近 3 個月相關 guideline / NEJM / Lancet / JAMA 大刊 + 主學會官網。如果真沒，這篇 paper 報的時機要重想」
- Controversy 答「沒爭議」→「沒爭議 = 沒討論題 = 浪費聽眾 30 分鐘。重找 angle 或重選 paper / case」
- Background 跟 take-home (F2) 跨距太大（e.g. background 講 disease epi、take-home 講 SDM）→「中間缺 logic bridge slide，補一張」
- Audience tier 是「跨科 / 醫學生」(F1) 但你的「最少 3 件事」全是 sub-specialty jargon →「重設 3 件事，配合聽眾 tier」

---

## JC-Specific Facets

### F6_JC: Study Design Fit

**Why it matters**: 報 paper 不是 summary、是評估 design 能不能回答這個 question。

**Baseline questions**:
- Research question 屬於：(a) efficacy；(b) safety；(c) prognosis；(d) diagnosis；(e) lived experience / preference；(f) mechanism；(g) economics
- Design：(a) RCT；(b) cohort；(c) case-control；(d) cross-sectional；(e) qualitative；(f) SR/MA；(g) case series；(h) basic / animal
- 用 **OCEBM / Sackett's user's guides** 評：design ↔ question 配對 (Strong fit / OK fit / Mismatch)?

**Follow-up triggers**:
- Qualitative 想答 efficacy →「Mismatch — frame 成 hypothesis-generating 而非 effectiveness evidence」
- RCT 想答 lived experience →「Mismatch — RCT 的 PRO 只是 quantitative slice」
- Single cohort 想答 causation →「Mismatch — 講 association 不講 causation」
- Mismatch 但作者沒承認 →「這是你的最強 critique angle」

---

### F7_JC: Methodology Red Flags（依 design 套 reporting guideline）

**Why it matters**: 用對應 reporting guideline 對 paper 體檢。

**Baseline questions** — 套對應 checklist：
- **RCT** → **CONSORT 2010**：randomization / allocation concealment / blinding / ITT / sample size justification / primary outcome pre-specified
- **Observational (cohort/case-control)** → **STROBE**：confounding adjustment / selection bias / measurement bias / missing data
- **SR / MA** → **PRISMA 2020**：PROSPERO 註冊 / search strategy / RoB2 / ROBINS-I / heterogeneity / publication bias (funnel)
- **Qualitative** → **COREQ 32-item / SRQR / CASP qualitative**：reflexivity / sampling rationale / saturation / member checking / triangulation / coder 信度
- **Diagnostic** → **STARD**：reference standard / blinded interpretation / spectrum bias
- **Prognostic** → **TRIPOD**：development vs validation / calibration / discrimination

列 **3 個紅旗 + 3 個做得好的點**。

**Follow-up triggers**:
- 紅旗 < 3 →「再讀 Methods + Results — paper 永遠有可挑，挑不出 3 個代表沒讀透」
- 紅旗 > 5 →「太多反而沒重點，挑 top 3 最致命」
- 紅旗都跟 take-home 衝突 →「為什麼還要 push 這個 take-home？」

---

### F8_JC: Generalizability / Transferability

**Why it matters**: paper 結論對「你的病人」適用嗎。

**Baseline questions**:
- Study population vs 你的目標 population 差異：age / sex / race / setting (tertiary vs community) / 健保系統 / time period
- Intervention 在台灣 implement 可行性：(a) 完全可；(b) 需 adapt；(c) 不可（藥不在台灣 / 系統不同）
- 你會套到「自己下一個病人」嗎？為什麼會 / 不會？

**Follow-up triggers**:
- US tertiary 套台灣 community →「Setting gap 大，需 adapt 段落」
- Population 90% 一種 race →「reproduce 性可能差，標 limitation」
- Intervention 含台灣沒上市的藥 →「not directly applicable，改 frame 成 conceptual lesson」

---

### F9_JC: Effect Size vs Statistical Significance

**Why it matters**: NS ≠ no difference；significant ≠ clinically meaningful。

**Baseline questions**:
- Primary outcome 的 effect size：HR / OR / RR / mean difference + 95% CI
- CI 跨 null 嗎？跨了還 push「有效」= 過度斷言
- **MID (minimal important difference)** 過了嗎？
- NNT / NNH 算過嗎？

**Follow-up triggers**:
- Paper 用「降低 X%」描述 NS 結果 →「misleading，改寫成『未達統計顯著』」（語氣保守客觀；統計 NS 不寫成「降低 X%」或「沒差」）
- p < 0.05 但 effect size 在 MID 以下 →「statistically sig but clinically trivial — 強 critique angle」
- 沒報 CI 只報 p →「red flag，CI 才是真資訊」
- NNT > 100 但強調「effective」→「實務上不太可能改 practice，take-home 降溫」

---

### F10_JC: Knowledge Gap（填了什麼洞 / 留了什麼洞）

**Why it matters**: paper 價值 = 把 evidence map 推前多少。

**Baseline questions**:
- 這篇之前領域知道什麼？（**1 句話 prior state**）
- 這篇加了什麼？（**1 句話 increment**）
- 這篇後仍不知道什麼？（**列 3 個 open question**）
- 跟 paper 自己的 discussion 比，你列的有重複還是新的？

**Follow-up triggers**:
- Prior state 寫不出 →「沒讀過該領域 prior work — 至少 grep 1 篇 SR 或 latest guideline 補背景」
- Increment = 「first qualitative / first in X population」→「take-home 是 hypothesis-generating，不是 practice-changing」
- Open question 全跟 paper discussion 重複 →「沒 added value，再想 1 個 paper 沒提的」

---

### F11_JC: Sample & Measurement Depth（依 design 分流）

**Why it matters**: F9_JC 紅旗是 broad-sweep（COREQ / CONSORT 整套 sniff test），但「sample 怎麼來」「instrument 量得準不準」這兩件事是**單獨會打死整篇 paper** 的點，值得拆出來深掘。**依 paper design 走對應 sub-checklist**。

**Baseline questions (RCT)**:
- **Sample size justification**：assumed effect size / variance 合理嗎？太樂觀 → underpowered；太保守 → 過度招募 + 倫理問題
- **Randomization mechanism**：computer-generated / sealed envelope / minimization？allocation concealment 怎麼做？
- **Blinding tiers**：participant / clinician / outcome assessor / statistician — 哪幾層 blinded？open-label trial 的 outcome 是 objective (e.g. mortality) 還是 subjective (e.g. PROM)？
- **Primary outcome pre-specification**：ClinicalTrials.gov / EUCTR / ISRCTN registration 在哪？預先 specified 跟 published 的 primary outcome 一致嗎？
- **Primary instrument validation**：用的 PROM / endpoint 有 validation paper 嗎？validated **在跟 study population 同樣的 population** 嗎？

**Baseline questions (Cohort / Case-Control)**:
- **Recruitment strategy**：consecutive / convenience / probability sampling？exclusion criteria 排掉誰、selection bias 偏哪邊？
- **Exposure ascertainment**：誰判定 exposure？timing relative to outcome？recall bias / detection bias 風險？
- **Outcome ascertainment**：blinded to exposure 嗎？inter-rater reliability (kappa) 報了嗎？
- **Confounder list**：作者 adjust 了哪些？你覺得**他們忽略了哪個關鍵 confounder**（age / sex / SES / comorbidity / co-treatment）？
- **Sample size + power**：a priori 計算還是 post-hoc rationalization？

**Baseline questions (Qualitative)**:
- **Sampling rationale**：purposive (maximum variation / typical case / extreme case) / theoretical / convenience？sampling logic 跟 research question 對應嗎？
- **Saturation criteria**：作者怎麼判斷 saturation reached？stop rule 明確（e.g. 連續 N 個 interview 沒新 code）還是含糊「team agreed」？
- **Coder team training**：how many coders / coding scheme 怎麼 develop / inter-coder agreement 怎麼算 / discrepancy 怎麼 resolve？
- **Reflexivity**：team 跟 participants 的權力關係 / pre-existing relationship 揭露嗎？interviewer 身分對 response 影響評估嗎？
- **Audit trail**：raw transcript / coding tree / memo 公開嗎（OSF / supplementary）？

**Baseline questions (SR / MA)**:
- **Protocol registration**：PROSPERO 註冊了嗎？protocol deviations 標了嗎？
- **Search strategy**：MEDLINE + Embase + Cochrane + grey literature + reference list + forward citation — 都跑了嗎？search date 多久前（> 2 年 stale）？
- **Dual independent reviewer**：title/abstract + full text 雙人 + 第三人 arbitrate？kappa 報了嗎？
- **Risk of bias tool**：用對應 design 的工具（RCT → RoB2 / 觀察性 → ROBINS-I / Newcastle-Ottawa / prognostic → QUIPS / diagnostic → QUADAS-2）？

**Baseline questions (Diagnostic accuracy)**:
- **Reference standard**：gold standard 真的 gold？imperfect reference 怎麼處理？
- **Spectrum bias**：study population 跟臨床實際 patient mix 對應嗎？enriched cohort 會虛高 accuracy
- **Blinded interpretation**：index test 跟 reference standard 雙向 blinded？

**Follow-up triggers**:
- Paper 沒揭露 randomization method →「red flag — 可能 quasi-random / alternation；改 cite 為 Tier B 而非 Tier A」
- Qual paper 答「sampling 是 convenience」→「transferability 嚴重受限，take-home 要降溫，open-question 補一條 future study with theoretical sampling」
- SR 沒 PROSPERO 註冊 →「outcome reporting bias + selective inclusion bias 風險增；標 limitation 並降 Tier」
- Instrument 不在 same population validated →「e.g. PROMIS 在腫瘤病人 validated ≠ 在 thyroidectomy population validated；標 limitation」
- 關鍵 confounder 缺漏（e.g. cohort 比較 thyroid hormone 跟 fatigue 但沒 adjust TSH）→「這就是 critique 主軸，要明確 surface」
- Diagnostic paper enriched cohort（50/50 positive/negative） + 強 push「accuracy 95%」 →「實際 clinical prevalence 通常 <10%，這 accuracy 數字不可外推」

---

### F12_JC: Analysis & Transparency（SAP / missing data / sensitivity / reproducibility）

**Why it matters**: 分析計畫 a priori vs post-hoc、missing data handling、sensitivity analysis 是否做、code / data 是否公開 — 這些決定 paper 結論是「robust」還是「one specific analytical choice 的 artifact」。Reviewer 跟外部讀者最常打的就是這層。

**Baseline questions**:
- **Statistical analysis plan (SAP)**：預先 published（protocol / registration）嗎？primary analysis 跟 SAP 一致嗎？deviations 報了嗎？
- **Missing data handling**：complete-case / multiple imputation / LOCF / inverse probability weighting？missing % > 20% 時用 complete-case 是 red flag
- **Subgroup analysis**：pre-specified（在 SAP）還是 fishing expedition？multiple testing correction（Bonferroni / FDR）做了嗎？interaction p value 報了嗎？
- **Sensitivity analysis**：作者有沒有 stress-test 主結論？(e.g. per-protocol vs ITT、不同 imputation 方法、排除 outlier、不同 cut-off) 結論還站得住？
- **Data / code availability**：raw data + analysis code 公開嗎（OSF / GitHub / Dryad / journal supplementary）？反過來：作者明確說 not available 嗎？
- **Pre-print / earlier version drift**：有沒有 pre-print 版本 vs 最終 published 版本的關鍵 number 變動？（reviewer 改要求 reanalyze 也算 deviation）

**Follow-up triggers**:
- 沒 pre-specified SAP →「primary outcome 可能事後 swap；如果 primary 是 composite，作者選哪個 component 主推也是 cherry-pick 風險」
- Missing data > 20% + complete-case 主分析 →「結論可能 systematically biased；要求 multiple imputation sensitivity 才能 trust」
- 大量 subgroup 沒 multiple testing correction →「false positive 機率超 5%；如果 paper take-home 是 spurious subgroup finding → 主 critique angle」
- 沒做 sensitivity analysis + 結論很 surprising →「single analytical choice artifact 風險高，cite 為 hypothesis-generating 而非 definitive」
- Code / data 不公開 + reproducibility 弱 →「在 Tier B-C 以下，open science 缺失另算扣分」
- Pre-print 跟最終版 primary outcome 變了 →「outcome switching，COMPare project 等級紅旗，要當 critique 開場白」

---

## Case-Specific Facets

### F6_Case: Teaching Point

**Why it matters**: case 不是病史朗讀、是教學工具。

**Baseline questions**:
- 一句話 teaching point（**限 25 字**）
- 屬於：(a) 罕見診斷的辨識；(b) 常見診斷被 miss 的 pattern；(c) 治療決策 trade-off；(d) 手術 / 操作技術 lesson；(e) 跨科溝通 / 系統錯誤；(f) 病人偏好 / SDM；(g) 倫理 / 法律
- 為什麼挑這個而不是同類其他 case？（**unique angle**）

**Follow-up triggers**:
- Teaching point > 25 字 →「砍到核心」
- 答 (a) 罕見 →「teaching value 通常在『what should have triggered the workup』而非診斷本身」
- 挑這 case 的理由是「剛好接到」→「重想：為什麼值得用 30 分鐘大家的時間？」

---

### F7_Case: Decisional Turning Points + Counterfactual

**Why it matters**: case discussion 辯論點 = 「換我會選不一樣」的 fork。

**Baseline questions**:
- **最有討論價值的 1-2 個 decision point**（不是全部）
- 每個 fork：你們選 X，alternative 是 Y / Z
- **Counterfactual**：走 Y 路徑，預期 outcome 差異？(有 / 沒有 / 不知道)

**Follow-up triggers**:
- 列 > 3 個 →「1 小時頂多 deep dive 2 個，砍 nice-to-have」
- 答「沒 alternative」→「不是 decision point，是 fait accompli — 換一個真有 fork 的時刻」
- 答「不知道 counterfactual」→「先查 1 篇 guideline / cohort 看 Y outcome 資料，否則流於 opinion」

---

### F8_Case: Evidence Base for Decisions

**Why it matters**: 「我們就這樣做」≠ 教學。

**Baseline questions**:
- 每個 turning point 依據：(a) RCT / guideline / Class I；(b) cohort / Class II；(c) expert consensus / 該院 protocol；(d) personal experience / supervisor 偏好
- 查證過 guideline 對應條目嗎？哪本？哪年？
- 如果 (c)(d)，預想會被質疑哪個 evidence-based alternative？

**Follow-up triggers**:
- 全 (a) →「沒討論空間 — 換個有 grey zone 的 case」
- 答「沒查 guideline」→「先查 1 條對應 NCCN / ESC / AHA / 學會 guideline，否則被問就垮」
- 答「supervisor 就這樣決定」→「那是 personal experience，標出來，不要包裝成 evidence」

---

### F9_Case: Patient-Centered Considerations

**Why it matters**: case 不只是 disease management、還是 person management。

**Baseline questions**:
- 病人 preference / value 在決策過程角色：(a) 主動 SDM；(b) 被動接受；(c) 沒被問；(d) 家屬代理
- 病人 vs 醫療團隊 priority 有衝突嗎？（cost / QoL / 工作 / 家庭 / religion / autonomy）
- 怎麼把「病人視角」帶進 discussion，**不只是 Social Hx**？

**Follow-up triggers**:
- 答「病人沒被問」→「本身就是 teaching point — SDM gap 是好議題」
- 病人 vs 團隊衝突沒解決 →「不要假裝沒事，攤在 discussion 講」
- 答「放在 Social Hx」→「太薄；考慮獨立 slide『From the Patient's Perspective』」

---

### F10_Case: Lesson Scope

**Why it matters**: lesson 是「全人類都該學」還是「就這個 zebra」。

**Baseline questions**:
- Lesson 適用：(a) 所有遇到該主訴的醫師；(b) 該科專科；(c) 該次專科；(d) 該院特定 service；(e) unique 情境
- 過去 6 個月你 / 同事看過幾個類似 case？(0 / 1-2 / 3-5 / >5)
- 如果 scope 很窄，為什麼還要 30 分鐘大家聽？

**Follow-up triggers**:
- 答「適用所有醫師」+ 0 次類似 →「scope 不對稱 — 改 frame 成『罕見但要記得 trigger workup』」
- 答 > 5 次類似 + scope 窄 →「放大 scope，這是 common pattern 不是 zebra」
- Case 太 unique →「teaching point 應該不是診斷本身、而是 system / process lesson」

---

### F11_Case: Disease Primer / Background（disease entity 5 分鐘 background）

**Why it matters**: Case discussion 開場 5 分鐘 disease primer 沒鋪好，後面 attending 的討論全飄 — 連 R 都不知道為什麼這 case 值得花時間。F6 Shared Background Setup 是通用面，本 facet 是 case 特化：聚焦 disease entity 而非 paper context。

**Baseline questions**:
- 這個 disease entity 聽眾**最少需要知道哪 3 件事**？(definition / epidemiology / current guideline pathway / pathophysiology / typical clinical presentation 中挑 3 個)
- 過去 5 年有沒有 landmark guideline update / RCT / SR 改變該 disease 的 management？是否影響本 case 的決策評估？
- 病人 demographic（age / sex / race / setting / comorbidity）對應的 disease prevalence + classic presentation 怎樣？這個 case 是 typical 還是 atypical presentation？
- 你報告的聽眾**科別 perspective**：外科 / 內科 / 急診 / 病理 / radiology 看同一 disease 切入點不同，你的 framing 對應哪個？
- 過去類似 case 的 published literature（review article / case series / systematic review of case reports）有沒有？

**Follow-up triggers**:
- 答不出 3 件事 →「先 grep 1 篇 latest review article 或 latest guideline 補背景，否則開場就垮」
- 沒查 5 年內 guideline update →「先查再報。Attending 一句『最新 guideline 怎麼說』就垮」
- Case 是 atypical presentation 但 background slide 只講 typical →「補一句 'this case deviates from typical presentation in X' 連到 teaching point」
- 答「沒查過 case literature」→「至少 PubMed 一次同 disease entity 的 case series，看看有沒有類似 reported case + outcome」

---

### F12_Case: Workup Strategy（test 順序 + 影響 management 的 vs 順便做的）

**Why it matters**: 「為什麼做這個 test 不做那個」「為什麼按這個順序」是 case discussion 教學核心。Workup 不只是「列做了哪些」，而是「為什麼這樣 design」。F8_Case 是「decision 背後 evidence」，本 facet 更早 — workup design 本身的 methodology。

**Baseline questions**:
- 你們的 workup 順序 vs 標準 algorithm / guideline pathway：完全一致 / 跳順序 / 跳掉某個 step？跳的理由（cost / 時間 / clinical urgency / pre-test probability）？
- 哪個 test 是**真的影響 management decision** 的？哪個是「順便做 / defensive medicine」？
- 有沒有 test 你們**沒做但 retrospectively 應該做**？為什麼當下沒做？
- 診斷確認 vs rule-out 兩條路徑：你們選哪條？trade-off 評估了嗎（cost / risk / sensitivity-specificity tradeoff）？
- 同一 case 如果不是你的醫院（換 community hospital / 偏鄉 / 國外）能不能 reproduce 這個 workup？resource-dependence 標出來嗎？
- Imaging / lab 的 ordering 有沒有 stewardship 考量？(過度檢查 / cost / radiation exposure / contrast risk)

**Follow-up triggers**:
- 答「全照 textbook」→「那 teaching value 低；挑一個 grey-zone 或有 deviation 的 case 比較有討論價值」
- 答「跳順序但 outcome 沒事」→「lucky ≠ right。Workup 順序教學重點：未來該不該重複這個 short-cut？risk-benefit 怎麼算？」
- 答「沒做某個 test 因為沒想到」→「**那是 teaching point # 1**，誠實列出來，不要包裝成『clinical judgment』」
- 答「全部 test 都重要」→「不可能 — 攻擊面太廣。挑 top 1-2 個 decisive test 主推，其他放 supplementary」
- 答「不知道在 community hospital 能不能 reproduce」→「補一行 'resource-dependent steps marked with *'，否則 audience 中的 community physician 沒辦法 take-home」
- Workup 含 imaging / contrast / radiation 但沒提 stewardship →「外科 / radiology attending 會打，補一句 risk-benefit 評估」

---

## Pack-wide Follow-up Triggers

- 任何答案太 vague（< 5 字 / 全 abstract / 全 weasel：「了解 / 認識 / 重要 / 關注」）→「具體一點：你能舉例嗎？想像 attending 拿你這句會反問什麼？」
- 任何「skip / 不知道」→ 標 *(unresolved)*，跳下一題，總結時 surface
- F1 / F2 / F3 / F5 任一答案跟其他 facet 矛盾 → 直接 surface
- Take-home (F2) 太 vague → **收尾後 push back**：「F2 沒釘穩 — 建議再 grill F2 once，否則 pptx 寫完還是會 drift」
- **F6 Background Setup 的「最少需要知道 3 件事」直接餵 outline slide / background slide bullets** — 沒這 3 件事 = background slide 寫不出
- 偵測到 paper 是 **qualitative** → 強制套 F7_JC COREQ + **F11_JC qualitative branch**（sampling rationale / saturation criteria / reflexivity / audit trail）
- 偵測到 paper 是 **RCT** → 強制問 F9_JC effect size + MID + NNT + **F11_JC RCT branch**（randomization / blinding / pre-spec primary） + **F12_JC SAP / missing data / sensitivity**
- 偵測到 paper 是 **SR / MA** → 強制問 **F11_JC SR branch**（PROSPERO / dual reviewer / RoB tool）+ **F12_JC publication bias funnel / heterogeneity sensitivity**
- 偵測到 paper 是 **observational cohort** + claim 含「effect / cause / reduce」→ 強制 surface F11_JC confounder list 缺漏點
- 偵測到 Case subtype + workup 有「跳順序 / 不照 algorithm」→ 強制問 F12_Case 跳的理由 + counterfactual

---

## 退讓規則

- 使用者要**寫 paper / manuscript** → 跳 `/academic-paper` / `/manuscript-writing-review` / `/manuscript-results` / `/academic-pipeline`
- **研究設計 / 統計規劃** → 跳 `/research-plan`
- **單純做 pptx 不用 grill**（已知所有 angle）→ 直接走 `/journal-club-discussion-pptx` / `/case-discussion-pptx`
- **單純讀 paper 摘要** → 跳 `/get-paper` / `/deep-research` paper review 模式
- **全套文獻回顧** → 跳 `/deep-research` full mode

---

## Quick mode 預設抽題（5-7 題）

對 academic-medical pack，Quick mode 預設挑這 6 個 facets（每個 facet 1 題）：

1. **F1 Audience**（誰會聽 + 誰會質詢）
2. **F2 Take-home**（30 字硬上限）
3. **F6 Background Setup**（最少需要知道 3 件事 — 直接 → background slide）
4. **F9_JC Methodology Red Flags** _(JC subtype)_ 或 **F7_Case Decisional Turning Points** _(Case subtype)_
5. **F4 Devil's Advocate**（3 個攻擊面 + 最沒把握的）
6. **F5 Discussion Spark**（想引發什麼辯論）

加碼 1 題（總共 7 題）的情境：
- Paper 是 qualitative → 加 **F11_JC qualitative branch**（sampling + saturation + reflexivity）
- Paper 是 RCT → 加 **F12_JC SAP / missing data / sensitivity**
- Paper 是 SR/MA → 加 **F11_JC SR branch**（PROSPERO + dual reviewer + RoB tool）
- Case workup 跳順序 → 加 **F12_Case 跳順序理由 + counterfactual**

Deep mode 跑全部 facets + recursive follow-up（15+ 題、~15-30 min）。

---

## 跟下游 skill 的 handoff 格式

Grill 結束、寫 `./grilled-<slug>-<date>.md` 後，輸出最後印：

```
已寫入 <path>，下一步建議：
- 直接 chain `/journal-club-discussion-pptx` / `/case-discussion-pptx`，把以下 grill 結論貼進 Stage 0：
  - Audience tier: <F1 結論>
  - Take-home（30 字）: <F2 結論>
  - Strongest claim + tier: <F3 結論>
  - Background 3 件事（→ slide 3 bullets）: <F6 結論>
  - 3 個 discussion sparks: <F5 結論>
  -（JC only）Methodology critique angle: <F9_JC top 紅旗 1-2 個>
  -（JC only）Sample / Measurement red flags: <F11_JC 對應 design branch 結論>
  -（JC only）Analysis / Transparency notes: <F12_JC 結論>
  -（JC only）Knowledge gap: <F10_JC open questions>
  -（Case only）Disease primer 3 件事: <F11_Case 結論>
  -（Case only）Workup deviation + counterfactual: <F12_Case 結論>
  -（Case only）Decisional turning point + counterfactual: <F7_Case 結論>
  -（Case only）Evidence base tier per fork: <F8_Case 結論>
```

讓使用者直接複製餵 pptx skill，避免 Stage 0 又被問一輪重複問題。

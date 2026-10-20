---
name: critical-ai
description: "用 clinical reasoning + EBM 6-lens 批判 AI 生成的醫學內容（DDx / management plan / paper summary / citation / research design），偵測 LLM 已知失敗模式（confidently wrong reasoning、right-answer-wrong-rationale、context-sensitivity blindness、sociodemographic bias）。Trigger：`/critical-ai`、`/cai`、「批判這 AI 答案」「審核 LLM 輸出」「ChatGPT 寫的對嗎」「這診斷 AI 給的合理嗎」「這 ChatGPT 的 management plan ok 嗎」。"
allowed-tools: Read Write Edit Bash WebFetch WebSearch
license: MIT
---

# critical-ai — 批判性評估 AI 醫學輸出

## Why this skill exists

2024–2026 RCT 證據確立兩個事實：
1. **LLM diagnostic accuracy 高** — Singhal *Nature* 2023 (PMID 37438534)；McDuff *Nature* 2025 AMIE (PMID 40205049) DDx top-10 hit rate 59% vs unassisted physician 34%。
2. **醫師不會用 LLM** — Goh *JAMA Netw Open* 2024 (PMID 39466245) RCT 50 醫師：physician + GPT-4 vs physician alone **沒差**；GPT-4 alone 卻顯著高於兩組醫師。Cabral *JAMA Intern Med* 2024 (PMID 38557971)：GPT-4 reasoning documentation quality 高於主治，但 **false reasoning（邏輯通順但結論錯）發生率也較高**。Jin *NPJ Digit Med* 2024 (PMID 39043988) GPT-4V：final answer 對 ~80%，但 **reasoning rationale 錯誤比例極高**。Rao *JAMA Netw Open* 2026 (PMID 41973425) **PrIME-LLM** 5-domain benchmark：21 主流 LLM 在 final diagnosis 強（failure rate <0.40），但 **differential diagnosis failure rate 0.90–1.00**。

**結論**：在 AI 時代，**critical appraisal of AI output 變成核心 cognitive skill**。本 skill 是這個 skill 的操作化 — 把 clinical reasoning（dual process / illness scripts / threshold / debiasing）與 EBM（RoB / GRADE / DAG）框架重新組裝成「AI output 專用 critique lens」。

## When to trigger

- 使用者貼 AI 生成的醫學內容（DDx / dx reasoning / management plan / paper summary / citation list / research design）要求審核
- **使用者貼 paper / abstract / SR 摘要請我審** → Lens 3（PICO framing）先跑，PICO 缺項直接 🔴 REJECT，不必往下做 Lens 5 深度 appraisal
- 顯式呼叫：`/critical-ai`、`/cai`
- 中文意圖：「批判這 AI 答案」「審核 LLM 輸出」「ChatGPT 寫的對嗎」「這診斷 AI 給的合理嗎」「Gemini 給的 management ok 嗎」「Claude 開的 workup 漏了嗎」「這篇 paper 摘要 AI 寫得對嗎」「AI 整理的文獻可信嗎」
- **Self-audit mode**：Claude 自己生成 clinical reasoning 後（DDx / management / SR conclusion / paper summary），內部跑一次本 skill 再輸出

## When NOT to trigger（路由給其他 skill）

| 情境 | 改用 |
|---|---|
| 純統計 pipeline 品質檢查 | `/biostats-guardian` |
| 完整 AI 研究流程多重把關 | `/research-guardian` |
| 一般科學主張評估（非 AI 生）| `/scientific-critical-thinking` |
| 三角驗證找 retrieval 盲區 | `/oe-triangulate` |
| 寫稿語言品質（不是 reasoning 品質）| `/manuscript-writing-review` |

## Inputs（缺也能跑，能補則加分）

1. **AI output**（必要）— 貼文字、給檔案 path、或描述
2. **Original prompt**（強烈建議）— 使用者問了什麼
3. **Model / source**（建議）— GPT-5 / Claude Opus / Gemini Pro / OpenEvidence / Med-PaLM 2 — 不同模型有不同已知失敗模式
4. **Artifact type**（缺則 skill 自己分類）— 6 種類別：
   - **A. Diagnostic reasoning / DDx**
   - **B. Management / treatment plan**
   - **C. Paper / SR summary / abstract**
   - **D. Citation list / reference**
   - **E. Research design / proposal**
   - **F. Clinical communication（衛教文 / 病人說明）**
5. **Clinical context**（建議）— 病人年齡 / sex / setting / 主訴 — 用來判斷 context-sensitivity gap

## The 6 Lenses

依 artifact type 決定套用哪幾個 lens。Lens 1 永遠套用。

**執行順序**：對 C/D/E artifact（paper / citation / research），**Lens 3（Question Framing）先於 Lens 5（Evidence Quality）**。Framing 不清楚，appraisal 沒意義 — 你不知道在 appraise 什麼問題。Lens 3 出 🔴（PICO 缺項 / 模糊）→ 標記後直接給 verdict，跳過 Lens 5 深度稽核。

### Lens 1 — Confidently-Wrong Pattern Scan（永遠套）

LLM 最危險的不是「明顯錯」，是「**讀起來很順但結論錯**」。檢查：

| 模式 | 操作化檢查 |
|---|---|
| **False reasoning**（Cabral 2024）| 逐句檢查 inference 鏈：每個「因此 / 所以 / 表示」前後是否真的邏輯成立？有無 leap？|
| **Right answer, wrong rationale**（Jin 2024）| 結論若正確，**獨立**驗證 rationale 對不對 — 不要被「答案對」催眠 |
| **Confidence-evidence mismatch** | LLM 用「確定」「明顯」「典型」等斷言詞時，問：cited evidence 撐得起這個 confidence 嗎？|
| **Fabricated specificity** | 數字 / 百分比 / 引用是否真實？任何「研究顯示 X%」沒附 PMID → 標 🔴 需驗證 |
| **Sociodemographic bias**（Omar *Nat Med* 2025, PMID 40195448）| 病人是 minority / female / 低收入時，AI 推薦是否與同條件白人男性 default 有別？|

### Lens 2 — Cognitive Bias Scan（套於 A/B — diagnostic / management）

Croskerry taxonomy → 把同樣 bias 反過來用在 AI 上：

| Bias | LLM 表現形式 | 操作化檢查 |
|---|---|---|
| **Anchoring** | LLM 黏在 prompt 第一個 cue | 重排 prompt cue order，answer 變嗎？|
| **Premature closure** | LLM 給一個 dx 就停 | DDx 列表只 1–2 個？ 🔴 |
| **Search satisficing** | 漏 concurrent 第二診斷 | Appendicitis + ovarian torsion 同存的 case，LLM 提了第二個嗎？|
| **Availability bias** | LLM over-weight 訓練常見 dx | 罕病 case，LLM 是否跳過罕病走 common one？|
| **Representativeness** | LLM 因「長得像」忽略 base rate | Atypical presentation 是否被 force 進 typical bucket？|
| **Confirmation** | LLM 只列支持 working dx 的 features | 有 disconfirming evidence 在 prompt 但 LLM 忽略？|

### Lens 3 — Question Framing Quality（套於 A/C/D/E — 所有 reasoning / literature artifact）

**核心觀念**：clinical one-liner（病人 framing）與 PICO（文獻 framing）是**同一個認知操作** — 把混沌資訊結構化成可推理的 question。Framing 是 EBM 5 steps (Ask → Acquire → Appraise → Apply → Assess) 的 **Step 1 "Ask"**，先於 appraisal。醫師讀文獻第一步就是抽 PICO；本 lens 把這個第一步操作化套在 AI output 上。

**A — Diagnostic reasoning（one-liner / problem representation）**

Bowen *NEJM* 2006 (PMID 17124019) 框架：

- AI 的 one-liner 是否包含 demographics + epi context + temporal + key abnormalities？
- Semantic qualifiers 夠不夠特異？（「pain」🔴 vs 「acute, severe, left-sided, pleuritic chest pain」🟢）
- 缺哪些必要 qualifier → 列出具體 missing list 給使用者補

**C/D/E — Paper / Citation / Research（PICO 家族 framing）**

Richardson *ACP J Club* 1995 (PMID 7582737) PICO + 後續變體。依 question type 選用：

| Question type | Framework | 必要 elements |
|---|---|---|
| Therapy / Intervention | **PICO** | Population / Intervention / Comparator / Outcome |
| SR / Meta-analysis | **PICOS**（PRISMA 2020）| + Study design |
| Prognosis / Timing | **PICOT** | + Timing horizon |
| Etiology / Harm / Exposure | **PECO** | Population / Exposure / Comparator / Outcome |
| Qualitative | **SPIDER** | Sample / Phenomenon / Design / Evaluation / Research type |

操作化檢查（套於 AI 寫的 paper 摘要 / SR 結論 / research proposal / citation 解讀）：

- **抽出 PICO**：AI output 能不能逐項抽出 P/I/C/O？抽不出 → 該 element 模糊
- **Population specificity**：有 inclusion/exclusion？年齡 / setting / 共病 / disease severity 是否定義？「critically ill patients」🔴 vs 「ICU patients with septic shock requiring vasopressor」🟢
- **Intervention specificity**：劑量 / 頻率 / duration / route 有沒有？「antibiotic therapy」🔴 vs 「ceftriaxone 2 g IV q24h × 7 days」🟢
- **Comparator quality**：active comparator 還是 placebo？「standard care」沒定義 → 🟡（standard care 在不同國家 / 機構差距大）
- **Outcome quality**：patient-important（mortality / QoL / functional status）vs surrogate（lab value / imaging）？全 surrogate 沒 patient-important → 🟡；composite outcome 各 component 同方向？
- **PICO-evidence 對齊**：AI 列的 reference / 引用的 study population 是否真的回答原 PICO？population mismatch（成人研究套兒童 / ICU 研究套門診）→ 🔴
- **Question-method 對齊**：therapy question 卻引 observational study 沒解釋 → 🟡；etiology question 用 PICO 而非 PECO → 🟡

**紅旗（觸發後直接給 verdict，跳過 Lens 5）**：
- AI 寫的 SR / RCT 摘要找不到完整 P/I/C/O → 🔴 REJECT
- Population / Intervention / Comparator 任一項完全沒定義 → 🔴 REJECT
- AI 自己沒抽 PICO 就開始下結論「這篇研究顯示 X」→ 🔴 REJECT（framing 缺位 = appraisal 沒地基）

### Lens 4 — Bayesian Threshold Sanity Check（套於 B — management/testing）

Pauker-Kassirer 1980 (PMID 7366635) 框架反過來：

- AI 建議的檢查 / 治療是否考慮 pretest probability？
- Pretest 落在哪個 zone：no-test / test / treat？
- 是否 over-testing（pretest 已過 treat threshold 卻還在 order workup）？
- 是否 under-testing（pretest 在 test zone 卻 dismissive）？
- AI 有沒有點出 testing threshold（哪個 LR 能跨過 → 才值得測）？

### Lens 5 — Evidence Quality（套於 C/D/E — paper / citation / research）

**Prerequisite**：Lens 3（Question Framing / PICO）必須先過。PICO 缺項 / 模糊時，不做本 lens 深度稽核（appraise 一個 ill-defined question 沒意義）。

依 artifact 分支：

| Sub-lens | 工具 | 紅旗 |
|---|---|---|
| Citation 存在性 | PubMed E-utilities verify PMID | 任何 PMID 找不到 → 🔴 hallucinated；改逐筆用 PubMed 查證 |
| Reporting guideline 對齊 | EQUATOR map (CONSORT / STROBE / PRISMA 2020 / STARD 2015 / TRIPOD+AI 2024 / CARE / SQUIRE / SPIRIT / CHEERS) | AI 寫 SR 摘要漏 PRISMA flow diagram counts → 🟡 |
| RoB tool 對齊 | RoB 2 / ROBINS-I / ROBINS-E / QUADAS-2 / NOS / JBI | AI 評 RCT 用 NOS（錯工具）→ 🔴 |
| GRADE 誤用 | 4 levels of certainty + 5 down + 3 up factor + EtD framework | AI 說「high evidence」卻引 observational study 沒 upgrade rationale → 🔴 |
| Causal inference | DAG（Greenland-Pearl-Robins 1999）+ Target Trial Emulation（Hernán 2016, JAMA 2022 PMID 36508210）+ TARGET Statement 2025 (PMID 40899949) | AI 建議用 EHR 做 causal claim 沒 specify target trial 7 components → 🔴 |
| Prediction model utility | DCA (Vickers 2006 PMID 17099194) + TRIPOD+AI 2024 (PMID 38626948) | AI 推 model 只看 AUC 沒 DCA → 🟡 |

### Lens 6 — Context-Sensitivity Gap（套於 B/F — management / 衛教）

McDuff *Nature* 2025 AMIE 研究核心訊息：**LLM 在 DDx 強，在 context-sensitivity（病人偏好 / 社會因素 / 資源限制 / accountability）弱**。檢查：

- AI 建議是否考慮病人的 preference / values / 經濟狀況 / health literacy？
- 是否套 SDM（Ottawa Decision Support Framework / Three-talk model Elwyn 2017 PMID 29109079）？
- 在台灣脈絡：健保給付 / 在地 guideline / 在地藥物可得性是否被考慮？
- 病人若是長者 / 兒童 / 孕婦 / 慢病多重 — AI 有沒有跳過 cookie-cutter answer 做個別化？

## Output Format（給使用者）

```
# critical-ai 批判報告

**Artifact type**: [A/B/C/D/E/F]
**Model**: [model name if known]
**Triaged lenses**: [Lens 1, 2, 3, 4, 5, 6 中啟動哪幾個]

---

## Lens 1 — Confidently-Wrong Pattern
🟢/🟡/🔴 [一句 verdict]
- [具體 finding 1]
- [具體 finding 2]

## Lens 2 — Cognitive Bias Scan
🟢/🟡/🔴 [一句 verdict]
- ...

[同樣對所啟動的每個 lens]

---

## 紅旗（必須處理）
1. [Lens X red flag] → [recommended fix]
2. ...

## 黃旗（建議改善）
1. ...

## Verdict
- ✅ ACCEPT：可採信
- ⚠️ ACCEPT WITH CAVEATS：採信但需 [具體警示]
- ❌ REJECT：需要 redo prompt — 建議改寫 prompt 為：「[改寫版]」
```

## Handoff routing

- Citation 問題 → 逐筆用 PubMed 查證 PMID / DOI
- 後續證據三角驗證 → `/oe-triangulate`（傳該 clinical question）
- 統計 pipeline → `/biostats-guardian`
- 完整研究 QC → `/research-guardian`

## Operational notes

- 使用者貼 AI 輸出時，**不要照著它的結構回答** — 跳出來，把它當 object of critique，不是 starting point
- Self-audit mode：Claude 自己生成 medical reasoning 後，inline 跑 Lens 1+2+3 再輸出（不必對使用者顯示完整 6-lens report，但內部要 check）
- 若 artifact 過長（>3000 字），先列**最高風險 3 個 claim** 做深度 critique，其他列為「未稽核」
- **不要 hedge** — 紅旗就是紅旗。AI critique 的價值在於敢說「這段不能信」

## Evidence base（本 skill 的 substrate）

| Paper | PMID | 對應的 lens |
|---|---|---|
| Singhal *Nature* 2023 | 37438534 | Lens 1（base rate of LLM clinical knowledge）|
| Goh *JAMA Netw Open* 2024 RCT | 39466245 | 整體（醫師不會用 LLM 是觀察基礎）|
| Cabral *JAMA Intern Med* 2024 | 38557971 | Lens 1 false reasoning |
| Jin *NPJ Digit Med* 2024 GPT-4V | 39043988 | Lens 1 right-answer-wrong-rationale |
| McDuff *Nature* 2025 AMIE | 40205049 | Lens 6 context-sensitivity |
| Omar *Nat Med* 2025 | 40195448 | Lens 1 sociodemographic bias |
| Rao *JAMA Netw Open* 2026 PrIME-LLM | 41973425 | Lens 1 + 6 multi-dim failure pattern |
| Croskerry *Acad Med* 2009 + BMJ Qual Saf 2013 | 19638766 / 23882089 | Lens 2 bias taxonomy |
| Bowen *NEJM* 2006 | 17124019 | Lens 3 problem representation (clinical one-liner) |
| Richardson *ACP J Club* 1995 PICO | 7582737 | Lens 3 question framing (PICO 家族 origin) |
| Pauker-Kassirer *NEJM* 1980 | 7366635 | Lens 4 threshold model |
| Hernán *JAMA* 2022 target trial | 36508210 | Lens 5 causal inference |
| TARGET Statement *JAMA* 2025 | 40899949 | Lens 5 reporting |
| Vickers-Elkin DCA 2006 | 17099194 | Lens 5 prediction utility |
| Elwyn three-talk *BMJ* 2017 | 29109079 | Lens 6 SDM |

## Caveats

- 本 skill **不是** AI 安全 / alignment 工具 — 不偵測 jailbreak / prompt injection
- 不取代臨床判斷 — output 是 **decision support**，使用者仍須自己 own the decision
- 對 LLM hallucination 的 citation 偵測有限 — 高風險 citation 一定逐筆用 PubMed 查證

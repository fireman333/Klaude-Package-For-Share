---
name: research-guardian
description: >
  AI 研究品質防護系統。在 AI agent 執行研究任務時，自動進行多重驗證、事實查核、文獻交叉比對、實驗設計檢查，防止幻覺、邏輯錯誤、引用錯誤、與 novelty 誤判。
  任何時候 AI 被要求進行以下操作都應觸發本 skill：
  生成研究假設、撰寫文獻回顧、設計實驗、分析數據、撰寫論文段落、評估研究結果的 novelty、
  進行 systematic review、做 meta-analysis、提出研究方向建議、或任何聲稱「發現」或「創新」的場景。
  即使使用者沒有明確要求驗證，只要涉及研究性質的輸出，都應主動啟動防護流程。
  本 skill 設計用於整合進 AI agent pipeline，作為研究輸出的品質閘門。
---

# Research Guardian — AI 研究品質防護系統

> **⚠️ STATUS: PREFLIGHT STUB (2026-05-08, CRITICAL audit fix)**
>
> 本 skill 的 `scripts/runner.py:178` `run_gate()` 目前是 stub — **不執行任何實際 audit**。
> Stub 行為已改為 fail-closed：每個 gate 回傳 `status="error"` + 1 個 critical UNVERIFIED issue，
> 讓 aggregator 推薦 `reject`（不是 `accept`），避免下游 skill 把 stub-pass 當作 real-pass。
>
> 本 skill 的 reference docs（`references/*.md`）+ schema 都還可參考、checklist 仍有設計價值，
> 但**不要把 runner 的 PASS 結果當作真實 QA 通過**。下游 skill（deep-research / academic-paper /
> lit-review）若依賴本 skill 作 QA gate，請改為手動 review 直到 runner 真正實作為止。
>
> 重新啟用：替換 `runner.py:run_gate()` 內的 stub 區塊為 subagent dispatch（`spawn_subagent(...)`）。

---

## 設計哲學

AI 做研究最危險的不是「做不到」，而是「做到了但是錯的，而且看起來很對」。
本 skill 的目的不是限制 AI 的研究能力，而是在每個關鍵節點加上驗證閘門，
確保輸出經得起 peer review 級別的檢驗。

核心原則：**每一個研究性斷言，都必須通過至少兩道獨立驗證才能輸出。**

架構鐵律：**產生內容的 agent 永遠不能評估自己的輸出。所有 Gate 的評估步驟必須由獨立的 subagent 在乾淨的 context 中執行。** 這不是優化建議——這是防止 context rot 和 self-evaluation bias 的硬性要求。詳見 `references/subagent-evaluation.md`。

效能原則：**不是每次都需要全開。** 先讀 `references/quick-modes.md` 選擇模式（🟢 QUICK / 🟡 STANDARD / 🔴 FULL）和場景化 Preset（ML投稿 / 臨床報告 / 社科調查 / 文獻回顧 / 假設生成）。用 10% 算力抓 80% 問題，需要時再自動升級。

---

## 觸發條件

當 AI agent 正在執行以下任一任務時，自動啟動對應的防護模組：

| 任務類型 | 啟動模組 | 參考文件 |
|---------|---------|---------|
| 生成假設 | Hypothesis Guard | `references/hypothesis-validation.md` |
| 文獻回顧 | Literature Guard | `references/literature-verification.md` |
| 實驗設計 | Experiment Guard | `references/experiment-checklist.md` |
| 結果分析 | Result Guard | `references/result-integrity.md` |
| 撰寫論文 | Writing Guard | `references/writing-verification.md` |
| 任何 gate 運行後 | Performance Metrics | `references/performance-metrics.md` |
| 所有 gate（架構層）| Subagent Evaluation | `references/subagent-evaluation.md` |
| 所有 gate（橫切層）| Logic Fallacy Chain | `references/logic-fallacy-chain.md` |
| Pipeline 入口（首先讀取）| Quick Modes | `references/quick-modes.md` |
| 平行執行架構 | Parallel Execution | `references/parallel-execution.md` |
| 所有 gate 輸出格式 | Issue Schema + Evidence | `references/issue-schema.md` |
| Pipeline 最前端 | Paper Parser + Metadata | `references/ingestion/paper-parser.md` |
| Gate 結果彙整後 | Critique Synthesis | `references/critique-synthesis.md` |
| Gate 結果彙整後 | Red Flag Synthesis | `references/red-flag-synthesis.md` |
| 多篇論文 | Batch Review Mode | `references/modes/batch-review.md` |
| 造假偵測 | Audit Mode | `references/modes/audit-mode.md` |
| 論文比較 | Compare Papers Mode | `references/modes/compare-papers.md` |
| 模擬審稿人 | Reviewer Personas | `references/surpass/reviewer-personas.md` |
| 預測審稿意見 | Counter-Arguments | `references/surpass/counter-arguments.md` |
| 版本比較 | Version Diff | `references/surpass/version-diff.md` |
| 投稿風險評估 | Rejection Risk Score | `references/surpass/rejection-risk.md` |
| 修正建議 | Fix Examples | `references/surpass/fix-examples.md` |
| 擴充系統 | Extensibility Guide | `references/extensibility-guide.md` |

每個模組可獨立運行，也可串聯成完整 pipeline。
Performance Metrics 模組在每次 gate 運行後自動收集效能數據，不需額外觸發。

**v1.7 架構升級（參考 OpenReviewer 設計）**：

1. **平行執行**：Pre-scan 之後，所有 gate + logic chain 同時派發、平行運行。
   FULL mode 從 ~22 min 降到 ~6.5 min（3.4x 加速）。詳見 `references/parallel-execution.md`。

2. **標準化 Issue Schema**：所有 gate 輸出統一的 JSON 格式，含 evidence anchoring
   （精確指向原文位置）、confidence 分數、suggested_fix。詳見 `references/issue-schema.md`。

3. **Issue Normalization**：Aggregator 自動去重、嚴重度校準、排序。
   同一問題被多個 gate 獨立偵測 → severity 自動上調。

4. **Cross-Section Consistency**：10 對章節強制交叉驗證（Abstract↔Results,
   Methods↔Results 等），在 Aggregator 階段執行。

5. **Citation Ethics**：self-citation rate 分析、citation clustering 偵測、
   predatory journal 偵測。在 Literature Guard 中同步執行。

6. **Anti-Hallucination Grounding**：所有 subagent 的 system prompt 強制附帶
   反幻覺規則——沒有 evidence 的判定不能產生 issue。

**橫切模組說明**：Logic Fallacy Chain 不是獨立的第 6 道 Gate，而是貫穿所有 Gate 的推理驗證層。每道 Gate 檢查「素材對不對」，Logic Chain 檢查「推理通不通」。兩者同時運行，各自由獨立的 subagent 執行。自動觸發對應關係：

- Hypothesis Guard → Logic Layer 1（形式邏輯）+ Layer 2（因果推理）
- Literature Guard → Logic Layer 4（論證結構）
- Experiment Guard → Logic Layer 2（因果推理）+ Layer 3（統計推理）
- Result Guard → Logic Layer 2 + 3 + 5（因果 + 統計 + 研究特有）
- Writing Guard → Logic Layer 1-5（全部）

---

## 防護流程總覽

⚠️ **架構鐵律**：下方每個 GATE 都必須由獨立的 subagent 執行，
不得由產生研究內容的主 agent 自我評估。subagent 只接收「待評估的輸出 + 檢查量表」，
不接收主 agent 的推理過程或對話歷史。詳見 `references/subagent-evaluation.md`。

```
研究輸入（由 Research Agent 產生）
  │
  ▼
══════════════════════════════════════════════════════════
  Pre-scan (Gate 0) — 30 秒快速掃描 → 決定模式和 Preset
══════════════════════════════════════════════════════════
  │
  ▼ 平行派發（所有 gate 同時啟動，各自獨立 subagent）
  │
  ┌──────────┬──────────┬──────────┬──────────┬──────────┐
  ▼          ▼          ▼          ▼          ▼          ▼
┌────┐    ┌────┐    ┌────┐    ┌────┐    ┌────┐    ┌─────┐
│ G1 │    │ G2 │    │ G3 │    │ G4 │    │ G5 │    │Logic│
│假設│    │文獻│    │實驗│    │結果│    │寫作│    │Chain│
│    │    │+倫理│   │    │    │    │    │    │    │L1-5 │
└─┬──┘    └─┬──┘    └─┬──┘    └─┬──┘    └─┬──┘    └──┬──┘
  │         │         │         │         │           │
  └────┬────┴────┬────┴────┬────┴────┬────┴────┬──────┘
       │         │         │         │         │
       ▼         ▼         ▼         ▼         ▼
  ┌─────────────────────────────────────────────────┐
  │  Issue Normalization（去重 + 嚴重度校準）         │
  │  → 標準化 JSON Issue Schema                     │
  │  → 同一問題被 2+ gate 偵測 → severity 上調      │
  └──────────────────────┬──────────────────────────┘
                         ▼
  ┌─────────────────────────────────────────────────┐
  │  Cross-Section Consistency（10 對交叉驗證）       │
  │  Abstract↔Results, Methods↔Results,             │
  │  Hypothesis↔Conclusion, Figures↔Text ...        │
  └──────────────────────┬──────────────────────────┘
                         ▼
  ┌─────────────────────────────────────────────────┐
  │  Aggregator + Performance Metrics               │
  │  → 最終信心等級 + 效能摘要                       │
  │  → Anti-Hallucination check（無證據=移除 issue）  │
  └──────────────────────┬──────────────────────────┘
                         ▼
══════════════════════════════════════════════════════════
  結果回傳（只傳評估結論，不傳推理過程）
══════════════════════════════════════════════════════════
                         │
                         ▼
            ✅ 研究輸出（標準化 Issue 報告 + 信心等級）
```

---

## 信心等級標記系統

所有通過防護流程的研究輸出，必須附帶信心等級：

- **🟢 HIGH** — 通過所有 gate，有多來源交叉驗證，引用均已確認存在
- **🟡 MEDIUM** — 通過大部分 gate，但部分斷言只有單一來源或無法完全驗證
- **🔴 LOW** — 有 gate 未通過或被跳過，輸出僅供參考，需人工審核
- **⚫ UNVERIFIED** — 未經過任何驗證流程，明確標示為未驗證的 AI 生成內容

每個輸出段落後應標記信心等級，而非只在文末標記一次。


---

## 全局默認規則 (v1.1 — 基於驗證測試新增)

### 未報告項的默認處理
```
當研究輸出未報告某個 checklist 要求的資訊時：

未報告的項目類型           → 默認處理
────────────────────────────────────────
方法論關鍵資訊（隨機種子、power analysis、IRB）
                          → 默認 🔴 FAIL
統計報告細節（CI、效果量）  → 默認 🟡 WARN
可重現性資訊（code、env）  → 默認 🟡 WARN
搜索/驗證紀錄              → 默認 🔴 INCOMPLETE

原則：沉默不等於合規。如果 checklist 要求報告但輸出沒有報告，
     gate 不能假設「沒報告 = 沒問題」。
```

### Pre-scan 步驟 (Gate 0)
```
在正式進入 5 道 Gate 之前，先做一個 30 秒的快速掃描：

□ 整體語氣是否合理？
  - 通篇 "prove", "definitive", "revolutionary" → 立即紅旗
□ 結論的強度是否與摘要中描述的方法匹配？
  - 一個 dataset + 一個 baseline → "全球適用" → 明顯不匹配
□ 是否有明顯的結構缺失？
  - 無 Limitations → 紅旗
  - 無反面文獻 → 紅旗

Pre-scan 不取代任何 Gate，但可以在 10 秒內提供整體風險評估，
幫助 Orchestrator 決定要使用哪種 Subagent 策略（A/B/C）。
```

### Cross-gate 矛盾偵測
```
Aggregator 在彙整報告時，必須檢查以下跨 gate 矛盾：

Gate 2 (Literature) 發現引用問題 → 自動觸發 Gate 4 (Result) 重檢
  理由：如果引用的基線數字是幻覺，比較結果也不可信

Gate 3 (Experiment) 發現設計缺陷 → 自動觸發 Gate 4 (Result) 重檢
  理由：設計有問題的實驗，結果的可信度也受影響

Gate 4 (Result) 發現 overclaim → 自動觸發 Gate 5 (Writing) 加嚴
  理由：結果段有 overclaim，Discussion 段很可能更嚴重

Logic Chain 發現因果謬誤 → 回饋到 Gate 1 (Hypothesis) 重檢
  理由：推理有問題可能意味著假設本身需要修正
```

---

## 各 Gate 詳細操作指引

詳細的檢查量表和操作步驟見各參考文件：

- **假設驗證**：見 `references/hypothesis-validation.md`
  - 何時讀取：當 AI agent 正在生成新的研究假設、研究問題、或宣稱發現了新的研究方向時
  
- **文獻驗證**：見 `references/literature-verification.md`
  - 何時讀取：當 AI agent 正在引用論文、做文獻回顧、或基於現有研究做論述時

- **實驗檢查**：見 `references/experiment-checklist.md`
  - 何時讀取：當 AI agent 正在設計實驗、選擇方法論、或計算統計參數時

- **結果驗證**：見 `references/result-integrity.md`
  - 何時讀取：當 AI agent 正在報告數值結果、繪製圖表、或從數據中得出結論時

- **寫作驗證**：見 `references/writing-verification.md`
  - 何時讀取：當 AI agent 正在撰寫研究報告、論文段落、或任何將公開發表的研究性文字時

- **效能量測**：見 `references/performance-metrics.md`
  - 何時讀取：當需要評估 Guardian 系統本身的表現、設定基準測試、建立效能儀表板、或偵測系統退化時
  - 也在每次完整 pipeline 運行後自動參考，用於生成效能摘要

- **Subagent 評估規範**：見 `references/subagent-evaluation.md`
  - 何時讀取：在整合 Guardian 到 agent pipeline 時必讀。定義了 context 隔離策略、subagent 啟動規範、禁止傳遞的內容清單、inter-rater reliability 檢查方法、以及三種風險對應的評估策略
  - 這是架構層級的規範，所有 gate 都必須遵循

- **邏輯謬誤鏈**：見 `references/logic-fallacy-chain.md`
  - 何時讀取：每道 Gate 運行時自動同步啟動。這是橫切模組，不是獨立 Gate——它在每道 Gate 旁邊平行運行，由獨立的 Logic Evaluator Subagent 執行
  - 包含 5 層檢查（形式邏輯、因果推理、統計推理、論證結構、研究特有謬誤），每道 Gate 啟動對應的層級
  - 如果算力有限，至少啟動 Layer 2（因果）+ Layer 3（統計），這兩層涵蓋最常見的 AI 推理錯誤

- **快捷模式**：見 `references/quick-modes.md`
  - 何時讀取：**每次 Guardian 啟動時優先讀取**。決定跑哪個模式（🟢 QUICK / 🟡 STANDARD / 🔴 FULL）和哪個場景化 Preset（ML投稿 / 臨床報告 / 社科調查 / 文獻回顧 / 假設生成）
  - 包含自動模式選擇器、漸進式升級規則、效能指標對照
  - 可節省約 83% 算力，攔截率下降 < 10%

- **平行執行架構**：見 `references/parallel-execution.md`
  - 何時讀取：整合 Guardian 到 agent pipeline 時必讀。Pre-scan 之後所有 gate 平行派發，FULL mode 3.4x 加速
  - 包含依賴分析、派發規範、API 範例代碼、效能估算

- **Issue Schema + Evidence + 正規化 + 引用倫理 + 反幻覺**：見 `references/issue-schema.md`
  - 何時讀取：所有 gate 的 subagent 必須遵循此格式輸出 issue。Aggregator 用此格式做去重和嚴重度校準
  - 包含：標準化 JSON issue 格式、evidence anchoring、10 對 cross-section 一致性檢查、citation ethics checklist、anti-hallucination grounding 規則

---

## 已知 AI 研究失敗模式（基於文獻）

本 skill 的設計基於已記錄的 AI 研究系統失敗案例：

1. **幻覺引用**：生成不存在的論文，包含看似合理的作者、期刊、年份
2. **Novelty 誤判**：將已知概念標記為「新發現」（如把 micro-batching 當創新）
3. **實驗程式碼錯誤**：已知有 42% 的自動實驗因 coding error 失敗
4. **結果與目標矛盾**：實驗設計用於優化 A 指標，卻報告 B 指標的改善
5. **過度推論**：從有限數據得出過強的因果結論
6. **結構性缺陷**：缺少圖表、重複段落、佔位文字未移除
7. **引用過時**：大量使用 5 年以上的文獻，忽略最新進展
8. **Score inflation**：在自我評估中系統性高估自身輸出的品質
9. **Context rot**：長對話中 agent 的判斷力隨 context 膨脹退化
10. **Self-evaluation bias**：LLM 評估者系統性偏好 LLM 生成的內容
11. **因果推理飛躍**：從觀察性數據直接得出因果結論
12. **邏輯斷裂靜默通過**：引用正確、數字正確，但推理邏輯是斷的
13. **跨章節不一致**：Abstract 的數字和 Results 不同、Methods 描述的分析在 Results 中消失
14. **引用倫理盲區**：過度自我引用、citation ring、選擇性忽略競爭性文獻
15. **無證據判定**：AI evaluator 自己也可能幻覺出「問題」——沒有原文證據的判定不應產生

本 skill 的每個 gate 都針對上述至少一個失敗模式設計。
其中第 8-10 項由 subagent 隔離架構解決（見 `references/subagent-evaluation.md`）。
第 5、11、12 項由 Logic Fallacy Chain 橫切模組解決（見 `references/logic-fallacy-chain.md`）。
第 13 項由 Cross-Section Consistency 解決（見 `references/issue-schema.md`）。
第 14 項由 Citation Ethics 解決（見 `references/issue-schema.md`）。
第 15 項由 Anti-Hallucination Grounding 解決（見 `references/issue-schema.md`）。

---

## 整合指引

### 作為 Agent Pipeline 的中間層

```
[Research Agent] → [Research Guardian Skill] → [Output]
                         │
                    每個 gate 可回傳：
                    - PASS：繼續
                    - FAIL + reason：退回修正
                    - WARN + detail：通過但標記
```

### 與現有工具整合

- **Web Search**：Literature Guard 會主動調用搜索來驗證引用是否存在
- **Code Execution**：Experiment Guard 可執行統計驗算腳本
- **File Creation**：Writing Guard 可輸出帶標記的最終文件

### Pipeline Runner（`scripts/runner.py`）

Python 腳本管理整個 pipeline 的生命週期：

```bash
python ${CLAUDE_SKILL_DIR}/scripts/runner.py review paper.txt                 # Auto mode
python ${CLAUDE_SKILL_DIR}/scripts/runner.py review paper.txt --mode full      # Full mode
python ${CLAUDE_SKILL_DIR}/scripts/runner.py review paper.txt --preset ml      # ML preset
python ${CLAUDE_SKILL_DIR}/scripts/runner.py resume                            # 從中斷處恢復
python ${CLAUDE_SKILL_DIR}/scripts/runner.py status                            # 查看進度
python ${CLAUDE_SKILL_DIR}/scripts/runner.py dashboard                         # 產生 HTML 儀表板
```

**Checkpoint / Resume 機制**：
- 每完成一個 gate → 自動寫入 `/tmp/research-guardian/checkpoints/`
- 如果 pipeline 中斷（crash、timeout、Ctrl+C）→ checkpoint 保留
- `resume` 指令從最後一個 checkpoint 繼續，已完成的 gate 不重跑
- 自動升級也有 checkpoint（QUICK → STANDARD → FULL 的每一步都記錄）

**輸出位置**：
```
/tmp/research-guardian/
├── checkpoints/          ← 進度 checkpoint（JSON）
│   └── run-YYYYMMDD-HHMMSS-xxxx.checkpoint.json
└── output/
    ├── json/             ← 機器可讀報告
    ├── markdown/         ← 人類可讀報告
    ├── html/             ← HTML 報告
    └── dashboard.html    ← 互動式儀表板
```

### JSON Schema（`schemas/guardian.schema.json`）

定義所有資料結構：Issue、GateResult、Scorecard、RedFlag、RejectionRisk、
PipelineCheckpoint、ReviewReport。所有 gate 的輸出都必須符合此 schema。

### 最小可用配置

如果只能啟用一個 gate，優先啟用 **Literature Guard**（引用驗證），
因為幻覺引用是目前 AI 研究中最常見且最容易被發現的錯誤。

### 擴充系統

需要新增領域（如物理學、法學）、新的研究設計類型、新的統計框架、
新的審稿人 persona、或新的 preset？見 `references/extensibility-guide.md`。
每種擴充有標準模板、命名規範、註冊步驟、和必要的回歸測試要求。
新增 domain sub-module 只需建 1-3 個檔案 + 在 parent 文件中註冊。
新增 Gate 是重量級變更，需要修改 8 個檔案——大多數情況下用 sub-module 或 logic layer 就夠了。

---

## 指令介面

| 指令 | 說明 |
|------|------|
| `/review` | 審查單篇研究輸出（自動選擇 Quick Mode）|
| `/review --mode full` | 完整審查（所有 gate + logic chain）|
| `/review --persona all` | 用 5 種審稿人 persona 模擬審查 |
| `/review --persona statistician` | 用特定 persona 審查 |
| `/review --diff v1 v2` | 比較兩個版本的差異 |
| `/batch-review` | 批次審查多篇研究 |
| `/audit` | 嚴格造假偵測模式 |
| `/compare` | 比較多篇論文並排名 |
| `/risk` | 只算 rejection risk score |
| `/fix` | 對已找到的 issues 生成修正範例 |

---

## 超越功能（OpenReviewer 沒有的）

本 skill 在覆蓋 OpenReviewer 所有功能的基礎上，提供以下獨有能力：

### 推理層
- **Logic Fallacy Chain（5 層推理驗證）**：不只查素材，查推理本身
- **結構性 Overclaim 偵測**：超越信號詞匹配，用 4 種結構性 pattern 偵測偽裝的 overclaim

### 品質保障層
- **Subagent 隔離 + Anti Context Rot**：防止 evaluator 自身的判斷退化
- **30 案例驗證 + 25 patches**：每個 checklist 項目都經過實證測試
- **Performance Metrics 自我監控**：系統追蹤自己的攔截率和精確率

### 效能層
- **Quick Modes（🟢🟡🔴）**：分級效能，不是每次都全開
- **平行執行**：FULL mode 3.4x 加速
- **場景化 Preset**：ML/臨床/社科/SR/提案 自動配置

### 覆蓋層
- **Domain Sub-modules**：biomedical、CS/ML、social science、qualitative 各有專屬 checklist
- **多語言 Overclaim**：中/日/韓/西 信號詞偵測
- **質性研究支持**：飽和、編碼嚴謹性、可信度四標準

### 超越層（獨有）
- **Reviewer Persona Simulation**：模擬 5 種審稿人（統計學家、領域專家、方法論者、懷疑論者、建設性導師）
- **Counter-Argument Generation**：預生成審稿人質疑 + 建議回應 + 預防性修正
- **Version Diff**：兩版論文差異分析，追蹤改善程度
- **Rejection Risk Score**：量化被拒風險 + 改進優先級（ROI 排序）
- **Fix Examples**：不只說「改這裡」，給出修正前/後的範例文字

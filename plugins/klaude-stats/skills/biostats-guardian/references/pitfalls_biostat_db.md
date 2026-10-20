# Pitfalls — Biostat 資料庫錯題本（跨資料庫共用）

Reflexion 風格的「錯題本」：每次跑某個臨床／生統資料庫的統計分析、踩到坑就 append 一行。Guardian 的 **Semantic Column Reviewer**（以及 drift 時的 Code Auditor、post 階段的 Results Auditor）在啟動前要先 Read 本檔對應小節，把已知陷阱當 ground-truth 比對 config / data dictionary。本檔的 pitfall 多屬「欄位存在但意思不對」（COL-012）這一類——確定性 precheck 抓不到，是保留 LLM 稽核的主要理由。

本檔以**資料庫**為單位分節，每新增一個資料庫就新增 `## <DB_NAME>` 章節。目前收錄：HF（heart failure）、TTM（targeted temperature management），未來其他資料庫（cohort、registry、跨領域 dataset）皆可直接擴充。

**檔案性質**：reference data，不是 @import，不會自動進 context。觸發 Read 的訊號（每個資料庫小節最上方記錄自己的訊號）：
- `research_plan.json$.dataset` 含有資料庫標記（例：`hf_db`、`ttm_db`、未來新增的標記）
- cwd 路徑 / data file 名稱 match 該資料庫的 keyword regex
- 使用者明確指名某資料庫

新增資料庫時，把該 DB 的 keyword regex / `dataset` 標記字串寫進該章節最上方，方便 guardian subagent 對齊偵測規則。

**何時 append**：
- 分析跑完發現某變數 coding 不直觀（missing 用特殊值、單位混用、follow-up 規則隱晦）
- Reviewer 來信指出某資料庫 quirk
- Sensitivity analysis 揭露某假設不成立
- 任何「下次新人別再踩」等級的教訓

**Append 格式**：每條獨立小節，用日期 + 一句話標題 + 細節。

---

## HF 資料庫（Heart Failure）

**偵測訊號**：`research_plan.json$.dataset = "hf_db"`；cwd / data path regex `(?i)(heart.?failure|hf[_-]?db)`。

<!-- TODO: 第一次踩坑時填入。模板如下 -->

### YYYY-MM-DD · EF coding 是百分比還是小數
- **症狀**：descriptive 看到 EF mean = 0.42（應該是 42%）
- **根因**：raw data EF column 用小數，data dictionary 沒明寫
- **修法**：cleansed CSV 統一改百分比，並在 `data_dictionary.csv` 註記「EF: percent (0-100), not fraction」
- **教訓**：每個百分比變數第一次跑 Table 1 都要看 mean range — 是否 ∈ [0, 1] 還是 [0, 100]
- **影響範圍**：Cox model 用 EF 當 covariate 時 HR 會差 100 倍

### YYYY-MM-DD · NYHA class 用 1-4 還是 I-IV
- 留 placeholder

### YYYY-MM-DD · BNP / NT-proBNP 混用
- 留 placeholder

### YYYY-MM-DD · Follow-up 失聯算 censoring 還是 LOST
- 留 placeholder

---

## TTM 資料庫（Targeted Temperature Management）

**偵測訊號**：`research_plan.json$.dataset = "ttm_db"`；cwd / data path regex `(?i)(ttm|targeted.?temperature|cooling)`。

### YYYY-MM-DD · Cooling onset time 起點
- **症狀**：cooling duration median 看起來不合理
- **根因**：`cooling_start` 起點欄位有兩種 — 部分病人從 ROSC（return of spontaneous circulation）算、部分從抵急診算
- **修法**：統一用 ROSC 為起點；無 ROSC time 的病人記為 missing 而非用入院時間填補
- **教訓**：時間欄位先看 distribution + check 上下游欄位（`rosc_time`, `ed_arrival_time`）是否合理 ordering
- **影響範圍**：door-to-cooling 這類 KPI 全部要重算

### YYYY-MM-DD · Rewarming 過快算 cooling 失敗嗎
- 留 placeholder

### YYYY-MM-DD · Target temperature 33°C vs 36°C 群組
- 留 placeholder

### YYYY-MM-DD · Neurological outcome（CPC score）的 dichotomy
- 留 placeholder（CPC 1-2 vs 3-5 還是 CPC 1-3 vs 4-5？）

---

## 通用陷阱（適用任何臨床／生統資料庫）

### Censoring 規則必須先 sign-off
- 死亡、心臟移植、LVAD、失聯、研究結束 — 哪些算 event、哪些算 censoring？
- competing event（例如：non-cardiac death 對 cardiac death）要走 CIF 不能 KM
- 在 `research_plan.json$.pipeline[*].censoring_rule` 寫死，跑分析前 contract sign-off

### Date 欄位的 timezone 與 dtype
- Excel 跨平台讀進來常變成 string；R / Python 解析方式不同
- 第一步 raw-data-processing 要 force parse + check distribution

### Categorical 變數的 reference level
- pandas 預設用字母序、R `factor()` 也用字母序 — 兩邊容易不一致
- Cox 跑出來 HR 方向相反就是這個 — 在 config 顯式宣告 `reference_level`

---

## 怎麼用本檔

1. **Guardian subagent（Semantic Column Reviewer / drift-only Code Auditor / Results Auditor）**：在 prompt 裡加 `先 Read ${CLAUDE_SKILL_DIR}/references/pitfalls_biostat_db.md 對應資料庫小節，把每條 pitfall 當 check item 比對 config / data dictionary`
2. **手動觸發**：跑新分析前 `Read` 本檔當 review checklist
3. **Append**：每次踩坑後 30 分鐘內補一條 — 越新鮮細節越完整

---

## Changelog

- 2026-04-28 · 建檔（synthesized from 李宏毅 lec 5 self-correction Reflexion pattern）

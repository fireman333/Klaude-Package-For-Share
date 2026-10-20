---
name: oe-map
description: |
  印出 OpenEvidence 相關 skill（openevidence / medq / oe-triangulate）的 cheat sheet：分工總表、決策樹、prompting pattern 總覽、安裝指引。Trigger: `/oe-map`、`/oe-help`、使用者提及「OE 怎麼用」「OE 我有哪些 skill」「OE 生態」「OE cheat sheet」等意圖時。
---

# OE Map — OpenEvidence skill 懶人包

觸發時，**原樣**把下面的 Cheat Sheet 貼給使用者（不改寫、不加長篇解釋）。最後補一行：`> 安裝 OpenEvidence MCP：見 ${CLAUDE_SKILL_DIR}/../openevidence/SETUP.md；prompting pattern 細節見 ${CLAUDE_SKILL_DIR}/../openevidence/SKILL.md「提問模式升級」。`

若使用者追問安裝 → 讀 `${CLAUDE_SKILL_DIR}/../openevidence/SETUP.md` 回答。

## Cheat Sheet

### 先決條件

OpenEvidence 這幾個 skill 需要自行安裝的 OpenEvidence MCP（非官方、社群專案）。沒裝時：`/medq` 會降級成 PubMed 驗證、`/oe-triangulate` 會降級成 PubMed 單路、`/openevidence` 會提示安裝。

### 怎麼選

| 情境 | 用哪個 | 一句話理由 |
|------|-------|-----------|
| 純 evidence 查詢（國考、臨床查詢） | **`/openevidence`**（`/oe`） | 單次、低成本，回 OE 原文整理 |
| 即時臨床 / 手術 / 統計問答，要 inline citation | **`/medq`** | Claude 先獨立草擬 → OE 驗證 → 單一整合回覆 |
| 重大決策 / 寫 paper / 懷疑 OE 有偏誤 / 想找 OE 沒讀到的新證據 | **`/oe-triangulate`** | OE 正問 + OE 反問 + PubMed 直搜，三路比對 |
| 驗證某個 OE 答案的 citation 是否真實、有無誤歸因 | 上游 `audit-oe`（選用，`npx skills add htlin222/audit-oe-skill`） | 逐條引用稽核；本外掛不內建 |

### 使用者講這些話 → 路由

| 關鍵字 | 路由 |
|--------|------|
| 「查 OE」「問 OE」「OE 幫我查」 | `/openevidence` |
| 「幫我查一下 XXX first-line」（要 citation） | `/medq` |
| 「正反都要」「OE 有沒有盲區」「三角驗證」 | `/oe-triangulate` |
| 「OE 怎麼用」「OE 有哪些 skill」 | `/oe-map`（本表） |

### 4 種 prompting pattern（何時用）

| Pattern | 做法 | 用在 |
|---------|------|------|
| **1 雙向對稱** | 同一題問「支持 benefit 的證據」+「null / negative 的證據」+「兩者衝突在哪」 | 是非向決策題（某藥有沒有效） |
| **2 Endpoint grid** | 要求輸出各 trial × 各 endpoint 的 HR (95% CI) 表格 | 要把 HR/CI 引進 paper、避免數字打架 |
| **3 原文強制** | 「只引 primary source，不引 review」 | meta-analysis / pooled 結果追溯來源 |
| **4 時間切片** | 依 2019–21 / 22–23 / 24–26 分段列代表文獻 | 怕 OE 吃不到新證據 |

單純概念釐清 / 機轉 / 國考複習：不套任何 pattern，直接問。

### 高風險任務的堆疊用法

寫 paper、倫理報告、重大臨床決策：`/medq` 或 `/openevidence` 建立背景 → 只對「會決定論證方向」的 1–2 個核心 claim 升級 `/oe-triangulate` → 最後對引用最敏感的答案做 citation 稽核（選用 audit-oe）。不要每題都三層全開。

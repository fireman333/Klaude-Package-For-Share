---
name: notebooklm-deep-research
version: "1.0.0"
description: >
  Automate deep research using NotebookLM notebooks combined with web search.
  This skill queries a NotebookLM notebook with structured questions, supplements
  with web research, synthesizes all findings into a comprehensive note, and saves
  it back to the notebook.
  Use this skill whenever the user mentions: deep research, deep dive, NotebookLM research,
  research a topic, 深度研究, 幫我研究, 幫我深入研究, 用NotebookLM研究, 深入了解,
  幫我查資料整理到NotebookLM, research into notebook, 幫我用筆記本研究,
  NotebookLM查資料, 深度調查, 幫我整理資料, deep dive into notebook.
---

# NotebookLM Deep Research

（選用：需要已安裝並登入 NotebookLM MCP server——`mcp__notebooklm__*` 工具；若這些工具不存在，請先告知使用者安裝，不要繞路。）

自動化深度研究流程：從 NotebookLM 筆記本提取現有知識 → 網路研究補充 → 統整合成 → 存回筆記本。

## When to Use

- 用戶想針對某個主題做深入研究，且有相關的 NotebookLM 筆記本
- 用戶想整合筆記本內容與最新網路資訊
- 用戶想將研究結果系統化地保存回筆記本

## Workflow

### Step 1: 選擇筆記本與確認研究主題

1. 呼叫 `mcp__notebooklm__notebook_list` 列出所有筆記本
2. 請用戶選擇目標筆記本（或根據上下文自動判斷）
3. 確認具體的研究問題或主題
4. 記錄 `notebook_id` 和 `research_topic`

如果用戶已在對話中提到筆記本名稱，直接比對並確認。

### Step 2: 偵察現有知識

**平行呼叫**以下三個 MCP 工具：
- `mcp__notebooklm__notebook_describe(notebook_id)` — 取得筆記本所有來源的 AI 摘要
- `mcp__notebooklm__notebook_get(notebook_id)` — 查看筆記本詳情（含已載入的 sources 清單）
- `mcp__notebooklm__note(action="list", notebook_id=...)` — 查看現有筆記

向用戶簡報：「您的筆記本包含 X 份來源和 Y 則筆記，涵蓋 [主題]。我將針對 [研究主題] 進行深度研究，補充不足之處。」

### Step 3: 結構化筆記本提問

根據研究主題，自動生成 4-6 個針對性問題，使用 `mcp__notebooklm__notebook_query` 逐一提問。

**問題類別（依主題調整）：**
1. **基礎定義與範圍** — 「請詳細說明 [主題] 的定義、範圍和分類」
2. **現有證據與關鍵發現** — 「根據來源資料，[主題] 的主要研究發現和證據有哪些？」
3. **機制與方法論** — 「[主題] 的運作機制或方法論細節為何？」
4. **爭議與限制** — 「[主題] 目前有哪些爭議、限制或未解決的問題？」
5. **臨床/實務意涵** — 「[主題] 對臨床實務或實際應用有什麼影響？」
6. **替代方案比較** — 「與其他替代方案相比，[主題] 的優缺點為何？」（若適用）

**重要：** 使用第一次 `notebook_query` 回傳的 `conversation_id` 進行後續追問，以維持對話上下文。

每個問題都應具體、有針對性，避免過於寬泛的提問。根據每次回答的深度，決定是否需要追問。

### Step 4: 網路研究補充

根據 Step 3 中發現的知識缺口，執行 3-5 次 `WebSearch`。

**搜尋策略：**
- 補充筆記本來源未涵蓋的最新資訊
- 搜尋最新指引、共識聲明、meta-analysis
- 尋找量化數據（盛行率、效應量、統計數據）
- 探索相反觀點或最新爭議

**搜尋語言：** 同時使用英文和繁體中文搜尋，以獲得更全面的結果。

每次搜尋後，記錄找到的關鍵資訊和來源 URL。

### Step 5: 統整合成

將 Step 3 和 Step 4 的所有資訊整合為結構化的研究筆記。

使用 `<SKILL_PATH>/references/research_note_template.md` 中的模板格式：

```markdown
# [研究主題] — 深度研究摘要

**日期**: YYYY-MM-DD
**來源**: NotebookLM 筆記本「[名稱]」+ 網路研究

## 重點摘要
（2-3 句總結）

## 筆記本來源的關鍵發現
（按主題分類，標註來源）

## 網路研究補充
（額外發現，附 URL 引用）

## 證據統整
（整合兩方來源的綜合分析）

## 知識缺口與未來方向
（尚未解答或需進一步研究的問題）

## 參考資料
（NotebookLM 來源 + 網路 URL）
```

### Step 6: 儲存至 NotebookLM

呼叫 `mcp__notebooklm__note`（action=create）：
- `action`: `"create"`
- `notebook_id`: 目標筆記本
- `title`: `Deep Research: [主題] ([日期])`
- `content`: Step 5 產生的完整 markdown 內容

向用戶確認筆記已成功儲存。

### Step 7: 呈現結果與後續建議

向用戶展示統整後的研究結果，並提供後續選項：

- 「要不要針對某個子主題做更深入的研究？」
- 「要不要用這些研究結果製作簡報？」（觸發 notebooklm-pptx skill）
- 「要不要搜尋 PubMed 找原始文獻？」（觸發 pubmed-search skill）
- 「要不要用這些資料撰寫 IRB 計畫？」（觸發 irb-plan-helper skill）

## Notes

- 問題數量和搜尋次數應根據主題的複雜度動態調整
- 如果筆記本來源內容稀少（回答簡短或含糊），應增加網路研究的比重
- 所有輸出使用繁體中文，除非用戶指定其他語言
- 醫學術語保留英文原文並附中文翻譯

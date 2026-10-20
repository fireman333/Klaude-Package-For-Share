---
name: oe-triangulate
description: |
  三角驗證工作流。對同一臨床問題並行跑三路查詢：(1) OpenEvidence 正問、(2) OpenEvidence 反問（negative query reflex，套 openevidence skill 的 Pattern 1 語法）、(3) PubMed 近 2 年 direct search。輸出 citation overlap、OE-only 盲點（H-index bias 推論）、PubMed-only 盲點（OE retrieval 未包含的新證據）、以及 claim-level 數字矛盾。用在 paper 寫作、重大臨床決策、教授會議前 evidence synthesis。底層依賴：openevidence MCP（需自行安裝，見 openevidence/SETUP.md）、pubmed MCP；缺 OE 時降級為 PubMed 單路。Trigger: `/oe-triangulate`、`/三角`、使用者提及「幫我三角驗證 XX」「OE + PubMed 交叉驗證」「正反面證據都要」「幫我看 OE 有沒有盲區」「重大決策 evidence synthesis」等意圖時。
---

# OE Triangulate — 三角驗證工作流

## 使用情境

| 情境 | 適用 | 原因 |
|------|------|------|
| RA paper discussion / introduction 前 | ✅ 強烈建議 | 引用數字前要確認沒有 retrieval 盲區 |
| 重大臨床決策（mortality-affecting） | ✅ 強烈建議 | 單問 OE 有方向性不對稱 |
| 教授會議 evidence synthesis | ✅ 建議 | 被追問 primary source 要答得出來 |
| 懷疑 OE 答案 stale / biased | ✅ 建議 | 對稱反問 + 時間 filter 能暴露盲區 |
| 國考複習 / 概念釐清 / 機轉 | ❌ 不需要 | 共識層級題目不需三角驗證，直接 `/oe` |
| 快速臨床查詢 | ❌ 不需要 | 成本不划算（3+ queries） |

## 三角驗證解決什麼問題

OE 的 retrieval 有兩個結構性缺陷（社群使用者分析）：

1. **Embedding search 不分 primary vs. secondary citation** → transitive citation
2. **H-index ranking 偏好老 positive 資料** → retrieval 對問法方向性敏感

實測：`empagliflozin HFpEF mortality benefit` 正問得 4 citations（偏 null），反問得 15 citations（補出 pooled MA + subgroup + post-2023 證據），同一臨床事實因問法不同結論偏移。

本 skill 用三路並行破此 bias：
- **OE 正問** ↔ **OE 反問**：觸發 retrieval 的 symmetry
- **PubMed direct search**：繞過 OE retrieval 池、直接命中 indexed papers
- **Diff**：找出三路的 overlap / gap / conflict

## 前置需求

- `openevidence` MCP 已安裝並認證（安裝：`${CLAUDE_SKILL_DIR}/../openevidence/SETUP.md`）（`mcp__openevidence__oe_auth_status`）
- `pubmed` MCP 可用（NCBI API key 建議配置，環境變數 `NCBI_API_KEY`）
- `${CLAUDE_SKILL_DIR}/../openevidence/scripts/parse_oe.py` 可執行
- `${CLAUDE_SKILL_DIR}/../openevidence/scripts/unify_artifacts.py` 可執行（建議：positive + negative artifactDir 一起跑可拿到 unified references + orphan recovery）
- `${CLAUDE_SKILL_DIR}/scripts/compare_citations.py` 可執行

> **⚠️ Orphan citation 注意**：OE 的 `answer.md` 用 span-order sequential 編號（含 re-cite），`N > len(citations.json)` 的 inline `[N]` **是同一篇 paper 重複引用、不是 orphan**。若 `compare_citations.py` 直接 strip 超界 [N]，positive vs negative overlap 比對會失真（漏掉真實 cite）。建議先用 `unify_artifacts.py <positive_artifactDir> <negative_artifactDir>` 把兩邊 artifact 一起餵進去，產 unified references + orphan-recovered inline map，再做 overlap analysis。詳見 OE SKILL.md「Artifacts 路徑」section。

## Workflow

### Stage 0：題目 refinement

若使用者題目太籠統（缺 population / intervention / outcome / time scope），用 `AskUserQuestion` 補齊。

**最小資訊**：
- Population（哪種病人？）
- Intervention / exposure（什麼藥 / 什麼介入？）
- Outcome（想看什麼結局？mortality / event / quality of life？）
- Time scope（近 2 年夠嗎？還是要全歷史？預設近 2 年）

**題目若已足夠明確**（例如「empagliflozin 對 HFpEF 的 mortality benefit」），直接進 Stage 1 不打擾使用者。

### Stage 1：並行三路查詢

**在同一則訊息內**並行呼叫三個 tool call，讓 MCP 同時 fetch：

1. **OE 正問**（Pattern 1 基礎版 — 直接問）：
   ```
   mcp__openevidence__oe_ask({
     question: "<原問題，英文化>",
     include_bibtex: true,
     crossref_validate: true,
     save_artifacts: true,
     timeout_sec: 180
   })
   ```

2. **OE 反問**（negative reflex，套 openevidence Pattern 1 反向語法）：
   ```
   mcp__openevidence__oe_ask({
     question: "Is there any positive evidence—including subgroup analyses, post-hoc analyses, pooled meta-analyses, or newer trials—that supports <intervention> producing <opposite outcome> in <population>? List specific positive findings, favorable subgroups, and any trial/MA showing the reverse direction.",
     include_bibtex: true,
     crossref_validate: true,
     save_artifacts: true,
     timeout_sec: 180
   })
   ```
   （「反問」定義 = 對正問的預期答案做否定。若正問預期 null，反問就找 positive；若正問預期 positive，反問就找 null 或反向。）

3. **PubMed direct search**（近 2 年 filter）：
   ```
   mcp__pubmed__pubmed_search_articles({
     term: "<intervention> AND <population> AND <outcome>",
     date_filter: "2024:2026[PDAT]",  # 或使用者指定的 time scope
     max_results: 30
   })
   ```

### Stage 2：Parse & normalize

- **OE**：兩個 OE 回傳都會因體積過大被存成 `.txt`。收集檔案路徑，批次跑：
  ```bash
  python3 ${CLAUDE_SKILL_DIR}/../openevidence/scripts/parse_oe.py <positive_txt>
  python3 ${CLAUDE_SKILL_DIR}/../openevidence/scripts/parse_oe.py <negative_txt>
  ```
- **PubMed**：取 pubmed_search_articles 結果的 PMID list，必要時用 `mcp__pubmed__pubmed_fetch_articles` 拿 metadata（title / year / abstract snippet）。

### Stage 3：Compare citations（關鍵自動化步驟）

呼叫 compare script，把三路 citation 清單 diff：

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/compare_citations.py \
  --positive <path_to_oe_positive_citations.json> \
  --negative <path_to_oe_negative_citations.json> \
  --pubmed <path_to_pubmed_results.json> \
  --out <output_dir>/comparison.md
```

Script 輸出 `comparison.md`，包含：
- **Shared citations**（三路皆引）→ consensus core
- **OE-positive-only**（只正問 OE 引）→ 原問題 retrieval 的主要 papers
- **OE-negative-only**（只反問 OE 引）→ 補 retrieval 盲區的 papers
- **PubMed-only**（只 PubMed 搜出）→ OE retrieval 池沒 index 到的 papers（**最有價值**，通常是近期或 regional study）
- **時間分佈**：每桶的年份 histogram

### Stage 4：Claim-level conflict detection（LLM 做）

讀正問 / 反問兩份 parse 過的 answer 文字，找：

1. **同一 outcome 的 HR/OR 數字差異 > 20%** → flag
2. **方向性衝突**（正問說 null、反問說 significant） → flag
3. **時間分佈盲區**：如果 PubMed-only 桶有 ≥ 3 篇近 2 年 paper 而 OE 兩側都沒引，flag 為 **stale retrieval**

**⚠️ Pre-verdict sanity check（務必先跑）**：

`shared_all = 0` 不一定是 DIVERGENT，很可能只是 **date filter artifact**：

- 若 OE 兩側引用的 landmark trial 發表年份 **早於 PubMed date filter 起點**（例如 EMPEROR-Preserved 2021 / DELIVER 2022，但 PubMed 只搜 2024–2026），這些 paper 永遠不可能出現在 PubMed bucket，`shared_all` 自然歸零。
- 判定順序：
  1. 檢查 `oe_both` 桶裡的 paper year 是否都 < PubMed date window 起點
  2. 若是 → `shared_all = 0` 是 artifact，**不算 DIVERGENT**，改看 `oe_both` 內容是否穩固、`pubmed_only` 是否有新證據
  3. 若 `oe_both` paper year 落在 PubMed window 內卻還是沒進 `shared_all` → 才是真的 retrieval disagreement
- 若想補齊核心重疊，重跑 PubMed 時把 date filter 拉寬或關掉（保留 sort-by-date），再跑一次 compare。

Claude 讀 comparison.md + 兩份 parse 過的 OE 答案，生成 `verdict.md` 做總結：

```markdown
# Triangulation Verdict

## Overall: {CONSENSUS | DIVERGENT | STALE}

- CONSENSUS: 三路結論一致、citation overlap > 50%
- DIVERGENT: 正反 OE 結論矛盾，或 citation overlap < 30%（**先排除 date filter artifact**）
- STALE: PubMed-only 有 ≥3 篇近 2 年 paper 未被 OE 引用

## Key findings
...

## Recommended follow-up
- 要用哪幾篇 primary source 當真正的寫作依據？
- 要不要進一步逐條稽核某個 citation（選用上游 `audit-oe`）？
```

### Stage 5：輸出

**目錄結構**：
```
triangulate-{topic-slug}/
  positive.md              # OE 正問 parse 過的 clean answer
  negative.md              # OE 反問 parse 過的 clean answer
  pubmed.md                # PubMed 搜尋結果摘要
  comparison.md            # Stage 3 script 輸出
  verdict.md               # Stage 4 LLM 總結（overall + key findings + follow-up）
  assets/
    positive-citations.json   # OE 正問原始 citations
    negative-citations.json   # OE 反問原始 citations
    pubmed-results.json       # PubMed 原始 response
```

**對使用者回報**：
- 一句話 verdict（CONSENSUS / DIVERGENT / STALE）
- 最重要 3 個 follow-up actions
- 完整資料路徑

## 錯誤處理

| 狀況 | 處理 |
|------|------|
| OE MCP 未安裝 / 未認證 | 不中止：降級為 PubMed 單路（失去正反 OE 對照），明確標示「降級模式：未使用 OpenEvidence」；並指引 SETUP.md |
| OE timeout | 重試 1 次，timeout_sec 拉到 300；仍失敗 → 降級為單側 OE + PubMed 兩路比對，標示「降級模式」 |
| PubMed MCP 不可用 | 降級為 OE 雙向比對（失去 PubMed-only 桶），標示「降級模式」 |
| compare_citations.py 找不到 DOI / PMID key | 降級為 title fuzzy match（>85% similarity），回報 match 信心 |
| 反問 question 產生不出合理語意 | 呼叫 AskUserQuestion 請使用者確認反向方向 |

## 與其他 skills 的關係

| Skill | 關係 | 何時用 vs. 用 oe-triangulate |
|-------|------|-----------------------------|
| `openevidence` | 上游單次查詢 | 快速問答用 `/oe`；要 evidence synthesis 用 `/oe-triangulate` |
| `audit-oe`（選用，`npx skills add htlin222/audit-oe-skill`） | 下游 citation 驗證 | `/oe-triangulate` 找 retrieval 盲區；audit-oe 驗 citation 正確性。**互補** |
| `deep-research` | 平行工具（不用 OE） | 純文獻回顧 / 大範圍 scope 用 deep-research；聚焦單一 clinical question 用 oe-triangulate |

## 成本預估

- 2× OE 查詢（約 30–120 秒 × 2）
- 1× PubMed search + 若干 fetch
- 1× compare script（<5 秒）
- 1× Claude LLM summarize（verdict.md）

**總時間**：約 2–4 分鐘
**Token cost**：約 2–3× 單次 `/oe`

## 注意事項

- **反問 question 的生成**：由 Claude 根據正問自動生成對稱反問。例：
  - 正問「X 有 Y benefit？」→ 反問「有哪些 evidence 顯示 X 沒有 Y benefit / 有反向 effect？」
  - 正問「guideline 建議 A」→ 反問「有哪些反對 A 的 evidence 或 alternative?」
- **PubMed 搜尋 term 的構造**：用 MeSH + title/abstract keyword 組合，避免太窄。
- **Time scope 預設 2024–2026**：這是 OE retrieval 池 stale-data 最常見的盲區。若使用者明確要全歷史，可關掉 date filter 但保留 sort-by-date。
- **落地檔案位置**：預設 `./triangulate-{slug}/`（current working dir）。若 cwd 是家目錄或系統位置，改到 `./triangulate-{slug}/`（新建子資料夾）避免污染。

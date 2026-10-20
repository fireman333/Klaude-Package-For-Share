---
name: openevidence
description: "透過 OpenEvidence MCP 查詢 AI 醫學文獻（需自行安裝 OpenEvidence MCP，見 SETUP.md）。支援臨床問題查詢、查看歷史查詢、取得特定文章。觸發關鍵詞：/oe、/openevidence、查 openevidence、查 OE、問 OE、查找 AI 文獻、OE 查詢、ask openevidence、oe search、查實證、查 evidence、AI 文獻查詢、幫我問 OE、OE 幫我查。即使使用者只說「幫我查一下 febrile neutropenia 的治療」或「OE 這個藥怎麼用」也應觸發。"
---

# OpenEvidence 醫學文獻查詢

透過 OpenEvidence MCP 工具查詢 AI 輔助的實證醫學文獻，回傳帶引用的臨床回答。

> **前置**：需要自行安裝 OpenEvidence MCP server（非本外掛內建、也不是官方 API）。安裝與登入步驟見 `${CLAUDE_SKILL_DIR}/SETUP.md`。**若 `mcp__openevidence__*` 工具不存在**：直接告訴使用者「尚未安裝 OpenEvidence MCP」並指向 SETUP.md；臨床問題的替代路徑是 PubMed MCP（`pubmed-search` skill）或網路搜尋，不要假裝查過 OE。

## 可用工具

| 工具 | 功能 |
|------|------|
| `mcp__openevidence__oe_ask` | 提問臨床問題，取得帶引用的回答 |
| `mcp__openevidence__oe_history_list` | 查看歷史查詢紀錄（可搜尋） |
| `mcp__openevidence__oe_article_get` | 用 article_id 取得特定文章完整內容 |
| `mcp__openevidence__oe_auth_status` | 檢查認證狀態 |

## Workflow

### 情境 A：使用者提出臨床問題（最常見）

1. **確認認證**：呼叫 `mcp__openevidence__oe_auth_status`。若未認證，告知使用者需先登入 OpenEvidence。

2. **組織查詢**：將使用者的問題轉為英文臨床查詢（OE 以英文回答品質最佳）。
   - 問題模糊時可直接用合理臨床措辭查詢，不需反問
   - 有明確子問題（劑量、禁忌、比較）時整合為一個完整查詢

3. **發送查詢**：呼叫 `mcp__openevidence__oe_ask`，`question` 填英文，其餘參數用預設值。

4. **解析回應（⚠️ 永遠走檔案 + parse_oe.py，不要嘗試直接讀 inline JSON）**：

   OE 回應是大型 JSON（經驗值 90K–170K chars），幾乎必然超過 MCP 單次回傳 token 上限。MCP 此時會自動將完整結果存成 `.txt` 檔並回傳錯誤訊息，內含檔案路徑（形如 `.../tool-results/mcp-openevidence-oe_ask-*.txt`）。這是**預期行為、不是錯誤**。

   標準處理流程：
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/parse_oe.py <saved_file_path>
   ```

   腳本輸出：
   - 第一行 `ARTICLE_ID: <uuid>`（追問用）
   - 第二行 `BIBTEX: <path>`（**僅 v0.2.0+ 有 `artifacts.articlePath` 時出現**）— 指向 Crossref-augmented `citations.bib` 路徑，給 `manuscript-results` 等 downstream 流程直接用
   - 清理後的文章內容（HTML 保留，引用改為 AMA 編號 `[1,2]`）
   - 文末附編號 References 列表

   **重要規則**：
   - 即使 oe_ask 沒報錯而直接回傳 inline JSON（小機率），仍**不要**嘗試 Read / Grep / 逐行解析 inline JSON —— 把它存成 tmp 檔後用 parse_oe.py 處理
   - 批次多輪查詢時（如 skill 需要 3-4 輪並行），一次把所有 `.txt` 都 parse 完，再讀取乾淨輸出
   - 若腳本失敗，備用：`python3 -c "import json; d=json.load(open('<file>')); print(d['extracted_answer_raw'])"`

5. **整理輸出**：以繁體中文整理回答
   - 使用 markdown 表格、分層標題、粗體重點
   - **醫學名詞格式**：英文為主、首次出現附繁體中文（例：Crohn's disease（克隆氏症）），藥名寫學名，縮寫首次附全稱
   - 藥物劑量用表格呈現
   - 保留腳本已處理的 AMA 編號引用，文末附 References
   - 回答結構：標題 → 重點摘要 → 詳細內容（含表格）→ 特殊注意事項 → References

6. **Figure auto-detect + download（強制）**：每次 `oe_ask` 完成後檢查 `article.json` 有無 `REACTCOMPONENT!:!PublicationFigure`：
   - **有任何 figure** → 自動跑全量下載（不帶 `--match`，抓所有 figure 包含 NCCN / JAMA / PMC 等）：
     ```bash
     python3 ${CLAUDE_SKILL_DIR}/scripts/download_figures.py <artifactDir>
     ```
   - **NCCN recovery**：若 answer.md / references 提到 `NCCN` / `National Comprehensive Cancer Network` / `NCCN Guidelines` 但 `article.json` **沒有** `storage.googleapis.com/nccn_images/` URL → 用 `original_article_id` 發 follow-up `oe_ask`：
     ```
     Please include the NCCN guideline flowchart pages (e.g., EVAL-1, <cancer>-1 through <cancer>-N, and the appendix page) relevant to this question. Embed each flowchart as a publication figure with caption.
     ```
     follow-up artifact 到手後再跑一次 `download_figures.py`

7. **Figure surface + opt-in prompt（強制，有 figure 時跳過不得）**：step 6 若下載到任何 figure：
   - **必須**在使用者回應最後加小節「**📎 Figures downloaded**」，列表呈現（讀 `figures/figures.json`，只列 `status=ok`，dup 不列）：
     ```
     | # | Name | Caption（截斷 80 chars） | Source | Local path |
     ```
     NCCN 圖在 Source 欄標 `NCCN <cancer> v<ver>`（從 URL `/nccn_images/<cancer>/versions/<ver>/` 抽）；其他標 host name。
   - **必須**先開啟 figures 資料夾（macOS：`open <artifactDir>/figures/`；其他系統請告知路徑）讓使用者在 Quick Look 看過每張圖再決定去向；告知使用者「已開啟 Finder，用 Spacebar 預覽，看完回來選」
   - **必須**呼叫 `AskUserQuestion` 明確問使用者：「有 N 張 figure，要放進哪份輸出？」，options：
     - `pptx` — 本次 session 若已在做 pptx（如 `case-discussion-pptx`、`journal-club-discussion-pptx`）嵌入對應 slide
     - `docx` — 本次 session 若已在做 docx 嵌入
     - `markdown` — 寫進本次回答的 md file
     - `skip` — 只下載，保留 local path 使用者手動取用
   - 不得因為簡潔原則省略此詢問

### 情境 B：使用者想查歷史紀錄

1. 呼叫 `mcp__openevidence__oe_history_list`（可用 `search` 篩選，`limit` 預設 20）
2. 列出歷史查詢清單（日期 + 問題摘要）

### 情境 C：使用者想看特定文章

1. 需要 `article_id`（UUID 格式）
2. 呼叫 `mcp__openevidence__oe_article_get` 取得完整內容
3. 同情境 A 步驟 4-5（用 parse_oe.py 解析後整理輸出）

### 情境 D：追問（Follow-up）

針對同一主題追問時：
1. 呼叫 `mcp__openevidence__oe_ask`，帶上 `original_article_id`（從前次 script 輸出第一行取得）
2. OE 會將追問視為同一對話脈絡，回答更精確

## 提問模式升級（anti-retrieval-bias）

OE 的 retrieval 有兩個已知結構性缺陷（見 社群上的使用者分析）：
1. **Embedding search 無法區分 primary vs. secondary citation** → transitive citation
2. **H-index ranking 偏好老 positive 資料、吃不進新 negative trial** → retrieval 對問法方向性敏感

這代表**同一個臨床事實，用不同問法問會得到結構性不同的答案**（實測 4 vs 15 citations）。以下 4 個 prompting pattern 用來把 retrieval 盲區打開。**不是每次都套**，依題目性質決定：

### Pattern 1：對稱雙向問（dual-query，最推薦）

**觸發條件**：題目涉及「某藥對某 outcome 有沒有效」「某介入是否值得做」「某療法的 mortality benefit」這類**是非向的臨床決策題**。

**做法**：把單向問改成三段式 prompt

```
Regarding <drug> in <condition> for <outcome>:
1. What evidence supports NO significant benefit (null or negative trials)?
2. What evidence supports a benefit, including prespecified subgroups, post-hoc analyses, and pooled meta-analyses?
3. Where do these two bodies of evidence conflict, and what is the overall evidence synthesis?
```

**效果**：強迫 OE 同時拉正反兩邊 retrieval，補齊 H-index bias 的盲區。

### Pattern 2：Endpoint grid（最推薦）

**觸發條件**：題目涉及 RCT 比較、多個 outcome 對照、或要引用 HR/CI 數字到 paper / 報告。

**做法**：在 question 最後加強制表格指令

```
Present results as a markdown table:
| Outcome | <Trial A> HR (95% CI) | <Trial B> HR (95% CI) | Pooled HR (95% CI) | Primary source paper |

Include: primary composite, HF hospitalization (first event), HF hospitalization (total), CV death, all-cause mortality.
Use exact numerical values with both CI bounds. Cite the primary source for each cell (not review articles).
```

**效果**：強迫 OE 把數字並排對齊，split-brain 數字（同一 outcome 來自不同研究的 HR 不同卻被混用）會立刻暴露。

### Pattern 3：原文強制（anti-transitive，視題目使用）

**觸發條件**：題目跟 meta-analysis / pooled 結果有關、或要追溯原始數字來源。

**做法**：

```
Cite ONLY primary-source papers, not review articles or guidelines.
For each meta-analysis or pooled analysis mentioned, identify:
- Original authors, year, journal of first publication
- Exact trials included
Do not cite a review that summarizes the MA — cite the MA paper itself.
```

**效果**：把 source-type 拉進 prompt，讓 OE 避開 HIGH-risk 的 review corpus chunk。

### Pattern 4：時間切片（anti-stale，視題目使用）

**觸發條件**：題目涉及「最新證據」「recent evidence」「post-2024」或你懷疑 OE 不知道新 trial。

**做法**：

```
Break the evidence landscape down by publication window:
- 2019–2021: landmark RCT results
- 2022–2023: pooled meta-analyses and subgroup analyses
- 2024–2026: network meta-analyses, guideline updates, and new trials
For each window, cite the most representative paper with exact HR and CI.
```

**效果**：強迫 OE 按時間軸呈現 retrieval 池，暴露 stale-data 盲區。

### Pattern 選用決策樹

```
題目類型判斷：
├─ 是非向決策題（有沒有 benefit / 該不該用）
│  └─ 套 Pattern 1（雙向對稱問）
├─ RCT 比較 / 要引 HR 數字到 paper
│  └─ 套 Pattern 2（endpoint grid）
├─ MA / pooled 分析追溯原始來源
│  └─ 套 Pattern 3（原文強制）
├─ 新證據 / 最新指引
│  └─ 套 Pattern 4（時間切片）
└─ 單純概念釐清 / 機轉 / 國考複習
   └─ 不套任何 pattern，直接問
```

**同時套多個 pattern 可行**。例如 RA paper 寫作前的關鍵題目，可以 Pattern 1 + Pattern 2 同時用。

## 注意事項

- 若 MCP 工具未載入（deferred），先用 `ToolSearch` 載入：`query: "openevidence", max_results: 5`
- OE 回應時間約 30-120 秒，屬正常
- 若認證失敗，提示使用者在瀏覽器登入 OpenEvidence 後重試
- **批次並行查詢策略**：需要多輪查詢時（如 3-4 輪主題查詢），請**在同一則訊息內並行呼叫 `oe_ask`**；各自會被 MCP 存成不同 `.txt` 檔，拿到所有檔案路徑後再用一個 bash 迴圈批次 parse：
  ```bash
  for f in /path/to/tool-results/mcp-openevidence-oe_ask-*.txt; do
    python3 ${CLAUDE_SKILL_DIR}/scripts/parse_oe.py "$f" > "/tmp/$(basename "$f" .txt)_parsed.txt"
  done
  ```

## Artifacts 路徑（`save_artifacts=true`）— 多輪查詢整合

當呼叫 `oe_ask` 時帶 `save_artifacts=true, crossref_validate=true`（批次查詢與論文寫作流程建議開啟），MCP 會在每次 query 的 `artifactDir` 產出三個檔案：

| 檔案 | 內容 |
|------|------|
| `answer.md` | 已 HTML→markdown、inline 引用標成 `[N]` 的可讀文本 |
| `citations.json` | 該次 query 的 AMA 引用陣列（`[{key, citation, pmid, doi, ...}, ...]`）|
| `article.json` | OE 的 full response tree（含 `articlesection_set → articleparagraph_set → articlespan_set → citations[]`）|

做 multi-query 整合報告（多次 `oe_ask` 串成一份 docx / markdown）時，**必須**用全部三個檔案，不能只用 answer.md + citations.json。

### ⚠️ Orphan citation 陷阱（**必讀**）

OE 的 inline `[N]` 是 **span-order sequential 編號**，**包含同一 paper 的重複引用**。例如 `citations.json` 只有 14 筆，但 `answer.md` 可能出現 `[25]`、`[26]`、`[28]` — 這些**不是 orphan**，而是某篇 paper 的第 25 / 26 / 28 次出現（先前已被 `[8]` 或 `[12]` 引用過）。

**錯誤做法**（曾造成 2026-04-23 session 的 citation loss bug）：把 `N > len(citations.json)` 的 inline `[N]` 直接 strip 掉 → **整段 claim 失去 evidence backing**，某些 references 變成「list 有但 text 沒 cite」的 orphan references。

**正確做法**：
1. 讀 `article.json`，walk `output.structured_article.articlesection_set[].articleparagraph_set[].articlespan_set[].citations[]`
2. 以 document order 給每個 citation 一個 1-indexed 的 inline number
3. 每個 citation 的 `metadata.citation_detail.pmid` 可拿到對應 PMID
4. 用 PMID 反查 `citations.json`（或全局 dedup 後的 unified list）取得正確 reference number

### 整合腳本

```bash
# 單 query（單 artifact dir）
python3 ${CLAUDE_SKILL_DIR}/scripts/unify_artifacts.py \
  /var/folders/.../openevidence-mcp/<uuid> \
  --output ./my_report

# 多 query（多個 artifact dir 合併成一份 references list）
python3 ${CLAUDE_SKILL_DIR}/scripts/unify_artifacts.py \
  /var/folders/.../openevidence-mcp/<uuid-q1> \
  /var/folders/.../openevidence-mcp/<uuid-q2> \
  /var/folders/.../openevidence-mcp/<uuid-q3> \
  --output ./my_report

# Legacy layout（一個 folder + 前綴檔名如 q1a_answer.md / q1a_citations.json / q1a_article.json）
python3 ${CLAUDE_SKILL_DIR}/scripts/unify_artifacts.py \
  ./oe_artifacts --qids q1a,q1b,q2a --output ./unified
```

輸出：
- `<out>/unified/<qid>_answer_remapped.md` — inline `[N]` 已 remap 到 unified 編號（orphan 已 recovery）
- `<out>/unified/references_ama.md` — 合併、去重、AMA 格式的 reference list
- `<out>/unified/mapping.json` — per-query 的 old→new number mapping（audit 用）
- `<out>/unified/orphan_recovery_log.json` — 哪些 inline `[N]` 是 orphan、recover 成哪個 unified number、對應哪個 PMID

### Figure 下載（`download_figures.py`）

OE artifact 的 `article.json` 裡 `REACTCOMPONENT!:!PublicationFigure` payload 帶原始 figure URL，預設 `parse_oe.py` 只轉成 `[Figure: caption](url)` markdown link，不下載 binary。要實體檔時走這支：

```bash
# 下載單檔 article.json 的所有 figure
python3 ${CLAUDE_SKILL_DIR}/scripts/download_figures.py path/to/q1_article.json

# 批次：整個 artifact dir 底下 *_article.json
python3 ${CLAUDE_SKILL_DIR}/scripts/download_figures.py path/to/oe_artifacts/

# 只抓特定來源（URL substring match，host **或** path 任一有命中即算；case-insensitive）
python3 ${CLAUDE_SKILL_DIR}/scripts/download_figures.py path/to/oe_artifacts/ --match nccn

# Dry-run：列清單不下載
python3 ${CLAUDE_SKILL_DIR}/scripts/download_figures.py path/to/oe_artifacts/ --dry-run
```

輸出：
- `{artifact_dir}/figures/{qid}_{name_slug}_{url_hash6}.{ext}` — 實體 figure 檔
- `{artifact_dir}/figures/figures.json` — manifest（`url / caption / name / host / qid / local_path / status`），`status` ∈ `ok | dup | http_<code> | url_err:<reason> | err:<type>:<msg>`

**`--match` 實作細節**：比對整個 URL（host + path），不是只看 host。NCCN flowchart 的 URL 實際是 `storage.googleapis.com/nccn_images/<cancer>/versions/<ver>/page_N.jpg` — host 是 GCS，關鍵字 `nccn` 在 path 裡，所以 `--match nccn` 才抓得到。用 `--host nccn`（以前版本的 flag）會 miss。

**OE 能 embed 的 figure 類型（實測 2026-04-24）**：
- **NCCN flowchart** — 直接問「NCCN workup / treatment algorithm for <cancer>」會回傳 `EVAL-X` / `<cancer>-N` / `<cancer>-A` 系列 flowchart（AML 單次查回 5 張）
- **Primary literature figure** — JAMA / JBS / 等 journal CDN（Watch-and-Wait outcome curve、KM plot 等）

**觸發時機**：
- 使用者明說「幫我把 OE 的圖下載下來」「抓 figure」「要 NCCN 流程圖」
- 簡報 / 論文寫作流程 準備要把 figure 放進 slide / docx 時
- NCCN flowchart 特定需求 → `--match nccn`；journal figure → `--match jama` 或 `--match pmc`

**版權 caveat**：下載只是 technical fetch，最終 figure 是否可再發佈受原出版社授權限制。NCCN 版權嚴，內部研究 / 個人學習走 fair use 可；公開 pptx / paper / 外部發佈前確認 NCCN 授權條款。

### 快速 sanity check

整合後 markdown / docx 完成前，跑這段確認沒留 dangling refs：
```python
import re
md = open("final.md").read()
text = md.split("## References")[0]
cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)})
refs_count = 48  # 改成實際 reference 數
print(f"Cited: {len(cited)}/{refs_count}")
print(f"In list but uncited: {sorted(set(range(1, refs_count+1)) - set(cited))}")
print(f"Out-of-range (should be 0): {[n for n in cited if n > refs_count]}")
```

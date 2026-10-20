---
name: pubmed-search
description: "Searches PubMed via NCBI E-utilities and outputs a formatted Excel of articles. Trigger: PubMed, search PubMed, literature search, find articles, search articles, article search, PubMed search, literature review, find papers, search papers, research articles, 搜尋文獻, 查 PubMed, PubMed 搜尋, 找文獻, 文獻整理, 搜論文, 查論文, 幫我找文獻, 幫我搜 PubMed, 文獻搜尋, 文獻整理小幫手, 找論文, 搜尋論文, 查文獻, 幫我查論文, 最新文獻, 研究搜尋, search for papers about X, 幫我找關於X的文獻, 搜一下PubMed, find recent studies on X."
---

# 文獻整理小幫手 — PubMed Literature Search & Organization

Search PubMed for research articles by keywords, retrieve article metadata (title, authors, year, journal, abstract), generate AI content summaries, and output a formatted Excel spreadsheet. Supports scheduled incremental updates for ongoing literature monitoring.

## Workflow

Follow these steps **in order** every time this skill is triggered.

### Step 1: Gather Requirements

Ask the user for the following information (skip items they've already provided):

1. **Search terms** — keywords, MeSH terms, or a full PubMed query string (supports Boolean operators AND/OR/NOT and field tags like `[TIAB]`, `[MeSH]`)
2. **Date range** (optional) — min and max publication dates in YYYY/MM/DD format (e.g., 2023/01/01 to 2025/12/31)
3. **Maximum results** (optional) — default is 100
4. **Email address** — required by NCBI E-utilities usage policy
5. **NCBI API key** (optional) — for higher rate limits (10 req/sec vs 3); get one at https://www.ncbi.nlm.nih.gov/account/settings/ and set it as the environment variable `NCBI_API_KEY` (never write it into the config file). Works without a key at the lower rate.
6. **Output file path** — where to save the .xlsx output (e.g., `~/Documents/PubMed_HeartFailure.xlsx`)
7. **Generate content summaries** (optional) — default is true; Claude will generate 1-2 sentence Chinese summaries for each article
8. **Schedule updates** (optional) — whether to set up periodic auto-updates (daily / every 3 days / weekly)

### Step 2: Generate JSON Config

Write a JSON config file **alongside the output file**, using the same base name with `_config.json` suffix (e.g., if `output_file` is `/path/to/Results.xlsx`, save config as `/path/to/Results_config.json`).

**Config schema:**

```json
{
  "search_terms": "heart failure AND atrial fibrillation",
  "date_range": {
    "min_date": "2023/01/01",
    "max_date": "2025/12/31"
  },
  "max_results": 100,
  "sort_by": "pub_date",
  "email": "user@example.com",
  "output_file": "/absolute/path/to/PubMed_Results.xlsx",
  "generate_summary": true,
  "author_truncate": 6,
  "tool_name": "pubmed-search-skill"
}
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `search_terms` | Yes | — | PubMed search query (supports Boolean, MeSH, field tags) |
| `date_range` | No | null | Object with `min_date` and `max_date` in YYYY/MM/DD format |
| `max_results` | No | 100 | Maximum articles to retrieve (max 10000) |
| `sort_by` | No | "pub_date" | Sort order: "pub_date" or "relevance" |
| `email` | Yes | — | Required by NCBI E-utilities policy |
| `output_file` | Yes | — | Absolute path for the .xlsx output |
| `generate_summary` | No | true | Whether Claude should generate content summaries |
| `author_truncate` | No | 6 | Show first N authors + "et al." when count exceeds this |
| `tool_name` | No | "pubmed-search-skill" | The `tool` parameter sent to NCBI |

### Step 3: Run the Search

Execute the PubMed search script:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/pubmed_search.py <CONFIG_PATH>
```

This calls PubMed E-utilities API (ESearch → EFetch), parses the XML responses, and produces:
- `<output>.xlsx` — formatted Excel with columns: PMID, 標題(Title), 作者(Authors), 年份(Year), 期刊(Journal), Abstract, 內容摘要(Summary), 文章連結(Link)
- `<output>.csv` — companion CSV file

The script respects NCBI rate limits (3 req/sec without API key, 10 with key) and includes retry logic for transient errors.


### Step 4: Generate Content Summaries (Optional)

If `generate_summary` is true in the config:

1. Read the output Excel file
2. For each article that has a non-empty abstract but an empty summary, generate a **1-2 sentence Chinese summary** (內容摘要) capturing:
   - Study type (e.g., randomized controlled trial, cohort study, meta-analysis)
   - Key findings or conclusions
   - Clinical relevance or implications
3. Write the summaries to a temporary JSON file:
   ```json
   {
     "12345678": "這是一項回顧性世代研究，探討心房顫動對心衰竭患者預後的影響，發現合併心房顫動的患者死亡風險顯著增加。",
     "87654321": "此統合分析納入15項隨機對照試驗，結果顯示新型口服抗凝血劑在預防中風方面優於華法林，且出血風險較低。"
   }
   ```
4. Run the fill-summaries command:
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/pubmed_search.py <CONFIG_PATH> --fill-summaries <SUMMARIES_JSON_PATH>
   ```

### Step 5: Present Results

After execution, tell the user:
- Total number of articles found
- Date range of articles
- Output file locations (xlsx, csv, **and bib**)
- A brief preview: show the first 5 article titles with years
- **Optional handoff**: if this is for an SR / meta-analysis / 跟教授協作的研究, suggest piping the .bib into EndNote via `/endnote-import <bib-path> --project <name>` (macOS EndNote 21 only).

Example:
```
✅ PubMed 搜尋完成！

📊 搜尋結果：共找到 47 篇文獻
📅 年份範圍：2020 - 2025
📁 輸出檔案：
   - Excel: ~/Documents/PubMed_HF_AF.xlsx
   - CSV:   ~/Documents/PubMed_HF_AF.csv
   - BibTeX: ~/Documents/PubMed_HF_AF.bib
   - 設定檔: ~/Documents/PubMed_HF_AF_config.json

📝 前 5 篇文獻：
1. [2025] Impact of Atrial Fibrillation on Heart Failure Outcomes...
2. [2024] Novel Biomarkers for Risk Stratification in HFpEF...
3. [2024] Catheter Ablation vs Medical Therapy for AF in HF...
4. [2023] Machine Learning Prediction of AF in Heart Failure...
5. [2023] Anticoagulation Strategies in HF with AF: A Meta-Analysis...

💡 要灌進 EndNote 嗎？跑：
   /endnote-import ~/Documents/PubMed_HF_AF.bib --project hf-af-2026
```

### Step 6: Schedule Updates (Optional)

If the user wants periodic updates, create a scheduled task (選用：需要 Claude 的排程功能，例如 scheduled-tasks MCP 或系統 cron；沒有就請使用者手動定期重跑 `--update`):

- **Daily**: cron `"30 8 * * *"` (every day at 8:30 AM)
- **Every 3 days**: cron `"30 8 */3 * *"` (every 3 days at 8:30 AM)
- **Weekly**: cron `"30 8 * * 1"` (every Monday at 8:30 AM)

The scheduled task prompt should instruct Claude to:
1. Run the script in update mode: `python ${CLAUDE_SKILL_DIR}/scripts/pubmed_search.py <CONFIG_PATH> --update`
2. If `generate_summary` is true, generate summaries for new articles and run `--fill-summaries`
3. Report the number of new articles found

Example scheduled task prompt:
```
使用 pubmed-search skill 更新文獻列表。執行以下步驟：
1. 執行 python ${CLAUDE_SKILL_DIR}/scripts/pubmed_search.py {CONFIG_PATH} --update
2. 如果有新文章，讀取輸出檔，為新文章產生中文內容摘要，寫入 summaries.json
3. 執行 python ${CLAUDE_SKILL_DIR}/scripts/pubmed_search.py {CONFIG_PATH} --fill-summaries summaries.json
4. 報告新增文章數量
```

### Step 7: Save Reusable Script

After presenting results:

1. Copy the Python script to the same directory as the output file:
```bash
cp ${CLAUDE_SKILL_DIR}/scripts/pubmed_search.py <OUTPUT_DIR>/pubmed_search.py
```

2. Tell the user the re-run instructions:
   - **Config file**: `<CONFIG_PATH>`
   - **Script**: `<OUTPUT_DIR>/pubmed_search.py`
   - **Full search**: `python <OUTPUT_DIR>/pubmed_search.py <CONFIG_PATH>`
   - **Update only**: `python <OUTPUT_DIR>/pubmed_search.py <CONFIG_PATH> --update`
   - **Common modifications** (edit the config JSON directly):
     - Change search terms: edit `search_terms`
     - Change date range: edit `date_range`
     - Change max results: edit `max_results`

---

## Output Columns

| Column | Description |
|--------|-------------|
| PMID | PubMed article identifier |
| 標題(Title) | Article title |
| 作者(Authors) | Author list (truncated to first N + "et al." if many) |
| 年份(Year) | Publication year |
| 期刊(Journal) | Journal name (ISO abbreviation) |
| Abstract | Full abstract text |
| 內容摘要(Summary) | AI-generated 1-2 sentence Chinese summary |
| 文章連結(Link) | Clickable hyperlink to PubMed article page |

## Example Usage

**User**: "幫我搜尋 PubMed 上關於 heart failure 和 atrial fibrillation 的文獻，最近三年的就好，最多 50 篇"

**Claude**: Gathers requirements, generates config, runs the search, generates summaries, and outputs a formatted Excel file with 50 articles sorted by year.

**User**: "幫我設定每週更新一次"

**Claude**: Creates a scheduled task that runs `--update` mode every Monday at 8:30 AM, fetching only new articles since the last update.

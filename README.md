# Klaude Package For Share

我平常在 Claude Code 裡用的醫學、統計、簡報、文件與生產力 skills，整理成可以一鍵安裝的版本。by WLK M.D.

> **最快的裝法：把這個網址丟給你的 Claude Code 或 Codex，跟它說「照 README 幫我安裝」。**
> 下面的「給 AI 的安裝指示」就是寫給它看的。

---

## 裡面有什麼

分成 4 包（plugin），可以只裝需要的。

### `klaude-stats`：臨床研究統計（17 個）

| Skill | 做什麼 |
|---|---|
| table1 | 產生 Table 1（基本特徵表），自動選檢定、輸出 Word / Excel |
| kaplan-meier | KM 存活曲線＋log-rank＋number at risk |
| competing-risk | 競爭風險分析（CIF、Fine-Gray） |
| univariate-forest | 單變項迴歸＋forest plot |
| multivariate-interaction | 多變項 Cox / logistic 與交互作用 |
| psm-matching | 傾向分數配對（PSM）＋平衡檢查 |
| auc-cstat | ROC / AUC / C-statistic 比較 |
| survival-diagnostics | 存活分析前的假設檢查（PH 假設等，需 R） |
| raw-data-processing | 原始資料清理、編碼、衍生變項 |
| data-dictionary | 建資料字典 |
| exploratory-data-analysis | 探索性資料分析 |
| flowchart | 收案流程圖（CONSORT / STROBE 風格） |
| pheweb-phewas | 查 PheWeb 做 PheWAS |
| manuscript-results | 把統計輸出寫成論文 Results 段落 |
| research-guardian | 研究設計與統計方法的把關檢查 |
| research-plan | 統計分析總指揮：一份 `research_plan.json` 串起上面所有 skill |
| biostats-guardian | 選配：統計 pipeline 跑前跑後的品質檢查 |

> **不一定要裝全套。** 每個統計 skill 都能單獨用（例如直接說「幫我做 Table 1」）；`research-plan` 只是把它們串起來，`biostats-guardian` 是加強版檢查，不用也可以。

### `klaude-med`：醫學寫作、文獻與臨床工具（20 個）

| Skill | 做什麼 |
|---|---|
| med-manuscript-writing | 醫學論文各段落撰寫 |
| manuscript-writing-review | 論文初稿審閱 |
| academic-style | 圖表套期刊風格 |
| deep-research | 深度文獻研究 / 文獻回顧 / fact-check |
| pubmed-search | PubMed 搜尋與整理 |
| get-paper | 合法下載全文：開放取用優先，再用你自己機構的 proxy / VPN |
| hypothesis-generation | 從資料或文獻產生研究假說 |
| scientific-critical-thinking | 用科學方法批判論文 |
| critical-ai | 批判 AI 生成的醫學內容 |
| clinical-scores | 臨床評分計算（附出處） |
| phi-deid | 病歷去識別化：在本機先處理，只有去識別化的文字進 AI |
| emr-to-ai-guide | 教學：怎麼合法、安全地把自己醫院的病歷頁面接進 AI 流程 |
| lit-rename | 文獻 PDF 批次改名 |
| endnote-import | 匯入 EndNote |
| zotero-archive | 存進 Zotero（需 Zotero MCP，選用） |
| notebooklm-deep-research | 用 NotebookLM 做深度研究（需 NotebookLM MCP，選用） |
| medq | 即時醫學問答＋引用查證 |
| openevidence / oe-triangulate / oe-map | OpenEvidence 查詢、交叉驗證、用法地圖（需自行安裝 OpenEvidence MCP，見 `openevidence/SETUP.md`；沒有也會改用 PubMed） |

### `klaude-slides-docs`：簡報與文件（11 個）

| Skill | 做什麼 |
|---|---|
| case-discussion-pptx | 病例討論投影片（醫院 / 報告者自己填） |
| case-discussion-docx | 病例討論書面報告（Word） |
| journal-club-discussion-pptx | 書報討論投影片（丟 PDF / DOI / PMID） |
| notebooklm-pptx | NotebookLM 內容轉投影片 |
| pptx-verify | 投影片視覺檢查（跑版、字太小、重疊） |
| pptx-handout | 投影片＋講稿做成 A4 handout |
| md-to-pdf | Markdown 轉漂亮的 PDF（含中文字型、目錄、書籤） |
| pdf-split-by-outline | 依書籤拆 PDF |
| marker-pdf-converter | PDF 轉 Markdown（含表格、公式） |
| pageindex | 長 PDF（guideline / 課本）精準問答，附頁碼 |
| excel-to-csv | Excel 轉 CSV |

### `klaude-productivity`：生產力（9 個 skill＋4 個輕量 agent）

| Skill | 做什麼 |
|---|---|
| grill-me | 做決定 / 開新計畫前，讓 Claude 用問題逼你想清楚 |
| no-wheels | 寫程式前先查有沒有現成的輪子 |
| auto-git | 寫程式時自動 commit、建檢查點 |
| license-decision-tree | 幫開源專案選授權 |
| writing-style-builder | 用你自己的 5–15 篇文章建立寫作風格，之後「用我的風格寫」 |
| zh-article-analyzer | 中文文章結構 / 用詞分析 |
| youtube-playlist-to-textbook | YouTube 播放清單整理成課本式 PDF |
| material-layout | 網頁版面照 Material Design 3 排 |
| vibe-coding-teacher | 給非工程背景的人：邊做邊學寫程式 |

附帶 4 個輕量 subagent（`lite-auditor`、`web-researcher`、`lit-extractor`、`browser-qa`），比預設 agent 省很多 token，用法見 [subagent 派法](docs/subagent-dispatch-guide.md)。

### 設定心得

- [autocompact 設 40 萬 tokens 的理由](docs/autocompact-400k.md)
- [subagent 怎麼派：什麼時候派、怎麼寫派工單、選哪個模型](docs/subagent-dispatch-guide.md)

---

## 安裝（Claude Code）

在 Claude Code 裡依序輸入：

```
/plugin marketplace add fireman333/Klaude-Package-For-Share
/plugin install klaude-stats@klaude-package-for-share
/plugin install klaude-med@klaude-package-for-share
/plugin install klaude-slides-docs@klaude-package-for-share
/plugin install klaude-productivity@klaude-package-for-share
```

不需要的包跳過就好。裝完輸入 `/reload-plugins` 或重開 Claude Code。

之後要更新：`/plugin` → Marketplaces → klaude-package-for-share → Update。

## 安裝（Codex）

```bash
git clone https://github.com/fireman333/Klaude-Package-For-Share.git
cd Klaude-Package-For-Share
bash install-codex.sh                 # 全部裝
bash install-codex.sh klaude-stats    # 只裝某一包
```

會複製到 `~/.agents/skills/`，重開 Codex 即可。（4 個 subagent 是 Claude Code 專用，Codex 不會裝。）

## 需要的工具

大部分 skill 第一次用時，Claude 會告訴你缺什麼、幫你裝。想一次裝好（macOS）：

```bash
brew install python pandoc typst poppler node uv
```

```bash
brew install --cask libreoffice
```

```bash
pip install pandas numpy scipy statsmodels lifelines scikit-learn matplotlib openpyxl python-docx python-pptx pypdf pymupdf jieba
```

- 統計裡的 `survival-diagnostics` 需要 R。
- 投影片類需要 `npm install -g pptxgenjs react react-dom react-icons sharp`。
- 選用的 API / 服務都用環境變數或自己的設定檔，**這個 repo 不含任何 key**：`NCBI_API_KEY`（PubMed 加速，可不設）、`UNPAYWALL_EMAIL`（get-paper，填你自己的 email）。

---

## 給 AI 的安裝指示

如果你是 Claude Code 或 Codex，使用者請你安裝這個 repo：

1. 先問使用者要裝哪幾包（klaude-stats / klaude-med / klaude-slides-docs / klaude-productivity），預設全部。
2. **Claude Code**：執行 `claude plugin marketplace add fireman333/Klaude-Package-For-Share`，再對每一包執行 `claude plugin install <包名>@klaude-package-for-share --scope user`，最後請使用者重開或輸入 `/reload-plugins`。
3. **Codex**：clone 這個 repo 到使用者指定的位置，執行 `bash install-codex.sh <包名...>`。
4. 依使用者會用到的 skill，檢查上面「需要的工具」是否已安裝；缺的列出來，問過使用者再裝。
5. 不要替使用者建立或填入任何 API key、帳號或 email；需要時請他們自己設定環境變數。

---

## 注意

- **病歷與個資**：請遵守你所在醫院的資安與個資規範。可識別的病歷不要直接貼進雲端 AI，先用 `phi-deid` 在本機去識別化。
- **醫學內容**：skill 產出的內容仍需自己查證，不能取代臨床判斷。
- **授權**：MIT（見 [LICENSE](LICENSE)）。部分 skill 改寫自他人的開源專案，資料夾內保留原作者的授權與出處，以那份為準：
  - survival-diagnostics 參考 [htlin222/survival-pipe](https://github.com/htlin222/survival-pipe)（MIT）
  - exploratory-data-analysis、hypothesis-generation、scientific-critical-thinking 來自 K-Dense（MIT）
  - pageindex 使用 [VectifyAI/PageIndex](https://github.com/VectifyAI/PageIndex)（MIT）
  - marker-pdf-converter 使用 [datalab-to/marker](https://github.com/datalab-to/marker)（程式碼 Apache-2.0，模型權重另有授權）
  - OpenEvidence MCP 來自 [htlin222/openevidence-mcp](https://github.com/htlin222/openevidence-mcp)（Apache-2.0，非官方）

### 也推薦這些（別人做的，請到原作者那裡裝）

- [htlin222/meta-pipe](https://github.com/htlin222/meta-pipe)：統合分析（meta-analysis）全流程
- [htlin222/robust-lit-review](https://github.com/htlin222/robust-lit-review)：可重現的系統性文獻回顧
- [htlin222/audit-oe-skill](https://github.com/htlin222/audit-oe-skill)：OpenEvidence 引用稽核
- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)：Obsidian 相關

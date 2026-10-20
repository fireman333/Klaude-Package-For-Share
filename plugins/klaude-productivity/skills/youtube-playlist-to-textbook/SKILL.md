---
name: youtube-playlist-to-textbook
description: Turn a YouTube lecture playlist into Chinese textbook-grade lecture notes (markdown + PDF) for a non-CS reader persona you can customize (default sample: medical-background learner familiar with PACS/HIS/EMR). Pipeline yt-dlp → claude -p headless（生成）→ optional NotebookLM fact-check → pandoc + Chrome headless PDF. Trigger `/yt-textbook`、`/playlist-textbook`、`/yt2text`，或使用者提及「把 YouTube playlist 變成教科書」「把課程影片轉成筆記」「playlist 生 lecture notes」「YouTube 生教材」「課程影片整理成講義」等意圖時，即使沒有明確用上述關鍵字也要主動觸發。
---

# YouTube Playlist → 中文教科書級講義

## 這個 skill 在做什麼

把 YouTube 的講座型播放清單（MIT OCW、Stanford、Khan、任何系列課程）轉成**中文教科書級 lecture notes**（markdown + 整合 PDF），reader persona 預設為「醫療背景、非 CS 的學習者（熟 PACS/HIS/EMR）」範本，Stage 1 可整段換成你自己的背景。

這條 pipeline 已用 MIT 6.824 分散式系統（20 集）驗證過，產出 130K 中文字 + 261 頁 PDF。

**核心設計**：三層協調
1. **yt-dlp** 抓字幕 → 餵給 claude -p headless 生成
2. **（選用：若你有 NotebookLM 才會用到）NotebookLM mega-notebook**（所有 YouTube URL 當 source）做事實校對 ground truth；沒有的話跳過 Stage 3 與 Stage 6，直接生成
3. **Claude** 負責編排、surgical patch、組裝 PDF

## 快速開始

```
使用者：幫我把這個 playlist 變成教科書 https://www.youtube.com/playlist?list=PL...

Claude：[Stage 0] Preflight — 檢查 claude / yt-dlp / pandoc / Chrome（nlm 為選用）
       [Stage 1] 3 問快速設定：persona + sections 要沿用預設嗎？
       [Stage 2] yt-dlp 抓清單 + transcript
       [Stage 3] 建 NotebookLM mega-notebook + 並行上傳所有 URL
       [Stage 4] （可選）先跑 Lec 1 給你看
       [Stage 5] 並行 worker 用 claude -p 生所有集數
       [Stage 6] 對每集抽 3-5 個事實用 NotebookLM 校對 → 不符就重寫
       [Stage 7] README + PDF
```

---

## Stage 0 — Preflight（10 秒）

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/preflight.sh
```

檢查這些工具：`claude` / `yt-dlp --version` / `pandoc --version` / Chrome 可執行；`nlm`（NotebookLM）為選用，缺了只警告。

**缺哪個就列出對應安裝指令給使用者**（`brew install pandoc` / `pip install yt-dlp`；選用的 `nlm login` 等），**不要自動安裝**。等使用者手動補齊再往下。

---

## Stage 1 — 3-Question Intake

問使用者 3 個問題，每題都給預設值讓使用者直接按 Enter 沿用：

**Q1. Playlist URL**（必要，無預設）
支援格式：`https://www.youtube.com/playlist?list=PL...` 或純 playlist ID。

**Q2. Reader persona**（預設範本：醫療背景、非 CS，熟 PACS/HIS/EMR；建議換成你自己的背景）
顯示預設 persona 文字（見 `references/default_persona.md`），問「要沿用嗎？或貼一段新的 persona 給我？」

**Q3. Section 架構**（預設 9 段）
顯示預設 9-section 清單（見 `references/default_sections.md` §0-§9），問「要沿用嗎？要改可以刪/改哪幾段？」

**將答案寫進專案根目錄的 `.skill-state.json`**：
```json
{
  "playlist_url": "...",
  "playlist_id": "...",
  "persona_text": "...",
  "sections": [...],
  "notebook_id": null,
  "stage": 1
}
```

---

## Stage 2 — Fetch Playlist + Transcripts

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/fetch_playlist.sh <PLAYLIST_URL>
```

此 script 會：
1. `yt-dlp --flat-playlist --print-json` 抓 metadata → `lectures-raw/playlist.json`
2. 對每集 `yt-dlp --write-auto-subs --skip-download --sub-lang en --convert-subs vtt` → `lectures-raw/NN_title/transcript.vtt`
3. VTT 去除 timestamp → `lectures-raw/NN_title/transcript.txt`

**檢驗**：每集應有 transcript.txt，字數 > 1000。若某集失敗（私人影片、無字幕）→ 標記跳過，繼續。

---

## Stage 3 — Mega-Notebook Auto-Build（選用：若你有 NotebookLM MCP 才會用到；否則跳過）

用新的 NotebookLM MCP 自動建 notebook + 平行上傳所有 YouTube URL：

```
# 1. 建 notebook
mcp__notebooklm__notebook_create(title="<playlist_title> 校對")
→ 回傳 notebook_id

# 2. 平行上傳（3 個一批，避免 rate limit）
for batch in chunks(playlist, 3):
    parallel: mcp__notebooklm__source_add(
        notebook_id=<id>,
        source_type="url",
        url=<youtube_url>
    )

# 3. 存狀態
.skill-state.json.notebook_id = <id>
```

**成本**：每筆 `source_add` 約 1-2 秒，NotebookLM 會在背景 process，但先別 query。

---

## Stage 4 — Pilot（可選，不強制）

如果使用者明確要求「先跑 Lec 1 給我看」→ 執行：

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/generate_lecture.py 1
```

完成後印出 markdown 前 500 字給使用者確認。**若使用者沒主動要求 pilot → 跳過直接進 Stage 5**（先前已決策：pilot 非強制）。

---

## Stage 5 — Batch Generation

這是耗時主力（每集 ~60-90 秒，20 集約 15-20 分鐘 with 2 worker）。

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/generate_lecture.py all --concurrent 2
```

內部邏輯：
- 對每集做 2 次 `claude -p --model haiku` call（prompt 走 stdin）
  - Part A：§0-§4（TL;DR / Motivation / Prerequisites / Core Concepts / Deep Dive）
  - Part B：§5-§9（醫學類比 / Q&A / Pitfalls / 自測題 / 延伸資源）
- 兩次 call 各約 3,500-5,000 中文字，合併後 ~7,000-10,000 字
- 產物寫到 `lectures/NN_title.md`

**Concurrency = 2（新預設）**：MIT 6.046J（34 集）實測發現 concurrent=3 會觸發 per-minute token quota（最後一個 batch 連續 429），降到 2 穩定度明顯提升。並行 nested `claude -p` 太多會撞訂閱的 rate-limit，token-per-minute 是瓶頸。
**批次間 sleep：30 秒**（從先前 10 秒調高），給 quota bucket 回補。

**RPM 節流（2026-04-17 新增）**：in-process sliding-window limiter，預設 `MAX_RPM=10`（用 `YTT_MAX_RPM` 環境變數覆寫）。超過就 async sleep 到最舊 request 脫離 60s 視窗，事前避開 429。

**429 專屬 backoff**：偵測 `429 / quota / exhausted / rate limit / RESOURCE_EXHAUSTED` → 60s/120s/240s（max_retries=4，cap 300s）；generic transient（AbortError、ECONNRESET、timeout）走較短 15s/30s/60s。log 會標 `[429/quota]` 或 `[transient]` 便於事後 grep。

**haiku → sonnet auto-fallback**（沿用原 flash→pro 設計；haiku 偶爾回 <1500 CJK）：
- 若 haiku 任一 part 回 <1500 CJK 且**不是 timeout/quota error**，`generate_one` 會自動用 `sonnet` 重跑一次
- 若需要整批 sonnet：`--model sonnet` override

**錯誤恢復**：`.state/progress.json` 紀錄每集結果（flock 互斥 + atomic rename，concurrent 安全）。`.state/progress.jsonl` 為 append-only journal，調查用。失敗集會重試，**不會重做已成功的**。

**絕不加 `--dangerously-skip-permissions`**（危險旗標；本 skill 純文字生成不需任何工具權限）。

---

## Stage 6 — Phase F 自動校對（選用：需要 Stage 3 的 NotebookLM notebook；沒有就跳過）

對每集抽 3-5 個關鍵事實到 NotebookLM 查證。流程：

```
for each lecture:
    # 1. 從講義抽 3-5 個可驗證的事實斷言
    facts = extract_factual_claims(lecture_md)   # heuristic: 「paper §X.Y 規定」「預設值為 X」等

    # 2. 逐一查 NotebookLM
    for fact in facts:
        q = f"請根據來源文件判斷以下敘述是否正確：{fact}。如不正確，請說明正確答案並引用 section。"
        answer = mcp__notebooklm__notebook_query(notebook_id, q)

        # 3. 若回答顯示不符
        if mismatches(answer):
            # 3a. claude -p 改寫該段落
            new_para = llm_rewrite(original_para, correction=answer)
            # 3b. Claude 做 surgical Edit + 顯示 diff
            show_diff_and_patch(lecture_path, old=original_para, new=new_para)
```

**diff 顯示後暫停 2 秒**讓使用者有機會 Ctrl+C 中斷（先前決策：自動重寫 + 可中斷）。

完整 phase F script：
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/phase_f_verify.py all
```

---

## Stage 7 — Assembly（README + PDF）

### 7.1 README.md

產出專案根目錄的 README.md，包含：
- Playlist 基本資訊（標題、集數、講者、來源 URL）
- **Mermaid 學習路徑圖**（lecture 依序 + 主題 cluster）
- **3 種學習模式**（考試衝刺 / 完整讀完 / 類比對照）的導讀
- Lecture 索引表（每集一行：編號 + 標題 + 重點關鍵字）

### 7.2 PDF Build

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/build_pdf.sh
```

沿用 6.824 驗證過的方案：
1. `cat` 所有 `lectures/*.md` → `build/combined.md`（用 `<hr class="pagebreak"/>` 分集）
2. `pandoc --from markdown+raw_html-yaml_metadata_block --to html5 --standalone --toc` → HTML
3. Python 注入 mermaid.js CDN（`<script src="...mermaid@10...">`）到 `</head>` 前
4. Chrome headless `--print-to-pdf` → `build/<playlist>-lecture-notes.pdf`

**字型/排版**：Heiti TC print-CSS（`build/style.css`，skill 有提供 default 可 copy）。

---

## 工具與資源總覽

### 必要工具（Stage 0 會檢查）
- `claude`（Claude Code CLI，generation engine 走 `claude -p` headless，用你的 Claude 訂閱、免 API key）
- `yt-dlp`（`pip install yt-dlp` 或 `brew install yt-dlp`）
- `pandoc`（`brew install pandoc`）
- Chrome（macOS: `/Applications/Google Chrome.app`，Linux: `google-chrome`；只有 Stage 7 產 PDF 才需要，沒有就只交付 markdown）

### 選用工具
- `nlm` + `notebooklm-mcp`（`uv tool install notebooklm-mcp-cli`，再 `nlm login`）：Stage 3 / 6 事實校對用

### NotebookLM MCP 工具（用新 `notebooklm-mcp` binary，38 tools）
- `mcp__notebooklm__notebook_create(title=...)` — 建 notebook
- `mcp__notebooklm__source_add(notebook_id=..., source_type="url", url=...)` — 上傳 YouTube URL
- `mcp__notebooklm__notebook_query(notebook_id=..., question=...)` — Phase F 校對
- `mcp__notebooklm__notebook_list()` — 列所有 notebook（若 state 遺失可回撈）
- `mcp__notebooklm__notebook_get(notebook_id=...)` — 查 notebook 詳情（含 sources）

### claude -p headless 呼叫（generation engine）

> 本 skill 生成引擎走 **`claude -p` headless**（用你的 Claude Code 訂閱、免 API key）。不走其他 CLI：多數 CLI 的 `-p` 不讀 stdin、大 argv 會截斷，不適合大 transcript 批次生成。

```bash
# 大 transcript prompt 走 stdin（claude -p 從 stdin 讀，永不截斷、無 ARG_MAX 問題）
cat /tmp/prompt_01A.txt | claude -p --model haiku

# 短 prompt 也可直接帶 argv
claude -p "<prompt>" --model haiku
```

- `claude -p` 只輸出**純文字** response（無 JSON wrapper、不需 `jq`）→ stdout 直接就是 markdown。
- 模型：預設 `haiku`（便宜快），fallback `sonnet`（part 回 <1500 CJK 時自動升級）；整批用 `--model sonnet`。
- **絕不加 `--dangerously-skip-permissions`**；本 skill 生成是純文字 completion，不需任何工具權限。

### 參考檔導航
- `references/default_sections.md` — 9 段預設 section 架構 + 每段寫作要求
- `references/default_persona.md` — reader persona 範本（可替換）+ 醫學名詞輸出格式
- `references/prompt_templates.md` — Part A / Part B 生成 prompt 完整模板
- `references/phase_f_rewrite_template.md` — Phase F 改寫 prompt（成功案例：Lec 03 §4.4）

---

## 目錄結構（skill 執行後產生）

```
<project_root>/
├── .skill-state.json          # 狀態檔（playlist_url / notebook_id / stage）
├── lectures-raw/              # Stage 2 原始輸入
│   ├── playlist.json          # metadata
│   └── NN_title/
│       ├── transcript.vtt
│       └── transcript.txt
├── lectures/                  # Stage 5 產出（完成版 markdown）
│   └── NN_title.md
├── .state/
│   └── progress.json          # 每集生成狀態（ok / err / cjk_total）
├── build/                     # Stage 7 組裝輸出
│   ├── combined.md
│   ├── <playlist>-lecture-notes.html
│   ├── <playlist>-lecture-notes.pdf
│   └── style.css
└── README.md                  # Stage 7 產出
```

---

## 決策樹（呼叫 skill 時的分支判斷）

| 使用者情境 | Claude 該做什麼 |
|---|---|
| 完全新 playlist | 從 Stage 0 開始跑完整 7 stage |
| 已跑過、想重跑某集 | `generate_lecture.py <num> --force` |
| 已跑過、想加新集數 | 偵測 `.skill-state.json`，只對新集數跑 Stage 2 + 5 + 6 |
| 跑一半掛掉 | 讀 `.state/progress.json`，從失敗集重跑 |
| 想只改 section 架構重生 | 改 `.skill-state.json.sections` → `generate_lecture.py all --force` |
| 想換 persona 重生 | 改 `.skill-state.json.persona_text` → 全部 `--force` |
| 想重建 PDF（沒改內容） | 直接 `bash ${CLAUDE_SKILL_DIR}/scripts/build_pdf.sh` |

---

## 常見錯誤與診斷

### yt-dlp 抓不到字幕
- **自動字幕不存在**：該影片作者關了 auto-caption。解法：手動提供 transcript 檔，放到 `lectures-raw/NN_title/transcript.txt`。
- **字幕抓到但空檔**：yt-dlp 有時抓到 0-byte vtt。檢查檔案大小 > 100 bytes。

### NotebookLM source_add 失敗
- **rate limit**：並行降到 1，重跑該批。
- **URL 格式錯**：確保是 `youtube.com/watch?v=` 而非 `youtu.be/` 短網址。

### claude 回應過短（< 1500 CJK）
- 常因 transcript 本身太短（< 10 分鐘短影片）。檢查 transcript.txt 字數是否 > 1000。
- 重跑一次通常會正常（或自動 fallback 到 `sonnet`）。

### PDF 渲染異常（mermaid 沒畫出來）
- pandoc 把 mermaid fenced block 輸出成 `<pre class="mermaid"><code>…</code></pre>`（class 在 `<pre>` 上，**不是** `<code class="language-mermaid">`）。Inject script 用 `pre.mermaid > code` selector 把每個 block 轉成 `<div class="mermaid">`，內容用 `block.textContent`（瀏覽器自動 decode `--&gt;` 回 `-->`）。
- 渲染完應該看到 HTML 裡有 `<div class="mermaid">…`；若還是 `<pre class="mermaid">`，代表 JS 沒跑成功 — 檢查 mermaid CDN 是否 load 失敗。
- Chrome `--virtual-time-budget=30000` 等 mermaid render 完成。若圖多於 20 張，調到 60000。
- Mermaid 10.9.5 已知禁用語法：`<-->` 雙向箭頭、未閉合 `<br>`（要 `<br/>`）、`[label]` 裡有雙引號（要把整個 label 包起來 `["..."]`）、node label 含 `->` 文字（要用 Unicode `→`）。違反會在該頁顯示 `Syntax error in text mermaid version 10.9.5`。

### Stage 6 Phase F 過度重寫
- 若發現 NotebookLM 判斷偏嚴（例如對語義近似但措辭不同也說不符）→ 手動設定 `.skill-state.json.phase_f_strict = false` 跳過 auto rewrite，只列 warning 供人工檢視。

---

## 後續擴充建議（非必備）

- **非 9-section 主題結構**：把 `references/default_sections.md` 複製到專案根目錄的 `sections.md`，skill 偵測到會優先用該檔。
- **非醫學 persona**：把 `references/default_persona.md` 換成工程、法律、金融 persona，完全相同架構只改 reader 設定。
- **多語輸出**：若要英文版 lecture notes，改 prompt template 的 `繁體中文為主` → `英文為主，中文保留在術語括號內`。

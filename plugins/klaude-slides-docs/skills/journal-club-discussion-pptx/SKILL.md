---
name: journal-club-discussion-pptx
description: "書報討論 pptx / open-slide deck 生成器，含 literature research（PubMed；有 OpenEvidence MCP 則加 OE，選用）。輸入 paper（PDF / DOI / PMID / URL）或自由文本 markdown，輸出 pptx（bilingual speaker notes）或 open-slide deck。觸發關鍵詞：/jc-pptx、/journal-club-pptx、/書報討論、/bp-pptx、書報討論 pptx、journal club slide、paper + lit review + pptx、open-slide 書報、jc open-slide。"
---

# Journal Club / Case Discussion PPTX Generator

> **中文臨床語氣**：寫中文內容（speaker notes）前先讀 `${CLAUDE_SKILL_DIR}/../case-discussion-pptx/references/clinical_writing_tone.md`（客觀保守措辭、禁用詞表），交付前 grep 禁用詞。

End-to-end 書報討論 / case discussion pptx pipeline. 專為 **paper / case + 文獻研究** 場景設計。

## When to Use

- **Journal club**: paper（PDF / DOI / PMID / URL）為主 → PICO / methods / results / discussion（**直接觸發本 skill**）
- **Freeform markdown**: 自己整理過的主題筆記 → 自訂 headings → slide（**直接觸發本 skill**）
- **Case discussion with literature review**（病歷內容為主）: 病歷整理成 markdown（先跑 `phi-deid`）後可走 admission route；若不需文獻研究，直接用 `case-discussion-pptx`。

**退讓規則**（不走本 skill）：
- 不需文獻研究的純 case 晨會 9-slide → `/case-discussion-pptx`
- 只做 literature review doc、不要 pptx → `/deep-research`
- 臨床問題清單 + 逐題查證報告（非 paper 為主） → 直接請 Claude 用 `/openevidence` 或 `/pubmed-search` 逐題查

## Slide Conventions

This skill conforms to the shared academic slide rules (Rule 1 body-English / Rule 2 citation 3-field / Rule 3 audit off body / Rule 4 bilingual speaker notes). Canonical spec: **`${CLAUDE_SKILL_DIR}/../case-discussion-pptx/references/slide_conventions.md`**. Pre-flight enforcement is in `render.py` (`rule1_preflight`, `rule3_preflight`). Any deviation requires explicit user override.

## 7-Stage Workflow

### Step 0 — Input Detection

執行 `python3 ${CLAUDE_SKILL_DIR}/scripts/input_router.py <input>` → 寫 `intake.json`。偵測順序：DOI → PMID → PubMed URL → 其他 URL → `.pdf` → markdown / freeform。結果送使用者 y/n 確認（顯示 `intake.json.type + source_meta.title + content_md 字數`）。

（若 type=admission，先把病歷整理成 markdown 並跑 `phi-deid`，確認沒有真實病人識別資訊才繼續。）

### Step 1 — Structured Extraction

**PHI guard（admission 路徑入口硬檢查）**：未跑過 `phi-deid` 的病歷內容不得進入投影片；有疑慮就 STOP 並請使用者先去識別化。

依 `intake.json.type` 走對應 prompt (`prompts/paper_extract.md` 等)，產 `structured.json`：
- **paper**: PICO / design / methods / primary & secondary results / limitations / conclusion
- **admission**: case_profile / timeline / findings (PE/lab/image/path) / dx / mgmt
- **freeform**: headings + body sections

**Checkpoint**: 使用者過目 `structured.json` 摘要、允許一輪修正。

### Step 2 — Discussion Questions

**若使用者已提供 1–3 條關切點（highlights）**: 先**轉寫為 Q1–Q3 的 draft**，再依 `prompts/discussion_questions.md` 補足到 3–5 題。轉寫原則：
- highlights 是聽者關切點（e.g. `"preop workup for colorectal CA"`）→ 開放式 Q（`"What preoperative workup do you consider essential for this case, beyond the current CT/CEA?"`）
- 聽眾預設 `attending` → 避開教學 recall 型
- `case_type` 影響 archetype 偏向：`mnm` → complication analysis、`academic-review` → guideline anchor、`diagnostic-challenge` → DDx、`management-dilemma` → SDM

**沒有 highlights**: 以 `prompts/discussion_questions.md` 生 3–5 題 open-ended questions。

兩種情況都寫 → `questions.json`。

**Checkpoint（必問）**: 使用者 keep / edit / regenerate。題目定錯後面全錯。

### Step 3 — Literature Research（PubMed 為主；OpenEvidence 選用）

> **選用：只有你裝了 OpenEvidence MCP 才跑下方「主線 OE」；沒有 OE 就跳過主線，只用「平行 PubMed」+ `research_synth.py --pubmed ...`（不傳 `--oe`），仍可得到完整 `research_findings.json`。**

**主線（sequential OE）** — 避免 artifact 90K–170K chars 炸 context：
```
for q in Q1..Qn:
    oe_ask(q)                                                     # MCP 自動存 artifactDir/（含 answer.md + citations.json）
    python3 ${CLAUDE_SKILL_DIR}/scripts/oe_summary_compactor.py <artifactDir> oe_sum_q{i}.json --qid Q{i} --question "<q_text>"
    Read oe_sum_q{i}.json  (<5K chars; source_mode=artifact_dir 為正，regex_fallback 代表 citations.json 缺失 → 視為 degraded)
```

**OE 圖表（選用）**：若 OE 回傳含 figure，可依 OE skill 的指示下載並嵌入 `results` / `literature_evidence` slide；沒有就略過。

> **Orphan citation 注意**：OE 的 `answer.md` 用 span-order sequential 編號（含同一篇 paper 重複引用），`N > len(citations.json)` 的 inline `[N]` 是 re-cite，不是 orphan。`oe_summary_compactor.py` 只讀 `citations.json`；若引用密度高、需跨 query 整合 references，請改用 OE skill 的 artifacts 整合流程。

**平行（single-message dispatch，n=3–5 subagents）**：
主線先給每 Q 算一條 PubMed query + MeSH 候選，然後在**一個訊息內** dispatch n 個 `general-purpose` subagents（Agent tool `model: haiku`：找文獻 / 列候選 PMID 屬機械查找，錯了可由 fetch 讀回抓到；若該 subagent 另需綜合彙整 `take_home` 判讀則用 `model: sonnet`），prompt 來自 `prompts/subagent_pubmed.md`。每個 subagent：
- 跑 `mcp__pubmed__pubmed_search_articles` → `pubmed_fetch_articles`（top 3–5 PMIDs）
- 寫 `pubmed_sub_q{i}.json`（含 `study_type / country / n / take_home`）
- 3 次 retry 無結果 → 記 `failures[]`，不靜默吞

**合成**：`python3 ${CLAUDE_SKILL_DIR}/scripts/research_synth.py` 讀所有 `oe_sum_*.json` + `pubmed_sub_*.json` → `research_findings.json`（per-Q evidence + dedup PMID + `all_citations` 彙總）。

**（選用）Citation 稽核**：若有 OE 來源 citations，可請 Claude 逐筆用 PubMed 核對 PMID / 年份 / 作者，結果寫回 JSON（audit 結果只放 speaker notes，Rule 3）。

**Checkpoint**: 每題至少 1 OE citation 或 1 PubMed pick；失敗題目清楚報告給使用者。

### Step 4 — Slide Data + Bilingual Speaker Notes
Claude 讀 `structured.json` + `questions.json` + `research_findings.json` → 寫 `<work_dir>/jc_<slug>_data.py`（Python module with `DATA` dict，schema 見 `data_schema.md`）。

**Speaker notes 每張必含** — （見 slide_conventions Rule 1–3）：
```
=== Abbreviations ===   （Rule 1: 首次出現英文縮寫 | 全稱 | 中文）
=== 核心論點 ===         （中文口白 / 重點）
=== 可預期提問 ===       （中文聽者 Q + 答題方向）
=== 補充數據 ===         （citation 三欄位: study type / country / n, Rule 2）
[=== Audit ===          — 只在 literature_evidence / references slide；audit verdict 不上 slide body, Rule 3]
```

Slide body **一律英文**（`render.py` 的 `rule1_preflight` 自動驗）。

**Background 整理過去研究優先用「表格」**：
報 background 段落時，**整理過去研究（既有文獻的 method / result / summary）一律優先用表格而非 bullets** — 視覺更精簡、跨研究好對照、密度更高。實作方式：
- **首選**：複用 `literature_evidence` slide type 的 citation table（欄位 Source / Design / n / Take-home 正好對應 作者年 / method / sample / 一句話 summary）；放在 background section 即成「過去研究整理表」。
- 一列一篇研究：`author_year` + `study_type`（method）+ `n` + `take_home`（key result 或 summary 一句話）。
- **散文式 bullets 只保留給 narrative 鋪陳**（problem statement / knowledge gap / study aim 這類「串故事」內容）；**多篇研究並列比較一律走表格**。
- 若同時要呈現「方法 vs 結果 vs 結論」三欄對照，可用 `take_home` 欄塞 summary，或在 builder 加 background-table 變體（study / method / key result / conclusion 四欄）。

### Step 5 — Render

**Step 5.0 — 輸出格式選擇（必問，除非委派模式已指定）**:

直接觸發模式必問（`AskUserQuestion` 或一句話詢問）：
- **`.pptx`**（預設）：傳統 PowerPoint binary，跨機器分享 / 列印 friendly / Office 生態系
- **`open-slide`**（選用，需 Node + pnpm + `@open-slide/cli`）：React + Vite static HTML deck（1920×1080 canvas / motion / inspector 可 inline 微調 / 可部署到靜態 hosting），但**輸出不是 .pptx**，是一個 React 專案資料夾。

**Step 5.A — `.pptx` path（output_format = pptx）**:
```bash
python3 ${CLAUDE_SKILL_DIR}/render.py <work_dir>/jc_<slug>_data.py <output_path>
```
- `<output_path>` 預設 `journal_club_<slug>_<date>.pptx`（目前工作目錄）
- Theme 由 `DATA.meta.theme` 決定（`journal_classic` 預設）
- 報告者姓名是使用者填寫欄位（`DATA.cover.presenter`），沒給就留 `（你的名字）` 占位，不要猜
- Cover 不計頁碼，第 2 張起自動編頁

**Step 5.B — `open-slide` path（output_format = open-slide）**:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/build_open_slide_deck.py <work_dir>/jc_<slug>_data.py <output_parent_dir>
```
- `<output_parent_dir>` 通常等於 `.pptx` 會放的同一資料夾；builder 內部以 `DATA.meta.topic_title` slugify 出子資料夾名 `<slug>/`
- 跑完得到 `<output_parent_dir>/<slug>/` React/Vite 專案 — 內含 `slides/journal-club/index.tsx`（16 個 Page React 元件 + meta + design + notes 平行陣列）+ `themes/` 3 個 theme bundle
- 第 5.0 題選定的 `DATA.meta.theme` 自動 map 到對應 open-slide theme id：`journal_classic`→`journal-classic`、`grand_rounds_warm`→`grand-rounds-warm`、`clinical_modern`→`clinical-modern`
- Theme palette 跟 pptx 對齊但 `clinical-modern` primary/accent 拆開（pptx 版有 `primary == accent` invisibility bug）
- Speaker notes 透過 `export const notes: (string | undefined)[]` 平行陣列傳遞給 open-slide presenter mode 自動讀取

### Step 6 — QA（**Hard gate — 不准跳過**）

**Output format 決定 QA 路徑**：
- `output_format = pptx` → 走 **Step 6.A**（python-pptx markitdown + qa_visual.py + subagent 6 項缺陷檢查）
- `output_format = open-slide` → 走 **Step 6.B**（browser dev server + 逐頁 navigate + screenshot + subagent QA）

#### Step 6.A — `.pptx` QA path

**為什麼這步是 hard gate**: `python -m markitdown <pptx>` 只看得到文字，**完全看不到版面**。實際渲染常見的 row overflow / column 溢位 / dot mis-align / footer collision / centered-vs-left 對齊衝突 / `• -` 雙標記，純文字檢查全部抓不到。**沒跑這步就回報「完成」= 把驗證責任推給使用者**，違反 verify-after-write 原則。

**必跑流程**（任一未跑禁止回報任務完成）：

1. **Render → JPGs**（不是 optional）：
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/qa_visual.py <pptx_path> --out-dir jc_qa
   ```
   產 N 張 `slide-NN.jpg`（N = slide 總數）。

2. **逐張視覺檢查**：
   - **Claude 主執行緒親自 Read** 至少：cover / outline / 任何 case_findings (4-col) / 任何 literature_evidence (table) / references — 這幾類最容易爆版。
   - **派 1 個 general-purpose subagent**（Agent tool `model: sonnet`；版面細節 Haiku 易漏判）把剩下的 slide JPGs 一次看完，要求逐張回報 6 項缺陷檢查清單（見下）。
   - **不要靠 markitdown 文字 dump 判斷版面**——文字過 ≠ 版面過。

3. **6 項缺陷檢查清單**（subagent prompt 必含）：
   1. **Overflow**: 文字跑出 footer 線、右邊界、card 邊界
   2. **Cropping**: 字句被 box 邊界切斷（mid-word / mid-sentence）
   3. **Mis-alignment**: dot/marker 沒對到字、column 寬度不齊、heading vs bullet alignment 衝突
   4. **Excessive whitespace**: 大片空白（>1" 死區）→ 字可以放大
   5. **Font too small**: 看起來 < 10pt body 在簡報距離不可讀
   6. **Markdown artifact**: `• -` 雙標記、`**bold**` 沒解、`[N]` orphan 等

4. **如果 ≥ 1 張有 P1/P2 缺陷**：回到 Step 4 修 DATA 或 builder.py 修 layout，**re-render → re-QA → re-render** 直到通過。**不准把缺陷推給使用者**「自己開檔調」。

5. **內容層稽核** — 抽查 3–5 筆 PMID 是否能解析到對應文章，並終檢 Rule 1/3（`pptx-verify` skill 可做版面層自動 QA）。與 Step 6.1-6.4 的版面層 QA 互補。

6. **A4 handout chain (optional)** — QA 通過後問使用者「要不要產 A4 handout PDF？（slide + speaker notes 對照，給現場 cue card 用）」。`yes` → invoke `pptx-handout`：
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/../pptx-handout/scripts/build_handout.py \
       --pptx "<output.pptx>" \
       --output "<same folder>/handout_<stem>.pdf" \
       --layout portrait
   ```
   報告時把 handout pdf 路徑跟 pptx 並列。Skip 條件：< 50% slides 有 speaker notes（handout 下半會大半留白）。

**反例（不可重蹈）**: 曾有一次跳過 qa_visual.py、只看 markitdown，把「文字抓得到」當「版面 OK」，導致 user 開檔才看到 slide 2 outline 6 items 溢位、slide 4 timeline dot 偏移、slide 8/11/12 table 撞 footer、slide 5 Pathology `• -` 雙標記。第二輪才補做 qa_visual 並修。

#### Step 6.B — open-slide QA path

> 此 QA 不需登入（localhost dev server）→ 優先用內建 Browser pane（deck 必須經 dev server 服務，不能 `file://`）；有 Chrome MCP 也可用（選用）。兩者都沒有 → 只做 `pnpm build` 驗證並請使用者自行開瀏覽器檢查。

**必跑流程**：

1. **Build verify**：
   ```bash
   cd <output_parent_dir>/<slug>
   pnpm build           # → dist/ 全綠 = TS strict + Vite 都 pass
                        # Builder 已用 --use-pnpm 預裝，不需再 pnpm install
   ```
   Build fail → 回 Step 4 修 DATA 或 Step 5.B 修 builder。
   
   **前置一次性**：第一次跑此 skill 前，全域裝 open-slide CLI：
   ```bash
   npm install -g @open-slide/cli   # 已裝可跳過；builder 偵測到全域就用，否則 fallback npx
   ```

2. **Dev server + Chrome MCP navigate**：
   ```bash
   cd <output_parent_dir>/<slug> && pnpm dev > jc_dev.log 2>&1 &
   ```
   然後用瀏覽器工具 `navigate` 到 `http://localhost:5173/s/journal-club`，逐頁 `?page=N` 走過所有 slides（cover / outline / 每張 content / discussion_question / literature_evidence / takeaway / references / blank_teacher）。

3. **逐張視覺檢查 + subagent QA**：
   - **Claude 主執行緒親自 screenshot** 至少：cover / outline / 每張 case_findings（4-col） / 每張 literature_evidence（table） / references — 最容易爆版的類型。
   - **派 1 個 general-purpose subagent**（Agent tool `model: sonnet`；版面細節 Haiku 易漏判）把剩下 slides 一次看完，要求逐張回報 6 項缺陷檢查（同 Step 6.A，但語意換成 web layout）：
     1. **Overflow**: 文字跑出 1920×1080 canvas 邊界、撞 Footer
     2. **Cropping**: 字句被 Card 邊界 / `overflow: hidden` 切斷
     3. **Mis-alignment**: bullet `▸` 對不到字、column gap 不齊
     4. **Excessive whitespace**: 大片空白可放大字 / 增 padding
     5. **Font too small**: < 22pt body 在 1920 canvas 顯小
     6. **Markdown artifact**: 任何 `**bold**` / `[N]` 未解析、CJK 漏到 body

4. **Console clean check**：
   ```
   （內建 Browser 的 read_console_messages，或 Chrome MCP 的同名工具）onlyErrors=true
   ```
   任何 React warning / runtime error → 修。

5. **缺陷修法**：
   - JSX layout bug（位置 / 顏色 / size） → 改 `scripts/build_open_slide_deck.py` 對應 `render_<type>()` → 重跑 builder → 重 build → 重 navigate
   - DATA 內容問題（多 bullet / 長文字） → 改 `<work_dir>/jc_<slug>_data.py` → 重跑 builder
   - Theme palette 問題 → 改 `${CLAUDE_SKILL_DIR}/../notebooklm-pptx/lib/open_slide_builder/themes/<id>.md` + `.demo.tsx`（兩個檔同步改）→ 重跑 builder

6. **A4 handout 不適用** — open-slide 自己有 presenter mode 顯示 speaker notes，不需 pptx-handout chain。

7. **完成 handoff**：
   - 印 deck 路徑 / dev URL / build 指令
   - 告知 user 可以用 `pnpm dev` 在本機看、`pnpm build` + `dist/` 部署到 Vercel / Cloudflare Pages
   - 提醒：open-slide inspector + `/apply-comments` skill 可 inline 點按修改（dev server 內）

### Step 7 — Zotero Archiving（選用：只有你裝了 Zotero MCP 才跑）

把這次報告**實際引用**的文獻歸進 Zotero：母 collection（per report）+ 每個討論題一個 section 子夾。**只在 Step 6 QA 通過後跑。**

**Precondition / skip**：`zotero` MCP 未連線 OR 使用者說過「不用歸 Zotero / skip zotero」→ 印 `[Step 7] skipped` 後結束，不報錯。（pure Zotero，不接 EndNote。）

**7.1 產生歸檔計畫**（deterministic）：
```
python3 ${CLAUDE_SKILL_DIR}/scripts/zotero_plan.py <research_findings.json> <structured.json> \
    --topic "<DATA.meta.topic_title 或 paper title>" [--date <YYYY-MM>] \
    --out <work_dir>/jc_<slug>_zotero_plan.json
```
plan JSON（由共用 `case-discussion-pptx/lib/zotero_archive` 核心產生，per-skill adapter 在 `scripts/zotero_plan.py`）：`parent`(Journal Club) / `report_collection`(`<YYYY-MM> <topic>`) / `primary_paper` / `sections[]`(section_id + subfolder + papers) / `doi_less[]` / `orphan_sections[]` / `stats`。

**7.2 建/沿用 collection → show→confirm → 歸檔 → 索引**：照共用執行手冊 **`${CLAUDE_SKILL_DIR}/../case-discussion-pptx/lib/zotero_archive/EXECUTION.md`** 跑（create-or-reuse parent `Journal Club` → 一張 `section → papers` 表 hard-gate 確認 → lookup-before-add 逐篇歸檔 → `zotero_update_search_database` → 印 tree + skip 清單）。其中 jc-pptx 的 section = 討論題（primary→母夾、各 Q→子夾）；`orphan_sections` = citation 的 `used_in_questions` 指向不存在題號。

**邊界**：pptx pilot **純 Zotero、不接 EndNote 下游**（簡報非共編 Word）；Word 類 skill（academic-paper 等）才在收尾加 Better BibTeX → `/endnote-import`。只歸 `all_citations`（實際採用的），lit-review 沒採用的不歸。

## Slide Types (MVP)

見 `data_schema.md` 與 `templates/example_paper_data.py`。

| Slide type | 典型用途 |
|---|---|
| `cover` | 第 1 張，含 label / title / big word / presenter |
| `outline` | 5–7 項大綱 |
| `section_divider` | 章節分隔大字 |
| `background` | 背景 bullets |
| `paper_meta` | journal / year / design / funding / main finding |
| `pico` | PICO 2×2 + secondary outcomes |
| `methods` | design / n / inclusion / exclusion / endpoint / stats / follow-up |
| `results` | key_numbers 表格 + figure caption |
| `case_profile` | age / sex / CC / underlying (admission 路徑) |
| `case_timeline` | events list |
| `case_findings` | PE / lab / image / path 多欄 |
| `case_dx_mgmt` | active / underlying / orders / goals |
| `discussion_question` | Q 主題 + suggested minutes + audience prompts |
| `literature_evidence` | Q 對應的證據整合 + citation 表 |
| `takeaway` | 3-point 總結 |
| `references` | Vancouver / AMA / APA7 citation 列表 |
| `blank_teacher` | 討論 / Q&A 收尾 |

## Typical Slide Order (paper route, ~16 張)

```
1  cover
2  outline
3  background
4  paper_meta
5  pico
6  methods
7  results
8  discussion_question Q1
9  literature_evidence Q1
10 discussion_question Q2
11 literature_evidence Q2
12 discussion_question Q3
13 literature_evidence Q3
14 takeaway
15 references
16 blank_teacher
```

Admission route: 3 替換為 `case_profile`，4 為 `case_timeline`，5 為 `case_findings`，6 為 `case_dx_mgmt`。

## Scripts Reference

| Script | 用途 |
|---|---|
| `scripts/input_router.py` | 偵測 type → `intake.json` |
| `scripts/oe_summary_compactor.py` | OE artifact .txt → compact JSON（主線讀） |
| `scripts/research_synth.py` | 合併 OE + subagent JSON → `research_findings.json` |
| `scripts/refs_format.py` | citation dict → Vancouver / AMA / APA7 string |
| `scripts/qa_visual.py` | pptx → pdf → jpg（Step 6.A） |
| `scripts/build_open_slide_deck.py` | DATA dict → open-slide React deck scaffold + slides/journal-club/index.tsx（Step 5.B） |
| `scripts/zotero_plan.py` | research_findings.json + structured.json → Zotero 歸檔計畫 JSON（Step 7） |

## Open-slide themes

3 個 open-slide theme bundle 隨 `${CLAUDE_SKILL_DIR}/../notebooklm-pptx/lib/open_slide_builder/themes/` 提供，對應 `templates/themes.py` 的 3 個 pptx theme（每個 bundle：`<id>.md` 文件 + `<id>.demo.tsx` 預覽）。`build_open_slide_deck.py` 自動複製進 scaffolded deck 的 `themes/`。

`render.py` 內建 Rule 1 pre-flight（掃 slide body 有無 CJK）。用 `--skip-rule1-check` 旁路（僅限 proper noun case label）。

## Prompts

- `prompts/paper_extract.md` — paper / admission / freeform structured extraction
- `prompts/discussion_questions.md` — 3–5 題生成 prompt（audience: attending / fellow）
- `prompts/subagent_pubmed.md` — PubMed subagent prompt template（含避免重複查詢機制）

## Dependencies

- `pip install python-pptx lxml`（pptx 路徑必需）
- 選用 MCP：PubMed（`mcp__pubmed__pubmed_*`，建議）、OpenEvidence、Zotero
- 選用 skills（同套件）：`phi-deid`、`marker-pdf-converter`（PDF 轉文字）、`pptx-verify`、`pptx-handout`
- open-slide 路徑（選用）：Node 18+、pnpm、`npm i -g @open-slide/cli`
- `render.py` 需要同套件的 `${CLAUDE_SKILL_DIR}/../case-discussion-pptx/lib/pptx_launder.py`（請保持兩個 skill 資料夾並排）

## Example

```bash
python3 ${CLAUDE_SKILL_DIR}/render.py ${CLAUDE_SKILL_DIR}/templates/example_paper_data.py example_jc.pptx
python3 -m markitdown example_jc.pptx | head -30
```

Expected: 16 slides, theme `journal_classic`, body English-only, notes bilingual.

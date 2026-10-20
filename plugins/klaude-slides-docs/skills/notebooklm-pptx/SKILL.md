---
name: notebooklm-pptx
description: "Topic-agnostic PPTX builder: the user drops in ANY sources (PDFs, notes, URLs, pasted text, or a NotebookLM notebook), states the topic / angle / audience, and the skill structures the content and renders a designed .pptx (or an open-slide React deck). Use when the user says: 把這些資料做成簡報, NotebookLM 做投影片, 資料丟進去指定主題做 pptx, 用這些來源做 PPT, make slides from these sources, NotebookLM to PPTX, turn my notes into a deck, 製作投影片, or any request to turn source material into a presentation on a chosen topic."
---

# Sources → Topic → PPTX

Turn any source material into a polished deck. The topic is whatever the user says it is; nothing is assumed (ethics, medicine, business, tech, teaching... all equal). Optional case / discussion-question / analysis-card layouts exist for decks that need them.

## When to Use

- User gives sources (files, links, notes, pasted text, a NotebookLM notebook) and asks for a presentation
- User specifies the topic / angle / audience / length after supplying the sources
- User wants a teaching, seminar, report or briefing deck with a consistent design

## Workflow

### Step 1: Collect sources, then the brief

1. Gather the sources the user provides (read PDFs / notes / URLs; if a NotebookLM notebook, see "Fetching from NotebookLM").
2. Ask (or infer from the message) the **brief**: topic or angle, audience, approximate length, language, and whether cases / discussion questions / analysis cards are wanted. If not stated, default to a plain explainer: title, objectives, content sections, summary, references.
3. Structure the CONTENT object (see schema below), using only information supported by the sources; note the source for each claim in `references`.

#### CONTENT schema (all fields optional except `title`)
- `title`, `subtitle`, `footer`, `author`, `outputPath`
- `objectives`: 2–5 strings
- `cases`: optional list of sections; each has `title`, `subtitle`, `description` (bullets), `coreIssue` (one line), `discussionQuestions` (2–4), `analysis` (1–4 items `{label, text}` with labels of your choice, e.g. 背景/風險/做法/結果 or any framework the topic calls for), `suggestion`, `source`
- `summaryPrinciples`: 3–5 takeaways `{title, desc, iconName}`
- `guidelines` (+ `guidelinesTitle`, `guidelinesSubtitle`, `guidelinesFootnote`), `analysisTitle` / `analysisSubtitle`, `references`

If the user wants content from NotebookLM, fetch it first (选用 `notebooklm-py`, see below), then proceed.

### Step 1.5: Output mode — `.pptx` vs open-slide React deck

Ask via `AskUserQuestion`:
- **`.pptx`（傳統可分享）** — 一個 .pptx 檔可寄出。預設。
- **open-slide React deck** — 高質感 motion / web 部署 / Design panel 即時調色，要 dev server iteration + 部署 hosting。

預設走 Step 2.A（.pptx）。選 open-slide 走 Step 2.B。

### Step 2.A: Generate the PPTX (default)

Use the bundled `scripts/generate_pptx.js` template as a foundation. The script contains all the design helpers — you should **not** write PptxGenJS code from scratch. Instead:

1. Read `scripts/generate_pptx.js`
2. Adapt the `CONTENT` object at the top of the script with the user's actual content
3. Run the script with `NODE_PATH="$(npm root -g)" node <path-to-script> [output.pptx]`（沒給路徑就輸出到目前資料夾的 `output.pptx`）

### Step 2.B: Generate the open-slide React deck

Write the populated CONTENT to a runner file (same JS shape as 2.A) and run:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/build_open_slide_deck.py \
    /path/to/<runner>.js \
    /path/to/output_parent_dir/
```

Builder:
- Uses `node + vm` to load CONTENT (works even when the runner doesn't `module.exports`)
- Maps CONTENT → open-slide DATA (cover / objectives / case_story per case / question / analysis cards / summary_grid / guidelines / references / blank_teacher)
- Reuses the bundled `${CLAUDE_SKILL_DIR}/lib/open_slide_builder` infra (themes, cover, chrome helpers) and includes its own `case_story` / `question` / `analysis` renderers
- Default theme `journal_classic`; override at DATA level if needed
- Runs `pnpm build` to verify TS strict

Output: `<output_parent>/<topic_slug>/`; run `pnpm dev` → `http://localhost:5173/s/<slug>`.

For visual QA of the open-slide deck: run `pnpm dev`, open `http://localhost:5173/s/<slug>` in a browser (built-in Browser pane or any browser) and screenshot each page; `file://` is blocked, so the deck must be served by the dev server.

The script automatically builds:
- Title slide (dark background with centered icon and title)
- Learning objectives slide (numbered card layout)
- For each case: description → discussion questions → optional analysis cards (1-4 columns)
- Summary slide (dark background with icon-labeled takeaway cards)
- Guidelines slide (numbered steps)
- References slide

### Step 3: Verify（**Hard gate — 不准跳過**）

`markitdown` 只看得到文字，**完全看不到版面**。row overflow、footer collision、column mis-align、`• -` 雙標記、`**bold**` 沒解 — 純文字檢查全部抓不到。**只跑 markitdown 就回報完成 = 把驗證責任推給使用者**。

**必跑兩段**：

1. **Text**: `python3 -m markitdown <output.pptx>` — content 齊不齊、排序對不對。

2. **Visual**（必做）:
   ```bash
   cd /tmp && rm -f slide-*.jpg
   soffice --headless --convert-to pdf "<output.pptx>"
   pdftoppm -jpeg -r 110 <output.pdf-name> slide
   ```
   Claude 主執行緒親自 Read cover + 任何 table-heavy slide；剩下派 sub-agent 看，檢 6 項：overflow / cropping / mis-alignment / whitespace / font<10pt / markdown artifact。≥ 1 張 P1/P2 缺陷 → 回 Step 2 修 + re-render，**不甩鍋使用者**。

**反例**: 曾有投影片 skill 跳過 visual QA，使用者開檔才發現多項版面缺陷；同類問題這個 skill 也會中。

## Fetching from NotebookLM（選用：需自行安裝 `pip install notebooklm-py` 並完成 Google 登入；沒有就直接貼內容給 Claude）

If the user's content is in a NotebookLM notebook, fetch it first:

```python
import asyncio
from notebooklm import NotebookLMClient

async def main():
    client = await NotebookLMClient.from_storage()
    async with client as c:
        # List notebooks to find the right one
        notebooks = await c.notebooks.list()
        for nb in notebooks:
            print(f"ID: {nb.id} | Title: {nb.title}")

        # Ask for structured content, steered by the user's topic / angle
        result = await c.chat.ask(NOTEBOOK_ID,
            "請用繁體中文，依以下主題與角度整理這個筆記本的重點：<使用者指定的主題、角度、聽眾>。"
            "輸出：1) 建議的簡報大綱 2) 每個段落的重點與來源 "
            "3) 若適合，可用的案例與討論問題 4) 結論與關鍵 takeaways")
        print(result.answer)

asyncio.run(main())
```

Then integrate the responses into the CONTENT structure for the PPTX script.

## Design System

The bundled script uses a cohesive, neutral academic/business design system:

### Color Palette
| Role | Hex | Usage |
|------|-----|-------|
| Dark BG | `1B3A4B` | Title & summary slides |
| Primary | `065A82` | Headers, number circles, top bars |
| Teal | `1C7293` | Accent bars, decorative elements |
| Light BG | `F0F5F9` | Content slide backgrounds |
| Coral Red | `D94F5C` | Emphasis callouts, warnings |
| Sage Green | `2B8A6E` | Suggestion boxes, positive outcomes |
| Gold | `D4A843` | Discussion question boxes |

### Component Library
- **addHeader(slide, title, subtitle)** — consistent top bar + title + separator
- **addCaseCard(slide, points, startY, height)** — teal-accented bullet card
- **addDiscussionBox(slide, questions, startY, height)** — gold-bordered question box
- **addAnalysisCards(slide, items, startY)** — 1–4 column analysis cards with your own labels
- **addSuggestionBox(slide, text, startY)** — green suggestion banner

### Typography
- Titles: Georgia, 26-40pt, bold
- Body: Calibri, 11-16pt
- Captions: Calibri, 9-10pt, muted

### Layout Rules
- 16:9 aspect ratio (10" x 5.625")
- 0.6" side margins
- Cards use factory-created shadows (never reuse shadow objects — PptxGenJS mutates them)
- Icons rendered via react-icons + sharp (SVG → PNG base64)

## Customization

The script is designed to be adapted. Common modifications:
- **Analysis labels**: set `analysis: [{label, text}]` per case; colors cycle through `ANALYSIS_COLORS`
- **Different language**: Change all text strings; the layout is language-agnostic
- **More/fewer cases**: Add or remove case slide groups; sections may omit discussion questions or analysis cards
- **Custom color palette**: Modify the `C` object at the top of the script
- **Additional slide types**: Use the existing helpers as building blocks (e.g., timeline cards, two-column comparison)

## Dependencies

```bash
npm install -g pptxgenjs react-icons react react-dom sharp
pip install "markitdown[pptx]"  # for verification
brew install --cask libreoffice   # soffice, for visual QA render
brew install poppler              # pdftoppm
brew install node pnpm            # node for generate_pptx.js; pnpm only for open-slide mode
```

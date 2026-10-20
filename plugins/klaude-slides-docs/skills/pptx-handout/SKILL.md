---
name: pptx-handout
description: "Build an A4 handout PDF from any .pptx (slide thumbnail + speaker notes per page); any pptx-generation skill can chain into it. Trigger when user mentions: A4 handout, pptx handout, slide + notes 對照, 把 pptx 印成講稿, slide cue card PDF, 投影片講稿合一, /pptx-handout, /handout."
---

# pptx-handout — PPTX → A4 Handout PDF

對任何 `.pptx` 產出 A4 直式（或橫式）handout PDF — 每張 slide 一頁，上半 slide 縮圖、下半 speaker notes，CJK-safe。

> **設計定位**：跟 `pptx-verify`、`md-to-pdf` 同類的 **generic post-processing wrapper**。本 skill 不知道 pptx 怎麼生成、不改 pptx body、只負責把 (slides + notes) 兩種既有資料變成可列印 / 帶上場的 A4 PDF。

## When to Use

- 使用者打 `/pptx-handout <path>` / `/handout <path>`
- 使用者說：「做成 A4 handout」「slide + notes 對照印出來」「把 pptx 變成講稿 PDF」「投影片配講稿 cue card」
- 任何 pptx-generation skill build 完，使用者點頭要 handout 時 chain 進來（contract 見下「Delegation Contract」）
- 拿到別人給的 .pptx 想印出來看 + 帶現場（speaker notes 印在 slide 下方）

## What it produces

A4 PDF（預設直式）：
- 每頁 1 張 slide
- Header：`Slide N / total · <title>` + 暗紅 rule line
- Top ~45%：slide JPG（aspect-preserving、置中）
- Bottom ~50%：speaker notes（9.5pt CJK font、word-wrap）

## Workflow

### Step 1：定位 pptx

- 使用者顯式指定路徑 → 用之
- 沒指定 → 在當前 cwd 找最新 .pptx；多個用 `AskUserQuestion` 列前 4 個讓使用者選
- 路徑必須是絕對路徑、檔案必須存在

### Step 2：決定輸出路徑

- 預設：`<同目錄>/handout_<pptx-stem>.pdf`
- 使用者指定其他路徑 → 用之
- 路徑已存在 → 直接覆寫（不問；要保留就改檔名跑兩次）

### Step 3：選 layout（可選；預設直式）

絕大多數情況 portrait 適合（多 notes、少 slide 邊距浪費）。如果使用者顯式講「橫式」「landscape」「寬版」才改。

可選：
- `portrait`（預設）— image 佔 45%、notes 50%
- `landscape` — image 佔 55%、notes 35%（slide 寬大、notes 較少）

### Step 4：跑 build_handout.py

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/build_handout.py \
    --pptx "<absolute pptx path>" \
    [--output "<absolute pdf path>"] \
    [--layout portrait|landscape] \
    [--font "<absolute ttf path>"] \
    [--no-notes-message "(此頁無備忘稿)"]
```

Script 內部流程：
1. `soffice --headless --convert-to pdf` 把 pptx → PDF
2. `pdftoppm -jpeg -r 100` PDF → 一張 JPG/slide
3. python-pptx 抽 title + speaker notes
4. reportlab Platypus 組 PDF — 每頁一個 PageTemplate，header 用 `onPage` callback 畫
5. CJK font 自動偵測（PingFang → STHeiti → Hiragino → STSong-Light CID fallback）

### Step 5：回報

```
✓ handout 寫到：<abs.pdf>（XXX KB · N 頁）
   你可以列印（A4 1 頁 = 1 slide + 講稿）或當電子 cue card
```

如果某些 slide 沒 speaker notes：印出哪幾張，建議使用者補。

## Delegation Contract — 給其他 pptx skill 串接用

任何 pptx-generation skill 想自動產 handout，invoke 本 skill 並傳：

```json
{
  "delegated_from": "<calling-skill-name>",
  "pptx_path": "<absolute path to built .pptx>",
  "preferred_output_path": "<absolute path>",  // optional; default <same folder>/handout_<stem>.pdf
  "layout": "portrait",                         // optional; default portrait
  "skip_user_questions": true                   // skip Step 1 + Step 3 intake
}
```

本 skill 偵測到 `delegated_from` → 跳 Step 1/3 的 AskUserQuestion，直接走 Step 4 build。

**回傳給 caller**：
- stdout 最後一行 = handout PDF 絕對路徑
- caller 把該路徑加進最終 report 給使用者

## 何時不該做

- pptx 完全沒 speaker notes（每張都空）→ handout 等於把 pptx 印成 PDF 加標題，沒意義；建議 pptx-handout 跳掉、直接 `soffice --convert-to pdf`
- 超過 100 張 slide → handout PDF 會超大（每張 ~80 KB JPG × 100 = ~8 MB）；先問使用者要不要 split 或降 dpi
- pptx 含 animation / video → handout 只抓 final frame，動畫資訊 lost；本 skill 不警告（屬於 pptx 本質限制）

## Dependencies

```bash
pip install python-pptx reportlab Pillow
brew install poppler  # for pdftoppm
brew install --cask libreoffice  # soffice
# 中文字型：macOS 內建 PingFang 即可；Linux/Windows 請裝 Noto Sans CJK 並用 --font 指定
```

## Design choices（紀錄）

- **A4 直式**：講者 cue card 慣例；landscape 太寬手拿不便
- **Image top + notes bottom**（不左右）：speaker notes 通常較長，垂直流好讀
- **CJK font auto-detect**：使用者跨 case 用繁中講稿，font fallback 必須無痛
- **reportlab Platypus**（非 canvas 手繪）：自動 word wrap、避免 char 斷在 mid-word
- **Output 預設次目錄**：`handout_<stem>.pdf` 跟 source pptx 同 folder，使用者好找
- **Header onPage callback**（非 story Spacer）：避免 header 撞到 image / notes 邊界

## 相關 skill

| Skill | 關係 |
|---|---|
| `pptx-verify` | 姊妹 post-processor — verify 跑 visual QA、handout 出列印 PDF；常一起 chain |
| `case-discussion-pptx` | 完成後可選 chain（使用者點頭即跑） |
| `journal-club-discussion-pptx` | 完成後可選 chain |
| `notebooklm-pptx` | 完成後可選 chain |
| `md-to-pdf` | 跟 handout 互補 — md→PDF（純文字場景），handout = 帶 slide 圖（簡報場景） |

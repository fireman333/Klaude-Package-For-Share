---
name: md-to-pdf
description: "Merge one or more markdown files into a polished PDF via pandoc + typst, with CJK-safe font stack, 3 typst presets (report / handoff / textbook), in-document TOC AND clickable PDF outline (sidebar bookmarks). Use when the user mentions: md to pdf, markdown to pdf, merge md files, export notes to pdf, build pdf from markdown, pdf with bookmarks, pdf with outline, 合併 md 成 pdf, md 轉 pdf, markdown 出 pdf, 把筆記做成 pdf, 把報告轉 pdf, pdf 加目錄, pdf 加書籤, pdf 加 outline, /md2pdf, /md-to-pdf."
---

# md-to-pdf

把一或多個 markdown 檔合併成一份 PDF。引擎為 `pandoc (md → typst) → typst compile`（不需要 LaTeX、不需要 Chrome），中文字型走 PingFang TC fallback chain，確保繁體中文不亂碼。內建 3 個 typst preset 對應 3 種輸出語境。

**為什麼用 typst（不是 Chrome headless）**：Chrome `--print-to-pdf` 產的 PDF 文字選取盒高度異常 —— 在 Preview / PDF Expert 選一行字會跳到上下多行、反白一大塊（降 line-height、移除 tagged tree 都無效）。typst 產的是正確的 per-line 文字 run，選取乾淨。**不要回退到 Chrome pipeline**。

**兩層導覽都有，且 typst 原生產生**（不需 PyMuPDF post-process，書籤頁碼永遠精準）：
- **In-document TOC**（pandoc `--toc`）— 內文前段，列出到 `--toc-depth`，clickable
- **PDF outline / bookmarks**（typst 從 heading 自動產生 `/Outlines`）— 左側側邊欄樹狀導覽，深度同 `--toc-depth`，所有 PDF reader 都看得到

## When to use

- 多份 .md 整合成一份報告（例：分析報告資料夾、SR/MA 中間 handoff、課程講義集）
- 單一 .md 出 PDF 給人看（不想用 markdown viewer / GitHub render）
- 需要繁體中文、表格、code block 都正確渲染、**且文字可正常選取**的 PDF
- **不適用**：純 HTML 排版（用 quarto）、學術 LaTeX 模板、PDF 操作如合併分割（用內建 pdf skill 或 pdf-split-by-outline）

## Workflow

### Step 0: Detect cwd context

如果 cwd 已有明顯 input（資料夾內 `.md` 多份且 README.md 列出順序），直接列出偵測結果讓使用者確認，不必逐項問。

### Step 1: Gather inputs (AskUserQuestion if any missing)

問使用者：

1. **Input** — 二擇一：
   - `--dir <path>` 整個資料夾（依 README.md 順序，或字典序，或使用者指定 order）
   - `--files "f1.md f2.md ..."` 顯式列檔
2. **Title** — PDF 封面與檔名用，繁中可
3. **Style preset** — `report`（學術 navy 邊框、預設）/ `handoff`（緊湊純文字）/ `textbook`（大字適合講義）
4. **Output path**（可省，預設 `<input-dir>/<title>.pdf`）
5. **Order**（僅 `--dir` 模式問）— 三選一：
   - `readme`（讀同目錄 README.md 的 list 順序，**預設**）
   - `alpha`（檔名字典序）
   - `manual`（使用者貼一份排序清單）

不要 silent 選預設；至少要列「我打算這樣做：dir=X、order=readme、style=report、title=Y」讓使用者確認。

### Step 2: Validate inputs

- 所有 `.md` 檔存在且可讀
- README.md 順序模式 → README 的 list 必須能對應到實際 `.md` 檔案；對不上就 fallback `alpha` 並告知使用者
- Output path 父目錄存在
- `typst` 存在（`command -v typst`）；缺則 `brew install typst`（單一 binary，~40 MB，不要靜默裝）
- `pandoc` 存在（`command -v pandoc`）；缺則 `brew install pandoc`

### Step 3: Build

呼叫 `${CLAUDE_SKILL_DIR}/scripts/build_pdf.sh`（CLI 介面跟舊版完全相同，dependents 不受影響）：

```bash
${CLAUDE_SKILL_DIR}/scripts/build_pdf.sh \
  --dir "<dir>" \
  --title "<title>" \
  --style "<report|handoff|textbook>" \
  --order "<readme|alpha|manual>" \
  [--toc-depth N]   # 0 = 不要內文 TOC + 不要書籤；預設 2（H1 + H2）
  [--output "<path>"] \
  [--files "f1.md f2.md ..."]
```

Script 內部：
1. Merge `.md`：cover (pandoc metadata title) + 各檔內容（`#pagebreak()` 分頁）→ `_merged.md`
2. `pandoc -t typst --toc --toc-depth=N` 出 `_merged.typ`
3. `scripts/inject_typst_style.py` 注入 preset show-rules（`presets/<style>.typ`）+ 通用修正：
   - 表格被 pandoc 包成 `align(center)` → 改 `align(left)`
   - TOC 標題本地化為繁體「目錄」（typst lang:zh 預設給簡體「目录」）
   - 書籤深度綁 `--toc-depth`：比 toc-depth 更深的 heading 設 `outlined: false`（留在內文、不進書籤）
4. `typst compile` 出 PDF —— in-document TOC + 側邊欄書籤都是 typst 原生產生
5. `_merged.md` / `_merged.typ` 留在 input 目錄供 debug

**typst preset 怎麼運作**：每個 `presets/<style>.typ` 是一段 typst `#set` / `#show` rules（字體 + lang:"zh" region:"tw" + 表格框線/斑馬紋 + heading 配色）。在 `#outline()` 前注入，所以 heading show-rules 對內文與 TOC 都生效。CJK 換行靠 `lang: "zh"`（沒設的話表格 cell 內中文不斷行會溢出）。

### Step 4: Verify output

- `pdfinfo` 檢查頁數合理（每篇 .md 平均 ≥ 1 頁；遠低於 1 → 可能 markdown 沒 render，回 Step 3 debug）
- 檔案大小 > 10 KB
- **驗 outline 條目 > 0**：`python3 -c "import fitz; print(len(fitz.open('<pdf>').get_toc()))"`（build_pdf.sh 末尾已印 `outline: N entries`）
- 主動回報路徑用 markdown link 格式（`[title](file://...)`）讓使用者點開

### Step 5: Offer cleanup

問使用者要不要刪 `_merged.md` / `_merged.typ`。預設保留供 debug；明確同意才刪。

## Style presets

| Preset | 適用 | 字型大小 | 風格 |
|---|---|---|---|
| `report` | 研究報告、趨勢分析、課堂報告 | 10.5pt | Navy 邊框、表格淡藍條紋、學術風 |
| `handoff` | Session handoff、會議紀錄、流水帳 | 10pt | 純黑白、緊湊、無多餘 styling |
| `textbook` | 講義、教材、自學筆記 | 12pt | 大字、米色底、H1 雙線、適合長時間閱讀 |

typst preset 檔在 `scripts/presets/*.typ`，可直接編輯（show-rules，所見即所得）。改色/字級不需碰 build_pdf.sh。

## Error Handling

- **typst missing** → `brew install typst`（不要自己跑 `brew` 沒問過）
- **pandoc missing** → `brew install pandoc`
- **README order mismatch** → fallback alpha + 告知使用者哪幾個檔對不上
- **PDF 0 頁或 < 10 KB** → 看 typst compile stderr（通常是某個 heading/table 語法被 inject 後壞掉，檢查 `_merged.typ`）
- **中文亂碼 / 變方框** → 確認 `typst fonts | grep PingFang` 看得到字體；preset 的 font fallback 第一中文順位是 `PingFang TC`（macOS 內建）
- **表格 cell 中文溢出 / 沒換行** → preset 少了 `#set text(lang: "zh")`；CJK 斷行靠它
- **TOC 標題顯示簡體「目录」** → inject 腳本的 `title: [目錄]` 替換沒生效，檢查 pandoc 是否仍輸出 `title: auto,`
- **outline = 0 entries** → markdown 沒有 `#`/`##` heading，或 `--toc-depth 0`。typst 原生產 outline，不會有「heading 在 PDF 找不到」的舊問題
- **`unknown variable: horizontalRule` / `expected function, found content` 指向 `#divider()`** → **inject 腳本已自動修**，注入訊息會印 `divider polyfill repaired (N)`。成因：markdown 含 `---` 分隔線且 typst < 0.15 時，pandoc 產的 polyfill 一行內有兩個錯——定義為 `horizontalrule`（小寫 r）卻引用 `horizontalRule`（大寫 R），且 `horizontalrule` 是 content 卻被當函式呼叫。日後若再出現，檢查 `inject_typst_style.py` 的 `_BROKEN_DIVIDER_POLYFILL` regex 是否還比對得到 pandoc 的新寫法。（pandoc 3.10.1 + typst 0.14.2 實測）
- **`label <N> does not exist in the document`** → **不是 pipeline 的錯，是來源 markdown 有懸空錨點**（章內目錄寫 `[標題](#3)` 但檔內無對應 anchor）。合併輸出本就有全域 TOC 與側邊欄書籤，章內目錄多餘：把那些連結降為純文字即可（`re.sub(r'\[([^\]]+)\]\(#\d+\)', r'\1', text)`）。**修來源檔，不要改 pipeline**

## Common Rationalizations

| Rationalization | Rebuttal |
|---|---|
| "Order 預設 alpha 應該夠用" | 趨勢分析這類有 README 的場景，alpha 會把「外科」排在「內科」前面；先讀 README 是對的 |
| "Title 從目錄名推就好" | 目錄名常是 `_analysis` / `output` 這類佔位，PDF 封面不能用；一定要問 |
| "Style 用預設 report 都對" | 純 handoff 用 report 那種 navy 重 styling 反而不對；要先看用途再選 preset |
| "PDF 跑出來就交差" | 跑出來不等於對。一定要 `pdfinfo` 看頁數 + outline 條目數，不到預期就 debug |
| "選取爛一點沒差，反正能看" | ❌ 使用者明確抱怨過 Chrome 版選字跳行。typst 就是為了這個換的，不要為了省事退回 Chrome |
| "我寫了自己的 wrapper / batch / parallel loop，verify step 可以跳" | **❌ 多次出包 pattern**。Wrapper 必須 replicate outline-count 驗證。看 PDF 檔存在 + size > 0 不夠 — outline = 0 PDF 還是會生、但側邊欄空白 |
| "改 preset 樣式要動 build_pdf.sh" | 不用。樣式全在 `presets/*.typ` 的 show-rules，改那邊就好；build_pdf.sh 只管 pipeline |

## Boundaries

- **Always**: 跑完用 `pdfinfo` 驗證頁數 + 驗 outline 條目 > 0（build_pdf.sh 末尾已印）；用 markdown link 格式回報路徑 + outline 條目數；保留中間檔（`_merged.md` / `_merged.typ`）供 debug
- **Wrapper 模式**: 自寫 batch / parallel wrapper 包 `build_pdf.sh` 時，**MUST** 在 wrapper 對每個產出 PDF 跑 outline 條目檢查；不能只信 `build_pdf.sh` exit 0 + 檔案存在
- **Ask first**: 覆蓋既有 PDF；刪中間檔；裝缺失的 dep（`brew install typst` / `brew install pandoc`）
- **Never**: 直接修 source `.md`；退回 Chrome `--print-to-pdf` pipeline（選取會壞）；用 LaTeX engine；silent 跳 Step 1 的 input 問題；**看到 `outline = 0` 還宣告 PDF 完成**

## Files

```
${CLAUDE_SKILL_DIR}/
├── SKILL.md
└── scripts/
    ├── build_pdf.sh            # main pipeline: merge → pandoc(typst) → inject → typst compile
    ├── inject_typst_style.py   # 注入 preset show-rules + CJK/table/outline-depth 修正
    ├── presets/
    │   ├── report.typ          # navy 學術風（預設）
    │   ├── handoff.typ         # 黑白緊湊
    │   └── textbook.typ        # 大字米色講義風
```

## Dependencies

字型：預設 preset 用 macOS 內建 PingFang TC。Linux/Windows 請安裝 Noto Sans CJK TC，並把 `scripts/presets/*.typ` 的 font 清單改成 `"Noto Sans CJK TC"`；`build_pdf.sh` 也要加對應 `--font-path`。

- `pandoc` (≥ 3.0) — `brew install pandoc`
- `typst` (≥ 0.12) — `brew install typst`（單一 binary）
- 選用 `pymupdf`：`pip install pymupdf`（僅供 outline 條目驗證）
- `python3` — 標準庫即可跑 inject 腳本；`pymupdf`（任一 system python）僅用於末尾 outline 條目驗證，缺了不影響出 PDF

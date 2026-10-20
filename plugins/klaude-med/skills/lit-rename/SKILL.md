---
name: lit-rename
description: |
  Batch rename PDF literature files to year_author_title format (e.g., 2022_Chang_Factors_affecting_outcomes_CA_TTM.pdf).
  
  Trigger this skill whenever the user wants to:
  - Rename PDFs to year_author_title format
  - Organize literature files by year/author
  - Clean up messy PDF filenames in a research folder
  - Convert DOI-based or opaque PDF names to readable format
  
  Trigger phrases: /lit-rename, /文獻重命名, rename literature files, 整理文獻檔名, 把文獻改成年份作者標題格式, rename pdfs to year author title, organize pdf filenames
---

# lit-rename: 文獻批次重命名

需求：Python 3；`pypdf`（`pip install pypdf`，供讀 PDF 第一頁）；macOS 的 Spotlight metadata（`mdls`）為加分項，沒有也能跑。

將資料夾內的 PDF 論文檔案統一重命名為 `year_author_title` 格式。

## Workflow

### Step 1: 確認目標目錄

若使用者未指定目錄，詢問目標目錄路徑。支援遞迴（子資料夾）或僅限頂層，預設遞迴。

### Step 2: 執行 metadata 萃取腳本

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/extract_metadata.py "<目錄路徑>"
```

腳本會輸出：
- 每個 PDF 的建議新檔名
- 無法自動判斷的檔案列表（需人工補充）
- 重複檔案警告

### Step 3: 確認對照表

將腳本輸出整理為表格呈現給使用者：

| 原始檔名 | 建議新檔名 | 狀態 |
|---------|-----------|------|
| NEJMoa2208687.pdf | 2022_Kjaergaard_BP_targets_comatose_survivors_CA.pdf | ✓ 自動 |
| my_notes.pdf | （略過：無 journal metadata） | ⚠ 略過 |

讓使用者確認或修改後再執行。

### Step 4: 執行重命名

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/rename_pdfs.py "<目錄路徑>" "<對照表 JSON 路徑>"
```

或直接用 Python `os.rename()` 執行對照表中的 rename。

### Step 5: 處理重複檔案

若偵測到相同論文（相同 title + author + year）出現在不同子資料夾或以不同檔名存在，建議用 `osascript` 移至 Trash：

```python
import subprocess
subprocess.run(['osascript', '-e', f'tell app "Finder" to delete POSIX file "{path}"'])
```

---

## Metadata 萃取邏輯（優先順序）

### 1. macOS `mdls`（最快，不需讀 PDF）

```bash
mdls -name kMDItemTitle -name kMDItemAuthors -name kMDItemDescription "<file>"
```

取 `kMDItemTitle` 作為論文標題，`kMDItemDescription` 通常含有 journal + DOI + year 資訊。

**判斷為無效 metadata 的條件**：
- `kMDItemTitle = (null)` 或 title 是軟體名稱（如 "Thomson", "Adobe InDesign..."）
- 這種情況進入下一層

### 2. `pypdf` 讀取 page 0 文字

```python
import pypdf
reader = pypdf.PdfReader(path)
text = reader.pages[0].extract_text()[:800]
```

從開頭文字中找出：
- 論文標題（通常是大字體的第一段落或全大寫行）
- 第一作者姓名
- 年份（搜尋 4 位數字 + 月份/期刊名組合）

### 3. 由檔名推斷（fallback）

支援的檔名模式：
- `author-et-al-YEAR-title-words.pdf` → 取 author, year, title
- `YEAR Author, et al.pdf` → 取 year, author（title 需從 PDF 取得）
- `l%C3%BCsebrink-...` → URL decode 後解析

---

## 重命名格式規則

```
YEAR_Lastname_Short_Title_Keywords.pdf
```

- **YEAR**: 4 位數字
- **Lastname**: 第一作者 last name，保留連字號（如 `Bro-Jeppesen`），去除 Jr/Sr
- **Title**: 截斷至 ≤50 字元，保留關鍵醫學術語，空格→底線，去除冠詞 (a/the/an)
- **副檔名**: 統一 `.pdf`（修正 `.pdf.pdf` 雙重副檔名）

### 標題截斷原則

- 保留疾病名、治療名、關鍵比較（如 `33C_vs_36C`）
- 刪除期刊固有的修飾語（"A study on...", "Investigation of..."）
- 保留縮寫（TTM, OHCA, IHCA, CPR, AHA, ERC, TIMECARD）

---

## 不重命名的例外清單

以下類型的檔案**略過**，不做 rename：
- 資料夾
- `.docx`, `.xlsx`, `.pptx`（非 PDF）
- **使用者自建整理文件**判斷標準：
  - 無 `kMDItemDescription` 中的 journal/DOI 資訊
  - 且檔名為中文或含「整理」「筆記」「研究」等關鍵字
  - 且 `pypdf` page 0 無明確作者列表格式
- 從問答工具匯出的查詢結果（檔名含「|」+ 問題句）

---

## 注意事項

- **特殊字元檔名**：URL-encoded（`%C3%BC`）在 macOS 上可能以字面字元存在磁碟，`os.rename()` 需用 `ls` 取得精確檔名再操作
- **ü / ö 等特殊字母**：直接保留在新檔名中（如 `Lüsebrink`），macOS 支援
- **確認後才執行**：永遠先呈現對照表給使用者確認，不要靜默執行

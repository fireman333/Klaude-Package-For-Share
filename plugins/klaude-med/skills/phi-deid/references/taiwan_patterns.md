# Taiwan PHI Regex Catalog

本文件列出 `patterns.py` 使用的每一條 regex + 設計 rationale。閱讀順序：由左至右 = 從最確定到最模糊的匹配，Claude / 使用者 debug 偽陽／陰性時可對照此表。

## 結構化 ID

### NATIONAL_ID — 身分證字號

```regex
(?<![A-Za-z0-9])[A-Z][12]\d{8}(?![A-Za-z0-9])
```

- 開頭大寫字母 + 1 或 2 + 8 位數字。
- `(?<![A-Za-z0-9])` / `(?![A-Za-z0-9])`：前後都不可接 alphanumeric，避免匹配 `XA123456789YB`（醫囑編號片段）中的子字串。
- 範例：`A123456789` ✓、`a123456789` ✗（首字必須大寫）、`A123456789ABC` ✗（後面還接字母）。

### UI_NUMBER — 外籍統一證號

```regex
(?<![A-Za-z0-9])[A-Z](?:[89]|[A-D])\d{8}(?![A-Za-z0-9])
```

- 同時涵蓋新制（`[89]` 第 2 碼）與舊制（`[A-D]` 第 2 碼）。
- 舊制會與身分證格式衝突嗎？不會：身分證第 2 碼是 `[12]`，不是 `[A-D]` 或 `[89]`，兩者互斥。

### PHONE_MOBILE — 手機

```regex
(?<!\d)09\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)
```

- 09 開頭 + 8 位數字，中間可選 `-` 或空白。
- `(?<!\d)` / `(?!\d)`：前後不可為數字，避免在 20-digit 序列中擷取。
- 範例：`0912-345-678` ✓、`0912345678` ✓、`0912 345 678` ✓、`20912345678` ✗。

### PHONE_LANDLINE — 市話

```regex
(?<!\d)0[2-8][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)
```

- 0 + 區碼（2-8）+ 3-4 位數字 + 4 位數字。
- 範例：`02-1234-5678` ✓、`03-456-7890` ✓、`04-22345678` ✓。

### EMAIL

```regex
\b[\w.+\-]+@[\w\-]+\.[\w.\-]+\b
```

- 標準 email pattern。不處理引號轉義等 RFC 完整規格，因為臨床 note 不會出現那種 email。

### PLATE_TW — 車牌

```regex
(?<![A-Za-z0-9])(?:[A-Z]{2,3}-\d{3,4}|\d{3,4}-[A-Z]{2,3})(?![A-Za-z0-9])
```

- 舊車牌：2-3 位字母 + `-` + 3-4 位數字（例 `ABC-1234`）
- 新車牌：3-4 位數字 + `-` + 2-3 位字母（例 `1234-AB`）

### LINE_ID

```regex
(?i)\bLINE(?:\s*ID)?[:：]\s*[A-Za-z0-9_.\-]{3,}
```

- 需 `LINE:` 或 `LINE ID:` 前綴；避免把任何看起來像 LINE 帳號的字串都替換。

---

## 語境 ID（需前綴才偵測）

### NHI_CARD — 健保卡號

```regex
(?:健保卡號|健保\s*IC\s*卡?|(?i:\bNHI\s*card\s*no\.?))[:：#\s]+(\d{12})
```

- `(?i:...)` 只把 `(?i)` scope 限定在英文部分，避免全局 case-insensitive。
- `\b` 防止匹配到單字內部（如 `snhi`）。
- 分隔符至少 1 個（`[:：#\s]+`）——bed false-positive 的教訓：`*` 太寬鬆會讓 keyword 擠在下一個 token 前。

### MRN / ADMISSION_NO / PATHOLOGY_NO / ACCESSION_NO / LAB_NO

結構一致：

```regex
(?:中文關鍵詞|(?i:\b英文關鍵詞 No\.?|\b縮寫\b))[:：#\s]+([A-Z0-9\-]{5,14})
```

- 中文關鍵詞：病歷號 / 住院號 / 病理號 / 影像號 / 檢驗單號
- 英文關鍵詞：Chart No / Admission No / Path No / Accession No / Lab No / Specimen No
- 縮寫：MRN / HN / Adm No
- 長度 5-14 位字母數字 + 可選連字號。

### BED — 床號

```regex
(?:床號|(?i:\bBed\b|\bRm\b|\bRoom\b))[:：#\s]+([A-Z0-9]{1,5}[-\s]?\d{1,3})
```

- 特別注意：`Rm`（Room 的縮寫）只有 2 字元且全英文小寫也常見，**必須加 word boundary `\b`** 否則會在 `metfo**rm**in` 中匹配 `rm`，吞掉後續的 `in 500`。
- 早期版本這裡沒有 `\b` 導致 `metformin 500` 被誤判為 `metform[BED_01] mg`，是開發過程抓到的最大 bug。

---

## 名字

姓氏來自 `data/surnames_zh.txt`（~300 個 Top 中研院姓氏，含 歐陽、司馬 等複姓）。職稱來自 `data/titles.txt`（`title|role` 格式）。

### Pattern A：姓名 + 職稱

```regex
(?P<name>\p{Han}{1,4})(?P<title>主治醫師|醫師|先生|太太|...)
```

- 1-4 個中文字 + 職稱
- Post-filter：`name` 首字必須是已知姓氏（或首 2 字為複姓）。
- 範例：`王小明先生` → `王小明`；`張醫師` → `張`；`歐陽修教授` → `歐陽修`。

### Pattern B：職稱 + 分隔符 + 姓名

```regex
(?P<title>主治醫師|R2|CR|...)(?P<sep>[:：]\s*|\s+)(?P<name>\p{Han}{2,4})
```

- 範例：`主治醫師：陳大衛`、`R2 黃志強`、`CR 林小華`。

### Pattern C：英文醫師頭銜

```regex
(?i)\b(?:Dr\.?|Attending|Fellow|CR|Chief\s+Resident)\s+(?P<name>[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20})?)\b
```

- `Dr. Chen`、`Attending Wang`、`Dr. John Smith`。

### Pattern D：Resident + 中文姓名

```regex
\b(?:R[1-5]|CR|PGY[1-3]?|Intern|Clerk)\s+(?P<name>\p{Han}{2,4})\b
```

- `R2 黃志強`、`PGY2 陳小華`、`Intern 林大衛`。

---

## 日期（在 `date_shift.py` 中）

### Western 格式

```regex
(?<![\d])(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}(?!\d)
```

- 年份 anchor 必須是 `19xx` 或 `20xx`（4 位）—— 避免匹配 `24/03/15` 這種歧義格式。
- 分隔符 `-` `/` `.` 三者皆可，保留原格式 shift。

### 民國（ROC）Chinese

```regex
民國\s*\d{2,3}年\s*\d{1,2}月\s*\d{1,2}日?
```

### 民國 hyphen/slash

```regex
民國\s*\d{2,3}[-/]\d{1,2}[-/]\d{1,2}
```

### 裸 ROC 年月日

```regex
(?<!\d)(?<!20)(?<!19)\d{2,3}年\s*\d{1,2}月\s*\d{1,2}日
```

- Negative lookbehind 防止把西元年誤判為民國（e.g. `2024年` 不匹配）。

### 不 shift（只 warn）

```regex
(?<!\d)\d{1,2}/\d{1,2}(?!\d)
```

- 裸 `MM/DD` 無年份 anchor：太歧義（可能是比例、分數、日期）。`apply_shift` 會 log warning 但不 shift。

---

## 被保護（不 shift）的臨床 token

完整清單在 `data/clinical_time_tokens.txt`。重點條目：

```regex
(?i)\bq\d+h\b              # q8h, q24h
(?i)\bb\.?i\.?d\b          # bid, b.i.d.
(?i)\bt\.?i\.?d\b          # tid
(?i)\bq\.?i\.?d\b          # qid
(?i)\bq\.?d\b              # qd
(?i)\bprn\b, (?i)\bstat\b
(?i)\bPOD\s*#?\s*\d+\b     # POD#3, POD 3
(?i)\bHD\s*#?\s*\d+\b      # HD4
住院第\s*\d+\s*天
手術後第\s*\d+\s*天
\d+\s*h\s*\d+\s*min        # 5h 20min
\d+\s*分鐘
(?<![-/\d])\d{1,2}:\d{2}(?::\d{2})?(?![-/\d])   # 23:45 (but not inside date)
\d+\s*mg/dL, \d+\s*mmHg, \d+\s*bpm
\d+\s*y/o, \d+\s*歲
```

Protect pass 會把每個 token 替換成 Unicode Private Use Area 標記（`\ue000<idx>\ue001`），date regex 跑完後再還原。這是整個 pipeline 最關鍵的設計決定 —— 若不 protect，`POD#3` 會被 naive date regex 誤判。

---

## 字元正規化

`normalize()` 在偵測前把以下字元變體統一，但**不改變 raw text**（只用於 detection，redaction 還是對原始 text 做）：

| 原始 | 正規化後 | 說明 |
|---|---|---|
| 份 | 分 | 身份 → 身分 |
| 臺 | 台 | 臺北 → 台北 |
| 齢 | 齡 | 年齢 → 年齡 |

這些都是單字元 1-to-1 map，`str.translate()` 保留 offset，所以偵測到的 `[start, end)` 可以直接套用在 raw text 上。

---

## 讀 detections：順序與合併

1. Regex detectors 各自跑，產出 `Detection` 列表。
2. Name candidates 用姓氏 + 職稱跑 4 種 pattern。
3. Hospitals 用 longest-first lexicon match。
4. CKIP（若啟用）跑 BERT NER，補捕 regex 漏掉的人名。
5. `merge_detections()` 按 `(start, -length)` 排序，**保留最長非重疊 span**。重疊時長度較長者勝。
6. `_apply_redactions()` **從後往前** 替換，避免修改文字中段後位移錯亂。

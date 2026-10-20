---
name: case-discussion-docx
description: "Render a clinical case discussion as a 書面報告 (.docx) in a first-person flowing-prose voice with inline [N] citations and Vancouver References; sister of `case-discussion-pptx` (same content, .docx out). Trigger: `/case-discussion-docx`, `/cd-docx`, `/case-docx`, or 「把這個 case 寫成書面報告」「這份 pptx 順便產一份 docx」「case discussion 的書面版」."
---

# Clinical Case Discussion DOCX Generator (書面報告)

> **中文臨床語氣**：寫中文報告前先讀 `${CLAUDE_SKILL_DIR}/../case-discussion-pptx/references/clinical_writing_tone.md`（客觀保守措辭、禁用詞表），交付前 grep 禁用詞。簡版：建議用「建議 / 可考慮 / 宜評估」，避免「必須 / 絕對 / 立即」；統計未達顯著寫「無統計顯著差異」，不寫「沒差」。

把一份已經整理好的 clinical case（admission note + discussion questions + literature trail）寫成繁體中文書面報告 `.docx`，採個人書面語氣（長複句、第一人稱、醫學名詞首次中英、正面收束）+ Vancouver-style inline `[N]` citations + 末頁 References。

**This skill is the docx sister of `case-discussion-pptx`** — input shape刻意對齊：相同的 case CONTENT 跟 discussionTrail 拿來就能用，不需重灌。

## When to Use

- 使用者在 case discussion / journal club 之外，還要交一份**書面報告**（討論課、外科實習作業、rotation reflection）
- 使用者跑完 `/case-pptx` 後問「順便產一份 docx 嗎？」（case-discussion-pptx 的 Step 3 會問，answer yes 就 chain 到本 skill）
- 使用者直接打 `/case-discussion-docx` / `/cd-docx` / `/case-docx`
- 自然語言：「把這個 case 寫成書面報告」「這份 pptx 順便產一份 docx」「case discussion 的書面版」「跟刀心得 docx」

**This skill does NOT replace** `/manuscript-results`（research paper Results section）、`/jc-pptx`（journal club pptx）。它專門服務「臨床 case 討論的書面版」這個 narrow use case。

## Voice 與排版

### Voice — 個人書面語氣

預設語氣重點（使用者若提供自己的寫作風格檔，以使用者的為準）：
- **第一人稱**「我」，不出現「使用者認為」「作者覺得」
- **長複句**為主（每句 3–5 個子句），用逗號串連、思維層層推進
- **口語書面混搭**：「蠻」「真的」「我覺得」「其實」與「闡述」「無疑」「呼應」自然切換
- **括號補充**穿插具體細節、舉例、個人感受
- **正面收束**：每節（特別是反思段）以感恩、展望、肯定價值收尾
- **設問**：偶爾以反問句推動讀者（與自己）的反思

（選用）若你用 `writing-style-builder` 建過自己的寫作風格 skill，可在起稿前載入它，讓報告更像你本人的文字。

### 中英文混用規則（本 skill 專屬，覆蓋一般 `English（中文）` 首次加註預設）

書面報告書寫對象是看得懂英文醫學名詞的台灣醫學師長同儕，照標準 `English（中文）` 加註會讓行文卡頓、像 OE 直譯，不符合書面報告語氣。本 skill 一律走「英文醫學名詞獨立、中文僅做敘事黏著」原則。

**規則 A — 醫學專有名詞純英文，不加中文括號註解**

涵蓋：疾病、解剖構造、症狀、徵候、檢驗、影像 modality、procedure、藥物（含學名與商品名）、scoring system、staging、guideline / trial 名稱、microbiology、pathology。

| 類型 | ❌ 錯誤（不要加中文） | ✅ 正確（純英文） |
|---|---|---|
| Underlying disease | `HTN（高血壓）`、`DM（糖尿病）`、`DLP（高血脂）` | `HTN`、`DM`、`DLP` |
| Procedure | `partial embolization（部分栓塞術）` | `partial embolization` |
| Imaging | `MRI（磁振造影）`、`DSA（數位減影血管攝影）` | `MRI`、`DSA` |
| Scoring | `Spetzler-Martin grade 4（Spetzler-Martin 分級第四級）` | `Spetzler-Martin grade 4` |
| Trial | `ARUBA 試驗（未破裂腦動靜脈畸形隨機試驗）` | `ARUBA trial` |
| Anatomy | `thalamus（視丘）`、`internal capsule（內囊）` | `thalamus`、`internal capsule` |

**規則 A.1 — Abbreviation 展開可雙向，但必須兩端都英文**

| 形式 | 範例 | 說明 |
|---|---|---|
| Full → abbrev | `right thalamic arteriovenous malformation（AVM）` | 全形括號內放縮寫，純英文 |
| Abbrev → full | `ICH（intracerebral hemorrhage）`、`DSA（digital subtraction angiography）`、`mRS（modified Rankin Scale）` | 全形括號內放全稱，純英文 |
| ❌ 錯誤 | `arteriovenous malformation（動靜脈畸形）`、`mRS（改良 Rankin 量表）` | 任何把英文翻成中文塞進括號的行為都禁止 |

**規則 B — 不在中文敘事中亂插英文連接詞 / 通用詞**

醫學「上下文用語」維持英文（case、evidence、trial、guideline、follow-up、management、rotation、obliteration、latency、ruptured / unruptured、worse / favor 等）；但**有自然中文對應的非醫學詞**直接走中文，不要硬塞英文。

| ❌ 錯誤（亂插英文） | ✅ 正確（中文敘事） |
|---|---|
| `我們這位病人 age 36 歲` | `我們這位病人 36 歲` |
| `病人 occupation 是會計師` | `病人職業是會計師` |
| `Family history 部分，patient 的母親有 HTN` | `Family history 部分，母親有 HTN`（人稱用中文，醫學詞用英文） |
| `Lab results 都是 normal range` | 可寫 `Lab 都在 normal range`（醫學詞 normal range 保留）或 `各項數值都在正常範圍內`（全中文亦可）— 不要用 `results` 這種無資訊量的英文 |
| `這次 admission 我們做了 evaluation` | `這次 admission 主要是做 evaluation`（evaluation 屬醫學行為詞，可保留；但 `做了` vs `主要是做` 用中文連接） |

**判斷標準**：那個英文字若有自然、單一、不會引起歧義的中文對應（age → 歲；occupation → 職業；patient → 病人；results → 結果），就走中文；若該英文是醫學圈內共識的精確術語（case、evidence、obliteration、ruptured、follow-up），就保留英文。**有疑慮時用中文**。

**規則 C — 藥物寫法**

| 形式 | 範例 | 說明 |
|---|---|---|
| 學名單獨 | `Aspirin`、`Mannitol` | 多數情境足夠 |
| 學名（商品名） | `cefepime（Maxipime）`、`piperacillin/tazobactam（Zosyn）` | 第一次出現且商品名常見時可用，純英文 |
| ❌ 錯誤 | `Aspirin（阿斯匹靈）`、`頭孢吡肟 [cefepime]` | 不加中文藥名 |

### 寫稿後 self-check（規則 A/B/C 對應）

寫完草稿、組 JSON 之前，主執行緒要對 body paragraphs 做以下 grep / 目視檢查（一旦中招，立即重寫該段）：

- `grep -E '[A-Za-z][A-Za-z\- ]+（[一-鿿]+）'` — 抓「英文醫學詞 + 中文翻譯括號」這個 anti-pattern。例外只有兩種：規則 A.1 的 abbrev 雙向展開（兩端都英文）、藥物學名（商品名）。命中其他即違規。
- 全文搜尋 `age \d+ 歲`、`occupation 是`、`patient 的`、`results 都是` 等亂插英文連接詞，全部改成中文敘事。
- 全文搜尋 `（高血壓）`、`（糖尿病）`、`（高血脂）`、`（部分栓塞術）`、`（動靜脈畸形）`、`（改良`、`（修飾後` 等常見誤譯模式 — 命中即砍中文括號。

通過這三輪檢查再進 Step 6 組 JSON。

### 排版 — 書面報告慣用格式

| 元素 | 設定 |
|---|---|
| Body 字型 | 標楷體 |
| Body 字級 | 12 pt |
| 行距 | 1.5 |
| 首行縮排 | 0.85 cm |
| Title | 18 pt 粗體置中 |
| Subtitle | 13 pt 置中 |
| H1 章節標題 | 16 pt 粗體 |
| H2 子標題 | 14 pt 粗體 |
| References | Times New Roman 11 pt、hanging indent 0.74 cm、行距 1.4 |
| 頁邊距 | 上下 2.2 cm、左右 2.5 cm |
| 引用格式 | inline `[N]`（Vancouver 式方括號數字，多筆用 `[1, 3]`） |

## 結構模板（9 sections）

預設輸出結構（Claude 可依 case 內容調整節次與順序，但骨架建議保留）：

1. **前言** — 為什麼選這個 case、報告結構簡述（可帶第一段 case 一句話 summary）
2. **Case 簡介** — 拆 3 個子節：(1.1) 病人 profile + underlying；(1.2) Clinical timeline；(1.3) Admission 時的關鍵 findings
3. **臨床評估的重點** — 視 case 性質：分級系統 / staging / DDx 推理 / OSCE-style approach
4. **Imaging / Investigations 的角色** — 各 modality 的貢獻與限制
5. **Treatment options 比較** — 各選項 evidence + trade-off
6. **關鍵 trial / guideline 的適用範圍** — 例：ARUBA、PARADIGM-HF、CHEST 等是否適用本 case
7. **為什麼選擇 X 治療路徑** — 把前面節次整合成 stepwise 的決策推理
8. **Long-term follow-up plan**（選填）
9. **個人反思** — 從 case 體會到的 lesson、感謝 rotation 同事老師、正面收束
10. **References** — Vancouver 式編號清單

每節在 body 引用相關文獻時，於句末加 `[N]` 對應到 References。**不在心得 / 反思段強塞 citation**，只引用該段論點需要支撐的地方。

## Workflow

### Step 1: 取得輸入

支援三種觸發路徑：

**A. 從 `/case-pptx` 鏈過來（最常見）**
- 上游已經跑完 Step 4 / Stage 3，`CONTENT` object 與 `discussionTrail` 都在記憶體 / 磁碟
- 上游把 `CONTENT` + `discussionTrail.md` path + `clinicalContext` 一起 pipe 過來，**不重問**
- 跳到 Step 2 直接寫稿

**B. 使用者獨立呼叫，已有 pptx 跑出來的 artifacts**
- 詢問：(a) `case_discussion_*.js` runner path（含 CONTENT）、(b) `<output>.discussion_trail.md` path
- Read 兩個檔，解析出 CONTENT + discussionTrail
- 進 Step 2

**C. 使用者獨立呼叫，只有原始病歷**
- 建議請使用者先跑 `/case-pptx`（含 PHI 檢查與 discussion trail）拿到 artifacts，再回來本 skill；不要在本 skill 裡重做那段

### Step 2: 載入語氣規則

讀上方「Voice」與「中英文混用規則」；若使用者有自己的寫作風格 skill（選用），一併載入。

### Step 3: 確認生產選項

用 `AskUserQuestion` 問（除非 A 路徑已由上游帶入）：

| 問題 | 預設 |
|---|---|
| 輸出路徑 | 與 pptx 同目錄、檔名 `書面報告_<slug>_<YYYYMMDD>.docx` |
| 報告者 | pptx CONTENT 的 reporter |
| 報告日期 | pptx CONTENT 的 reportDate |
| 結構模板 | `default`（9 sections）/ `compact`（5 sections — 前言 + Case + 討論 + 反思 + Refs，適合 < 800 字短報告）/ `custom`（使用者貼大綱） |
| 引用樣式 | `vancouver-bracket`（預設 `[N]`）/ `vancouver-superscript`（¹）/ `author-year`（Mohr 2014） |
| 字型 | `標楷體`（預設）/ `新細明體` / `Times New Roman + 標楷體 mixed`（中英分別） |
| 加 cover page | `no`（預設）/ `yes`（封面頁含 title + reporter + 學號 + 系級 + 日期） |

### Step 4: 起稿（Claude 主執行緒寫）

依 Step 1 的 CONTENT + discussionTrail，寫一份完整繁中草稿。**寫稿責任在 Claude，不在 script**；script 只負責排版。

寫稿 checklist：
1. 每節長度依 case 複雜度自由分配，但整篇至少 3000 字（書面報告慣例 vs 心得文）
2. 每個 discussionQuestion 至少對到 1 個 section（通常是 Treatment options / Trial 適用範圍 / 為什麼選 X）
3. **Inline citation rule**：
   - 從 `discussionTrail[].citations` 抽出所有 unique 的文獻
   - 依首次出現順序給編號 `[1]`、`[2]`、…
   - 在 body 句末標 `[N]`（句號之前）
   - 同一論點引多筆用 `[1, 3]` 或 `[2-4]`
4. 個人反思段**禁止**強塞 citation
5. 寫完跑兩輪 self-check：
   - **Voice check** — 上方 Voice 六點（第一人稱、長複句、括號補充、正面收束…）
   - **中英文混用 check** — 本 SKILL.md「中英文混用規則」三條規則 + 三條 grep 自查（規則 A/B/C 之後那段），命中即重寫該段才進 Step 6

### Step 5: 整理 References

- 把所有 inline 用過的 `[N]` 對應到 References list
- 若 discussionTrail 的 citation 形式為 `"[N] PMID 12345 — Author. Journal Year"`，補成 Vancouver 完整格式：`Author A, Author B. Title. Journal. Year;Vol(Issue):Pages. PMID: 12345. doi: 10.xxxx/yyyy.`
- 缺資訊（缺 DOI / volume / pages）時：若有 PubMed MCP，用 `mcp__pubmed__pubmed_format_citations` 以 PMID 補 Vancouver 完整格式；沒有就保留原有欄位並在報告中標註「待補」
- 編號從 1 起，對應 inline `[N]`

### Step 6: 組 CONTENT JSON 給 build script

寫完草稿後，把所有段落結構化成 JSON：

```json
{
  "title_main": "神經外科 Case Discussion 書面報告",
  "title_sub": "36 歲女性右側 thalamic AVM ...",
  "reporter": "（你的名字）",
  "report_date": "2026/05/04",
  "rotation": "範例：神經外科 profile",
  "cover_page": false,
  "font_body": "標楷體",
  "citation_style": "vancouver-bracket",
  "sections": [
    {
      "heading": "前言",
      "level": 1,
      "paragraphs": ["這次神經外科 case discussion ...", "我希望透過這份書面報告 ..."]
    },
    {
      "heading": "一、Case 簡介",
      "level": 1,
      "paragraphs": []
    },
    {
      "heading": "1.1　病人 profile 與 underlying",
      "level": 2,
      "paragraphs": ["病人是一位 ..."]
    },
    ...
  ],
  "references": [
    "1. Kim H, McCulloch CE, ... Neurology. 2014;83(7):590–7. PMID: 25015366. doi: ...",
    "2. ..."
  ],
  "output_path": "書面報告_AVM_CyberKnife_20260504.docx"
}
```

寫到 `<output_dir>/.docx_build_<slug>.json`（與 `.docx` 同目錄、隱藏檔字首避免污染）。

### Step 7: Run build script

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/build_report_docx.py \
    --content "<json_path>"
```

腳本讀 JSON、套排版、寫 `.docx` 到 `output_path`。

### Step 8: Verify (light gate)

不像 pptx 需要 visual rendering（Word 檔的版面問題比 pptx 少很多），但仍要：

1. **檔案存在 + 大小合理**（> 20 KB 通常代表正常產出）
2. **Citation 對應檢查**：
   - 抓 inline 用過的所有 `[N]` 編號集合 → 跟 References 列表編號集合比對
   - 不該有 inline 用了 `[7]` 但 References 缺 `7`，或 References 列了 `[10]` 但 body 沒用過
   - 用 `python3 -c "import re; ..."` script-level 檢查
3. **字數 sanity check**：< 1500 字 too short（除非 `compact`）、> 8000 字 偏長（建議使用者拆）
4. **PHI 殘留 grep**：若上游有 phi-deid，grep `[PATIENT_NN]` / `[DATE_NN]` token 進到 docx；若上游沒 deid，grep 真實姓名 / 病歷號 pattern（參考 `phi-deid` skill 的規則）

驗證失敗 → 回 Step 4 修稿或 Step 6 修 JSON，re-run build → re-verify。

### Step 8.5: Zotero archiving（選用：只有你裝了 Zotero MCP 才跑；chained-from-pptx 時跳過）

把這份 case 的引用文獻歸進 Zotero（與 `case-discussion-pptx` 共用同一個 adapter + discussionTrail，**一個 case 只歸一次**）。

- **若本次是從 `case-discussion-pptx` 委派下來**（pptx 已跑過 Step 6.7 Zotero archiving）→ **跳過**，避免重複歸檔。
- **若本次是 standalone 入口**（直接 `/case-docx`，pptx 沒跑）且 `zotero` MCP 已連線且 discussionTrail 非空：把 discussionTrail dump 成 JSON，跑共用 adapter，照執行手冊歸檔：
  ```
  python3 ${CLAUDE_SKILL_DIR}/../case-discussion-pptx/scripts/zotero_plan_case.py <output_dir>/<slug>_trail.json \
      --topic "<case title>" --out <output_dir>/<slug>_zotero_plan.json
  ```
  然後照 **`${CLAUDE_SKILL_DIR}/../case-discussion-pptx/lib/zotero_archive/EXECUTION.md`** 跑（parent `Case Discussions` → show→confirm → lookup-before-add → index）。

### Step 9: Report

告知使用者：
- 輸出 path（clickable）
- 字數 / 章節數 / inline citation 數
- 提醒：Word docx 排版細節（字級、行距、邊界）可在 Word / Pages 直接調；想改文字內容直接編輯 docx，下次要改大幅內容再重跑 skill
- 若 Step 8 偵測 PHI / citation 不對應，列出明細

## Inputs from upstream skills

當被 `/case-pptx` 委派時，上游應 pipe：

```json
{
  "delegated_from": "/case-pptx",
  "case_content": { ... pptx CONTENT object ... },
  "discussion_trail_md": "/path/to/<output>.discussion_trail.md",
  "clinical_context": { ... clinicalContext from intake ... },
  "pptx_output_path": "/path/to/case_discussion_<slug>.pptx",
  "preferred_docx_output_path": "/path/to/書面報告_<slug>_<date>.docx",
  "skip_step3_questions": true
}
```

收到 `delegated_from` 時跳過 Step 3 多餘問題（沿用上游已收集的 reporter / date / output_path / 字型偏好）。

## Error handling

| 失敗模式 | 處理 |
|---|---|
| `python-docx` not installed | `pip install python-docx` |
| Citation 編號不連續（`[1][2][4]` 缺 `3`） | 重新 normalize 編號順序，rebuild |
| Inline 用了 `[N]` 但 discussionTrail 沒對應 | 告知使用者該 claim 沒 evidence backing；建議加 PubMed 補引或刪除該 claim |
| References 過少（< 5）對於正式書面報告偏少 | 警告但不中斷；建議用 `/openevidence` 或 `/pubmed-search` 補 |
| 使用者要 figure | 本 skill 不嵌圖（書面報告慣例純文字 + table）；想加 figure → 自己 Word 內貼 |

## Why this skill exists（不是直接擴充 case-discussion-pptx）

- pptx 跟 docx 的 information architecture 完全不同：pptx 一張 slide ≤ 50 字，docx 一節數百字
- 受眾不同：pptx 講者 + 觀眾現場互動，docx 評分老師遠端閱讀
- Voice 不同：pptx 多半 telegraphic（English bullet），docx 連貫敘事 + 第一人稱（中文長句）
- Citation 形式不同：pptx 偏好 footer 小字 + 每張 slide 1-3 source，docx 用 inline `[N]` + 末頁完整 References
- 把 docx 揉進 pptx skill 會讓 pptx skill 過度複雜；獨立 sub-skill 讓兩邊各自演化

## 依賴

```bash
pip install python-docx
```

（選用）PubMed MCP 的 `pubmed_format_citations` 可用於補 Vancouver 完整 citation。

## 設計原則

- **Voice 規則集中在本檔 Voice 一節**
- **Skeleton 在 SKILL.md，prose 在 Claude 主執行緒寫**（不在 script 裡 hardcode 模板段落 — 那會生成出 AI 痕跡很重的文章）
- **Script 只負責排版**：JSON in → styled .docx out
- **Citation 完整性是 hard gate**（Step 8 verify），inline + References 編號必須一一對應
- **與 pptx 共用 input shape**：CONTENT + discussionTrail 從 pptx skill 直接 pipe 過來，使用者不重答 question

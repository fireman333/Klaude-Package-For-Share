# phi-deid 使用者完整指南

## 情境

你是醫學生 / RA / PGY / R。臨床工作有大量書寫任務：

- **Admission note** — 新入院病人的完整病史整理
- **Progress note** — 每日進展、檢查結果、治療調整
- **Discharge note** — 出院摘要、follow-up 建議
- **Patient list** — 病房交班 / 晨會表格
- **Handoff list** — 夜班交班單
- **Case discussion** — 晨會報 case / tumor board 準備

LLM 的寫作協助能省掉大量模板工作（尤其是把雜亂的 raw observation 整理成結構化章節）。但把原始病歷貼進 Claude / ChatGPT / Gemini 就會違反個資法與醫療機構的資安規範。

`phi-deid` 解決的問題：**讓 LLM 看到「去識別化版本」寫稿，寫完再本地還原成真實版本貼回 HIS**。

---

## 單一 note 基本流程

### 1. 從 HIS 複製病歷到本地檔案

不要貼進對話！用 Finder / Terminal / 編輯器存成純文字檔：

```
~/Documents/raw_note.txt
```

### 2. 告訴 Claude 任務與路徑

```
請用 phi-deid 處理 ~/Documents/raw_note.txt（patient-key: bed12_APR），
然後依內容幫我寫一份 progress note（SOAP 格式）。
```

### 3. Claude 執行

Claude 會：

1. 呼叫 `deid.py --input ~/Documents/raw_note.txt --patient-key bed12_APR --validate`
2. 看 stdout JSON 確認處理成功、`leak_count=0`
3. `Read(~/phi-deid-sessions/<stamp>_bed12_APR/deid.txt)` —— 此檔所有 PHI 已替換成 token
4. 依 deid.txt 內容起稿 SOAP，**保留所有 `[PATIENT_01]`、`[DATE_...]` 等 token 原形**
5. `Write(~/phi-deid-sessions/<stamp>_bed12_APR/deid_progress_draft.txt)`
6. 呼叫 `reidentify.py --session bed12_APR --input .../deid_progress_draft.txt`
7. `Read(.../reidentify_report.txt)` —— 只含統計，無 PHI
8. 告訴你「還原完成，檔案在 `final_deid_progress_draft.PHI_DO_NOT_READ.txt`，請你自己打開 review」

### 4. 你自己打開 final 檔、review、貼回 HIS

Claude **永遠不讀** final 檔。

---

## 跨多份 note 的一致性（關鍵情境）

### 情境

週一寫 admission note，週三寫 progress note，下週出院寫 discharge note —— 三份都是同一個病人。你希望：
- 三份 note 的 `[PATIENT_01]` 指向同一個真名
- 三份 note 的日期 shift 幅度一致（例如入院 2024-03-15、手術 2024-03-18、出院 2024-03-25 —— shift 後仍保留 3 天、10 天的相對關係）

### 做法

**全部用同一個 `--patient-key`**：

```bash
# 週一
python deid.py --input ~/Documents/admission.txt --patient-key bed12_APR

# 週三：session 已存在，明確指定延用
python deid.py --input ~/Documents/progress_0318.txt --patient-key bed12_APR --reuse-session

# 下週
python deid.py --input ~/Documents/discharge.txt --patient-key bed12_APR --reuse-session
```

三份的 `mapping.json` 共用，新出現的 PHI 延續已有 token（王小明 → 永遠是 `[PATIENT_01]`）。新的 PHI 才分配新 token。

### 不加 `--reuse-session` 的行為

預設會 **error**，告訴你「這個 alias 已存在」，避免你誤打錯 alias 把兩個病人的 mapping 混在一起。

---

## 多個同時住院的病人

```bash
python deid.py --input note1.txt --patient-key bed12_APR
python deid.py --input note2.txt --patient-key bed15_WANG
python deid.py --input note3.txt --patient-key bed21_LIN
```

每個 patient-key 有獨立的 session folder + mapping + date offset。互不干擾。

### 命名建議

- ❌ 用真名：`--patient-key 王小明`（等於把 PHI 放進 session 資料夾名稱）
- ❌ 用 hash：`--patient-key $(md5 A1234567)`（仍是 PHI-derived identifier，理論上可還原）
- ✅ 用自己記得的符號：`bed12_APR`、`ER_20260416_male`、`JohnDoeCase01`

---

## 列出 / 刪除 session

```bash
# 列出（不含任何 PHI，只有 alias 與 folder path）
python scripts/mapping.py list

# 刪除單一 session（含 raw / mapping / deid.txt 全部清除）
python scripts/mapping.py delete bed12_APR
```

建議每個病人寫完一份 note 即刻考慮：
- 還要繼續跟這個 case（progress / discharge 還沒寫）→ **保留**
- 已出院 / 已結案 → **刪除**

---

## `--validate` 的意義

```bash
python deid.py --input ... --patient-key ... --validate
```

加上 `--validate` 後，script 會在產出 `deid.txt` 之後**再跑一次所有 regex detector**，若發現任何 PHI-shaped 字串（且不是已知 pseudonym token）就計入 `leak_count`。

- `leak_count == 0`：去識別化乾淨（regex 層面）
- `leak_count > 0`：有漏網之魚。Claude 應**停止起稿**，告訴使用者：
  - 具體漏掉的類別 + offset（在 stdout JSON 的 warnings 中）
  - 建議使用者人工補上該段文字的去識別化後再重跑

**注意**：`--validate` 只抓 regex-shaped leaks（ID / 電話 / 健保卡號…），**不**能偵測中文人名遺漏（那需要 NER）。CKIP 已啟用時 recall 會好很多，但仍可能漏罕見姓 / 英文轉寫。**使用者必須人工 review**。

---

## CKIP 首次安裝

第一次用 phi-deid 時，若沒裝 CKIP，deid.py 會在 warnings 中提示：

```
CKIP not installed — name detection may miss cases.
Install with: python scripts/ner_ckip.py --install
```

執行：

```bash
python ${CLAUDE_SKILL_DIR}/scripts/ner_ckip.py --install
```

會 pip install `ckip-transformers` + `torch`（CPU 版本），並在第一次使用時下載 `albert-tiny-chinese-ner` 模型（~50MB）。之後完全離線執行。

若不想裝 CKIP，每次加 `--no-ckip` 跳過：

```bash
python deid.py --input ... --patient-key ... --no-ckip
```

---

## 常見問題

### Q：deid.txt 打開看起來漏了病人名字

可能原因：
- 姓不在 `data/surnames_zh.txt` lexicon 中 → 加進去
- 名字獨立出現（無前後職稱 / 關係 anchor）→ 需要 CKIP
- 英文轉寫姓名（`Wang`、`Mr. Lin`）→ regex Pattern C 只抓 `Dr. X` 型式，一般書面名需 CKIP

解法：啟用 CKIP、或人工在 `deid.txt` 中補上替換後再餵給 LLM。

### Q：reidentify_report.txt 顯示 "Coverage drop"

例：`Coverage drop: [PATIENT_01] appeared 3x in deid.txt but only 1x in draft`

表示 LLM 把某次提到 `[PATIENT_01]` 改寫成「病人」「個案」。結果還原只會替換剩下那 1 次 —— 那些被改寫的地方會是「病人」而不是真名。

解法：
- 如果你不需要還原那些地方的真名（「這位病人需要...」寫進 HIS 也 OK），忽略。
- 如果你需要還原（例如 HIS 要求姓名明確），把 draft 手動編輯回 `[PATIENT_01]` 再重跑 reidentify。

**預防**：寫起稿 prompt 時加上「請保留 [XXX_NN] 這類 token 原形，不要改寫成中文代稱」。

### Q：reidentify_report.txt 顯示 "Possible patient merge"

例：`Possible patient merge: phrase '兩位病人' at offset 123 with no pseudonym within 30 chars`

表示 draft 中出現「兩位病人」但附近沒有具體的 pseudonym 指明是哪兩位。若原始 deid.txt 有多個 PATIENT token，這可能代表 LLM 合併了兩個病人的資訊（罕見但致命）。

解法：人工 review draft 那一行，確認沒有資訊錯置。

### Q：日期被 shift 後感覺「不像真日期」

這是功能，不是 bug。shift 幅度是 session-scoped 隨機 ±365 天，任何相對關係（入院到手術的間距、POD#N）都保留。還原時會 shift 回原日期。

### Q：POD#3 變成「POD-3」或被日期 regex 吃掉了

不應該發生 —— `POD\s*#?\s*\d+` 在 protect list 中。若真發生了：
1. 檢查 `data/clinical_time_tokens.txt` 是否漏了特殊格式
2. Report bug（提供觸發字串）

### Q：這個工具跟 IRB 核准是什麼關係？

**無關**。phi-deid 讓你日常臨床寫作流程能合規使用 LLM 協助，但：
- 研究用途（論文、publication）仍需 IRB 核准。
- IRB 審查考量的是資料蒐集與使用目的的合法性，不只是技術上的去識別化。

---

## 實戰 prompt 範本

### Admission note

```
請用 phi-deid 處理 ~/Documents/admission_raw.txt（patient-key: bed12_APR），
然後依內容整理成標準 admission note：
- CC / PI / PMH / PSH / Allergy / Medication / Social / Family history
- PE / 入院時 vital signs / labs
- Impression / Plan

保留 [XXX_NN] token 原形，不要改寫成中文代稱。
```

### Progress note（SOAP）

```
請用 phi-deid 處理 ~/Documents/progress_0318.txt（patient-key: bed12_APR，延用 session），
整理成 SOAP：
- S: subjective（病人主訴 + 夜間狀況）
- O: objective（vital signs、labs、imaging、PE）
- A: assessment（#1 #2 #3 problem list + 變化）
- P: plan（今日調整）

保留 [XXX_NN] token。
```

### Discharge note

```
請用 phi-deid 處理 ~/Documents/discharge_raw.txt（patient-key: bed12_APR，延用 session），
整理成 discharge summary：
- Chief diagnosis
- Admission course（入院當下狀況）
- Hospital course（住院期間重大事件 by POD）
- Discharge condition
- Discharge medication
- Follow-up plan（OPD, lab f/u）

保留 [XXX_NN] token。
```

### Handoff list（夜班交班）

```
請用 phi-deid 處理 ~/Documents/night_handoff_bed12.txt、~/Documents/night_handoff_bed15.txt、
~/Documents/night_handoff_bed21.txt（分別 patient-key: bed12_APR / bed15_WANG / bed21_LIN），
然後整理成一份夜班交班表格：
| 床號 | 病人 | 主問題 | 今晚注意事項 | To-do |
|------|------|--------|--------------|-------|

保留 [XXX_NN] token。
```

### Case discussion（晨會報 case）

```
請用 phi-deid 處理 ~/Documents/tumor_board_case.txt（patient-key: TB_20260416），
然後做成 tumor board 報告大綱：
1. Presentation（CC、PI）
2. Past medical / oncologic history
3. Current investigation（影像、病理、分期）
4. Differential diagnosis
5. Treatment options（含 pros/cons）
6. My recommendation

保留 [XXX_NN] token。
```

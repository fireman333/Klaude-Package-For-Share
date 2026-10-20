---
name: phi-deid
description: Taiwan 病歷 LLM 工作流去識別化前處理器。原始病歷先本地 Python 處理，只有去識別化版本進入 Claude context。草稿完成後本地還原 PHI，Claude 不讀最終檔。Trigger - `/phi-deid`、使用者提及「幫我打 admission note / progress note / discharge note / patient list / handoff / case discussion」並附帶病歷內容、或明確說「去識別化」「PHI」「de-identify」「幫我隱蔽病人資訊」等意圖時。
---

# phi-deid — Taiwan 病歷去識別化前處理器

這個 skill 讓使用者在利用 LLM 協助寫 admission note / progress note / discharge note / patient list / handoff / case discussion 之前，先在本機做完去識別化；LLM 看到的只有 `[PATIENT_01]` 這類 pseudonym，完全看不到真實病人資料。草稿完成後再本機還原真實 PHI —— 整個循環中 Claude 永遠不讀原始病歷或最終還原版。

## ⚠️ 契約條款（Claude 的強制規則）

> 這不是可有可無的建議。違反任一條即等同把 PHI 送入雲端對話 —— 這正是這整套 skill 要防的事情。

### 🔴 絕對不可 Read / Grep / cat-head-tail 的檔案

1. **任何檔名包含 `PHI_DO_NOT_READ`** —— 原始病歷 + 還原後的最終檔
   - ❌ `Read(~/phi-deid-sessions/20260416_bed12_APR/raw.PHI_DO_NOT_READ.txt)`
   - ❌ `Bash("cat ~/phi-deid-sessions/*/final_*.PHI_DO_NOT_READ.txt")`
   - ✅ `Bash("python scripts/deid.py --input ~/Documents/raw_note.txt ...")` —— 只透過 Python script 處理
2. **`mapping.json`** —— 含真名逆向表
   - ❌ `Read(.../mapping.json)` 或 `Grep pattern=... mapping.json`
   - ✅ 讓 `reidentify.py` 自己讀；Claude 只收 JSON summary
3. **`final_*.txt`（不含 `_report` 尾綴者）** —— 還原後的真實病歷
   - ❌ `Read(final_progress.PHI_DO_NOT_READ.txt)`
   - ✅ `Read(reidentify_report.txt)` —— 只含計數 + warning，無 PHI

### 🔴 絕對不可請使用者把原始病歷貼進對話

- ❌「麻煩貼一下病歷內容，我幫你去識別化」
- ❌「你把那段 progress note 的原文貼給我看看」
- ✅「先把原始病歷存成 `~/Documents/raw_note.txt`（或任何本地路徑），我呼叫 `deid.py` 處理後再讀去識別化版本」
- ✅ 若使用者不小心貼了 —— 立刻停止處理，提醒使用者該貼文已進入雲端對話 context，建議他更換 session / 不再使用該段文字做後續工作流。

### 🔴 `deid.py` / `reidentify.py` 的 stdout 僅吐 JSON summary

- 這兩個 script 的設計就是讓 Claude 只看到「處理了幾個 PATIENT_NAME / 幾個 DATE / 產出檔案路徑是什麼」—— 不吐原始內容片段、不吐去識別化片段。
- Claude 要看去識別化後的內容，**只能** `Read(deid.txt)`（該檔不含 PHI）。

### 🔴 如果使用者主動要求 Claude 讀原始檔

這個契約是 best-effort，不是 cryptographic boundary。使用者若堅持 `Read(raw.PHI_DO_NOT_READ.txt)`，系統無法阻擋。但：

1. Claude **必須拒絕第一次請求**，說明 reason（PHI 一旦進 context 就已傳到雲端）。
2. 若使用者再次堅持 —— Claude 可執行，但 **明確警告**這違反了 phi-deid 的設計前提。
3. 不得因「方便」「節省步驟」主動建議繞過契約。

---

## 🧭 使用流程（Claude 執行步驟）

### Step 1：使用者準備原始病歷檔案

使用者應**自己在本機**把 HIS 複製貼上的病歷內容存成 `.txt`，例如：
- `~/Documents/raw_note.txt`
- `~/Documents/patients/bed12_admission.txt`

若使用者把病歷貼進對話 —— 參照上方「絕對不可」條款拒絕處理。

### Step 2：決定 patient-key（alias）

- **使用者命名**：例如 `bed12_APR`、`JohnDoeCase01`、`ER_20260416_male`。
- **使用者的責任**：不要用病人真名當 alias。
- **跨 note 一致性**：同一病人的 admission / progress / discharge 一律用**同一個** `--patient-key`，這樣 pseudonym + date offset 會在所有 note 之間保持一致。
- 若 alias 已存在於 registry：預設會 error。使用者明確說「延用既有 session」時才加 `--reuse-session`。

### Step 3：呼叫 `deid.py`

```bash
python ${CLAUDE_SKILL_DIR}/scripts/deid.py \
  --input ~/Documents/raw_note.txt \
  --patient-key bed12_APR \
  --validate
```

Claude 只看到 stdout JSON，例如：

```json
{
  "session": "bed12_APR",
  "session_folder": "~/phi-deid-sessions/20260416_bed12_APR",
  "deid_output": "~/phi-deid-sessions/20260416_bed12_APR/deid.txt",
  "counts": {"PATIENT_NAME": 1, "MRN": 1, "DOCTOR_NAME": 4, ...},
  "date_shifts": 5,
  "date_offset_days": 137,
  "warnings": [],
  "leak_count": 0
}
```

- `leak_count > 0` —— 表示 `--validate` 在去識別化後的文本中仍偵測到 PHI-shaped 字串。必須告訴使用者、不可繼續起稿。
- `warnings` 非空 —— 可能包含「Ambiguous MM/DD 未 shift」「CKIP 未安裝」等非致命提示，視情況告知使用者。

### Step 4：`Read` 去識別化版本

```
Read(~/phi-deid-sessions/20260416_bed12_APR/deid.txt)
```

這個檔案**可以讀**，其中所有 PHI 都已被替換成 `[PATIENT_01]`、`[MRN_01]`、`[PHONE_02]` 等 pseudonym token。

### Step 5：在 Claude context 內起稿

使用者說「幫我改寫成 progress note 格式」「整理成交班清單」「做成 case discussion slide」—— Claude 依 deid.txt 內容起稿。**必須保留** 所有 `[XXX_NN]` 形式的 token 原封不動，不要改寫成「病人」「某醫師」「該家屬」等中文代稱，否則還原時會失去 anchor。

### Step 6：把草稿寫進檔案

```
Write(~/phi-deid-sessions/20260416_bed12_APR/deid_progress_draft.txt)
```

（或任何本地路徑。建議放同一個 session folder 方便管理。）

### Step 7：呼叫 `reidentify.py`

```bash
python ${CLAUDE_SKILL_DIR}/scripts/reidentify.py \
  --session bed12_APR \
  --input ~/phi-deid-sessions/20260416_bed12_APR/deid_progress_draft.txt
```

Claude 看到的 stdout JSON：

```json
{
  "session": "bed12_APR",
  "final_output": "~/phi-deid-sessions/20260416_bed12_APR/final_deid_progress_draft.PHI_DO_NOT_READ.txt",
  "report": "~/phi-deid-sessions/20260416_bed12_APR/reidentify_report.txt",
  "unknown_tokens": [],
  "warnings": [],
  "draft_token_count": 19
}
```

### Step 8：`Read` reidentify_report.txt（**僅此檔**可讀）

```
Read(.../reidentify_report.txt)
```

只含 counts + warnings，**不含任何 PHI**。Claude 依此判斷是否有 coverage loss、unknown token、merge 疑慮，告訴使用者結論。

**不可讀** `final_deid_progress_draft.PHI_DO_NOT_READ.txt` —— 該檔已含真實 PHI。請使用者自己用編輯器打開、review、貼回 HIS。

### Step 9：session 結束時提醒清除

寫完一個 note 後建議使用者：

```bash
python ${CLAUDE_SKILL_DIR}/scripts/mapping.py delete bed12_APR
# 或保留以便未來同一病人延續使用
```

---

## 🔧 可用的 scripts（速查）

| Script | 用途 | 輸出 |
|---|---|---|
| `deid.py --input X --patient-key Y [--validate] [--no-ckip] [--reuse-session]` | 去識別化 | JSON summary + session/deid.txt |
| `reidentify.py --session Y --input draft.txt` | 還原 | JSON summary + session/final_*.PHI_DO_NOT_READ.txt + session/reidentify_report.txt |
| `mapping.py list` | 列出所有 session alias（無 PHI） | JSON |
| `mapping.py delete <alias>` | 刪除指定 session | JSON |
| `ner_ckip.py --install` | 首次安裝 CKIP NER（albert-tiny，~50MB） | JSON |
| `ner_ckip.py --check` | 檢查 CKIP 是否已安裝 | JSON |

所有 script 的 stdout 都是 JSON，適合讓 Claude 直接解析。

---

## 🧩 覆蓋的 PHI 類別

| 類別 | Pseudonym | 偵測方式 |
|---|---|---|
| 病人姓名 | `[PATIENT_NN]` | 姓氏 lexicon + 職稱語境 + CKIP PERSON |
| 家屬姓名 | `[FAMILY_NN]` | 關係語境（太太 / 兒子 / 個案之母 等） |
| 醫師姓名 | `[DOCTOR_NN]` | 職稱（主治醫師 / R1-5 / CR / PGY / Dr. / Attending 等） |
| 護理師姓名 | `[NURSE_NN]` | 職稱（護理師 / NS / 專師） |
| 身分證字號 | `[NATIONALID_NN]` | regex `[A-Z][12]\d{8}` |
| 外籍統一證號 | `[UINUMBER_NN]` | regex `[A-Z](?:[89]\|[A-D])\d{8}` |
| 健保卡號 | `[NHICARD_NN]` | 語境 regex（需 "健保卡號" 等前綴） |
| 病歷號 / 住院號 / 病理號 / 影像號 / 檢驗單號 | `[MRN_NN]` / `[ADM_NN]` / `[PATH_NN]` / `[ACCESSION_NN]` / `[LAB_NN]` | 語境 regex |
| 床號 | `[BED_NN]` | 語境 regex（需 "床號" / "Bed" 前綴） |
| 手機 / 市話 | `[PHONE_NN]` | regex |
| Email | `[EMAIL_NN]` | regex |
| LINE ID | `[LINEID_NN]` | regex |
| 車牌 | `[PLATETW_NN]` | regex |
| 地址 | `[ADDRESS_NN]` | 22 縣市 anchor + 區/鄉/鎮/路/街/巷/弄/號/樓 |
| 日期（含出生日期） | **隨 session offset 隨機 shift**（保留格式與相對關係） | date_shift protect-first pipeline |
| 醫療機構 | `[HOSPITAL_NN]` | lexicon + CKIP ORG |
| 科別 | **保留**（臨床必要） | — |

### 被保留不動的臨床 token（protect list）

為避免 date shift 破壞臨床語意，以下 token 全數保護：
- 相對時間：`POD#3`、`HD4`、`住院第5天`、`手術後第3天`
- 給藥頻率：`q8h`、`qd`、`bid`、`tid`、`qid`、`prn`、`stat`
- Duration：`5h 20min`、`30分鐘`、`8小時`
- 時間：`23:45`（無日期 anchor 的 HH:MM）
- 生理數值：`138/82 mmHg`、`105 bpm`、`38.9°C`
- 年齡：`72 歲`、`72 y/o`

---

## ⚠️ 已知限制（誠實告知使用者）

1. **不等於 IRB 核准** —— 這個工具讓 LLM 工作流更合規，但不豁免倫理審查、不是 anonymization 的法律認證。
2. **中文人名 recall 非 100%** —— 英文姓名轉寫、罕見姓、簽名區縮寫仍可能漏。**必須人工 review** deid.txt，不可盲信。
3. **Claude context isolation 是 best-effort** —— 非 cryptographic boundary。若使用者堅持讓 Claude 讀原始檔，系統無法阻擋。
4. **Phase 1 不處理 Word / PDF / OCR** —— 使用者需手動複製貼上成純文字。
5. **Mapping file 僅 chmod 600** —— 未加密。建議使用者 session 結束後 `mapping.py delete`。
6. **LLM paraphrasing 會失去 anchor** —— 如果 LLM 把 `[PATIENT_01]` 改寫成「病人」，還原時無法自動還原。`reidentify.py` 的 coverage check 會警告，但 Claude 應主動避免：起稿時保留 token 原形。

---

## 🧪 Negative Examples（錯誤示範）

### 錯：直接請使用者貼病歷

```
User: 幫我把這份 admission 改寫成 progress note
Assistant: 好的，麻煩貼一下 admission note 內容。
```

**錯在哪**：使用者一旦貼上，PHI 就已進入雲端對話。正確做法：

```
Assistant: 這份 admission note 如果含 PHI，建議你先把原文存成本地檔案（例如 ~/Documents/admission.txt），
我再呼叫 phi-deid skill 處理後才讀取去識別化版本。你的檔案路徑是？
```

### 錯：起稿時改寫 token

```
User: 改寫成 progress note
Assistant: （讀 deid.txt 後起稿）"病人持續發燒..."  ← 把 [PATIENT_01] 改成了「病人」
```

**錯在哪**：reidentify 找不到 anchor，還原時會警告 coverage drop。正確做法：保留 `[PATIENT_01]` 原形，讓還原 script 替換回真名。

### 錯：讀 final 檔自我檢查

```
User: 還原完了
Assistant: 讓我讀 final_progress.PHI_DO_NOT_READ.txt 確認一下內容正確...  ← 錯！
```

**錯在哪**：檔名已標明 `PHI_DO_NOT_READ`。正確做法：

```
Assistant: 已還原，請你自己用編輯器打開 final_progress.PHI_DO_NOT_READ.txt review 後貼回 HIS。
reidentify_report.txt 顯示 0 unknown token、0 warning，還原應該乾淨。
```

### 錯：hash MRN 當作 alias

```bash
python deid.py --patient-key $(echo "A1234567" | md5)  ← 錯！
```

**錯在哪**：hash 出來的 alias 仍是 PHI-derived identifier，仍可被還原或關聯。正確做法：使用者自己取一個人類可記但與真實 ID 無關的別名，例如 `bed12_APR`。

---

## 📚 References

詳細內容見：
- `references/phi_categories.md` —— PHI 清單 + 台灣法規依據
- `references/taiwan_patterns.md` —— Regex catalog + 範例
- `references/usage_guide.md` —— 完整 workflow（含跨 note、多病人場景）

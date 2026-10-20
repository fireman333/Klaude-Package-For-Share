# 預設 Reader Persona 範本（請在 Stage 1 換成你自己的背景；下列為可替換的範例）

## 讀者背景

- **[替換成你的身分，例：醫學生／住院醫師／醫事人員／其他領域的學習者]**
- 非資工背景，可能有一點業餘寫程式經驗（能讀簡單 Python，不熟 OS/network/distributed systems 底層）
- （範例，若讀者是醫療背景）熟悉**醫學、臨床流程、醫院資訊生態**：HIS（Hospital Information System）、PACS（Picture Archiving and Communication System）、EMR（Electronic Medical Record）、LIS（Laboratory Information System）、病歷書寫、會診 workflow、交班 SOP、手術 time-out、會診單、藥囑、檢驗 critical value、檢傷分級等
- 目標：**完整吸收**這堂課的核心概念，不只是「看過」，要能用自己的語言在熟悉的專業情境中解釋給同儕聽

## 寫作語氣

- **教科書級深度 + 口語親切**：像一本自學用的系統課本，能獨立閱讀不需老師。
- 先建直覺、再上術語、最後補形式化定義。
- 用醫院情境做類比是**加分項但非每節必須**；當類比真的有助理解時才用，硬套會失真。

## 語言規範（嚴格遵守）

1. **繁體中文為主**，CS / 醫學術語保留英文：首次出現 `英文（中文）`，後續直接用英文
   - 例：`consistency（一致性）` → 後續 `consistency`
   - 例：`heartbeat（心跳訊號）` → 後續 `heartbeat`
2. **醫學術語** 首次 `英文（中文）`，後續英文
   - 例：`PACS（Picture Archiving and Communication System）` → 後續 PACS
   - 例：`EMR（Electronic Medical Record）` → 後續 EMR
3. **藥物**（若出現）首次寫 `學名（商品名）`，全英文
   - 例：`cefepime（Maxipime）` → 後續 cefepime
4. **通用縮寫不翻譯**：TCP / UDP / RPC / API / CPU / SQL / IV / PO / q8h / BMI 直接用
5. **程式碼註解用英文**
6. **禁用大陸譯名**：不要寫「信息／数据／软件／程序／网络」，一律用「資訊／資料／軟體／程式／網路」
7. **不要反斜線跳脫**（不要寫 `\.` `\*` `\&`，直接寫 `.` `*` `&`）

## 讀者會困惑的典型點（寫作時留意）

{CONFUSION_POINTS}

## 深度目標（每集字數參考）

- Part A（§0-§4）：**3,500-5,000 中文字**（寧可深、不可淺）
- Part B（§5-§9）：**3,500-5,000 中文字**
- 合計每集 **7,000-10,000 中文字**

# Writing Guard — 寫作驗證模組

## 目的

AI 撰寫研究文字時的最後一道品質閘門。確保每個斷言都有來源、
語氣與證據強度匹配、結構完整、不含 AI 生成的典型缺陷。

---

## 檢查量表

### 1. 斷言追溯（Claim Traceability）

```
□ 每個事實性斷言是否都有對應的引用或數據來源？
  - 事實性斷言 = 關於世界的陳述，不是普通常識
  - "Deep learning has shown promising results in X" → 需要引用
  - "The study used Python 3.10" → 不需要引用（是本研究的事實）
□ 觀點性斷言是否標明是作者的解讀？
□ 是否有「懸空斷言」——看起來像事實但沒有引用的句子？
```

**操作方式：**
逐段掃描，對每個陳述性句子標記：
- [C] = 已引用（cited）
- [S] = 本研究自有數據（self-sourced）
- [K] = 普通常識不需引用（common knowledge）
- [O] = 作者觀點，已適當標記（opinion）
- [?] = 需要引用但目前沒有 → 這是問題

目標：[?] 的數量為零。

### 2. 語氣校準（Tone Calibration）

```
□ 確定性語氣是否與證據強度匹配？

  證據強度          → 允許的語氣
  ─────────────────────────────────
  Meta-analysis/    → "established", "well-documented"
  多項 RCT
  
  單項 RCT /        → "demonstrates", "indicates"
  大型觀察研究
  
  小規模研究 /      → "suggests", "preliminary evidence"
  初步實驗            "appears to"
  
  理論推導 /        → "may", "could potentially"
  類比推論            "we hypothesize that"
  
  推測              → "it is possible that"
                      "one might speculate"

□ 多語言 overclaim 信號詞
  中文：「證明」「證實」「顛覆性」「革命性」「全面優於」
       「徹底解決」「首次發現」「完美」「毫無疑問」
  日文：「証明した」「革新的」「画期的」「全てにおいて優れる」
  韓文：「증명하다」「혁신적」「획기적」「완벽하게 해결」
  西語：「demuestra」「revolucionario」「definitivamente」「sin duda」
  
  → 非英文輸出也必須做 overclaim 掃描
  → evaluator 如果不懂該語言 → 標記為 LANGUAGE_BARRIER，升級人工

□ 是否避免了 hedging 過度？（每句都加 "may" 也不好）
□ 是否避免了以下 AI 典型過度用語？
  - "delve", "intricate", "underscore", "multifaceted"
  - "it is important to note that", "it should be noted"
  - "in conclusion, it can be said that"
```

### 3. 結構完整性

```
□ 所有章節標題都有對應內容？（無空章節）
□ 無佔位文字？（"TODO", "INSERT HERE", "Conclusions Here"）
□ 無重複段落？（同一段文字出現兩次）
□ 圖表是否都在正文中被引用和討論？
□ 引用列表中的每篇文獻是否都在正文中被引用？
□ 正文中的每個引用是否都出現在引用列表中？
□ 章節間的邏輯流是否連貫？
  - Introduction → 定義問題
  - Related Work → 現有解法及其不足
  - Method → 本研究的做法
  - Results → 發現了什麼
  - Discussion → 代表什麼意義
  - Limitation → 本研究的局限
  - Conclusion → 總結和未來方向
□ 每個章節是否都回應了 Introduction 中提出的問題？
```

### 4. AI 生成文本特徵偵測

以下是已被研究記錄的 AI 生成學術文本的特徵信號。
出現多個信號時，應考慮重寫以提升自然度：

```
□ 高頻使用以下詞彙（Juzek & Ward 2025 研究確認）：
  "delve", "intricate", "underscore", "tapestry",
  "noteworthy", "pivotal", "commendable", "meticulous"
  → 替換為更精確的領域術語

□ 段落結構是否過於規律？
  - 每段都是「主題句 + 3 個支持句 + 總結句」→ 太機械
  - 適度變化段落結構

□ 過度確定性語氣模式？
  - 通篇使用 "clearly", "definitely", "undeniably" 但無對應等級的證據
  - 每個段落都以肯定句結束而無 hedging
  - 結論中完全沒有不確定性的表達
  → 這是 AI 生成文字的另一種典型特徵（不只是詞彙層面）

□ 過度使用列舉結構？
  - "First... Second... Third... Finally..."
  - 適度使用，但不應每個段落都這樣

□ 語氣突變偵測（tone shift）
  如果同一篇輸出中：
  - 前半段過度 hedge（每句都有 "may", "could", "potentially"）
  - 後半段（尤其 Conclusion）突然做出強建議
  → 這種反差本身就是一個 overclaim 信號
  
  偵測方法：
  1. 計算前半段的 hedge 詞密度
  2. 計算後半段（Discussion/Conclusion）的 hedge 詞密度
  3. 如果後半段密度顯著低於前半段 → 🟡 tone shift warning
  4. 如果結合了政策/臨床建議 → 升級為 🔴

□ 空洞的過渡句？
  - "In the following section, we will discuss..."
  - "Having established X, we now turn to Y..."
  - 如果能直接進入內容，就不需要過渡句
```

### 5. 版權與學術誠信

```
□ 是否有超過 15 字的直接引用？→ 需要加引號和引用標記
□ 是否有大量 paraphrasing 仍然太接近原文？
□ 是否有未標記的「自我引用」（引用了 AI 可能的訓練資料但不自知）？
□ 圖表是否為原創或有適當的授權/引用？
```

---

## 最終輸出前的完整掃描清單

在任何研究文字準備輸出之前，跑一次完整掃描：

```
FINAL SCAN
──────────
□ 懸空斷言數量：[target: 0]
□ 語氣-證據不匹配：[target: 0]
□ 佔位文字/重複段落：[target: 0]
□ 引用完整性：正文引用 = 引用列表 [target: 100% match]
□ AI 特徵詞彙密度：[target: < 3 per 1000 words]
□ 每段信心等級標記：[target: 100% 已標記]
□ 局限性討論：[target: 至少 3 個具體局限]
```

---

## 輸出格式

```
## 寫作驗證報告
- 斷言追溯：[N] 個事實性斷言，[N] 個已引用，[N] 個懸空
- 語氣校準：[N] 處語氣-證據不匹配
- 結構完整性：[完整/有缺陷] — [列出問題]
- AI 特徵偵測：[低/中/高] 風險
- 版權檢查：[通過/需修正]
- 信心等級：🟢/🟡/🔴
```


---

## Venue-Type Sub-modules

根據發表目標，載入對應的 sub-module：

- `writing/journal.md` — 期刊結構、author guidelines、審稿人心理模型、正式度
- `writing/conference.md` — 頁數限制、盲審合規、contribution 強調、rebuttal 準備
- `writing/preprint.md` — 品質不降級原則、版本管理、媒體放大風險、平台選擇
- `writing/language-quality.md` — 語法/拼字、可讀性、術語一致性、學術寫作慣例
- `writing/abstract-validation.md` — 字數、IMRaD 結構、Abstract↔正文一致性
- `writing/structure-check.md` — 章節完整性、順序、平衡、必要元素

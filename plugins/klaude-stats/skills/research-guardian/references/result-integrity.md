# Result Guard — 結果驗證模組

## 目的

AI 報告研究結果時最危險的錯誤不是數字算錯，而是「結論超出數據的支持範圍」。
本模組確保數值正確、統計報告規範、結論適度。

---

## 檢查量表

### 1. 數值一致性（Cross-check）

```
□ 表格中的數字與正文描述是否一致？
  - 逐一比對：正文提到的每個數字，在對應的表格/圖表中是否一致
□ 圖表中的趨勢與文字描述是否一致？
  - 文字說「顯著上升」，圖表是否真的顯示上升？
□ 摘要中的數字與正文/表格是否一致？
□ 百分比加總是否合理（例如：各類別的百分比總和約等於 100%）？
□ 樣本數是否前後一致（排除後的 N 在後續分析中是否正確反映）？
```

**操作方式：**
- 建立一個「數值登記表」：列出所有在文中出現的數值及其來源
- 交叉比對同一個數值在不同位置（摘要、正文、表格、圖表）的呈現
- 任何不一致都標記為 🔴

### 2. 統計報告規範

```
□ p 值是否報告了精確值（而非僅 p < 0.05）？
□ 效果量是否報告？（Cohen's d, η², r² 等）
□ 信賴區間是否報告？
□ 使用的統計檢定是否明確說明？
□ 自由度是否報告（適用時）？
□ 是否區分了統計顯著性和實際顯著性？
  - p < 0.001 但效果量 d = 0.05 → 統計顯著但實際可能無意義
```

**APA 格式快速檢查：**
- t 檢定：t(df) = X.XX, p = .XXX, d = X.XX
- ANOVA：F(df1, df2) = X.XX, p = .XXX, η² = .XX
- 相關：r(N) = .XX, p = .XXX
- 卡方：χ²(df, N = XX) = X.XX, p = .XXX

### 3. 結論適度性（最重要的檢查）

```
□ 結論是否使用了適當的限定語？
  - ❌ "This proves that..."
  - ❌ "We have shown definitively..."
  - ✅ "These results suggest..."
  - ✅ "This finding is consistent with..."
□ 是否避免了從相關性推論因果性？
  - 觀察性研究 → 只能說「相關」或「關聯」
  - 只有 RCT → 才能謹慎地說「因果」
□ 結論是否超出了樣本範圍？
  - 在特定人群上的發現 → 不能推論到所有人
  - 在特定數據集上的結果 → 不能宣稱普遍性
□ 是否承認了研究的局限性？
□ 是否討論了替代解釋？
```

**Overclaim 偵測規則：**

以下詞彙在研究結論中出現時，自動觸發檢查：
- "prove", "proven", "definitive", "conclusive"
- "first ever", "unprecedented", "revolutionary"
- "all", "always", "never", "none"
- "clearly demonstrates", "undeniably shows"

出現上述詞彙 → 觸發檢查，但判定必須結合研究設計等級：

信號詞觸發後的判定流程：
```
1. 偵測到信號詞（如 "proves", "causes"）
2. 檢查研究設計等級：
   - 大型 RCT / Meta-analysis of RCTs → 允許 "effect", "caused"
   - 單項 RCT → 允許 "demonstrated", "effect of"
   - 觀察性研究 → 只允許 "associated", "suggests"
   - 無實驗 → 只允許 "may", "could"
3. 如果語言強度 ≤ 設計允許 → PASS
4. 如果語言強度 > 設計允許 → FAIL
不要僅憑信號詞就判定為 overclaim——RCT 說 "causes" 是合法的。
```

### 結構性 Overclaim 偵測
```
即使沒有信號詞，以下結構性模式也構成 overclaim：

Pattern 1: 前提弱 + 結論強 = 結構性跳躍
  偵測：比較 Results 段的語氣和 Discussion/Conclusion 段的語氣
  如果語氣強度在 Conclusion 突然上升 → 🔴

Pattern 2: 研究範圍小 + 結論範圍大 = 泛化跳躍
  偵測：Methods 的 N/sites/populations vs. Conclusion 的 scope
  N<500 + "all" / "global" / "universal" → 🔴

Pattern 3: 觀察性設計 + 行動建議 = 設計-結論不匹配
  偵測：Methods 的 design type vs. Conclusion 的 recommendation
  Cross-sectional + "should implement" / "recommend" → 🔴

Pattern 4: 小效果 + 強行動建議 = 證據-行動不匹配
  偵測：d < 0.3 + "should be adopted" → 🔴

這些模式不依賴特定詞彙，而是結構性的不匹配。
```

### 4. 可重現性資訊

```
□ 是否提供了足夠的資訊讓他人重現結果？
  - 資料來源和取得方式
  - 完整的方法論描述
  - 程式碼或分析腳本（如適用）
  - 軟體版本和環境配置
□ 是否報告了隨機種子（如適用）？
□ 是否報告了計算資源需求？
□ 是否有多次實驗的變異度報告（標準差、信賴區間）？
```

### 5. 幻覺結果偵測

AI 可能生成「看起來合理但並非基於實際計算」的數值。以下信號值得懷疑：

```
□ 所有結果是否都太整齊？（所有 p 值恰好是 .001 或 .05）
□ 效果量是否太一致？（所有比較的效果量幾乎相同）
□ 是否有「不可能的數字」？
  - 百分比 > 100% 或 < 0%
  - 負的標準差
  - 樣本量為小數
  - F 值或 t 值為負
□ 結果是否與該領域的已知效果量差距過大？
  - 如果該領域的典型效果量是 d = 0.3，而 AI 報告 d = 2.5 → 需要深究
```

### 6. 實作 grounding（防空殼報告）

當 AI 產出看似流暢的 results section，對每一段結論都要求它同時提供來源：

```
□ Script / notebook cell 對應：每段 results 文字指向哪個 code cell 或 script 行號
□ Raw output 片段：從 stdout / log / 原始 table 直接貼一行，且必須包含 summary 引用的那個數字
□ 引用文獻時：URL + 原文段落（不只是 citation 標籤）
```

任何段落無法提供以上 3 項中對應的那一項 → 🔴 視為「未 grounded」。

**操作方式：**
- Audit 時對每個結論問一句「show me where this number comes from」
- AI 若回覆「根據分析結果…」但拿不出 raw output 或 code 對應 → 高度可疑
- 第 5 節「幻覺結果偵測」是從數字樣態找破綻；本節從「拿不拿得出出處」找破綻，兩者互補
- Huli 2026-04-18 逆向工程文章的教訓：AI 能寫出頭頭是道但空洞的報告，只追問實作細節才會露餡

---

## 輸出格式

```
## 結果驗證報告
- 數值一致性：[N] 個數值已檢查，[N] 個一致 / [N] 個不一致
- 統計報告規範：[符合/部分符合/不符合] APA 格式
- Overclaim 偵測：[發現 N 處過度推論] → [列出]
- 幻覺結果風險：[低/中/高] — [可疑信號列表]
- 可重現性：[資訊充足/部分/不足]
- 實作 grounding：[N] 段結論中 [M] 段未附 code/output/原文 → [列出]
- 信心等級：🟢/🟡/🔴
```


---

## Statistical Framework Sub-modules

根據使用的統計框架，載入對應的 sub-module：

- `result/frequentist.md` — p 值報告、效果量、CI、APA 格式、常見統計錯誤偵測
- `result/bayesian.md` — Bayes Factor、後驗分佈、MCMC 診斷、先驗敏感度
- `result/ml-metrics.md` — 分類/迴歸/排序/生成指標選擇、不平衡處理、可疑信號
- `result/qualitative.md` — 主題證據支持度、引述充分性、反例處理、結論適度性

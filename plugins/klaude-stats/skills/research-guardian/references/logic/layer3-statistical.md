# Logic Layer 3: Statistical Reasoning Deep Guide

## 何時載入
當 Experiment/Result Guard 啟動 Layer 3 時。

---

## 統計推理謬誤的操作化檢查

### 基率忽視 (Base Rate Neglect)
```
偵測場景：報告了很高的 accuracy/sensitivity/specificity
檢查步驟：
  1. 基率（prevalence/base rate）是多少？
  2. 計算 PPV (Positive Predictive Value)
     PPV = (sensitivity × prevalence) / 
           (sensitivity × prevalence + (1-specificity) × (1-prevalence))
  3. 如果 prevalence < 5%，即使 sensitivity 99%，PPV 也可能很低

修正：報告 PPV 和 NPV，不只是 sensitivity/specificity
```

### 多重比較問題
```
偵測場景：多次統計檢定但只報告顯著的
檢查步驟：
  1. 計算總共做了幾次檢定 (K)
  2. Family-wise 假陽性率 = 1 - 0.95^K
     K=10 → 40% 至少一個假陽性
     K=20 → 64% 至少一個假陽性
  3. 是否做了校正？
     - Bonferroni: α/K（最保守）
     - Holm: step-down（較佳）
     - BH-FDR: 控制偽發現率（推薦）

修正：報告校正前和校正後的 p 值
```

### 大數謬誤
```
偵測場景：超大樣本量 + 微小差異 + 高度顯著
檢查步驟：
  1. N > 10,000 且 p < .001？
  2. 效果量有多大？
     d < 0.1 → 即使顯著也幾乎無實際意義
  3. 是否討論了實際顯著性 vs. 統計顯著性？

修正：強制報告效果量和實際意義的討論
```

### 倖存者偏誤
```
偵測場景：樣本來自「成功案例」或「現有數據」
檢查步驟：
  1. 被排除的數據（失敗案例、缺失數據）有多少？
  2. 排除是否與結果相關？
     如果失敗案例被排除 → 效果量被高估
  3. 是否做了敏感度分析？（最壞情況假設）

修正：報告排除的數量和原因 + 做 worst-case 分析
```

### p 值誤解
```
常見錯誤判斷清單：
❌ "p = .04 比 p = .03 更不顯著" → p 值不是連續的證據指標
❌ "p = .06 接近顯著" → 沒有「接近顯著」這回事
❌ "p > .05 代表沒有效果" → absence of evidence ≠ evidence of absence
❌ "兩個效果 p 值不同代表它們不同" → 必須直接比較兩效果
❌ "N.S. = 虛無假設為真" → 可能只是 power 不足
```

### 生態謬誤
```
偵測場景：從群體數據推論個體
檢查步驟：
  1. 分析的層級是什麼？（國家/組織/個人）
  2. 結論推論到什麼層級？
  3. 如果分析層級 > 結論層級 → 生態謬誤風險

修正：明確標示分析層級，限制結論到同一層級
```

### HARKing 偵測
```
Hypothesizing After Results are Known
偵測信號：
  - 假設「太完美」地被數據支持
  - 探索性分析被呈現為驗證性分析
  - 沒有預註冊
  
檢查步驟：
  1. 是否有預註冊？（osf.io, ClinicalTrials.gov）
  2. 如果有，分析是否與預註冊一致？
  3. 探索性分析是否被明確標記為「探索性」？

修正：區分 confirmatory 和 exploratory 分析
```

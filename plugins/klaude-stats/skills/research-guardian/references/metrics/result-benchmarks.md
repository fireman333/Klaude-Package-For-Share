# Result Guard Benchmarks

## 測試集設計
```
標準測試集：1 份結果報告含 10 個植入錯誤

植入錯誤類型：
  - 3 個數值不一致（表格與正文數字不同）
  - 2 個 overclaim（結論超出數據支持）
  - 2 個統計報告錯誤（p 值與檢定統計量不匹配）
  - 1 個幻覺數值（看似合理但非計算產生）
  - 1 個百分比加總錯誤
  - 1 個效果量異常大（d > 3.0）
```

## 基準指標
```
Primary:   Inconsistency detection rate (target: > 85%)
Secondary: Overclaim detection rate (target: > 70%)
Tertiary:  Hallucinated result detection (target: > 60%)
False flag rate: (target: < 15%)
Latency:   Average check time per result section (target: < 120s)
```

## 數值一致性驗證方法
```
建立數值登記表：
  1. 掃描 Abstract → 記錄所有數值
  2. 掃描 Results → 記錄所有數值
  3. 掃描 Tables → 記錄所有數值
  4. 交叉比對 → 任何不一致 = 🔴
  
自動化可能性：regex 提取數值 + 交叉比對
```

## 回歸測試用例
```
Case 1: "accuracy improved by 15%" but table shows 12% → should catch
Case 2: "p < .001, t(20) = 1.5" → impossible, should catch
Case 3: Correct statistical report → should pass
```

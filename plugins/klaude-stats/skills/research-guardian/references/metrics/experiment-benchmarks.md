# Experiment Guard Benchmarks

## 測試集設計
```
標準測試集：10 個實驗設計（5 有缺陷 + 5 合理）

有缺陷設計（5 個）：
  - 1 個資料洩漏（test data in training pipeline）
  - 1 個不公平 baseline（deliberately weak baseline）
  - 1 個統計效力不足（N too small for declared effect size）
  - 1 個多重比較未校正
  - 1 個目標指標不一致（optimize A, report B）

合理設計（5 個）：
  - 從已發表且通過審查的論文中提取
  - 覆蓋 RCT, observational, ML experiment
```

## 基準指標
```
Primary:   Design flaw detection rate (target: > 70%)
Secondary: False alarm rate (target: < 20%)
Tertiary:  Anti-pattern identification accuracy (target: > 60%)
Latency:   Average check time per design (target: < 90s)
```

## 回歸測試用例
```
Case 1: ML experiment where normalization is fit on entire dataset → should catch leakage
Case 2: RCT with proper randomization and blinding → should pass
Case 3: Observational study claiming causation → should flag language
```

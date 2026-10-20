# Hypothesis Guard Benchmarks

## 測試集設計
```
標準測試集：10 novel + 10 non-novel 假設
來源：從近期發表論文中提取

Novel 假設（10 個）：
  - 從最近 3 個月的頂會論文中提取被 reviewer 認為 novel 的假設
  - 確保覆蓋不同領域
  
Non-novel 假設（10 個）：
  - 取已知概念（如 micro-batching for SGD）重新包裝
  - 取已被多次發表的假設，改變措辭
  - 取被 reviewer 指出 "lack of novelty" 的假設
```

## 基準指標
```
Primary:   Novelty classification accuracy (target: > 75%)
Secondary: Logicality check recall (target: > 70%)
Tertiary:  Testability identification rate (target: > 80%)
Latency:   Average time per hypothesis (target: < 60s)
```

## 已知弱點
```
- 跨領域假設的 novelty 判斷較差（搜索範圍不夠廣）
- 高度交叉的領域（如 AI+bio）容易漏掉相鄰領域的已有工作
- 術語變體的偵測依賴搜索引擎的能力
```

## 回歸測試用例
```
Case 1: "Using attention mechanisms for time series" → should flag as non-novel
Case 2: "Applying protein folding methods to RNA structure" → context-dependent
Case 3: [Fresh case from recent paper] → should identify as novel
每次更新 skill 後重新跑這些 case。
```

# Literature Guard Benchmarks

## 測試集設計
```
標準測試集：20 篇引用（15 真實 + 5 幻覺）

真實引用（15 篇）：
  - 5 篇高引用的 foundational papers
  - 5 篇近 2 年的 recent papers
  - 5 篇不同領域的跨領域 papers

幻覺引用（5 篇）：
  - 2 篇完全虛構（作者+標題+期刊全假）
  - 2 篇部分真實（真作者+假標題，或真標題+假年份）
  - 1 篇已撤回的論文（看能否偵測 retraction）
```

## 基準指標
```
Primary:   Hallucination detection rate (target: > 90%)
Secondary: False rejection rate (target: < 10%)
Tertiary:  Coverage completeness (target: > 70% of key papers found)
Latency:   Average verification time per citation (target: < 30s)
```

## 三重驗證成功率追蹤
```
Track each verification method independently:
  - Title exact search success rate
  - Author+year+keyword search success rate
  - DOI/URL resolution success rate
  
Goal: at least 2/3 methods confirm each real citation
```

## 回歸測試用例
```
Case 1: "Attention Is All You Need, Vaswani et al., 2017" → real, must pass
Case 2: "Deep Learning for Climate, Zhang & Liu, Nature 2024" → fabricated
Case 3: [Recently retracted paper] → should detect retraction
```

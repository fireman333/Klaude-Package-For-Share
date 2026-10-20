# Critique Synthesis — 結構化評論生成

## 何時載入
Aggregator 完成 issue 彙整後，產出最終評論。

---

## 輸出結構

### 1. Executive Summary（200 字內）
```
一段話概括：
  - 這篇研究做了什麼
  - 核心貢獻是什麼
  - 主要問題是什麼
  - 整體評估（accept / borderline / reject 及理由）
```

### 2. Strengths（結構化列表）
```
每個 strength 需要：
  - 一句話描述
  - 指向原文的具體段落
  - 為什麼這是 strength（不只是 "well-written"，而是具體原因）

模板：
  S1: [標題]
      原文：[SEC-X-PY]
      說明：[為什麼這做得好]
```

### 3. Weaknesses（結構化，按嚴重度排序）
```
W1 (Critical): [標題]
   原文：[SEC-X-PY]
   問題：[具體描述]
   建議：[修正方向]
   
W2 (Major): ...
W3 (Minor): ...
```

### 4. Questions for Authors
```
從 issues 中提煉出需要作者回應的問題：
  - 方法論的 assumption 是否合理？
  - 結果的替代解釋？
  - 缺失的實驗或分析？
  
每個問題需要指向觸發它的 issue ID。
```

### 5. Recommendation
```
recommendation 必須基於以下公式：

critical issues > 0          → reject
major issues >= 4             → weak_reject
major issues >= 2             → borderline
major issues < 2 且無 critical → weak_accept
全部 minor 或無 issues         → accept

confidence = 基於 parse_quality 和 evidence coverage
```

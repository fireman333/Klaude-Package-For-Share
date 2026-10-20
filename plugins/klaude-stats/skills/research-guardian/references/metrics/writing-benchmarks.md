# Writing Guard Benchmarks

## 測試集設計
```
標準測試集：1 份 3000 字的研究報告含植入問題

植入問題：
  - 5 個懸空斷言（事實性宣稱無引用）
  - 3 個語氣-證據不匹配（觀察性研究用因果語言）
  - 2 個 AI 特徵詞彙密集段落（delve, intricate, underscore）
  - 1 個佔位文字（"TODO" 或 "[citation needed]"）
  - 1 個重複段落
  - 1 個引用列表與正文不匹配（正文引用了列表中沒有的）
```

## 基準指標
```
Primary:   Unsourced claim detection rate (target: > 80%)
Secondary: Tone mismatch detection rate (target: > 70%)
Tertiary:  Structural issue detection rate (target: > 90%)
AI artifact detection: (target: > 75%)
Latency:   Average check time per 1000 words (target: < 60s)
```

## 斷言追溯的操作化
```
逐句標記系統：
  [C] = cited
  [S] = self-sourced (own data)
  [K] = common knowledge
  [O] = clearly marked opinion
  [?] = needs citation but doesn't have one

Target: 0 instances of [?]
```

## 回歸測試用例
```
Case 1: "Studies have shown that X improves Y" (no citation) → should catch [?]
Case 2: "We found that X = 42.3 in our experiment" → should mark [S], pass
Case 3: Paragraph with 5 instances of "delve" and "intricate" → should flag AI artifact
```

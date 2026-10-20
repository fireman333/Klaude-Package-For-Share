# Batch Review Mode — 多論文批次審查

## 何時載入
當使用者需要同時審查多篇論文時。

---

## 批次流程
```
1. 收集所有論文 → 逐篇跑 Paper Parser
2. 對每篇論文獨立跑 Guardian pipeline（平行）
3. 彙整所有論文的結果
4. 產出批次摘要報告

批次摘要包含：
  - 每篇論文的信心等級（🟢🟡🔴）
  - 跨論文的常見問題模式
  - 排名（按品質從高到低）
  - 需要最多關注的論文標記
```

## 效能最佳化
```
多篇論文 → 所有論文的 gate 完全平行
  10 篇論文 × 7 subagents = 70 subagent calls
  但平行執行 → 總時間 ≈ 單篇時間 + 彙整時間
  
Token 管理：
  每篇論文獨立 context → 不會互相干擾
  批次摘要的 context 只包含各篇的最終報告（不含原文）
```

## 批次報告格式
```
═══ BATCH REVIEW SUMMARY ═══
Papers reviewed: [N]
Average confidence: [🟢/🟡/🔴]

Ranking:
  1. paper_a.pdf — 🟢 HIGH (0 critical, 1 major)
  2. paper_c.pdf — 🟡 MEDIUM (0 critical, 3 major)
  3. paper_b.pdf — 🔴 LOW (2 critical, 5 major)

Common issues across papers:
  - [Issue pattern] appeared in [N/total] papers
  - [Issue pattern] appeared in [N/total] papers
```

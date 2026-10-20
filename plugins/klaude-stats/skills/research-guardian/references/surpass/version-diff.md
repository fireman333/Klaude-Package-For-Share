# Version Diff — 版本差異分析

## 我們有、OpenReviewer 沒有。這是超越。

## 目的
比較同一篇論文的兩個版本，追蹤改善程度，確認先前 review 的問題是否被 addressed。
常見場景：revision 後重新審查、preprint v1 vs v2。

---

## 比較流程
```
1. 對兩個版本分別跑 Guardian pipeline
2. 對比兩個版本的 issue 列表
3. 產出 diff 報告：哪些問題修了、哪些新增、哪些惡化
```

## Diff 報告格式
```
═══ VERSION DIFF: v1 → v2 ═══

RESOLVED Issues (v1 had, v2 fixed):
  ✅ G4-001: overclaim in Discussion → reworded to hedged language
  ✅ G2-003: hallucinated citation → removed and replaced

NEW Issues (v2 introduced):
  🆕 G3-005: new experiment added but baseline unfair
  🆕 G5-002: new claim in Conclusion without support

PERSISTENT Issues (still present):
  ⚠ G1-001: novelty still insufficient — not addressed
  ⚠ G4-002: effect size still not reported

IMPROVED but not resolved:
  📈 G5-001: overclaim reduced from "proves" to "suggests" (but still some issues)

Summary:
  v1 issues: 12  →  v2 issues: 9
  Resolved: 5  |  New: 2  |  Persistent: 4  |  Improved: 1
  Net improvement: +3 issues resolved
  
Recommendation change: weak_reject → borderline (improved)
```

## 使用方式
```
/review --diff v1.pdf v2.pdf
/review --diff v1.pdf v2.pdf --focus-on-previous-issues
```

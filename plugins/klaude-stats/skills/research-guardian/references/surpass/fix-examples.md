# Fix Examples — 修正範例生成

## 我們有、OpenReviewer 沒有。這是超越。

## 目的
不只說「這裡有問題」和「建議修正」，而是直接給出修正後的範例文字，
讓作者可以直接採用或根據範例改寫。

---

## 修正範例生成規則

### 什麼時候給範例
```
□ severity ≥ major → 必須提供修正範例
□ 問題是語氣/措辭相關 → 給出 before/after 對比
□ 問題是結構相關 → 給出建議的段落結構
□ 問題是缺失相關 → 給出建議新增的段落範本
```

### Before/After 範例格式
```
Issue: G5-003 — 因果語言超出設計
Severity: major

BEFORE (原文):
  "Our results prove that mindfulness meditation causes
  a reduction in cortisol levels."

AFTER (修正建議):
  "Our results suggest an association between mindfulness
  meditation and lower cortisol levels. However, the
  cross-sectional design of this study precludes causal
  inference, and the observed relationship may be influenced
  by unmeasured confounders such as baseline stress levels
  and lifestyle factors."

CHANGES:
  - "prove" → "suggest an association"
  - "causes" → removed (cross-sectional cannot establish causation)
  - Added limitation acknowledgment
  - Added potential confounders
```

### 缺失段落範本
```
Issue: G5-008 — Limitations 段完全缺失
Severity: major

SUGGESTED ADDITION:
  "This study has several limitations. First, [design limitation
  specific to this study]. Second, [sample limitation]. Third,
  [measurement limitation]. Fourth, [generalizability limitation].
  Future work should address these limitations by [specific
  suggestions]."

EXAMPLE (based on this paper's context):
  "This study has several limitations. First, the cross-sectional
  design prevents causal inference about the relationship between
  social media use and academic performance. Second, our sample
  was drawn from a single university, limiting generalizability.
  Third, social media use was measured via self-report, which
  may be subject to recall bias. Fourth, we did not control for
  mental health status, which may confound the observed
  association. Future work should employ longitudinal designs
  with objective social media usage tracking."
```

### 統計報告修正
```
Issue: G4-005 — 統計報告不完整（只有 p 值）
Severity: major

BEFORE:
  "The difference was significant (p = .03)."

AFTER:
  "The treatment group showed significantly lower scores
  than the control group (M = 4.2, SD = 1.1 vs. M = 5.1,
  SD = 1.3; t(98) = 3.71, p = .03, d = 0.74, 95% CI
  [0.32, 1.16])."

ADDED:
  - Descriptive statistics (M, SD)
  - Test statistic with df
  - Effect size (Cohen's d)
  - 95% confidence interval
```

## 與 Audience 參數的整合
```
audience = "expert":
  修正範例使用完整學術語言
  
audience = "student":
  修正範例附帶解釋「為什麼這樣改」
  
audience = "self-check":
  只給 before/after，不加解釋
```

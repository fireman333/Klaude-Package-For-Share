# Rejection Risk Score — 被拒風險量化

## 我們有、OpenReviewer 沒有。這是超越。

**校準聲明**：本公式基於啟發式規則，未經真實 accept/reject 資料校準。
分數僅供相對比較（「修這個問題能降多少風險」），不代表精確的被拒機率。
如果未來有標註資料，應用 logistic regression 校準替換此公式。

## 目的
在投稿前量化被拒絕的風險，讓作者知道「現在投出去有多大機率被拒」以及「做什麼改進能最大幅度降低風險」。

---

## 風險計算模型

### 基礎分數（從 issue 計算）
```
base_risk = 0.0

for issue in issues:
  if issue.severity == "critical":
    base_risk += 0.25  (每個 critical 加 25%)
  elif issue.severity == "major":
    base_risk += 0.08  (每個 major 加 8%)
  elif issue.severity == "minor":
    base_risk += 0.02  (每個 minor 加 2%)

base_risk = min(base_risk, 0.95)  # 上限 95%
```

### 修正因子
```
# 有 Limitations → 減少風險（表示作者有自覺）
if has_limitations and len(limitations) >= 3:
  risk *= 0.85

# 有 novelty → 減少風險
if novelty_score == "high":
  risk *= 0.80

# 引用有問題 → 大幅增加風險（審稿人最容易發現）
if hallucinated_citations > 0:
  risk = min(risk + 0.30, 0.95)

# 無統計顯著性報告 → 增加風險
if no_significance_tests:
  risk *= 1.15
```

### 風險等級
```
Risk < 20%:  🟢 LOW — 可以投稿
Risk 20-40%: 🟡 MEDIUM — 建議修正後再投
Risk 40-60%: 🟠 HIGH — 需要重大修改
Risk > 60%:  🔴 VERY HIGH — 不建議投稿，先大幅修訂
```

### 改進優先級
```
對每個 issue 計算：
  risk_reduction = 如果修正這個 issue，風險降多少？
  effort = 修正這個 issue 需要多少工作量？
  priority = risk_reduction / effort

按 priority 排序 → 作者知道先修什麼 ROI 最高。
```

## 報告格式
```
═══ REJECTION RISK ASSESSMENT ═══
Current risk: 47% 🟠 HIGH

Top 3 improvements (by ROI):
  1. Fix overclaim in Discussion → risk drops to 35% (🟡)
     Effort: LOW (reword 3 sentences)
  2. Add missing baseline → risk drops to 28% (🟡)
     Effort: MEDIUM (run 1 additional experiment)
  3. Add Limitations section → risk drops to 24% (🟡)
     Effort: LOW (write 1 paragraph)

After all fixes: estimated risk = 18% 🟢
```

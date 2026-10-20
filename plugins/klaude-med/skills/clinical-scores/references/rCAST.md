# rCAST Score

**來源文獻：** Refined CAST (rCAST) — post-cardiac arrest prognostic score  
**適用對象：** OHCA/IHCA 病人，ROSC 後在 ICU 的預後評估

---

## 計算公式

```
rCAST = 1.0 × (Initial Rhythm)
      + 2.0 × (Witness/until ROSC time)
      + 2.5 × (pH)
      + 0.5 × (Lactate)
      + 4.5 × (GCS Motor)
```

**分數範圍：0 ~ 18.5（越高越差）**

---

## 各組成分數對應表

### Initial Rhythm（權重 × 1.0）
| 分數 | 0 | 1 |
|------|---|---|
| 判定 | Shockable | Non-Shockable |

### Witness / until ROSC time（權重 × 2.0）
| 分數 | 0 | 1 | 2 |
|------|---|---|---|
| 判定 | Witnessed + CPR < 20 min | Witnessed + CPR ≥ 20 min | No Witness |

### pH（權重 × 2.5）
| 分數 | 0 | 1 | 2 | 3 |
|------|---|---|---|---|
| 判定 | ≥ 7.31 | 7.16–7.30 | 7.01–7.15 | ≤ 7.00 |

### Lactate（權重 × 0.5，單位 mmol/L）
| 分數 | 0 | 1 | 2 | 3 |
|------|---|---|---|---|
| 判定 | ≤ 5.0 | 5.1–10.0 | 10.1–14.0 | ≥ 14.1 |

### GCS Motor（權重 × 4.5）
| 分數 | 0 | 1 |
|------|---|---|
| 判定 | ≥ 2 | 1 |

---

## 嚴重度分層（Tertile-based，來自 TIMECARD registry）

| 分組 | rCAST 範圍 | Survival Rate | Favorable CPC Rate |
|------|-----------|--------------|-------------------|
| Low Risk | 0 – 8.0 | ~58.7% | ~49.2% |
| Moderate Risk | 8.5 – 13.0 | ~37.4% | ~21.3% |
| High Risk | 13.5 – 18.5 | ~18.6% | ~5.6% |

（Trend test p < 0.001 for both outcomes）

---

## AUC 判別力（TIMECARD registry, n=1,086）

| Outcome | AUC (95% CI) | Youden Cutoff | Sensitivity | Specificity |
|---------|-------------|--------------|-------------|-------------|
| Survival to discharge | 0.722 (0.693–0.752) | 11.0 | 0.622 | 0.714 |
| Favorable CPC (CPC 1–2) | 0.802 (0.773–0.830) | 7.5 | 0.826 | 0.629 |

---

## Logistic Regression（per 1-point increase）

| Outcome | OR | 95% CI | p-value |
|---------|-----|--------|---------|
| Survival | 0.843 | 0.820–0.867 | <0.001 |
| Favorable CPC | 0.778 | 0.751–0.806 | <0.001 |

---

## 欄位對應（TIMECARD 資料庫）

| rCAST 組成 | 欄位名稱 | 備註 |
|-----------|---------|------|
| Initial Rhythm | `ini_shockable` | 1=shockable, 0=non-shockable |
| Witness/ROSC | `wit_collapse` + `cpr_duration` | wit=0 或 NaN → No Witness (=2) |
| pH | `ca_ph` | 心跳停止時動脈血 pH |
| Lactate | `ca_la` | 心跳停止時乳酸 (mmol/L) |
| GCS Motor | `gcs_m_rosc` | ROSC 後 GCS Motor |

---

## 分析腳本位置

（本套件不附分析腳本；請依上方欄位對應表自行撰寫計算程式。）

# Experiment Guard: Observational Studies

## 何時載入
當研究設計為觀察性研究（cohort, case-control, cross-sectional）時。

---

## 觀察性研究設計檢查清單

### 研究類型辨識
```
□ 明確標記研究類型？
  - Cohort（追蹤暴露組 vs. 非暴露組 → 看結果）
  - Case-control（比較有結果 vs. 無結果 → 看暴露）
  - Cross-sectional（同一時間點測量暴露和結果）
  - Ecological（群體層級，非個體層級）

□ 是否有因果宣稱超出設計允許？
  - Cross-sectional → 只能說「相關」
  - Cohort → 可以說「預測」但因果仍需謹慎
  - Case-control → 只能計算 OR，不能算 RR
```

### 混淆變項控制（觀察性研究核心問題）
```
□ 已辨識的混淆變項列表？
□ 控制策略？
  - 統計調整（多變量回歸）
  - 傾向分數匹配（propensity score matching）
  - 工具變項（instrumental variables）
  - 差異中的差異（difference-in-differences）
□ 殘餘混淆（residual confounding）是否被討論？
□ 未測量的混淆變項是否被承認？
  → 至少列出 3 個可能但未能控制的混淆變項
□ 敏感度分析是否做了？
  - E-value：需要多強的未測混淆才能解釋掉效果？
```

### 偏誤檢查清單
```
□ 選擇偏誤
  - 樣本如何選取？是否代表目標族群？
  - 自願者偏誤？健康工人效應？
□ 資訊偏誤
  - 暴露和結果的測量是否獨立？
  - 回憶偏誤（case-control 特有）？
  - 測量工具的信效度？
□ 時序性
  - 暴露是否確定在結果之前？
  - 如果無法確認 → 無法推論因果方向
□ 倖存者偏誤
  - 是否只分析了「存活」的樣本？
□ 反向因果
  - A→B 和 B→A 都合理嗎？
```

### 報告標準
```
□ 是否遵循 STROBE 聲明？
  - Cohort: STROBE-cohort
  - Case-control: STROBE-cc
  - Cross-sectional: STROBE-cs
□ 缺失資料的處理方式是否報告？
□ 敏感度分析的結果是否報告？
```

### 因果推論語言校準
```
觀察性研究允許的語言：
  ✅ "associated with", "correlated with"
  ✅ "predicted", "prospectively linked to"
  ✅ "suggests a relationship between"
  ⚠ "may contribute to"（需要機制支持）
  ❌ "causes", "leads to", "due to"
  ❌ "effect of", "impact of"（暗示因果）
```

## 輸出格式
```
## 觀察性研究設計檢查補充
- 研究類型：[cohort/case-control/cross-sectional]
- 混淆控制：[N] 個已控制 / [N] 個未控制
- 偏誤風險：[選擇/資訊/時序/倖存者] 各 [Low/Medium/High]
- STROBE 完整性：[完整/部分/缺失]
- 因果語言合規：[合規/有超出]
```

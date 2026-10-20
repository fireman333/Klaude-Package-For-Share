# Result Guard: Bayesian Statistics

## 何時載入
當結果報告使用貝氏統計方法（Bayes Factor, 後驗分佈, MCMC 等）時。

---

## 報告規範檢查

### Bayes Factor 報告
```
□ BF 值的方向是否明確？
  - BF₁₀ = 支持 H₁ 對 H₀ 的證據
  - BF₀₁ = 支持 H₀ 對 H₁ 的證據
  - BF₁₀ = 1/BF₀₁
□ BF 的解讀是否適當？
  BF₁₀ 1-3:    Anecdotal evidence
  BF₁₀ 3-10:   Moderate evidence
  BF₁₀ 10-30:  Strong evidence
  BF₁₀ 30-100: Very strong evidence
  BF₁₀ > 100:  Extreme evidence
□ BF < 1 是否被正確解讀為支持虛無假設的證據？
□ 先驗分佈的選擇是否報告和合理化？
```

### 後驗分佈報告
```
□ 後驗分佈的摘要統計是否完整？
  - 中位數或均值
  - 95% HDI（Highest Density Interval）或 credible interval
□ HDI 是否包含實際等價區域 (ROPE)？
  - 完全在 ROPE 外 → 效果存在
  - 完全在 ROPE 內 → 效果實際上為零
  - 部分重疊 → 不確定
□ 後驗分佈的形狀是否報告/視覺化？
```

### MCMC 診斷
```
□ 收斂診斷是否報告？
  - R̂ (Gelman-Rubin) < 1.01
  - ESS (Effective Sample Size) > 400
  - 軌跡圖（trace plot）無明顯趨勢
□ Chain 數量？（≥ 4 recommended）
□ Warm-up / burn-in 期是否足夠？
□ 發散轉換（divergent transitions）？
  - > 0 → 模型可能有問題
```

### 先驗敏感度分析
```
□ 是否做了先驗敏感度分析？
  - 使用不同先驗重新分析 → 結論是否穩健？
□ 先驗是否為 informative？
  - 如果是 → 需要明確合理化來源
□ 預設先驗（default priors）是否適合該問題？
  - 例：Cauchy(0, √2/2) 對於效果量可能太寬
```

### Bayesian 模型比較
```
□ 如果做了模型比較（WAIC, LOO-CV）：
  - 是否報告了 SE？
  - 模型間的差異是否超出 SE？
  - 是否考慮了模型平均（model averaging）？
□ 是否避免了「Bayesian p-hacking」？
  - 嘗試多個先驗，只報告支持假設的結果
```

## ROPE 分析檢查
```
如果報告使用了 ROPE (Region of Practical Equivalence)：
□ ROPE 區間的設定是否有文獻依據？
  - 醫學：通常基於 MCID（最小臨床重要差異）
  - 行為科學：常見 [-0.1, 0.1] 的 Cohen's d 等效
□ 後驗落在 ROPE 外的比例是否報告？
  - > 95% outside ROPE → "practically meaningful"
  - > 89% outside → "can be considered meaningful" (weaker)
  - < 89% → "undecided"
□ ROPE 結論是否與 HDI 一致？
  - 如果整個 95% HDI 落在 ROPE 外 → 強證據
  - 如果 HDI 部分重疊 ROPE → 結論不確定
□ ROPE 寬度是否合理？
  - 太窄 → 容易宣稱效果存在（寬鬆）
  - 太寬 → 容易宣稱效果為零（保守）
```

## 輸出格式
```
## Bayesian 統計驗證
- BF 報告：[正確/方向不明/解讀有誤]
- 先驗選擇：[合理化/預設/未報告]
- MCMC 診斷：R̂=[X] ESS=[N] 發散=[N]
- 先驗敏感度：[已做/未做]
- 結論穩健性：[穩健/先驗依賴/不確定]
```

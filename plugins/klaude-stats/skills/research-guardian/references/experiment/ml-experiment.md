# Experiment Guard: ML Experiments

## 何時載入
當實驗設計為機器學習/深度學習實驗時。

---

## ML 實驗設計檢查清單

### 資料來源多樣性
```
□ 資料來自幾個獨立來源？
  - 1 個來源 → 🟡 WARN：泛化性未知，結論必須限定
  - 2-3 個來源 → ✅：基本的多樣性
  - 4+ 個來源 → ✅：較強的泛化性證據
□ 如果單一來源，是否在 Discussion 中明確標記為 limitation？
□ 跨機構/跨地區的資料差異是否被考慮？
```


### 資料分割
```
□ Train / Validation / Test 分割比例合理？
  - 常見：70/15/15 或 80/10/10
□ 分割方式正確？
  - 隨機分割 → 確認分層抽樣（stratified）
  - 時間序列 → 必須按時間分割，不能隨機
  - 群組數據 → 確認同一群組不跨越 train/test
□ 資料洩漏（data leakage）檢查？
  - 前處理（normalization, feature engineering）是否只在 train set 上 fit？
  - 特徵選擇是否只用 train set 的資訊？
  - 是否有未來資訊洩漏？（時序問題）
□ Test set 是否只被用了一次？
  - 在 test set 上反覆調參 = 間接過擬合
```

### 基線比較
```
□ Baseline 是否包含？
  - Random baseline（下限）
  - Simple baseline（例：logistic regression, majority vote）
  - 已知 SOTA（上限參考）
□ Baseline 是否使用最佳實踐配置？
  ❌ 弱 baseline → 讓自己的方法看起來更好
  ✅ 認真調參的 baseline → 公平比較
□ Baseline 使用相同的資料前處理和分割？
□ Baseline 結果來源？（自己跑 vs. 引用論文數字）
  - 引用論文數字 → 確認實驗條件是否一致
```

### 超參數與可重現性
```
□ 超參數搜索策略報告？
  - Grid search / Random search / Bayesian optimization
  - 搜索範圍和最終選定值
□ 報告所有嘗試還是只報告最佳？
  ❌ 只報告最佳結果
  ✅ 報告搜索過程和最佳結果
□ 隨機種子固定且報告？
  - 至少 3-5 個不同種子的結果（報告 mean ± std）
□ 計算資源報告？
  - GPU 型號、訓練時間、記憶體用量
  - CO₂ 排放估計（如適用）
□ 環境報告？
  - Python 版本、PyTorch/TF 版本、CUDA 版本
  - 或提供 requirements.txt / Docker image
```

### 評估指標
```
□ 指標是否適合任務和資料？
  - 不平衡分類 → accuracy 不夠，需要 F1/AUROC/AUPRC
  - 排序任務 → MRR, NDCG, MAP
  - 生成任務 → BLEU/ROUGE 已知有限制，需要人工評估
□ 是否報告了信賴區間或標準差？
□ 統計顯著性檢驗？
  - Paired t-test 或 McNemar's test 比較兩個模型
  - 多模型比較 → Friedman test + post-hoc
□ 效果量是否實際有意義？
  - 0.1% accuracy 差異在 N=1M 上可以顯著但無意義
```

### ML 特有反模式
```
⚠ 計算不對稱：用 100 GPU hours 的模型打敗 1 GPU hour 的 baseline
  修正：報告 accuracy-per-FLOP 或 Pareto 圖

⚠ Prompt 工程 vs. 方法創新：
  如果核心改進只是更好的 prompt → 貢獻類型要誠實標記

⚠ 測試集選擇偏誤：
  只在自己方法表現好的 benchmark 上報告
  修正：在領域公認的標準 benchmark 上報告

⚠ 消融研究不完整：
  只移除一個組件看效果下降，不做加法消融
  修正：做 additive（逐步加入）和 subtractive（逐步移除）消融
```

## 輸出格式
```
## ML 實驗設計檢查補充
- 資料洩漏風險：[Low/Medium/High]
- Baseline 公平性：[公平/偏向自己方法]
- 可重現性等級：[seed ✅ code ✅ data ✅ env ✅] → [HIGH/MED/LOW]
- 反模式觸發：[列出]
```

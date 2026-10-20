# Result Guard: ML Performance Metrics

## 何時載入
當結果報告涉及機器學習模型的效能指標時。

---

## 指標選擇適當性

### 分類任務
```
□ 資料是否平衡？
  - 不平衡（minority < 20%）→ accuracy 不可信
  - 不平衡時必須報告：precision, recall, F1, AUROC, AUPRC
□ 報告了哪些指標？
  - Accuracy：只在平衡資料上有意義
  - Precision：false positive 代價高時重要（如：spam 偵測）
  - Recall：false negative 代價高時重要（如：癌症篩檢）
  - F1：precision 和 recall 的調和平均
  - AUROC：門檻無關的整體效能
  - AUPRC：不平衡資料上比 AUROC 更有意義
□ 是否報告了 confusion matrix？
□ 門檻（threshold）是否明確且合理化？
```

### 迴歸任務
```
□ MSE/RMSE：對異常值敏感
□ MAE：較穩健
□ R²：解釋的變異比例
  - R² 可以為負（比 mean baseline 更差）
  - R² = 0.99 → 可能過擬合，需懷疑
□ 是否報告了殘差分析？
```

### 排序/推薦任務
```
□ MRR (Mean Reciprocal Rank)
□ NDCG@K
□ MAP (Mean Average Precision)
□ Hit Rate@K
□ K 的選擇是否合理且一致？
```

### 生成任務
```
□ 自動指標的限制是否被承認？
  - BLEU/ROUGE 與人類判斷的相關性有限
  - Perplexity 不等於生成品質
□ 是否有人工評估補充？
  - Likert scale? Elo rating? Preference ranking?
  - 評估者數量和 inter-rater agreement (Cohen's κ)?
□ LLM-as-judge 是否有 bias 檢查？
  - 位置偏誤、冗長偏誤、自我偏誤
```

### 統計嚴謹性
```
□ 結果是否報告了 mean ± std（多次實驗）？
□ 種子數量 ≥ 3？（推薦 5-10）
□ 是否做了統計顯著性檢驗？
  可接受的替代（ML 領域慣例）：
    - mean±std 的 CI 不重疊 ≈ 可接受的顯著性證據
    - 但只限於 seeds ≥ 5 且 std 合理的情況
    - 最佳實踐仍然是做 paired test
  - paired t-test 或 bootstrap test
□ 差異是否實際有意義？
  - 0.1% accuracy 差異即使顯著也可能無意義
  - 報告「改進的實際意義」不只是數字
□ 是否有 error bar 或 CI 在圖表中？
```

### 常見可疑信號
```
⚠ accuracy = 100% 或 loss = 0 → 資料洩漏
⚠ 所有模型結果完全相同 → 可能沒有真的跑不同配置
⚠ test accuracy > train accuracy → 不正常
⚠ 大幅超越 SOTA → 確認實驗條件是否公平
⚠ 只報告 best run 不報告 average → cherry-picking
⚠ validation 結果完美但 test 結果不報告 → 可能 test 很差
```

## 輸出格式
```
## ML 指標驗證
- 指標-任務匹配：[適當/不足]
- 不平衡處理：[已處理/未處理/N/A]
- 統計嚴謹性：[mean±std ✅] [顯著性 ✅/❌] [種子數 N]
- 可疑信號：[列出]
```

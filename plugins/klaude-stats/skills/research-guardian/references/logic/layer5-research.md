# Logic Layer 5: Research-Specific Fallacies Deep Guide

## 何時載入
當 Result Guard 啟動 Layer 5 時。專門針對 AI 做 ML 研究的推理陷阱。

---

## 研究特有謬誤的操作化檢查

### Benchmark 泛化謬誤
```
偵測信號：
  "achieves state-of-the-art on [benchmark]" → 直接推論到真實場景
  
檢查步驟：
  1. Benchmark 是否代表真實使用場景？
     - ImageNet ≠ 工業視覺檢測
     - GLUE/SuperGLUE ≠ 實際的 NLP 應用
  2. Benchmark 的資料分佈是否與目標場景一致？
  3. Benchmark 是否已被「遊戲化」？（被過度優化）
  4. 是否在非標準 benchmark 上做了驗證？

修正模板：
  "Our method achieves [score] on [benchmark]. We note that [benchmark]
   [specific limitation]. Performance in [real-world scenario] may differ
   due to [distributional shift / domain gap / etc.]."
```

### 消融 ≠ 必要性
```
偵測信號：
  "Removing component X decreases performance → X is essential"
  
問題：
  - 移除 X 後用 Y 替代可能同樣有效
  - X 的效果可能依賴於與其他組件的特定組合
  - X 的效果可能因超參數配置而異

修正：
  - 做 additive 消融（從零開始逐步加入）和 subtractive（逐步移除）
  - 報告 "X contributes [N]% in our configuration"
    而非 "X is essential"
```

### SOTA 幻覺
```
偵測信號：
  "Our method outperforms all baselines"

檢查步驟：
  1. Baseline 列表是否完整？
     → 檢查 Papers With Code 的排行榜
  2. Baseline 最後確認日期是什麼時候？
  3. 是否有更新的工作已經超越了報告的「SOTA」？
  4. Baseline 配置是否公平？（同等計算資源？同等調參？）

修正：
  "As of [date], our method achieves the highest [metric] on [benchmark]
   among the methods we compared. More recent concurrent work may exist."
```

### 規模外推
```
偵測信號：
  "Given the trend at [small scale], we expect [conclusion at large scale]"

問題：
  - Scaling laws 不是線性的
  - 可能有 phase transition（某個規模以上行為突然改變）
  - 計算成本的外推也可能不準確

修正：
  - 在至少 3 個不同規模上驗證趨勢
  - 討論 scaling law 的不確定性
  - 明確標示外推範圍
```

### 人類等價謬誤
```
偵測信號：
  "Our model achieves human-level performance"

問題：
  - 「人類水準」的定義是什麼？（專家？普通人？群眾？）
  - AI 和人類的錯誤模式可能完全不同
  - AI 可能在簡單題目上出錯，困難題目上答對
  - 準確率相同 ≠ 能力相同

修正：
  - 報告 error analysis（AI 和人類各在哪裡犯錯）
  - 使用 agreement 而非只比較 accuracy
  - 報告 complementarity（AI + 人類 > 任一單獨）
```

### 負面結果壓制
```
偵測信號：
  - 只報告成功的實驗
  - 完整實驗日誌缺失
  - 某些 baseline 或條件的結果被省略

檢查步驟：
  1. 實驗設計中提到了 N 個條件，結果中是否報告了全部 N 個？
  2. 是否有「補充材料中的其他結果」暗示被省略的內容？
  3. 失敗的嘗試是否被討論？

修正：
  所有實驗結果（包括負面的）都應報告。
  負面結果可以放在 Appendix 但必須在正文中提及。
```

### 複雜度幻覺
```
偵測信號：
  複雜方法只比 simple baseline 好一點點

檢查步驟：
  1. 改進幅度是多少？
  2. 複雜度增加了多少？（參數量、計算時間、記憶體）
  3. 複雜度-效能的 trade-off 是否值得？
  
修正：
  - 報告 Pareto frontier（效能 vs. 複雜度）
  - 與 simple baseline 的差異是否統計顯著？
  - 在實際部署場景中，額外的複雜度是否可接受？
```

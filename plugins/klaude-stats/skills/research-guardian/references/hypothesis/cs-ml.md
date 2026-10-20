# Hypothesis Guard: Computer Science / ML Domain

## 何時載入
當研究假設涉及機器學習、深度學習、NLP、電腦視覺、系統架構、演算法設計時。

---

## CS/ML 假設的特殊要求

### 1. Novelty 驗證（ML 領域高風險）
```
□ 是否搜索了以下來源？
  - arXiv（cs.LG, cs.CL, cs.CV, cs.AI）— 預印本常比期刊早 6-12 個月
  - Papers With Code — 確認 SOTA 排行榜
  - Semantic Scholar — 引用網絡追蹤
  - 頂會 proceedings（NeurIPS, ICML, ICLR, ACL, CVPR, AAAI）
□ 是否檢查了「換了名字的舊概念」？
  ML 領域常見：同一技術用不同名字重新發表
  - Attention ≈ soft alignment ≈ weighted pooling
  - Prompt tuning ≈ prefix tuning ≈ soft prompts（微妙差異）
  - 確認你的 novelty 不只是術語創新
□ 是否檢查了同期（concurrent）工作？
  arXiv 時代，多組人可能同時做類似研究
```

### 2. 可重現性設計
```
□ 假設是否可以用公開資料集驗證？
  - 如果需要私有資料 → 標記為 limited reproducibility
□ 計算資源需求是否合理？
  - 如果需要 100+ GPU hours → 大多數人無法重現
  - 必須報告計算預算
□ 是否有明確的 baseline 可以比較？
  - 已有 SOTA → 必須與之比較
  - 無明確 SOTA → 使用合理的 simple baseline
□ 隨機種子和超參數是否會被記錄？
```

### 3. ML 假設常見陷阱
```
⚠ Benchmark ≠ 真實世界
  假設："在 ImageNet 上表現好 → 在醫療影像上也好"
  修正：明確限定為 "在 [具體 benchmark] 上驗證"

⚠ 規模外推陷阱
  假設："在小資料集上的趨勢 → 放大後也成立"
  修正：討論 scaling behavior 和 phase transition 風險

⚠ 消融 ≠ 必要性
  假設："移除 X 效果下降 → X 是關鍵創新"
  修正："X 在本配置中有貢獻" ≠ "X 是唯一解法"

⚠ 超參數敏感度
  假設可能在特定超參數下成立但在其他配置下不成立
  修正：假設中明確預期的超參數敏感度

⚠ 測試集過擬合
  在已被廣泛使用的 benchmark 上刷分，可能是間接的測試集過擬合
  修正：在至少一個較新/較少使用的 benchmark 上驗證

⚠ SOTA 過期風險
  ML 領域 SOTA 更新速度快，投稿時可能已被超越
  修正：記錄 baseline 搜索的截止日期
```

### 4. 系統性研究 vs. 增量改進
```
評估假設的貢獻類型：

 新架構/範式      → 高風險高報酬，需要強實驗支持
 改進現有方法      → 需要 ablation 證明改進來源
 新的應用場景      → 需要證明為什麼現有方法不適用
 理論分析         → 需要實驗驗證理論預測
 資料集/Benchmark  → 需要證明與現有資源的差異和價值
 負面結果/複現     → 需要嚴格的實驗設計和統計效力

假設的 framing 必須與貢獻類型對齊。
```

### 5. 搜索策略
```
第一輪：廣度搜索
  "[方法名] + [任務名]"
  "[方法類別] survey 2024 2025"

第二輪：精確搜索
  "[具體技術] + [具體 benchmark]"
  "[作者] + [相關關鍵詞]"（追蹤活躍的研究組）

第三輪：反向搜索
  "[方法] limitation"
  "[方法] failure cases"
  "[方法] does not work"

必查：Papers With Code 的 SOTA 排行和 Methods 頁面
```

---

## 輸出格式
```
## CS/ML 假設驗證補充報告
- Novelty 狀態：[novel/incremental/replication] — [最接近工作的差異]
- 貢獻類型：[architecture/improvement/application/theory/dataset/negative]
- 可重現性：[HIGH/MEDIUM/LOW] — [公開資料 ✅/❌] [計算預算]
- SOTA 檢查：[當前 SOTA] on [benchmark] = [score] (截至 [日期])
- 已知陷阱觸發：[列出觸發的陷阱]
```

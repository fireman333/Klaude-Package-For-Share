# Writing Guard: Conference Paper

## 何時載入
當撰寫投稿至學術會議的論文時（NeurIPS, ICML, ICLR, ACL, CVPR, CHI 等）。

---

## 會議論文特殊要求

### 頁數限制（硬性）
```
□ 是否在頁數限制內？
  - NeurIPS/ICML/ICLR: 通常 8-10 頁（不含 references）
  - ACL: 8 頁 long / 4 頁 short
  - CVPR: 8 頁
  - CHI: variable（通常 10-12 頁）
□ Appendix/supplementary 的規則？
  - 是否算入頁數？
  - 審稿人是否被要求閱讀？（通常不被要求）
  → 核心內容必須在正文頁數限制內
```

### 盲審合規（雙盲會議）
```
□ 是否移除了所有作者身份標記？
  - 作者姓名和機構
  - acknowledgements（提交時）
  - 自我引用改為第三人稱 "Previous work [X] showed..."
    而非 "In our previous work, we showed..."
  - GitHub repo 連結匿名化
□ 文件 metadata 是否清除？（PDF 的 author 欄位）
□ 圖表中是否有機構 logo？
```

### 會議論文的 Contribution 強調
```
會議論文比期刊更強調「一句話貢獻」：

□ Contribution list 是否在 Introduction 末尾明確列出？
  典型格式：
  "Our contributions are as follows:
   (1) We propose X, which...
   (2) We demonstrate Y on Z benchmarks...
   (3) We release code/data at [anonymous URL]"

□ 每個 contribution 是否可獨立驗證？
□ 是否避免了虛假 contribution？
  ❌ "We provide a comprehensive literature review" → 不算
  ❌ "We apply X to Y for the first time" → 只有 novelty 在 X 才算
```

### 實驗部分的會議標準
```
□ ML 會議通常期望：
  - 多個 benchmark 上的結果（不是只一個）
  - 與最新 SOTA 的比較（不是兩年前的）
  - Ablation study（證明每個組件的貢獻）
  - 計算成本報告
  - 失敗案例分析（limitations）
□ Reproducibility checklist 是否完成？
  - NeurIPS/ICML 有正式的 reproducibility checklist
  - 通常需要在提交時一併提供
```

### Rebuttal 準備
```
會議有 rebuttal 機制：
□ 寫作時是否預想了可能的質疑？
  - 方法的 assumption 是否太強？
  - baseline 是否足夠？
  - 是否有遺漏的相關工作？
□ 是否預留了補充實驗的空間？
  - rebuttal 中常需要加跑實驗
□ 論文中的「明顯弱點」是否已在 Discussion 中先行承認？
  → 主動承認比被審稿人指出好
```

## 輸出格式
```
## Conference 寫作驗證補充
- 頁數：[N] / [limit] — [合規 ✅ / 超出 ❌]
- 盲審合規：[通過 / 有洩漏風險]
- Contribution 清晰度：[明確 / 模糊]
- Reproducibility checklist：[完成 / 部分 / 未完成]
```

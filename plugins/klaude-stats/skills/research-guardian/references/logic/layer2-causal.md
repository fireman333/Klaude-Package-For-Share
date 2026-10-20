# Logic Layer 2: Causal Reasoning Deep Guide

## 何時載入
當 Hypothesis/Experiment/Result Guard 啟動 Layer 2 時。
這是 AI 最常犯錯的 Layer——從相關跳到因果。

---

## 因果推理的操作化檢查

### 步驟 1：提取所有因果宣稱
```
掃描文字中的因果信號詞：
  強因果："causes", "leads to", "results in", "produces",
          "due to", "because of", "effect of", "impact of"
  弱因果："contributes to", "drives", "triggers", "influences"
  安全詞："associated with", "correlated with", "predicts",
          "linked to", "related to"

對每個因果信號詞，記錄：
  - 宣稱的因：[X]
  - 宣稱的果：[Y]
  - 使用的語言：[exact phrase]
  - 支持的研究設計：[observational/RCT/etc.]
```

### 步驟 2：因果強度階梯對照
```
研究設計              允許的最強語言
─────────────────────────────────────
Cross-sectional     → "associated with" only
Case-control        → "associated with", "linked to"
Cohort (prospective)→ "predicts", "prospectively associated"
Quasi-experiment    → "suggests a causal relationship"
RCT                 → "caused", "produced an effect"
RCT Meta-analysis   → "established causal effect"
Mendelian random.   → "genetically associated causal effect"

如果語言強度超過設計允許 → 標記為 MAJOR
```

### 步驟 3：混淆變項檢查
```
對每個因果宣稱 X → Y：
  □ 列出至少 3 個可能的混淆變項 Z
    （Z 同時影響 X 和 Y 的第三因子）
  □ 這些 Z 是否被控制？
    - 統計控制（regression adjustment）
    - 設計控制（randomization, matching）
    - 未控制 → 標記為殘餘混淆風險
  □ 反向因果是否可能？（Y → X）
  □ 是否考慮了中介變項？（X → M → Y）
    - 如果控制了中介變項 → 會低估 X 的效果
```

### 步驟 4：Hill's Criteria 快速檢查（生物醫學）
```
Bradford Hill 因果判斷標準（非硬性，作為參考）：
□ 關聯強度：效果量大嗎？
□ 一致性：多項研究結果一致嗎？
□ 特異性：暴露是否特異性地影響特定結果？
□ 時序性：因在果之前？（唯一硬性要求）
□ 劑量-反應：暴露越多效果越強？
□ 合理性：有生物學機制解釋嗎？
□ 連貫性：與已知知識一致嗎？
□ 實驗證據：有實驗支持嗎？
□ 類比：類似的暴露-結果有先例嗎？
```

### 步驟 5：辛普森悖論檢查
```
□ 整體效果方向是否與子群體一致？
□ 是否有重要的交互作用？
□ 如果按性別/年齡/嚴重度分層，效果是否改變？
如果整體效果是正的但某子群體是負的 → 標記 ⚠ 需解釋
```

## 常見因果推理錯誤的修正模板
```
錯誤：  "X causes Y (based on observational data)"
修正：  "X is associated with Y. While the directionality and
        potential confounders [list] limit causal inference,
        the [strength/consistency/plausibility] of the
        association warrants further investigation through
        [experimental design]."
```

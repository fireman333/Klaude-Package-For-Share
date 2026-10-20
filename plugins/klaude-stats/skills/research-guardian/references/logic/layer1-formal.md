# Logic Layer 1: Formal Logic Deep Guide

## 何時載入
當 Hypothesis Guard 或 Writing Guard 啟動 Layer 1 時。

---

## 形式邏輯謬誤偵測的操作化步驟

### 步驟 1：提取推理鏈
```
從待評估的文字中，提取所有 "因為 A 所以 B" 的推理結構。
每個推理寫成：
  前提 1: [P1]
  前提 2: [P2]（如有）
  結論:   [C]

目標：每段文字提取 0-3 個推理鏈。
```

### 步驟 2：對每個推理鏈跑以下檢查

#### 肯定後件 (Affirming the Consequent)
```
模式：If P then Q. Q observed. Therefore P.
偵測方法：
  1. 結論是否聲稱某個原因成立？
  2. 支持證據是否只是觀察到了預期的結果？
  3. 是否有其他原因也能產生相同結果？

常見偽裝：
  "This is consistent with our hypothesis"
  → 本身沒問題，但如果後續結論變成 "therefore our hypothesis is confirmed"
  → 就是 affirming the consequent

修正模板：
  "The observation of Q is consistent with P, but also consistent with
   alternative explanations including [A1, A2, A3]."
```

#### 否定前件 (Denying the Antecedent)
```
模式：If P then Q. Not P. Therefore not Q.
偵測方法：
  1. 是否因為某個方法失敗就否定了目標的可能性？
  2. 是否因為某個條件不成立就否定了結論？

修正模板：
  "Method P did not achieve Q in our experiments. However, this does not
   preclude Q being achievable through alternative approaches."
```

#### 循環論證 (Circular Reasoning)
```
偵測方法：
  1. 結論是否只是前提的重新表述？
  2. 論證中是否有 A→B→A 的循環？

常見偽裝：
  "Our metric is good because the model scores well on it.
   The model is good because it scores well on our metric."

修正：用獨立的外部標準驗證。
```

#### 不當全稱推論 (Hasty Generalization)
```
偵測信號詞：
  "always", "never", "all", "universally applicable",
  "in general", "as a rule"

偵測方法：
  1. 結論中是否有全稱量詞？
  2. 證據是否只來自有限的樣本/案例？
  3. 樣本是否具有代表性？

修正模板：
  "In the [N] cases/datasets tested, [finding]. Further validation
   across [broader contexts] is needed to assess generalizability."
```

#### 虛假二分法 (False Dilemma)
```
偵測信號：
  "either... or...", "the only two options",
  "if not A, then B"

偵測方法：
  1. 是否呈現了只有兩個選項的框架？
  2. 是否存在第三或更多選項？
  3. 是否存在光譜或程度的差異？

修正模板：
  "While we contrast A and B, intermediate approaches or
   alternative frameworks such as [C, D] may also apply."
```

### 步驟 3：嚴重度判定
```
推理是核心論點的一部分？
  是 + 謬誤確定 → CRITICAL
  是 + 謬誤可能 → MAJOR
  否 + 謬誤確定 → MINOR
  否 + 謬誤可能 → STYLE
```

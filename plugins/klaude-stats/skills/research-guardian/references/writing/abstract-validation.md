# Writing Guard: Abstract Validation

## 何時載入
當 Writing Guard 檢查 Abstract 段落時。

---

## Abstract 結構檢查

### 必要元素（IMRaD 結構）
```
□ Background/Motivation: 為什麼做這個研究？（1-2 句）
□ Problem/Gap: 現有知識的不足是什麼？（1 句）
□ Method: 怎麼做的？（1-3 句）
□ Results: 發現了什麼？（2-3 句，含關鍵數字）
□ Conclusion/Implication: 這代表什麼？（1-2 句）

缺少任何一項 → 🟡 WARN
只有 Background + Conclusion 沒有 Results → 🔴 FAIL
```

### 字數檢查
```
□ 字數是否在目標範圍內？
  - 一般期刊：150-300 字
  - Structured abstract（臨床）：250-350 字
  - 會議：150-250 字
  - 太短 (< 100) → 可能資訊不足 🟡
  - 太長 (> 400) → 可能需要精簡 🟡
```

### Abstract ↔ 正文一致性
```
□ Abstract 中的數字是否與 Results 一致？
  逐一比對：Abstract 提到的每個數值 → Results 中查找
□ Abstract 的結論是否與 Discussion/Conclusion 一致？
□ Abstract 是否提到了正文中沒有的資訊？
  → 🔴 FAIL（Abstract 不能包含正文沒有的新結果）
□ Abstract 是否遺漏了正文的核心發現？
```

### 常見 Abstract 問題
```
⚠ 過度承諾："first ever", "revolutionary", "paradigm shift" 在 abstract 中
⚠ 結論超出 methods："We prove X" 但 methods 是觀察性研究
⚠ 引用在 abstract 中（大多數期刊不允許）
⚠ 縮寫未展開（abstract 應該獨立可讀）
```

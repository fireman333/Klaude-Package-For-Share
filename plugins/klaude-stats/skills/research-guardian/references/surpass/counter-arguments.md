# Counter-Argument Generation — 預生成審稿人質疑

## 我們有、OpenReviewer 沒有。這是超越。

## 目的
不只找出問題，還預測審稿人會怎麼質疑——讓作者可以在投稿前準備好回應，
甚至直接在論文中預先 address 這些質疑。

---

## 從每個 Issue 生成 Counter-Argument

### 生成規則
```
對每個 severity ≥ major 的 issue，生成：

1. Reviewer Question（審稿人可能的措辭）
   - 模擬真實審稿語氣（"The authors claim X, but..."）
   - 具體引用論文中的問題段落
   
2. Expected Author Response（建議的回應策略）
   - 如果可以修正 → "修正方案 + 修正後的範例文字"
   - 如果是設計限制 → "承認 + 解釋為什麼仍然有價值"
   - 如果是合理的反駁 → "反駁的論點和支持證據"

3. Preemptive Fix（在論文中預先處理）
   - 建議在 Discussion/Limitations 中加入的段落
   - 建議在 Methods 中加入的 justification
```

### 範例
```
Issue: G4-003 (major) — 因果語言超出設計允許
  
Reviewer Question:
  "The authors state 'social media use causes poor academic 
  performance' (p.8), but this is a cross-sectional study. 
  How do the authors justify causal language?"

Expected Author Response:
  "We thank the reviewer for this observation. We have revised
  the language to 'social media use is associated with lower
  academic performance.' We acknowledge that our cross-sectional
  design cannot establish causality and have added this to the
  limitations section."

Preemptive Fix:
  → 在 Discussion 中加入：
  "We note that the cross-sectional design of this study
  precludes causal inference. The observed association between
  social media use and academic performance may reflect reverse
  causation or unmeasured confounding factors."
```

## 與 Quick Modes 的整合
```
🟢 QUICK: 不生成 counter-arguments
🟡 STANDARD: 只對 critical issues 生成
🔴 FULL: 對所有 major + critical 生成
/review --persona all: 每個 persona 生成獨立的 counter-arguments
```

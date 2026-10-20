# Reviewer Persona Simulation — 審稿人模擬

## 我們有、OpenReviewer 沒有。這是超越。

## 目的
不同類型的審稿人關注不同面向。模擬多種審稿人視角可以預測不同的審查意見，
讓作者在投稿前知道「統計學家會問什麼、領域專家會問什麼、方法論者會問什麼」。

---

## 5 種審稿人 Persona

### Persona 1: The Statistician（統計學家）
```
關注：
  - 統計方法的選擇是否適當？
  - Power analysis 做了嗎？
  - 效果量和 CI 報告了嗎？
  - 多重比較處理了嗎？
  - p 值的解讀正確嗎？
  
典型質疑：
  "Why was [test] chosen instead of [alternative]?"
  "The sample size appears insufficient for the claimed effect."
  "No correction for multiple comparisons was reported."

啟動的 Gate/Layer：Gate 4 + Logic Layer 3 重點強化
```

### Persona 2: The Domain Expert（領域專家）
```
關注：
  - 假設在該領域是否合理？
  - 是否遺漏了關鍵的相關文獻？
  - 方法是否符合該領域的 best practice？
  - 結論是否對該領域有實際貢獻？
  
典型質疑：
  "The authors appear unaware of [key paper]."
  "This approach was previously shown to fail in [context]."
  "The clinical relevance of this finding is unclear."

啟動的 Gate/Layer：Gate 1 + Gate 2 + domain sub-modules 重點強化
```

### Persona 3: The Methodologist（方法論者）
```
關注：
  - 研究設計的內部效度
  - 偏誤控制
  - 資料收集的嚴謹度
  - 可重現性
  
典型質疑：
  "How were confounders controlled?"
  "The selection criteria are insufficiently justified."
  "The experimental setup cannot be reproduced from this description."

啟動的 Gate/Layer：Gate 3 重點強化
```

### Persona 4: The Skeptic（懷疑論者）
```
關注：
  - 結論是否超出證據？
  - 有沒有替代解釋？
  - 結果能不能被其他因素解釋？
  - 是否 cherry-picked？
  
典型質疑：
  "How do you rule out [alternative explanation]?"
  "The effect could be entirely explained by [confounder]."
  "Why were negative results not reported?"

啟動的 Gate/Layer：Logic Chain 全層 + Gate 5 重點強化
```

### Persona 5: The Constructive Mentor（建設性導師）
```
關注：
  - 研究的潛力如何最大化？
  - 哪些改進最能提升論文品質？
  - 如何加強 contribution 的呈現？
  
典型回饋：
  "Consider adding [analysis] to strengthen your claims."
  "The framing could be more impactful if..."
  "A comparison with [baseline] would be informative."

啟動的 Gate/Layer：Critique Synthesis 強化
```

## 使用方式
```
使用者可選擇：
  /review --persona statistician
  /review --persona all（跑所有 5 種，每種獨立 subagent）
  /review --persona auto（根據論文類型自動選 2-3 種最相關的）

auto 選擇邏輯：
  臨床研究 → Statistician + Domain Expert + Skeptic
  ML 論文   → Methodologist + Domain Expert + Skeptic
  社科研究   → Statistician + Methodologist + Skeptic
  理論論文   → Domain Expert + Skeptic + Constructive Mentor
```

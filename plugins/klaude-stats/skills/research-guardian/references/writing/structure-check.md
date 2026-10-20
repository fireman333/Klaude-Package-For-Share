# Writing Guard: Structure Check

## 何時載入
當 Writing Guard 檢查論文整體結構時。

---

## 章節完整性檢查

### 必要章節（IMRaD + 擴展）
```
□ Title — 存在且完整
□ Abstract — 存在（詳見 abstract-validation.md）
□ Introduction — 存在
  - 包含研究動機？
  - 包含 research gap？
  - 包含研究目的/假設？
  - 以 contribution list 結束？（會議論文）
□ Related Work / Background — 存在
  - 與 Introduction 的 gap 是否對齊？
□ Methods / Methodology — 存在
  - 足夠詳細到可重現？
□ Results / Experiments — 存在
  - 只報告事實，不含解讀？
□ Discussion — 存在
  - 與 Introduction 的問題對應？
  - 包含替代解釋？
  - 包含與現有文獻的比較？
□ Limitations — 存在
  - ≥ 3 項具體限制（不是泛泛而談）
□ Conclusion — 存在
  - 不重複 Discussion
  - 包含未來方向？
□ References — 存在且非空
□ Appendix/Supplementary — 如有，是否在正文中被引用？
```

### 章節順序
```
標準順序：Title → Abstract → Intro → Related Work → Methods → 
Results → Discussion → Limitations → Conclusion → References

可接受的變體：
  - Related Work 放在 Methods 之後（某些會議慣例）
  - Results and Discussion 合併（某些期刊允許）
  - Limitations 嵌入 Discussion 中（常見）
  
不可接受：
  - Methods 在 Results 之後
  - Discussion 在 Results 之前
  - Conclusion 在 Discussion 之前
```

### 章節平衡
```
□ 各章節的篇幅是否合理？
  Introduction: 10-15% 
  Related Work: 10-15%
  Methods: 20-30%
  Results: 20-30%
  Discussion: 15-20%
  
⚠ Methods 只佔 5% → 細節可能不足
⚠ Results 佔 50% → 可能缺乏分析和解讀
⚠ Discussion 只佔 5% → 可能缺乏深度
```

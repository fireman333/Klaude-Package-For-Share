# Literature Guard: Gap Framing Validation

## 何時載入
當 Literature Guard 評估 Related Work / Introduction 的 gap construction 時。

---

## Gap Framing 誠實度檢查

### Gap 是否真實存在？
```
□ 作者宣稱的 "gap" 是否有文獻支持？
  - "No prior work has studied X" → 搜索確認是否真的沒有
  - "Previous methods cannot handle Y" → 搜索確認是否真的不能
□ 是否選擇性引用來製造 gap？
  - 只引用較弱的先前工作 → 忽略了更強的
  - 只引用較早的 → 忽略了最新的
□ Gap 是否有意義？
  - "No one has applied X to dataset Z" → 可能是因為不值得做
  - 技術可行性 gap ≠ 研究價值 gap
```

### 先前工作描述的公平性
```
□ 先前工作的描述是否準確反映原文？
  - 是否只描述缺點不提優點？
  - 是否用過於簡化的方式描述複雜的方法？
  - 引用的限制是否是原作者自己承認的（還是作者強加的）？
□ 比較是否公平？
  - 是否在相同條件下比較？
  - 是否用先前工作的最佳配置？
```

### Gap 與 Contribution 的對齊
```
□ Introduction 建構的 gap 是否與 Methods 的設計對應？
  - Gap: "cannot handle long sequences" → Methods 是否真的解決長序列？
□ 每個 contribution 是否對應至少一個 gap？
  - 有 gap 但沒有對應的 contribution → 結構不完整
  - 有 contribution 但沒有對應的 gap → motivation 不足
```

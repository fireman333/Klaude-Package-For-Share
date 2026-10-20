# Writing Guard: Language Quality

## 何時載入
當 Writing Guard 執行時，作為語言層面的檢查（補充語氣/結構的檢查）。

---

## 語言品質檢查清單

### 語法與拼字
```
□ 是否有明顯的語法錯誤？
  - 主詞動詞不一致
  - 時態不一致（Methods 用過去式，Results 混用現在式）
  - 懸垂修飾語
□ 專業術語拼寫是否正確？
  - "Gaussian" 不是 "Guassian"
  - "Bayesian" 不是 "Baysian"
  - "heterogeneity" 不是 "heterogenity"
□ 非母語寫作的常見錯誤？
  - 冠詞使用（a/an/the）
  - 介系詞選擇
  - 可數/不可數名詞
```

### 可讀性
```
□ 平均句長是否合理？（目標：15-25 字/句）
  - > 40 字/句 → 建議拆分
□ 是否有過長的段落？（> 200 字建議分段）
□ 被動語態的密度？
  - > 40% 被動 → 建議增加主動語態
□ 專業術語首次使用是否有定義？
□ 縮寫首次使用是否有展開？
```

### 術語一致性
```
□ 同一概念是否使用一致的術語？
  - 不要在同一篇中交替使用 "model" 和 "system" 指同一東西
  - 不要交替 "accuracy" 和 "precision" 除非是不同指標
□ 符號是否一致？
  - 同一變數不要在不同段落用不同符號
```

### 學術寫作慣例
```
□ 避免第一人稱？（視領域慣例）
□ 避免口語表達？（"a lot of" → "numerous"）
□ 避免模糊量詞？（"some studies" → "three studies (X, Y, Z)"）
□ 避免情感語言？（"amazing results" → "notable improvement"）
```

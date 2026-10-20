# Experiment Guard: Figures & Tables Validation

## 何時載入
當研究包含圖表時。

---

## 圖表驗證檢查清單

### 引用完整性
```
□ 每個 figure/table 是否在正文中被引用？
  - "as shown in Figure X" / "Table Y reports"
  - 正文中從未提到的圖表 → 🟡
□ 引用順序是否連續？
  - Figure 1, Figure 3（跳過 2）→ 🟡
□ 正文中引用的圖表是否都存在？
  - "see Figure 5" 但只有 4 個 figure → 🔴
```

### Caption 品質
```
□ 每個 figure/table 是否有 caption？
□ Caption 是否足以獨立理解圖表？
  - 只寫 "Results" 不夠 → 需要描述性 caption
□ Caption 是否包含關鍵的軸標籤、單位、圖例說明？
□ Caption 中的數字是否與圖表中的數字一致？
```

### 圖表數據 ↔ 正文一致性
```
□ 正文描述的趨勢是否與圖表一致？
  - "Figure 2 shows a clear upward trend" → 圖表真的有上升嗎？
□ 正文引用的數值是否能在圖表中找到？
□ 表格中的數字加總是否正確？（如百分比加總）
□ 表格的 best results 標記是否正確？
  - 粗體標示最佳但不是真的最高 → 🔴
```

### 圖表品質信號
```
⚠ 圖表解析度過低（文字模糊）
⚠ 色盲不友善的配色（紅綠對比）
⚠ Y 軸不從零開始（可能誇大差異）
⚠ 3D 圖表（幾乎總是比 2D 更難讀）
⚠ 圖表太多（> 10 個可能需要精簡到 supplementary）
```

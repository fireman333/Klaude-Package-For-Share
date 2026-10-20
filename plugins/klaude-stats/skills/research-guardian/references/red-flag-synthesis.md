# Red Flag Synthesis — 紅旗摘要

## 何時載入
Aggregator 最後一步，產出紅旗摘要給使用者快速判斷。

---

## 紅旗定義
紅旗 ≠ 一般問題。紅旗是暗示研究可能有根本性問題的信號。

## 紅旗類別

### Integrity Red Flags（誠信紅旗）
```
🚩 幻覺引用（不存在的論文被引用為支持證據）
🚩 數據太完美（所有 p 值都恰好顯著、零副作用、100% 效果）
🚩 結果與方法矛盾（sensitivity 95% 但宣稱 zero false negatives）
🚩 引用已撤回的研究作為核心證據
🚩 方法不可重現（"proprietary" 且無替代驗證途徑）
```

### Methodology Red Flags（方法論紅旗）
```
🚩 從觀察性研究直接做因果推論
🚩 資料洩漏（preprocessing fit on entire dataset）
🚩 無 baseline 或只有極弱的 baseline
🚩 效果量超出文獻常模 3 倍以上且無解釋
🚩 多重比較未校正且選擇性報告
```

### Reporting Red Flags（報告紅旗）
```
🚩 完全沒有 Limitations
🚩 結論的範圍遠超研究的範圍（N=100 → "global implications"）
🚩 標題含 "Revolutionary" / "Breakthrough" / "Miraculous"
🚩 討論中完全沒有替代解釋
🚩 所有先前工作都被描述為劣於本研究
```

## 紅旗摘要格式
```
═══ RED FLAG SUMMARY ═══
Total red flags: [N]
Integrity:    [N] 🚩
Methodology:  [N] 🚩
Reporting:    [N] 🚩

[If any integrity red flags → "⚠ THIS PAPER REQUIRES MANUAL REVIEW"]
[If only methodology/reporting → list with suggested fixes]
```

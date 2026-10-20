# Audit Mode — 嚴格造假偵測

## 何時載入
當使用者懷疑論文可能有造假、操縱或嚴重誠信問題時。

---

## 與 FULL Mode 的差異
```
FULL Mode: 找出所有品質問題 → 建設性回饋
Audit Mode: 專門偵測可能的造假信號 → 鑑識分析

Audit Mode 額外啟動：
  □ 所有引用的完整三重驗證（不只抽樣）
  □ 數值模式分析（Benford's Law、p-value distribution）
  □ 圖表操縱偵測（重複使用、不合理的完美趨勢）
  □ 文字重複偵測（是否有大段落與其他論文重疊）
  □ 作者歷史檢查（是否有撤回紀錄）
```

## Audit Checklist
```
□ 數據造假信號
  - 數字分佈是否符合 Benford's Law？（第一位數字分佈）
  - 標準差是否太一致？（所有實驗的 SD 幾乎相同 → 可疑）
  - 結果是否太完美？（效果量、p 值、accuracy 的分佈）
  
□ 圖表造假信號
  - 不同 figure 中是否有重複的圖像區塊？
  - 圖表中的數據點是否與表格完全一致？
  - 圖表的解析度是否異常？（過低可能隱藏細節）

□ 文字造假信號
  - 是否有與已發表論文的大段落重疊？
  - 方法描述是否從其他論文複製但改了數字？
  - 是否有 AI 生成的典型文字模式？

□ 引用造假信號
  - 是否引用了不存在的論文？
  - 是否引用了自己未發表的論文作為支持證據？
  - 引用內容是否與原文方向相反？
```

## Audit 報告格式
```
═══ INTEGRITY AUDIT REPORT ═══
Mode: FORENSIC AUDIT
Confidence: [0-1]

FRAUD RISK ASSESSMENT: [LOW / MEDIUM / HIGH / CRITICAL]

Evidence inventory:
  [每個信號的詳細證據和原文位置]
  
Conclusion:
  [基於證據的客觀判定，不猜測動機]
  
⚠ 注意：本報告是 AI 生成的初步篩查，
  不構成正式的學術不端指控。
  嚴重問題應由機構倫理委員會正式調查。
```

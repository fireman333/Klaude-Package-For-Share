# Compare Papers Mode — 多論文比較排名

## 何時載入
當使用者需要比較多篇論文的品質或選擇最佳的時。

---

## 比較流程
```
1. 所有論文獨立跑 Guardian pipeline（平行）
2. 對每篇論文產出標準化的 scorecard
3. 多維度比較
4. 產出排名和比較報告
```

## 比較維度（Scorecard）
```
每個維度 1-5 分：

Originality:       假設的新穎度和貢獻的獨特性
Soundness:         方法論的嚴謹度和邏輯的正確性
Rigor:             實驗設計的完整度和統計分析的適當性
Clarity:           寫作清晰度和結構組織
Reproducibility:   可重現性（資料、代碼、方法描述）
Significance:      結果的重要性和潛在影響力
Integrity:         誠信度（引用正確性、數據一致性、利益衝突透明度）

Overall Score = weighted average（權重可由使用者自訂）
```

## 比較報告格式
```
═══ PAPER COMPARISON ═══

             Paper A    Paper B    Paper C
Originality    4          3          5
Soundness      4          5          3
Rigor          3          4          4
Clarity        5          3          4
Reproducib.    3          5          2
Significance   4          4          5
Integrity      5          5          4
─────────────────────────────────────────
Overall        4.0        4.1        3.9

Ranking: 1. Paper B  2. Paper A  3. Paper C

Key differentiators:
  - Paper A excels in clarity but lacks rigor
  - Paper B is most methodologically sound
  - Paper C has highest originality but reproducibility concerns
```

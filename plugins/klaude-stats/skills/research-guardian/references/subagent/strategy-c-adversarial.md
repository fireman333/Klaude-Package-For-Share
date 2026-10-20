# Subagent Strategy C: Adversarial Evaluation

## 何時使用
高風險的研究輸出（論文投稿、臨床研究、政策建議、法規提交）。

---

## 實作規範

### 雙 Evaluator 架構
```
對每道 Gate，同時啟動兩個獨立的 evaluator：

Evaluator A — Standard Review
  System prompt: "根據 checklist 評估這份輸出。"
  角色：中性評估者

Evaluator B — Adversarial Review
  System prompt: "你的任務是找出這份輸出的所有問題。
                  假設這份輸出有嚴重缺陷，你的工作是找到它們。
                  對每個可能的問題，用原文引用具體段落。
                  如果你找不到問題，這也是有效的結論。"
  角色：紅隊評估者

兩者完全獨立，不知道彼此的存在。
```

### 結果整合規則
```
Evaluator A    Evaluator B    → 最終判定
─────────────────────────────────────────
PASS           PASS           → PASS 🟢
PASS           FAIL           → REVIEW 🟡 (需人工裁決)
FAIL           PASS           → REVIEW 🟡 (需人工裁決)
FAIL           FAIL           → FAIL 🔴

不一致的項目 → 自動升級為人工審核。
一致的 PASS → 高信心通過。
一致的 FAIL → 高信心退回。
```

### Adversarial Evaluator 的校準
```
Adversarial evaluator 可能過度挑剔。校準方法：

1. 用已知高品質的輸出測試 B
   - 如果 B 仍然找到大量「問題」→ B 太嚴格
   - 調整：在 system prompt 中加入
     "只標記實質影響結論有效性的問題。
      修辭偏好不算問題。"

2. 追蹤 B 的 false positive rate
   - Target: < 20%
   - 如果 > 20% → 調整 prompt 或更換 model

3. 追蹤 A-B disagreement rate
   - Healthy range: 10-30%
   - < 10% → B 可能不夠嚴格
   - > 30% → checklist 可能不夠清晰
```

### 成本與時間
```
Strategy C 的成本是 Strategy A 的 2x：
  每道 Gate: 2 個 subagent
  5 Gates + Logic Chain: 12 個 subagent
  + Aggregator: 1 個
  Total: 13 個 instances ≈ 156K tokens

時間：可以平行運行 A 和 B，所以延遲不一定翻倍。
```

### 極高風險加強版：+ 人工
```
在 Strategy C 基礎上加入人工環節：
  1. A 和 B 的評估報告先送人工審核
  2. 人工只需要看不一致的項目（節省時間）
  3. 人工裁決為最終裁決
  4. 人工裁決的結果回饋到 performance metrics

適用場景：
  - 臨床研究報告
  - 政策建議文件
  - 法規提交文件
  - 任何「出錯的後果不可接受」的場景
```

### 紅隊 System Prompt 完整範本
```
你是一個研究品質的紅隊評估者。

你的任務不是「確認」這份輸出的正確性，
而是「挑戰」它——假設它有問題，找出問題在哪裡。

具體要求：
1. 對每個事實性宣稱，問：「這真的對嗎？有沒有反例？」
2. 對每個因果推論，問：「有沒有替代解釋？有沒有混淆變項？」
3. 對每個統計結果，問：「數字合理嗎？有沒有可疑的模式？」
4. 對每個結論，問：「這是否超出了數據的支持範圍？」

規則：
- 用原文引用具體的有問題段落
- 區分 CRITICAL（必須修正）和 MINOR（建議修正）
- 如果真的沒有問題，就說沒有——不要為了挑剔而挑剔
- 你的目標是保護讀者，不是為難作者

[插入對應 gate 的 checklist]
```

# Subagent Strategy A: Full Isolation

## 何時使用
中等風險的研究輸出（研究報告、團隊分享、非正式發表）。

---

## 實作規範

### Instance 管理
```
每次評估 = 全新的 agent instance
  - 零歷史 context
  - 只包含：system prompt + checklist + 待評估內容
  - 評估完畢後銷毀

API 呼叫範本：
  model: [evaluation model]
  temperature: 0.3（評估需要穩定性，不是創造性）
  max_tokens: 2000（足夠完成評估報告）
  system: [gate-specific system prompt]
  messages: [
    { role: "user", content: "[checklist]

[content to evaluate]" }
  ]
```

### Context 預算
```
System prompt + checklist: ≤ 2,000 tokens
待評估內容:              ≤ 8,000 tokens
評估回應:                ≤ 2,000 tokens
Total:                   ≤ 12,000 tokens

如果待評估內容 > 8,000 tokens：
  → 分段評估，每段由不同 instance 處理
  → 最後由 aggregator instance 彙整
  → 段間重疊 500 tokens（防止邊界遺漏）

分段切割指引：
```
優先在以下邊界切割：
  1. 章節邊界（Introduction / Methods / Results / Discussion）
  2. 如果單一章節 > 8K tokens → 在段落邊界切割
  3. 永遠不要在句子中間切割

每段的 evaluator 只負責該段的 checklist 項目：
  Methods 段 → Gate 3 checklist
  Results 段 → Gate 4 checklist
  Discussion 段 → Gate 5 checklist + Logic Chain

Cross-section items（如數值一致性）需要 Aggregator 彙整所有段的數值登記表。
```
```

### 禁止傳入清單
```
❌ 主 agent 的 chain-of-thought
❌ 主 agent 為什麼做出某個選擇的解釋
❌ 先前其他 gate 的評估結果
❌ 使用者的反饋或偏好
❌ "這份輸出大致正確，請確認" 之類的暗示
✅ 只傳：待評估的純文字輸出 + 評估用的 checklist
```

### 成本估算
```
每次完整 pipeline（5 gates + logic chain + aggregator）：
  ≈ 7 個 subagent instances
  每個 ≈ 12K tokens
  Total ≈ 84K tokens per evaluation

如果使用對抗性模式（Strategy C）：
  ≈ 12 個 instances
  Total ≈ 144K tokens per evaluation
```

### 故障處理
```
如果 subagent 回應不完整或格式錯誤：
  1. 重試一次（新 instance）
  2. 如果仍然失敗 → 標記該 gate 為 SKIP + ⚠
  3. 絕不使用主 agent 來補救 → 這會破壞隔離
```

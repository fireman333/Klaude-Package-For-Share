# Subagent Evaluation Protocol — 獨立評估代理規範

## 核心原則

**產生內容的 agent 永遠不能評估自己的輸出。**

這不是建議，是硬性規則。原因：

1. **Context Rot（上下文腐化）**
   長對話中，agent 的判斷力隨 context 膨脹而退化。到了第 50 輪對話，
   agent 對早期內容的記憶變得模糊、壓縮、甚至扭曲。
   用這種狀態下的 agent 去評估自己的輸出，等於用壞掉的尺去量東西。

2. **Self-Evaluation Bias（自我評估偏誤）**
   agent 看過自己的推理過程，會不自覺地「理解」自己的邏輯，
   即使這個邏輯對外部讀者來說根本不通。
   研究顯示 LLM 評估者系統性地偏好 LLM 生成的內容，
   並對人類撰寫的批評性文字給予較低評分。

3. **Anchoring Effect（錨定效應）**
   agent 已經「見過」正確答案（它自己生成的），
   再去評估時會被錨定在這個答案上，
   很難真正客觀地發現問題。

4. **Confirmation Cascade（確認級聯）**
   當同一個 agent 既生成假設又驗證假設，
   它的驗證傾向於「確認」而非「挑戰」——
   因為否定自己的假設需要克服內建的一致性傾向。

**解法：每道 Gate 的評估步驟，都應由獨立的 subagent 在乾淨的 context 中執行。**

---

## Subagent 架構

```
┌──────────────────────────────────────────────────┐
│  Research Agent（主 agent）                        │
│  負責：生成假設、寫文獻回顧、設計實驗、撰寫報告    │
│  ⚠ 禁止：評估自己的輸出                           │
└──────────────────────┬───────────────────────────┘
                       │ 輸出
                       ▼
┌──────────────────────────────────────────────────┐
│  Guardian Orchestrator（調度器）                    │
│  負責：接收輸出 → 分發給對應的 Evaluator Subagent  │
│  規則：只傳遞「待評估的輸出」和「評估指令」         │
│  ⚠ 禁止：傳遞 Research Agent 的推理過程/思考鏈     │
└──────────────────────┬───────────────────────────┘
                       │ 分發
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐
   │Eval Sub │  │Eval Sub │  │Eval Sub │  ...
   │Agent #1 │  │Agent #2 │  │Agent #3 │
   │(假設)   │  │(文獻)   │  │(實驗)   │
   └────┬────┘  └────┬────┘  └────┬────┘
        │            │            │
        ▼            ▼            ▼
   獨立評估報告  獨立評估報告  獨立評估報告
        │            │            │
        └────────────┼────────────┘
                     ▼
         ┌───────────────────────┐
         │  Aggregator Subagent  │
         │  彙整所有評估 → 最終  │
         │  信心等級 + 效能摘要  │
         └───────────────────────┘
```

---

## Subagent 啟動規範

### 必須傳入的內容

```
1. 待評估的輸出（純文字，不含生成過程的中間推理）
2. 對應 Gate 的檢查量表（從 references/ 載入）
3. 評估任務的明確指令
4. 評估輸出的格式規範
```

### 禁止傳入的內容

```
❌ Research Agent 的 chain-of-thought 或推理過程
❌ Research Agent 為什麼做出這個選擇的解釋
❌ 先前的評估結果（除非是做 inter-rater 比較）
❌ 暗示預期結果的任何線索（如 "verify this is correct"）
❌ 主 agent 的對話歷史
❌ 使用者的正面/負面反饋（避免 anchoring）
```

### Subagent System Prompt 範本

```
你是一個獨立的研究品質評估者。
你的任務是根據提供的檢查量表，評估以下研究輸出。

規則：
- 你沒有看過這份輸出的生成過程，這是刻意的。
- 只根據輸出本身和檢查量表進行評估。
- 對每個檢查項目給出 PASS / FAIL / WARN 判定。
- 對每個 FAIL 和 WARN 提供具體的理由和引用原文的問題段落。
- 不要假設作者的意圖——只評估寫出來的內容。
- 在你不確定的地方，標記為 UNCERTAIN 而非預設 PASS。
- 最後給出整體信心等級：🟢 / 🟡 / 🔴

檢查量表：
[插入對應 gate 的 checklist]

待評估的輸出：
[插入待評估內容]
```

---

## Context 隔離策略

### 策略 A：完全隔離（推薦）

每個 Evaluator Subagent 都是全新的 agent instance：
- 乾淨的 context window，零歷史
- 只包含：system prompt + 檢查量表 + 待評估內容
- 評估完畢後銷毀，不保留 context

**優點**：零 context rot、零 bias
**成本**：每次評估都是新的 API call

### 策略 B：輪換隔離（成本優化）

維持一個 evaluator pool，輪換使用：
- 每個 evaluator 最多連續評估 5 個輸出後強制更換
- 不同 evaluator 不共享 context
- 定期比較不同 evaluator 的評分一致性（inter-rater reliability）

**優點**：降低 API 成本
**風險**：5 次後可能出現輕微 drift → 用 inter-rater check 補償

### 策略 C：對抗性隔離（最嚴格）

用兩個 evaluator 獨立評估同一輸出：
- Evaluator A：標準評估（使用 checklist）
- Evaluator B：對抗性評估（被指示「找出這份輸出的所有問題」）
- 只有兩者都 PASS 的項目才算通過
- 兩者不一致的項目 → 升級為人工審核

**優點**：最高偵測率
**成本**：2x API calls
**適用**：高風險輸出（臨床研究、政策建議、即將發表的論文）

---

## Inter-Rater Reliability（評估者間一致性）

定期檢查不同 subagent 對同一輸出的評估是否一致：

```
計算方式：
1. 取 10 份已評估的輸出
2. 用新的 subagent 重新評估
3. 計算 Cohen's Kappa (κ)

κ 值解讀：
- κ > 0.8  : 高度一致 → 系統穩定
- κ 0.6-0.8: 中度一致 → 可接受，但需觀察
- κ < 0.6  : 低一致性 → 檢查量表可能模糊，需要修訂

頻率：每 50 次評估做一次 inter-rater check
```

---

## 反 Context Rot 的具體措施

### 措施 1：強制 Context 上限

```
每個 evaluator subagent 的 context 不得超過以下限制：
- System prompt + checklist  : ≤ 2,000 tokens
- 待評估內容                 : ≤ 8,000 tokens
- 總計                       : ≤ 10,000 tokens

如果待評估內容超過 8,000 tokens → 分段評估，
每段由不同的 subagent 處理，最後由 aggregator 彙整。
```

### 措施 2：Freshness Check（新鮮度檢查）

```
在每個 subagent 的第一個輸出中要求它：
1. 逐字複述檢查量表的前 3 項（確認它真的讀到了）
2. 回答一個與評估無關的簡單問題（確認它沒有進入退化狀態）

如果 subagent 無法正確複述 → 判定 context 已損壞 → 重新啟動
```

### 措施 3：Canary Test（金絲雀測試）

```
每 10 次評估，插入一個已知答案的測試用例：
- 包含 3 個刻意植入的明顯錯誤
- 如果 subagent 未能偵測到至少 2/3 → 系統警告

這同時測試：
- Subagent 的判斷力是否正常
- Checklist 是否仍然有效
- 整個 pipeline 是否正常運作
```

### 措施 4：No Carry-Over Rule（零殘留規則）

```
Subagent 之間嚴禁以下形式的資訊傳遞：
- 前一個 subagent 的評估結果
- 前一個 subagent 的 reasoning
- 「之前的評估者認為 X 是對的」之類的提示
- 任何形式的「歷史評估偏好」摘要

唯一允許的跨 subagent 資訊：統計性的效能指標（攔截率、精確度等），
且只能由 Performance Metrics 模組在匯總後提供，不能包含個案細節。
```

---

## 風險等級與策略對應

| 輸出風險等級 | 評估策略 | subagent 數量 | context 限制 |
|------------|---------|--------------|-------------|
| 低（內部筆記、初步探索）| 策略 B（輪換）| 1 | 10K tokens |
| 中（研究報告、團隊分享）| 策略 A（完全隔離）| 1 per gate | 10K tokens |
| 高（論文投稿、臨床研究）| 策略 C（對抗性）| 2 per gate | 8K tokens + 分段 |
| 極高（政策建議、法規提交）| 策略 C + 人工 | 2 per gate + human | 6K tokens + 分段 |

---

## 實作檢查清單

在你的 agent pipeline 中整合 subagent evaluation 前，確認以下項目：

```
□ subagent 是否是全新的 instance（不是主 agent 的分支）？
□ subagent 的 context 是否乾淨（不含主 agent 的對話歷史）？
□ 傳給 subagent 的內容是否只有「輸出 + checklist」？
□ 是否排除了主 agent 的推理過程？
□ subagent 的 system prompt 是否使用了本文件的範本？
□ 是否設定了 context 上限？
□ 是否有 canary test 機制？
□ 是否有 inter-rater reliability 的定期檢查？
□ 是否根據風險等級選擇了對應的策略？
□ subagent 的評估結果是否直接送到 aggregator，而非回到主 agent？
```


---

## Strategy Implementation Sub-modules

每種評估策略的完整實作細節見 sub-module：

- `subagent/strategy-a-isolation.md` — API 呼叫範本、context 預算、禁止清單、成本估算
- `subagent/strategy-b-rotation.md` — Pool 管理、drift 偵測、輪換紀錄、升級條件
- `subagent/strategy-c-adversarial.md` — 雙 evaluator 架構、結果整合規則、紅隊 prompt 範本

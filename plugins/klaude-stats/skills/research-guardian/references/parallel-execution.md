# Parallel Execution Architecture
# Inspired by OpenReviewer's Stage 2 parallel dispatch

## 核心改變

舊架構（序列）：
```
Gate 1 → Gate 2 → Gate 3 → Gate 4 → Gate 5 → Logic → Aggregator
Total time: sum of all gates (~15-20 min in FULL mode)
```

新架構（平行 + 依賴感知）：
```
                    ┌→ Gate 1 (Hypothesis) ─────┐
                    ├→ Gate 2 (Literature) ─────┤
Input → Pre-scan →  ├→ Gate 3 (Experiment) ─────┼→ Aggregator → Output
                    ├→ Gate 4 (Result) ─────────┤
                    ├→ Gate 5 (Writing) ─────────┤
                    └→ Logic Chain (all layers) ─┘

Total time: max of all gates (~5-7 min — 3x speedup)
```

---

## 依賴分析：哪些可以平行？

### 完全獨立（可平行）
```
Gate 1 (Hypothesis)  ↔ Gate 2 (Literature)    → 獨立 ✅
Gate 1 (Hypothesis)  ↔ Gate 3 (Experiment)    → 獨立 ✅
Gate 2 (Literature)  ↔ Gate 3 (Experiment)    → 獨立 ✅
Gate 2 (Literature)  ↔ Gate 4 (Result)        → 獨立* ✅
Gate 3 (Experiment)  ↔ Gate 5 (Writing)       → 獨立 ✅
Gate 4 (Result)      ↔ Gate 5 (Writing)       → 獨立* ✅
Logic Layer 1-5      ↔ Gate 1-5               → 獨立 ✅

*注：雖然 cross-gate 矛盾偵測需要彼此的結果，
但那是 Aggregator 的工作，不需要在 gate 層面序列化。
```

### 有依賴（需要序列的部分）
```
Pre-scan → 所有 Gates（Pre-scan 決定要跑哪些 gate）
所有 Gates → Aggregator（Aggregator 需要所有 gate 的結果）
Aggregator → Cross-gate 矛盾偵測（需要完整結果才能比對）
```

### 結論：Pre-scan 之後，所有 gate + logic chain 可以完全平行。

---

## 平行派發規範

### Orchestrator 的派發邏輯
```
1. Pre-scan（序列，~30 秒）
   → 決定模式（QUICK/STANDARD/FULL）
   → 決定 Preset（ML/Bio/SocSci/SR/Proposal）
   → 產生 gate list

2. 平行派發（同時啟動所有需要的 gate）
   → 每個 gate 由獨立 subagent 執行
   → Logic chain 的對應 layers 也同時啟動
   → 所有 subagent 接收相同的「待評估輸出」
   → 彼此不知道對方的存在（隔離原則不變）

3. 收集結果（等待所有 subagent 完成）
   → 設定 timeout：每個 subagent 最多 3 分鐘
   → 如果超時 → 標記該 gate 為 TIMEOUT + SKIP

4. Aggregator（序列，~1 分鐘）
   → 彙整所有結果
   → 跑 cross-gate 矛盾偵測
   → 跑 issue 正規化（去重、統一嚴重度）
   → 產生最終報告
```

### 實作方式

#### 在 Claude Code / Cowork 中（有 subagent）
```
所有 gate subagent 在同一個 assistant message 中用多個 task tool calls 派發。
關鍵：把所有 task calls 放在同一個 message → 平行執行。
分開的 messages → 序列執行。

範例 pseudocode：
  results = await Promise.all([
    spawnSubagent("gate1", input, checklist_1),
    spawnSubagent("gate2", input, checklist_2),
    spawnSubagent("gate3", input, checklist_3),
    spawnSubagent("gate4", input, checklist_4),
    spawnSubagent("gate5", input, checklist_5),
    spawnSubagent("logic", input, logic_checklist),
  ]);
  final = await spawnSubagent("aggregator", results);
```

#### 在 API pipeline 中
```
使用 Promise.all 或 asyncio.gather 同時發出多個 API calls。
每個 call 是一個獨立的 conversation（乾淨 context）。

Python 範例：
  import asyncio
  
  async def run_gate(gate_name, input_text, checklist):
      response = await client.messages.create(
          model="claude-sonnet-5-5",
          system=checklist,
          messages=[{"role": "user", "content": input_text}]
      )
      return {"gate": gate_name, "result": response}
  
  gates = [
      run_gate("hypothesis", paper, hypothesis_checklist),
      run_gate("literature", paper, literature_checklist),
      run_gate("experiment", paper, experiment_checklist),
      run_gate("result", paper, result_checklist),
      run_gate("writing", paper, writing_checklist),
      run_gate("logic", paper, logic_checklist),
  ]
  results = await asyncio.gather(*gates)
```

---

## 效能提升估算

### FULL Mode
```
序列（舊）：Gate1(2m) + Gate2(5m) + Gate3(4m) + Gate4(4m) + Gate5(3m) + Logic(3m) + Agg(1m)
= 22 分鐘

平行（新）：Pre-scan(0.5m) + max(Gate1..Logic)(5m) + Agg(1m)
= 6.5 分鐘

加速比：22 / 6.5 ≈ 3.4x
```

### STANDARD Mode
```
序列：Gate4(4m) + Gate5(3m) + Logic(3m) + Lit-partial(2m) + Agg(1m)
= 13 分鐘

平行：Pre-scan(0.5m) + max(4m) + Agg(1m)
= 5.5 分鐘

加速比：13 / 5.5 ≈ 2.4x
```

### Token 成本不變（平行不增加 token，只減少延遲）

---

## 與 Subagent 隔離的相容性

平行執行完全相容 subagent 隔離原則：
```
✅ 每個 gate 仍然是獨立的 subagent instance
✅ 每個 subagent 仍然只接收「輸出 + checklist」
✅ subagent 之間仍然不共享 context
✅ 主 agent 的推理過程仍然不傳入

唯一的改變：從「一個接一個啟動」變成「同時啟動」。
隔離性不受影響，因為隔離是由 context 決定的，不是由時序決定的。
```

---

## Quick Mode 的平行化

```
🟢 QUICK: 不需要平行（只有 1 個 subagent call）
🟡 STANDARD: 3-4 個 subagent → 平行化後從 ~13min → ~5.5min
🔴 FULL: 7 個 subagent → 平行化後從 ~22min → ~6.5min ← 最大收益
```

---

## 動態路由（三道防線）

平行架構的預設模式是全平行（所有 gate 同時跑）。
動態路由是三層可選的智慧調整機制，每一層是前一層的 fallback。
預設全部啟用，但即使全部關閉，系統仍然正常運作（退化為靜態路由）。

### 防線 1：Content-Aware Pre-scan（開始前）

Pre-scan 在派發 gate 之前，分析輸入內容自動辨識領域、研究設計、統計方法，
據此決定每個 gate 應載入哪些 sub-modules。

```
詳見 quick-modes.md 的「Preset 自動辨識」段落。

效果：消除使用者手動選 preset 的需求。
成本：Pre-scan 本身 < 30 秒，不影響後續平行執行。
觸發率預估：~80% 的案例能正確辨識（基於術語和引用來源的明確性）。
```

### 防線 2：Routing Signals（執行中，gate 間）

Gate 在執行過程中可產生 routing signals，通知其他 gate 或 aggregator
調整行為。這**不打破平行架構**——signals 由 aggregator 事後處理。

```
Routing Signal 格式：
{
  "source_gate": "literature_guard",
  "signal_type": "domain_detected",
  "payload": {"domain": "biomedical", "confidence": 0.9},
  "timestamp": "..."
}

預定義 Signal 類型：

domain_detected — Gate 從內容中辨識到特定領域
  來源：Gate 2（從引用來源辨識）或 Gate 3（從方法描述辨識）
  消費者：Aggregator（決定是否補跑缺失的 domain sub-module）

severity_escalation — 某 Gate 發現 CRITICAL issue
  來源：任何 Gate
  消費者：Aggregator（觸發自動升級到 FULL mode）

data_integrity_alert — 發現可能的數據造假信號
  來源：Gate 4（數值異常）或 Gate 2（幻覺引用）
  消費者：Aggregator（觸發 Audit Mode 的部分 checklist）

cross_reference — 某 Gate 發現的資訊可以幫助另一個 Gate
  來源：Gate 2（引用驗證結果）
  消費者：Aggregator（用於 cross-section consistency 的深度檢查）
```

#### 兩種處理模式

```
模式 A：事後處理（預設）
  所有 gate 全平行跑完 → Aggregator 收集所有 routing signals
  → 如果有 domain_detected 但對應 sub-module 沒跑 → Aggregator 補跑
  → 延遲：0（不影響平行執行）+ 補跑的時間

模式 B：兩階段平行（可選，高風險場景）
  第一階段：Gate 1 + Gate 2 平行（~3min）
  → 收集 routing signals
  → 根據 signals 調整 Gate 3-5 的 sub-module 配置
  第二階段：Gate 3 + Gate 4 + Gate 5 + Logic Chain 平行（~5min）
  → 延遲：~8min（vs. 全平行的 ~6.5min，多 ~1.5min）
  → 適用：跨領域研究、pre-scan 辨識 confidence = low 的案例

選擇規則：
  Pre-scan confidence ≥ high → 模式 A（全平行）
  Pre-scan confidence = medium → 模式 A（全平行）
  Pre-scan confidence = low → 模式 B（兩階段）
  使用者指定 --adaptive → 模式 B
```

### 防線 3：Intra-Gate Dynamic Loading（Gate 內）

單一 Gate 在執行 checklist 時，可能發現需要一個未被 pre-scan 選中的
sub-module。Gate 可以在自己的執行過程中動態載入。

```
觸發條件：
  Gate 3 正在用通用 checklist 檢查 Methods →
  發現描述了 "Bayesian hierarchical model" →
  通用 checklist 沒有 ROPE/MCMC 的檢查項 →
  動態載入 result/bayesian.md

規則：
  1. Gate 只能載入自己 gate 對應的 sub-modules
     Gate 3 (Experiment) 可以載入 experiment/*.md
     Gate 3 不能載入 result/*.md（那是 Gate 4 的事）
  2. 動態載入的 sub-module 執行結果標記為 "dynamically loaded"
     → Aggregator 可以看到哪些是靜態路由、哪些是動態路由
  3. 動態載入不延長超時（仍然在 gate 的 3 分鐘限制內）
     如果 sub-module 太大無法在時限內跑完 → 標記 SKIP + routing signal
     → Aggregator 決定是否補跑

何時不觸發：
  - Pre-scan 已正確選擇了 sub-module → 不需要動態載入
  - Gate 的 checklist 覆蓋了需要的檢查 → 不需要
  - 動態載入只在 gate 的 evaluator subagent 判斷「通用 checklist
    無法充分評估這段內容」時才觸發
```

### 三道防線的協同

```
Pre-scan 辨識到 biomedical + ml-experiment
  → Gate 3 載入 ml-experiment.md（靜態路由）✅
  → Gate 3 跑到一半發現有 qualitative 的 member checking
  → Gate 3 動態載入 qualitative.md（防線 3）✅
  → Gate 2 發現引用包含 Cochrane Reviews
  → Gate 2 發出 routing signal: domain_detected = biomedical（防線 2）
  → Aggregator 發現 biomedical sub-module 沒被 Gate 1 使用
  → Aggregator 補跑 Gate 1 + hypothesis/biomedical.md ✅

三道防線各自獨立，任何一道足以捕獲 pre-scan 的盲區。
全部關閉 = 退化為靜態路由（仍然有效，只是少了自適應能力）。
```

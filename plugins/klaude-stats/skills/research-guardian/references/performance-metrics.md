# Performance Metrics — 防護系統效能量測模組

## 目的

Research Guardian 本身也是一個系統，需要被驗證。
本模組定義如何量測每道 gate 的效能，追蹤系統整體表現，
以及判斷防護系統是「真的有用」還是「只是增加延遲」。

核心問題：**你的防護系統擋下了多少真正的錯誤？放過了多少？誤殺了多少正確的輸出？**

---

## 指標體系

### Level 1: Gate 層級指標（每道 Gate 各自追蹤）

| 指標 | 定義 | 計算方式 | 健康範圍 |
|------|------|---------|---------|
| **攔截率** (Catch Rate) | 該 gate 標記問題的比例 | 標記數 / 總檢查數 | 10%-40%* |
| **精確度** (Precision) | 標記的問題中，真正是問題的比例 | TP / (TP + FP) | > 80% |
| **召回率** (Recall) | 實際問題中，被成功標記的比例 | TP / (TP + FN) | > 70% |
| **誤殺率** (False Positive Rate) | 正確輸出被錯誤標記的比例 | FP / (FP + TN) | < 15% |
| **漏放率** (Miss Rate) | 真正的錯誤未被攔截的比例 | FN / (FN + TP) | < 30% |
| **處理時間** (Latency) | 該 gate 的平均執行時間 | 平均秒數 | 視 gate 而定 |

*攔截率健康範圍說明：
- 太低 (< 5%) → gate 可能形同虛設，檢查不夠嚴格
- 太高 (> 50%) → gate 可能過度敏感，或上游輸入品質太差
- 持續 0% → gate 可能有 bug，完全沒在運作

### Level 2: Pipeline 層級指標（整體系統）

| 指標 | 定義 | 計算方式 | 健康範圍 |
|------|------|---------|---------|
| **端到端通過率** | 一次通過所有 gate 的比例 | 首次全通過 / 總次數 | 30%-70% |
| **平均修正輪次** | 從首次提交到全部通過的平均迭代次數 | 總修正次數 / 總任務數 | 1-3 輪 |
| **總延遲** | 完整防護流程的端到端耗時 | 所有 gate 時間總和 | < 研究任務本身的 20% |
| **品質提升量** (Quality Delta) | 經過防護 vs. 未經防護的品質差異 | 見下方計算方式 | 正值且顯著 |
| **信心校準度** | 信心等級與實際正確率的吻合度 | 見下方計算方式 | 校準誤差 < 10% |

### Level 3: 長期趨勢指標

| 指標 | 定義 | 追蹤週期 | 期望趨勢 |
|------|------|---------|---------|
| **上游品質趨勢** | AI agent 原始輸出的品質是否隨時間提升 | 週/月 | 上升 |
| **Gate 攔截率趨勢** | 各 gate 攔截率是否隨時間下降 | 週/月 | 緩慢下降（代表上游改善）|
| **新錯誤類型出現率** | 未被現有 gate 覆蓋的新錯誤類型頻率 | 月 | 低且穩定 |
| **人工介入率** | 需要人類最終裁決的比例 | 週 | 緩慢下降 |

---

## 各 Gate 的專屬效能指標

### Hypothesis Guard

```
METRICS:
- novelty_false_positive   : 被標記為「不新穎」但實際是新穎的假設數
- novelty_false_negative   : 被放行但後來發現已有人做過的假設數
- avg_search_queries       : 平均每次驗證使用的搜索次數
- literature_coverage_score: 搜索結果覆蓋相關文獻的比例 (0-1)
```

**基準測試方法：**
取 10 個已知 novel 的假設 + 10 個已知不 novel 的假設（從已發表論文中提取），
跑 Hypothesis Guard，計算分類準確率。目標：> 75%。

### Literature Guard

```
METRICS:
- hallucination_catch_rate : 幻覺引用被成功攔截的比例
- valid_rejection_rate     : 真實引用被錯誤標記為幻覺的比例
- verification_completeness: 引用中被實際驗證的比例 (target: 100%)
- avg_verification_time    : 平均每篇引用的驗證耗時
- citation_freshness_score : 引用新近性得分 (基於中位年份)
```

**基準測試方法：**
在一段文獻回顧中故意混入 5 篇幻覺引用和 15 篇真實引用，
跑 Literature Guard，計算偵測率。目標：幻覺偵測 > 90%，真實引用誤判 < 10%。

### Experiment Guard

```
METRICS:
- design_flaw_detection    : 設計缺陷被識別的比例
- code_error_prevention    : 程式碼問題在執行前被攔截的比例
- antipattern_detection    : 反模式被正確標記的數量
- false_alarm_rate         : 合理設計被錯誤質疑的比例
```

**基準測試方法：**
取 5 個有已知設計缺陷的實驗方案 + 5 個合理的方案，
跑 Experiment Guard，計算辨識準確率。目標：> 70%。

### Result Guard

```
METRICS:
- inconsistency_detection  : 數值不一致被發現的比例
- overclaim_detection      : 過度推論被標記的比例
- hallucinated_result_catch: 幻覺數值被偵測的比例
- false_flag_rate          : 正確結果被錯誤質疑的比例
```

**基準測試方法：**
在一份結果報告中植入 5 處數值不一致和 3 處 overclaim，
跑 Result Guard，計算偵測率。目標：不一致偵測 > 85%，overclaim 偵測 > 70%。

### Writing Guard

```
METRICS:
- unsourced_claim_detection: 懸空斷言被標記的比例
- tone_mismatch_detection  : 語氣-證據不匹配被標記的數量
- ai_artifact_detection    : AI 特徵詞被識別的數量
- structural_issue_count   : 結構性問題被發現的數量
```

---

## Quality Delta 計算方式

衡量防護系統的「真實價值」——有它 vs. 沒它，差多少？

### 方法 A：A/B 對照（推薦）

```
1. 取 N 個相同的研究任務
2. A 組：AI agent 直接輸出（不經過 Guardian）
3. B 組：AI agent 輸出經過 Guardian 完整流程
4. 請領域專家盲審兩組輸出，評分 1-10
5. Quality Delta = B 組平均分 - A 組平均分
6. 用配對 t 檢定計算顯著性

目標：Quality Delta > 1.0 且 p < 0.05
```

### 方法 B：錯誤植入測試（快速驗證用）

```
1. 取一份高品質的研究輸出
2. 故意植入 K 個已知錯誤（分布在各 gate 負責的範圍）
   - 3 篇幻覺引用
   - 2 處數值不一致
   - 2 處 overclaim
   - 1 個實驗設計反模式
   - 2 個懸空斷言
3. 跑 Guardian 完整流程
4. Error Detection Rate = 被偵測的錯誤數 / K

目標：Error Detection Rate > 75%
```

### 方法 C：歷史回測

```
1. 收集過去被 peer reviewer 指出的問題（從審稿意見中提取）
2. 在提交前的版本上跑 Guardian
3. 計算 Guardian 能事先攔截多少 reviewer 指出的問題

目標：事先攔截率 > 50%
```

---

## 信心校準度量測

檢查 🟢🟡🔴 標記是否名副其實。

```
校準度計算：
1. 收集所有被標記為 🟢 (HIGH) 的輸出，事後驗證正確率
   - 期望：> 90% 正確
2. 收集所有被標記為 🟡 (MEDIUM) 的輸出，事後驗證正確率
   - 期望：50%-90% 正確
3. 收集所有被標記為 🔴 (LOW) 的輸出，事後驗證正確率
   - 期望：< 50% 正確

校準誤差 = |實際正確率 - 期望正確率| 的平均值
目標：校準誤差 < 10%

如果 🟢 標記的輸出實際只有 60% 正確 → 系統過度樂觀，需調嚴
如果 🔴 標記的輸出實際有 80% 正確 → 系統過度保守，需調鬆
```

---

## 效能儀表板格式

每次 Guardian 運行完畢後，附加以下摘要：

```
══════════════════════════════════════════
 RESEARCH GUARDIAN — PERFORMANCE SUMMARY
══════════════════════════════════════════
 
 Pipeline Run #[N]         Date: [YYYY-MM-DD]
 Task Type: [hypothesis/literature/experiment/result/writing]
 
 GATE STATUS
 ───────────
 Hypothesis Guard  : [PASS/FAIL/SKIP]  │ Issues: [N]  │ Time: [Xs]
 Literature Guard  : [PASS/FAIL/SKIP]  │ Issues: [N]  │ Time: [Xs]
 Experiment Guard  : [PASS/FAIL/SKIP]  │ Issues: [N]  │ Time: [Xs]
 Result Guard      : [PASS/FAIL/SKIP]  │ Issues: [N]  │ Time: [Xs]
 Writing Guard     : [PASS/FAIL/SKIP]  │ Issues: [N]  │ Time: [Xs]
 
 AGGREGATE
 ─────────
 Total issues found     : [N]
 Correction rounds      : [N]
 Total pipeline time    : [Xs] ([N]% of task time)
 Final confidence level : 🟢/🟡/🔴/⚫
 
 CUMULATIVE (last 30 days)
 ─────────────────────────
 Tasks processed        : [N]
 First-pass rate        : [N]%
 Avg correction rounds  : [N]
 Hallucination catches  : [N]
 Overclaim catches      : [N]
 Human escalations      : [N]
══════════════════════════════════════════
```

---

## 退化偵測（系統自我監控）

Guardian 系統本身可能隨時間退化。以下信號代表系統需要維護：

```
⚠ 警告信號：
- 連續 20 次運行攔截率為 0%        → gate 可能失效
- 精確度降到 60% 以下              → 規則可能過時
- 處理時間增加 > 50%               → 效能問題
- 人工推翻 Guardian 判斷的比例 > 30% → 規則需要更新
- 新類型錯誤連續 3 次未被攔截       → 需要新增檢查項目

🔴 緊急信號：
- 被標記為 🟢 的輸出出現嚴重錯誤   → 立即審查信心校準
- Gate 完全無法執行（crash/timeout） → 立即修復
```


---

## Gate-Specific Benchmark Sub-modules

每道 Gate 的具體基準測試設計見 sub-module：

- `metrics/hypothesis-benchmarks.md` — 10 novel + 10 non-novel 測試集、回歸用例
- `metrics/literature-benchmarks.md` — 15 真實 + 5 幻覺引用測試集、三重驗證追蹤
- `metrics/experiment-benchmarks.md` — 5 有缺陷 + 5 合理設計測試集
- `metrics/result-benchmarks.md` — 10 種植入錯誤測試、數值登記表方法
- `metrics/writing-benchmarks.md` — 13 種植入問題測試、斷言追溯操作化

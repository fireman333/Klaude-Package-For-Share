# Subagent Strategy B: Rotation Isolation

## 何時使用
低風險的研究輸出（內部筆記、初步探索、brainstorming）。

---

## 實作規範

### Pool 管理
```
維持一個 evaluator pool：
  - Pool size: 3-5 個 evaluator slots
  - 每個 evaluator 最多連續評估 5 個輸出
  - 達到 5 次後強制更換（新 instance）
  - 不同 evaluator 不共享 context

生命週期：
  Evaluator #1: 評估 1,2,3,4,5 → 銷毀
  Evaluator #2: 評估 6,7,8,9,10 → 銷毀
  ...
```

### 與 Strategy A 的差異
```
Strategy A: 每次評估 = 新 instance（最安全，最貴）
Strategy B: 每 5 次 = 新 instance（平衡安全和成本）

成本節省：約 60-70%（減少了 instance 建立的開銷）
風險增加：第 4-5 次評估可能有輕微 context drift
```

### Drift 偵測
```
每個 evaluator 的第 1 次和第 5 次評估做對照：
  - 相同的 canary test case
  - 如果第 5 次的結果與第 1 次顯著不同 → drift 已發生
  - 此時縮短輪換週期（改為每 3 次更換）

Inter-rater check:
  - 每 20 次評估，讓兩個不同的 evaluator 評估同一輸出
  - 計算 agreement rate
  - 如果 agreement < 70% → 檢查 checklist 是否模糊
```

### 輪換紀錄
```
維持一個 rotation log：
  Evaluator ID | Created | Tasks Done | Last Canary Score | Status
  E001         | 10:00   | 3/5        | PASS              | Active
  E002         | 10:15   | 5/5        | PASS              | Retired
  E003         | 10:30   | 1/5        | PASS              | Active
```

### 何時升級到 Strategy A
```
如果以下任一條件成立 → 升級為完全隔離：
  - 研究將被正式發表
  - 涉及臨床或政策決策
  - Canary test 失敗
  - 使用者明確要求最高嚴謹度
```

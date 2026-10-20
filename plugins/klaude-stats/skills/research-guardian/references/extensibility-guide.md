# Extensibility Guide — 擴充手冊

## 何時讀取
當你需要為 Research Guardian 新增領域、gate、邏輯層、preset、persona、或任何自訂規則時。

---

## 擴充點總覽

```
可擴充的面向          目前有的                    擴充方式
─────────────────────────────────────────────────────────
Domain sub-modules    biomedical, cs-ml,          加檔案 + 註冊
                      social-science
Study type modules    rct, observational,         加檔案 + 註冊
                      ml-experiment, qualitative
Stat frameworks       frequentist, bayesian,      加檔案 + 註冊
                      ml-metrics, qualitative
Writing venues        journal, conference,        加檔案 + 註冊
                      preprint
Logic layers          5 layers (formal →          加檔案 + 註冊
                      research-specific)
Reviewer personas     5 personas                  加到 reviewer-personas.md
Presets               ml, clinical, socsci,       加到 quick-modes.md
                      sr, proposal                + runner.py PRESETS dict
Modes                 review, batch, audit,       加到 modes/ + 指令表
                      compare
Gates                 5 gates                     重量級擴充（見下方）
Signal words          EN, ZH, JA, KO, ES          加到 writing-verification.md
Scorecard dimensions  7 dimensions                加到 issue-schema.md
Red flag categories   3 categories                加到 red-flag-synthesis.md
```

---

## 1. 新增 Domain Sub-module（最常見的擴充）

當你需要支援新的研究領域（如物理學、法學、人文、工程、環境科學）。

### 步驟

```
1. 建立 3 個檔案（對應 hypothesis、literature、experiment 三道 gate）：
   references/hypothesis/{domain}.md
   references/literature/{domain}.md
   references/experiment/{domain}.md    ← 如果該領域有獨特的實驗設計

2. 每個檔案遵循既有模板結構（見下方）

3. 註冊：在對應的 Layer 1 reference 文件末尾的 sub-module 清單中加入指向
   例：hypothesis-validation.md 的「Domain-Specific Sub-modules」段落

4. （可選）在 quick-modes.md 中加入該領域的 Preset
```

### 模板：`references/hypothesis/{domain}.md`

```markdown
# Hypothesis Guard: {Domain Name}

## 何時載入
當研究假設涉及 {領域描述} 時。

---

## {Domain} 假設的特殊要求

### 1. {領域特有的假設品質標準}
（這個領域判斷假設好不好的標準是什麼？）

### 2. {領域特有的 novelty 判斷}
（這個領域怎麼判斷一個假設是不是 novel？常見的偽 novelty？）

### 3. {領域特有的陷阱}
（這個領域最常見的假設錯誤是什麼？）

### 4. {領域特有的搜索策略}
（這個領域去哪裡搜文獻？用什麼資料庫？）

---

## 輸出格式
（保持和其他 domain 一致的格式）
```

### 範例：如果要加「環境科學」

```
references/hypothesis/environmental.md   — 生態效度、尺度問題、時間跨度
references/literature/environmental.md   — 灰色文獻（政策報告）的處理、IPCC 引用規範
references/experiment/environmental.md   — 田野實驗、長期監測、衛星資料驗證
```

---

## 2. 新增 Study Type（實驗設計類型）

當你需要支援新的研究設計（如 N-of-1 trial、Delphi method、action research）。

### 步驟

```
1. 建立：references/experiment/{study-type}.md
2. 遵循模板（見 rct.md 或 qualitative.md 的結構）
3. 註冊：在 experiment-checklist.md 的 sub-module 清單中加入
```

### 關鍵：每個 study type 必須回答

```
□ 這種設計的有效性標準是什麼？（不要套用 RCT 的標準）
□ 這種設計允許什麼程度的因果推論？
□ 這種設計的常見偏誤有哪些？
□ 這種設計對應的報告標準是什麼？（CONSORT? STROBE? 其他?）
```

---

## 3. 新增 Statistical Framework

當你需要支援新的統計方法（如 structural equation modeling、survival analysis、network meta-analysis）。

### 步驟

```
1. 建立：references/result/{framework}.md
2. 必須包含：
   - 報告規範（該方法必須報告什麼？）
   - 常見錯誤（該方法最容易犯什麼錯？）
   - 可疑信號（什麼數值模式暗示有問題？）
3. 註冊：在 result-integrity.md 的 sub-module 清單中加入
```

---

## 4. 新增 Logic Layer

當你發現一類新的推理謬誤未被現有 5 層覆蓋。

### 步驟

```
1. 建立：references/logic/layer{N}-{name}.md
2. 必須包含：
   - 操作化的偵測步驟（不是理論描述，是 evaluator 可以逐步執行的）
   - 偵測信號（在原文中看到什麼 → 觸發檢查）
   - 嚴重度判定規則
   - 修正模板
3. 註冊：在 logic-fallacy-chain.md 中加入觸發規則
4. 在 SKILL.md 的 gate→logic layer 對應表中加入
```

---

## 5. 新增 Preset

最輕量的擴充——不需要新建任何檔案。

### 步驟

```
1. 在 quick-modes.md 的「場景化 Preset」段落中加入新的 Preset 定義
2. 在 runner.py 的 PRESETS dict 中加入對應的 gate 列表
3. 格式：

### 📦 Preset X: 「{場景名}」

觸發：{什麼時候用這個 preset}
自動執行：
  □ Gate N: {哪個 sub-module}
  □ ...
跳過：{哪些不需要}
成本：~N subagent calls
```

---

## 6. 新增 Reviewer Persona

### 步驟

```
在 surpass/reviewer-personas.md 中加入新的 persona block：

### Persona N: The {Name}（{中文名}）

關注：（這種審稿人最在乎什麼？3-5 項）
典型質疑：（模擬 2-3 句審稿意見）
啟動的 Gate/Layer：（重點強化哪些 gate？）
```

---

## 7. 新增 Gate（重量級擴充）

新增 Gate 是最大的結構性變更，需要修改多個檔案。只在現有 5 道 gate 都無法覆蓋的新檢查維度時才做。

### 需要修改的檔案

```
1. 新建：references/{gate-name}.md（Layer 1 reference，~200-400 行）
2. 新建：references/{gate-name}/{sub-modules}（如需要）
3. 修改：SKILL.md — 觸發條件表 + gate→logic 對應表
4. 修改：parallel-execution.md — 加入依賴分析
5. 修改：quick-modes.md — 決定在哪些 mode/preset 中啟用
6. 修改：runner.py — GATES list 和 MODES/PRESETS dicts
7. 修改：issue-schema.md — 如果需要新的 issue category
8. 修改：metrics/ — 新增對應的 benchmark 設計
```

### 新 Gate 的必要條件（避免不必要的膨脹）

```
✅ 新增 Gate 的理由成立：
  - 現有 5 道 gate + logic chain 無法覆蓋
  - 有獨立的檢查維度（不是現有 gate 的子集）
  - 有至少 5 個可操作的 checklist 項目

❌ 不應新增 Gate 的情況：
  - 可以用 sub-module 加到現有 gate → 用 sub-module
  - 可以用 logic layer 覆蓋 → 用 logic layer
  - 只有 1-2 個 checklist 項目 → 合併到最相關的 gate
```

---

## 8. 新增語言的 Overclaim 信號詞

### 步驟

```
在 writing-verification.md 的「多語言 overclaim 信號詞」區塊中加入：

  {語言名}：「{信號詞1}」「{信號詞2}」...

選擇標準：
  - 選等同於英文 "prove", "demonstrate", "revolutionary" 的詞
  - 不要選正常學術寫作中合法使用的詞
  - 每種語言 5-10 個信號詞即可
```

---

## 命名規範

```
檔案名：kebab-case（如 social-science.md, ml-experiment.md）
Gate 名：snake_case（如 hypothesis_guard, result_guard）
Issue ID：{GATE_CODE}-{NNN}（如 G1-001, LC-003, CS-005）
Anchor ID：{SECTION}-P{N}（如 SEC-INTRO-P3, SEC-RESULTS-P1）
Preset 名：lowercase（如 ml, clinical, socsci）
```

---

## 版本策略

```
版本號：{major}.{minor}
  major：新增 Gate、移除模組、breaking change
  minor：新增 sub-module、preset、persona、bug fix

目前版本：2.0
下一個 minor（新增 domain/preset）：2.1
下一個 major（新增 Gate 或架構改變）：3.0

版本記錄在 SKILL.md 的 frontmatter 中（description 欄位）
和 runner.py 的 report["version"] 中。
```

---

## 擴充後的驗證

任何擴充都應該跑至少 3 個回歸測試：

```
1. 一個新模組應該抓到的案例 → 確認新功能有效
2. 一個新模組不應該影響的案例 → 確認沒有副作用
3. 一個邊界案例 → 確認判定邏輯合理

使用 test-matrix.md 的格式記錄測試結果。
```

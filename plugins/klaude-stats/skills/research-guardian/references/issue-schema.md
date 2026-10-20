# Issue Schema & Evidence System
# Inspired by OpenReviewer's structured issue format

## 標準化 Issue 格式（所有 Gate 必須遵循）

每個 gate / logic layer 輸出的 issue 必須符合以下結構：

```json
{
  "id": "G4-003",
  "gate": "result_guard",
  "category": "overclaim",
  "severity": "major",
  "title": "因果語言超出研究設計允許",
  "description": "使用 'causes' 描述 cross-sectional 研究的發現",
  "location": {
    "anchor_type": "paragraph",
    "anchor_id": "DISCUSSION-P3",
    "section": "Discussion",
    "excerpt_start": "These findings prove that..."
  },
  "evidence": [
    {
      "type": "section",
      "pointer": "METHODS-P1",
      "excerpt": "cross-sectional survey of 450 students",
      "support_level": "direct"
    },
    {
      "type": "inferred",
      "pointer": "causal_strength_ladder",
      "support_level": "direct"
    }
  ],
  "suggested_fix": "改為 'These findings suggest an association between...'",
  "confidence": 0.92,
  "logic_layer": "L2-causal"
}
```

### 欄位定義

```
id:           [Gate簡碼]-[序號]  例：G1-001, G2-003, LC-007
gate:         哪個 gate 發現的
category:     問題類別（見下方類別表）
severity:     "critical" | "major" | "minor"
title:        一句話摘要（< 15 字）
description:  完整描述
location:     問題在原文中的精確位置
  anchor_type: "section" | "paragraph" | "sentence" | "figure" | "table" | "equation" | "reference"
  anchor_id:   穩定的錨點 ID（例：METHODS-P3 = Methods 第 3 段）
  section:     所在章節名
  excerpt_start: 問題段落的開頭幾字（用於定位）
evidence:     支持此判定的證據列表
  type:        "section" | "paragraph" | "figure" | "table" | "reference" | "inferred" | "external"
  pointer:     指向的錨點或規則名稱
  excerpt:     相關原文摘錄
  support_level: "direct"（直接證據）| "weak"（間接）| "inferred"（推論）
suggested_fix: 具體的修正建議
confidence:   0.0-1.0 的信心分數
logic_layer:  如果由 Logic Chain 發現，標記是哪一層
```

### Issue 類別表
```
hypothesis:    假設相關（novelty、可測試性、邏輯一致性）
literature:    文獻相關（幻覺引用、覆蓋度、準確性）
experiment:    實驗設計（偏誤、統計效力、資料洩漏）
result:        結果報告（數值不一致、統計錯誤）
overclaim:     過度推論（語氣超出證據、泛化跳躍）
logic:         邏輯謬誤（因果飛躍、循環論證等）
structure:     結構缺陷（缺失章節、佔位文字）
consistency:   一致性（跨章節矛盾、數字衝突）
ethics:        倫理相關（IRB 缺失、引用倫理）
formatting:    格式（統計報告格式、引用格式）
```

---

# Cross-Section Consistency Module

## 何時載入
在 Aggregator 彙整所有 gate 結果後，自動執行。

## 10 對強制交叉驗證

```
Pair 1:  Abstract ↔ Results
  → 摘要中的數字是否與結果段一致？
  → 摘要中的結論是否被結果支持？

Pair 2:  Introduction ↔ Discussion
  → Introduction 提出的問題，Discussion 是否回應了？
  → Discussion 是否引入了 Introduction 沒提過的新問題？

Pair 3:  Introduction ↔ Methods
  → Introduction 的研究目標，Methods 是否有對應的實驗設計？
  → 有沒有 Methods 中描述但 Introduction 沒動機的分析？

Pair 4:  Methods ↔ Results
  → Methods 描述的每個分析，Results 是否都有報告？
  → Results 報告的數據，Methods 是否都有描述方法？

Pair 5:  Results ↔ Discussion
  → Discussion 的解讀是否與 Results 的數據一致？
  → Discussion 是否討論了 Results 中未報告的發現？

Pair 6:  Results ↔ Conclusion
  → Conclusion 是否超出 Results 的支持範圍？
  → Conclusion 中的數字（如有）是否與 Results 一致？

Pair 7:  Figures/Tables ↔ Text
  → 每個 figure/table 是否在正文中被引用和討論？
  → 正文描述的趨勢是否與 figure/table 一致？

Pair 8:  References ↔ Citations
  → 正文引用的每篇文獻是否都在 reference list 中？
  → Reference list 的每篇文獻是否都在正文中被引用？

Pair 9:  Claims ↔ Evidence
  → 每個事實性宣稱是否有對應的證據？
  → 證據是否真的支持宣稱（不是相反方向的）？

Pair 10: Hypothesis ↔ Conclusion
  → 結論是否回答了假設？
  → 如果假設未被支持，是否被誠實承認？
```

### 交叉驗證的 Issue 格式
```json
{
  "id": "CS-001",
  "gate": "cross_section",
  "category": "consistency",
  "severity": "major",
  "title": "Abstract 數字與 Results 不一致",
  "location": {
    "anchor_type": "cross_section",
    "section_a": "Abstract",
    "section_b": "Results"
  },
  "evidence": [
    {
      "type": "paragraph",
      "pointer": "ABSTRACT-P1",
      "excerpt": "accuracy of 97.2%",
      "support_level": "direct"
    },
    {
      "type": "paragraph", 
      "pointer": "RESULTS-P3",
      "excerpt": "accuracy of 96.8%",
      "support_level": "direct"
    }
  ]
}
```

---

# Citation Ethics Module

## 何時載入
在 Literature Guard 執行時同步啟動。

## 引用倫理檢查清單

### Self-Citation 分析
```
□ 計算 self-citation rate = 自我引用數 / 總引用數
  - < 10%: 正常
  - 10-20%: 🟡 注意（某些領域正常）
  - > 20%: 🔴 需要解釋
□ Self-citation 是否分佈在整篇論文中？
  - 集中在 Related Work → 可能用自我引用建構 novelty
  - 分佈均勻 → 較正常
□ 是否引用了自己未發表/正在審查的工作？
  - 在雙盲審查中 → 🔴 可能破壞盲性
```

### Citation Clustering
```
□ 引用是否過度集中在少數研究群組？
  - 計算：top-3 作者群組佔引用的比例
  - > 40% → 🟡 citation concentration
□ 是否存在 citation ring（互相引用的小圈子）？
  - 同一組作者在多篇引用中交叉出現 → 可疑
□ 地理/機構集中度？
  - 所有引用來自同一國家/機構 → 🟡
```

### Predatory Journal 偵測
```
□ 引用的期刊是否在 Beall's List 或類似清單中？
□ 是否引用了沒有同行審查的來源且當作正式證據？
□ 是否引用了 retracted papers？（見 literature/biomedical.md 的 Retraction Check）
```

### 引用操縱信號
```
□ 大量引用非常老舊且與主題關聯性弱的文獻？
  → 可能是為了引用數而引用
□ 引用了競爭對手的工作但只描述其缺點？
  → 🟡 偏頗引用
□ 關鍵競爭性文獻完全未被引用？
  → 🔴 選擇性忽視
```

---

# Issue Normalization & Deduplication

## 何時載入
Aggregator 收集所有 gate 結果後，在產生最終報告前。

## 正規化流程

### Step 1: 格式統一
```
確保所有 issue 都符合標準 JSON schema。
缺少的欄位 → 補充預設值：
  confidence: 默認 0.7
  suggested_fix: 默認 "需要進一步分析"
  evidence: 默認 [{type: "inferred", support_level: "weak"}]
```

### Step 2: 去重
```
兩個 issue 如果滿足以下條件 → 合併：
  - 指向同一段文字（location 相同或重疊）
  - 描述同一類型的問題（category 相同）
  - 來自不同的 gate

合併規則：
  - 保留 severity 最高的
  - 合併 evidence 列表
  - confidence = max(兩者的 confidence)
  - 在 description 中標注 "detected by Gate X and Gate Y"
```

### Step 3: 嚴重度校準
```
跨 gate 嚴重度校準規則：
  - 同一問題被 2+ gate 獨立偵測 → severity 上調一級
  - 問題只有 inferred evidence → severity 不得高於 "major"
  - confidence < 0.5 → severity 不得高於 "minor"
```

### Step 4: 排序
```
最終 issue 列表排序：
  1. severity: critical → major → minor
  2. 同 severity 內按 confidence 降序
  3. 同 confidence 按 location（出現順序）
```

---

# Anti-Hallucination Grounding

## 何時載入
作為所有 subagent system prompt 的強制附錄。

## 規則

```
1. 每個判定必須有至少一條 evidence：
   - direct: 原文中的明確段落/數字
   - weak: 原文中暗示但未明說
   - inferred: 基於領域知識推論
   
2. 不能有 evidence 的判定：
   - 不是 FAIL → 是 "insufficient evidence to evaluate"
   - 永遠不要猜測問題存在
   - "I cannot verify X" ≠ "X is wrong"

3. Confidence 規則：
   - 有 direct evidence → confidence ≥ 0.8
   - 只有 weak evidence → confidence 0.5-0.7
   - 只有 inferred → confidence 0.3-0.5
   - 沒有 evidence → 不產生 issue

4. 措辭規則：
   ✅ "The paper states X but the data shows Y"（有證據）
   ✅ "Insufficient evidence to verify claim X"（承認無法判定）
   ❌ "The authors likely fabricated X"（猜測動機）
   ❌ "This is probably wrong"（無證據的判定）
```

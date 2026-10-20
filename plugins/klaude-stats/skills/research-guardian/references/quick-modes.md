# Quick Modes — 快捷模式與效能最佳化

## 何時載入
每次 Guardian pipeline 啟動時優先讀取本文件。
本模組決定「跑什麼」和「跑多深」，在浪費算力和漏掉問題之間取平衡。

---

## 設計原則

完整 pipeline（5 gates + logic chain + aggregator）= 7+ subagent calls。
大多數場景不需要全開。關鍵是：**用 10% 的算力抓到 80% 的問題。**

根據 Batch 1-3 的測試數據，問題分佈如下：
```
Gate 4 (Result Guard)   : 攔截了 28% 的問題 ← 最高
Gate 5 (Writing Guard)  : 攔截了 22% 的問題
Logic Chain (Layer 2+3) : 攔截了 20% 的問題
Gate 2 (Literature)     : 攔截了 15% 的問題
Gate 3 (Experiment)     : 攔截了 10% 的問題
Gate 1 (Hypothesis)     : 攔截了 5% 的問題  ← 最低
```

結論：**Result Guard + Writing Guard + Logic Layer 2-3 = 70% 的攔截力。**

---

## 三個快捷模式

### 🟢 QUICK MODE — 「30 秒體檢」
```
適用場景：
  - 內部筆記、初步想法、brainstorming 輸出
  - 非正式分享、團隊討論用
  - 「幫我快速看一下有沒有明顯問題」

執行內容：
  1. Pre-scan（Gate 0）— 30 秒快速掃描
     □ 整體語氣合理嗎？
     □ 結論強度 vs. 方法匹配嗎？
     □ 有明顯結構缺失嗎？（無 limitations = 立即紅旗）
  
  2. Overclaim 快篩 — 信號詞 + 結構性 Pattern 掃描
     □ 信號詞命中？
     □ 四個結構性 overclaim pattern觸發？
  
  3. 數值 Sanity Check — 只看數字合不合理
     □ accuracy > 99%? → 可疑
     □ 效果量 > 2.0? → 可疑
     □ p 值和檢定統計量能不能對上？

成本：1 subagent call，~3K tokens
時間：< 1 分鐘
預期攔截率：~60% of all issues（抓大放小）
```

### 🟡 STANDARD MODE — 「門診檢查」
```
適用場景：
  - 研究報告、團隊交付物
  - 投稿前的初次自檢
  - 「我要確保主要問題都被處理了」

執行內容：
  1. Gate 4 (Result Guard) — 完整版
  2. Gate 5 (Writing Guard) — 完整版
  3. Logic Layer 2 (因果) + Layer 3 (統計) — 只跑最高優先級的兩層
  4. Gate 2 (Literature) — 只做引用存在性（跳過覆蓋度和新近性）
  5. Pre-scan 結果中的紅旗項 → 觸發對應 gate 的深度檢查

跳過的：
  - Gate 1 (Hypothesis) — 到這個階段假設通常已確定
  - Gate 3 (Experiment) — 除非 Pre-scan 觸發紅旗
  - Logic Layer 1, 4, 5 — 除非 Gate 5 發現結構問題
  - 所有 domain sub-modules — 除非主 gate 明確需要

成本：3-4 subagent calls，~15K tokens
時間：3-5 分鐘
預期攔截率：~85% of all issues
```

### 🔴 FULL MODE — 「全身健檢」
```
適用場景：
  - 論文投稿（journal 或 conference）
  - 臨床研究報告
  - 政策建議、法規提交
  - 「這份東西要見世面，不能出任何錯」

執行內容：
  - 全部 5 Gates + 全部 5 Logic Layers + Aggregator
  - 所有適用的 domain sub-modules
  - Cross-gate 矛盾偵測
  - Subagent Strategy A 或 C（視風險等級）

成本：7-13 subagent calls，~50-100K tokens
時間：10-20 分鐘
預期攔截率：>95% of all issues
```

---

## 自動模式選擇器

### 第一層：模式選擇（使用者意圖）

如果使用者沒有指定模式，根據以下信號自動選擇：

```
信號                                    → 模式
──────────────────────────────────────────────
"快速看一下" / "有沒有明顯問題"        → 🟢 QUICK
"幫我檢查" / "review this"            → 🟡 STANDARD
"投稿前" / "submission" / "publication" → 🔴 FULL
"臨床" / "clinical" / "patient"        → 🔴 FULL
"政策" / "policy" / "regulatory"       → 🔴 FULL
內部筆記 / draft / brainstorm          → 🟢 QUICK
有 "limitations" 段落                   → 🟡 STANDARD（至少已有自覺）
無 "limitations" + 有 overclaim 信號   → 🔴 FULL（需要最嚴格）
```

### 第二層：Preset 自動辨識（內容感知路由）

Pre-scan 不只判斷模式，還**分析內容本身**來自動選擇 preset 和 sub-modules。
使用者不需要知道系統有哪些 preset——系統自己從內容中推斷。

```
辨識維度         掃描方式                           → 路由結果
──────────────────────────────────────────────────────────────
領域辨識:
  引用來源       PubMed/NEJM/Lancet 等             → biomedical
                 arXiv/NeurIPS/ICML 等             → cs-ml
                 PsycINFO/SSRN/ERIC 等             → social-science
  術語           patient, RCT, placebo, dosage      → biomedical
                 model, accuracy, epoch, GPU        → cs-ml
                 participants, survey, Likert, α    → social-science

研究設計辨識:
  Methods 關鍵詞  randomized, blinded, placebo      → rct sub-module
                 cohort, case-control, cross-sect.  → observational
                 fine-tuned, trained, benchmark     → ml-experiment
                 interview, thematic, saturation    → qualitative

統計方法辨識:
  Results 格式   t(df), F(df1,df2), χ², p=         → frequentist
                 posterior, HDI, BF, MCMC, ROPE     → bayesian
                 AUROC, F1, precision, recall       → ml-metrics

辨識規則:
  - 多個領域信號同時出現 → 載入所有匹配的 domain sub-modules
  - 無法辨識 → 不載入 domain sub-module（用通用 checklist）
  - 辨識結果附帶 confidence（high/medium/low）
  - confidence = low 時，在報告中標記 "auto-detected, may be inaccurate"
```

### 路由輸出格式
```
Pre-scan 輸出包含兩部分：

1. 模式決定：
   mode: "standard"
   reason: "overclaim signals detected, no limitations"

2. 路由決定：
   domain: ["biomedical", "cs-ml"]    ← 可以多個
   domain_confidence: "medium"
   study_type: "ml-experiment"
   stat_framework: "ml-metrics"
   sub_modules_to_load: [
     "hypothesis/biomedical.md",
     "experiment/ml-experiment.md",
     "result/ml-metrics.md"
   ]
```

---

## 快速診斷套餐（場景化 Preset）

### 📦 Preset A: 「ML 論文投稿前」
```
觸發：ML/DL 論文 + 會議/期刊投稿

自動執行：
  □ Gate 2: 引用存在性 + SOTA 時效性（cs-ml sub-module）
  □ Gate 3: ML experiment sub-module 完整版
     → 資料洩漏 checklist（逐句掃描）
     → Baseline 公平性
     → 超參數完整性
  □ Gate 4: ML metrics sub-module
     → 指標-任務匹配
     → 統計顯著性
     → 可疑信號清單
  □ Gate 5: Conference sub-module
     → 頁數、盲審合規、Contribution 清晰度
  □ Logic Layer 5: 研究特有謬誤
     → Benchmark 泛化、消融≠必要、SOTA 幻覺

跳過：RCT/觀察性/質性 sub-modules、Bayesian、社科量表
成本：~4 subagent calls
```

### 📦 Preset B: 「臨床研究報告」
```
觸發：醫學/臨床 + 涉及病人數據

自動執行：
  □ Gate 1: Biomedical hypothesis sub-module
     → 臨床可轉譯性、生物學合理性、安全性紅線
  □ Gate 2: Biomedical literature sub-module
     → 證據等級標記、Retraction check（強制）
     → 引用分級（Tier 1/2/3）
  □ Gate 3: 根據設計自動選 RCT / Observational sub-module
     → IRB 確認、CONSORT/STROBE 完整性
  □ Gate 4: Frequentist sub-module（大部分臨床研究用頻率學派）
     → 效果量 + CI + NNT
  □ Gate 5: Journal sub-module
  □ Logic Layer 2: 因果推理（臨床最關鍵）

跳過：ML metrics、CS/ML 文獻標準、conference format
成本：~5 subagent calls
```

### 📦 Preset C: 「社科調查研究」
```
觸發：問卷/調查 + 心理/社會/教育變項

自動執行：
  □ Gate 1: Social science sub-module
     → 構念效度、再現性危機意識、WEIRD 偏誤
  □ Gate 2: Social science literature sub-module
     → 再現性狀態標記、效果量校準
  □ Gate 3: Observational sub-module
     → 混淆控制、因果語言校準
  □ Gate 4: Frequentist sub-module
     → p 值報告規範、效果量
  □ Logic Layer 2 + 3: 因果 + 統計

跳過：ML 相關、Bayesian、RCT、臨床特有
成本：~4 subagent calls
```

### 📦 Preset D: 「文獻回顧 / Systematic Review」
```
觸發：literature review / systematic review / meta-analysis

自動執行：
  □ Gate 2: 完整版（三重驗證 + 覆蓋度 + 新近性）
     → 領域 sub-module（根據主題自動選）
     → SR 摘要豁免規則
  □ Gate 5: 完整版
     → 斷言追溯（每個宣稱都要有引用）
  □ Logic Layer 4: 論證結構
     → Cherry-picking 偵測（是否只引用支持的文獻？）
     → 稻草人偵測（反面觀點是否被公平呈現？）

跳過：Gate 3（沒有自己的實驗）、Gate 4（沒有自己的數據）
成本：~3 subagent calls ← 最輕量的 preset
```

### 📦 Preset E: 「假設生成 / 研究提案」
```
觸發：hypothesis / research proposal / grant application

自動執行：
  □ Gate 1: 完整版 + 領域 sub-module
     → Novelty 三重搜索
     → 搜索紀錄強制（強制）
  □ Gate 2: 只做覆蓋度和新近性（引用存在性在提案階段次要）
  □ Logic Layer 1 + 2: 形式邏輯 + 因果推理
     → 假設的邏輯一致性
     → 因果宣稱是否超出可驗證範圍

跳過：Gate 3-5（還沒有實驗和結果）
成本：~2 subagent calls ← 最快的 preset
```

---

## 漸進式升級（Progressive Escalation）

任何模式都可以在執行過程中自動升級：

```
🟢 QUICK 中發現嚴重問題：
  → Pre-scan 觸發 > 2 個紅旗 → 自動升級到 🟡 STANDARD
  → 發現幻覺引用或自相矛盾 → 自動升級到 🔴 FULL

🟡 STANDARD 中發現嚴重問題：
  → 任何 gate 報告 CRITICAL → 自動升級到 🔴 FULL
  → Cross-gate 矛盾觸發 → 自動升級到 🔴 FULL

🔴 FULL 中發現極端問題：
  → 多個 CRITICAL + 幻覺引用 → 建議 Strategy C（對抗性）+ 人工

升級只向上不向下。一旦升級，不會因為後續 gate 通過而降級。
```

---

## 效能指標對照

```
模式         subagent calls   tokens    時間     攔截率    適用頻率
─────────────────────────────────────────────────────────────────
🟢 QUICK     1               ~3K       <1min    ~60%      60% of tasks
🟡 STANDARD  3-4             ~15K      3-5min   ~85%      25% of tasks
🔴 FULL      7-13            ~50-100K  10-20min >95%      15% of tasks
─────────────────────────────────────────────────────────────────
加權平均成本：~12K tokens/task（vs. 全部用 FULL 的 ~70K）
→ 節省約 83% 的算力，攔截率下降 < 10%
```

---

## 輸出格式

Guardian 報告的開頭應顯示使用了哪個模式：

```
══════════════════════════════════
 RESEARCH GUARDIAN v1.4
 Mode: 🟡 STANDARD (auto-selected)
 Preset: ML Paper (Preset A)
 Escalated: No
══════════════════════════════════
```


---

## 報告語氣校準

Guardian 報告的語氣應根據目標讀者調整：

```
audience 參數    語氣風格                     範例
──────────────────────────────────────────────────────
"expert"        標準學術語氣                  "FAIL: overclaim — 因果語言超出設計允許"
"student"       建設性、教育性                "這裡有個可以改進的地方：cross-sectional
                                             設計不適合用因果語言，建議改為..."
"self-check"    簡潔、行動導向                "⚠ 改 'causes' → 'associated with'"
"manager"       高層摘要，不含術語            "結論部分有 3 處過度推論，建議修正後再發佈"

預設：如果未指定 → "expert"
Quick Mode 預設：→ "self-check"
```

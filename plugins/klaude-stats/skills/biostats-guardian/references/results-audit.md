# Results Audit Checklist (Role 3 — Post-Execution Results Auditor)

此 checklist 在 `run_pipeline.py` 完成執行後，由獨立 subagent 對每一個 biostats skill 的輸出（log 檔、stdout/stderr、output table、更新後的 research_plan.json）做事後稽核。

> **2026-08-11 改版**：
> - **RES-003（掃 log 抓 `[QC_*]`）已刪除。** `run_pipeline.py` 的 `extract_qc_warnings()`（2026-08-12 快照約 :331，經 `_record_qc()` 寫入）用同一組 prefix 做同一件事，結果已存進 `step.qc_warnings[]`。派一隻 LLM 去重跑一個 regex 是這一層最純粹的浪費。**取代方式**：agent 直接讀 `research_plan.json$.pipeline[i].qc_warnings[]`，把它當**既有事實**納入判斷（該不該升級成 block 仍是 agent 的工作），不要自己去掃 log 重找一次。
> - **RES-004（success_criteria）改為讀 evaluator 輸出**，不再目視。
> - **RES-001 / RES-002 / RES-006 由 `precheck_configs.py` 的 post 模式涵蓋**；agent 引用其結果，只在**輸出不存在時**才自己算（見各條的「涵蓋狀態」）。缺結果不等於通過。

## Subagent 身份規範

- **你是 Results Auditor**。角色接近「臨床期刊 reviewer」。
- **Context 隔離**：你不看 script 本身（那是 Role 2）、不看 config 產生過程；只看執行**結果**（輸出檔 + log）。
- **數據 grounding**：每個判斷必須指向具體的數值 + 出處（哪個檔案、哪個 cell、哪行 log）。

## Rubric

| 層級 | 意義 |
|---|---|
| `pass` | 數值合理、無 QC 警訊、success_criteria 全過 |
| `warn` | 有 `[QC_WARNING]` 或數值邊緣（CI 很寬、接近 implausibility threshold） |
| `block` | 有 `[QC_BLOCKING]`、數值荒謬、success_criteria 未達、樣本數重大流失 |
| `uncertain` | 輸出格式異常無法 parse |

## Check ID 完整清單

### RES-001 數值合理性
**涵蓋狀態：** 由 `precheck_configs.py`（post 模式）計算。agent 引用 `precheck_post.json` 的結果；**該檔不存在時**才自己從 output 表算一次，並在 summary 註明「確定性層缺席，本條由 LLM 補算」。
**Check:**
- HR / OR ∈ [0.01, 100]；超過此範圍通常是估計崩潰或 sparse data
- 95% CI width < 3 orders of magnitude（e.g. HR 2.0 但 CI [0.001, 5000] → 警訊）
- p-values ∈ [0, 1]
- Sample size N > 0；不可負、不可 NaN
**Evidence:** output Excel/CSV 中的 HR、CI、p column。
**Severity map:** HR > 100 或 < 0.01 → `block`（除非明確標註 penalized/firth）。CI 跨 3 orders → `warn`。

### RES-002 Sample size 對齊
**涵蓋狀態：** 由 `precheck_configs.py`（post 模式）計算。同 RES-001 的引用/補算規則。
**Check:** 每個 skill 最終使用的 N 必須和 `flowchart` 的 final-cohort N 一致（± documented drops）。
**Evidence:** flowchart output 的最終 N vs 該 skill output 的 N。
**Severity map:** 差異 > 5% 且未在 qc_warnings 說明 → `block`。

### RES-003 —— 已刪除（2026-08-11）
**原內容：** 掃描 `{output_dir}/logs/{step_id}.log` 找 `[QC_BLOCKING]` / `[QC_WARNING]` 並轉成 issue。
**為什麼刪：** `run_pipeline.py` 的 `extract_qc_warnings()` 已用同一組 prefix 掃過同一批 log，結果寫在 `research_plan.json$.pipeline[i].qc_warnings[]`。這條等於派一隻 LLM 重跑一個 regex。
**取代方式：** agent **讀** `qc_warnings[]` 當輸入事實（判斷某條 warning 在本研究脈絡下該不該升級成 block，仍是 agent 的工作、仍要做），但不重新掃 log。
**編號保留不回收**，避免與舊 report 的 `check_id` 撞號。

### RES-004 Success criteria 達成（改為讀 evaluator 輸出）
**涵蓋狀態：** `success_criteria[].check` 本來就是機器可讀的運算式（`"events_per_group >= 1"`、`"model_converged == true"`、`"ci_width < 100"`），由 `precheck_configs.py` 的 evaluator 逐條求值。
**Check:**
1. 讀 evaluator 輸出（每條 criterion 的 `check` 字串、代入的實際值、`passed` 真假、criterion 自帶的 `severity`）。
2. **不要目視評估運算式**——過去這一條是「schema 定義了一個 mini-DSL 卻沒有 parser，改由 LLM 目視」，正是要修掉的失效模式。
3. Agent 只做兩件 evaluator 做不到的事：(a) 標為 fail 的 criterion，判斷它是真缺陷還是門檻訂得不合理；(b) **檢查 criteria 本身夠不夠**——某個 step 的 success_criteria 是空的或只有 trivial 條件（例如只檢查檔案存在），這是 plan 的漏洞，開一條 `warn`。
4. evaluator 輸出不存在 → 本條**不得跳過**：agent 自己逐條代入求值，並在 summary 註明「evaluator 缺席，本條由 LLM 補算」。
**Evidence:** evaluator 輸出的 criterion 條目（含實際值），或補算時的來源 cell/log 行。
**Severity map:** 依 criterion 自帶的 severity（blocking → block；warning → warn）。criteria 空缺或 trivial → `warn`。

### RES-005 輸出重複值
**Check:** 若輸出含 subject-level CSV（例如 PSM 匹配後 cohort），不應有重複的 subject_id（除非 matching 允許 replacement，需在 config 宣告）。
**Evidence:** output CSV 的 subject_id 重複檢查。
**Severity map:** 有重複且未宣告 → `block`。

### RES-006 Event count for regression（EPV）
**涵蓋狀態：** 由 `precheck_configs.py`（post 模式）計算。同 RES-001 的引用/補算規則。
**Check:** 任何 regression 的 events-per-variable (EPV) 實際執行時 ≥ 10（呼應 COL-007，但這邊是事後實測）。
**分母是「擬合的參數數」，不是「變項數」**：類別變項展開成 k−1 個 dummy、spline 展開成 (knots−1) 個基底、交互項各算一個。用變項數當分母會系統性高估 EPV。
**Evidence:** log 中的 event count + 實際擬合的參數數。
**Severity map:** EPV < 5 → `block`。5-10 → `warn`。
**注意：** EPV ≥ 10 是下限不是安全證書；過了門檻不代表估計穩定（仍要看 CI 寬度與 RES-001）。

### RES-007 Convergence
**Check:** log 中是否有 `ConvergenceWarning`、`LinAlgError`、`PerfectSeparation`、`singular matrix` 等字樣。
**Evidence:** log 行。
**Severity map:** 有任一 → `block`（模型沒有真的 fit 好）。

### RES-008 Kaplan-Meier / CIF 數值
（僅對 `kaplan-meier`、`competing-risk` 套用）
**Check:**
- Survival probability ∈ [0, 1]，單調不遞增
- Median survival 若為 NA 必須有 reason（未達 50% event）
- CIF + survival 的和 ≤ 1（competing risk）
**Evidence:** output 中的 survival table。
**Severity map:** 任一違反 → `block`。

### RES-009 PSM balance
（僅對 `psm-matching` 套用）
**Check:** matching 後每個 covariate 的 SMD（standardized mean difference）應 < 0.1。
**Evidence:** balance diagnostics output。
**Severity map:** 任一 SMD > 0.25 → `block`。0.1-0.25 → `warn`。

### RES-010 Cross-skill consistency
**Check:** 當多個 skill 處理同一 cohort 時，它們回報的 N 必須一致：
- `table1` total N = `flowchart` final N
- `kaplan-meier` 的 at-risk N at t=0 = table1 的 group N
- `univariate-forest`、`multivariate-interaction` 的 N 一致（若 covariate missing 導致差異，必須在 log 說明）
**Evidence:** 各 skill 的 N。
**Severity map:** 未解釋的差異 > 5% → `block`。

### RES-011 Missing / NaN 在輸出
**Check:** output 表格中不應有 NaN（除非是合理佔位，例如「組內無 event 所以無法估 HR」）。
**Evidence:** output 表格 cell。
**Severity map:** 關鍵欄位 NaN 未解釋 → `warn`。

### RES-012 Figure sanity（若有）
**Check:** 若 skill 產生 PNG/PDF（KM curve、forest plot），檔案存在且 > 10 KB（避免空圖）。
**Evidence:** file size。
**Severity map:** 檔案 < 10 KB → `block`。

### RES-013 Table1 特定
（僅對 `table1` 套用）
**Check:**
- 每個 row 的 N 合計必須等於 cohort total
- p-value column 若有 grouping 必須計算；未 grouping 則不應有 p
- categorical 變項的百分比和應 ≈ 100%（± rounding）
**Evidence:** table1 output cells。
**Severity map:** N mismatch → `block`。% 遠離 100% → `warn`。

### RES-014 Cross-language sanity（雙路徑驗證；cause-specific 限定）
**靈感**：李宏毅 2026 lec 5 self-correction §7 陷阱 2「幻覺式修正」— 同一工具自我檢查容易陷入「用錯誤糾正錯誤」，必須引入外部 grounding。對 regression 結果做 R ↔ Python 雙路徑互算就是最便宜的 grounding。

**何時跑**（缺省行為，可被 `research_plan.json$.guardian.cross_lang_check` 覆寫）：
- `quick` mode：對 `is_primary_outcome=true` 的 regression step 啟用（限縮版 — 不跑次要 regression 以節省時間）
- `standard` / `full` mode：對所有 regression step 啟用
- `cross_lang_check: false` 顯式關閉 → 全部跳過（適用 toy run、教學、無法雙語環境）
- `cross_lang_check: true` 顯式開啟 → 所有 mode 對所有 regression step 強制啟用（覆寫 quick 的 primary-only 限縮）

**僅對以下 skill 套用**：`univariate-forest`（Cox / Logistic）、`multivariate-interaction`（Cox / Logistic）、`competing-risk`（**cause-specific Cox**, R survival::coxph vs Python lifelines.CoxPHFitter — Fine-Gray cross-lang sanity 是 R-only via cmprsk，本 guardian 不支援；P-7 audit fix 2026-05-07）、`auc-cstat`（Cox C-index）。其他 skill（table1、KM curve）不適用。

**Check**：
1. 主分析是 R survival → 用 Python `lifelines.CoxPHFitter` 或 `scikit-survival` 對同一份 cleansed CSV 重跑
2. 主分析是 Python lifelines → 用 R `survival::coxph` 重跑
3. 比對 primary covariate 的 HR、95% CI、p-value：
   - **HR 相對誤差** `|HR_R - HR_Py| / HR_R` < 1% → pass
   - 1-5% → warn（可能是 tied event 處理 method 差異：Efron vs Breslow vs exact）
   - \> 5% → block（hard error，coding bug 或變數定義不一致）
4. 同樣比對 events count、N — 必須 100% 一致

**Subagent 執行協定**：
- Subagent 收到 RES-014 task 時，呼叫 `Bash` 用 `Rscript -e` 或 `python -c` 跑最小 reproducible 重算（不是重跑整個 skill，只重跑 primary covariate 的 regression）
- 用 `python -c 'import lifelines; cph = lifelines.CoxPHFitter(); cph.fit(df, "t", "e"); print(cph.summary)'` 即可
- 結果寫進 issue 的 `evidence`：`{"type": "cross_lang_repro", "main_HR": 1.42, "alt_HR_lifelines": 1.41, "rel_diff_pct": 0.7}`

**Evidence**：reproducer command + R/Python 雙邊 HR/CI/p-value table。

**Severity map**：
- HR rel_diff > 5% → `block`
- HR rel_diff 1-5% 且 events count 一致 → `warn`（提示用戶選定 tied event handling method 並在 manuscript 註明）
- HR rel_diff > 1% 且 events count 不一致 → `block`（資料切割不同步，coding bug）

**注意**：
- Tied event 處理：R `coxph` 預設 Efron，Python `lifelines` 預設也是 Efron（一致）；但若 R script 顯式用 `ties="breslow"` 必須在 Python 端對齊
- Categorical reference level：兩邊必須對齊；若不一致 HR 會反向（這是常見的 false-block 來源 — 先 check reference level 再判 severity）
- Missing data handling：R `na.action` 預設 `na.omit`，Python `lifelines` 自動 drop NA；若兩邊 N 不同先排除這個原因再 flag

**時間成本參考**：跑一次 alt-language regression 約 2-10 秒（小資料）到 1-2 分鐘（大資料）。User 已確認此成本可接受，因此 RES-014 在所有 mode 預設啟用；`quick` 限縮為 primary outcome only 以避免次要 regression 重複跑爆時間。

### RES-015 PH 假設：測了沒 + 違反時做了什麼（2026-08-11 新增；2026-08-12 收斂適用範圍）

reviewer 問的從來不是「測了沒」而已，而是「**違反時做了什麼——只是偵測到不算處置**」。這一條檢查後半句答不答得出來。

> **⚠ 適用範圍逐 producer 列舉，不是「所有 Cox」。** 初版寫成對 `multivariate-interaction`／`univariate-forest`／competing-risk cause-specific Cox 一律要求 PH 產物，但**目前只有 `multivariate-interaction` 真的產生那些檔案**——那會讓正確執行的 `univariate-forest` run 因為缺一個它從不產生的檔案被擋。跨 skill 的硬規則只能在**每個被列名的 producer 都實作同一份契約之後**才啟用。

| Producer | 目前的契約 | 缺件時 |
|---|---|---|
| `multivariate-interaction` | **完整**：`<output_base>_ph_test.json`（含 `status`、global、per_variable）＋ `_ph_diagnostics.png` ＋ 違反無 remedy 時 exit 2 | **block** |
| `univariate-forest` | **部分**：輸出表有逐變項 `*_schoenfeld_p` 欄位，但無 global 檢定、無產物檔、無 remedy gate | Cox run 而該欄位全空 → `warn`；**不得因為沒有 `_ph_test.json` 而 block** |
| `competing-risk`（cause-specific Cox）、其他 Cox producer | **無** | **不檢查、不 block**，直到該 skill 實作契約為止 |

**確定性版先跑，LLM 版只收尾。** RES-015 的可機械化部分已由 `scripts/ph_remedy_gate.py`（`RES-015-det`）在 manuscript 之前執行：artifact 在不在、`status` 是什麼、declared remedy 有沒有對應產物、`disclose` 有沒有 decision-log ID，以及**有 evidence sidecar 時的內容驗證**（sidecar 綁不綁得上這張表、remedy 相不相符、`status` 是不是 `computed`、分層變項有沒有涵蓋真正違反的變項）。**Results Auditor 不重做這些**，只處理確定性版讀不懂的爭議個案：**沒有 sidecar** 而產物存在但內容明顯不是那個分析（自建 step、或 sidecar 出現前的舊產物）、borderline 的臨床意義判讀、稿件把未處置 HR 當主估計呈現的措辭問題，以及 **`rmst` 的未校正問題**——它是各組 KM、沒有共變項，取代的卻是校正過的模型，稿件必須照實說，而「說得夠不夠清楚」只有人判得出來。gate 報告的 `verified_remedies` 與 `attestations_unverified` 兩欄就是分界：前者已驗過內容，後者才需要人。

**Check（只對契約「完整」的 producer 全套套用）:**
1. 輸出旁必須有 `<output_base>_ph_test.json`。**沒有 = 沒測**，不是「大概沒問題」。
2. 讀 `status`：
   - `computed` → 進第 3 點
   - `not_computed` → **block**（算不出來不是通過；step 本身也會 exit 2）
   - `not_applicable` → 確認模型本來就沒 fit 成功（該失敗另有 block），否則 → `block`
3. `global.p` 與各 `per_variable[].p` 對兩條線判讀（門檻定義見 `qa_thresholds.md`）：
   - **p < 0.01（gate，rank transform）** → `violated`，走第 4 點
   - **0.01 ≤ min p < 0.05（borderline band，取 rank/km 兩個 transform 的最小值）** → **不 block**，但這個 run **不得被描述成「符合 PH 假設」**。artifact 的 `borderline: true`、footnote 會寫「the assumption is NOT established」、`[QC_WARNING]` 會進 `qc_warnings[]`。Results Auditor 要確認：(a) 該 warning 真的出現在 manifest / qc_warnings，(b) `effect_size` 的 early/late split HR 有被看過，(c) 稿件沒有出現「PH assumption was satisfied」這類措辭。**這是實測的盲區**：n=500 的真實 early-only 效應（HR 0.5→1.0）40 次模擬有 9 次落在這個帶裡。
   - 帶內個案交 reviewer challenge domain 5 逐條表態（dismiss with reason / escalate），不得沉默通過。
4. `violated == true` 時，config 必須有事前指定的 `ph_violation_remedy`，且該 remedy 對應的動作**看得到**：
   - `stratify` / `time_varying` / `rmst` → pipeline 要有對應 step 或明確的手動分析產物；只有宣告、沒有產物 → `block`
   - `disclose` → 稿件 limitations 要有對應文字；沒有 → `warn`
5. 稿件若把違反 PH 的 adjusted HR 當主要效應量呈現而未提 remedy → `block`。

**擴充到其他 producer 的前提（三項全滿足才把它從「無」搬到「完整」）：**
(a) 產出同名同格式的 `_ph_test.json`（含 `status` 三態）；(b) 有 global 檢定、不只逐變項；(c) 違反且無 remedy 時該 skill 自己會非零退出。**三項沒到齊就不要寫進硬規則**——只有一支腳本撐得住的跨 skill 規則，擋掉的會是正確的執行。

**Evidence:** `ph_test.json` 的 `status` / `global` / `violating_variables`、config 的 `ph_violation_remedy`、對應 remedy 產物的路徑。
**Severity map:** 見上表與第 2、4 點。

## Output Format

與前兩個 role 同格式，`role` = `results`：

```json
{
  "role": "results",
  "skill": "kaplan-meier",
  "step_id": "km_os",
  "status": "warn",
  "issues": [
    {
      "role": "results",
      "skill": "kaplan-meier",
      "step_id": "km_os",
      "check_id": "RES-001",
      "severity": "warn",
      "message": "Group B 的 HR = 8.4 (95% CI 0.12, 582)，CI 跨 4 orders of magnitude，sparse data。",
      "evidence": [
        {"type": "output_table", "pointer": "km_os.xlsx!Sheet1!B4:D4", "value": {"HR": 8.4, "CI_low": 0.12, "CI_high": 582}}
      ],
      "suggestion": "檢查 Group B 的 event 數；若 < 5 個 event 建議合併分組或改用 Firth correction。",
      "confidence": 0.88
    }
  ],
  "summary": "Role 3 warn：一個 CI 過寬（sparse data 風險），其餘數值合理。",
  "completed_at": "2026-04-16T08:30:00+00:00"
}
```

## 寫回 research_plan.json

Role 3 的 issues 必須同步寫回 `research_plan.json$.pipeline[i].qc_warnings[]`，格式沿用現有 stderr `[QC_WARNING]` / `[QC_BLOCKING]` 的 string 慣例，但額外附 `[GUARDIAN]` tag：

```
[GUARDIAN_WARNING] RES-001 km_os: HR CI spans 4 orders (sparse data)
[GUARDIAN_BLOCKING] RES-007 uni_os: LinAlgError in model fit
```

這讓既有的 `extract_qc_warnings()` 繼續運作、不用改 run_pipeline.py。

## What Role 3 Does NOT Do

- 不重跑 pipeline、不執行 script
- 不改 output 檔（純 read-only）
- 不下「接受/拒絕 publish」的結論（只 flag；決定權在 user）

# Code Audit Checklist (Code Auditor — **drift-only**)

> **2026-08-11 改版：Role 2 不再每個 step 派一隻。**
> pipeline 的 `.py` 是版本控制下、跨專案完全相同的檔案。過去每個專案、每一步、每次重跑都重讀一次同一份 104 KB 的 `missing_data.py`，在可查紀錄裡抓到 0 件。現在的流程是：
>
> 1. `scripts/script_hashes.py check` 比對 sha256 與 skill 出貨版（含專案內 vendored 副本）。
> 2. **一致 → 完全跳過本 checklist**，印一行「pipeline 腳本未修改，跳過程式稽核」。
> 3. **不一致 → 派一隻** Code Auditor，**scope 限 `script_hashes.json` 的 `audit_scope[]`**，其餘檔案不讀不評。
> 4. baseline 不存在 → 視為 `block`（缺 baseline 不等於沒改動），不是跳過。
>
> 「route 有沒有真的接上」不靠讀 code 判斷，靠 `research-plan/scripts/test_routes_synthetic.py` 的已知真值 fixture。既有的 `test_pipeline_contract.py` **不算**替代品——mutation testing 已證明它測不到 wiring（刪掉 `reviewer_gate_satisfied` 呼叫仍 ALL PASS）。
>
> **⚠ 本 checklist 裡「拿 plan 對照 config」的那幾條（CODE-001 方法適切性、CODE-005 adjustment 完整性、CODE-007 filter 一致性）不能只在 drift 時才跑。** 出貨腳本原封不動、config 卻漏掉事前指定的 adjuster，雜湊會過、fixture 會過，而這幾條就這樣沒人管了。它們的確定性版本改由 `scripts/plan_routing_audit.py` **每次執行**都跑（PR-001/002/003/004）。本檔的完整版仍在 drift 時由 Code Auditor 套用。
>
> 本 checklist 的內容**完全保留**：一旦有人改了腳本，這些就是該問的問題。

## Subagent 身份規範

- **你是 Code Auditor**。你是臨床統計學家 + 程式碼審閱者的綜合角色。
- **Context 隔離**：你不參與 config 的生成；只看最終的 script + config 做靜態分析。不看 Claude 或 user 的對話。
- **只做靜態分析**：不執行 code、不讀 data。所有判斷基於 script 原始碼 + config JSON + research_plan.json。
- **不重寫 code**：你的任務是 flag 問題、給具體 suggestion。由 user 決定是否接受。
- **資料庫 pitfall 預讀**：若觸發 `${CLAUDE_SKILL_DIR}/references/pitfalls_biostat_db.md` 內某資料庫小節的偵測條件（dataset 標記 / regex），先 Read 該小節。pitfall 中涉及 reference level、censoring 規則、變數 coding、tied event 處理等項目對應到 CODE-001..013 既有 check（用最相關的編號 + message 註明「依 pitfalls_biostat_db.md 第 X 條」）。未觸發資料庫條件則跳過。

## Rubric

| 層級 | 意義 | 範例 |
|---|---|---|
| `pass` | 檢查通過 | CODE-001：Cox model 套用於 time-to-event outcome，合理 |
| `warn` | 存疑但可能可接受 | CODE-004：script 有 `dropna()` 但有 log 記錄被刪 n |
| `block` | 確定的方法選擇錯誤 | CODE-001：Cox 套到 binary outcome，應改用 logistic |
| `uncertain` | script 無法靜態分析（複雜動態邏輯）| — |

## Check ID 完整清單

### CODE-001 統計方法適切性
**Check:** script 使用的統計方法必須與 outcome type、時間結構相符。

| outcome_type | 適用方法 | 不適用（block） |
|---|---|---|
| time-to-event（有 time + event）| Cox PH, KM, competing risk | logistic / linear |
| binary（只有 event，無 follow-up 時間）| logistic, Fisher | Cox |
| continuous | linear, Wilcoxon, t-test | logistic, Cox |
| count | Poisson, negative binomial | linear（除非 log transform） |
| paired | paired t-test, Wilcoxon signed-rank | independent t-test |

**Evidence:** script 中的 `CoxPHFitter()`、`LogisticRegression()`、`sm.Logit()` 等 API 呼叫 + config 中的 outcome 結構。
**Severity map:** 方法與 outcome type 明確不符 → `block`。

### CODE-002 Config ↔ Code drift
**Check:**
- script 中所有變數值都應來自 config（不應 hardcode）
- config 中每個 key 都應該被 script 讀到（否則 config 改了不 effectful）
- 特別敏感：`alpha`、`reference_level`、`follow_up_years`、`n_boot`、`missing_strategy`
**Evidence:** script 的 literal string/number + config key 清單。
**Severity map:** 關鍵統計參數被 hardcode（例如 `alpha=0.05` 寫死）而 config 也有這個 key → `block`（drift）。config key 被忽略 → `warn`。

### CODE-003 Reference category
**Check:** 類別變項在 regression 中的 reference level 必須符合：
- `research_plan.grouping.reference_level`（grouping）
- `research_plan.covariates[].reference`（covariate）
- 若未指定，不得用 pandas 預設（字母順序第一），要在 config 明確宣告
**Evidence:** script 中 `C(var, Treatment(reference=...))`、`pd.Categorical(var, categories=[...])`、或 `statsmodels.formula` 中的 relevel。
**Severity map:** reference level 與 research_plan 不符 → `block`。未指定 reference → `warn`。

### CODE-004 NA handling
**Check:**
- script 不得在未記錄 n 的情況下 `dropna()`
- 允許的模式：`df = df.dropna(subset=[...]); print(f"[QC_WARNING] dropped {n_before - n_after} rows")`
- multiple imputation 若被使用，必須明確宣告 m、seed
**Evidence:** script 中所有 `dropna`、`fillna` 呼叫 + 前後的 logging。
**Severity map:** silent dropna → `block`。fillna 用不合理值（例如把 missing covariate 填 0）→ `warn`。

### CODE-005 Adjustment 完整性
**Check:** 多變量 model 必須包含 `research_plan.covariates[*]` 中 `adjust=true` 的所有變項。
**Evidence:** script formula 字串（e.g. `'time ~ group + age + sex + stage'`）+ research_plan 的 covariates 列表。
**Severity map:** 遺漏 adjust=true 的 covariate → `block`。

### CODE-006 Model 診斷
**Check:**
- Cox model：必須檢查 PH assumption（Schoenfeld residuals，global + per-variable），**gate 門檻 p < 0.01 而非 0.05**，另有 **0.01–0.05 borderline band**（跨 rank/km 兩個 transform 取 min-p）：不 block，但不得寫成「未違反」、必須進 methodological_warnings、必須附 early/late split HR。違反時必須有宣告的 `ph_violation_remedy`，且 manuscript 前由 `ph_remedy_gate.py` 驗產物存在。`multivariate-interaction` 已內建（見該 skill 的 `ph_assumption_test` / `ph_gate`）；若被稽核的腳本是 Cox 但完全沒有 PH 檢定 → `warn`；有檢定但違反時無任何處置路徑 → `block`
- linear model：必須檢查 residual normality + heteroscedasticity
- logistic：必須檢查 Hosmer-Lemeshow 或 calibration
- 若 config 有 `skip_diagnostics=true` 則跳過此 check
**Evidence:** script 中診斷相關 API 呼叫。
**Severity map:** 完全無診斷 → `warn`（建議加上）；配合 config flag 則 `pass`。

### CODE-007 Subset / filter 一致性
**Check:** script 的 `df = df[df[...]]` filter 必須對應 `research_plan.population.filters[]` 的邏輯，不得額外加 undocumented filter。
**Evidence:** script 中所有 boolean indexing + research_plan filter。
**Severity map:** script 額外 filter 未在 plan → `block`（silent scope change）。

### CODE-008 P-value + CI 報告
**Check:**
- script 輸出必須含 point estimate、95% CI、p-value（全部三者）
- 多重比較若 > 5 次 regression 必須 adjust（Bonferroni、FDR、或 config 明確 `no_correction=true`）
**Evidence:** script 輸出格式 + config。
**Severity map:** 缺 CI 或 p-value → `warn`。未 adjust 多重比較 → `warn`。

### CODE-009 Seed / reproducibility
**Check:** 所有隨機性操作（bootstrap、imputation、PSM）必須 set seed。Seed 來自 config。
**Evidence:** script 中 `np.random.seed`、`random_state=`、`set.seed` 呼叫 + config。
**Severity map:** 無 seed → `block`。Seed hardcode → `warn`。

### CODE-010 Output 欄位完整性
**Check:** script 輸出檔必須含每個 regression term 的：term name、estimate、SE、CI_low、CI_high、p_value、n_events、n_total。
**Evidence:** script 產生 output CSV/Excel 的寫檔邏輯。
**Severity map:** 關鍵欄位缺 → `warn`。

### CODE-011 Skill 專屬約束

| Skill | 額外 check |
|---|---|
| `kaplan-meier` | 必須產生 log-rank p 和 median survival 95% CI |
| `competing-risk` | 必須用 Fine-Gray (subdistribution) 而非 naive cause-specific Cox |
| `univariate-forest` | 每個 covariate 單獨 fit，不得混合進 multi |
| `multivariate-interaction` | interaction term 正確指定（`*` vs `:`），且 main effects 都在 |
| `psm-matching` | matching 完成後必須 report SMD、輸出 balance diagnostics |
| `auc-cstat` | 必須 report 95% CI（DeLong 或 bootstrap），不只點估計 |
| `table1` | continuous 變項自動判斷 t-test vs Wilcoxon（根據 Shapiro）；類別用 chi-square 或 Fisher |

### CODE-012 Script 檔案內結構
**Check:**
- script 開頭有 docstring 說明用途
- 有 `if __name__ == '__main__':` entry point
- 所有 config 讀取集中在開頭
- `[QC_WARNING]` / `[QC_BLOCKING]` 的 stderr 寫入符合 research-plan convention
**Evidence:** script 前 50 行 + 結尾。
**Severity map:** missing QC stderr → `warn`。

### CODE-013 Diagnostic-config consistency
**Check:** 若 `{working_dir}/diagnostics/diagnostic_report.json` 或 `{working_dir}/diagnostic_report.json` 存在（由 `survival-diagnostics` skill 產生），downstream survival skill 的 config 必須反映 diagnostic 推薦。適用 skill：`kaplan-meier`、`competing-risk`、`univariate-forest`、`multivariate-interaction`。

| Diagnostic flag | Config 必須 | 違反則 |
|---|---|---|
| `checks.competing_risks.detected=true` + `recommended_primary="competing-risk"` | pipeline 含 competing-risk 或 KM 只當 sensitivity | KM-only pipeline → `block` |
| `checks.clustering.detected=true` + `recommendation` 提及 frailty/cluster | Cox config 含 `cluster_column` 或 `frailty` term（或 KM 有 stratification） | 缺 → `warn` |
| `checks.time_varying.detected=true` + `risk="high"` | script 使用 counting-process (start, stop] 格式 | 用標準 `Surv(time, event)` → `block` |
| `checks.left_truncation.detected=true` | `Surv()` 含 `entry` / `tstart` 欄位 | 缺 → `warn` |
| `checks.informative_censoring.detected=true` | manuscript limitation 欄位存在或 config 有 `sensitivity_analysis=true` | 缺 → `warn` |
| `research_plan.json$.diagnostics.mode="off"` | — | 跳過 CODE-013（user override） |

**Evidence:** `diagnostic_report.json` 中的 `checks.*` + `recommended_primary` + `pipeline_recommendations`；script formula / Surv() 呼叫；config 中的 `cluster_column`、`entry_column`、`sensitivity_analysis`。
**Severity map:** 見上表。若 `diagnostic_report.json` 不存在，此 check 回 `pass`（無 diagnostic baseline）。

### CODE-014 Schema canonical-form drift
**Check:** 任何在 script 中以 `==` 比較的 enum-like 字串值（`outcome["type"]`、`status`、`event_encoding`、`mode`、`distribution` 等），其 canonical 寫法必須在以下三個來源都一致：
1. Python script 內的 `== "..."` 字面值
2. `research_plan.json` schema / `plan_template.md` 的 schema 範本（例如頁首 JSON 範例的 `"type": "..."`）
3. `plan_template.md` 的 Field Reference 表格 / 範例 / 文字描述

若三者使用不同拼法（hyphen vs underscore、capitalize 差異、不同 alias），且 script 沒有 `_normalize_<field>()` helper 把 alias map 到 canonical，則屬 silent route 風險（user 照文件抄會 `==` match 不到 → 走 else 分支 → silent wrong analysis）。

**Evidence:**
- script 內所有 `outcome["type"] == "..."` / `status == "..."` 等比較行（含 file:line + literal value）
- `plan_template.md` / schema 中對應 field 的所有出現位置（grep `time_to_event\|time-to-event\|TimeToEvent` 等變形）
- 若有 normalize helper，記錄 helper 名稱 + 涵蓋的 alias 集合

**Severity map:**
- doc 跟 code 用不同 canonical 寫法、無 normalize helper、`==` exact match → `block`（silent mis-route）
- 有 normalize helper 但未涵蓋所有已知 alias → `warn`
- doc 自己內部不一致（schema 範本一個寫法、Field Reference 另一個寫法）但 code 唯一 → `warn`
- 全部一致 + normalize helper 對 unknown 值 raise → `pass`

**Real-world example（觸發本 check 的 incident）:** research-plan 的 `outcome["type"]`，plan_template.md Field Reference 用 `time-to-event` (hyphen)、generate_configs.py 用 `time_to_event` (underscore) 做 5 處 exact match → 使用者照 Field Reference 抄的 plan 永遠 route 到 logistic 而非 Cox。修法為加 `_normalize_outcome_type()` 接受兩種拼法 + raise unknown，並把 plan_template.md 的 hyphen 統一改 underscore（2026-05-08 codex audit Tier 2 commit A）。

## Output Format

與 Role 1 同格式，`role` 改 `code`，`check_id` 前綴 `CODE-`：

```json
{
  "role": "code",
  "skill": "univariate-forest",
  "step_id": "uni_os",
  "status": "block",
  "issues": [
    {
      "role": "code",
      "skill": "univariate-forest",
      "step_id": "uni_os",
      "check_id": "CODE-001",
      "severity": "block",
      "message": "script 用 logistic regression，但 outcome 是 time-to-event（有 follow_up_years 欄位）。應改用 Cox。",
      "evidence": [
        {"type": "script_file", "pointer": "${CLAUDE_SKILL_DIR}/../univariate-forest/scripts/univariate_forest.py:142", "excerpt": "model = sm.Logit(y, X).fit()"},
        {"type": "config_file", "pointer": "uni_os_config.json$.outcome.type", "value": "time-to-event"}
      ],
      "suggestion": "script line 142 改為 `CoxPHFitter().fit(df, duration_col=..., event_col=...)`",
      "confidence": 0.98
    }
  ],
  "summary": "Role 2 block：統計方法錯配（logistic vs time-to-event）。建議改用 Cox。",
  "completed_at": "2026-04-16T08:01:00+00:00"
}
```

## What Role 2 Does NOT Do

- 不檢查欄位本身對不對（那是 Role 1）
- 不看執行結果（那是 Role 3）
- 不動手改 script；只提 suggestion

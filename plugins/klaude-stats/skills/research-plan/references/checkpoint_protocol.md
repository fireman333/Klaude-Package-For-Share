# Checkpoint Protocol

Defines the adaptive checkpoint behavior for the biostatistics pipeline.
Adapted from academic-pipeline's orchestrator checkpoint system + agentic-data-scientist's Criteria Checker and Stage Reflector.

---

## Checkpoint Types

### Type Determination Rules

由 `run_pipeline.py` 的 `resolve_checkpoint_type()` **實作**，依序判定：

```
MANDATORY（群組本身就標了）      → MANDATORY，不可降級
consecutive_continue_count < 3   → FULL
random() < 0.25                  → FULL（隨機抽查，checkpoint 會記 spot_check: true）
其餘                             → SLIM
```

群組的基礎型別：

| 群組 | 基礎型別 | 備註 |
|---|---|---|
| `foundation` | **MANDATORY** | 固定 |
| `outcome_{id}` | FULL | primary outcome 同時有 MI 與 PSM 時升級 MANDATORY 並強制停 |
| `supplementary` | FULL + `synthesis` | 本次沒排到 pre-manuscript 閘門時**升級成 MANDATORY** |
| `manuscript` | **MANDATORY** + `pre_checkpoint` | **在群組執行之前**觸發，不是之後 |

### ⚠ 三種型別「停不停」不一樣

| 型別 | 會停嗎 |
|---|---|
| MANDATORY / FULL | **會。** 寫 `pipeline_state = "awaiting_review"`、存檔、印橫幅、**結束程序** |
| SLIM | **不會。** 印一行就繼續跑下一組，並自己在 `checkpoints[]` 記 `"decision": "continue"`（因為沒有人被問過） |
| manuscript 的 pre_checkpoint | 有 blocker → **兩種模式都停**；沒 blocker → 只有 `--hitl` 停 |

**整個群組後 checkpoint 機制只在 `--hitl` 下才會走到**（auto 模式只有 pre-manuscript briefing 與有 blocker 時會停）。

### 停下來的方式不是問答

腳本**不讀 stdin**。FULL / MANDATORY 的「暫停」＝把狀態存檔後結束程序；使用者的「回答」＝**再跑一次同一個指令**，下次啟動時由 `record_resume_decision()` 把它記成 `continue`（或在有 blocker 時記成 `blocked`）。所以文件裡的「Options: 1) Continue …」是**給 Claude 呈現給人看的選單**，不是腳本會解析的輸入。

### SLIM Checkpoint

```
  [✓] {group_id} complete ({n_steps} steps, {duration}s) → continuing [SLIM, {n} consecutive continues]
```

**連續 3 次 continue 之後就不再停了。** 這是刻意的（減少 checkpoint 疲勞），但對使用者的體感是「pipeline 開始一路跑到底」——**要對他講清楚**，不要宣稱「每組都會停下來確認」。要恢復每組都停，中間穿插一次 `review` 把 `consecutive_continue_count` 歸零。約 25% 的 SLIM 會被隨機抽回 FULL 以防自動化怠惰。

---

## Checkpoint Templates

### MANDATORY Checkpoint (Foundation Group)

```
━━━ Foundation Group Complete ━━━

Cohort:
  Total: N={total}
  {group_a_label}: n={n_a} ({pct_a}%)
  {group_b_label}: n={n_b} ({pct_b}%)
  Exclusions: {n_excluded} patients excluded in {n_steps} steps

Outputs:
  ✓ Flowchart.xlsx + Flowchart.png  [{figure_num}]
  ✓ Table1.xlsx                     [{table_num}]

Statistical QC:
  {qc_warnings or "None"}

━━━ Stage Reflection ━━━
{reflection_content — see Stage Reflector section below}

Next: {outcome_name} survival analyses (KM + competing risk + regression)
Options:
  1) Continue to {outcome_name} analyses
  2) Review outputs in detail
  3) Modify plan (change covariates, outcomes, exclusion criteria)
  4) Pause pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### MANDATORY Checkpoint (Pre-Manuscript)

```
━━━ All Analyses Complete — Ready for Manuscript ━━━

Pipeline: [✓]flowchart → [✓]table1 → [✓]km → [✓]cr → [✓]uni → [✓]multi → [✓]psm → [✓]auc → [○]manuscript

Summary of Key Findings:
  Primary outcome ({outcome_name}):
    KM: median survival {x} vs {y} {time_unit}, log-rank p={p}
    Univariate: HR={hr} [{ci_lo}-{ci_hi}], p={p}
    Multivariate: aHR={ahr} [{ci_lo}-{ci_hi}], p={p}

Statistical QC (all steps):
  Blocking issues: {n_blocking or "None"}
  Warnings: {n_warnings or "None"}

Output files: {n_files} files ({n_xlsx} Excel, {n_png} figures)

Options:
  1) Generate manuscript Results section
  2) Review specific analysis outputs
  3) Re-run specific steps with different settings
  4) Pause — review all outputs before generating manuscript
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### FULL Checkpoint (Per-Outcome Group)

```
━━━ {Outcome Name} Analyses Complete ━━━

Results:
  KM: median survival {x} vs {y}, log-rank p={p}
  Univariate: HR={hr} [{ci_lo}-{ci_hi}], p={p}
  Multivariate: aHR={ahr} [{ci_lo}-{ci_hi}], p={p}
  {competing_risk_line if enabled}

Outputs: {file_list with Figure/Table numbers}
Statistical QC: {warnings or "None"}
Next: {next_group_description}

Options: 1) Continue  2) Review  3) Modify  4) Pause
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### SLIM Checkpoint

```
[✓] {group_name} complete ({n_steps} steps, {duration}s) → continuing to {next_group}...
```

---

## Stage Reflector

**實作位置：`scripts/precheck_configs.py` 的 `check_stage_reflector()`。** 2026-08-12 之前這一節描述的是一個**不存在的機制**——`grep -rn "Reflector" scripts/` 零命中，整張規則表只有文件、沒有任何程式執行它。現在它是 precheck 的一部分，跟著 `--stage pre` 與 `--stage post` 一起跑。

> **這代表兩件事跟以前不一樣**：① 它**不再只在 Foundation checkpoint 觸發**，而是每次跑 precheck 都算一次；② 它算的是**資料**（套用 population filter 之後的 DataFrame），不是「讀 Table1.xlsx 與 Flowchart 的輸出」——所以在任何 step 跑之前就有結果。

### Reflector Rules（以程式為準）

全部是 `report.warn()`，**一條都不擋**。

| 警告 ID | 觸發條件 | 訊息內容 |
|---|---|---|
| `REFLECT-epv` | 該 outcome 的 **EPV < 10** | rule of 10 允許約 `effective_events // 10` 個參數，模型實際配了 `n_fitted_params` 個 |
| `REFLECT-small-n` | 最小組 **n < 30** | 明講「這**只是精確度的觀察**；共變項預算由 EPV 管，見 RES-006」 |
| `REFLECT-imbalance` | `max(組人數) / min(組人數) > 5` | 考慮 PSM 或 IPW |
| `REFLECT-events` | 任一組事件數 **< 5** | 考慮捨棄該 outcome 或併成複合終點 |
| （只進 suggestions，不發獨立警告） | 共變項缺失 **> 50%** | 要理由 + sensitivity，**不自動移除**（MAR 成立時 MI 處理得了——Madley-Dowd 2019） |
| （同上） | 共變項缺失 **> 20%** | 從共變項移除或插補 |
| `REFLECT`（info） | 沒有任何建議 | `no adjustments suggested` |

> ### 原本第一列是個 bug，現在拆成兩條
>
> 舊表寫「**Any group n < 30** → 依 rule of 10（`min(events) / 10`）減共變項」。**條件用 n、公式用 events，兩者不同調**：一個 n=25 但事件很多的組不需要減共變項，一個 n=500 但只有 8 個事件的組非減不可，而舊規則兩個都判錯。
>
> 修法是拆開：**`REFLECT-epv` 用 EPV 觸發**（那才是共變項預算的正確判準），**`REFLECT-small-n` 保留 n<30 但降格成獨立的精確度觀察**。資訊沒有丟，只是不再用錯的條件去驅動錯的公式。

### Reflector Input

`check_stage_reflector(report, plan, df_filtered, epv_results)`：
1. `df_filtered` —— 套過 `population.filters` 的資料
2. `epv_results` —— 由 RES-006 先算好的每個 outcome 的 EPV
3. 分組來自 `grouping`，事件數由 `events_by_group()` 算

### Reflector Output Format

腳本這一端只有 stderr 的 `[QC_WARNING] REFLECT-*` 行，以及 `precheck_report.json$.reflector_suggestions` 裡的建議清單。**下面這個選單是 Claude 呈現給人看的格式，不是腳本印的：**

### Reflector Output Format

```
━━━ Stage Reflection ━━━
Observations:
  - {observation_1}
  - {observation_2}

Auto-suggestions:
  ⚠ {suggestion_1}
    → {recommended_action_1}
  ⚠ {suggestion_2}
    → {recommended_action_2}
  ✓ {positive_observation}

Apply suggestions? [1] Accept all  [2] Review individually  [3] Skip
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Reflector Behavior

**程式負責**：計算五條規則、發 `[QC_WARNING] REFLECT-*`、把建議寫進 `precheck_report.json$.reflector_suggestions`。

**Claude 負責（沒有程式強制）**：
- 把警告**翻成對使用者的具體建議並詢問**——腳本只會印，不會問，也不會等
- 使用者接受 → 改 `research_plan.json` 的 covariates / outcomes → 重產受影響的 config
- 使用者跳過 → 照原計畫走（警告在後續每次 precheck 仍會再出現）
- **回填 `checkpoints[].reflection_applied`**。⚠ **`run_pipeline.py` 寫 checkpoint 時一律把它填 `False`**，它是留給 Claude 在真的採納建議後自己改的。**看到 `false` 不代表沒有建議，只代表沒有人記錄有沒有照做。**

不變的紀律：
- **只建議，絕不自動改**
- 基於客觀統計判準，不是主觀判斷
- **這些是事前指定的方法學防護**（EPV 限制、避免不收斂），應該一開始就寫進 SAP，**不是**看到結果才驅動的改動
- **絕不可以建議更動主要結局或暴露定義**——只能動模型設定（共變項、插補策略）

---

## Statistical QC Gates (Dual-Layer)

### Blocking (step marked `error`; dependents become `blocked`, the rest of the pipeline continues)

| Check | Condition | Applies To |
|-------|-----------|-----------|
| Zero events | 0 events in any group | KM, CR, Uni, Multi |
| Convergence failure | Model did not converge | Uni, Multi, PSM, AUC |
| Invalid estimate | HR/OR = Inf, NaN, or ≤ 0 | Uni, Multi |
| **PH 違反且未宣告 remedy** | Schoenfeld 全域檢定 **p < 0.01**（`PH_ALPHA`，rank transform）**且** plan 的 `outcomes[<id>].ph_violation_remedy` 沒填 | Multi（Cox） |

### Warning (informational, does not block)

| Check | Condition | Applies To |
|-------|-----------|-----------|
| Small sample | n < 30 in any group (note: events per group is a better metric for survival analysis) | All |
| Extreme estimate | HR/OR > 10 or CI width > 100 | Uni, Multi |
| Moderate extreme estimate | HR/OR > 5 | Uni, Multi |
| High missing | > 20% missing for any variable | Table1, Uni, Multi |
| Very high missing | > 50% missing — requires sensitivity analysis justification, not auto-removal | Table1, Uni, Multi |
| **PH borderline** | `0.01 <= p < 0.05`（`PH_ALPHA_REVIEW`，取 rank 與 km 兩種 transform 裡最極端的 p） | Multi (Cox) |
| **PH 違反但已宣告 remedy** | p < 0.01 且 `ph_violation_remedy` 有填 —— 見下方 remedy 表，四個值的警告內容不同 | Multi (Cox) |
| Low event rate | Events < 10 in any group | KM, CR, Uni, Multi |

#### PH 的兩個門檻為什麼是 0.01 與 0.05

`PH_ALPHA = 0.01` 是**自動硬閘門**，刻意不用 0.05：在 n≈6000 時 0.05 會被臨床上無關緊要的偏離觸發，**一個老是為了瑣事亮紅燈的閘門，只會訓練使用者養成無腦 override 的習慣**。`PH_ALPHA_REVIEW = 0.05` 是 borderline 帶的外緣：在 n≈500 時一個真實而且臨床上很大的早期效應（HR 0.5 → 1.0）有相當比例會落在 0.01–0.05，扔掉它太浪費。

**兩個門檻的分工**：0.01 以下 = 程式擋；0.01–0.05 = 程式**不擋但發 warning**，由人表態。

> **borderline 不得沉默通過。** manifest 有 PH-borderline warning 時，reviewer challenge 的 domain 5 必須逐條表態（`dismiss` 並寫理由，或 `escalate`）——見 `reviewer_challenge.md` §2。

#### 四個 `ph_violation_remedy` 的實際行為

宣告在 **`outcomes[<id>].ph_violation_remedy`**（不是計畫頂層）。四個合法值，**沒有一個由這個 step 執行**——remedy 一律是自己的 step、自己的表，這樣本 workbook 的 Sheet 1 與 Sheet 2 才會是同一套假設配適的（2026-08-12 裁決，爭議五）：

| remedy | 這個 step 會做什麼 | 你還要做什麼 |
|---|---|---|
| `disclose` | 發 warning：調整後的 HR 是整段追蹤的平均，**必須寫進 Limitations 並綁一個 `ph_disclose_decision_id`** | 填那個 decision-log ID。**沒填的話 manuscript 階段的 artifact gate 會擋** |
| `stratify` | 發 warning：本 step 不執行 remedy | 通常什麼都不用做——**pipeline 自動補 `ph_stratified_<outcome>`**。要事前點名分層變項才填 `ph_strata_variables` |
| `time_varying` | 同上 | **pipeline 自動補 `ph_time_varying_<outcome>`**，但要填 **`tv_cut_points`**（時間窗切點），否則 manuscript gate 會擋 |
| `rmst` | 同上 | **pipeline 自動補 `ph_rmst_<outcome>`**，但要填 **`rmst_tau`** 或 **`rmst_tau_rule`**，否則 manuscript gate 會擋 |

三個 remedy step 都需要 `plan_schema_version: 2`。**四個值的 Sheet 1 HR 都是未經處置的**，在該 remedy 的分析真的跑出來之前**不可以當成主要估計呈現**。manuscript 階段的 artifact gate（`ph_remedy_gate.py`）會檢查產物在不在，有 evidence sidecar 的還會驗內容（處置有沒有對應到真正發生的違反；時間窗 / tau 是不是來自 plan）。

> **照實對使用者講**：三個 remedy 現在真的會被跑，但產出的是**另一張表**，主表仍未處置——不要說成「主表的 HR 已經修好了」。`tv_cut_points` / `rmst_tau` 沒填時分析照跑、表照出，擋的是 manuscript gate；要講清楚是「這個數字還不能投稿，因為時間窗 / tau 沒有事前寫進計畫」，不是「跑失敗了」。`rmst` 另外要講它是**未校正**的。

### Per-Step Success Criteria Schema

Each pipeline step defines `success_criteria` in the plan JSON:

```json
{
  "id": "uni_primary",
  "skill": "univariate-forest",
  "status": "pending",
  "success_criteria": [
    {"check": "events_per_group >= 1", "severity": "blocking"},
    {"check": "model_converged == true", "severity": "blocking"},
    {"check": "hr_is_finite == true", "severity": "blocking"},
    {"check": "sample_size >= 30", "severity": "warning"},
    {"check": "ci_width < 100", "severity": "warning"}
  ]
}
```

**`check` 是一套會被真的求值的迷你 DSL，不是註解。** 文法、可用的 metric 名、以及求不出值時會怎樣，全部定義在 `plan_template.md` 的〈`success_criteria` 的文法〉一節；求值器在 `precheck_configs.py` 的 `evaluate_criterion()`，由 RES-004 驅動。

**寫錯的代價比不寫還大**：一個永遠求不出值的 criterion 在計畫裡**看起來像一個保證，實際上什麼都沒有強制**——所以無法解析的 criterion 在 **pre 與 post 兩個階段都是 blocking**。

Scripts emit QC results to stderr with `[QC_WARNING]` or `[QC_BLOCKING]` prefixes.
`run_pipeline.py` parses these and stores in `step.qc_warnings`.

---

## Checkpoint Decision Semantics

| User Input | Action |
|-----------|--------|
| `continue` / `yes` / `1` | Proceed to next group, increment `consecutive_continue_count` |
| `review` / `2` | Display output files for user inspection, do NOT increment continue count |
| `modify` / `3` | Enter plan modification mode (change covariates, outcomes, etc.) |
| `pause` / `4` | Set `pipeline_state = "paused"`, save state |
| `skip {step_id}` | Mark specific step as `skipped` |

---

## Results Interpretation Prompts (opt-in)

At MANDATORY checkpoints, offer brief statistical interpretation after presenting results:

```
Would you like me to interpret these results? [y/n]
```

If yes, provide concise clinical interpretation:
- Primary outcome effect direction and magnitude
- Consistency between univariate and multivariate results
- Whether baseline differences (from Table 1) may confound results
- Whether PSM or additional adjustment is recommended

This is NOT mandatory. User can always skip. Maximum 3-4 sentences per interpretation.

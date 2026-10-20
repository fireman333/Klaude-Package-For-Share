# Research Plan JSON Schema Reference

> **`plan_schema_version: 2` 是凍結的。** 本文件以 `scripts/generate_configs.py`（以及指紋部分的 `scripts/reviewer_challenge.py`）的實作為準。有出入時**以程式為準**，並回報本文件哪裡過時。
>
> **宣告的位置本身就是強制手段。** 有幾個欄位（最典型是 `outcomes[].ph_violation_remedy`）**只在特定位置被讀取**，寫在計畫頂層會被靜默忽略——這不是實作偷懶，而是刻意的：進計畫指紋的是 `outcomes`，寫在那裡的宣告事後補填會讓 reviewer challenge 作廢，這正是「事前指定」可以被檢查的原因。位置對不對，決定的是這個宣告有沒有可稽核性。

## 版本與遷移

| 情況 | 行為 |
|---|---|
| `plan_schema_version` 是 `> 2` 的整數 | **到處 fail closed。** `generate_configs.py` 直接 `[FATAL]` 拒跑；`--migrate` 也拒絕（那會是降級） |
| `== 2` | 全功能：自動補 step 真的寫進計畫、`diagnostics.data_fingerprint` 缺席升級為 FATAL |
| `< 2`、缺席、或不是整數 | **仍然可以跑**，但自動補 step 只印預覽（在暫存副本上算，不動計畫），且缺 `data_fingerprint` 只降級成警告 |

升版走 `generate_configs.py <plan> --migrate`。它**只寫指紋中性的欄位**（`plan_schema_version`、`covariate_provenance` 的空格），刻意不替你填 `pipeline_profile` / `model_purpose` / `estimand_type` / `multiplicity`——那四個進指紋或屬於決策，程式替你猜一個等於偽造一份事前指定。

## Complete Schema

```jsonc
{
  "plan_schema_version": 2,          // int。> 2 到處 fail closed
  "version": 1,                      // 人工版本號，供 reviewer_challenge_v{version}.json 命名
  "pipeline_profile": "submit",      // explore | submit。缺席 == "submit"。⚠ 進指紋
  "auto_steps_enabled": true,        // false = 永久拒絕自動補 step
  "estimand_type": "causal",         // causal | associational。缺席 == 未指定。⚠ 進指紋（有寫才進）
  "model_purpose": "etiologic",      // prediction | etiologic。⚠ 以 _decisions 形式進指紋
  "decision_log": "report/decision_log.md",   // 選填，預設 <output_dir>/decision_log.md
  "covariate_provenance": {"age": "DAG 事前指定"},   // {column: why}
  "covariates_selection_rule": "全部依 2019 年 ESC guideline 的 confounder 清單",
  "study": {
    "title": "string — research title",
    "design": "cohort | case-control | cross-sectional | rct",
    "data_file": "/absolute/path/to/data.xlsx",
    "data_dictionary": "/absolute/path/to/Data_Dictionary.csv (optional)",
    "cluster_column": null,
    // 下面四個也可以寫在 study 底下，且 study 優先於頂層同名鍵
    "pipeline_profile": null, "estimand_type": null, "model_purpose": null
  },
  "population": {
    "filters": [
      {"column": "col_name", "operator": "==|!=|>|>=|<|<=|in|not_in", "value": "number|string|array"}
    ],
    "exclusion_steps": [
      {
        "description": "Human-readable label for flowchart",
        "condition": "pandas query expression to EXCLUDE (e.g., 'age < 20')",
        "keep_condition": "pandas query expression to KEEP (alternative to condition)"
      }
    ]
  },
  "grouping": {
    "column": "col_name",
    "groups": [
      {"value": 1.0, "label": "Group A"},
      {"value": 0.0, "label": "Group B"}
    ]
  },
  "outcomes": {
    "primary": {
      "id": "primary",
      "name": "MACE",
      "type": "time_to_event | competing_risk | binary",
      "description": "CV death or HF hospitalization",
      "time_column": "time_col (required if time_to_event)",
      "event_column": "event_col",
      "competing_event_column": "competing_col (optional)",
      "competing_event_labels": {"1": "Primary event", "2": "Competing event"},
      "time_unit": "days | months | years",
      "time_scale": 365.25,
      "time_points": [1, 3, 5],

      // ---- v2 欄位 ----
      "hypothesis_family": "primary",        // 自由字串。缺席時 primary 取 "primary"，secondary 取 null
      "analysis_intent": "confirmatory",     // confirmatory | exploratory | unknown
                                             //   缺席：primary → "confirmatory"，secondary → "unknown"
      "n_events": 308,                       // fitted analysis set 的**總** events（不是較小那組的）
      "ph_violation_remedy": "disclose",     // stratify | time_varying | rmst | disclose
      "ph_disclose_decision_id": "D-021"     // remedy 是 disclose 時要填
    },
    "secondary": [
      {
        "id": "secondary_1",
        "name": "All-cause mortality",
        "type": "time_to_event",
        "time_column": "time_death",
        "event_column": "event_death",
        "time_unit": "years",
        "time_scale": 365.25,
        "time_points": [1, 3, 5],
        "analysis_intent": "unknown"         // 沒寫就是 unknown。**絕不替 secondary 猜 confirmatory**
      }
    ]
  },
  "multiplicity": {
    // outcomes[] 沒寫時的後備宣告位置；兩邊都有時 outcomes[] 優先
    "outcomes": {"secondary_1": {"hypothesis_family": null, "analysis_intent": "exploratory"}}
  },
  "covariates": [
    {
      "name": "Age",
      "column": "age",
      "type": "continuous",
      "scale": 10,
      "scale_label": "per 10 years",
      "selection_basis": "dag_prespecified",        // ⚠ 進指紋（見下）
      "selection_rationale": "自由文字，**不進指紋**"
    },
    {
      "name": "Male sex",
      "column": "gender",
      "type": "binary",
      "reference": 0
    },
    {
      "name": "NYHA class",
      "column": "NYHA_Dis",
      "type": "ordinal",
      "label_map": {"1.0": "I", "2.0": "II", "3.0": "III", "4.0": "IV"}
    }
  ],
  "derived_variables": [
    {
      "name": "BMI",
      "type": "expression",
      "expression": "BW_Dis / (Height_Dis / 100) ** 2",
      "dependencies": ["BW_Dis", "Height_Dis"]
    },
    {
      "name": "SBP",
      "type": "coalesce",
      "columns": ["SBP_Ad", "SBP_opd"]
    }
  ],
  "analyses": {
    "psm_enabled": true,
    "competing_risk_enabled": true,
    "auc_enabled": true,
    "auc": {"bootstrap_n": 2000, "seed": 42,
            "clinical_model_columns": []}   // 空 = 每個共變項各自報 discrimination
  },
  "missing_data": {
    "strategy": "assess_only | mi_sensitivity | mi_primary",
    "auxiliary_variables": [],
    "m": null,
    "seed": 42,
    "maxit": 20,
    "method_overrides": {},
    "primary_analysis": "complete_case | mi"
  },
  "advanced_analyses": {
    "nonlinearity":    {"enabled": false, "variables": [], "knots": 4,
                        "knot_percentiles": null, "reference": null},
    "robust_variance": {"enabled": false, "cluster_column": null,
                        // ⚠ "mixed" 已於 2026-08-11 撤除 —— 給它會直接 ValueError，不是警告
                        "method": "cluster_robust | gee",
                        "correlation_structure": "exchangeable",
                        "within_cluster_time_column": null,
                        "compare_to_naive": true},
    "calibration":     {"enabled": false, "eval_times": [], "bootstrap_n": 500,   // 200 = 協議下限與快速模式，輸出會標記
                        "study_purpose": "etiologic | prediction"},
    "weighting":       {"enabled": false, "method": "iptw | overlap",
                        "stabilized": true,
                        "trim": {"enabled": false, "percentile": [1, 99]}},
    "immortal_time":   {"enabled": false, "mode": "landmark | extended_cox",
                        "exposure_time_column": null, "landmark_times": []},
    "evalue":          {"enabled": false, "reference_confounders": [],
                        // 預設 <output_dir>/Multi_{outcome_id}.xlsx；相對路徑對 output_dir 解析
                        "source_file": null,
                        "source_sheet": "Multivariate Analysis"},
    "strobe":          {"enabled": false},
    // Step 6.7 的閘門。aggregate_file 不填就是 <output_dir>/reviewer_challenge_v{version}.json。
    // 有 manuscript 步驟就一定要有 reviewer-challenge 步驟，否則 generate_configs 會 FATAL。
    "reviewer_challenge": {"aggregate_file": null}
  },
  "pipeline": [
    {
      "id": "flowchart",
      "skill": "flowchart",
      "status": "pending",
      "depends_on": [],
      "output_file": "Flowchart",
      "skip_reason": null,        // 唯一有意義的值是 "profile"（explore 停放）；見下
      "model_purpose": null       // 最窄的 model_purpose 宣告位置，會蓋過 study / 頂層
    },
    {
      "id": "table1",
      "skill": "table1",
      "status": "pending",
      "depends_on": [],
      "output_file": "Table1"
    },
    {
      "id": "km_primary",
      "skill": "kaplan-meier",
      "status": "pending",
      "depends_on": [],
      "outcome": "primary",
      "output_file": "KM_primary"
    },
    // 有 manuscript 就必須有這一對，且 manuscript 要（傳遞）依賴 gate。
    {
      "id": "reviewer_challenge",
      "skill": "reviewer-challenge",
      "status": "pending",
      "depends_on": ["km_primary"]
    },
    {
      "id": "manuscript",
      "skill": "manuscript-results",
      "status": "pending",
      "depends_on": ["reviewer_challenge"]
    }
  ],
  "output_dir": "/absolute/path/to/output/",
  "table_figure_mapping": {
    "flowchart": "Figure 1",
    "table1": "Table 1",
    "km_primary": "Figure 2"
  },
  "abbreviations": "AF = atrial fibrillation; BMI = body mass index; ...",

  // === v2.0 New Fields (Pipeline Optimization) ===

  "pipeline_mode": "auto | hitl",
  "pipeline_state": "planning | running | awaiting_review | paused | feedback | completed",
  "consecutive_continue_count": 0,

  "guardian": {
    // Biostats Guardian QA layer (see ${CLAUDE_SKILL_DIR}/../biostats-guardian/SKILL.md).
    // Default: omit → "quick" for auto mode, "standard" for hitl mode.
    "mode": "off | quick | standard | full",
    "disabled_roles": [],            // e.g. ["code"] to skip Role 2
    "block_on_warn": false,          // if true, warn-level issues also pause the pipeline
    "max_parallel": 6                // hint only; Anthropic API enforces actual concurrency
  },

  // 由 run_pipeline.py 寫入。兩種形狀（before_group / after_group），欄位不完全一樣
  "checkpoints": [
    {
      "group": "manuscript", "group_id": "manuscript",
      "type": "MANDATORY", "checkpoint_type": "MANDATORY",
      "position": "before_group",          // ← manuscript 的 checkpoint 在群組**之前**
      "decision": null,                    // 停下來時是 null，之後由 record_resume_decision 改寫
      "reflection_applied": false,         // ⚠ 腳本一律寫 false；要 Claude 自己回填
      "blockers": ["…"],                   // 只有 before_group 有這個鍵
      "timestamp": "2026-04-02T14:30:00",
      "steps_completed": []
    },
    {
      "group": "outcome_primary", "group_id": "outcome_primary",
      "type": "FULL", "checkpoint_type": "FULL",
      "position": "after_group",
      "decision": "continue",              // SLIM 會自己填 continue（沒有人被問過）
      "reflection_applied": false,
      "timestamp": "2026-04-02T14:35:00",
      "steps_completed": ["km_primary", "uni_primary", "multi_primary"],
      "spot_check": true                   // 只有被 25% 隨機抽回 FULL 時才出現
    }
  ],

  // 由 generate_configs.py 讀。mode: "completed" 時四個欄位必填，逐項驗
  "diagnostics": {
    "mode": "completed",                 // completed | off
                                         //   alias → completed: on / done / ran / complete
                                         //   alias → off:       not_applicable / "n/a"
                                         //   其餘（not_run / pending …）一律 FATAL
    "report_path": "diagnostics/diagnostic_report.json",  // completed 必填，須存在於磁碟
    "completed_at": "2026-08-11T09:00:00",                // completed 必填，須晚於資料檔 mtime
    "data_fingerprint": "3f2a91c47b0e15d8",               // study.data_file 的 sha256[:16]
                                                          //   schema v2 缺席 = FATAL
    "flags_detected": ["clustering"],    // 三種形狀都收，見下
    "reason": "本研究無 time-to-event 分析",   // 僅 mode:"off"，>= 10 字元
    "overrides": {
      "clustering": {
        "decision_id": "D-017",          // 須 fullmatch #\d+ 或 Xxx-yyy，且**存在於 decision_log.md**
        "reason": "單一中心，群集僅為採檢批次",
        "outcomes": ["primary", "secondary_1"]   // 須涵蓋每個被建模的 outcome
      }
    }
  },

  // 覆寫 manuscript 的抽取來源清單。給了就**取代**由 pipeline 推導的那份，並記一條 method warning
  "manuscript": {
    "analysis_files": [
      {"type": "multivariate", "path": "Multi_primary.xlsx"}   // type 與 path 都必填
    ]
  },

  "version_history": [
    {"version": 1, "created_at": "2026-04-01T10:00:00", "reason": "initial"}
  ],

  "feedback_rounds": [
    {
      "round": 1,
      "version_transition": "1→2",
      "changes": 3,
      "affected_steps": 8,
      "feedback_file": "advisor_feedback_v1.docx",
      "timestamp": "2026-04-02T14:30:00"
    }
  ],
  "max_feedback_rounds": 3,
  "total_steps_executed": 0,
  "max_total_steps": 80
}
```

## Pipeline Step Schema (v2.0)

Each step in the `pipeline` array has these fields:

```json
{
  "id": "uni_primary",
  "skill": "univariate-forest",
  "status": "pending",
  "depends_on": [],
  "outcome": "primary",
  "output_file": "Uni_primary",
  "started_at": null,
  "completed_at": null,
  "runtime_seconds": null,
  "retry_count": 0,
  "qc_warnings": [],
  "success_criteria": [
    {"check": "events_per_group >= 1", "severity": "blocking"},
    {"check": "model_converged == true", "severity": "blocking"},
    {"check": "hr_is_finite == true", "severity": "blocking"},
    {"check": "sample_size >= 30", "severity": "warning"},
    {"check": "ci_width < 100", "severity": "warning"}
  ]
}
```

### New fields (v2.0):
- `started_at` — ISO timestamp when step execution began (null if not started)
- `completed_at` — ISO timestamp when step execution finished (null if not finished)
- `retry_count` — number of retry attempts (max 1)
- `qc_warnings` — array of QC warning strings collected from script stderr
- `success_criteria` — array of checks with severity (`blocking` or `warning`)

### Default Success Criteria by Skill

| Skill | Blocking Criteria | Warning Criteria |
|-------|------------------|-----------------|
| flowchart | final_n > 0 | — |
| table1 | groups_have_data | cell_count >= 5 |
| kaplan-meier | events_per_group >= 5 | events_per_group >= 10, sample_size >= 30 |
| competing-risk | events_per_group >= 5 | events_per_group >= 10, sample_size >= 30 |
| univariate-forest | events_per_group >= 1, model_converged, hr_is_finite | sample_size >= 30, ci_width < 100, events_per_group >= 10 |
| multivariate-interaction | events_per_group >= 1, model_converged, hr_is_finite | sample_size >= 30, ci_width < 100, events_per_group >= 10 |
| psm-matching | matched_pairs > 0, model_converged | smd_max < 0.1 |
| auc-cstat | events >= 20, model_converged | events >= 50, sample_size >= 30 |
| manuscript-results | input_files_exist | — |

> 這些預設值全部只用上面那張表裡的合法 metric。**自己加條件時先對照那張表**——寫一個不存在的 metric 名不會有人幫你發現拼錯了，它會在 pre 階段被記成 `unknown`（info），到 post 階段才變成 blocking。
>
> 另外注意 `model_converged` / `hr_is_finite` / `ci_width` / `matched_pairs` / `smd_max` / `input_files_exist` **都是 post-only**：在 pre 階段它們一律是 `unknown`，那是正常的，不是設定錯了。

## `success_criteria` 的文法 ★ 它會被真的求值

求值器：`precheck_configs.py` 的 `evaluate_criterion()`，由 RES-004（`check_success_criteria()`）驅動，pre 與 post 兩個階段都跑。**刻意不是 `eval()` / `exec()`**：文法只有一個比較式、運算子是固定白名單、每個字面量都過 `ast.literal_eval`。

### 只有兩種合法形狀

```
<metric> <op> <literal>      events_per_group >= 5
<metric> <op> <metric>       events >= final_n
<metric>                     model_converged        ← 裸 metric，取布林真值
```

- **左邊一定是裸的 metric 名**（`[A-Za-z_][A-Za-z0-9_]*`）。不可以是字面量、算式、函式呼叫或括號。
- **運算子只有六個**：`>=` `<=` `==` `!=` `>` `<`。**沒有 `in`，沒有連鎖比較。**
- **右邊**：`true` / `false`（不分大小寫）、`null` / `none` → `None`、任何 `ast.literal_eval` 吃得下的字面量（數字、字串、list、dict），**或另一個 metric 名**。
- **沒有 `and` / `or` / `not`。** `smd_max < 0.1 and matched_pairs >= 50` **不是**兩個條件，而是一個**無法解析**的 criterion——要兩個條件就寫成兩列。

### 可用的 metric（權威清單）

`build_metrics()` 建立的命名空間就是全部；**其他名字一律當成 unknown**。

| Metric | 型別 | 何時算得出來 | 意思 |
|---|---|---|---|
| `sample_size` | int | 一直有 | 該 step 的分析人數 |
| `final_n` | int | 一直有 | flowchart 的最終 N（pre 階段用篩選後列數代替） |
| `events` | int | 有可解析的 outcome 時 | 各組事件數**總和** |
| `events_per_group` | int | 同上 | 各組事件數的**最小值** |
| `epv` | float | 該 outcome 算得出 EPV 時 | events per fitted parameter |
| `groups_have_data` | bool | 有分組時 | 每一組都 > 0 人 |
| `cell_count` | int | 有分組時 | 最小組的人數 |
| `input_files_exist` | bool | **post only** | 該 step 的輸出路徑存在 |
| `hr_is_finite` | bool | **post only** | 所有效應量與 CI 上界都是有限數 |
| `ci_width` | float | **post only** | 最寬的 CI 寬度 |
| `matched_pairs` | int | **post only** | 輸出裡最小的 N |
| `smd_max` | float | **post only** | 配對後最大的 SMD |
| `model_converged` | bool | **post only** | `qc_warnings` 裡沒有 converg / singular 字樣 |

### 求不出值時會怎樣 —— 三種結果，沒有一種是「當作通過」

| 結果 | 條件 | 行為 |
|---|---|---|
| `pass` | 求值為真 | 計數，不輸出 |
| `fail` | 求值為假 | `severity` 以 `block` 開頭 → **blocking**；否則 warning。**`severity` 缺席時預設 `warning`** |
| `unknown` | metric 不在命名空間，或值是 `None` | **post 階段 + blocking severity → blocking**（「跑完之後仍然求不出值的阻擋級條件，是沒被滿足，不是通過了」）；pre 階段 → info；post + warning → warning |
| `unparsable` | 不合文法、空字串、或型別不能比較 | **pre 與 post 都 blocking**（見下） |

> **無法解析的 criterion 在每個階段都擋，這是刻意的。** 一個沒有人能求值的條件比沒有條件更糟：它在計畫裡**看起來像一個保證**，卻什麼都不強制。訊息會直接告訴你正確形狀（`It must be a single comparison, e.g. 'events_per_group >= 5'`）。

另外兩個結構性警告：**會產出檔案但完全沒宣告 `success_criteria` 的 step** 會被警告；**所有 criterion 都是 warning 級的 step** 也會被警告（等於沒有任何硬條件）。`status: "skipped"` 的 step 不求值。

## Pipeline Step Status Values

- `pending` — not yet started
- `running` — currently executing
- `done` — completed successfully
- `error` — failed (check log)。**失敗的正式拼法是 `error`，沒有 `failed`**
- `needs_rerun` — 回饋標記要重跑，**或該 step 的 config 自上次執行後改過**（`config_sha256` 不符）
- `skipped` — **只有 `--skip` 與 explore profile 停放會寫**；偵測到既有輸出**不會**寫這個狀態
- `blocked` — 依賴失敗，**或該 step 的 config 檔被刪了**

## Pipeline Auto-expansion Rules

For each outcome (primary + each secondary), generate:

| Step ID pattern | Skill | Depends on |
|----------------|-------|------------|
| `km_{outcome_id}` | kaplan-meier | — |
| `cr_{outcome_id}` | competing-risk | — (only if competing_risk_enabled) |
| `uni_{outcome_id}` | univariate-forest | — |
| `multi_{outcome_id}` | multivariate-interaction | `uni_{outcome_id}` |
| `mi_{outcome_id}` | missing-data | `missingness`, `multi_{outcome_id}` (only if `missing_data.strategy` != `assess_only`) |

`mi_{outcome_id}` 產的是「多重插補 + pooled analysis + CC vs MI 對照」。**預設不產生**，等 `missingness` 的缺失評估 verdict 出來再決定要不要加。

**每個 outcome 另依 `advanced_analyses.<key>.enabled` 產生**（方法學規格 `advanced_analyses.md`；不開就不產生這個 step）：

| enabled 的 key | 產生的 step | `depends_on` |
|---|---|---|
| `nonlinearity` | `rcs_{outcome_id}` | `multi_{outcome_id}` |
| `robust_variance` | `robust_{outcome_id}` | `multi_{outcome_id}` |
| `immortal_time` | `landmark_{outcome_id}`（`mode="extended_cox"` 時 id 為 `extcox_{outcome_id}`） | `flowchart` |
| `calibration` | `calibration_{outcome_id}` | `multi_{outcome_id}` |
| `weighting` | `weighting_{outcome_id}` | `multi_{outcome_id}` |
| `evalue` | `evalue_{outcome_id}` | **`multi_{outcome_id}`（必要——它讀 `Multi_{outcome_id}.xlsx` 的估計值）** |

Shared steps (generated once):

| Step ID | Skill | Depends on |
|---------|-------|------------|
| `flowchart` | flowchart | — |
| `table1` | table1 | — |
| `missingness` | missing-data | — (**always generated**, never conditional) |
| `psm` | psm-matching | — (only if psm_enabled) |
| `auc` | auc-cstat | — (only if auc_enabled) |
| `strobe` | strobe | — （`advanced_analyses.strobe.enabled` 時產生；無 `depends_on`，但**要排在 manuscript 之前**：有 `strobe` 就把它加進 `manuscript.depends_on`） |
| `reviewer_challenge` | reviewer-challenge | the analysis steps it reviews (**required whenever `manuscript` exists**) |
| `manuscript` | manuscript-results | all other steps, and **必須含 `reviewer_challenge`**（傳遞依賴即可） |

> **`manuscript` 的 `depends_on` 要真的把關卡列進去**，否則「fatal 擋住 manuscript」只是文件上的說法：
> - 有 `strobe` → 加進 `manuscript.depends_on`
> - **`reviewer_challenge` 一定要在 `manuscript.depends_on` 的傳遞依賴裡**。缺 step 或缺依賴，`generate_configs.py` 會 FATAL 退出，不會靜默放行（2026-08-11 起；此前只有文件規定，runner 擋不住）。

## Analysis Groups (v2.0)

Steps are organized into groups for parallel execution and HITL checkpoints.
See `pipeline_state_machine.md` for detailed group definitions.

| Group | Group ID | Steps | Checkpoint Type |
|-------|----------|-------|----------------|
| Foundation | `foundation` | flowchart, table1, missingness | MANDATORY |
| Per-outcome (primary) | `outcome_primary` | km_primary, cr_primary, uni_primary, multi_primary, mi_primary | FULL/SLIM |
| Per-outcome (secondary_N) | `outcome_secondary_N` | km_secondary_N, cr_secondary_N, uni_secondary_N, multi_secondary_N, mi_secondary_N | FULL/SLIM |
| Supplementary (Synthesis Review) | `supplementary` | psm, auc, calibration_*, weighting_*, evalue_* | FULL + `synthesis`（沒排到 pre-manuscript 閘門時升 MANDATORY） |
| Manuscript | `manuscript` | strobe, reviewer_challenge, manuscript | MANDATORY，且在群組**執行之前**觸發 |

Within each group, independent steps run in parallel. Sequential dependencies (multi depends on uni) run after independent steps complete.

## Table/Figure Auto-numbering

Default numbering order:
1. Figure 1 — Flowchart
2. Table 1 — Baseline characteristics
3. Figure 2 — KM curve (primary)
4. Table 2 — Univariate regression (primary) + Figure 3 (forest plot)
5. Table 3 — Multivariate regression (primary)
6. Figure 4+ — CIF plot (primary, if enabled)
7. Repeat for each secondary outcome
8. Table N — PSM results (if enabled)
9. Table N+1 — AUC/C-statistics (if enabled)

## `pipeline_profile` —— explore 還是 submit

| 值 | 別名 | 效果 |
|---|---|---|
| `explore` | `exploration` / `exploratory` | `manuscript-results`、`reviewer-challenge`、`strobe` 被**停放**：`status: "skipped"` + `skip_reason: "profile"`，不產 config、不執行。manifest 另記 `guardian_mode_recommended: "off"`。`explore` 也不會自動補 `strobe` step |
| `submit` | `submission` / `confirmatory` | **缺席時的預設值。** 把 `skip_reason == "profile"` 的 step 解除停放改回 `pending` |

**其他值 → `ValueError` → FATAL。** 可寫在 `study.pipeline_profile` 或計畫頂層（`study` 優先）。

- **`skip_reason` 是可逆性的關鍵**：只有帶 `skip_reason: "profile"` 的停放會被 `submit` 解除。**手動 `--skip` 的 step 沒有這個鍵，兩個方向都不會被動到。**
- **`pipeline_profile` 進指紋，但只在這個鍵有寫的時候**（optional fingerprint field）。這就是 `--migrate` 刻意不替你寫入預設值的原因——寫進去會無故改變指紋。
- 執行面：`explore` 下每個 step 在 `explore_ledger.jsonl` 留一列。

> ⚠ **`submit` 一律要 promotion record，即使這個專案從來沒有 explore 過。** `verify_promotion_record()` 對每個 `pipeline_profile: "submit"` 的計畫都檢查 `promotion_record.json` 在不在，**沒有「沒探索過就免了」的例外**。
>
> 這對「一開始就知道要投稿、直接寫 submit」的專案是一道多出來的手續：仍然要跑一次 `reviewer_challenge.py promotion-diff`（`--explore` 與 `--submit` 指向同一份計畫也可以，差異為空，但 `--after-seeing-outcomes` 仍必填）。**不想要這道手續的話，起手用 `explore`**，等真的要投稿時再轉 `submit` 並產紀錄——那本來就是這個機制設計的走法。用法細節見 `reviewer_challenge.md` §4.3。

## `covariates[].selection_basis` —— 共變項是怎麼進來的

**四個合法值**（`reviewer_challenge.py` 的 `SELECTION_BASIS_VALUES`）：

| 值 | 意思 |
|---|---|
| `dag_prespecified` | 依 DAG，在看資料之前就定好 |
| `clinical_prior` | 依臨床先驗知識 / guideline，事前指定 |
| `univariable_screen` | **逐變項篩選挑出來的** |
| `data_driven_other` | 其他由資料驅動的選法（stepwise、LASSO…） |

> **這個欄位不是給人看的註解，它進計畫指紋。** 而且它是被抽出來以「決策」的形式雜湊的（跟 `model_purpose` / `analysis_intent` / `estimand_type` 同一組），意思是**把 `clinical_prior` 改成 `univariable_screen` 會讓既有的 reviewer challenge 立刻失效**。這正是重點：後兩個值會讓後續的 p 值失去原本的解釋，所以它必須是一個**改了就要重新被挑戰**的宣告。
>
> ⚠ **`generate_configs.py` 完全不讀 `selection_basis`**（`grep` 零命中）。讀它的是 `reviewer_challenge.py`。所以填錯值**不會**在產 config 時被擋——要到 reviewer challenge 才會出現。

**三個相關但不同的欄位，不要混**：

| 欄位 | 位置 | 進指紋？ | 用途 |
|---|---|---|---|
| `selection_basis` | `covariates[]` | **是**（以決策形式） | 選法的**分類**，四個枚舉值 |
| `selection_rationale` | `covariates[]` | **否**（明確被剔除） | 自由文字理由，改它不會動指紋 |
| `covariate_provenance` | 計畫頂層，`{column: why}` | **否** | 逐欄位的理由，`selection_rationale` 的後備 |
| `covariates_selection_rule` | 計畫頂層，字串 | **否** | 一句涵蓋全部共變項的規則 |

理由的解析順序：`covariates[].selection_rationale` → `covariate_provenance[<column>]` → `covariates_selection_rule`（會被標成 `(plan-level rule)`）→ 都沒有就記一條 method warning，列出前 8 個沒理由的共變項。

## `outcomes[].ph_violation_remedy` ★ 位置就是強制手段

**四個合法值**：`stratify` / `time_varying` / `rmst` / `disclose`。其他值 → `ValueError`，不會被放過。

### 只讀 `outcomes[<id>]`，寫在計畫頂層是**刻意無效**的

```jsonc
// ✅ 會被讀到
"outcomes": {"primary": {"ph_violation_remedy": "disclose", "ph_disclose_decision_id": "D-021"}}

// ❌ 靜默忽略 —— 程式裡沒有任何一行讀計畫頂層的這個鍵
"ph_violation_remedy": "disclose"
```

**為什麼位置這麼重要**：計畫指紋雜湊 `outcomes`，不雜湊未知的頂層鍵。宣告在 `outcomes[]` 裡 → 事後補填會改變指紋 → 既有的 reviewer challenge 立刻失效、必須重跑。**這就是「事前指定」可以被檢查的機制**；放在頂層的話，補填不留任何痕跡，宣告就變成一句空話。

### 哪些值 pipeline 真的會執行（2026-08-12 起 `stratify` 也會了）

由 `_carry_ph_remedy()` 帶進 config，**呼叫點只有一個：`gen_multivariate_interaction()`**。它寫進 config 的鍵名不變：`ph_violation_remedy` 與 `ph_disclose_decision_id`。

| remedy | 有沒有 step generator | 實際行為 |
|---|---|---|
| `disclose` | 不需要 | multivariate step 發 warning，要求 `ph_disclose_decision_id`。**manuscript 階段的 artifact gate（`ph_remedy_gate.py`）沒看到那個 ID 就擋** |
| `stratify` | ✅ `ph-stratified` → `scripts/ph_stratified.py` | 自動補 `ph_stratified_<outcome>` step，跑 stratified Cox |
| `time_varying` | ✅ `ph-time-varying` → `scripts/ph_time_varying.py` | 自動補 `ph_time_varying_<outcome>` step，跑分段常數 HR |
| `rmst` | ✅ `ph-rmst` → `scripts/ph_rmst.py` | 自動補 `ph_rmst_<outcome>` step，跑 RMST 對比 |

三者都由 `_plan_pipeline_changes()` 依 `_REMEDY_STEPS` 表自動加入（需 `plan_schema_version: 2`；舊 plan 只會被告知，跑 `--migrate` 才套用），都**另出一張表**、都寫 evidence sidecar 供 gate 驗內容。**`disclose` 不在表裡**，它不需要 step。

#### 三個 remedy 各自的產物與 optional 欄位

| remedy | 產物 | `outcomes[<id>]` 的 optional 欄位 |
|---|---|---|
| `stratify` | `Stratified_<oid>.xlsx` + `_remedy.json` | `ph_strata_variables`（欄位名 list；不填 = `auto`，取自 PH 檢定的 `violating_variables`） |
| `time_varying` | `TimeVarying_<oid>.xlsx` + `_remedy.json` | **`tv_cut_points`（時間窗切點，該 outcome 的 `time_unit` 為單位）**、`time_varying_variables`（不填 = `auto`） |
| `rmst` | `RMST_<oid>.xlsx` + `_remedy.json` | **`rmst_tau`（數值）或 `rmst_tau_rule`（規則名，目前支援 `min_of_arm_max_followup`）** |

**粗體那兩個是 gate 會擋的**：`tv_cut_points` 與 tau 都是「作者選的一個時間」，而兩個 remedy 的答案都隨那個選擇移動。看完效應在哪裡轉向才畫的時間窗，是沿著時間軸做的次族群搜尋；看完哪個 tau 讓對比好看才定的 tau，是 RMST 全部的 p-hacking 面。所以它們必須寫在 `outcomes[]` 裡（＝進指紋）。**沒寫不是死路**：分析照跑、表照出，作者看得到數字與確切的修法，擋的是 manuscript gate——把人擋在沒有出口的門前比放行更糟。

`time_varying` 的實作是**預先指定時間窗的分段常數 HR**（`CoxTimeVaryingFitter` + start/stop 格式）。切 episode 是免不了的：lifelines 的 `CoxPHFitter` 沒有 R 的 `tt()`，隨時間變的係數只能用區間列表達。避開的是無界版本——每人最多「切點數 + 1」列，而不是每個事件時間一列。

⚠ `rmst` 目前的實作是**未校正**的（各組 Kaplan-Meier，沒有共變項），而它取代的是校正過的模型——這是 estimand 的改變，不只是尺度。sidecar 記 `adjusted: false`、gate 每次都 warn。校正版需要 IPTW 或 pseudo-observation 迴歸，都還沒實作；若 confounding 在原模型裡真的有作用，`stratify` / `time_varying` 才是保留校正的選項。

#### `stratify` 產出什麼，以及為什麼是另一張表

`ph_stratified.py` **不會**去改 multivariate step 的 workbook。在那支腳本裡加 `strata=` 會讓 Sheet 1 的被分層變項失去 HR，而 Sheet 2 的交互作用模型仍是未分層的——同一個檔案裡兩張表用不同假設配適，版面上卻沒有任何地方講（2026-08-12 裁決，爭議五）。所以主分析原封不動、保持內部一致，remedy 是**第三張表**加上明確的交叉引用。代價是讀者要看第二個檔，這比一個看起來一致、實際不一致的檔案划算。

| 產物 | 內容 |
|---|---|
| `Stratified_<outcome>.xlsx` | Sheet 1 分層後的模型（被分層的變項列成 `— (stratified)`，不是整列消失）；Sheet 2 各層 n / 事件數 + 分層後的 PH 重驗 |
| `Stratified_<outcome>_remedy.json` | evidence sidecar（`ph_remedy_evidence/1`），以 `table_basename` + `table_sha256` 綁定該 workbook |

`ph_remedy_gate.py` 對**有 sidecar** 的 remedy 驗內容：sidecar 綁的是不是這張表、remedy 是不是宣告的那個、`status` 是不是 `computed`，以及最關鍵的一條——**實際分層的變項有沒有涵蓋 PH 檢定真正判定違反的變項**。分層在沒違反的變項上，模型裡的違反原封不動、卻多了一張看起來像修正的表，這正是只驗檔案存在抓不到的失敗。**沒有 sidecar**（自建 step、或 sidecar 出現前的舊產物）→ 退回原本的「檔案存在 + 具名簽字」路徑，既有專案零 migration 成本。

#### `outcomes[<id>].ph_strata_variables`（optional，欄位名 list）

不填 = `"auto"`：分層變項在執行期取自 PH 檢定產物的 `violating_variables`。這不是放寬事前指定——**事前指定的是「若 PH 違反則分層」這個決定**；哪個共變項違反是資料的性質，不是決定，而分層在違反者以外的變項上根本不構成 remedy。要事前點名就填欄位名 list；sidecar 會記 `strata_variables_source` 是 `plan` 還是 `auto_from_ph_test`，讀的人分得出來。放在 `outcomes[]` 裡 → 進指紋，事後改會作廢既有 challenge。

**兩種會被拒絕（exit 2）而不是硬做的情況**：① 違反的是**曝險變項本身**——`strata=` 會刪掉它的係數，remedy 等於刪掉研究要報的結果，訊息會指向 `time_varying` / `rmst`；② 違反的是**連續變項**——分層需要類別，切點怎麼切是有多個合理答案的分析決定，腳本不會在一個已發表的估計底下靜默替你決定；請把分好組的變項放進 plan（切點寫進 decision log）再點名。

`ph_disclose_decision_id` **單獨宣告而沒有 remedy** → 記一條 `ph_disclose_decision_id_without_remedy` warning，且**什麼都不帶進 config**。

## 計畫指紋（`plan_fingerprint`）—— 改什麼會讓 reviewer challenge 失效

實作在 `reviewer_challenge.py` 的 `plan_fingerprint()`；`generate_configs.py` 動態 import 它，不自己重寫一份。輸出是 `sha256` 的**前 16 碼**。

**一律納入**：`study`、`population`、`grouping`、`outcomes`、`covariates`、`derived_variables`、`analyses`、`missing_data`、`advanced_analyses`。
**有寫才納入**：`estimand`、`pipeline_profile`、`estimand_type`。
**`pipeline` 只納入骨架**：每個 step 只取 `{id, skill, outcome, depends_on(排序後)}`，並依 id 排序。所以 `status`、`skip_reason`、`output_file`、`runtime` 這些**執行狀態不會讓指紋改變——單純重跑不會失效**。
**遞歸剔除**：`selection_rationale`（任何深度）。
**抽出來另算**：`model_purpose`、`study_purpose`、`analysis_intent`、`selection_basis`、`estimand_type` 從原位移除，正規化成枚舉後統一雜湊進 `_decisions`。
**完全不進指紋**：`covariate_provenance`、`covariates_selection_rule`、`decision_log`、`multiplicity`、`manuscript`、`diagnostics`、`table1`、`table_figure_mapping`、`plan_schema_version`、`auto_steps_enabled`、`version`，以及所有 `_` 開頭的暫存鍵。

> 指紋動了不代表要重跑全部十個 domain —— 先跑 `reviewer_challenge.py rerun-scope` 看哪幾個真的失效。**沿用的 domain 要在 `decision_log.md` 留一列**，否則「只重跑三個」跟「只跑了三個」在檔案上分不出來。
>
> 「我只改了註解為什麼指紋變了」→ 跑 `reviewer_challenge.py explain-fingerprint --plan <計畫> --against <另一份>`。

## `missing_data` 區塊語意

方法學規格見 `missing_data_protocol.md`。整個區塊是 optional —— 沒寫的話，`missingness`（缺失評估）照樣產生並執行，只是拿全部預設值；`mi_{outcome_id}` 不會被展開。

| 欄位 | 型別 / 允許值 | 預設 | 語意 |
|---|---|---|---|
| `strategy` | `"assess_only"` \| `"mi_sensitivity"` \| `"mi_primary"` | `"assess_only"` | 決定 **Step 3 展開時要不要生 `mi_{outcome_id}` 步驟**。`assess_only` = 只跑評估；`mi_sensitivity` = 跑 MI，但 complete-case 仍是主分析；`mi_primary` = 跑 MI 並事前指定 MI 為主分析 |
| `auxiliary_variables` | `["col", ...]` | `[]` | 進插補模型但不在分析模型裡的欄位（協議 §3 item 5）。評估步驟拿它當 `candidate_auxiliary`，插補步驟拿它當 `auxiliary_variables` |
| `m` | int \| `null` | `null` | 插補次數。`null` = 由腳本套協議 §4.4 的 `m = max(20, ceil(最大缺失百分比))`（上限 100）。**`null` 不等於 mice 預設的 5** |
| `seed` | int | `42` | 隨機種子。與 `m` 一起寫進輸出檔，否則結果不可重現（協議 §4.4） |
| `maxit` | int | `20` | MICE 迭代次數（收斂 trace 用） |
| `method_overrides` | `{"col": "pmm"\|"logreg"\|"polyreg"\|"polr"}` | `{}` | 逐欄覆寫插補方法；沒列到的欄位由腳本依變項型態自動選（協議 §4.3） |
| `primary_analysis` | `"complete_case"` \| `"mi"` | **`"complete_case"`** | 論文的主分析是哪一個。**pipeline 永遠不會自動把它改成 `"mi"`** —— 協議 §7 明訂這是要事前指定、並登記進 `decision_log.md`（帶永久 ID）的人為決策。評估步驟給的 verdict 只是建議 |

> `strategy` 與 `primary_analysis` 是兩件事。`mi_sensitivity` + `primary_analysis: "complete_case"` 是常見組合（MI 當 sensitivity）；`mi_primary` 應搭 `primary_analysis: "mi"`，但兩者不會互相自動改寫——不一致時由 Claude 在 Step 3 向使用者指出，不靜默修正。

## `analyses.auc` 區塊語意（discrimination / incremental value）

`analyses.auc_enabled` 決定要不要跑；`analyses.auc` 這個 sub-block 決定**怎麼跑**。整塊 optional。

| 欄位 | 型別 | 預設 | 語意 |
|---|---|---|---|
| `bootstrap_n` | int | `2000` | C-index 的 percentile CI 要幾次重抽。**幾百列資料配 2000 次就足以撞到 runner 的 600s step timeout**；會 timeout 的專案請刻意調低並記進 `decision_log.md`，不要把 timeout 讀成分析失敗 |
| `seed` | int | `42` | 重抽種子。不寫死就不可重現 |
| `clinical_model_columns` | `["col", ...]` | `[]` | **incremental value 的 base model**。空 = 關閉，每個共變項各自報自己的 discrimination（原本唯一的行為）。填了就改問「這個變項對既有模型還能加多少」，輸出多出 clinical model / clinical model + variable / **Delta C-index** 三欄 |

**`clinical_model_columns` 是宣告，不是方便設定。** 哪些變項算「已知」直接決定 Delta 的大小，事後挑一組讓候選變項好看的 base model 就是這個問題全部的 p-hacking 面。它放在 `analyses` 底下**是為了進 plan fingerprint**（`analyses` 在 `FINGERPRINT_FIELDS` 裡）——跟 `rmst_tau`、`tv_cut_points` 放進 `outcomes[]` 是同一個理由：宣告必須早於結果，改了宣告既有的 reviewer challenge 就作廢。

三條硬行為（違反一律 FATAL，不靜默處理）：

- 只寫**欄位名**，不要重寫 label / type / scale——那些在 `covariates` 已經有一份，寫第二份就是同一個事實的第二個定義。
- 列出的欄位必須是 `covariates` 裡有的，否則 FATAL 並印出可用欄位（打錯字不會被靜默忽略）。
- **base model 裡的變項不會再被當候選**：`auc_cstat` 算的是 `base + candidate`，候選變項若本身就在 base 裡等於進去兩次、Delta 恆為 0。所以把全部共變項都列進去 = 沒有東西可以評估 = FATAL。

## `advanced_analyses` 區塊語意

方法學規格見 `advanced_analyses.md`。整個區塊 optional；**每一項預設 `enabled: false`**，因為它們各自回答不同的研究問題，全開只會產生一堆沒人解讀的檔案。Step 3 依 `enabled` 決定要不要展開對應步驟。

| 步驟 | skill | 群組 | 何時該開 | 關鍵設定 |
|---|---|---|---|---|
| `rcs_{outcome}` | `nonlinearity` | outcome | 有連續共變項（幾乎總是） | `variables` 空 = 全部連續共變項；`knots` 預設 4 |
| `robust_{outcome}` | `robust-variance` | outcome | Step 3.5 診斷標了 clustering，或資料有中心／醫師／重複量測 | **`cluster_column` 必填**（沒填會回頭找 `study.cluster_column`），沒填會記 method warning、步驟會擋，而且在 Step 3.5 的閘門眼中算 **inert（不算補救）**。`method` 只剩 `cluster_robust` / `gee`，**`mixed` 給了會直接報錯** |
| `calibration_{outcome}` | `calibration` | supplementary | **預測模型研究**才需要 | `study_purpose` 預設 `etiologic`（只報 discrimination）；設 `prediction` 才跑整套 |
| `weighting_{outcome}` | `weighting` | supplementary | 想要 ATE 或 PSM 丟掉太多人時 | `method` = `iptw`（ATE）或 `overlap`（ATO）。**與 PSM 的 ATT 是不同的 estimand** |
| `landmark_{outcome}` / `ExtendedCox_{outcome}` | `immortal-time` | outcome | 暴露分組用到 time zero 之後的資訊 | `exposure_time_column` 與 `landmark_times` 必填；**時點要事前指定，給幾個就全報** |
| `evalue_{outcome}` | `evalue` | supplementary | 觀察性研究的主結論（幾乎總是） | `reference_confounders` 沒給會記 method warning——沒有尺度錨點的 E-value 讀者無從判斷 |
| `strobe` | `strobe` | manuscript | 要投稿前 | 依 `study.design` 自動選 cohort / case-control / cross-sectional 版本。若希望 checklist 先結案再寫 Results，給 `manuscript-results` 加 `depends_on: ["strobe"]` |
| `reviewer_challenge` | `reviewer-challenge` | manuscript | **有 manuscript 就必開**（不受 `enabled` 控制） | 不跑分析，讀 Step 6.7 的 aggregate JSON 把關。缺 step 或 manuscript 沒依賴它 → `generate_configs.py` FATAL |

**共通**：每個步驟的輸出第一個分頁都要回答「這個估的是什麼 estimand」；所有預設值（knots、bootstrap 次數、landmark 時點、correlation structure、trimming 門檻）都是要登記進 `decision_log.md` 的方法學決策，不是可以靜默採用的實作細節。

### 兩個會被自動補進 `pipeline[]` 的步驟

`rcs_{outcome}` 與 `strobe` **不必寫進計畫**，`generate_configs.py` 的 `_plan_pipeline_changes()` 會補。但**三個前提要同時成立**才真的寫進計畫，否則只印預覽：

1. 沒帶 `--only`
2. `auto_steps_enabled` 不是 `false`
3. `plan_schema_version` 是 `>= 2` 的整數

| 補的 step | 條件 |
|---|---|
| `rcs_{oid}`（`nonlinearity`） | 該 outcome 有 `multivariate-interaction` step、至少一個 `type: "continuous"` 共變項、沒有既存的 nonlinearity step、算得出參數預算、沒有無法定價的項、且 `n_events` 沒填或 `events >= 10 × 預算`。**兩種 profile 都補** |
| `strobe` | 有 `manuscript-results` step 且它的 `status` 不是 `skipped`（所以 `explore` 下不補），且沒有既存的 strobe step |

`rcs_*` **只是診斷，不取代主模型的線性項**。其餘進階分析一律要自己在 `advanced_analyses.<key>.enabled` 明寫，沒有自動開啟。

## `diagnostics` 區塊語意

由 `generate_configs.py` 讀，是 Step 3.5 四個硬閘門的輸入。

| 欄位 | 規則 |
|---|---|
| `mode` | 封閉集合。`completed` ← {`completed`,`on`,`done`,`ran`,`complete`}；`off` ← {`off`,`not_applicable`,`n/a`}。**其餘（含 `not_run`、`pending`）一律 FATAL** |
| `report_path` | `mode: "completed"` 必填；相對路徑對 `output_dir` 解析；**檔案必須存在於磁碟** |
| `completed_at` | 必填 ISO timestamp；**資料檔 mtime 晚於它 → FATAL**（換了資料沒重跑診斷） |
| `data_fingerprint` | `study.data_file` 的 sha256 前 16 碼。對不上 → FATAL；**`plan_schema_version >= 2` 時缺席本身就是 FATAL**（v1 只降級成警告） |
| `flags_detected` | 三種形狀：`["clustering"]`／`{"clustering": true}`／`{"clustering": {"detected": true, "risk": "high"}}`。`detected` 必須是真的 bool；**認不得的 flag 名直接報錯** |
| `reason` | 僅 `mode: "off"`；試 `reason` → `override_reason` → `note`，**至少 10 個字元**，太短會被當成沒寫 |
| `overrides.<flag>` | 見下 |

**canonical flag 名與別名**：`competing_risk`（←`competing_risks`）、`left_truncation`（←`delayed_entry`）、`time_varying`（←`time_varying_exposure`/`time_dependent_exposure`）、`clustering`（←`cluster`）。另外 `informative_censoring` 與 `proportional_hazards`（←`ph_violation`/`non_proportional_hazards`）**會被接受但不設閘門**——收下它們只是為了不要把它們報成「認不得的 flag」。

**四個閘門與所需補救**：`competing_risk`→`competing-risk`；`left_truncation`→**沒有任何補救 step，一定擋**；`time_varying`→`immortal-time`（`risk` 是 `low`/`none` 時放行，**沒記等級視為觸發**）；`clustering`→`robust-variance`。覆蓋是**逐 outcome** 算的，且**參數沒填的補救 step 算 inert、不計入**。

**`overrides.<flag>` 四個條件缺一不可**：`decision_id` 符合 `#\d+` 或 `Xxx-yyy` 且**真的出現在 `decision_log.md`**、非空 `reason`、該決策條目的文字含該 flag 的關鍵詞（中英皆收）、`outcomes[]` **涵蓋每個被建模的 outcome**。

### 偽 flag `diagnostics_off` —— 「我根本沒跑診斷」的強化版宣告

`diagnostics_off` 可以當成 `overrides` 的鍵，但**不能**出現在 `flags_detected`（它刻意不在 `_CANONICAL_FLAGS` 裡，正是為了讓它可以被 override 命名、卻不會被當成一個「偵測到的發現」）。接受的拼法：`diagnostics_off` / `diagnostics` / `off`。

**跟直接寫 `mode: "off"` 差在舉證強度，兩者都合法**：

| 做法 | 要提供什麼 | 適合什麼情況 |
|---|---|---|
| `mode: "off"` + `reason`（≥10 字元） | 一句自由文字，**沒有人會去查證** | 顯然不適用（例如整篇沒有 time-to-event 分析） |
| `overrides.diagnostics_off` | 完整四條件：真實存在的 decision-log ID、理由、關鍵詞相符、`outcomes[]` 涵蓋 | **有 survival 分析、但決定不跑診斷**——這種宣稱值得被稽核 |

關鍵詞（`_FLAG_KEYWORDS["diagnostics_off"]`）：`diagnostic` / `survival-diagnostics` / `not applicable` / `no time-to-event` / `診斷` / `不適用`。

> **選哪個是舉證責任的選擇，不是語法偏好。** 「這個研究沒有存活分析所以不需要診斷」用 `mode: "off"` 就夠；「有存活分析但我們決定不跑診斷」應該走 `overrides.diagnostics_off`，因為那是一個需要有人具名負責的決定。

> **`diagnostics.override_reason` 已不再放行任何閘門**（2026-08-12 起；此前一句 `"N/A"` 能一次解開四個）。它現在只剩 `mode: "off"` 的自由文字理由這一個用途。

## `manuscript.analysis_files[].type` 的合法值

給了 `manuscript.analysis_files` 就會**取代**由 pipeline 推導的清單，並記一條 `manuscript_analysis_files_overridden` warning。每筆 `type` 與 `path` 都必填（缺一個 → `ValueError`），`path` 是絕對路徑或相對 `output_dir`。

`type` 必須是 `manuscript-results/scripts/extract_data.py` 的 `EXTRACTORS` 的鍵（**注意混用底線與連字號，照抄**）：

```
table1  univariate  multivariate  kaplan_meier  competing_risk  psm  auc
weighting  nonlinearity  robust-variance  calibration  immortal-time
evalue  strobe  missing-data
```

`flowchart`、`reviewer-challenge`、`missing-data` 在推導清單時被列為「不抽取」，那是一行資訊，不是警告。

## Sub-skill Config Mapping

Below is how research plan fields map to each sub-skill's config.

### Shared fields (inherited by all configs)
- `data_file` ← `study.data_file`
- `filters` ← `population.filters`
- `derived_variables` ← `derived_variables`
- `grouping` ← `grouping`
- `abbreviations` ← `abbreviations`
- `missing_data_handling` ← `"listwise"` (default)

### flowchart
- `initial_label` ← derived from `study.title`
- `exclusion_steps` ← `population.exclusion_steps`
- `final_label` ← `"Final study cohort"`
- `group_split` ← `grouping`
- `output_file` ← `"{output_dir}/Flowchart.xlsx"`

### table1
- `sections` ← built from `covariates` array, grouped by type
- `title` ← `"Table 1. Baseline Characteristics"`
- `output_file` ← `"{output_dir}/Table1.xlsx"`

### missing-data — assessment (`missingness`, Foundation, always generated)
- `mode` ← `"assessment"` (fixed)
- `analysis_variables` ← built from `covariates` (`{column, type, label←name}`)
- `outcomes` ← primary + every secondary, each `{id, type, time_column, event_column}` (type 已 normalize)
- `candidate_auxiliary` ← `missing_data.auxiliary_variables` (default `[]`)
- `thresholds` ← `{low: 5, high: 40}` — 協議 §2 的 verdict 分界，非使用者可調
- `output_file` ← `"{output_dir}/Missingness.xlsx"`
- `plot_file` ← `"{output_dir}/Missingness_pattern.png"`

### missing-data — imputation (`mi_{outcome_id}`, per outcome, conditional)
- `mode` ← `"imputation"` (fixed)
- `analysis_type` ← `"cox"` if time_to_event / competing_risk, `"logistic"` if binary（判定與 multivariate-interaction 完全相同，好讓 CC vs MI 是同一個模型的對照）
- `cox_settings` / `logistic_settings` ← from outcome（另一個為 `null`）
- `sections` ← built from `covariates`（同 multivariate-interaction）
- `auxiliary_variables` ← `missing_data.auxiliary_variables` (default `[]`)
- `mi_settings` ← `{m, seed, maxit, method_overrides}` from `missing_data`，預設 `{null, 42, 20, {}}`
- `output_file` ← `"{output_dir}/MI_{outcome.id}.xlsx"`
- `diagnostics_plot` ← `"{output_dir}/MI_{outcome.id}_diagnostics.png"`
- **competing_risk outcome**：generator 仍產出 config，但同時記一條 `mi_competing_risk_unsupported` methodological warning（協議 §6）；`missing_data.py` 執行時會吐 `[QC_BLOCKING]`。錯誤訊息集中在腳本一處，generator 不重複擋

### kaplan-meier (per outcome)
- `time_column` ← `outcome.time_column`
- `event_column` ← `outcome.event_column`
- `time_unit` ← `outcome.time_unit`
- `time_scale` ← `outcome.time_scale`
- `time_points` ← `outcome.time_points`
- `title` ← `"Kaplan-Meier: {outcome.name}"`
- `output_file` ← `"{output_dir}/KM_{outcome.id}.xlsx"`

### competing-risk (per outcome)
- `time_column` ← `outcome.time_column`
- `event_column` ← `outcome.competing_event_column` or derived
- `event_labels` ← `outcome.competing_event_labels`
- `primary_event` ← `1`
- `time_unit` / `time_scale` / `time_points` ← from outcome
- `fine_gray` ← built from `covariates` if desired
- `output_file` ← `"{output_dir}/CR_{outcome.id}.xlsx"`

### univariate-forest (per outcome)
- `analysis_type` ← `"cox"` if time_to_event, `"logistic"` if binary
- `cox_settings` ← `{time_column, event_column}` from outcome
- `logistic_settings` ← `{outcome_column: event_column}` from outcome
- `sections` ← built from `covariates`
- `output_file` ← `"{output_dir}/Uni_{outcome.id}.xlsx"`

### multivariate-interaction (per outcome)
- Same as univariate-forest, plus:
- `interaction_variables` ← `"all"`
- `output_file` ← `"{output_dir}/Multi_{outcome.id}.xlsx"`

### psm-matching
- `matching_variables` ← built from `covariates`
- `matching` ← `{caliper: {enabled: true, width: 0.20}, ratio: 1}`
- `analysis_type` ← based on primary outcome type
- `outcomes` ← all outcomes (primary + secondary)
- `output_file` ← `"{output_dir}/PSM.xlsx"`

### auc-cstat
- `analysis_type` ← based on primary outcome type
- `cox_settings` or `logistic_settings` ← from primary outcome
- `sections` ← built from `covariates`
- `clinical_model` ← `{enabled: false}` (user can enable)
- `output_file` ← `"{output_dir}/AUC.xlsx"`

### manuscript-results
- `analysis_files` ← list of all completed output files with their types
- `study_design` ← `study.design`
- `primary_outcome` ← `outcomes.primary.description`
- `secondary_outcomes` ← descriptions from secondary outcomes
- `group_description` ← built from `grouping.groups` labels
- `table_figure_map` ← `table_figure_mapping`
- `language` ← `"english"` (default)
- `output_file` ← `"{output_dir}/Results_Section.docx"`

## Skill Script Paths

| Skill | Script | Path |
|-------|--------|------|
| flowchart | flowchart.py | `${CLAUDE_SKILL_DIR}/../flowchart/scripts/flowchart.py` |
| table1 | make_table1.py | `${CLAUDE_SKILL_DIR}/../table1/scripts/make_table1.py` |
| kaplan-meier | kaplan_meier.py | `${CLAUDE_SKILL_DIR}/../kaplan-meier/scripts/kaplan_meier.py` |
| competing-risk | competing_risk.py | `${CLAUDE_SKILL_DIR}/../competing-risk/scripts/competing_risk.py` |
| univariate-forest | univariate_forest.py | `${CLAUDE_SKILL_DIR}/../univariate-forest/scripts/univariate_forest.py` |
| multivariate-interaction | multivariate_interaction.py | `${CLAUDE_SKILL_DIR}/../multivariate-interaction/scripts/multivariate_interaction.py` |
| psm-matching | psm_matching.py | `${CLAUDE_SKILL_DIR}/../psm-matching/scripts/psm_matching.py` |
| auc-cstat | auc_cstat.py | `${CLAUDE_SKILL_DIR}/../auc-cstat/scripts/auc_cstat.py` |
| missing-data | missing_data.py（+ `mice_driver.R`） | `${CLAUDE_SKILL_DIR}/scripts/missing_data.py` |
| manuscript-results | extract_data.py + generate_docx.py | `${CLAUDE_SKILL_DIR}/../manuscript-results/scripts/` |

---

## Sub-skill research_plan.json Read Contract (Step 0 auto-read)

> Complementary to the "Sub-skill Config Mapping" section above. That section documents how `research-plan` Step 3 plan fields flow into each skill's generated config (the **write** side). This section documents which `research_plan.json` fields each sub-skill's Step 0 Context Recovery **reads** back when run (the **read** side).

**Purpose**: Every biostats sub-skill's Step 0 "Context Recovery" reads specific fields from `research_plan.json`. This table is the authoritative contract — `generate_configs.py` MUST write these fields, sub-skills MUST NOT depend on fields outside this list. If a field is missing at runtime, the sub-skill fails loudly (no silent errors).

**Global fields read by all biostats skills** (from `research_plan.json` root):
- `data_path` (string) — CSV or Excel
- `output_dir` (string) — where to write skill artifacts
- `group_var` (string) — primary grouping column (intervention vs control)
- `group_labels` (object, optional) — human-readable labels e.g. `{"1": "TTM 33°C", "0": "Control"}`
- `covariates[]` (array of strings) — adjustment variables
- `derived_variables[]` (array of objects, optional) — calculated columns
- `data_dictionary_path` (string, optional) — `Data_Dictionary.csv`

**Per-skill fields read from `outcomes[]`**:

| Sub-skill | Required outcome fields | Optional outcome fields | Notes |
|-----------|-------------------------|-------------------------|-------|
| **flowchart** | `name` | `exclusions[].reason`, `exclusions[].n` | Reads N at each stage from `pipeline[].flowchart_stages[]` if present; otherwise asks user |
| **table1** | `name`, `type` ∈ {binary, continuous, categorical} | `strata` | Ignores `time_column` / `event_column` |
| **kaplan-meier** | `name`, `type = "time_to_event"`, `time_column`, `event_column`, `time_unit` ∈ {days, months, years}, `time_scale` | `time_points[]` (e.g. [30, 180, 365]), `event_labels` | Must run `/survival-diagnostics` first if `risk = high` in any check |
| **competing-risk** | `name`, `type = "competing_risk"`, `time_column`, `event_column`, `competing_event_column`, `competing_event_labels[]`, `time_unit`, `time_scale` | `time_points[]`, `fine_gray_covariates[]` | `competing_event_column` can be same as `event_column` if coded 0/1/2; type alias `"competing-risk"` (hyphen) accepted |
| **univariate-forest** | `name`, `type`, (if `time_to_event`: `time_column` + `event_column`) | — | Covariates pulled from root-level `covariates[]` |
| **multivariate-interaction** | `name`, `type`, (if `time_to_event`: `time_column` + `event_column`), `interaction_var` | `block if diagnostic_report.json.checks.time_varying.detected = true && risk = high` | Reads root `covariates[]` for adjustment model |
| **psm-matching** | `name` (outcome column), `type`, (if `time_to_event`: `time_column` + `event_column`) | — | PS model built from root `covariates[]` |
| **auc-cstat** | `name`, `type` ∈ {binary, time_to_event, competing_risk}, (if `time_to_event` / `competing_risk`: `time_column` + `event_column`) | `time_horizon` (for time-dependent AUC) | Baseline model = root `covariates[]`. `competing_risk` routes via cause-specific Cox + stderr WARN |

**Fields consumed from `diagnostic_report.json`** (produced by `/survival-diagnostics`):

| Consumer skill | Read field | Action on value |
|---------------|-----------|-----------------|
| kaplan-meier | `checks.competing_risk.detected = true` & `risk = high` | Re-route to competing-risk; warn user |
| kaplan-meier | `checks.left_truncation.detected = true` | Use start-time/stop-time Surv object |
| competing-risk | `recommended_primary = "competing-risk"` | Proceed normally |
| univariate-forest | `checks.clustering.detected = true` & `risk = high` | Add `cluster()` term or use robust SE |
| multivariate-interaction | `checks.time_varying.detected = true` & `risk = high` | **BLOCK** — requires time-varying Cox, not in this skill |
| psm-matching | `checks.informative_censoring.detected = true` | Warn user about bias |
| auc-cstat | `checks.competing_risk.detected = true` | Use cumulative-incidence-based AUC, not KM-based |

**Contract enforcement**:

1. **`generate_configs.py` side**: After reading `research_plan.json`, for each pipeline step, verify all required fields present for that skill. If any missing → raise `ValueError("research_plan.json outcomes[] missing required field X for skill Y")`. Do not silently default.

2. **Sub-skill Step 0 side**: After auto-reading `research_plan.json`, verify required fields exist. If `research_plan.json` is absent (skill run standalone), prompt user interactively — do NOT fabricate.

3. **Schema drift protection**: When adding new optional fields, bump the `research_plan.json$.schema_version` and document here. Sub-skills check `schema_version` compat and warn if older than expected.

**Origin note**: Added 2026-04-23 per pipeline handoff debug plan. Previously the contract was implicit — sub-skill Step 0 documented field names inconsistently, making it hard to catch missing fields before runtime. This table is now the single source of truth.

# Run Pipeline Protocol — `run_pipeline.py` 的旗標、模式、checkpoint 與 QC 閘門

**這份是 SKILL.md Step 6 的規則本體**（2026-09-07 從 SKILL.md 搬出，內容未改）。SKILL.md 只留入口段：何時跑、指令、閘門與失敗行為一句話。

相關：checkpoint 的完整規格見 `checkpoint_protocol.md`；`outcomes[].ph_violation_remedy` 的欄位語意見 `plan_template.md`；狀態機與分析群組見 `pipeline_state_machine.md`。

---

## 指令與旗標

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_pipeline.py <OUTPUT_DIR>/research_plan.json [--hitl] [--no-parallel]
```

**完整旗標表**（以 `run_pipeline.py` 的 argparse 為準）：

| 旗標 | 做什麼 |
|---|---|
| `--from STEP_ID` / `--only STEP_ID` | 從某步開始／只跑某步。**`--only` 會整段跳過依賴檢查**（所以 manuscript 的閘門另外在執行前再驗一次） |
| `--hitl` | 群組結束後暫停。**這是 checkpoint 會真的停下來的唯一模式** |
| `--no-parallel` | 關掉群內平行 |
| `--detect-only` | 只報告不執行（Step 5） |
| `--skip a,b,c` | 逗號分隔，把這些 step 標成 `skipped`。**只接受目前是 `pending` 或 `done` 的 step**，其他狀態會出聲拒絕 |
| `--skip-precheck` | 不跑 pre 階段的 `precheck_configs.py`。**這不是免費的**——它會自動變成一條待表態的方法學替代（見下方替代機制），manuscript 前不處理就擋 |
| `--emit-rerun` | 只寫出 `<OUTPUT_DIR>/rerun.sh` 然後**直接結束，不跑任何 step** |
| `--list-substitutions` | 列出所有方法學替代與目前的表態，然後結束 |
| `--accept-substitution ID:REASON` | 接受某條替代。可重複給。**理由不可省略**（第一個冒號之後全部算理由） |
| `--reject-substitution ID:REASON` | 拒絕某條替代。可重複給 |
| `--override-watchdog DECISION_LOG_ID` | 記錄一次腐爛看門狗的放行，然後**結束不跑**（下一次真的執行時才生效） |
| `--override-feedback-rounds` | 突破 `max_feedback_rounds` 上限 |

> **`--emit-rerun`、`--list-substitutions`、accept/reject、`--override-watchdog` 都是「做完就結束」的動作**，不會順便把 pipeline 跑掉。要執行請不帶這些旗標再跑一次。

**退出碼**：`0` = 跑完（**即使有 step 失敗、被 blocked、或 checkpoint 停下來，退出碼仍是 0**——不要拿退出碼判斷成敗，要讀 Step 7 的狀態）／`1` = 計畫檔不存在，或 pre 階段 precheck 沒過／`2` = 替代表態被拒、`--from`/`--only` 指到不存在的 step、feedback 輪次超限。

The runner operates differently depending on pipeline mode:

## Auto Mode (`pipeline_mode: "auto"`)

- Executes all analysis groups in sequence: Foundation → Per-outcome (primary) → Per-outcome (secondary_1) → ... → Supplementary → Manuscript
- Within each group, independent steps run **in parallel** (e.g., flowchart + table1, or km + cr + uni)
- Sequential dependencies (multi depends on uni) run after independent steps complete
- Updates `status` in research_plan.json with file locking for parallel safety
- Logs stdout/stderr to `<OUTPUT_DIR>/logs/{step_id}.log` (**每次執行該 step 前會清掉舊 log**；要保留診斷歷史請自行複製)
- Errors do NOT abort the pipeline — the runner records the error, marks dependent steps as `blocked` (they never ran, so they are **not** counted as errors), and continues to the next independent step
- Failed steps get **one automatic retry** (2s delay) before being marked as `error`。注意 `retry_count` 一旦寫入就不歸零——同一個 step 在後續任何一次 run 都不會再自動重試。**重試只涵蓋 Phase 2（正式執行）；Phase 1 的 `--check-missing` 失敗會直接回報、不重試**，所以 config schema 不合造成的崩潰一定是在 check phase 現形
- QC 行（`[QC_*]` / `[GUARDIAN_*]`）在 check phase、正式執行、重試三個階段都會被收進 `qc_warnings[]`，**step 失敗時也會保留**
- After all steps complete, proceed directly to Step 7

> **哪些是腳本做的、哪些是 Claude 做的**（2026-08-12 更新——多數原本只有文件規定的東西現在有程式了，但**不是全部**）：
>
> **腳本負責（有程式強制）** —— 依賴排序、群內平行、subprocess 執行與 600 秒 timeout、重試、QC 行擷取、`status` / `total_steps_executed` / `checkpoints[]` 的持久化、HITL 暫停、80 步上限、`max_feedback_rounds` 上限（超限 exit 2，要 `--override-feedback-rounds` 才過）、**Stage Reflector 的五條規則**（`precheck_configs.py` 的 `check_stage_reflector()`，發 `REFLECT-*` 警告）、**FULL/SLIM/MANDATORY 的深度判定與 25% 隨機抽查**（`resolve_checkpoint_type()`）、config 漂移偵測（`config_sha256`）、方法學替代的表態閘門、**缺失評估（`missingness`）的缺失率／樣態／listwise 損失／MCAR 關聯檢定與 verdict**、**MI（`mi_{outcome_id}`）的插補、pooled estimate + FMI、CC vs MI 對照表與收斂診斷圖**。
>
> **Claude 負責（無程式強制，不要宣稱「系統擋下了」）** —— 把 Reflector 的警告**轉成對使用者的具體建議並執行**（腳本只發警告，不會改計畫、不會問你要不要改）、checkpoint 停下來之後的**呈現與詮釋**、Step 7 的結果解讀、**採不採納缺失評估的 verdict（要不要加 `mi_*` 步驟）、主分析選 complete-case 還是 MI**、以及把 method warning 念給使用者聽（Step 4a）。
>
> **一個具體後果**：`checkpoints[].reflection_applied` **永遠是 `false`**，因為那是留給 Claude 在真的採納了 Reflector 建議時自己回填的欄位。看到它是 `false` 不代表沒有建議，只代表沒有人記錄有沒有照做。

## HITL Mode (`pipeline_mode: "hitl"`)

Same execution as auto mode, but **actually stops after the first analysis group completes**: the runner writes the checkpoint into `checkpoints[]`, sets `pipeline_state = "awaiting_review"`, and exits. Re-running the same command resumes — completed steps are not repeated. Checkpoint content is defined in `${CLAUDE_SKILL_DIR}/references/checkpoint_protocol.md`.

> 2026-08-11 之前 `--hitl` 只印出 checkpoint 橫幅就繼續跑完全部，等於宣稱暫停卻沒暫停。現在會真的停。

**Checkpoint type determination**（`resolve_checkpoint_type()`，依序判定）：

| Condition | Type | 會停嗎 |
|-----------|------|---|
| Foundation group | **MANDATORY**（固定） | **會** |
| Manuscript group | **MANDATORY**（固定，且是 **pre_checkpoint**——在該群組**執行之前**觸發） | 有 blocker 就停，**兩種模式都停**；沒 blocker 時只有 `--hitl` 會停 |
| Supplementary group（Synthesis Review） | FULL + `synthesis`；本次沒有排到 pre-manuscript 閘門時**升級成 MANDATORY** | 會 |
| Per-outcome group | FULL（primary outcome 同時有 MI 與 PSM 時升級 MANDATORY 並強制停） | 會 |
| `consecutive_continue_count < 3` | FULL | 會 |
| `consecutive_continue_count >= 3` | SLIM，其中約 **25%** 隨機抽回 FULL | **SLIM 不會停**（見下） |

> **Manuscript checkpoint 在群組之前，不是之後。** 它印的是 `print_manuscript_briefing()` 的六段簡報（含腐爛看門狗、方法學替代表態、post 階段 precheck、explore→submit promotion），目的是在寫論文**之前**把所有沒結案的東西攤出來。所以「manuscript 跑完再檢查」是錯的心智模型。

**MANDATORY checkpoint (after Foundation) — Stage Reflector**

Reflector 的五條規則現在由 `precheck_configs.py` 的 `check_stage_reflector()` **實際計算並發出警告**（2026-08-12 起；此前只有文件，`scripts/` 裡沒有任何東西叫 Reflector）：

| 警告 ID | 觸發條件 | 建議 |
|---|---|---|
| `REFLECT-epv` | 該 outcome 的 **EPV < 10** | rule of 10 允許約 `events // 10` 個參數，目前模型配了幾個一併列出 |
| `REFLECT-small-n` | 最小組 **n < 30** | **只是精確度的觀察**；共變項預算由 EPV 管（見 RES-006），不由 n 管 |
| `REFLECT-imbalance` | 組間人數比 **> 1:5** | 考慮 PSM 或 IPW |
| `REFLECT-events` | 任一組的事件數 **< 5** | 考慮捨棄該 outcome 或併成複合終點 |
| （無 ID，只進建議清單） | 共變項缺失 **> 20%** / **> 50%** | 20% 以上：移除或插補；50% 以上：**不自動移除**，要理由 + sensitivity（MAR 成立時 MI 處理得了） |
| `REFLECT`（info） | 全部通過 | `no adjustments suggested` |

> **原本的第一列寫「Any group n < 30 → 依 rule of 10 減共變項」是個 bug**：條件用 n、公式用 events，兩者不同調。現在拆成兩條——EPV 觸發的 `REFLECT-epv` 管共變項預算，`REFLECT-small-n` 只作為獨立的精確度觀察保留下來，資訊沒有丟。

**這五條全部是 `report.warn()`，一條都不擋。** 腳本算出建議並印出來；**要不要照做、怎麼跟使用者講，是 Claude 的工作，沒有程式強制**。Reflector 永遠不自己改計畫，也**絕不可以**建議更動主要結局或暴露定義——只能動模型設定（共變項、插補策略）。

**Important**: These Reflector rules are **pre-specified methodological safeguards** (EPV constraints, convergence prevention), not hypothesis-driven changes. They should be documented in the study's Statistical Analysis Plan (SAP) upfront. The Reflector must **never** suggest changing the primary outcome or exposure definition — only model specification adjustments. All suggestions are logged in the checkpoint audit trail for transparency.

**FULL checkpoint:**

Detailed summary with all metrics, output files, QC warnings, and decision menu:
```
Options: 1) Continue  2) Review outputs  3) Modify plan  4) Pause
```

**SLIM checkpoint — ⚠ 它不會停下來**

連續 3 次 continue 之後降級成 SLIM。**SLIM 印完一行就直接繼續跑下一組，不寫 `awaiting_review`、不等任何人**：

```
  [✓] outcome_primary complete (4 steps, 45s) → continuing [SLIM, 4 consecutive continues]
```

而且它會**自己在 `checkpoints[]` 記下 `"decision": "continue"`** —— 因為沒有人被問過。所以：

> **使用者體感上，連續 continue 三次之後 pipeline 就會一路跑到底**（除非撞到 MANDATORY、或 25% 抽查抽回 FULL）。這是刻意的設計（減少 checkpoint 疲勞），但**不要對使用者說「每組都會停下來確認」**——三組之後就不會了。要每組都停，在中間穿插一次 `review` 把 `consecutive_continue_count` 歸零。
>
> 另外：**整個群組後 checkpoint 機制只在 `--hitl` 下才會走到**（auto 模式只有 pre-manuscript 那個 briefing 和有 blocker 時會停）。所以 SLIM 的「不停」只在 hitl 模式下觀察得到。

**FULL / MANDATORY 停下來的方式不是問答，是結束程序。** 它把 `pipeline_state` 設成 `"awaiting_review"`、存檔、印出橫幅，然後**結束**。使用者的「回答」＝**再跑一次同一個指令**；下一次啟動時 `record_resume_decision()` 把它記成 `continue`（或在有 blocker 時記成 `blocked`）。腳本不讀 stdin。

**User decisions at checkpoints:**
- `continue` → 再跑一次同一個指令即可，`consecutive_continue_count` +1
- `review` → 檢視輸出，**不要**遞增 continue count（這是讓 SLIM 降級回 FULL 的方法）
- `modify` → 改計畫（共變項、結局等），改完重產 config
- `pause` → 設 `pipeline_state = "paused"`，存檔

## 方法學替代必須逐條表態才過得了 manuscript

`manifest.json$.methodological_warnings[]` 的每一條都有一個內容衍生的 ID（`SUB-` + sha256 前 8 碼，所以重產不會換號，但**改動內容會讓先前的表態失效**）。runtime 也會補進兩種：`--skip-precheck` 會自己變成一條，QC 輸出裡的 PH／competing risk／immortal time／positivity／separation／convergence／EPV 字樣也會被收成 `runtime_qc` 替代。

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_pipeline.py <PLAN> --list-substitutions
python3 ${CLAUDE_SKILL_DIR}/scripts/run_pipeline.py <PLAN> --accept-substitution SUB-1a2b3c4d:已與指導教授確認採 cause-specific
```

- **理由不可空白**——「accepted 但沒寫理由，跟沒讀過是同一件事」，空理由會被拒絕並 exit 2。
- **未表態的會在 pre-manuscript briefing 變成 blocker**，重跑不會讓它消失。
- **`rejected` 也一樣擋**——因為拒絕了但計畫沒改，那條替代仍在。要真的解掉就得回去改計畫。

## Statistical QC Gates (both modes)

Scripts emit QC results to stderr with prefixes. The runner captures these:

**Blocking** (step marked `error`, pipeline handles gracefully):
- 0 events in any group
- Model convergence failure
- HR/OR = Inf, NaN, or ≤ 0

**Warning** (informational, displayed at checkpoint):
- n < 30 in any group (note: for survival analysis, events per group is a better metric than total n)
- Events < 10 per group (for Cox/logistic regression models)
- HR/OR > 10 or CI width > 100 (consider also flagging HR/OR > 5 as soft warning)
- \> 20% missing for any variable
- \> 50% missing for any variable → mandatory sensitivity analysis justification required (do NOT auto-remove; valid MI can handle high missingness if MAR holds — Madley-Dowd 2019)
- PH assumption borderline：`0.01 <= p < 0.05`（見下）

## PH 假設違反 ★ 這一段的四個值只有一個 pipeline 真的會算

**門檻是固定的 0.01 / 0.05，不隨 n 調整**（舊版寫「p < 0.05；n > 5000 時改用 0.01」，那是錯的）：

| Schoenfeld 全域 p | 行為 |
|---|---|
| **`p < 0.01`（`PH_ALPHA`，rank transform）且 `ph_violation_remedy` 沒填** | **Blocking** —— multivariate step 標 `error`，依賴它的 step 變 `blocked` |
| `p < 0.01` 且 remedy 有填 | 降成 warning，內容依 remedy 而不同（見下表） |
| **`0.01 <= p < 0.05`（`PH_ALPHA_REVIEW`）** | Warning，**不擋**。但 reviewer challenge 的 domain 5 **必須逐條表態**（dismiss + 理由，或 escalate），不得沉默通過 |

**宣告位置：`outcomes[<id>].ph_violation_remedy`，逐 outcome。寫在計畫頂層會被靜默忽略**——那個位置就是強制手段（指紋雜湊 `outcomes`，所以事後補填會讓既有的 reviewer challenge 失效，這正是「事前指定」可被檢查的原因）。

| remedy | pipeline 幫你算嗎 | 你要做什麼 |
|---|---|---|
| `disclose` | ✅ 這個 step 就處理完 | 填 `outcomes[<id>].ph_disclose_decision_id`，並寫進 Limitations。**沒填 → manuscript 階段的 `ph_remedy_gate.py` 擋** |
| `stratify` | ✅ **自動補 `ph_stratified_<outcome>`** | 通常什麼都不用做。要事前點名分層變項才填 `outcomes[<id>].ph_strata_variables` |
| `time_varying` | ✅ **自動補 `ph_time_varying_<outcome>`** | **填 `outcomes[<id>].tv_cut_points`**（時間窗切點）。不填也會跑，但 manuscript gate 會擋 |
| `rmst` | ✅ **自動補 `ph_rmst_<outcome>`** | **填 `outcomes[<id>].rmst_tau`（數值）或 `rmst_tau_rule`（規則名）**。不填也會跑，但 manuscript gate 會擋 |

三個 remedy step 都需要 `plan_schema_version: 2`（舊 plan 只會被告知，跑 `--migrate` 才套用），都**另出一張表**而不去動 multivariate 那張——在同一支腳本裡加 `strata=` 會讓 Sheet 1 失去被分層變項的 HR、Sheet 2 卻還是未分層模型，同檔兩張表兩套假設（2026-08-12 裁決爭議五）。三者都寫 evidence sidecar，`ph_remedy_gate.py` 據以**驗內容**：

> - **`stratify`**：實際分層的變項要涵蓋 PH 檢定真正判定違反的變項。曝險本身違反、或違反的是連續變項 → **拒絕執行（exit 2）**並指向 `time_varying` / `rmst`，不會靜默替你分箱。
> - **`time_varying`**：做成隨時間變的變項要涵蓋真正違反的變項，**且時間窗必須來自 plan**。實作是預先指定時間窗的分段常數 HR（`CoxTimeVaryingFitter` + start/stop；每人最多切點數 +1 列）。
> - **`rmst`**：唯一要辯護的是 **tau 來自 plan**——估計是到 tau 為止的積分，看完結果才選 tau 是這個方法全部的 p-hacking 面。⚠ 目前的實作是**未校正**的（各組 KM），是 estimand 的改變，sidecar 記 `adjusted: false`、gate 每次都 warn。
>
> **切點與 tau 沒宣告時不是死路**：分析照跑、表照出（作者看得到數字與確切的修法），擋的是 manuscript gate。這是刻意的——把人擋在沒有出口的門前比放行更糟。
>
> **自建的 step 仍然認得**，`ph_remedy_gate.py` 認的是：① step 的 **id 或 skill 含特定字串**（`stratify`→`stratif`；`time_varying`→`time_varying`/`timevarying`/`extcox`/`extended_cox`/`tvc`；`rmst`→`rmst`）② 該 step 宣告的產物真的在磁碟上（不帶副檔名的 stem 也算，會比對 `<stem>.*`）。**沒有 evidence sidecar 的自建 step 走的是舊路徑**：只驗檔案存在，manuscript 前要作者具名簽字。

完整規格見 `references/checkpoint_protocol.md` 與 `references/plan_template.md`。

## Safety Limits

- **Step timeout**: 600 seconds per step
- **Max retry**: 1 per step
- **Max total steps**: 80 across all runs (initial + re-runs). If exceeded, force pause with warning.

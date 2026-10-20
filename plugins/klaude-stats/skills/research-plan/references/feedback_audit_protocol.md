# Feedback Audit Protocol

Defines the complete advisor feedback processing workflow for the biostatistics pipeline.
Adapted from academic-pipeline's Post-Review Socratic Revision Coaching + agentic-data-scientist's Loop Detection.

---

## Overview

When the user provides advisor feedback (typically a `.docx` file with tracked changes and comments), this protocol defines a 7-step audit process: Extract → Classify → Impact Analysis → Socratic Discussion → Version Backup → Selective Re-run → Diff Report.

**Trigger phrases**: 「老師給了意見」「advisor feedback」「教授回饋」「修改統計」「re-run pipeline」「重跑分析」「老師意見」

---

## Step A: Feedback Extraction

```bash
python ${CLAUDE_SKILL_DIR}/scripts/process_feedback.py <FEEDBACK.docx> \
  --output <OUTPUT_DIR>/feedback_parsed.md \
  --plan-path <OUTPUT_DIR>/research_plan.json \
  --backup
```

This extracts feedback from both formats advisors commonly use:
- **Tracked changes + comments**: parses `<w:ins>`, `<w:del>`, `<w:comment>` XML tags
- **Plain text paragraphs**: extracts all paragraph text

The `--backup` flag triggers automatic version backup (Step E below).

### Input
Advisor's annotated `.docx` file containing:
- Tracked Changes (insertions + deletions)
- Margin Comments (批註)
- Plain Text Paragraphs (內文批注)

### Output
Two files:
1. `feedback_parsed.md` — human-readable markdown (existing format)
2. `feedback_structured.json` — machine-readable structured data (NEW)

### Structured JSON Schema

```json
{
  "version": 2,
  "feedback_file": "advisor_feedback_v2.docx",
  "extracted_at": "2026-04-02T14:30:00",
  "plan_version_at_extraction": 1,
  "items": [
    {
      "id": "FB-001",
      "source": "comment",
      "raw_text": "BMI 應該用 continuous 不要 binary",
      "context": "Table 1 中 BMI 被分為 ≥30 vs <30",
      "category": null,
      "affected_steps": [],
      "priority": null,
      "config_changes": [],
      "resolution": null
    }
  ],
  "summary": {
    "total_items": 0,
    "by_source": {"comment": 0, "insertion": 0, "deletion": 0, "text": 0},
    "by_category": {}
  }
}
```

---

## Step B: Structured Classification

Claude classifies each feedback item into one of 6 categories using the rules below.

### Category Definitions

| Category | Description | Typical Examples |
|----------|-------------|-----------------|
| `variable_change` | Variable definition modification | Change type (binary→continuous), add/delete variable, change encoding |
| `outcome_change` | Outcome modification | Change endpoint, change time scale, add/delete outcome |
| `covariate_change` | Covariate adjustment | Add/delete covariate, change reference category |
| `method_change` | Methodology modification | Change exclusion criteria, change matching caliper, add/delete analysis type |
| `population_change` | Study population modification | Change inclusion/exclusion criteria |
| `presentation_change` | Presentation modification | Change chart format, axis labels, text description |

### Classification Rules

Apply in order (first match wins):
1. If feedback mentions inclusion/exclusion criteria, patient selection → `population_change`
2. If feedback mentions adding/removing/changing an outcome or endpoint → `outcome_change`
3. If feedback mentions changing a variable's type, encoding, or definition → `variable_change`
4. If feedback mentions adding/removing covariates or changing reference categories → `covariate_change`
5. If feedback mentions statistical methods, matching parameters, analysis types → `method_change`
6. If feedback only mentions formatting, labels, axis, colors, text → `presentation_change`

---

## Step C: Impact Analysis

### Automatic Impact Mapping

Each category maps to affected pipeline steps:

```
population_change     → ALL steps (flowchart + table1 + all outcomes + psm + auc + manuscript)
outcome_change        → km_{id} + cr_{id} + uni_{id} + multi_{id} + manuscript
variable_change       → table1 + uni_* + multi_* + psm + auc
covariate_change      → uni_* + multi_*
method_change         → depends on specific change (Claude determines)
presentation_change   → only the specific affected step
```

### Impact Matrix Format

```
━━━ Feedback Impact Matrix ━━━

FB-001: BMI 改為 continuous
  Category: variable_change
  Affected: table1, uni_primary, uni_secondary_1, multi_primary, multi_secondary_1, psm, auc
  Config changes: covariates[BMI].type = "continuous", remove label_map

FB-002: 加入 eGFR 作為 covariate
  Category: covariate_change
  Affected: uni_primary, uni_secondary_1, multi_primary, multi_secondary_1
  Config changes: covariates += {name: "eGFR", column: "eGFR_Dis", type: "continuous"}

Total affected steps: 8/12
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Config Change Specification

For each feedback item, Claude specifies the exact JSON path changes needed:
```json
{
  "id": "FB-001",
  "config_changes": [
    {"path": "covariates[name=BMI].type", "from": "binary", "to": "continuous"},
    {"path": "covariates[name=BMI].label_map", "action": "delete"}
  ]
}
```

---

## Step D: Socratic Feedback Discussion (opt-in)

Adapted from academic-pipeline's Stage 3→4 Transition Coaching.

> ### 📌 待使用者裁決：這一整節要不要保留
>
> **這是純 Claude 行為，沒有任何程式強制**——`scripts/` 裡沒有東西執行、計數或檢查這 5 輪對話。2026-08-12 的文件同步把它標記為**待決**，**沒有自行刪除**。
>
> 兩邊的論點：
> - **保留**：`affected_steps >= 3` 的改動常常有使用者沒預期到的連鎖效應（新共變項與既有變項共線、換 outcome 定義讓事件數掉到 EPV 以下）。先講一輪比跑完再發現便宜。
> - **刪除**：Step C 的 Impact Matrix 已經把受影響範圍算出來了，而下方的對話範本偏長；使用者趕時間時這一節多半被跳過，等於維護一段沒人走的路。
>
> **在使用者決定之前照現況執行**（opt-in，觸發條件見下）。

### Trigger Conditions
- `affected_steps` >= 3 → offer discussion
- `affected_steps` <= 2 → skip (too minor)
- All items are `presentation_change` → skip

### Skip Conditions
- User says 「直接改」「不用討論」「just fix it」→ skip entirely
- User says 「ok」after 2 rounds → respect and stop
- Maximum 5 rounds

### Dialogue Template

```
Round 1: "教授的回饋中，哪一條你覺得影響最大？為什麼？"
         → Help user understand cascading effects

Round 2: "{Variable} 從 {old_type} 改成 {new_type} 後，你預期結果方向會改變嗎？"
         → Build statistical intuition before seeing results

Round 3: "加入 {new_covariate} 後，如果跟 grouping variable 高度共線，你會怎麼處理？"
         → Surface potential problems proactively

Round 4: "這次有 {n}/{total} 步驟需要 re-run。先跑 table1 看新 baseline，還是全部重跑？"
         → Guide re-run strategy

Round 5: Summary of user decisions, confirm action plan
```

### Coaching Rules
- Each response 100-200 words, ask more than answer
- First acknowledge what the advisor feedback addresses well
- Never judge the advisor's feedback quality

---

## Step E: Version Backup

**`--backup` 需要同時給 `--plan-path`**，否則靜默不備份。

**腳本做的**（`process_feedback.py --backup --plan-path ...`）：

1. Read current `research_plan.json` → version = N
2. Backup: `research_plan.json` → `research_plan_v{N}.json`
3. Backup outputs: `mkdir <OUTPUT_DIR>/v{N}/` → copy all .xlsx, .png, .docx, .csv
4. Backup configs into `v{N}/configs/`（**全部** config，不只受影響的）
5. Bump `version` → N+1、append `version_history`、set `pipeline_state = "feedback"`、存回 plan

> 若 `research_plan_v{N}.json` 已存在但 plan 仍停在版本 N，腳本會**以 exit 3 中止**而不是覆蓋。這代表上一輪的版本沒有正確遞增；先去看那份舊快照，別讓它被蓋掉。

**Claude 做的（腳本不會做，要自己執行）**：

6. 依 Step C 的 Impact Matrix，把受影響的 step 標成 `status = "needs_rerun"` —— 沒做這一步，Step F 的「只重跑受影響的」會變成什麼都不跑（未帶 `--from` 時 `done` 的 step 一律跳過）
7. 把本輪的分類結果寫進 `feedback_rounds[]`
8. 把每一項回饋登記進 `decision_log.md`（Step H），舊決策標 `superseded`、開新 ID

### Version Bump Sequence

```
1. Read current research_plan.json → version = N
2. Copy research_plan.json → research_plan_v{N}.json
3. Create backup directory: mkdir v{N}/
4. Copy all output files to v{N}/: cp *.xlsx *.png *.docx v{N}/
5. Copy affected configs: cp configs/{step}_config.json → configs/{step}_config_v{N}.json
6. Update version_history in plan:
   append {"version": N+1, "created_at": ISO_NOW, "reason": "advisor feedback: {summary}"}
7. Update feedback_rounds:
   append {"round": R, "version_transition": "N→N+1", "changes": count, "affected_steps": count, ...}
8. Mark affected steps: status = "needs_rerun"
9. Set pipeline_state = "feedback"
10. Save research_plan.json (now version N+1)
```

### Backup Directory Structure

```
output_dir/
├── research_plan.json              (v{N+1}, current)
├── research_plan_v{N}.json         (v{N}, backup)
├── v{N}/                           (v{N} outputs backup)
│   ├── Table1.xlsx
│   ├── KM_primary.xlsx
│   └── ...
├── configs/
│   ├── manifest.json
│   ├── table1_config.json          (v{N+1}, regenerated)
│   └── table1_config_v{N}.json     (v{N}, backup)
├── logs/
│   └── feedback_audit_v{N+1}.json  (structured feedback record)
└── ...
```

---

## Step F: Selective Re-run

### Re-run Strategy

1. Regenerate only affected configs:
   ```
   generate_configs.py research_plan.json --only step1,step2,...
   ```
   > 帶 `--only` 時**自動補 step 的機制整段關閉**（不會偷偷加 `rcs_*` 或 `strobe`）。`--only` 也不能跟 `--migrate` 併用。

2. Execute pipeline (auto-detects `needs_rerun` steps):
   ```
   run_pipeline.py research_plan.json
   ```
   > **重產 config 這件事本身就會讓相關的 `done` step 自動降級成 `needs_rerun`** —— 啟動時 `mark_stale_steps()` 比對 `config_sha256`，內容變了就降級。所以就算 Step E 第 6 點漏標，改過設定的 step 仍然會重跑。
   >
   > **但它救不了「設定沒變、只是決策變了」的情況**（例如老師要求換參考組但你還沒改 config）。Step E 第 6 點的手動標記仍然必要，只是不再是唯一防線。

3. Special handling for `population_change`:
   - Run flowchart FIRST (re-calculate N)
   - MANDATORY checkpoint after flowchart:
     ```
     "收案人數從 N={old_n} 變為 N={new_n}，{change_direction} {abs_change} 人。確認繼續？"
     ```
   - If user confirms → run remaining steps
   - If user rejects → pause, discuss

---

## Step G: Diff Report

```bash
python ${CLAUDE_SKILL_DIR}/scripts/pipeline_status.py <OUTPUT_DIR>/research_plan.json --diff {N}
```

> **`--diff` 只做檔案層級的清單比對**（哪些輸出檔新增、消失、大小改變）。它**不會**開啟 Excel、不會讀 HR/OR/CI/p。下面這份數值 diff 是 **Claude 讀 `v{N}/` 與現行輸出的 Excel 之後自己寫的**，不是程式算出來的——所以每個數字都要標明來自哪個檔的哪一格，並且比照 `delivery_discipline.md` §1 規則 1（數字單一來源）。

### Comparison Logic

1. Read key metrics from `v{N}/` backup Excel files
2. Read key metrics from current output Excel files
3. Compare:
   - Sample sizes (N, n per group)
   - Effect estimates (HR, OR, aHR, aOR)
   - Confidence intervals
   - P-values
   - Survival rates at time points
   - AUC/C-statistics

### Diff Report Format

```
━━━ Re-run Comparison (v{N} → v{N+1}) ━━━

FB-001 ({description}):
  Univariate (primary): HR {old} [{old_ci}] → HR {new} [{new_ci}]
  Multivariate (primary): aHR {old} [{old_ci}] → aHR {new} [{new_ci}]
  {significance_change_note if applicable}

FB-002 ({description}):
  {comparison_lines}

Sample size impact: N={old_n} → N={new_n} ({change})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Significance Change Flags

- Direction change (HR > 1 → HR < 1): `🔴 Direction changed`
- Significance threshold crossed (p < 0.05 ↔ p >= 0.05): `🔴 Significance changed`
- Large magnitude change (> 100%): `🔴 Major magnitude shift`
- Moderate magnitude change (> 50%): `🟠 Substantial magnitude shift`
- Notable magnitude change (> 20%): `🟡 Notable magnitude shift`
- Confidence interval overlap lost between versions: `🟠 CI no longer overlaps`

After presenting the diff report, this is a **MANDATORY checkpoint** — user must confirm the new results before proceeding.

---

## Feedback Loop Safety

### Max Feedback Rounds

Default: `max_feedback_rounds = 3` (configurable in plan JSON)

**這條上限現在由 `run_pipeline.py` 的 `check_feedback_rounds()` 強制**（2026-08-11 起；此前只是一段給模型看的規則）：

| 已記錄的輪數 vs `limit` | 程式行為 |
|---|---|
| `rounds < limit` | 照跑 |
| `rounds >= limit` | 印 ⚠ 警告（「這麼多輪通常代表分歧不是統計問題」），**照跑** |
| `rounds >= limit + 1` | ⛔ **回 False → `run_pipeline.py` 以 exit 2 中止** |

**唯二的放行方式**：`run_pipeline.py <plan> --override-feedback-rounds`（會印一行「上限已被覆寫」留痕），或在計畫裡調高 `max_feedback_rounds` **並在 `decision_log.md` 寫明理由**。

| Round | Behavior |
|-------|----------|
| 1 | Normal flow [A]→[G] |
| 2 | Normal flow + "已進入第 2 輪修改" notice |
| 3 | Normal flow + limit warning（程式印，**不擋**） |
| 4+ | **程式擋，exit 2。** 要 `--override-feedback-rounds` 才過 |

### Round 3 Warning

```
━━━ ⚠ 已達 3 輪修改上限 ━━━
累計變更：
  - v1→v2: {changes_1}
  - v2→v3: {changes_2}
  - v3→v4: {changes_3}

建議：
  1. 與指導教授安排面對面會議，釐清研究方向
  2. 帶著 v1 vs v4 的 Diff Report 去開會
  3. 如果確定需要第 4 輪，輸入 "override" 繼續

Options: [1] 結束 pipeline  [2] Override 繼續  [3] 匯出完整修改歷史
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 80-Step Safety Limit

`run_pipeline.py` tracks `total_steps_executed` across all runs (initial + re-runs).
If total exceeds `max_total_steps` (default 80) → force pause with warning:

```
⚠ Pipeline safety limit reached: {total} / {max} steps executed.
This includes {n_initial} initial + {n_rerun} re-run steps across {n_rounds} feedback rounds.
Raise `max_total_steps` in research_plan.json to continue, or review whether the research plan needs fundamental restructuring.
```

---

## Step H: Change-control ledger (變更控制紀錄) ★ Mandatory whenever a decision changes

Steps A–G re-run the analysis correctly. They do **not** leave a record of *what the old decision was and why it changed* — and once a report has been handed to an advisor, that record is what lets anyone (including the advisor, a reviewer, or you six months later) tell which numbers moved and on whose instruction. Do this **in addition to** A–G, never instead of.

**Three rules, no exceptions:**

1. **Never overwrite a decision in place. Supersede it.** Every decision carries a permanent ID (`A1`, `B5`, `C3`…). IDs are **never reused and never renumbered** when rows are inserted — reports, verification documents and rebuttal letters cite them. Mark the old row `superseded`, keep it, and add a **new row with a new ID**.
2. **Every decision row carries a status**: `active` (in force; the reported numbers come from it) / `superseded` (replaced — prefix the method cell with `~~已取代 → 見 <new ID>~~`) / `withdrawn` (recorded but never adopted, e.g. the advisor rejected it).
3. **Append one ledger row per change**: date, who asked, `old ID → new ID`, one-line reason, which scripts must be re-run.

**Where the ledger lives:**

| Project shape | Ledger location |
|---|---|
| Has `research_plan.json` (this skill's normal path) | `version_history` + `feedback_rounds` in the plan JSON, **plus** a human-readable `decision_log.md` change-control section so the advisor can read it without parsing JSON |
| **Manual statistics project — numbered scripts + `data/*_stats.json`, no `research_plan.json`** | `report/decision_log.md`, final section, table `日期 / 提出者 / 舊 ID → 新 ID / 理由 / 需重跑`（骨架 `${CLAUDE_SKILL_DIR}/assets/templates/decision_log_skeleton.md` §H）. This skill runs in **discipline-only mode** for such projects (see Mode Selection): it does **not** take over the statistics or rewrite the numbered scripts, but it does own the ledger, the verification protocol and the watchdog gate |

**What triggers the ledger** (same test as "does this need a re-run"):

| Change | Ledger + re-run? |
|---|---|
| Cohort definition, endpoint, any threshold or cut-point | **Yes** |
| Statistical method (model, imputation, selection, validation) | **Yes** |
| Advisor rejects an approach and asks for a different one | **Yes** (the rejected one becomes `withdrawn`, not deleted) |
| Report wording / layout / section order only | No ledger, but still re-run any citation-resolution and document-build steps, or the delivered file silently diverges from its source |
| Typo or dead path | No |

**Close the loop with a freshness check.** After re-running, verify that every machine-generated stats file is newer than both the dataset and its generating script, and that the delivered document is newer than its markdown source. A project with a staleness watchdog should exit 0 before the change is called done; a project without one should at minimum have the timestamps compared by hand. **A ledger entry with no re-run behind it is worse than no entry — it asserts a change that the numbers do not reflect.**

> **Why this exists**: In one real project, Independent verification found nine severe issues in a report that had already been through one verification round; the dominant failure mode was not arithmetic (543 values checked, 9 genuinely wrong) but **claims that had been superseded and never retracted** — a novelty claim refuted weeks earlier still sat in the "if you only say three things" section, and the header still advertised the previous verification round as fully resolved when one item had only been disclosed, not fixed. Both would have been caught by an append-only ledger with statuses. Full case: that project's `report/decision_log.md` section H and `report/VERIFICATION.md`.

---

## Complete Flow Diagram

```
教授回饋 .docx
    │
    ▼
[A] Extract ──→ feedback_parsed.md + feedback_structured.json
    │
    ▼
[B] Classify ──→ Each item gets category
    │
    ▼
[C] Impact Analysis ──→ Impact Matrix (which steps affected)
    │
    ▼
[D] Socratic Discussion (opt-in, ≥3 steps)
    │  ├─ Understand cascading effects
    │  ├─ Predict result direction
    │  └─ Decide re-run strategy
    │
    ▼
[E] Version Backup ──→ v{N}/ + research_plan_v{N}.json
    │
    ▼
[F] Selective Re-run ──→ Only affected steps
    │  ├─ population_change → MANDATORY after flowchart
    │  └─ Others → direct re-run
    │
    ▼
[G] Diff Report ──→ v{N} vs v{N+1} comparison
    │
    ▼
[H] MANDATORY Checkpoint ──→ User confirms new results
    │  ├─ Accept → update manuscript (if needed)
    │  └─ More changes → back to [A] (subject to max_feedback_rounds)
```

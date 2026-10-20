# Pipeline State Machine

Defines the formal state model for the biostatistics pipeline.
Adapted from academic-pipeline's state machine with biostatistics-specific simplifications.

---

## Step States (7 types)

| State | Description | Icon |
|-------|-------------|------|
| `pending` | Not yet started | `○` |
| `running` | Currently executing | `▶` |
| `done` | Completed successfully | `✓` |
| `error` | Failed (check log) | `✗` |
| `needs_rerun` | Marked for re-execution after feedback, **or the step's config changed since it last ran** | `↺` |
| `skipped` | **只有兩個來源：`--skip`，以及 `pipeline_profile: "explore"` 停放投稿專用步驟** | `⊘` |
| `blocked` | Dependency failed, or the step's config file was deleted | `⊗` |

> **`skipped` 不會因為「偵測到既有輸出」而被寫入。** 舊版這一列寫「mid-entry detected existing output」，但 `report_detection()` 是唯讀的，明確拒絕改任何狀態；沒有排到的 step 回報的字串是 `not_scheduled`，也不是 `skipped`。**唯二**的寫入者是 `apply_skips()`（只在有 `--skip` 時被呼叫）和 profile 停放（會同時寫 `skip_reason: "profile"`）。
>
> `--skip` 只接受目前是 `pending` 或 `done` 的 step（`SKIPPABLE_FROM`），其他狀態會出聲拒絕。

> **`error` 是失敗的正式拼法**，沒有 `failed` 這個狀態。

## Legal Step Transitions

```
pending ──→ running          (execution starts)
running ──→ done             (success)
running ──→ error            (failure)
done    ──→ needs_rerun      (feedback marks for re-execution)
error   ──→ running          (retry, max retry_count=1)
needs_rerun ──→ running      (re-execution starts)
done    ──→ needs_rerun      (config_sha256 drift — 每次啟動自動偵測)
pending ──→ skipped          (--skip，或 explore profile 停放)
done    ──→ skipped          (--skip；SKIPPABLE_FROM = pending / done)
skipped ──→ pending          (submit profile 解除 skip_reason=="profile" 的停放)
done    ──→ blocked          (該 step 的 config 檔被刪了)
any     ──→ blocked          (dependency in error/blocked state)
```

## Prohibited Step Transitions

- `done` → `pending` — cannot undo without going through `needs_rerun`
- `blocked` → `running` — must resolve blocker first
- `skipped` → `running` — 要先回到 `pending`。**唯一自動做這件事的是 submit profile 解除停放**，而且只解除帶 `skip_reason: "profile"` 的；手動 `--skip` 的永遠要人自己改
- `error` → `done` — must go through `running` again

---

## Pipeline Global States (6 types)

| State | Description |
|-------|-------------|
| `planning` | Steps 1-4: interactive planning phase (study design, variable mapping, plan generation) |
| `running` | Steps 5-6: execution phase (mid-entry detection + pipeline execution) |
| `awaiting_review` | HITL checkpoint active, waiting for user decision |
| `paused` | User explicitly paused the pipeline |
| `feedback` | Processing advisor feedback (Step 7) |
| `completed` | All steps done or user terminated |

## Legal Pipeline Transitions

```
planning ──→ running           (plan confirmed, execution starts)
running  ──→ awaiting_review   (HITL checkpoint reached)
awaiting_review ──→ running    (user says "continue")
awaiting_review ──→ paused     (user says "pause")
running  ──→ completed         (all steps done)
running  ──→ feedback          (user provides advisor feedback mid-run)
paused   ──→ running           (user resumes)
feedback ──→ running           (re-run affected steps)
any      ──→ completed         (user terminates pipeline)
```

---

## Analysis Groups

Steps are organized into groups for parallel execution and HITL checkpoints.

| Group | Group ID | Steps | Depends On | Parallel Within Group |
|-------|----------|-------|-----------|----------------------|
| Foundation | `foundation` | flowchart, table1, missingness | None | Yes (all independent) |
| Per-outcome (×N) | `outcome_{id}` | km_{id}, cr_{id}, uni_{id} | Foundation | Yes (three independent) |
| Per-outcome (×N) | `outcome_{id}` | multi_{id}, rcs_{id}, robust_{id}, landmark_{id}, mi_{id} | uni_{id} / multi_{id} | No (depends on uni/multi) |
| Supplementary | `supplementary` | psm, auc, **calibration, weighting, evalue** | Foundation | Yes |
| Manuscript | `manuscript` | **strobe, reviewer_challenge,** manuscript | All above | No (needs all outputs) |

> 分組由 `run_pipeline.py` 的 `group_steps_by_analysis_group()` 依 **skill** 決定，不是依 step id。`SUPPLEMENTARY_SKILLS` 現在含 `psm-matching`、`auc-cstat`、`calibration`、`weighting`、`evalue`；manuscript 群組含 `manuscript-results`、`strobe`、`reviewer-challenge`。

### Group Execution Order

```
[Foundation] ──→ [Per-outcome: primary] ──→ [Per-outcome: secondary_1] ──→ ... ──→ [Supplementary] ──→ [Manuscript]
```

Within each group, independent steps run in parallel using `concurrent.futures.ThreadPoolExecutor` (`max_workers=min(4, n)`). Threads, not processes: the steps are subprocess launches, so the GIL is not the bottleneck and a shared plan object stays addressable.
Sequential steps (multi depends on uni) run after independent steps complete.

### HITL Checkpoint Triggers

In `--hitl` mode:
- Foundation → **MANDATORY**，會停（sample size affects all downstream）
- Per-outcome → FULL 或 SLIM（adaptive）。**SLIM 不會停**，見 `checkpoint_protocol.md`
- Supplementary → FULL + `synthesis`；本次沒排到 pre-manuscript 閘門時升級 MANDATORY，會停
- Manuscript → **MANDATORY**，而且是 **`pre_checkpoint`：在該群組執行之前觸發**，不是之後。有 blocker 時**兩種模式都停**

**auto 模式沒有群組後 checkpoint。** 整個 `if (hitl or halt_in_auto) and ...` 區塊在 auto 底下只有被特別標記強制停的群組會走到；auto 模式真正會停下來的只有 pre-manuscript briefing（且有 blocker 時）。

---

## Safety Limits

| Limit | Value | Triggered Action |
|-------|-------|-----------------|
| `max_retry_count` per step | 1 | Mark as `error`, continue to next independent step |
| `max_feedback_rounds` | 3 (configurable) | Warn user, suggest face-to-face meeting with advisor |
| `max_total_steps` | 80 | Cumulative across every run; persisted to `research_plan.json$.total_steps_executed`. Force pause, prevent infinite re-run loops |
| Step execution timeout | 600 seconds | Kill subprocess, mark as `error` |

---

## Mid-Entry Detection Rules

Before pipeline execution, scan `output_dir` for existing output files:

**`--detect-only` 是唯讀的**：它印出每個 step 的 `status`、磁碟上有沒有輸出檔、以及下一次執行會跑什麼，**不改任何狀態**。

1. 決定跑不跑的是 **`status`，不是檔案在不在**。`status="done"` 就不重跑（未帶 `--from` 時）。
2. 檔案存在但 `status` 不是 `done` → 印 **⚠ 孤兒輸出**警告，下次執行會覆蓋它。
3. 檔案不存在 → 維持 `pending`。

### Config 漂移偵測（取代舊的「版本對不對得上」）

舊版第 3 點寫「versions don't match → warn」，但當時 manifest 根本沒有版本或雜湊可比。**現在有了，比的是 `config_sha256`，不是 plan version**：每個 step 執行前把它的 config 檔雜湊起來寫進 step，之後每次啟動由 `mark_stale_steps()` 比對一次。

| 比對結果 | 行為 |
|---|---|
| 一致 | 維持 `done` |
| **`drifted`**（config 內容變了） | **降級成 `needs_rerun`** + 寫 `stale_reason` |
| **`config_missing`**（config 檔被刪了） | 降級成 `blocked`，`blocked_by = "(config file deleted)"` |
| **`unstamped`**（沒有記錄過雜湊） | 印出來提醒，**不降級**——那是這個機制之前跑的舊輸出，無從判定 |

**兩個要記住的性質**：
- 這個降級**每次啟動都對整條 pipeline 的每個 `done` step 跑一次**，**跟有沒有帶 `--only` 無關**（`--only` 只影響哪些 step 會被執行，不影響漂移標記）。
- `--detect-only` 底下同樣的比對**只印警告、不改狀態**。

Present detected files to user for confirmation before proceeding.

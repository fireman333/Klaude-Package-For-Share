# Survival Pre-flight Diagnostics — Step 3.5 的執行協定與四個 plan-time 硬閘門

**這份是 SKILL.md Step 3.5 的規則本體**（2026-09-07 從 SKILL.md 搬出，內容未改）。SKILL.md 只留入口段：何時觸發、跳過條件、閘門會擋什麼、放行怎麼走。

相關：`diagnostics` 區塊的欄位語意、canonical flag 名與別名、偽 flag `diagnostics_off` 見 `plan_template.md`〈`diagnostics` 區塊語意〉；R driver 本身屬 `${CLAUDE_SKILL_DIR}/../survival-diagnostics/`。

---

## 執行協定
**When to run:** After `research_plan.json` is written, if `pipeline[]` contains any of `kaplan-meier`, `competing-risk`, `univariate-forest`, `multivariate-interaction` (i.e. time-to-event analyses).

**Skip condition:** `research_plan.json$.diagnostics.mode = "off"` OR no survival steps in pipeline.

**Workflow:**

1. Build `<OUTPUT_DIR>/diagnostics/diagnostic_config.json` from the primary survival outcome:
   ```json
   {
     "data_file": "{study.data_file}",
     "filters": [{population.filters}],
     "time_column": "{primary.time_column}",
     "event_column": "{primary.event_column}",
     "id_column": "{study.id_column or null}",
     "cluster_column": "{study.cluster_column or null}",
     "entry_column": null,
     "candidate_covariates": [...from covariates[] name field, cap at 10 clinically key ones],
     "output_dir": "<OUTPUT_DIR>/diagnostics"
   }
   ```

2. Invoke the R driver (note: `LANG=en_US.UTF-8` required for non-ASCII paths on macOS):
   ```bash
   LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 Rscript ${CLAUDE_SKILL_DIR}/../survival-diagnostics/scripts/survival_diagnostics.R <OUTPUT_DIR>/diagnostics/diagnostic_config.json
   ```

3. Read `<OUTPUT_DIR>/diagnostics/diagnostic_report.json`. Write `research_plan.json$.diagnostics`。**`mode: "completed"` 時有四個欄位是必填**，`generate_configs.py` 逐項驗，缺一個就 `[FATAL]` 退出（詳細語意見 `references/plan_template.md` 的 `diagnostics` 一節）：

   | 欄位 | 驗什麼 |
   |---|---|
   | `report_path` | 相對路徑對 `output_dir` 解析，**檔案必須真的在磁碟上** |
   | `completed_at` | ISO timestamp，且**資料檔的 mtime 不得晚於它**（資料換過、診斷沒重跑 → FATAL） |
   | `data_fingerprint` | `study.data_file` 的 sha256 前 16 碼。對不上 → FATAL；`plan_schema_version >= 2` 時**缺這個欄位本身就是 FATAL** |
   | `flags_detected` | 三種形狀都收：`["clustering"]`／`{"clustering": true}`／`{"clustering": {"detected": true, "risk": "high"}}`。**認不得的 flag 名會直接報錯**，不會被當成沒事 |

4. **四個 flag 是 plan-time 硬閘門，不是建議**（2026-08-12 起）。`generate_configs.py` 的 `_validate_diagnostics_honored()` 在**產 config 之前**檢查；擋下來時它印 `[FATAL] ... Step 3.5 detected N condition(s) the pipeline does not handle` 並**以 exit 1 中止**，一個 config 都不會產生。

   | flag | 要有的補救 step（skill） | 沒補救會怎樣 |
   |---|---|---|
   | `competing_risk` | `competing-risk` | 擋。只影響 **time-to-event outcome** |
   | `left_truncation` | **沒有任何補救 step** | **一定擋。** pipeline 裡沒有任何 skill 處理延遲進入——risk set 混進尚未受觀察的人會讓 KM 與 Cox **偏誤**，不是資訊不足。寫進 limitations 等於發表一個附註解的錯數字。只能改 time origin，或在 pipeline 外算完再帶結果進來 |
   | `time_varying` | `immortal-time` | 擋。`risk` 是 `low` / `none` 時放行；**沒記 risk 等級一律視為觸發** |
   | `clustering` | `robust-variance` | 擋 |

   **兩個容易誤判成「已經處理了」的地方**：
   - **覆蓋是逐 outcome 算的。** 幫 primary 加了 `robust-variance` 不會讓 secondary 過關。
   - **有 step 但參數沒填 = inert，不算數。** `robust-variance` 沒有 `cluster_column`、`immortal-time` 沒有 `exposure_time_column`、landmark 模式沒有 `landmark_times` —— 這三種都會被點名 `Present but inert`。

5. **放行只有一條路：per-flag 的 `diagnostics.overrides.<flag>`。**

   ```jsonc
   "diagnostics": {
     "overrides": {
       "clustering": {
         "decision_id": "D-017",
         "reason": "單一中心收案，群集僅為採檢批次，與結果無關",
         "outcomes": ["primary", "secondary_1"]
       }
     }
   }
   ```

   四個條件**全部**成立才放行，任一不成立就照擋並印出理由：

   | 條件 | 細節 |
   |---|---|
   | `decision_id` 格式對 | 必須 `fullmatch` `#\d+` 或 `Xxx-yyy`（大寫開頭、至少一段連字號）。`D-017`、`RP-2026-04`、`#42` 可以；`d17`、`abc` 不行 |
   | 該 ID **真的存在於 `decision_log.md`** | 路徑取 `plan.decision_log`，沒設就是 `<output_dir>/decision_log.md`。**程式會實際打開檔案找那個 ID**——填任意字串解不開 |
   | 那則決策**寫的就是這件事** | 條目文字要出現該 flag 的關鍵詞（中英皆可：`clustering` 收 `cluster` / `群集` / `叢集` / `gee` / `random effect`）。指向一則不相干的決策不算 |
   | `outcomes[]` **涵蓋每一個被建模的 outcome** | 少列一個就擋，並列出缺哪些 |

   放行後不是靜默通過：manifest 會記一條 `diagnostic_gate_overridden_<flag>` 的 method warning，照 Step 4a 念給使用者聽，並寫進 manuscript 的 limitations。

   > **`diagnostics.override_reason` 已經不再放行任何閘門**（2026-08-12 起；此前一句 `"N/A"` 可以一次解開全部四個）。它現在只剩一個用途：當 `mode: "off"` 的自由文字理由（`reason` / `override_reason` / `note` 任一，**至少 10 個字元**）。
   >
   > 完全沒有 `diagnostics` 區塊、但 pipeline 裡有 time-to-event 分析 → 也是 `[QC_BLOCKING]` 中止。「沒跑診斷」與「跑了診斷沒發現」從外面看長得一樣，所以不能靠沉默通過。

6. Present summary (mirror `/survival-diagnostics` output format). Options:
   - [A] Revise plan（回 Step 3 補上被點名的 step 與參數）—— **這是預設路徑**
   - [B] 確認 flag 不適用 → 走 `mode: "off"` + ≥10 字元理由
   - [C] 承認 flag 成立但這次不處理 → 寫 `decision_log.md` 開一個永久 ID，再填 per-flag `overrides`

**Default behavior by pipeline_mode:** 兩種模式**都會被擋**——這是 plan-time 的 fail-closed 檢查，不看 `pipeline_mode`。差別只在呈現：`auto` 直接把 FATAL 訊息與修法念出來，`hitl` 停下來問 [A/B/C]。

> **哪些是程式強制、哪些是 Claude 做的**：上面 4、5 兩點的檢查與放行條件**全部由 `generate_configs.py` 強制**，繞不過去。**Claude 負責的是**：跑 R driver、把 `diagnostic_report.json` 的內容正確寫進 `research_plan.json$.diagnostics`、以及向使用者解釋每個 flag 的臨床意義。**寫錯 `flags_detected` 沒有人會發現**——程式驗的是形狀與一致性，不是它有沒有忠實反映報告。

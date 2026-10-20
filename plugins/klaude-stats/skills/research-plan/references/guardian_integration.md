# Guardian Integration — Step 4.5 pre-execution 稽核的呼叫協定

**這份是 SKILL.md Step 4.5 的規則本體**（2026-09-07 從 SKILL.md 搬出，內容未改）。SKILL.md 只留入口段：何時跑、預設值、三支腳本的退出碼、閘門與保留關卡。

**Step 6.5（post-execution）留在 SKILL.md**，它只有三個動作。完整的 subagent prompt 模板、Role 1/2/3 分工哲學、模式與成本表在 `${CLAUDE_SKILL_DIR}/../biostats-guardian/references/integration.md`（**那是另一個 skill 的檔案，本檔不重述、也不取代它**）。

---

## 呼叫協定
**When:** after `generate_configs.py`, before `run_pipeline.py`. Controlled by `research_plan.json$.guardian.mode`.

**Default:**
- `pipeline_mode="auto"` → `guardian.mode="quick"` (Role 1 only, non-blocking)
- `pipeline_mode="hitl"` → `guardian.mode="standard"` (Role 1 + Role 2, block on issues)
- Disable: set `guardian.mode="off"` in plan or pass `--guardian-mode off`

**Action:** delegate to `biostats-guardian` skill. **2026-08-12 起 pre 階段不再每個 step 派一隻 agent** —— 純運算的部分改由三支確定性腳本做掉，只剩語意問題派 agent：

**先跑三支腳本（不派任何 agent）：**

```bash
# ① 確定性欄位／設定檢查 —— 取代 Role 1 的 per-step fan-out
python3 ${CLAUDE_SKILL_DIR}/scripts/precheck_configs.py <OUTPUT_DIR>/research_plan.json --stage pre \
  --configs <OUTPUT_DIR>/configs --out <OUTPUT_DIR>/guardian/precheck.json

# ② 計畫 → config 的路由稽核 —— 取代 Role 2 的「這個專案選對方法沒」那一半
python3 ${CLAUDE_SKILL_DIR}/../biostats-guardian/scripts/plan_routing_audit.py \
  --plan <OUTPUT_DIR>/research_plan.json --configs <OUTPUT_DIR>/configs \
  --json <OUTPUT_DIR>/guardian/plan_routing.json

# ③ 腳本雜湊比對 —— 取代 Role 2 的「腳本被改過沒」那一半
python3 ${CLAUDE_SKILL_DIR}/../biostats-guardian/scripts/script_hashes.py check \
  --project-dir <OUTPUT_DIR> --json <OUTPUT_DIR>/guardian/script_hashes.json
```

三支共用同一套退出碼：**`0` 通過／`1` 有阻擋級發現／`2` 跑不起來**。`2` 一律當成 `block`，**不是 pass**——確定性層失效時要明講「本次退回 LLM 欄位稽核」，不要靜默略過。

`precheck_configs.py --stage pre` 涵蓋 COL-001（欄位存在）／COL-002（dtype）／COL-003（reference level）／COL-005（篩選後 n 與缺失門檻）／RES-006（EPV）／`success_criteria` 的實際求值／**以及 Stage Reflector 的五條規則**（見 Step 6）。輸出走 `[QC_BLOCKING]` / `[QC_WARNING]` / `[QC_INFO]` stderr 慣例，另寫一份 `precheck_report.json`。

> ### ⚠ `script_hashes.py update` 是**使用者保留關卡** —— agent 永不自跑
>
> `check` 隨便跑，**`update` 不行**。`update` 重新產生雜湊基準線，等於宣告「現在磁碟上的腳本就是對的」。讓 agent 自己跑它，就是讓被稽核的人自己簽收——腳本被改壞之後跑一次 `update`，drift 偵測從此永遠是綠的，而且沒有任何痕跡顯示發生過什麼。
>
> **雜湊對不上時 agent 該做的**：回報哪些檔變了（`script_hashes.json` 的 `audit_scope[]`）、派一隻 scope 限縮在那些檔的 Code Auditor、把結論交給使用者。**要不要更新基準線由使用者自己下指令。** 腳本本身也擋：`update` 有三個前置條件（工作樹乾淨、測試通過等），任一不成立就 exit 2 拒絕。

**再派 agent（只有這兩種情況）：**

1. `standard` / `full` 模式 → **一隻** Semantic Column Reviewer（**全 plan 一隻，不是每 step 一隻**），處理腳本抓不到的語意問題（欄位名稱與臨床意義不符、分布跟協議上限打架之類）
2. ③ 的雜湊 exit 1 → 一隻 Code Auditor，scope 限 `script_hashes.json$.audit_scope[]`

然後 aggregate RoleReports via:
   ```bash
   python ${CLAUDE_SKILL_DIR}/../biostats-guardian/scripts/runner.py aggregate \
     --phase pre --mode {mode} --plan <OUTPUT_DIR>/research_plan.json \
     --reports <role_report_paths...> \
     --out <OUTPUT_DIR>/guardian/pre_report.json
   ```
3. Present 繁中 summary. On `aggregated_status=block` in hitl mode, **pause** and ask user: [A] fix + re-run `generate_configs.py`, [B] override, [C] skip that skill. On `warn` continue unless `block_on_warn=true`. On `pass` print one-line ✅ and proceed.

Prompt template and full integration details: `${CLAUDE_SKILL_DIR}/../biostats-guardian/references/integration.md`.

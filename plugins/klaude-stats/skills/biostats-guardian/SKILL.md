---
name: biostats-guardian
description: >
  biostats-guardian：統計 pipeline 品質防護，deterministic-first。執行前用腳本做確定性檢查（`precheck_configs.py` 欄位/型別/EPV/success_criteria、`script_hashes.py` 比對 pipeline 腳本 sha256），只對腳本抓不到的語意問題派 subagent（欄位存在但意思不對、estimand 設計、PH 違反後做了什麼）；執行後由 Results Auditor 稽核輸出。涵蓋 table1、kaplan-meier、competing-risk、univariate-forest、multivariate-interaction、psm-matching、auc-cstat。
  Trigger: `/biostats-guardian`、`/bg-review`，或「統計審核」「pipeline 檢查」「跑統計前要先檢查」「research-plan 執行前後 QA」。選配 skill；`research-plan` 偵測到本 skill 已安裝時會在 Step 4.5 / 6.5 呼叫。
---

# Biostats Guardian — 統計 Pipeline 品質防護

> **選配的品質檢查**：不裝它，`research-plan` 與各統計 skill 照常運作。本 skill 與兄弟 skill 放在同一個 plugin 內（`${CLAUDE_SKILL_DIR}/../<skill>/`）。
>
> **第一次使用**：隨附的 `baselines/pipeline_scripts.json` 是空白佔位檔（沒有 hash）。請執行一次
> `python ${CLAUDE_SKILL_DIR}/scripts/script_hashes.py update --note "first install"`，在你自己的機器上建立基準線；之後 `check` 才會有意義。沒建立前 `check` 回 exit 2 並提示這行指令。

## 設計哲學

統計錯誤有三種類型在 `run_pipeline.py` 的 `ThreadPoolExecutor` 跑完之前不會被發現：
(1) 欄位名稱拼錯但 config 和 script 拼法一致；
(2) Cox 硬套到 binary outcome、reference level 用 pandas 預設；
(3) 產出看起來合理但 HR=1e6、CI 跨 5 orders、EPV<5 的 unstable 估計。

本 skill 在 `run_pipeline.py` 的**前後**插入稽核，抓的是以上三類。
核心鐵律（抄自 `research-guardian`）：**產生內容的 agent 永遠不能評估自己的輸出。**
每個 subagent 都是 fresh context，只讀原始 artifact（config JSON、script、log、output Excel），
看不到 main agent 的 chain-of-thought、也看不到其他 role 的結論。

**第二鐵律（2026-08-11 新增）：能用 assert 的，不准用 agent。** 原本的 Role 1（每 step 一隻欄位稽核）與 Role 2（每 step 一隻程式稽核）在 2 個 outcome 的專案是 ~52 隻 subagent、佔 token 總量 45–50%，可查紀錄裡抓到 0 件——因為它們檢查的是集合運算與比大小。現在：

| 層 | 誰做 | 位置 |
|---|---|---|
| 欄位 / dtype / reference level / n / 缺失率 / EPV / 數值合理性 / N 對齊 / success_criteria | `precheck_configs.py`（跑一次） | `research-plan/scripts/` |
| pipeline `.py` 有沒有被改過 | `script_hashes.py check`（sha256） | 本 skill `scripts/` |
| **這個專案選對分析了沒**（adjuster 到齊、outcome 路由、參照組方向） | `plan_routing_audit.py`（plan vs config，每次跑） | 本 skill `scripts/` |
| route 有沒有真的接上 | `test_routes_synthetic.py`（已知真值 fixture） | `research-plan/scripts/` |
| STROBE domain 報告 | `strobe_signoff.py`（腳本輸出 + 作者簽名） | 本 skill `scripts/` |
| **欄位存在但意思不對**、estimand / 因果設計、違反 PH 之後做了什麼 | **subagent（保留）** | `column-audit.md` B 節、`results-audit.md` |

刪掉的每一條檢查都必須有明確接手者；沒有接手者的一律保留。

詳見 `references/integration.md` 的 Producer ≠ Evaluator 說明與 Strategy A 實作。

---

## 觸發條件

| 場景 | 行為 |
|---|---|
| `/biostats-guardian pre` | 手動觸發 pre-execution 審查（讀 `research_plan.json` → 跑 `precheck_configs.py` + `script_hashes.py` → 視需要派 1 隻 Semantic Column Reviewer／1 隻 drift-only Code Auditor） |
| `/biostats-guardian post` | 手動觸發 post-execution 審查（讀輸出 + log，派 Role 3 subagents） |
| `/biostats-guardian all` | 先跑 pre、等 pipeline 完、再跑 post |
| `/biostats-guardian --skill {skill} --role {column|code|results}` | 指定單一 skill + role |
| `/bg-review` | `/biostats-guardian` 的 alias |
| `research-plan` 自動呼叫 | `research_plan.json$.guardian.mode != "off"` 時，在 Stage 3.5 / Stage 5 自動派 subagent |
| 使用者提及「pipeline 執行前檢查一下」「統計結果自動複查」「跑 stat 之前派 auditor」 | 視為觸發 |

---

## 模式

定義在 `research_plan.json$.guardian.mode`（或 CLI `--guardian-mode`）：

| Mode | Pre（腳本，永遠跑） | Pre（agent） | Post | 全 pipeline subagent 數 | 適用 |
|---|---|---|---|---|---|
| `off` | — | — | — | 0 | 只靠人工看 config 就夠的 toy run |
| `quick` | precheck + hash | 0（hash drift 才 +1） | Role 3 RES-014 only（primary outcome） | 0–1 + 1 | `pipeline_mode=auto` 自動預設 |
| `standard` | precheck + hash | 1（Semantic Column Reviewer，**全 plan 一隻**） | Role 3（每 step 一隻，含 RES-014、RES-015） | 1–2 + n_steps | `pipeline_mode=hitl` 預設；正式研究 |
| `full` | precheck + hash | 1 + 每個 drift 檔一隻 | Role 3 全套 + cross-skill aggregator | 同上 + 1 global | PI review、publication-grade |

改版前 `standard` 的 pre-phase 是 13 step × 2 role = 26 隻；現在是 1–2 隻。**確定性層跑不起來時要回退成舊的逐 step LLM 稽核並在摘要明講**，不是靜默跳過。

`pipeline_mode=auto` → guardian 降為 `quick`，永不阻斷；
`pipeline_mode=hitl` → guardian 預設 `standard`，遇 block 暫停請 user ack。

### Cross-language sanity（RES-014）開關

- `research_plan.json$.guardian.cross_lang_check`：`true` / `false` / 缺省。
- 缺省行為：所有 mode（含 `quick`）對 regression step 自動啟用。`quick` 額外限縮為**僅 `is_primary_outcome=true`** 的 step，避免每個次要 regression 都重跑；`standard`+ 對所有 regression step 跑。
- 顯式 `false`：對所有 step 跳過 RES-014（適用 toy run、教學、無法雙語環境的場景）。
- 顯式 `true`：對所有 regression step 強制啟用（覆寫 `quick` 的 primary-only 限縮）。
- 詳細協定見 `references/results-audit.md` 的 RES-014。

---

## 執行流程（由 Claude 驅動）

### Pre-execution（Stage 3.5）

**先決條件：** `generate_configs.py` 已生成 `{step_id}_config.json`；`run_pipeline.py` **尚未**執行。

1. 讀 `research_plan.json` 的 `guardian.mode`、`pipeline[]`、`guardian.disabled_roles`。
2. **先跑腳本，不派 agent**（細節與退回規則見 `references/integration.md` Stage 3.5）：
   ```bash
   python ${CLAUDE_SKILL_DIR}/../research-plan/scripts/precheck_configs.py --stage pre \
     --plan {plan_path} --configs {config_dir} --out {output_dir}/guardian/precheck.json
   python ${CLAUDE_SKILL_DIR}/scripts/plan_routing_audit.py \
     --plan {plan_path} --configs {config_dir} --json {output_dir}/guardian/plan_routing.json
   python ${CLAUDE_SKILL_DIR}/scripts/script_hashes.py check \
     --project-dir {output_dir} --json {output_dir}/guardian/script_hashes.json
   ```
   precheck 或 routing audit 有 `[QC_BLOCKING]` → 直接進入第 6 步的三級處理。hash exit 0 → 印「pipeline 腳本未修改，跳過程式稽核」。
3. 只有這兩種情況派 agent（同一 message 內平行）：
   - `standard` / `full`：**一隻** Semantic Column Reviewer（全 plan 一隻，不是每 step 一隻）
   - hash exit 1：**一隻** Code Auditor，scope 限 `script_hashes.json` 的 `audit_scope[]`
4. 等 subagent 回傳單一 JSON（符合 `schemas/biostats-guardian.schema.json` 的 RoleReport）。
5. 用 `scripts/runner.py aggregate` 彙整成 `{output_dir}/guardian/pre_report.json`：
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/runner.py aggregate \
     --phase pre --mode standard \
     --plan {plan_path} \
     --reports role1_table1.json role2_table1.json ... \
     --out {output_dir}/guardian/pre_report.json
   ```
6. 根據 `aggregated_status` 決定：
   - `block` → 印繁中摘要 + 詳細 block issues，**暫停**問 user：[A] 修正重跑 / [B] Override / [C] 略過此 skill
   - `warn` → 印摘要；若 `block_on_warn=false` 直接繼續
   - `pass` → 一行 ✅ 繼續

### Post-execution（Stage 5）

**先決條件：** `run_pipeline.py` 已結束，`{output_dir}/` 下有 log 檔與 output Excel。

1. 讀 `run_pipeline.py` 更新後的 `research_plan.json`（含 stderr `[QC_*]` 已解析到 `qc_warnings`）。
1b. 跑 post 模式的確定性檢查（Role 3 讀它、不重算）：
   ```bash
   python ${CLAUDE_SKILL_DIR}/../research-plan/scripts/precheck_configs.py --stage post \
     --plan {plan_path} --configs {config_dir} --out {output_dir}/guardian/precheck_post.json
   ```
   接著跑 **PH remedy artifact gate**（manuscript 之前，dispute 5）：
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/ph_remedy_gate.py \
     --plan {plan_path} --output-dir {output_dir} \
     --json {output_dir}/guardian/ph_remedy_gate.json
   ```
   declared remedy 沒有對應產物 → block；`disclose` 沒有 decision-log ID → block。**宣告不等於執行**，這道 gate 就是把「has been run」變成程式能驗的東西。
   若 pipeline 有 `strobe` step，另跑 `scripts/strobe_signoff.py`（見 `references/integration.md` Stage 5 步驟 0b），**不要為 STROBE 派 agent**。
2. 對每個 completed step 派 Role 3 subagent（同一 message 內平行）。
3. `scripts/runner.py aggregate --phase post ...` 彙整成 `{output_dir}/guardian/post_report.json`。
4. **寫回** Role 3 issues 到 `research_plan.pipeline[i].qc_warnings[]`：
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/runner.py writeback \
     --plan {plan_path} \
     --report {output_dir}/guardian/post_report.json
   ```
   格式：`[GUARDIAN_WARNING] RES-001 km_os: ...` / `[GUARDIAN_BLOCKING] RES-007 uni_os: ...`。
   沿用現有 `extract_qc_warnings()` 的 parsing 慣例，不需改 `run_pipeline.py`。
5. 同三級處理（block 暫停 / warn 續 / pass ✅）。

### Ad-hoc 觸發

使用者手動 `/biostats-guardian pre` 或 `/biostats-guardian --skill kaplan-meier --role column`：
Claude 跳過 pipeline integration，直接讀當前目錄的 `research_plan.json` 找 artifact、派 subagent、輸出 report 到 `{output_dir}/guardian/ad_hoc_{timestamp}.json`。

---

## Subagent Prompt 模板

每個 Role subagent 的 prompt 骨架（完整版在 `references/integration.md`）：

```
你是獨立的 Biostats Guardian Role {N} Auditor。

[任務] 對以下 biostats skill 的 pre-flight/post-execution artifact 做品質稽核。

[輸入]
- research_plan.json: {plan_path}
- Data_Dictionary.csv: {dict_path or "N/A"}
- precheck 結果: {output_dir}/guardian/precheck.json     # Semantic Reviewer / Role 3 必讀
- 雜湊比對結果: {output_dir}/guardian/script_hashes.json # Code Auditor only
- Skill: {skill}, Step ID: {step_id}                     # Role 3（每 step 一隻）
- Config: {config_dir}/*.json
- Data head: 自己跑 python -c "..." 取得                  # Semantic Reviewer
- Logs: {log_path}                                       # Role 3 only
- Output Excel: {output_path}                            # Role 3 only

[檢查量表]
請完整閱讀並依照 ${CLAUDE_SKILL_DIR}/references/{ref}.md 中的 {CHECK_IDS}。
  Semantic Column Reviewer → column-audit.md **B 節**：COL-004、006、007、008、009、010、011、012
      （A 節的 COL-001/002/003/005 已由 precheck_configs.py 涵蓋，**不要重做**）
  Code Auditor（只在 hash drift 時存在）→ code-audit.md, CODE-001..014，
      **scope 限 script_hashes.json 的 audit_scope[]**，其餘檔案不讀不評
  Role 3 → results-audit.md, RES-001、002、004..015
      （**RES-003 已刪除**：改讀 research_plan.json 的 qc_warnings[]，不要自己掃 log）

[規則]
- Producer ≠ Evaluator：你不看 main agent 的推理、不看其他 role 的 report。
- 無證據不產生 issue：每個 issue 必須附 evidence（具體 pointer）。
- confidence < 0.6 一律標 severity=uncertain，不猜。
- message 繁中，JSON field 英文。

[輸出]
只輸出單一 JSON object，符合 ${CLAUDE_SKILL_DIR}/schemas/biostats-guardian.schema.json
的 RoleReport。不要 markdown 包裹、不要前後文字、不要解釋。
```

---

## File Manifest

- `SKILL.md`（本檔）
- `schemas/biostats-guardian.schema.json` — Issue / RoleReport / GuardianReport JSON schema
- `scripts/issue_schema.py` — Pydantic 模型 + `aggregate()` helper
- `scripts/runner.py` — CLI：`validate` / `aggregate` / `summary` / `writeback`（不 spawn subagent）
- `scripts/plan_routing_audit.py` — **雜湊補不了的那一半**：比對 plan 宣告 vs config 實際（PR-001 adjuster 到齊／PR-002 outcome↔model family／PR-003 competing-risk 路由／PR-004 grouping 與參照組）。**每次執行都跑，與 script drift 無關**——出貨腳本原封不動、config 漏掉事前指定的 adjuster，雜湊與 synthetic fixture 都會放行
- `scripts/script_hashes.py` — **取代 Role 2 整層**：`check`（sha256 比對 pipeline 腳本與出貨版，含專案內 vendored 副本）／`update`（第一次使用建立 baseline；skill 升版後重產）
- `baselines/pipeline_scripts.json` — 出貨版腳本的 sha256 baseline（含 `git_commit` / `note` / `changed_since_previous`）。第一次使用要由使用者跑一次 `update` 建立；skill 升版後要重產，否則每次 check 都誤報 drift、每次白派一隻 Code Auditor。**`update` 由使用者自己執行、agent 發現 drift 時不自跑**（見「不做的事」）。可選加 `--require-clean-git`（要求 git 已 commit）與 `--run-tests`（先跑 fixture 測試）
- `scripts/ph_remedy_gate.py` — **PH remedy 的「宣告 → 有產物」驗證**（`RES-015-det`，manuscript 之前跑）。declared remedy 沒有對應產物 → block；`disclose` 沒有 decision-log ID → block；`status: not_computed` → block；borderline → warning 交 D5。**不擋 multivariate step 本身**，擋的是未處置的 HR 進 manuscript。⚠ **兩種強度不同的綠燈**（schema `ph_remedy_gate/2`）：有 evidence sidecar（`<stem>_remedy.json`）→ **驗內容**（sha256 綁定該表、remedy 相符、`status: computed`，再加逐 remedy 的檢查：`stratify` 分層變項要涵蓋 Schoenfeld 真正判定違反的變項；`time_varying` 同樣要涵蓋、**且時間窗要來自 plan**；`rmst` **tau 要來自 plan**）→ 進 `verified_remedies`、不用簽字；沒有 sidecar → 退回**只驗檔案存在**，在 manifest 記 `ph_remedy_declared_not_computed`，由 pre-manuscript 表態閘門要求作者具名簽字（記不進 manifest 就改為阻擋）。三個 remedy 都有 shipped generator 會寫 sidecar（2026-08-12）
- `scripts/strobe_signoff.py` — **取代 reviewer-challenge domain 10 的 agent**：把 `strobe.py` 的 checklist 轉成 domain report JSON，並強制作者簽名（`--signed-off-by`）。輸出即 `reviewer_challenge.py aggregate` 的 domain report 形狀（`domain: "reporting_strobe"`、`schema: "strobe_domain_report/1"`，與該檔 `DOMAINS` / `DOMAIN_REPORT_SCHEMAS` 逐字相同），並帶 `plan_fingerprint`（委派 `reviewer_challenge.plan_fingerprint`）綁定本輪分析——消費端 `provenance_problems()` 對不上或 null 一律 block；輸入優先讀 `strobe.py` 的 `<stem>_rows.json`（結構化，含每列 `kind`——哪些項目只能由作者撰寫以它為準），找不到才 fallback 解析 markdown 並印警告。輸出是 **reviewer-challenge domain report、不是 guardian RoleReport**（`check_id` 為 `STROBE-*`，刻意不符合 RoleReport schema），不要餵給 `runner.py aggregate`
- `references/column-audit.md` — A 節 = 已由 `precheck_configs.py` 涵蓋（存檔用）；B 節 = Semantic Column Reviewer 的實際工作（COL-004、006–012）
- `references/code-audit.md` — Code Auditor checklist（CODE-001..014），**只在 sha256 drift 時使用**
- `references/results-audit.md` — Role 3 checklist（RES-001、002、004..015；RES-003 已刪除；RES-014 = R↔Python cross-language sanity；RES-015 = PH 假設與 remedy）
- `references/qa_thresholds.md` — 量化 threshold cheat sheet（missing data、PH p<0.01、Cox convergence、events/subgroup、DPI、n(%)/IQR 格式）；每列標示由 **[script]** 或 **[agent]** 執行，agent 判 severity 時引用、標 [script] 的不重算
- `references/integration.md` — Producer ≠ Evaluator 說明、平行執行、與 research-plan 整合點、user-facing 輸出
- `references/pitfalls_biostat_db.md` — 跨資料庫的 Reflexion 錯題本（user-specific reference data）。每個資料庫獨立小節（目前含 HF / TTM；未來新資料庫直接新增 `## <DB_NAME>` 章節）。Semantic Column Reviewer（以及 drift 時的 Code Auditor、post 階段的 Results Auditor）在 cwd / data path / `research_plan.json$.dataset` 偵測到任一登錄資料庫的標記時主動 Read 對應小節比對 config / data dictionary。**這些 pitfall 多屬 COL-012 語意類，腳本抓不到，是保留 agent 的主要理由之一**
- `tests/fixtures/` — golden-fail fixtures：`fixture_wrong_dtype`、`fixture_leakage`、`fixture_bad_method`、`fixture_absurd_hr`

---

## 預設行為

1. `research_plan.json$.guardian` 缺失 → 視為 `{"mode": "quick", "block_on_warn": false, "disabled_roles": [], "cross_lang_check": null}`。`cross_lang_check: null`（或鍵缺失）= auto，依 mode 決定（見上方「Cross-language sanity 開關」段）。
2. `research_plan.json$.guardian.mode = "off"` → 完全跳過，不印任何摘要。
3. 找不到對應 skill 的 config 或 script → 該 step 記為 `status=error`，aggregated_status 升為 `error`。
4. Subagent 回傳非 JSON 或 schema 驗證失敗 → `runner.py aggregate` 產出一筆 `status=error` 的 meta RoleReport；Claude 顯示「某 subagent 輸出無法解析」並問 user 要否重派。
5. **一次 pipeline 執行最多跑 pre 一次 + post 一次；第三次呼叫一律 no-op。**
   Guardian 過去在同一個專案跑三次：research-plan Step 4.5（pre）→ Step 6.5（post）→ Step 10b 的收尾驗證 再「Re-run in quick mode」。第三次檢查的是 config 欄位，而 **config 從 Step 4.5 到 Step 10 之間沒有改過**——它是純重複，不是「不同目的」。
   判定：若 `{output_dir}/guardian/pre_report.json` 已存在，且 `{config_dir}/*.json` 的 sha256 與該 report 記錄的一致 → 印一行「config 自 pre 階段未變更，跳過重複稽核（見 pre_report.json）」後**直接返回**，不派任何 agent、不重跑腳本。
   例外（會真的重跑）：config 確實改過（例如 user 選了修正後重跑 `generate_configs.py`）、或使用者顯式 `/biostats-guardian pre --force`。
6. **確定性層失效 ≠ 通過**：`precheck_configs.py` 或 `script_hashes.py` 不存在／非零退出／輸出缺席時，一律當 `block` 處理並在摘要明講；`quick` 模式可退回舊的逐 step LLM 稽核，但要標示「本次退回 LLM 欄位稽核」。

---

## User-Facing 輸出範例

```
Biostats Guardian 審查摘要（Pre-execution, standard mode）
────────────────────────────────────────────
確定性層（0 個 subagent）
  precheck_configs.py  : 13 steps — 通過 11、警告 1、阻擋 1
  plan_routing_audit.py: 13 steps 的 config 與 plan 宣告一致
  script_hashes.py     : pipeline 腳本未修改（26 個檔案雜湊一致），跳過程式稽核
語意層（1 個 subagent）
  Semantic Column Reviewer: 警告 1

⚠️  警告：2
  - univariate-forest: COL-005 共變量 age missingness 42%（precheck）
  - multivariate-interaction: COL-012 `total_ttm_hr` 分佈與計畫敘述不符，疑似混入 transfer time（semantic）
🛑 阻擋：1
  - kaplan-meier: COL-002 event_col 有 4 個 unique values（precheck）

請決定：
[A] 修正後重跑 generate_configs.py
[B] Override 阻擋（我已看過，繼續執行）
[C] 略過此 skill
```

**摘要必須分列「確定性層」與「語意層」並印出各派了幾隻 agent**——這是防止本次改版被悄悄回退成 fan-out 的可見指標。

Post-phase 版本把每個 skill 的結果補上具體數值（HR、CI、N、event count、PH global p），並列出 `[GUARDIAN_WARNING]` 已寫回 `research_plan.json` 的哪一行。

---

## 與 research-guardian 的關係

| 面向 | research-guardian | biostats-guardian |
|---|---|---|
| 目標 | 審查 manuscript（hypothesis、literature、writing） | 審查統計 pipeline（columns、code、results） |
| 時機 | 寫作完成後 | 統計執行前 + 後 |
| 輸入 | 論文文字 | research_plan.json + config + script + data + log |
| Roles | 5 gates + logic chain | 3 roles |

兩者共用 Producer ≠ Evaluator 原則，可串聯（pipeline 跑完 → biostats-guardian post → manuscript 寫完 → research-guardian）。

---

## 不做的事

- **不執行 `script_hashes.py update`。** 這由使用者自己執行（第一次建立基準線除外也是使用者跑）。偵測到 hash drift 時，agent 唯一的自動動作是派 Code Auditor 審 diff 並回報；把 drift bless 掉等於自己關掉自己的警報。威脅模型不是使用者惡意，是「某個 session 為了讓 pipeline 跑過改了腳本，再順手 update 讓 gate 閉嘴」
- 不重寫 biostats leaf skill 的 script（只 flag，不改 code）
- 不執行 pipeline（那是 `run_pipeline.py` 的工作）
- 不改 output Excel（純 read-only）
- 不做最終「accept/reject」判斷（只給 evidence-backed issue，決定權在 user）

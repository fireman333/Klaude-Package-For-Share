---
name: research-plan
description: "Orchestrate research stats pipeline. Trigger: research plan, statistical plan, study protocol, 研究計劃, 統計規劃, 論文統計, 自動化統計, 幫我規劃統計, 規劃分析流程, plan my analysis, design my study analysis, 幫我做整篇論文的統計, run all analyses, 跑完整個分析, 全部統計一起跑, advisor feedback, 老師意見, 修改統計, revise analysis, 重跑分析, re-run pipeline, 老師回饋, 指導教授意見, update research plan, 幫我規劃這篇論文要做的統計, plan all the stats for my paper, 老師給了意見要改統計, 幫我重跑分析."
---

# Research Plan — Automated Biostatistics Pipeline

> **不一定要裝全套。** 每個統計 skill（`table1`、`kaplan-meier`、`competing-risk`、`univariate-forest`、`multivariate-interaction`、`psm-matching`、`auc-cstat`…）都能**單獨使用**；`research-plan` 只是把它們串成一條自動化流程。`biostats-guardian` 是**選配的品質檢查**——沒裝時，Step 4.5 / 6.5 直接略過（`precheck_configs.py` 的確定性檢查仍會跑），不影響其他流程。
>
> 檔案路徑：`${CLAUDE_SKILL_DIR}` 是本 skill 的資料夾；同一個 plugin 內的兄弟 skill 在 `${CLAUDE_SKILL_DIR}/../<skill>/`。

> **措辭規則（統計顯著性）**：未達統計顯著只代表「這份資料沒偵測到差異」，**不等於**沒有差異或兩者相同（要證明相同需 non-inferiority 設計與預設 margin）。一律寫「無統計顯著差異」「未達顯著」，不寫「沒有關聯」「證明沒效」「降低 X%」（HR 的 95% CI 跨 1 時）。報告任何 NS 結果都要附 point estimate + CI。

Orchestrate a complete medical research paper's statistical analyses from a single natural-language study description. This skill acts as a **conductor** that translates your research question into structured configs, then calls the individual analysis skills (flowchart, table1, kaplan-meier, competing-risk, univariate-forest, multivariate-interaction, psm-matching, auc-cstat, manuscript-results) with support for parallel execution, adaptive checkpoints, and structured advisor feedback handling.

The key value: you describe your study once, confirm the variable mappings once, and the entire pipeline runs automatically — with intelligent pauses at critical decision points.

## Reference Documents

These files define the detailed protocols referenced throughout this workflow:

- `${CLAUDE_SKILL_DIR}/references/plan_template.md` — Complete research plan JSON schema (v2.0)
- `${CLAUDE_SKILL_DIR}/references/pipeline_state_machine.md` — Step/pipeline states, analysis groups, safety limits
- `${CLAUDE_SKILL_DIR}/references/survival_preflight.md` — Step 3.5 存活分析診斷的執行協定與四個 plan-time 硬閘門
- `${CLAUDE_SKILL_DIR}/references/guardian_integration.md` — Step 4.5 pre-execution 稽核的呼叫協定（三支腳本、退出碼、保留關卡）
- `${CLAUDE_SKILL_DIR}/references/run_pipeline_protocol.md` — Step 6 的旗標表、auto/HITL 模式、checkpoint 深度、方法學替代表態、QC gates 與 PH remedy
- `${CLAUDE_SKILL_DIR}/references/checkpoint_protocol.md` — Adaptive checkpoints (FULL/SLIM/MANDATORY), Stage Reflector, QC gates
- `${CLAUDE_SKILL_DIR}/references/feedback_audit_protocol.md` — 7-step advisor feedback audit protocol
- `${CLAUDE_SKILL_DIR}/references/missing_data_protocol.md` — 缺失資料評估與多重插補的方法學規格（何時跑、插補模型怎麼設、哪些情況要擋）
- `${CLAUDE_SKILL_DIR}/references/advanced_analyses.md` — 七項 reviewer 會要的分析（E-value、STROBE、RCS、群集穩健、calibration、IPTW、landmark）的方法學規格
- `${CLAUDE_SKILL_DIR}/references/reviewer_challenge.md` — 投稿前模擬審稿的十個 domain rubric、反奉承條款、閘門行為
- `${CLAUDE_SKILL_DIR}/references/delivery_discipline.md` — **交付紀律規則本體**：六條硬規則、看門狗 C1–C10、驗收三題、findings 登記簿、bootstrap、可攜性

**Bundled tooling** — `${CLAUDE_SKILL_DIR}/assets/` ships the delivery-discipline tools, so this skill is self-contained and runs from **any** working directory:

| 路徑 | 用途 |
|---|---|
| `assets/check_freshness.py` | 腐爛看門狗（**C1–C10**）。canonical 版本。C8／C9／C10 的判斷邏輯不寫在它裡面，而是委派給下面三支 lint |
| `assets/lint_bare_numbers.py` | **C8** 的判斷邏輯：交付物裡印出來的每個數字，在它自己宣告的 stats 來源裡找不找得到。也可單獨跑 |
| `assets/lint_absolute_claims.py` | **C9** 的判斷邏輯：絕對句／新穎性宣稱有沒有帶檢索範圍（資料庫、檢索日期、命中筆數）。吃路徑參數，可單獨掃一份 md |
| `assets/reconcile_prisma.py` | **C10** 的判斷邏輯：稿件宣稱的 PRISMA 整數 vs 磁碟上的篩選／全文／抽取檔實際筆數。吃 MA 專案根目錄 |
| `assets/templates/` | 7 個範本。**程式會檢查的**：`research-checks.yaml`（看門狗設定）、`verification_findings.json`（C4 讀）、`omission_reasons.json`（C7 讀）。**人工維護、零程式 reader**：`PROJECT_STATE.yaml`（環境／seed／caveats／未辦事項——過期不會有人告訴你）、`decision_log_skeleton.md`（但 gate 會查裡面的 decision ID）、`project_CLAUDE.md`、`gitignore-medical` |
| `assets/README.md` | 工具怎麼用 |


### 閘門腳本一覽 —— 誰在什麼時候擋你

多數關卡現在是**確定性腳本**，不是給 Claude 看的規則。這張表是「哪一支在哪一步、失敗了怎麼辦」的索引；細節在各步驟裡。

| 腳本 | 位置 | 何時跑 | 失敗怎麼辦 |
|---|---|---|---|
| `generate_configs.py` | research-plan/scripts | Step 4 | exit 1 = `[FATAL]`（缺欄位／Step 3.5 閘門／缺 reviewer-challenge／重複 step id）；exit 2 = 有 skill 沒有 generator。**照訊息修計畫再產一次** |
| `precheck_configs.py` | research-plan/scripts | `--stage pre` 在 Step 4.5；`--stage post` 在 Step 6.5 | exit 1 = 有阻擋級發現，修完重跑；exit 2 = **跑不起來**（計畫／資料檔／config 目錄有問題），先修環境。pre 沒過時 `run_pipeline.py` 直接 exit 1 不執行 |
| `plan_routing_audit.py` | biostats-guardian/scripts | Step 4.5，每次執行 | 跟腳本改沒改無關——它查「這個專案有沒有選對方法」。exit 1 逐條看發現 |
| `script_hashes.py check` | biostats-guardian/scripts | Step 4.5 前置 | exit 1 = 腳本被改過 → 派 Code Auditor，scope 限 `audit_scope[]`。**`update` 是使用者保留關卡，agent 永不自跑** |
| `estimate_inventory.py` | research-plan/scripts | post（由 precheck post 自動呼叫）；也可單獨跑 | 產 `coverage_diff.json`，餵看門狗 **C7**。exit 1 = 有跑了但沒報的估計，逐條寫不列出的理由 |
| `check_numbers_sourced.py` | research-plan/scripts | **交付前，要自己跑**（不在 pipeline 呼叫鏈裡） | exit 1 = 有數字對不到來源 → 逐條人工判定；exit 2 = 參數或索引有問題 |
| `ph_remedy_gate.py` | biostats-guardian/scripts | manuscript 之前（precheck post 會呼叫） | **只擋 manuscript，不擋 multivariate step 本身**。exit 1 = PH remedy 宣告了但產物不在 |
| `strobe_signoff.py` | biostats-guardian/scripts | reviewer challenge 的 domain 10 | **取代原本派 agent 的做法。** exit 1 = 有該補的項目沒補，或需要人寫的項目沒有作者簽名（`--signed-off-by`）；exit 2 = checklist 讀不到（**不是通過**） |
| `reviewer_challenge.py` | research-plan/scripts | Step 6.7，以及 manuscript 執行前再驗一次 | exit 1 = 有未結案 fatal／domain 沒跑齊／指紋對不上 |
| `check_freshness.py` | research-plan/**assets** | Step 10a，以及 pre-manuscript briefing | exit 1 = 有紅燈；exit 2 = 沒設定檔或 `--stage` 值不合法 |
| `lint_bare_numbers.py` | research-plan/**assets** | 由看門狗 **C8** 委派；寫作當下也可單獨反覆掃一份 md | exit 1 = 交付物裡有數字在它宣告的 stats 來源裡找不到（手打值、或漏宣告來源）→ 逐條判定，不要放寬 `min_integer` 了事；exit 2 = 沒設定檔或該項寫成空設定，**不是通過** |
| `lint_absolute_claims.py` | research-plan/**assets** | 由看門狗 **C9** 委派；吃路徑參數，可單獨掃目錄或單一檔 | exit 1 = 有絕對句／新穎性宣稱沒帶檢索範圍（資料庫、檢索日期、命中筆數、篩了幾筆）→ 補限定或把宣稱收窄；exit 2 = 沒有 `paths` 可掃，**不是通過** |
| `reconcile_prisma.py` | research-plan/**assets** | 由看門狗 **C10** 委派（僅 MA 版面）；吃 MA 專案根目錄 | exit 1 = 稿件宣稱的 PRISMA 整數與磁碟上的裁定檔對不起來（含兩輪篩選被拼成一張流程圖）→ 逐階段核；exit 2 = 不是 MA 版面／沒有裁定檔／稿件無 PRISMA 數字，**不是通過** |
| `test_pipeline_contract.py` / `test_routes_synthetic.py` | research-plan/scripts | 改動本 skill 的腳本之後 | 契約與路由的迴歸測試。**`test_routes_synthetic.py` 取代了原本 Role 2 的一半**（另一半是 sha256 比對） |

> **退出碼有兩套慣例，不要混用。** `precheck_configs.py`、`check_freshness.py`、三支 guardian 腳本、`estimate_inventory.py`、`check_numbers_sourced.py` 都是 **`2` = 跑不起來、`1` = 有發現**。但 **`generate_configs.py` 相反**：它的 `[FATAL]` 走 `sys.exit("<訊息>")`，Python 對字串參數一律 exit **1**，而 exit `2` 留給「有 skill 找不到 generator」。判讀前先確認在看哪一支。
>
> **訊息前綴也有兩種，grep 時兩個都要抓。** `generate_configs.py` 的致命錯誤有些印 `[FATAL]`（缺欄位、Step 3.5 閘門、schema 版本），有些印 `[QC_BLOCKING]`（完全沒有 `diagnostics` 區塊、diagnostics 區塊沒記錄任何一次執行）——**同一支腳本、同一類「不能繼續」，兩個 grep 不到彼此的標籤**。`precheck_configs.py` 則已統一成 `[QC_BLOCKING]`（連「跑不起來」也用這個前綴，好讓只掃 `[QC_*]` 行的呼叫端看得到）。要找所有阻擋原因，`grep -E '\[FATAL\]|\[QC_BLOCKING\]'`。

## Mode Selection (Step 0) — 先決定要走哪條路

**在做任何事之前先判斷專案形狀**，兩條路的入口不同：

| cwd 偵測到 | 模式 | 走哪裡 |
|---|---|---|
| 有 `research_plan.json` | **pipeline（resume）** | 讀計畫 → 跳 Step 5 中途接入偵測 |
| 沒有，且使用者要規劃 / 跑統計 | **pipeline（new）** | Step 1 開始 |
| 有 `data/*_stats.json` + 編號腳本（`scripts/NN_*.py`）但**沒有** `research_plan.json` | **discipline-only** | 見下方 |
| 使用者只說「幫這個資料夾上交付紀律 / 加看門狗 / 補決策紀錄 / 派驗收」 | **discipline-only** | 見下方 |

### discipline-only 模式（手工統計專案）

這類專案的統計已經由使用者自己的編號腳本跑完，**本 skill 不接管統計、不改寫它的腳本**，只負責把交付紀律架上去。動作：

1. **先跑看門狗看現況**（沒有設定檔就是 exit 2 = 未受保護，不是通過）：
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/assets/check_freshness.py . 
   ```
2. 依 `references/delivery_discipline.md` §3 補齊缺的東西：`research-checks.yaml`、專案級 `CLAUDE.md`、`decision_log.md`（永久 ID + 狀態欄）、`verification_findings.json`、`.gitignore`。**已存在的檔一律不覆寫**，只補缺口並列出差異讓使用者確認。
3. 需要驗收時，照 §1 規則 3 派 fresh-context agent（含必問三題）。
4. 收尾走 Step 10 的看門狗硬 gate。

> **不要**在 discipline-only 模式硬生 `research_plan.json`。那會製造第二個真值來源，跟既有的編號腳本打架。

## Workflow (pipeline 模式)

Follow these steps **in order**. Steps 1–3 are interactive (require user input). Steps 4–10 are automated (with HITL checkpoints if enabled).

---

### Step 1: Gather Study Design (研究計劃訪談)

Interview the user to collect:

1. **Research title / objective** — what question is this study answering?
2. **Data file path** — absolute path to the xlsx/csv data file
3. **Data Dictionary path** (optional) — path to `Data_Dictionary.csv`; if not provided, skip dictionary-based matching in Step 2
4. **Study design** — `cohort`, `case-control`, `cross-sectional`, or `rct`
5. **Grouping** — how patients are split (e.g., "AF vs no AF"); capture both natural-language description and suspected column name if offered
6. **Inclusion / exclusion criteria** — natural language (e.g., "只收 HFpEF 的病人", "排除 age < 20")
7. **Primary outcome** — natural language description, type (`time_to_event` or `binary`), and whether competing risks apply
8. **Secondary outcomes** — same format as primary; can be zero or many
9. **Covariates** — natural-language list of variables to adjust for in regression models
10. **Advanced analyses** — ask whether to include: PSM (yes/no), competing risk (yes/no), AUC/C-statistics (yes/no)
    - AUC 答 yes 時**還有第二個問題**：要的是「每個變項各自的 discrimination」，還是「這個 marker 對既有臨床模型還能**多加**多少（incremental value / Delta C-index）」？後者要**當場把 base model 的欄位定下來**，寫進 `analyses.auc.clinical_model_columns`（語意見 `${CLAUDE_SKILL_DIR}/references/plan_template.md` 的 `analyses.auc` 一節）。它進 plan fingerprint——事後才挑 base model 等於挑一個讓候選變項好看的比較基準，那是這個問題全部的 p-hacking 面。base model 裡的變項不會再被當候選（`base + candidate` 會把它算兩次）。time-to-event outcome 記得同時把 `analyses.auc.bootstrap_n` 調低，2000 次 paired bootstrap 很容易撞 600s step timeout
11. **缺失資料** — ask: 「這份資料有沒有已知的缺失？要不要做多重插補（MI）？」預設：**缺失評估一定跑**（不問要不要，只問有沒有已知缺失、有沒有想放進插補模型的輔助變項），**MI 依評估結果再決定**。使用者若當下就要指定，記進 `missing_data.strategy`（`assess_only` / `mi_sensitivity` / `mi_primary`）與 `missing_data.primary_analysis`（預設 `complete_case`）。詳見 `${CLAUDE_SKILL_DIR}/references/missing_data_protocol.md`
12. **Output directory** — where all results go
13. **Pipeline mode** — ask: "是否使用 HITL 模式（每個分析群組後暫停確認）？預設為 auto（全部跑完再呈現）。" Options:
    - `auto` (default) — runs all steps, presents results at the end
    - `hitl` — pauses after each analysis group with adaptive checkpoints
14. **探索期還是投稿前** — ask: 「這次是**探索期**（先看資料長怎樣、還會改設定）還是**投稿前**（要產出可以寫進論文的數字）？」寫進 `pipeline_profile`。**沒問等於預設 `submit`**（缺席時程式取 `submit`），而 `submit` 會把投稿級的關卡全部打開，探索期會一直被擋。

    | 值 | 別名（都收） | 效果 |
    |---|---|---|
    | `explore` | `exploration` / `exploratory` | `manuscript-results`、`reviewer-challenge`、`strobe` 三個 step 被**停放**（`status: "skipped"` + `skip_reason: "profile"`），不產生 config、不執行。manifest 另記 `guardian_mode_recommended: "off"` |
    | `submit`（**預設**） | `submission` / `confirmatory` | 把 `skip_reason: "profile"` 的 step 解除停放改回 `pending`。**手動 `--skip` 的 step（沒有 `skip_reason`）不會被動到**，兩個方向都是 |

    > **這不是「跑快一點」的開關，是「這批數字算不算數」的宣告。** `explore` 模式下每個 step 都會在 `explore_ledger.jsonl` 留一列（含 `config_sha256` 與計畫指紋）；之後要轉 `submit`，`run_pipeline.py` 會要求一份 explore → submit 的 promotion record（`reviewer_challenge.py promotion-diff`），把「探索時看到結果才改的設定」攤出來。**先探索再投稿是正常做法，不留紀錄地探索完直接當成事前指定不是。**

If the user provides a free-text paragraph describing everything, parse it and extract what you can, then ask for clarification on anything missing. Users often describe their study conversationally — the skill's job is to turn this into structure.

---

### Step 2: Variable Mapping & Confirmation (欄位比對與確認) ★ Critical Step

This step ensures no analysis runs on wrong columns. It is the **single most important safeguard** in the pipeline.

#### 2a. Read the data

```python
import pandas as pd
df = pd.read_excel(data_file)  # or read_csv
print(f"Shape: {df.shape}")
print(f"Columns: {df.columns.tolist()}")
```

For each column mentioned by the user (grouping, outcomes, covariates, filters), print:
- Column name, dtype, non-null count
- `value_counts()` (top 10) for categorical/binary
- `describe()` for continuous

#### 2b. Read the Data Dictionary (if available)

```python
dict_df = pd.read_csv(data_dictionary_path)
# Columns: 類別, name, label, values
```

Use the `label` and `values` columns to help match user descriptions to column names.

#### 2c. Build the mapping table

For every variable the user mentioned, create a row:

```
| 使用者描述            | 對應欄位名稱       | 資料類型      | 數值分布/編碼                  | 用途           |
|----------------------|--------------------|--------------|-----------------------------|---------------|
| 年齡                  | age                | continuous   | mean=72.3, range 30-98      | covariate     |
| 有無 AF              | AF_hx              | binary       | {0, No}{1, Yes}             | grouping      |
| CV death             | CV_Death           | binary       | {0, No}{1, Yes}             | outcome event |
| HFpEF only           | HF_type == 3       | filter       | {1,HFrEF}{2,HFmrEF}{3,HFpEF}| inclusion    |
| 追蹤時間 (天)         | follow_up_days     | continuous   | median=1095, range 1-3650   | outcome time  |
```

Present this table and **explicitly ask the user to confirm or correct each row**.

#### 2d. Handle unmapped variables

If you cannot find a matching column for a user-described variable:
- List candidates from the data dictionary with similarity scores
- Ask the user to pick or provide the correct column name
- If a variable genuinely doesn't exist in the data, note it and ask if the user wants to derive it or skip it

**Do NOT proceed to Step 3 until the user confirms all mappings.**

---

### Step 3: Generate Research Plan JSON (產生研究計劃)

After confirmation, generate `research_plan.json` in the output directory.

**完整 JSON schema、v2.0 欄位、`success_criteria` 預設值、pipeline 自動展開規則（每個 outcome 的 `km_/cr_/uni_/multi_/mi_`、`advanced_analyses.<key>.enabled` 對應的 step 與 `depends_on`、共用 step、兩個會被自動補進 `pipeline[]` 的 step 及其三個前提）：`${CLAUDE_SKILL_DIR}/references/plan_template.md`**〈Complete Schema〉〈Pipeline Step Schema (v2.0)〉〈Pipeline Auto-expansion Rules〉〈`advanced_analyses` 區塊語意〉。

**兩個閘門留在這裡，不要只當成文件規定**：① **`reviewer_challenge` 一定要在 `manuscript.depends_on` 的傳遞依賴裡**，有 `strobe` 也要加進去——缺 step 或缺依賴，`generate_configs.py` 會 FATAL 退出，不會靜默放行（2026-08-11 起）；② `mi_{outcome_id}` **只在 `missing_data.strategy` 不是 `assess_only` 時才產生**，預設不產生，等缺失評估的 verdict 出來再決定。

Present a summary of the plan to the user: 分析總數 / 依分析群組排列的 step 清單 / Table/Figure 編號 / pipeline mode (auto/hitl)，並 ask for final confirmation before execution。

#### 3d. Bootstrap 交付紀律骨架 ★ 必做，不是可選

`research_plan.json` 只管統計怎麼跑，**管不了交付出去的數字會不會腐爛**。計畫確認後、跑分析前，在 `<OUTPUT_DIR>` 架起紀律骨架：從 `${CLAUDE_SKILL_DIR}/assets/templates/` 複製 `research-checks.yaml`、`PROJECT_STATE.yaml`、`project_CLAUDE.md`（→ `CLAUDE.md`）、`decision_log_skeleton.md`（→ `report/decision_log.md`）、`gitignore-medical`（→ `.gitignore`），然後 `git init -q`。**cp 指令全文、四個佔位符各要填什麼、`git check-ignore -v` 的驗證步驟：`${CLAUDE_SKILL_DIR}/references/delivery_discipline.md` §3。**

**範本原樣留著 `<...>` 等於沒做**——看門狗會因為路徑不存在回 exit 2。至少留 C1（stats 新鮮度）與 C5（文件 vs stats）。`decision_log.md` 的起始列是 Step 8 變更控制的起點，**沒有起始列，之後就沒有東西可以 supersede**。已存在的檔一律不覆寫——列出差異問使用者。

---

### Step 3.5: Survival Pre-flight Diagnostics (存活分析資料結構診斷) ★ Auto-triggered when survival outcomes planned

**When to run:** `research_plan.json` 寫好之後，`pipeline[]` 含任一 time-to-event 分析（`kaplan-meier` / `competing-risk` / `univariate-forest` / `multivariate-interaction`）時。**Skip condition:** `research_plan.json$.diagnostics.mode = "off"`，或 pipeline 沒有 survival step。

**做什麼**：產 `<OUTPUT_DIR>/diagnostics/diagnostic_config.json` → 跑 `${CLAUDE_SKILL_DIR}/../survival-diagnostics/scripts/survival_diagnostics.R`（macOS 非 ASCII 路徑要帶 `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8`）→ 把 `diagnostic_report.json` 的內容寫進 `research_plan.json$.diagnostics` → 向使用者解釋每個 flag 的臨床意義。

**閘門：四個 flag 是 plan-time 硬閘門，不是建議**（2026-08-12 起）。`generate_configs.py` 的 `_validate_diagnostics_honored()` 在**產 config 之前**檢查 `competing_risk` / `left_truncation` / `time_varying` / `clustering`：沒有對應補救 step（或 step 有但參數沒填 = **inert，不算數**）就印 `[FATAL] ... Step 3.5 detected N condition(s) the pipeline does not handle` 並 **exit 1，一個 config 都不會產生**。`left_truncation` **沒有任何補救 step，一定擋**；覆蓋是**逐 outcome** 算的；完全沒有 `diagnostics` 區塊而 pipeline 有 time-to-event 分析 → `[QC_BLOCKING]` 中止。**兩種 `pipeline_mode` 都會被擋**（fail-closed，不看 mode），差別只在呈現：`auto` 把 FATAL 訊息與修法念出來，`hitl` 停下來問 [A/B/C]。

**放行只有一條路：per-flag 的 `diagnostics.overrides.<flag>`**，四個條件全部成立才過（`decision_id` 格式對、該 ID **真的存在於 `decision_log.md`**、那則決策寫的就是這件事、`outcomes[]` 涵蓋每一個被建模的 outcome）。放行不是靜默通過——manifest 記一條 `diagnostic_gate_overridden_<flag>` method warning，照 Step 4a 念給使用者聽並寫進 manuscript 的 limitations。**`diagnostics.override_reason` 已不再放行任何閘門**（2026-08-12 起），只剩 `mode: "off"` 的自由文字理由（≥10 字元）。**其餘細則**（`mode: "completed"` 的四個必填欄位、`flags_detected` 的三種形狀、`overrides` 四條件、選項 [A]/[B]/[C]、哪些是程式強制哪些是 Claude 做的）：**`${CLAUDE_SKILL_DIR}/references/survival_preflight.md`**，欄位語意另見 `${CLAUDE_SKILL_DIR}/references/plan_template.md`〈`diagnostics` 區塊語意〉。

---

### Step 4: Generate Sub-skill Configs (產生各分析的設定檔)

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/generate_configs.py <OUTPUT_DIR>/research_plan.json
```

This reads the research plan and produces one JSON config per pipeline step in `<OUTPUT_DIR>/configs/`（`status: "skipped"` 的 step 不產生 config）。Each config conforms exactly to the target skill's expected schema (documented in `${CLAUDE_SKILL_DIR}/references/plan_template.md` under "Sub-skill Config Mapping").

Also generates `<OUTPUT_DIR>/configs/manifest.json` tracking all configs with their skill, step_id, and generation timestamp.

After generation, briefly list the configs created and their target skills.

**退出碼**（跟本 skill 其他腳本**不同**，別套用同一套判讀）：

| exit | 意思 |
|---|---|
| `0` | 產完了。**method warning 不影響退出碼**——照樣是 0，所以不能用退出碼代替 Step 4a |
| `1` | `[FATAL]` —— 缺必填欄位、`plan_schema_version > 2`、Step 3.5 閘門沒過、有 manuscript 卻沒有 reviewer-challenge、pipeline 有重複 step id、`--migrate` 與 `--only` 同時給 |
| `2` | 有 step 的 skill 沒有對應的 generator（`generator_failures`），或 `--migrate` 撞到 plan lock |

#### 4-migrate. 既有專案先跑 `--migrate` ★ v1 計畫升 v2 的唯一正規路徑

計畫是 2026-08-11 之前建立的（沒有 `plan_schema_version`，或它 `< 2`）→ **先跑一次遷移**，否則自動補 step 的機制整段不啟動（只會印預覽），而且 `diagnostics.data_fingerprint` 缺席只會降級成警告，等於少了一層保護：

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/generate_configs.py <OUTPUT_DIR>/research_plan.json --migrate
```

它會加鎖（`<plan>.lock`）、備份成 `<plan>.bak-YYYY-MM-DD`，然後**只寫兩個東西**：

- `plan_schema_version: 2`
- `covariate_provenance`：把沒有理由的共變項補成 `{"<column>": null}` 的空格，等人來填

**它刻意不寫的四個欄位**，每個都會印出理由：`pipeline_profile`、`model_purpose`、`estimand_type`、`multiplicity`。原因同一個：**這四個進計畫指紋，程式替你猜一個等於偽造一份事前指定。** 遷移只做指紋中性的事，跑完會印出指紋沒變的確認。這四個要人自己填。

`--migrate` 不能跟 `--only` 一起用（前者改寫計畫、後者只重產 config），同時給會 exit 1。計畫宣告的版本比 2 高 → 拒絕遷移（那會是降級）。

#### 4a. 方法學替代必須浮出來 ★ 不可省略

`manifest.json$.methodological_warnings[]` 記錄 generator **代替使用者做的統計決定**。這些不是程式警告，是會改變數字意義的方法學選擇。目前有兩種：

| kind | 發生什麼 | 為什麼要講 |
|---|---|---|
| `competing_risk_routed_to_cause_specific` | primary outcome 是 competing risk，但 univariate-forest / multivariate-interaction / psm-matching / auc-cstat 一律走 cause-specific Cox（競爭事件當 censoring） | 估的是**病因學 hazard，不是絕對風險**。要 subdistribution (Fine-Gray) 得直接用 competing-risk skill。reviewer 一定會問 |
| `time_scale_assumed` | outcome 沒指定 `time_scale`，generator 假設原始欄位單位是**天**並依 `time_unit` 換算 | 猜錯的話**每一個存活估計都會整體偏移一個常數倍率，而且不會有任何錯誤訊息** |

**動作**：把每一條念給使用者聽（繁中）、確認假設正確、寫進 `decision_log.md` 成為有永久 ID 的決策列，並在 manuscript 的 statistical methods / limitations 反映。**不要因為 pipeline 跑得完就當它不存在。**

---

### Step 4.5: Pre-execution Guardian (統計設定品質稽核) ★ Optional but default ON in HITL

**When:** after `generate_configs.py`, before `run_pipeline.py`. Controlled by `research_plan.json$.guardian.mode`。**Default:** `pipeline_mode="auto"` → `quick`（Role 1 only, non-blocking）；`pipeline_mode="hitl"` → `standard`（block on issues）；`guardian.mode="off"` 或 `--guardian-mode off` 關閉。

**先跑三支腳本（不派任何 agent）**：`${CLAUDE_SKILL_DIR}/scripts/precheck_configs.py --stage pre`、`${CLAUDE_SKILL_DIR}/../biostats-guardian/scripts/plan_routing_audit.py`、`${CLAUDE_SKILL_DIR}/../biostats-guardian/scripts/script_hashes.py check`。三支共用同一套退出碼：**`0` 通過／`1` 有阻擋級發現／`2` 跑不起來**。**`2` 一律當成 `block`，不是 pass**——確定性層失效時要明講「本次退回 LLM 欄位稽核」，不要靜默略過。

> ### ⚠ `script_hashes.py update` 是**使用者自己執行**的指令 —— agent 發現 drift 時不自跑
>
> **第一次使用**：隨 plugin 出貨的 baseline 是空白佔位檔，`check` 會回 exit 2 並提示。請使用者執行一次 `python ${CLAUDE_SKILL_DIR}/../biostats-guardian/scripts/script_hashes.py update --note "first install"` 建立自己的基準線（之後只有刻意改過 pipeline 腳本才需要再跑）。沒裝 biostats-guardian 就略過這整個 Step。
>
> `check` 隨便跑，**`update` 不行**：它重新產生雜湊基準線，等於宣告「現在磁碟上的腳本就是對的」，也就是讓被稽核的人自己簽收——腳本被改壞之後跑一次 `update`，drift 偵測從此永遠是綠的，而且沒有任何痕跡。**雜湊對不上時 agent 該做的**：回報哪些檔變了（`script_hashes.json$.audit_scope[]`）、派一隻 scope 限縮在那些檔的 Code Auditor、把結論交給使用者。**要不要更新基準線由使用者自己下指令。**

**再派 agent（只有這兩種情況）**：① `standard` / `full` → **一隻**全 plan 的 Semantic Column Reviewer（不是每 step 一隻）；② 雜湊 exit 1 → 一隻 Code Auditor，scope 限 `audit_scope[]`。然後 `runner.py aggregate --phase pre` 彙整成 `<OUTPUT_DIR>/guardian/pre_report.json`，present 繁中 summary：`block` 在 hitl 模式**暫停**問 [A] 修正 + 重跑 `generate_configs.py`／[B] override／[C] 略過該 skill；`warn` 續跑（除非 `block_on_warn=true`）；`pass` 印一行 ✅。**完整指令與涵蓋的檢查編號（COL-001/002/003/005、RES-006、`success_criteria` 求值、Stage Reflector 五條規則）：`${CLAUDE_SKILL_DIR}/references/guardian_integration.md`**；subagent prompt 模板與分層哲學：`${CLAUDE_SKILL_DIR}/../biostats-guardian/references/integration.md`。

---

### Step 5: Mid-Entry Detection (中途接入偵測)

Before execution, scan the output directory for existing output files:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/run_pipeline.py <OUTPUT_DIR>/research_plan.json --detect-only
```

`--detect-only` **reports and executes nothing.** It prints, per step: the recorded `status`, whether output files exist on disk, and what the next run would execute.

**What decides a skip is `status`, not the presence of a file.** 但 `status="done"` 現在**不是無條件相信**——每個 step 執行前會把它的 config 檔雜湊成 `config_sha256` 寫進 step，之後每次啟動都比對一次。

| 情況 | 行為 |
|---|---|
| `status="done"` 且 config 雜湊一致 | 不重跑（`should_run` 保證；未帶 `--from` 時 done 一律跳過） |
| `status="done"` 但 **config 內容變了** | **自動降級成 `needs_rerun`** 並寫 `stale_reason`。改了設定卻沿用舊數字，是這裡最貴的錯 |
| `status="done"` 但 **config 檔被刪了** | 降級成 `blocked`，`blocked_by = "(config file deleted)"`。不能證明那份輸出是怎麼來的 |
| `status` ∈ `pending` / `needs_rerun` / `error` / `blocked` | 會跑 |
| 檔案存在但 `status` 不是 `done` | 印 **⚠ 孤兒輸出**警告——下次執行會覆蓋它。要保留就先備份，或手動把 `status` 改成 `done` |
| step 從來沒被這套雜湊機制蓋過章（`unstamped`） | 印出來提醒，**不降級**——那是 2026-08-11 之前跑的舊輸出，無從判定 |

> 這個降級是**每次啟動都跑一次**（`mark_stale_steps()`），對**整條 pipeline 的每一個 `done` step** 生效，**跟有沒有帶 `--only` 無關**。`--detect-only` 只印不改。

```
━━━ Mid-Entry Detection ━━━
  ✓ flowchart      status=done      2 output file(s) on disk
  ✗ table1         status=pending   1 output file(s) on disk

  Recorded complete: 1/2
  Would run:         1/2 → table1

  ⚠ Output files exist for step(s) not recorded as done: table1
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If this is a fresh run with no existing outputs, skip this presentation entirely and proceed to Step 6.

> **不要**只因為看到 `Table1.xlsx` 存在就宣告該步完成。孤兒輸出最常見的來源是上一版計畫——沿用它等於把舊 cohort 的數字混進新分析。

---

### Step 6: Run the Pipeline (執行分析)

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_pipeline.py <OUTPUT_DIR>/research_plan.json [--hitl] [--no-parallel]
```

**完整旗標表（14 個）、兩種模式的行為、checkpoint 深度判定、Stage Reflector 的五條規則、方法學替代的表態閘門、QC gates 與 PH 假設違反的四種 remedy：`${CLAUDE_SKILL_DIR}/references/run_pipeline_protocol.md`。**

**退出碼**：`0` = 跑完（**即使有 step 失敗、被 blocked、或 checkpoint 停下來，退出碼仍是 0**——不要拿退出碼判斷成敗，要讀 Step 7 的狀態）／`1` = 計畫檔不存在，或 pre 階段 precheck 沒過／`2` = 替代表態被拒、`--from`/`--only` 指到不存在的 step、feedback 輪次超限。**`--emit-rerun`、`--list-substitutions`、accept/reject、`--override-watchdog` 都是「做完就結束」的動作**，不會順便把 pipeline 跑掉；要執行請不帶這些旗標再跑一次。

The runner operates differently depending on pipeline mode:
#### Auto Mode (`pipeline_mode: "auto"`)

群組依序執行 Foundation → Per-outcome（primary → secondary_N）→ Supplementary → Manuscript，群內獨立的 step **平行**跑，stdout/stderr 進 `<OUTPUT_DIR>/logs/{step_id}.log`（**每次執行前清掉舊 log**）。**錯誤不中止 pipeline**：記錄錯誤、把依賴它的 step 標 `blocked`（它們從未執行，**不**計入錯誤），繼續下一個獨立 step；失敗的 step 有**一次**自動重試，`retry_count` 一旦寫入就不歸零。跑完直接進 Step 7。

> **哪些是腳本做的、哪些是 Claude 做的**——不要把 Claude 該做的事說成「系統擋下了」。**腳本負責**：依賴排序、群內平行、600 秒 timeout、重試、QC 行擷取、狀態與 `checkpoints[]` 持久化、HITL 暫停、80 步與 `max_feedback_rounds` 上限、Stage Reflector 計算、checkpoint 深度判定與 25% 抽查、config 漂移偵測、方法學替代的表態閘門、缺失評估與 MI 的計算。**Claude 負責**：把 Reflector 的警告轉成具體建議並執行、checkpoint 停下之後的呈現與詮釋、Step 7 的結果解讀、採不採納缺失評估的 verdict、把 method warning 念給使用者聽（Step 4a）。
>
> **一個具體後果**：`checkpoints[].reflection_applied` **永遠是 `false`**——那是留給 Claude 自己回填的欄位，`false` 不代表沒有建議，只代表沒有人記錄有沒有照做。

#### HITL Mode (`pipeline_mode: "hitl"`)

執行方式同 auto，但**第一個分析群組跑完就真的停**：寫 checkpoint、設 `pipeline_state = "awaiting_review"`、印橫幅、**結束程序**。腳本不讀 stdin——**使用者的「回答」＝再跑一次同一個指令**（下次啟動 `record_resume_decision()` 把它記成 `continue`，有 blocker 時記成 `blocked`）；已完成的 step 不重跑。

**三件容易誤傳的事**：① **Manuscript checkpoint 在群組執行之前觸發**（`print_manuscript_briefing()` 的六段簡報：腐爛看門狗、方法學替代表態、post 階段 precheck、explore→submit promotion 等），「manuscript 跑完再檢查」是錯的心智模型；② 連續 continue 三次之後降級成 **SLIM，而 SLIM 不會停**（印一行就繼續，並自己在 `checkpoints[]` 記 `"decision": "continue"`），約 **25%** 隨機抽回 FULL——**不要對使用者說「每組都會停下來確認」**，要每組都停就穿插一次 `review` 把 `consecutive_continue_count` 歸零；③ **整個群組後 checkpoint 機制只在 `--hitl` 下才走得到**（auto 模式只有 pre-manuscript briefing 和有 blocker 時會停）。

Checkpoint 深度判定表、Stage Reflector 的五條警告規則（`REFLECT-epv` / `-small-n` / `-imbalance` / `-events` 與缺失建議）、FULL / SLIM / MANDATORY 的呈現與四種 user decision 語意：`${CLAUDE_SKILL_DIR}/references/run_pipeline_protocol.md`、`${CLAUDE_SKILL_DIR}/references/checkpoint_protocol.md`。**Reflector 只建議、不改計畫，且絕不可以建議更動主要結局或暴露定義**——只能動模型設定。

#### 方法學替代必須逐條表態才過得了 manuscript

`manifest.json$.methodological_warnings[]` 的每一條都有內容衍生的 ID（`SUB-` + sha256 前 8 碼；重產不會換號，但**改動內容會讓先前的表態失效**）。`--list-substitutions` 看清單，`--accept-substitution SUB-xxxxxxxx:理由` / `--reject-substitution SUB-xxxxxxxx:理由` 表態。

**理由不可空白**——「accepted 但沒寫理由，跟沒讀過是同一件事」，空理由會被拒絕並 exit 2。**未表態的會在 pre-manuscript briefing 變成 blocker**，重跑不會讓它消失。**`rejected` 也一樣擋**——拒絕了但計畫沒改，那條替代仍在，要真的解掉就得回去改計畫。runtime 會自己補進哪兩種替代（`--skip-precheck`、`runtime_qc`）與指令範例：`${CLAUDE_SKILL_DIR}/references/run_pipeline_protocol.md`。

#### Statistical QC Gates (both modes)

Scripts emit QC results to stderr with prefixes; the runner captures these.

- **Blocking**（step 標 `error`，pipeline 照樣往下走）：任一組 0 events、模型不收斂、HR/OR = Inf / NaN / ≤ 0
- **Warning**（資訊性，checkpoint 呈現）：任一組 n < 30、每組 events < 10、HR/OR > 10 或 CI width > 100、任一變項缺失 > 20%、缺失 > 50%（**不自動移除**，要理由 + sensitivity；MAR 成立時 MI 處理得了 — Madley-Dowd 2019）、PH borderline（`0.01 <= p < 0.05`）。逐條門檻與註記：`${CLAUDE_SKILL_DIR}/references/run_pipeline_protocol.md`。

#### PH 假設違反 ★ 這一段的四個值只有一個 pipeline 真的會算

**門檻是固定的 0.01 / 0.05，不隨 n 調整**（舊版寫「n > 5000 時改用 0.01」是錯的）。Schoenfeld 全域 p：

| p | 行為 |
|---|---|
| **`p < 0.01`（`PH_ALPHA`）且 `ph_violation_remedy` 沒填** | **Blocking** —— multivariate step 標 `error`，依賴它的 step 變 `blocked` |
| `p < 0.01` 且 remedy 有填 | 降成 warning，內容依 remedy 而不同 |
| **`0.01 <= p < 0.05`（`PH_ALPHA_REVIEW`）** | Warning，**不擋**。但 reviewer challenge 的 domain 5 **必須逐條表態**（dismiss + 理由，或 escalate），不得沉默通過 |

**宣告位置：`outcomes[<id>].ph_violation_remedy`，逐 outcome。寫在計畫頂層會被靜默忽略**——那個位置就是強制手段（指紋雜湊 `outcomes`，事後補填會讓既有的 reviewer challenge 失效）。四個 remedy（`disclose` / `stratify` / `time_varying` / `rmst`）各自 pipeline 幫你算什麼、你要填哪個欄位、`ph_remedy_gate.py` 驗什麼內容、自建 step 怎麼被認得：`${CLAUDE_SKILL_DIR}/references/run_pipeline_protocol.md`（欄位語意另見 `${CLAUDE_SKILL_DIR}/references/plan_template.md`、`${CLAUDE_SKILL_DIR}/references/checkpoint_protocol.md`）。**切點與 tau 沒宣告時不是死路**：分析照跑、表照出（作者看得到數字與確切的修法），擋的是 manuscript gate——把人擋在沒有出口的門前比放行更糟。

#### Safety Limits

- **Step timeout**: 600 seconds per step
- **Max retry**: 1 per step
- **Max total steps**: 80 across all runs (initial + re-runs). If exceeded, force pause with warning.

---

### Step 6.4: Missing Data — 評估與多重插補 ★ 評估永遠跑

方法學規格全在 `${CLAUDE_SKILL_DIR}/references/missing_data_protocol.md`（何時該做 MI、插補模型要放什麼、哪些情況要擋）。這裡只講它在 pipeline 裡的位置。

**兩個步驟做什麼：**

| Step | 群組 | 做什麼 | 產物 |
|---|---|---|---|
| `missingness` | Foundation | 每個分析變項的缺失 n / %（並依分組拆開）、缺失樣態、**listwise 會讓 N 從多少掉到多少**、缺失指標與分組／事件／追蹤時間的關聯檢定、輔助變項候選、verdict | `Missingness.xlsx` + `Missingness_pattern.png` |
| `mi_{outcome_id}` | 該 outcome 的群組 | R `mice` 多重插補 → 同一個模型跑 pooled analysis（Rubin's rules，報 FMI）→ `CC_vs_MI` 對照分頁 → 收斂與分布診斷圖 | `MI_{outcome}.xlsx` + `MI_{outcome}_diagnostics.png` |

**兩條硬規則：**

1. **缺失評估永遠跑。** `missingness` 無條件產生、無條件執行，沒有開關。理由：「這份資料沒有缺失問題」本身就是需要證據的宣稱，不能靠印象。Foundation checkpoint 要把 listwise 的 N 損失直接念給使用者聽——那是「什麼都不做」的實際代價。
2. **MI 不會自動變成主分析。** 評估給的 verdict（`complete_case_ok` / `mi_recommended` / `mi_with_caution` / `mcar_refuted` / `outcome_missing`）**只是建議**，跟 Stage Reflector 同一個原則：只建議、不自動改。要不要加 `mi_*` 步驟、以及主分析是 complete-case 還是 MI，都是**事前指定**的人為決策，必須登記進 `decision_log.md`（帶永久 ID，格式見 `references/delivery_discipline.md`）並寫進 `missing_data.primary_analysis`（預設 `complete_case`）。pipeline 兩個都算給你看，選哪個是人的責任。

**其他 step 不受影響**：KM、Table 1、PSM、AUC、回歸維持原本的 `missing_data_handling`。MI 是**額外**的一條分析路線，不是替換。這一點要在 Step 7 講清楚，否則會出現「Table 1 的 N 跟回歸模型的 N 對不起來」而沒人解釋。

**擋下來的情況**（協議 §6，由 `missing_data.py` 吐 `[QC_BLOCKING]`，不靜默退回 complete-case）：結果變項本身缺失、competing risk 的 MI、R / `mice` 不可用。其中 competing_risk outcome 在 Step 4 產 config 時就會記一條 methodological warning（`mi_competing_risk_unsupported`）並照樣產出 config——真正的擋在腳本裡，錯誤訊息只有一處。撞到就照 4a 浮出來給使用者，不要自己改 outcome 定義。

---

### Step 6.5: Post-execution Guardian (統計結果品質稽核) ★ Optional but default ON in HITL

**When:** after `run_pipeline.py` finishes, before presenting results. Skipped entirely if `guardian.mode="off"` or `"quick"`.

**Action:** delegate to `biostats-guardian` skill:
1. For each completed pipeline step, spawn one **Role 3 Results Auditor** subagent per step (parallel, single message; Agent tool `model: sonnet`; fatal-severity disputes are arbitrated by `model: opus`). Each subagent reads `<OUTPUT_DIR>/logs/{step_id}.log`, the output Excel, and `research_plan.json$.pipeline[i].success_criteria`. Checklist: `${CLAUDE_SKILL_DIR}/../biostats-guardian/references/results-audit.md`.
2. Aggregate + write back:
   ```bash
   python ${CLAUDE_SKILL_DIR}/../biostats-guardian/scripts/runner.py aggregate \
     --phase post --mode {mode} --plan <OUTPUT_DIR>/research_plan.json \
     --reports <role_report_paths...> \
     --out <OUTPUT_DIR>/guardian/post_report.json

   python ${CLAUDE_SKILL_DIR}/../biostats-guardian/scripts/runner.py writeback \
     --plan <OUTPUT_DIR>/research_plan.json \
     --report <OUTPUT_DIR>/guardian/post_report.json
   ```
   `writeback` appends `[GUARDIAN_WARNING]` / `[GUARDIAN_BLOCKING]` lines into `pipeline[i].qc_warnings[]`, compatible with the existing `extract_qc_warnings()` convention.
3. Present 繁中 summary. On `block`, pause and ask user whether to re-run the offending step. Guardian issues automatically surface in Step 7's "QC warnings" section via `pipeline_status.py`.

---

### Step 6.6: Advanced Analyses (reviewer 會要的七項) ★ 依 `advanced_analyses.enabled` 展開

方法學規格全文：`${CLAUDE_SKILL_DIR}/references/advanced_analyses.md`。**每一項預設關閉**——它們回答不同的研究問題，全開只會產生一堆沒人解讀的檔案。

| 步驟 | 補上的缺口 | 什麼時候該開 |
|---|---|---|
| `rcs_{outcome}` | 連續變項被強制線性 | 有連續共變項時（幾乎總是）。年齡、eGFR、BMI、血壓在臨床上很少是線性的 |
| `robust_{outcome}` | 群集讓變異被低估 | Step 3.5 標了 clustering，或資料有中心／醫師／重複量測。**忽略它的方向永遠是讓結果看起來比實際更顯著** |
| `calibration_{outcome}` | 只有 discrimination | **預測模型研究**才需要。病因學研究報 C-index 可以，但不要說成模型效能 |
| `weighting_{outcome}` | 只有 PSM 沒有加權法 | 想估 ATE，或 PSM 配掉太多人時。IPTW=ATE／PSM=ATT／overlap=ATO，**是三個不同的臨床問題** |
| `landmark_{outcome}` | immortal time bias | 暴露分組用到 time zero 之後才知道的資訊時（例如「住院期間有沒有開刀」） |
| `evalue_{outcome}` | 未測量干擾沒有被量化 | 觀察性研究的主結論。它讀 `Multi_{outcome}.xlsx` 的估計值，不重打數字 |
| `strobe` | 報告完整性 | 投稿前。產出的 checklist 每個 `covered` 都附產物指標 |

**三條硬規則**：

1. **每個步驟的輸出第一個分頁要回答「這個估的是什麼 estimand」。** 尤其是 weighting——ATE / ATT / ATO 不可混談，也不可因為哪個 p 值比較小就選哪個。
2. **所有預設值都是要登記進 `decision_log.md` 的方法學決策**，不是實作細節：knots 數與參考值、bootstrap 次數、landmark 時點、correlation structure、trimming 門檻。
3. **`p-nonlinear ≥ 0.05` 不等於「線性是對的」**，`E-value` 大不等於「沒有干擾」，`landmark` 不可只報最顯著的那個時點。這三句要出現在對使用者的說明裡，不要只留在產物註腳。

**Step 4 產生 config 時**，`manifest.json$.methodological_warnings[]` 會記下這幾種情況，照 Step 4a 念給使用者聽：`robust_variance_without_cluster_column`（沒指定群集欄，步驟會擋）、`evalue_without_benchmark`（E-value 沒有尺度錨點）、`immortal_time_on_binary_outcome`（landmark 需要 time-to-event）。

---

### Step 6.7: Reviewer Challenge (投稿前模擬審稿) ★ manuscript 之前的單次關卡

**When:** 分析結果要寫成 manuscript 之前。HITL 模式的 manuscript pre-checkpoint 是天然落點；auto 模式在 Step 6.5 之後、把結果拿去寫論文之前跑。**先決條件**：Step 10a 的看門狗 exit 0、Step 7.5 的第三方驗收做過——對一個本來就不可重現的 pipeline 跑這一關，只會得到一份精準指出它不可重現的報告。

> ### ⚠ 步驟編號在這裡不是執行順序 —— 照號碼跑會死循環
>
> 6.7 要等 10a、10a 在 Step 10、Step 10 要等 pipeline 跑完，而 pipeline 跑完包含 `manuscript`、`manuscript` 又要等 6.7。真正的順序是**把 Step 6 拆成兩段**：`Step 6（跑到 manuscript group 之前）→ 6.5 post guardian → 7 呈現結果 → 7.5 第三方驗收 → 10a 看門狗 exit 0 → 6.7 reviewer challenge → Step 6 續（manuscript group，閘門再驗一次）→ 9 / 10b`。**這個順序不必手動安排**——`run_pipeline.py` 的 manuscript pre-checkpoint 會在該群組執行前把所有沒結案的東西列成 blocker 並停下來，你只要在那裡停下時把 6.7 與 7.5 做完再重跑同一個指令即可。編號留著是為了跟舊文件對得起來；完整說明見 `${CLAUDE_SKILL_DIR}/references/reviewer_challenge.md` §0。

**跟 guardian 不重疊**：guardian 問「欄位對不對、程式對不對、數字合不合理」；這一關問「**這個研究設計本身，reviewer 會不會打回來**」。不要重做欄位與程式稽核。

**怎麼跑**：`reviewer_challenge.py domains` 看要派哪十個 domain → **一個 domain 一隻 fresh-context agent（Agent tool `model: sonnet`；fatal 等級爭議的仲裁升 `opus`），彼此不通訊**（互相看得到就會互相說服），只讀不改，prompt 必須含 `references/reviewer_challenge.md` §3 的**反奉承條款** → `reviewer_challenge.py aggregate` 取得閘門判定：exit `0` = 沒有未結案 fatal，可以往 manuscript 走；exit `1` = 有 fatal、**或十個 domain 沒跑齊、或報告格式不合** → 擋住 manuscript。**少跑 domain 不算通過**；**沒有證據指標的 `fatal` 會被自動降級為 `concern`** 並記 `demoted_from_fatal`。

**閘門是 pipeline step，不是自律**（2026-08-11 起）：plan 要有 `reviewer-challenge` step，且 `manuscript-results` 的 `depends_on` 要（直接或間接）含它，否則 `generate_configs.py` FATAL 退出；**manuscript 執行前閘門會再跑一次**（`--only manuscript` 會整段跳過依賴檢查）。**沒有跳過旗標**——fatal 的出路只有修正，或標 `wontfix` + `decision_log_id`（閘門會**實際開啟 `decision_log.md` 找那個 ID**）；`concern` 不擋，但每一條都要有去處；版本或 plan 指紋對不上一樣擋。指令全文、十個 domain 的完整 rubric、產物 schema、閘門逐項檢查表、`rerun-scope` 分域重跑（含 carry over 要留 decision-log 紀錄）、`explain-fingerprint`、`promotion-diff`：`${CLAUDE_SKILL_DIR}/references/reviewer_challenge.md`。

---

### Step 7: Present Results (彙報結果)

```bash
python ${CLAUDE_SKILL_DIR}/scripts/pipeline_status.py <OUTPUT_DIR>/research_plan.json
```

Present to the user:

1. **Progress bar** — visual pipeline status:
   ```
   Pipeline: [✓]flowchart → [✓]table1 → [✓]km → [✓]cr → [✓]uni → [✓]multi → [✓]psm → [✓]auc → [✓]manuscript
   ```

2. **Group status** — grouped by analysis group:
   ```
   Foundation:    [✓] flowchart  [✓] table1
   Primary:       [✓] km  [✓] cr  [✓] uni  [✓] multi
   Supplementary: [✓] psm  [✓] auc
   Manuscript:    [✓] manuscript
   ```

3. **Summary of key findings** — sample sizes, significant p-values, effect estimates

4. **QC warnings** — any statistical warnings collected during execution

5. **Timing statistics** — total duration, average per step, slowest step

6. **File inventory** — list all generated .xlsx, .png, .docx files with their Table/Figure numbers

6a. **Writing next step** (one line, only when `manuscript` step is done or user mentions writing) — Results text comes from `manuscript-results`; Title/Abstract/Introduction/Methods/Discussion/Conclusion and any de-LLM/audit pass → `/med-manuscript-writing` (it reads `research_plan.json`: `study.design`, `estimand_type`, `outcomes`, `covariates`, `multiplicity`, `table_figure_mapping`, `output_dir`, `decision_log`).

7. **Any errors** — which steps failed and the error message from the log

8. **Version history** — if multiple versions exist, show the version timeline

**Results interpretation (opt-in):** At MANDATORY checkpoints, offer brief statistical interpretation:
- Primary outcome effect direction and magnitude
- Consistency between univariate and multivariate results
- Whether baseline differences may confound results
- Whether additional adjustment is recommended

This is NOT mandatory. User can always skip. Maximum 3-4 sentences per interpretation.

---

### Step 7.5: Third-party Verification (第三方驗收) ★ 交付給人之前必做

**When:** 分析結果要寫進 manuscript、交給指導教授 / reviewer / 共同作者之前。純自己看的中途結果可以跳過。**這一步跟 Step 4.5 / 6.5 的 `biostats-guardian` 不重複。** Guardian 稽核的是「設定對不對、程式跑得對不對、結果數值合不合理」；這一步稽核的是「**報告呈現的東西，跟實際跑出來的東西，涵蓋範圍一不一樣**」。

#### 為什麼 —— 這個 domain 最常見的失效模式不是算錯

一次獨立第二輪驗收：543 個數值裡真正算錯只有 9 個，但九項嚴重發現裡有三項是**選擇性呈現**——跑六個分析只列兩個、跑三個 frame 只報兩個、跑兩個亞群只報一個，而且方向一致地朝對假說有利的一邊。逐格核對數值**完全抓不到這種問題**。

#### 怎麼派

1. 派**未參與原分析**的 fresh-context agent（Agent tool `model: sonnet`；fatal 等級爭議的仲裁升 `opus`），**一節一隻**，彼此不通訊（互相看得到就會互相說服）。
2. 每隻的驗收條件 = 逐格核對該節數值 **＋ 必問三題**：① 這個分析總共跑了幾個？報告列了幾個？**差額在哪、為什麼不列？** ② 這個檢定有沒有**對照組／另一層／另一個 frame** 也該跑？沒跑就不能拿它論證特異性。③ **專題報告與主報告的涵蓋範圍差在哪？**
3. 報告中出現、但 `<OUTPUT_DIR>` 任何輸出檔都找不到的數字 → 要求驗收者**自行重算並附程式片段**。找不到來源的數字就是不該存在的數字。三題的完整措辭與「為什麼是問為什麼、不是問是多少」：`${CLAUDE_SKILL_DIR}/references/delivery_discipline.md` §1 規則 3。

#### 發現寫進登記簿，不是寫進對話

```bash
cp ${CLAUDE_SKILL_DIR}/assets/templates/verification_findings.json <OUTPUT_DIR>/data/verification_findings.json
```

在 `research-checks.yaml` 打開 `C4_open_findings` 指向這個檔。**範本是「空的登記簿」，不是「一筆範例」**——`findings` 開出來就是 `[]`，加第一筆是往 `findings[]` 裡塞，不是去改 `_一筆發現的欄位長這樣` 那個說明鍵（它以 `_` 開頭就是為了讓人一眼看出不是資料）。`status` 欄（`open` / `fixed` / `wontfix`）是唯一真值來源，**看門狗 C4 讀它擋交付**；修好改 `fixed` 並寫 `fixed_note`，**不要刪紀錄**。

#### 報告裡的數字要對得到來源 —— `check_numbers_sourced.py`

逐格核對數值這件事**不要再靠人眼或 LLM**。交付前跑 `python3 ${CLAUDE_SKILL_DIR}/scripts/check_numbers_sourced.py <報告檔...> --output-dir <OUTPUT_DIR>`：exit `0` = 每個數字都對得到來源／`1` = 有 `unsourced`，發 `[QC_WARNING] SOURCE:`／`2` = 跑不起來。

> **`unsourced` 是給人讀的清單，不是判決**——可能是合法的手算，也可能是憑印象打的，**由人逐條看**；它把「543 個數字要逐格比對」縮成「這 12 個對不到來源」。**這支腳本不在 `run_pipeline.py` 的呼叫鏈裡**，要自己跑，**沒有任何東西會在你忘記時提醒你。** 分類語意與 `numbers_sourced_report.json` 的欄位見 `${CLAUDE_SKILL_DIR}/references/delivery_discipline.md` §1 規則 3。

#### 跑了但沒報出來的估計 —— `estimate_inventory.py` 與 C7

`python3 ${CLAUDE_SKILL_DIR}/scripts/estimate_inventory.py <OUTPUT_DIR> --reported <報告檔...>` 掃 `<OUTPUT_DIR>` 的 workbook 盤點**實際跑出來的每一個估計**，跟報告引用的數字做差集，寫成 `coverage_diff.json`。exit `0` = 全部都出現在交付物裡；`1` = 有 `omitted`，發 `[QC_WARNING] COVERAGE:`。**`omitted` 不等於作弊**——但每一條都必須有一個寫下來的不列出理由，這正是看門狗 **C7** 讀 `coverage_diff.json` 在擋的東西。`precheck_configs.py --stage post` 會**自己呼叫它**產出這份檔。完整規則見 `${CLAUDE_SKILL_DIR}/references/delivery_discipline.md` §1 規則 3、4。

---

### Step 8: Process Advisor Feedback (處理指導教授回饋) ★ Structured Audit Protocol

When the user provides advisor feedback (trigger phrases: 「老師給了意見」「advisor feedback」「教授回饋」「修改統計」「re-run pipeline」「重跑分析」「老師意見」), follow the 7-step audit protocol defined in `${CLAUDE_SKILL_DIR}/references/feedback_audit_protocol.md`.

#### Step A: Feedback Extraction

```bash
python ${CLAUDE_SKILL_DIR}/scripts/process_feedback.py <FEEDBACK.docx> --output <OUTPUT_DIR>/feedback_parsed.md \
  --plan-path <OUTPUT_DIR>/research_plan.json --backup
```

吃兩種格式：**tracked changes + comments**（解析 `<w:ins>` / `<w:del>` / `<w:comment>` XML tag）與**純文字段落**。產出 `feedback_parsed.md`（人讀）+ `feedback_structured.json`（機器讀，含 items array）。`--backup` 觸發 Step E 的版本備份。

#### Step B: Structured Classification

Claude 把每一項回饋歸進 6 類之一（**first-match-wins order**）：`population_change`（→ ALL steps）→ `outcome_change`（→ km + cr + uni + multi + manuscript）→ `variable_change`（→ table1 + uni + multi + psm + auc）→ `covariate_change`（→ uni + multi）→ `method_change`（依內容而定）→ `presentation_change`（只影響該輸出）。各類的定義、判別規則與完整 impact mapping：`${CLAUDE_SKILL_DIR}/references/feedback_audit_protocol.md` Step B / Step C。

#### Step C: Impact Analysis

產出 Impact Matrix：每一項的 category、affected steps、以及需要的 config 變更（JSON path + from/to），末尾給 `Total affected steps: n/N`。格式範例與 config change specification 見 reference Step C。

#### Step D: Socratic Feedback Discussion (opt-in)

**Trigger conditions:** `affected_steps >= 3` → offer discussion；`<= 2` → skip；全部是 `presentation_change` → skip；使用者說「直接改」「不用討論」「just fix it」→ skip。最多 5 輪。五輪的用途（理解連鎖效應 → 先預測結果方向 → 浮出共線性之類的問題 → 決定 incremental vs full 重跑 → 確認行動計畫）、對話範本與 coaching rules：`${CLAUDE_SKILL_DIR}/references/feedback_audit_protocol.md` Step D（該節整體**待使用者裁決是否保留**，在那之前照現況執行）。

#### Step E: Version Backup

**`--backup` 需要同時給 `--plan-path`**，否則靜默不備份。**腳本做的**：讀版本 N → 備份 `research_plan.json` → `research_plan_v{N}.json` → 把所有 .xlsx/.png/.docx/.csv 複製到 `<OUTPUT_DIR>/v{N}/`、configs 複製到 `v{N}/configs/`（**全部** config，不只受影響的）→ bump `version` 到 N+1、append `version_history`、設 `pipeline_state = "feedback"`、存回 plan。

> 若 `research_plan_v{N}.json` 已存在但 plan 仍停在版本 N，腳本會**以 exit 3 中止**而不是覆蓋。先去看那份舊快照，別讓它被蓋掉。

**Claude 做的（腳本不會做，要自己執行）**：依 Step C 的 Impact Matrix 把受影響的 step 標成 `status = "needs_rerun"`（**沒做這一步，Step F 的「只重跑受影響的」會變成什麼都不跑**）、把本輪分類結果寫進 `feedback_rounds[]`、把每一項回饋登記進 `decision_log.md`（Step H，舊決策標 `superseded`、開新 ID）。

#### Step F: Selective Re-run

1. 只重產受影響的 config：`python3 ${CLAUDE_SKILL_DIR}/scripts/generate_configs.py <plan> --only step1,step2,...`
   > 帶 `--only` 時**自動補 step 的機制整段關閉**（不會偷偷加 `rcs_*` 或 `strobe`），也不能跟 `--migrate` 併用。
2. 執行 pipeline（自動偵測 `needs_rerun`）：`python3 ${CLAUDE_SKILL_DIR}/scripts/run_pipeline.py <plan> [--hitl]`
   > **重產 config 本身就會讓相關的 `done` step 自動降級成 `needs_rerun`**（`mark_stale_steps()` 比對 `config_sha256`），所以就算 Step E 漏標，改過設定的 step 仍會重跑。**但它救不了「設定沒變、只是決策變了」的情況**——Step E 的手動標記仍然必要，只是不再是唯一防線。
3. **`population_change` 特殊處理**：先跑 flowchart 重算 N，之後是 **MANDATORY checkpoint**——「收案人數從 N={old} 變為 N={new}，{change} 人。確認繼續？」使用者確認才跑其餘 step，拒絕就暫停討論。

#### Step G: Diff Report

`python ${CLAUDE_SKILL_DIR}/scripts/pipeline_status.py <OUTPUT_DIR>/research_plan.json --diff {N}`

> **`--diff` 只做檔案層級的清單比對**（哪些輸出檔新增、消失、大小改變）。它**不會**開啟 Excel、不會讀 HR/OR/CI/p。數值 diff 是 **Claude 讀 `v{N}/` 與現行輸出的 Excel 之後自己寫的**——每個數字都要標明來自哪個檔的哪一格，比照 `${CLAUDE_SKILL_DIR}/references/delivery_discipline.md` §1 規則 1（數字單一來源）。

要比較的量（N、HR/OR/aHR/aOR、CI、p、存活率、AUC）與六個 significance change flag 的門檻與符號（方向改變 / 顯著性跨界 / >100% / >50% / >20% / CI 不再重疊）：`${CLAUDE_SKILL_DIR}/references/feedback_audit_protocol.md` Step G。**呈現完 diff 報告是 MANDATORY checkpoint** —— 使用者必須確認新結果才能往下走。

#### Feedback Loop Safety

**Max feedback rounds: 3**（plan JSON 的 `max_feedback_rounds`）。`rounds >= limit` 印警告但**照跑**；`rounds >= limit + 1` **程式擋、`run_pipeline.py` exit 2**，要 `--override-feedback-rounds` 才過（或調高上限**並在 `decision_log.md` 寫明理由**）。

**80-step safety limit**：`total_steps_executed` 跨所有執行（initial + re-runs）不得超過 `max_total_steps`（預設 80），超過強制暫停並警告。逐輪行為表與 Round 3 警告的完整版面：`${CLAUDE_SKILL_DIR}/references/feedback_audit_protocol.md`〈Feedback Loop Safety〉。

#### Step H: Change-control ledger (變更控制紀錄) ★ Mandatory whenever a decision changes

Steps A–G re-run the analysis correctly. They do **not** leave a record of *what the old decision was and why it changed* —— 而報告一旦交給老師，那份紀錄就是任何人（老師、reviewer、六個月後的你）用來判斷哪些數字動了、依誰的指示動的唯一依據。這一節是**額外**做的（in addition to A–G），不是取代。

**三條規則，沒有例外**：① **永不就地覆寫決策，要 supersede**——每個決策帶永久 ID（`A1`、`B5`、`C3`…），**插列時不重用、不重新編號**（報告、驗收文件與 rebuttal letter 都在引用它們），舊列標 `superseded` 並**保留**，另開一個新 ID 的新列；② **每一列都有狀態**：`active`（現行有效，報告的數字來自它）／`superseded`（已被取代——方法欄前面加 `~~已取代 → 見 <new ID>~~`）／`withdrawn`（記錄過但從未採用，例如老師否決）；③ **每次變更 append 一列 ledger**：日期、誰要求的、`舊 ID → 新 ID`、一行理由、要重跑哪些腳本。

**ledger 放哪**（有 `research_plan.json` → plan 的 `version_history` + `feedback_rounds`，**外加**一份人讀得懂的 `decision_log.md` 變更控制節；手工統計專案 → `report/decision_log.md` 最後一節，骨架 `${CLAUDE_SKILL_DIR}/assets/templates/decision_log_skeleton.md` §H，此時本 skill 走 **discipline-only 模式**：不接管統計、不改寫編號腳本，但擁有 ledger、驗收協定與看門狗閘門）、**什麼會觸發 ledger + 重跑**（世代定義／終點／門檻／統計方法／老師否決某做法 = 要；純排版與章節順序 = 不用 ledger，但仍要重跑引用解析與文件 build，否則交付檔會安靜地跟來源分岔；typo 或死路 = 不用）、以及該事故全文：`${CLAUDE_SKILL_DIR}/references/feedback_audit_protocol.md` Step H。

**用新鮮度檢查收尾。** 重跑之後確認每個機器產生的 stats 檔都比資料集與它的產生腳本新、交付文件比它的 markdown 來源新；有看門狗的專案要 **exit 0** 才算做完，沒有的至少要人工比對 timestamp。**一筆背後沒有重跑的 ledger 紀錄比沒有紀錄更糟——它主張了一個數字並未反映的改動。**

---

### Step 9: Save Reusable Pipeline (儲存可重用腳本)

After the pipeline completes successfully:

1. Copy all Python scripts to `<OUTPUT_DIR>/scripts/`
2. Save `research_plan.json` + all configs to `<OUTPUT_DIR>/configs/`
3. Save checkpoint log: `<OUTPUT_DIR>/logs/checkpoints.json` (all checkpoint decisions)
4. Save version history: included in `research_plan.json` under `version_history` and `feedback_rounds`
5. `rerun.sh` —— **不要手打，讓腳本產**：

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/run_pipeline.py <OUTPUT_DIR>/research_plan.json --emit-rerun
```

它寫出 `<OUTPUT_DIR>/rerun.sh`（`chmod 755`）然後**結束，不跑任何 step**。內容由 `RERUN_TEMPLATE` 決定，用 `python3`（不是 `python`）並帶 `set -euo pipefail`。**pipeline 正常跑完時也會自動產一次**，所以多數情況這一步已經做掉了；`--emit-rerun` 是用來補產或更新的。

> **以前這裡貼的是一段要 Claude 照抄的 shell**，那份手打版用 `python`、少了 `set -euo pipefail`——在只有 `python3` 的機器上會直接失敗，而且中間某步錯了還會繼續往下跑。**改動 rerun 的行為要去改 `run_pipeline.py` 的 `RERUN_TEMPLATE`，不要改這份文件裡的副本。**

`--emit-rerun` 會檢查 `scripts/run_pipeline.py` 與 `configs/research_plan.json` 是不是已經在 `<OUTPUT_DIR>` 底下（也就是第 1、2 點做完了沒），沒有的話會出聲警告——**產出的 rerun.sh 指向的是那兩個路徑**，順序顛倒的話它會指到不存在的檔。

Tell the user: "All scripts and configs are saved. You can re-run the entire analysis later with `bash <OUTPUT_DIR>/rerun.sh` without needing Claude. Use `--hitl` for interactive mode or `--no-parallel` to disable parallel execution."

---

### Step 10: End-to-end Verification & Auto-commit (收尾驗證)

#### 10a. 腐爛看門狗 ★ 硬 gate — exit 非 0 不得宣告完成

**先跑這個，再跑其他收尾動作。**

```bash
python3 ${CLAUDE_SKILL_DIR}/assets/check_freshness.py <OUTPUT_DIR>
```

| exit | 意思 | 動作 |
|---|---|---|
| `0` | 啟用的檢查全過 | 繼續 10b |
| `1` | **有問題**——包含「設定裡指到的路徑不存在」 | **停。不 commit、不說「做完了」、不讓使用者拿去交。** 列出每一項紅燈與對應的修法（通常是重跑某支腳本或更新某份文件），修完重跑看門狗 |
| `2` | **跑不起來 —— 這些面向未受保護**。五類來源：沒有 `research-checks.yaml`、`--stage` 值錯、YAML 壞掉、啟用 0 項、`cannot_run` 非空（含**啟用了但比對池是空的**假通過型） | **這不是通過，也不等於「補一份 yaml 就好」。** 先看輸出是哪一種，triage 表見 `references/delivery_discipline.md` §2；只有第一類才回 Step 3d 補設定檔 |

> **exit 2 ≠「路徑不存在」。** 這份文件以前把「設定裡的路徑不存在」寫成 exit 2，是錯的——設定檔在、但它指到的檔不在，會被當成**一項檢查失敗**走 exit 1（實測：`C1: 找不到 stats_index（None）` → exit 1）。分清楚的實益：exit 2 的修法是「補設定檔」，exit 1 的修法是「去把那個檔生出來或改路徑」。

**十項**檢查（C1–C10）的語意見 `${CLAUDE_SKILL_DIR}/references/delivery_discipline.md` §2。**exit 非 0 時唯一允許的回報方式是「卡在哪、要做什麼才會綠」**，不得以「主要分析都跑完了」代替。

> **C8 / C9 / C10 在範本 `research-checks.yaml` 裡是註解掉的，照抄範本開的專案不會啟用它們**（`enabled()` 的規則是「YAML 沒列 = 關」）。註解掉不是因為它們可選，是因為這三項各自需要專案才知道的宣告——C8 要逐份文件寫 `sources:`、C9 要 `paths:`、C10 要 MA 專案根 `root:`——而**整項寫成 `{}` 會被當成「無法進行」走 exit 2，不是通過**。所以範本不能替你猜，只能留一段填空。
>
> 什麼樣的專案該解註解：
>
> - **C8**：只要交付物（docx / md / qmd / 報告）裡會印出數字就該開。它是規則 1「數字單一來源」唯一的閘——前七項全部只比檔案與檔案，沒有一項真的去讀文件裡的那個數字。0813 AF 交給老師的 docx 手打「313 筆」對上登記簿的 315，當時七項全綠。開之前先逐份文件宣告 `sources`（同 C5 的寫法），不要偷懶讓它拿全部 stats 檔當池子——池子越寬越容易撞號。
> - **C9**：只要文件裡會出現絕對句／新穎性宣稱（「至今沒有研究做過 X」「首次」「唯一」）就該開，lit review 與 introduction／discussion 是主要對象。Quarto 把 Introduction 與 Methods 拆成兩檔時用 `scope: dir`（預設），要求證據寫在同一檔裡才算數就用 `scope: file`。
> - **C10**：**只有 MA 版面**（`01_protocol/` … `09_qa/`）才開，一般統計專案開了只會回 exit 2。它對的是稿件裡的 PRISMA 整數 vs 磁碟上的裁定檔——某 MA 專案 稿件寫 47 筆進全文、`fulltext_decisions.csv` 卻有 185 列，兩輪篩選被拼成一張流程圖。

> **這支看門狗也被 `run_pipeline.py` 在 pre-manuscript briefing 裡自動跑一次**（`[3/6]` 段，帶 `--quiet`）。非 0 就變成擋住 manuscript 的 blocker。要放行得先 `run_pipeline.py <PLAN> --override-watchdog <DECISION_LOG_ID>` 記一筆，下次執行才生效。
>
> ⚠ **這個 override 的 ID 沒有被驗證。** 跟 Step 3.5 的 `diagnostics.overrides` 不同，`--override-watchdog` 只把字串原樣存進 `plan.watchdog_override`，**不會去 `decision_log.md` 找它在不在**，也不綁定特定的失敗項目或時間——填了就一直有效到有人手動移除那個鍵。**所以它的可信度完全靠人自律**；用了就要真的去 `decision_log.md` 開一列，並在交接時講明。

> 為什麼是硬 gate：C1 / C5 抓的是「文件裡的數字寫在最後一次重跑之前」——這種錯不會讓任何程式報錯，只會讓交出去的報告安靜地跟它引用的檔案不一致。

#### 10b. 收尾驗證（選用）

Step 9 完成（所有 script 已存檔、`research_plan.json` 定稿）**且 10a 回 exit 0** 後，做一次端到端的最後確認：

1. 用 Glob 確認 `success_criteria.expected_outputs` 全部存在。
2. 確認 10a 的看門狗 exit 0。
3. 若專案是 git repo 且使用者同意，才 commit（訊息註明 verify-passed）；有任何失敗 → 不 commit，交給使用者決定。
4. 使用者說「不用驗證」就整段略過。

> **這裡不再第三次跑 `biostats-guardian`。** 以前寫「在 quick 模式重跑一次 guardian」，但 config 從 Step 4.5 到這裡**一個字都沒改過**（真改了的話 `config_sha256` 會把 step 降級成 `needs_rerun`，那就得回頭重跑，不會走到這裡），所以第三次稽核跑的是同一批輸入、必然得到同一個結論。**重複的稽核不會增加保證，只會增加「跑過三次」的錯覺。**
>
> 剩下的層各自不可取代：
> - **Step 4.5 pre guardian**：跑之前擋設定錯誤（此時還沒有數字）。**auto 模式預設 `quick` 也會跑這一層**
> - **Step 6.5 post guardian**：跑完之後擋結果不合理（此時還沒呈現給人）
> - **Step 10b 收尾驗證**：只確認**可重現性契約**還完整——檔案在不在、看門狗綠不綠、能不能 commit。它稽核的是交付物的狀態，不是統計本身
>
> ⚠ **auto 模式（Step 1 第 13 題的預設值）下 `guardian.mode` 預設是 `quick`，而 Step 6.5 在 `quick` 底下整段跳過。** 也就是說**預設路徑的使用者根本不會跑到 post guardian**。真正接住結果層問題的是 `precheck_configs.py --stage post`（RES-001 數值合理性 / RES-002 N 對齊 flowchart / RES-004 success_criteria / RES-006 EPV，外加 PH remedy gate 與 coverage 盤點），那一層**不受 `guardian.mode` 影響、一定會跑**。
>
> **要 auto 模式也有 LLM 層的結果稽核，得自己把 `guardian.mode` 設成 `standard`。** 這是一個取捨（auto 的賣點就是不打斷），但**不要對使用者說「結果已經過三層稽核」**——預設設定下 LLM 結果稽核那一層是關的。

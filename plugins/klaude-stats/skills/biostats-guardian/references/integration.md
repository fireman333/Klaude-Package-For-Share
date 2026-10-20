# Integration Guide — biostats-guardian × research-plan

## 架構哲學（必讀）

### 第一鐵律：能用 assert 的，不准用 agent（2026-08-11 起）

原本 pre-phase 對「每個 step × 每個 role」派 subagent，2 個 outcome 的專案光 Guardian 家族就是 ~52 隻、佔 token 總量 45–50%，而在可查紀錄裡**抓到 0 件**。原因不是驗得不夠，是**驗錯層**：欄位存不存在、dtype 對不對、EPV 幾、log 裡有沒有 `[QC_*]`，全都是集合運算與比大小，交給 LLM 只是把確定性檢查換成機率性檢查，還更貴。

現在的分層：

| 這類問題 | 誰做 | 為什麼 |
|---|---|---|
| 欄位存在 / dtype / reference level / 篩選後 n / 缺失率 / EPV / 數值合理性 / N 對齊 / success_criteria | `research-plan/scripts/precheck_configs.py`（跑一次，秒級） | 純運算，且 100% 召回 |
| pipeline 自己的 `.py` 有沒有被改過 | `scripts/script_hashes.py`（sha256 比對） | 版本控制下、跨專案完全相同的檔案，不需要每次重讀 |
| **這個專案**選對分析了沒（adjuster 有沒有到齊、outcome 有沒有 route 對、參照組有沒有換掉） | `scripts/plan_routing_audit.py`（plan vs config 比對） | **雜湊過不等於選對**：出貨腳本原封不動、config 卻漏掉事前指定的 adjuster，兩個位元組層檢查都會放行 |
| route 有沒有真的接上（PSM 方向、left truncation、competing event、non-PH、缺失樣態） | `research-plan/scripts/test_routes_synthetic.py`（已知真值 fixture） | mutation testing 已證明既有 516 條 contract test 測不到 wiring；但它跑的是自己的罐頭 fixture，不看這個專案 |
| **欄位存在但意思不對**、estimand / 因果設計、規格本身是不是研究問題要的 | **LLM subagent（保留）** | assert 只能證明「程式照規格跑」，不能證明「規格就是研究問題要的」 |

**刪掉的東西必須有明確的接手者**；沒有接手者的檢查一律保留（寧可多一條檢查，不可掉一條規則）。

### 鐵律：Producer ≠ Evaluator
參考 `research-guardian/references/subagent-evaluation.md` Strategy A。
**每個 Role 1/2/3 subagent 必須是 fresh context**，不得看到：
- Main agent 的 chain-of-thought
- 其他 role 的 report
- 使用者與 Claude 的對話歷史
- 前一次 audit 的結論（avoid anchoring）

實作方式：Claude 用 Agent tool 呼叫 subagent 時，只傳**原始 artifact 路徑**（config JSON、script 檔、log 檔），subagent 自己讀。

### 平行執行
Claude 在**單一 message 內**發出多個 Agent tool calls 即並行。Post-phase 的 Role 3 仍是每個 step 一隻並行；pre-phase 已經沒有 fan-out（見下方模式表）。

Anthropic API 自動排隊處理；不需 Python semaphore。

### 模式與成本（2026-08-11 改版後）

Pre-phase 不再有「每 step 一隻」的 fan-out。Role 1 由 `precheck_configs.py` 取代，Role 2 由 sha256 比對 **加上 `plan_routing_audit.py`** 取代（雜湊管位元組、routing audit 管「這個專案選對沒」——少了後者，改版會留下一個 config 錯了沒人管的洞），只剩一隻**全 plan 一次**的 Semantic Column Reviewer 處理腳本抓不到的語意問題。

| Mode | Pre（腳本） | Pre（agent） | Post（agent） | 全 pipeline 約略 subagent 數 |
|---|---|---|---|---|
| `off` | — | — | — | 0 |
| `quick` | precheck + routing + hash | 0（hash 有 drift 才 +1） | Role 3 RES-014 only（primary outcome） | 0–1 pre + 1 post |
| `standard` | precheck + routing + hash | 1（Semantic Column Reviewer，全 plan 一隻） | Role 3（每 step 一隻，含 RES-014） | 1–2 pre + n_steps post |
| `full` | precheck + routing + hash | 1 + 每個 hash drift 檔一隻 | Role 3 全套 + cross-skill aggregator | 同上 + 1 global |

對照改版前：`standard` 的 pre-phase 是 13 step × 2 role = 26 隻，現在是 1–2 隻。

預設：
- `research_plan.pipeline_mode = "auto"` → guardian `quick`
- `research_plan.pipeline_mode = "hitl"` → guardian `standard`
- 明確關閉：`research_plan.guardian.mode = "off"`
- RES-014 cross-language sanity 開關見 SKILL.md「Cross-language sanity 開關」段；缺省 = 依 mode 自動。

## Pipeline 整合點

### Stage 3.5 — Pre-execution Guardian

**何時：** 在 `run_pipeline.py` 執行**之前**（configs 已生成）。

**步驟：**

1. Claude 讀 `research_plan.json` 取得 `guardian.mode`。若為 `off` 跳過整段。

2. **Step A — 確定性欄位/設定檢查（取代 Role 1 的 per-step fan-out）。** 跑一次，不派任何 agent：
   ```bash
   python ${CLAUDE_SKILL_DIR}/../research-plan/scripts/precheck_configs.py --stage pre \
     --plan {plan_path} --configs {config_dir} --out {output_dir}/guardian/precheck.json
   ```
   它涵蓋 COL-001（欄位存在）／COL-002（dtype）／COL-003（reference level）／COL-005（篩選後 n 與缺失門檻），以及 RES-001（數值合理性）／RES-002（N 對齊 flowchart）／RES-006（EPV）／PSM 方向 assert／`success_criteria` evaluator。輸出沿用 `[QC_BLOCKING]` / `[QC_WARNING]` stderr 慣例。
   - 有 `[QC_BLOCKING]` → **暫停**，比照下方三級處理，不必等 agent。
   - **腳本不存在或跑不起來 → 視為 `block`，不是 pass。**（確定性層失效時要回退到舊的 Role 1 逐 step 稽核，並在摘要裡明講「本次退回 LLM 欄位稽核」。）

3. **Step A2 — plan 層統計 routing 稽核（每次都跑，與腳本有沒有被改無關）：**
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/plan_routing_audit.py \
     --plan {plan_path} --configs {config_dir} --json {output_dir}/guardian/plan_routing.json
   ```
   **這一層補的是雜湊比對本質上補不了的洞。** 雜湊只證明「程式的位元組沒變」，`test_routes_synthetic.py` 只證明「出貨版對它自己的罐頭 fixture 路由正確」——兩者都不過問**這個專案**選對了沒。出貨腳本原封不動、fixture 全綠，而 config 漏掉事前指定的 `stage_tnm`，或 competing-risk 問題被 route 進普通 Cox，兩個檢查都會放行。舊的 Role 2 抓得到這一類（它的示範案例正是「漏掉 adjuster = CODE-005」），因為它是拿著 plan 跟 config 一起看的。這一層把那個能力保留下來，而且是確定性的、不需要 LLM。
   - PR-001 事前指定的 adjustment set 有沒有真的進到 adjusted model（`adjust=false` 或 step 的 `exclude_covariates` 是宣告過的例外 → warn 而非 block；config 有 plan 沒宣告的變項 → warn，silent scope change）
   - PR-002 outcome type ↔ model family ↔ time/event 欄位接線
   - PR-003 competing_risk outcome 有沒有對應的 competing-risk step
   - PR-004 grouping 欄位與組別順序（參照組換掉 = 效應量方向反過來）
   - 判定不了的一律 `[QC_WARNING]` 並指名缺哪個欄位；**沉默不代表通過**。plan / config 讀不到、或一個 step 都比對不到 → exit 2，當 block 處理。

4. **Step B — pipeline 腳本雜湊比對（取代 Role 2 整層）：**
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/script_hashes.py check \
     --project-dir {output_dir} --json {output_dir}/guardian/script_hashes.json
   ```
   - exit 0 → 印一行「pipeline 腳本未修改，跳過程式稽核」，**不派任何 agent**。
   - exit 1 → **只對 drift 的檔案**派 **一隻** Code Auditor（prompt 見下），檢查量表 `references/code-audit.md`；scope 限 `audit_scope[]` 列出的檔案，不是整個 pipeline。
   - exit 2（baseline 不存在）→ 視為 `block`；缺 baseline 不等於沒改動。
   - `check` 每次都會印出這個 baseline 是**哪個 commit、誰、為什麼** bless 的（`git_commit` + `note`），dirty tree 或跳過測試 bless 的會標 `[DIRTY TREE]` / `[tests skipped]`。
   - **⚠ `script_hashes.py update` 由使用者自己執行（含第一次建立基準線）。任何 agent（含主 session）偵測到 hash drift 時，唯一的自動動作是派 Code Auditor 審 diff 並回報；不得自行執行 update。** 威脅模型不是使用者惡意，是「某個 session 為了讓 pipeline 跑過改了 `missing_data.py`，再順手 update 讓 gate 閉嘴」——在鼓勵 agent 順手修的自動化文化裡這是現實風險。
   - Update 預設不要求 git 或測試；可選 `--require-clean-git`（covered scripts 須已 commit）與 `--run-tests`（先跑 `test_routes_synthetic.py` / `test_pipeline_contract.py`，位元組相同不等於行為正確）。
   - **`update` ≠「程式是對的」**：它只證明「這個位元組狀態被人認可了」。「這個專案選對分析沒」是 Step A2 `plan_routing_audit.py` 與語意層的職責，不是 baseline 的。

5. **Step C — route 正確性（一次性成本，非每次執行）：** `research-plan/scripts/test_routes_synthetic.py` 用已知真值的小資料斷言每條 route。它取代的是「Role 2 讀 code 猜 wiring 對不對」；既有的 `test_pipeline_contract.py` **不算**替代品（mutation testing 已證明它測不到 wiring）。CI／skill 升版時跑，不必每個專案跑。

6. **Step D — 語意稽核（保留的 LLM 工作，全 plan 一隻）：** 派 **一隻** Semantic Column Reviewer（`quick` 模式可略過），檢查量表 = `references/column-audit.md` 的「Semantic checks」小節。它做的是腳本做不到的事：欄位存在但**意思不對**（例：`total_ttm_hr` 其實混入 transfer time）、leakage、derived variable 語意、資料字典語意衝突、skill 專屬語意約束。**不要**再叫它檢查欄位存不存在或 dtype——Step A 已用 100% 召回做完了。

7. Claude 用 `scripts/runner.py aggregate` 把 precheck 結果與（若有的）agent report 彙整成 `{output_dir}/guardian/pre_report.json`。

8. 判斷：
   - 有 `block` → 印出繁中摘要 + 詳細 issue，**暫停**請 user 決定（修正 / override / 略過）
   - 只有 `warn` → 印出摘要，若 `block_on_warn=false` 直接繼續
   - 全 `pass` → 一行 ✅ summary 繼續

**Subagent prompt 模板（Semantic Column Reviewer — 全 plan 一隻，read-only；Agent tool `model: sonnet`）：**
```
你是獨立的 Biostats Guardian Semantic Column Reviewer。

[任務] 對整份 research plan 的欄位使用做「語意層」稽核。確定性檢查（欄位存在、dtype、
reference level、篩選後 n、缺失率、EPV）已由 precheck_configs.py 全數跑過，結果在
{output_dir}/guardian/precheck.json — 你要讀它，但**不要重做**這些檢查。

[輸入]
- research_plan.json: {plan_path}
- Data_Dictionary.csv: {dict_path or "N/A"}
- 全部 config: {config_dir}/*.json
- precheck 結果: {output_dir}/guardian/precheck.json
- Data head: 執行 `python -c "import pandas as pd; print(pd.read_excel('{data_file}').head(20).to_string())"` 取得

[Pitfall reference 預讀]
若 `research_plan.json$.dataset` 含資料庫標記（例：`hf_db`、`ttm_db`），或 cwd / data path
match `${CLAUDE_SKILL_DIR}/references/pitfalls_biostat_db.md` 內某資料庫小節
的偵測 regex，先 Read 該小節，把每條 pitfall 當額外 check item 比對 config / data dictionary。
未踩到資料庫 trigger 條件則跳過此預讀。

[檢查量表]
讀 ${CLAUDE_SKILL_DIR}/references/column-audit.md 的 B 節「Semantic checks
(LLM-only)」：COL-004、COL-006、COL-007、COL-008、COL-009、COL-010、COL-011、COL-012。
COL-006 / COL-007 是條件性的：precheck.json 已有結果就直接引用，不要重算。
COL-012（欄位語意 / 測量效度）是本次派工的主要目的，請最花力氣在這一條。

[規則]
- 產生內容的 agent 不能評估自己的輸出：你不看 main agent 的推理。
- 無證據不產生 issue：每個 issue 必須附 evidence（具體 pointer）。
- confidence < 0.6 一律標 severity=uncertain，不要猜。
- precheck.json 已回報過的問題不要重複開 issue。
- 繁中 message，英文 JSON field。

[輸出]
只輸出單一 JSON object，符合 biostats-guardian.schema.json 的 RoleReport。
不要 markdown 包裹、不要前後文字、不要解釋。
```

**Subagent prompt 模板（Code Auditor — 只在 sha256 drift 時派，scope 限 drift 檔案；Agent tool `model: sonnet`）：**
```
你是獨立的 Biostats Guardian Code Auditor。

[任務] pipeline 腳本的 sha256 與 skill 出貨版不一致，代表有人改過。只稽核**改動過的檔案**。

[輸入]
- 雜湊比對結果: {output_dir}/guardian/script_hashes.json（讀 audit_scope[]）
- 出貨版對照: 用 baseline 中的 sha256（以及你自己的備份／git diff，若有）說明差異
- research_plan.json: {plan_path}
- 相關 config: {config_dir}/*.json

[檢查量表]
讀 ${CLAUDE_SKILL_DIR}/references/code-audit.md 的 CODE-001..014，
但**只套用在 audit_scope[] 列出的檔案**。未列出的檔案已由雜湊證明未變更，不要讀、不要評。

[規則]
- 無證據不產生 issue；每個 issue 附 file:line。
- confidence < 0.6 一律標 severity=uncertain。
- 繁中 message，英文 JSON field。

[輸出]
只輸出單一 JSON object，符合 biostats-guardian.schema.json 的 RoleReport。
```

**Subagent prompt 模板（Role 3 — post-execution，含 RES-014 特殊指示；Agent tool `model: sonnet`，fatal 等級爭議的仲裁升 `opus`）：**
```
你是獨立的 Biostats Guardian Role 3 Results Auditor。

[任務] 對以下 biostats skill 的 post-execution 結果做品質稽核（RES-001..014）。

[輸入]
- research_plan.json: {plan_path}
- Skill: {skill}, Step ID: {step_id}, is_primary_outcome: {true|false}
- Output Excel: {output_xlsx_path}
- Pipeline log: {output_dir}/logs/{step_id}.log
- Cleansed CSV (for RES-014 only): {cleansed_csv_path}
- Mode: {quick|standard|full}, cross_lang_check: {auto|true|false}

[檢查量表]
讀 ${CLAUDE_SKILL_DIR}/references/results-audit.md 的 RES-001..014。
RES-014 觸發條件（cross-language sanity）：
- mode=quick + is_primary_outcome=true，或
- mode in {standard, full}（對 regression skill：univariate-forest / multivariate-interaction
  / competing-risk Fine-Gray / auc-cstat C-index），或
- cross_lang_check=true 顯式覆寫
- cross_lang_check=false 顯式關閉 → 跳過 RES-014

[Pitfall reference 預讀]
與 Role 1/2 相同：偵測到資料庫標記時先 Read pitfalls_biostat_db.md 對應小節。

[RES-014 執行協定]
若 RES-014 觸發：你被授權使用 Bash 工具跑最小 reproducible 重算。
- 若主分析是 R survival → 用 `python -c '...lifelines / scksurv...'` 重跑 primary covariate
- 若主分析是 Python lifelines → 用 `Rscript -e 'library(survival); coxph(...)'` 重跑
- 比對 HR / 95% CI / events count / N，相對誤差 thresholds 見 results-audit.md RES-014
- evidence 寫成 `{"type": "cross_lang_repro", "main_HR": ..., "alt_HR": ..., "rel_diff_pct": ...}`
- 注意 tied event method（Efron vs Breslow）、reference level、na handling 三大 false-block 來源

[規則]
- 產生內容的 agent 不能評估自己的輸出：你不看 main agent 的推理 / 其他 role 的 report。
- 無證據不產生 issue。confidence < 0.6 一律 severity=uncertain。
- 繁中 message，英文 JSON field。

[輸出]
只輸出單一 JSON object，符合 biostats-guardian.schema.json 的 RoleReport。
```

### Stage 5 — Post-execution Guardian

**何時：** `run_pipeline.py` 結束後。

**步驟：**
0. 先跑 post 模式的確定性檢查（RES-001 數值合理性 / RES-002 N 對齊 flowchart / RES-004 success_criteria evaluator / RES-006 EPV）：
   ```bash
   python ${CLAUDE_SKILL_DIR}/../research-plan/scripts/precheck_configs.py --stage post \
     --plan {plan_path} --configs {config_dir} --out {output_dir}/guardian/precheck_post.json
   ```Role 3 subagent **讀它、不重算**；缺席時才自己補算並在 summary 註明。
0a. **PH remedy artifact gate（manuscript 之前跑，dispute 5）**：
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/ph_remedy_gate.py \
     --plan {plan_path} --output-dir {output_dir} \
     --json {output_dir}/guardian/ph_remedy_gate.json
   ```
   `multivariate-interaction` 在 plan 宣告了 remedy 時把 PH 違反從 block 降成 warning。那個降級只有在**後面真的有人查 remedy 做了沒**時才站得住——原本沒有，skill 自己的警告寫「must not be presented as the primary estimate until the '{remedy}' analysis **has been run**」，而「has been run」沒有任何程式驗。這支就是驗它的：
   - remedy ∈ {stratify, time_varying, rmst} → pipeline 要有對應 step 且其 declared output 真的存在；缺 → `[QC_BLOCKING]`「declared remedy '{r}' has no artifact; the unremediated Sheet 1 HR may not reach the manuscript」
   - remedy == `disclose` → 要有 `ph_disclose_decision_id` 且該 ID 在 `decision_log.md` 找得到；缺 → block。**disclose 從零成本出口變成一列有永久 ID 的決策。**
   - `status: not_computed` → block（算不出來不是通過）
   - borderline → warning，並註明 reviewer challenge domain 5 必須逐條表態
   - **這道 gate 不擋 multivariate step 本身**：那張未處置的表可以是中間產物，不能進 manuscript。
   - ⚠ **這道 gate 有兩種綠燈，強度差很多，不要混為一談**（2026-08-12 起，報告 schema `ph_remedy_gate/2`）：
     - **verified**：remedy step 旁邊有 evidence sidecar（`<stem>_remedy.json`，schema `ph_remedy_evidence/1`）。gate 會驗它綁的是不是這張表（`table_basename` + `table_sha256`，與 PSM contrast sidecar 同一套綁定）、remedy 是不是宣告的那個、`status` 是不是三態中的 `computed`，以及最關鍵的一條——**實際做的分析有沒有對應到真正發生的違反**（stratify：分層變項要涵蓋 Schoenfeld 判定違反的變項）。進報告的 `verified_remedies`，**不記 manifest、不要簽字**。
     - **unverified**：沒有 sidecar（自建 step，或 sidecar 出現前的舊產物）。退回原本的行為：只證明「宣告的產物存在」，**不打開那個檔**。取一個 id 含 `stratif` 的 step、隨便產一個檔就過得了。
   - **不去解析 xlsx 是刻意的**：sidecar 是唯一契約，再讀一次 workbook 等於同一組事實有兩份定義，一定會漂。sha256 綁定買到的是「這份 sidecar 描述的不可能是別張表」；買不到的是「有人蓄意同時偽造兩者」——那不是任何檔案檢查擋得住的。
   - 因此只要有 remedy 是靠「檔案存在」過關，gate 會在 `configs/manifest.json` 記一條 `ph_remedy_declared_not_computed`（shape 與 `run_pipeline._append_manifest_warning` 相同，依 `kind` 去重），**pre-manuscript 表態閘門會要求作者具名 accept/reject 並寫理由**——理由要寫明「我算了什麼、產物在哪、用什麼方法」。記不進 manifest（例如 manifest 不存在）→ **改為阻擋**：綠燈的正當性本來就建立在「等一下有人要簽字」上，簽字要求記不下來，這個綠燈就沒有根據。
   - unverified 路徑的分工不變：腳本能證明檔案在，只有人能為裡面的內容負責——與 STROBE 作者簽名同一個形狀。
   - **三個 remedy 於 2026-08-12 都有了 step generator**（`ph-stratified` / `ph-time-varying` / `ph-rmst`；宣告後由 `_plan_pipeline_changes()` 依 `generate_configs._REMEDY_STEPS` 自動補 step），都走 verified 路徑。逐 remedy 的內容檢查不同，因為它們出錯的方式不同：`stratify` 驗分層變項有沒有涵蓋違反者；`time_varying` 除了涵蓋還要**時間窗來自 plan**；`rmst` 沒有「涵蓋」可驗（它整個繞開 HR），要驗的是 **tau 來自 plan**——估計是到 tau 為止的積分，看完結果才選 tau 是這個方法全部的 p-hacking 面。切點 / tau 沒宣告時**分析照跑、表照出**，擋的是 manuscript gate：把人擋在沒有出口的門前比放行更糟。
   - ⚠ `rmst` 目前的實作是**未校正**的（各組 KM），是 estimand 的改變而不只是尺度；sidecar 記 `adjusted: false`，gate 每次都發 warning。Results Auditor 讀到這條時要看稿件有沒有照實說。
   - **step 宣告產物用的是不帶副檔名的 stem**（`Multi_primary` → `Multi_primary.xlsx`），gate 比對時會一併試 `<stem>.*`。在此之前它只做字面比對，所以對**所有 pipeline 產生的 step** 都永遠找不到產物——那一側是無聲的 no-op，只有 block 路徑被走過，而它給的答案剛好和「產物真的不存在」該給的一樣，所以看不出來。

0b. 若 pipeline 有 `strobe` step：跑 `scripts/strobe_signoff.py --checklist <Strobe.md> --plan {plan_path} --signed-off-by "<作者>" --out {output_dir}/guardian/domain10_strobe.json`（`--plan` 可省略：預設讀 `strobe_rows.json$.artifacts.plan`，那是 strobe.py 實際建 checklist 用的那份 plan），產出 reviewer-challenge domain 10 的報告。輸出直接是 `reviewer_challenge.py aggregate` 收得下的形狀（`domain: "reporting_strobe"` — 必須與該檔 `DOMAINS` 的 key 逐字相同、頂層 `verdict`、`comments[]` 各帶 verdict/severity/comment/remedy/status/evidence），跑完把它跟其餘九個 domain report 一起餵給 aggregate。**domain key 打錯不是筆誤等級的問題**：schema 驗證失敗 → 該 domain 算未涵蓋 → manuscript gate 擋住，而且訊息指不到真正的原因。它**優先讀 `strobe.py` 產的 `<stem>_rows.json`**（結構化、含每列的 `kind`），找不到才 fallback 去解析 markdown 表格並印一行警告——解析表格是位置耦合，欄位一動就會靜默讀錯。舊專案磁碟上只有 markdown，所以 fallback 保留，但**fallback 一律不放行**：沒有 `kind` 就分不出「流程該產而沒產」與「本來就該作者寫」，此時輸出固定是 `STROBE-UNCLASSIFIED` 的 fatal，簽名也救不了。fallback 是為了讓舊專案不炸掉，不是為了讓它們過關。
   **報告出處**：`ph_remedy_gate.json` / `plan_routing.json` / domain 10 report 都帶 `schema` / `run_id` / `generated_at` / `plan_fingerprint`（domain 10 另帶 `checklist_sha256` 與 `plan_source`），且**動工前先刪、結束時 atomic 寫入**——固定路徑的輸出被 kill 之後留下的是「檔案不存在」而不是「上一輪的通過」。消費端必須驗 fingerprint，並把 `plan_fingerprint: null` 當成無法驗證（不是通過）。**不要為 domain 10 派 agent**——`strobe.py` 已經逐項把 34 列對應到產物，再派一隻 LLM 讀那份 checklist 是重工。腳本唯一補不上的是「人類撰寫的那幾項到底寫了沒」，所以由作者簽名補，沒有簽名 → block。
1. 對每個 pipeline step 的完成結果，在同一 message 內派 Role 3 subagent（Agent tool `model: sonnet`）。
2. 各 subagent 讀 `{output_dir}/logs/{step_id}.log`、`{output_dir}/{output_base}.xlsx`、research_plan.json 的 success_criteria。
3. 彙整成 `guardian_post_report.json`，寫到 `{output_dir}/guardian/post_report.json`。
4. 將 Role 3 issues 用 `[GUARDIAN_WARNING]` / `[GUARDIAN_BLOCKING]` 格式追加進 `research_plan.pipeline[i].qc_warnings[]`。
5. 同樣的三級處理（block → 暫停、warn → 繼續報告、pass → ✅）。

### 不要有第三次（Step 10b 收尾驗證）

`research-plan` Step 10b 的收尾驗證 原本會「Re-run biostats-guardian in quick mode」，那是同一個專案裡的**第三次** guardian。quick 模式就是欄位稽核，而**欄位 config 從 Step 4.5 到 Step 10 之間沒有改過**——第三次是純重複，不是「不同目的」。

Guardian 端的行為（見 SKILL.md 預設行為第 5 條）：偵測到 `{output_dir}/guardian/pre_report.json` 已存在且 config sha256 未變 → 印一行「config 自 pre 階段未變更，跳過重複稽核」後直接返回，**不論呼叫者是誰，包含 `/verify`**。

收尾驗證該做的是 `success_criteria.expected_outputs` 的 glob 檢查 + 看門狗，那是零 token 的腳本工作。呼叫端要同步刪掉那一行（見交接清單）。

## Claude 端的呼叫範例（概念性）

```
# Stage 3.5 pre-phase — 先跑兩支腳本，不派 agent
# --stage 一律顯式寫出來：預設是 pre，所以漏寫時 post 模式會安靜地跑成 pre，
# 少掉 RES-001/002 與 success_criteria 的 post 判定，而輸出看起來一切正常。
<tool_use: Bash> python ${CLAUDE_SKILL_DIR}/../research-plan/scripts/precheck_configs.py --stage pre \
  --plan {plan_path} --configs {config_dir} --out {output_dir}/guardian/precheck.json
<tool_use: Bash> python ${CLAUDE_SKILL_DIR}/scripts/script_hashes.py check \
  --project-dir {output_dir} --json {output_dir}/guardian/script_hashes.json

# 只有這兩種情況才派 agent：
#   (a) standard/full 模式 → 1 隻 Semantic Column Reviewer（全 plan 一隻，不是每 step 一隻）
#   (b) 雜湊 exit 1        → 1 隻 Code Auditor，scope 限 script_hashes.json 的 audit_scope[]
<tool_use: Agent> model: sonnet; subagent: semantic column reviewer for the whole plan

# 彙整（precheck 結果與 agent report 一起進 aggregate）
<tool_use: Bash> python ${CLAUDE_SKILL_DIR}/scripts/runner.py \
  aggregate --phase pre --mode standard \
  --reports {output_dir}/guardian/semantic_report.json ... \
  --out {output_dir}/guardian/pre_report.json

# 印摘要，若 block 則停下請 user ack
```

## User-Facing Output

主 agent 回給 user 的 summary 範例（繁中）：

```
Biostats Guardian 審查摘要（Pre-execution, standard mode）
────────────────────────────────────────────
確定性層（0 個 subagent）
  precheck_configs.py  : 13 steps 檢查完成 — 通過 11、警告 1、阻擋 1
  plan_routing_audit.py: 13 steps 的 config 與 plan 宣告一致
  script_hashes.py     : pipeline 腳本未修改（26 個檔案雜湊一致），跳過程式稽核
語意層（1 個 subagent）
  Semantic Column Reviewer: 警告 1

⚠️  警告：2
  - univariate-forest: COL-005 共變量 age missingness 42%（precheck）
  - multivariate-interaction: COL-012 `total_ttm_hr` 分佈與「目標體溫管理時數」不符，
    p75=71hr 遠超過協議上限 24hr，疑似混入 transfer time（semantic）
🛑 阻擋：1
  - kaplan-meier: COL-002 event_col 有 4 個 unique values（precheck）

請決定：
[A] 修正後重跑 generate_configs.py
[B] Override 阻擋（我已看過，繼續執行）
[C] 略過此 skill
```

摘要**一定要分開列出「確定性層」與「語意層」**，並印出各自派了幾隻 agent。這是防止改版被悄悄回退成 fan-out 的可見指標。

## 手動 ad-hoc invocation

User 也可以在 pipeline 之外手動觸發 guardian：

```
/biostats-guardian pre   # 只跑 pre phase
/biostats-guardian post  # 只跑 post phase
/biostats-guardian all   # pre + post（需 pipeline 已跑完）
/biostats-guardian --skill kaplan-meier --role column  # 指定 skill + role
```

這會由 Claude 讀 `research_plan.json` 找到相關 artifact，派 subagent，輸出 report 到 `{output_dir}/guardian/`。

## 與 research-guardian 的關係

| 面向 | research-guardian | biostats-guardian |
|---|---|---|
| 目標 | 審查 manuscript（hypothesis、literature、writing） | 審查統計 pipeline（columns、code、results） |
| 時機 | 寫作完成後 | 統計執行前 + 後 |
| 輸入 | 論文文字 | research_plan.json + config + script + data + logs |
| Roles | 5 gates + logic chain | 3 roles |
| 可並用 | ✅ 互補；post-execution 後可以再跑 research-guardian 審查 manuscript |

兩者共用 Producer ≠ Evaluator 原則，但 issue schema 不同（因領域差異）。

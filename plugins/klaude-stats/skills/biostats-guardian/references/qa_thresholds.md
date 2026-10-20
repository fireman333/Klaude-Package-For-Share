# QA Thresholds Cheat Sheet

Consolidated thresholds for the deterministic precheck layer and the remaining audit agents. These values define when an issue should be flagged as `warn` vs `block` vs `pass`.

**Source of defaults:** htlin222/survival-pipe `AGENTS.md § QA Thresholds`, adapted to the user's biostats pipeline.

**Override:** Each threshold can be overridden per project by editing `research_plan.json$.qa_thresholds` (reserved — not yet wired through `run_pipeline.py`; currently the values below are the defaults).

**Who applies which row (2026-08-11):** rows marked **[script]** are evaluated by a script — `research-plan/scripts/precheck_configs.py` for COL-*/RES-*, `biostats-guardian/scripts/plan_routing_audit.py` for PR-* — not by an agent — an agent must read that output rather than recompute it. Rows marked **[agent]** need judgement and stay with the Semantic Column Reviewer / Results Auditor. Check IDs below were corrected in the same pass; several previously pointed at the wrong check (e.g. EPV was labelled RES-004, which is `success_criteria`).

---

## Data-quality thresholds

| Check | Warn | Block | Check ID | Who |
|-------|------|-------|----------|-----|
| Missing data in time / event / outcome columns | > 5 % | > 20 % | COL-005 | **[script]** |
| Missing data in grouping column | > 1 % | > 10 % | COL-005 | **[script]** |
| Missing data in key covariates (planned adjusters) | > 10 % | > 30 % | COL-005 | **[script]** |
| Event count per group (KM / CIF) | < 10 | < 5 | COL-007 | **[script]**, agent 只在 precheck 缺席時補 |
| Events per variable (EPV) for Cox — denominator is **fitted parameters**, not variables | < 10 | < 5 | COL-007 (pre) / RES-006 (post) | **[script]** |
| Sample size per subgroup (forest-plot strata) | < 20 events | < 10 events | RES-001 | [agent] |
| Column measures something other than what the plan describes | — | any evidenced case | COL-012 | **[agent]** — 腳本永遠抓不到 |
| Pre-specified adjuster missing from an adjusted model's config | — | any missing adjuster | PR-001 | **[script]** `plan_routing_audit.py`（每次跑，與 script drift 無關） |
| Outcome type vs model family / time-event column mismatch | — | any mismatch | PR-002 | **[script]** 同上 |
| `competing_risk` outcome with no competing-risk step | — | always | PR-003 | **[script]** 同上 |
| Config grouping column or group order differs from the plan | — | any mismatch | PR-004 | **[script]** 同上 — 參照組換掉會讓效應量方向反過來 |
| Config contains variables the plan never declared | any | — | PR-001 | **[script]** silent scope change |

---

## Model-fit thresholds

| Check | Flag condition | Action | Check ID | Who |
|-------|----------------|--------|----------|-----|
| Proportional hazards — global Schoenfeld（gate，rank transform） | **p < 0.01**（不是 0.05：大 n 下臨床無意義的偏離也會顯著，實測 n=6000 的 7% 瑣碎偏離在 0.05 下 15 次觸發 4 次、0.01 下 1 次） | 違反且 plan 無宣告的 `ph_violation_remedy` → **Block**；有 remedy → warn，且 manuscript 前的 `ph_remedy_gate.py` 要求看到 remedy 產物 | RES-015 / CODE-006 | script emits, [agent] adjudicates |
| **PH borderline band** — min p 跨 rank/km 兩個 transform | **0.01 ≤ p < 0.05** | **不 block**。但：禁止「未違反／assumption satisfied」措辭、必須進 `methodological_warnings`、必須附 early/late split HR、交 reviewer domain 5 逐條表態。實測 n=500 的真實 early-only 效應 40 次有 9 次落在此帶 | RES-015 | **[script]** emits, D5 adjudicates |
| PH per-covariate Schoenfeld | **p < 0.01** for any（borderline 同上帶） | Flag 該 covariate；比對 `_ph_diagnostics.png` 的斜率與 split HR | RES-015 | 同上 |
| Declared remedy 沒有對應產物（manuscript 前） | stratify/time_varying/rmst 無 step 產物，或 disclose 無 decision-log ID | **Block** — 宣告不等於執行 | RES-015-det | **[script]** `ph_remedy_gate.py` |
| PH diagnostic artifacts missing — **僅 `multivariate-interaction`** | `_ph_test.json` 不存在 | **Block** — 沒有產物就是沒測。其他 Cox producer 目前不產生這些檔，**不得因缺件而 block**（逐 producer 適用範圍表見 results-audit.md RES-015） | RES-015 | [agent] |
| PH test 算不出來 | `_ph_test.json` 的 `status: not_computed` | **Block** — 算不出來不是通過；skill 本身也會 exit 2 | RES-015 | script emits, [agent] confirms |
| Cox model convergence | Fit failed, iterations maxed, or any NA coefficient | **Block** (invalid results) | RES-007 | **[script]** |
| Cox log-likelihood ratio test | Not significant yet SHR/HR flagged as "significant" | Contradiction → flag | RES-001 | [agent] |
| Fine-Gray model convergence | Fit failed or NA SHR | **Block** | RES-007 | **[script]** |
| Standard error magnitude | HR / SHR CI spans > 5 orders of magnitude (e.g., 0.01–50) | **Block** — unstable estimate, likely small N or collinearity | RES-001 | **[script]** |
| Absurd effect size | HR > 20 or < 0.05 without biological plausibility | Flag for manual review | RES-001 | **[script]** flags, [agent] judges plausibility |
| Kaplan-Meier curve crossings | Multiple crossings with log-rank p < 0.05 | Flag — PH likely violated; consider RMST or Wilcoxon | RES-008 | [agent] |

---

## Reporting / figure thresholds (Results Auditor)

| Check | Rule | Check ID |
|-------|------|----------|
| Figure file present and non-empty | > 10 KB（空圖偵測） | RES-012 |
| Figure resolution | ≥ 300 DPI | RES-012 |
| Number-at-risk table below KM | Required for primary KM figures | RES-008 |
| Count formatting | `n (%)` for categorical counts | RES-013 |
| Continuous summary formatting | `median (IQR)` for skewed; `mean ± SD` for symmetric | RES-013 |
| p-value formatting | `< 0.001` for p < 0.001; otherwise 3 decimals | RES-013 |
| HR / SHR / OR formatting | `x.xx (0.yy–z.zz)` with 95% CI | RES-013 |
| Cited figure / table existence | Every in-text reference must map to an actual output file | RES-012 |
| Abbreviations | Defined at first use in each Table / Figure footnote | RES-013 |

---

## Survival-specific thresholds (Role 3, post-execution)

These complement the **pre-execution** routing checks in `survival-diagnostics` (`${CLAUDE_SKILL_DIR}/../survival-diagnostics/`). QA thresholds here cover what Role 3 audits **after** the KM / CIF / Cox has run:

| Check | Threshold | Action |
|-------|-----------|--------|
| KM median survival CI width | upper / lower ratio > 10 | Flag instability |
| CIF vs 1-KM at median follow-up | Divergence > 0.05 in competing-risk study using 1-KM | **Block** — use CIF instead |
| Gray's test reported without cause-specific Cox | Missing sensitivity analysis | Flag |
| Log-rank p without PH check | Missing | Flag |
| Number at risk dropping to < 10 before max follow-up shown | x-axis extends into sparse tail | Flag |

---

## Usage in subagent prompts

When the Semantic Column Reviewer, the (drift-only) Code Auditor and the Results Auditor read this file via the `references/qa_thresholds.md` pointer in `SKILL.md § Subagent Prompt 模板`, they use these thresholds as the reference point for deciding `severity` on each issue. **Rows marked [script] are inputs, not tasks** — read the precheck output and adjudicate; do not recompute.

- `pass`: metric is within acceptable range
- `warn`: metric violates a Warn threshold → report + continue
- `block`: metric violates a Block threshold → report + halt pipeline (pre-mode) OR mark step error (post-mode)
- `uncertain`: cannot compute metric due to missing info; `confidence < 0.6`

Individual check IDs reference the detailed criteria in:
- `references/column-audit.md` — section A (script-covered) and section B (semantic, agent)
- `references/code-audit.md` (CODE-*) — only invoked when `script_hashes.py check` reports drift
- `references/results-audit.md` (RES-*; RES-003 deleted 2026-08-11, RES-015 scoped per producer)
- `scripts/plan_routing_audit.py` (PR-*) — plan-vs-config routing, runs every time and is
  independent of whether any script changed; `--help` documents each check

This file is the **cross-check summary** — the authoritative numeric thresholds to use when any of those three audits need a quantitative cutoff.

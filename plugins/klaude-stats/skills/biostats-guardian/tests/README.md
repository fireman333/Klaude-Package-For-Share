# Biostats Guardian — Golden-fail Fixtures

Each fixture is a minimal artifact bundle that a Role 1/2/3 subagent should flag with a specific check_id at a specific severity. Fixtures are **contract tests** for the checklists in `references/*.md`; they do not spawn actual subagents.

## How to use

For each fixture:
1. Manually inspect the bundled `inputs/` (or read it as if you were the subagent).
2. Apply the corresponding `references/{column,code,results}-audit.md` checklist.
3. Compare your output against `expected.json`. The check_id + severity must match exactly; the message wording is illustrative.

A fixture passes if a Role N subagent run on the inputs produces (at minimum) the `expected.issues[]` items.

## Fixtures

| Directory | Role | Check | Severity | What's wrong |
|---|---|---|---|---|
| `fixture_wrong_dtype/` | 1 (column) | COL-002 | block | `event_col` has 4 unique values {0,1,2,9}, not binary |
| `fixture_leakage/` | 1 (column) | COL-004 | block | covariate `lab_day30` measured 30 days after `index_date` |
| `fixture_bad_method/` | 2 (code) | CODE-001 | block | script uses `LogisticRegression` for time-to-event outcome |
| `fixture_absurd_hr/` | 3 (results) | RES-001 | block | output table reports HR = 1.2e6 with CI spanning 9 orders |

## Adding a new fixture

```
tests/fixtures/fixture_<short_name>/
├── README.md              # one-line description of the failure mode
├── inputs/                # exact files a subagent would receive
│   ├── research_plan.json
│   ├── {step_id}_config.json   # for Role 1/2
│   ├── {script}.py             # for Role 2
│   ├── data_head.csv           # for Role 1 (simulated df.head(20))
│   ├── logs/{step_id}.log      # for Role 3
│   └── output/{step_id}.xlsx   # for Role 3 (or a CSV proxy)
└── expected.json          # minimum issues the subagent must produce
```

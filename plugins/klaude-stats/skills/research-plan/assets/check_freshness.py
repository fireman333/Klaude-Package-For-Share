"""Staleness watchdog for numeric research deliverables — shared across research/ projects.

Why this exists
---------------
Handoff material tells you what to read. Nothing in it proves that what you read is
still true. Numbers drift out of their sources silently: the dataset is rebuilt but a
downstream analysis is not re-run; the report text is written before the last rerun and
never re-checked against it; a verification round finds real problems that nobody closes.
Every one of those has actually happened in this domain. This script is the proof.

Ten checks. Each is independent and each can be switched off per project.

  C1  every machine-generated stats file is newer than BOTH its generating script and
      the analysis dataset
      -> catches "dataset rebuilt, downstream analyses not re-run"
  C2  every "要改就改這裡" pointer in the decision log still resolves to a file that
      exists, and any symbol named in backticks still appears in that file
      -> catches decision-log rot after refactoring
  C3  the verification document's stated coverage vs the current length of the document
      it verified
      -> catches "the report grew after it was verified"
  C4  the verification findings register has no OPEN findings at blocking severity
      -> catches "it was verified, and the verification found things nobody fixed".
         C3 alone goes green on coverage while severe defects still stand.
  C5  the report is newer than every stats file it quotes
      -> catches "the pipeline was re-run but the prose was not re-checked against it"
  C6  the statistical outputs were independently verified AFTER the last re-run, and no
      stats-stage finding is still open
      -> this is the gate that stops you writing prose on top of unverified numbers.
         C1 proves the numbers are current; C6 proves somebody checked them.
  C7  every estimate that was run either appears in the deliverables or has a written
      reason for not appearing (reads estimate_inventory.py's coverage_diff.json)
      -> catches selective presentation, which C1-C6 cannot see: they all check what
         IS written down, and none of them asks what was left out.
  C8  every number printed in a deliverable is findable in the stats files that
      deliverable declares as its sources (delegates to lint_bare_numbers.py)
      -> catches hand-typed numbers, which C1-C7 structurally cannot see: they all
         compare files against files and none of them reads a number out of prose.
         The 0813 AF handover shipped a hand-typed 313 against a register holding
         315, with all seven checks green.
  C9  every absolute / novelty claim carries its search scope — which databases, what
      search date, how many hits (delegates to lint_absolute_claims.py)
      -> catches an "at present no study has done X" written with nothing retrievable
         behind it. Delivery_discipline rule 5 — the last rule with no tooling.
  C10 every PRISMA number the manuscript claims matches what the screening / full-text /
      extraction files on disk actually count (delegates to reconcile_prisma.py)
      -> catches two screening rounds being spliced into one flow diagram. 某 MA 專案
         reported 47 records advancing to full text while fulltext_decisions.csv held
         185; the tool existed for months and nothing invoked it.

Two-stage use (recommended once a project has ~8+ analysis scripts)
-------------------------------------------------------------------
Run the analysis, then gate on the statistics BEFORE assembling any document:

    python3 check_freshness.py PROJECT_DIR --stage analysis    # C1, C2, C4(stats), C6
    ... only if that exits 0, build the documents ...
    python3 check_freshness.py PROJECT_DIR                     # + C3, C5, C8, C9

Rationale: statistical defects are the expensive ones — they force a rerun AND a rewrite
of every sentence built on them. Document defects are cheap to fix once the numbers are
settled. Gating in that order stops verification effort being spent on prose whose
underlying numbers are about to change. It does NOT remove the need for the document-level
pass: selective presentation, cross-document inconsistency and provenance gaps only exist
once the document exists, and no amount of JSON checking will surface them.

Usage
-----
    python3 <path>/_shared/check_freshness.py [PROJECT_DIR] [--quiet] [--stage analysis|all]

PROJECT_DIR defaults to the current directory. The script reads `research-checks.yaml`
from the project root; see `_shared/templates/research-checks.yaml` for the schema and
`_shared/README.md` for the reasoning. A project with no config is reported as
unconfigured rather than silently passing — an unconfigured project has no guarantees,
and saying "OK" would be a lie.

Exit codes: 0 = every enabled check actually ran and passed. 1 = a check ran and found
a problem. 2 = a check could not run, so that aspect is unprotected.

  2 means "no guarantee was produced": `research-checks.yaml` missing; `--stage` given
  something other than analysis/all; zero checks enabled; C4's findings register absent
  (never verified is not the same as verified clean); a C5 document declaring an empty
  `sources: []` (comparing against nothing always passes); `C7_coverage: {}`,
  `C8_bare_numbers: {}` or `C9_absolute_claims: {}` (an empty config is not a
  config); and either delegated lint returning 2 itself — C8 when a document or a
  declared source file is missing, C9 when a configured path holds nothing scannable.
  A configured *analysis* path that does not exist is still a problem (exit 1), not an
  inability to run.

  Above all of those sits one structural rule (2026-09-03, second audit): every check
  must report how many objects it actually compared this run, and a check that compared
  ZERO is treated as unable to run — never as a pass. An empty comparison pool (an index
  listing no files, a decision log with no pointers, a coverage audit with no executed
  estimates, a missing stats_index) makes a check incapable of finding anything, and the
  old code answered that with a note and exit 0. The named entry points that were patched
  one by one before this were six instances of that one shape. The only legitimate zeros
  are C1b (stats-to-stats edges; folded into C1 and not counted separately) and C8 / C9 /
  C10, whose logic lives in a separate lint that returns its own exit 2 when it has
  nothing to scan.

  Third audit, same day: counting the pool was not enough either. A pool of N entries
  that all point at files which do not exist counted as N compared — 某專案
  declared seven paths, every one under a non-existent analysis/, and stayed green.
  So a check now counts only entries it could actually resolve; the unresolvable ones
  are listed one by one (which path, why), and N declared with zero valid is exit 2.

  Every exit path prints the roster first — which checks were enabled and how many
  objects each compared, which were skipped and why. Exit 0 used to mean either
  "everything passed" or "none ran", with near-identical wording; that ambiguity was the
  root of every false green this script had. (2026-09-03 audit.)

  Fourth round (2026-09-04): C7 reconciles executed = reported + omitted (an emptied
  `omitted` list is no longer a pass); C3 compares the claimed line count against the
  document both ways and can read it from a JSON register field; C4 gains the four
  guards ported from 0813 AF's fork (high-water file against deleted records and
  severity downgrades, `superseded` must name a successor, severity whitelist,
  builder-vs-artefact freshness under C5); config keys are validated; broken JSON /
  YAML is exit 2, not a traceback; `strict_status: no` / `off` / `False` are rejected.

Handing a project folder to someone else
----------------------------------------
This file lives outside the project, so a copied folder cannot run it. Before handing
over, vendor a copy:

    cp <research>/_shared/check_freshness.py <project>/analysis/scripts/_check_freshness_vendored.py

and say in the handover which version was vendored. Keeping the shared copy canonical is
deliberate (fixes reach every project); the vendored copy is for portability only.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 pyyaml：python3 -m pip install pyyaml")

CONFIG_NAME = "research-checks.yaml"
CHECK_KEYS_ALL = ("C1_stats_freshness", "C2_decision_log_pointers", "C3_verification_coverage",
                  "C4_open_findings", "C5_document_vs_stats", "C6_stats_gate", "C7_coverage",
                  "C8_bare_numbers", "C9_absolute_claims", "C10_prisma_reconcile")

# One vocabulary for "this finding is resolved", shared by C4 and C6.
#
# They used to disagree: C4 blocked only `status == "open"`, while C6 blocked
# anything outside ("fixed", "closed", "withdrawn", "n/a"). A finding closed as
# `wontfix` — which delivery_discipline.md rule 4 names as a legitimate way to
# close one — therefore passed C4 and was held by C6, and the message told you to
# go and fix a finding you had already decided about. Two checks reading one
# register must agree on what its status column means.
# 2026-09-04（第四輪，自 0813 AF 分支版回流）：`superseded` 納入結案詞彙，但 C4 另外
# 要求它必須指名登記簿裡存在的繼任者 id（superseded_by 或 fixed_note）——沒說被誰
# 取代的 superseded 是無聲關案，會被記成問題（exit 1）。
CLOSED_STATUSES = ("fixed", "closed", "wontfix", "withdrawn", "n/a", "superseded")
OPEN_STATUSES = ("open",)

# 嚴重度白名單（丙-3）。看門狗讀不懂的嚴重度不能被當成「不嚴重」：以前只比對
# `severity in block_on`，於是 "Severe "（尾隨空白）、"sever"（打錯）都靜默落到不擋那邊。
# 專案可在 C4 用 `severity_vocab:` 覆寫；block_on 裡的值永遠算在白名單內。
DEFAULT_SEVERITY_VOCAB = ("嚴重", "中等", "輕微", "severe", "moderate", "minor",
                          "critical", "major", "high", "medium", "low", "info")


def sev(v) -> str:
    """嚴重度正規化：去頭尾空白、小寫。分支版第 7 輪抓到 "Severe " 靠尾隨空白逃出集合。"""
    return str(v if v is not None else "").strip().lower()


# research-checks.yaml 每一項檢查接受的鍵（丁）。打錯鍵名以前會被靜默忽略——
# `C4_open_finding`（少個 s）看起來像「沒開」，與刻意關掉一模一樣。
ALLOWED_KEYS = {
    "C1_stats_freshness": {"stats_index", "dataset", "data_dir", "scripts_dir"},
    "C2_decision_log_pointers": {"file", "scripts_dir"},
    "C3_verification_coverage": {"verification", "register", "register_field", "document",
                                 "tolerance"},
    "C4_open_findings": {"register", "block_on", "strict_status", "highwater", "severity_vocab"},
    "C5_document_vs_stats": {"document", "stats_index", "data_dir", "scripts_dir"},
    "C6_stats_gate": {"record", "register", "stats_index", "data_dir", "block_on",
                      "strict_status"},
    "C7_coverage": {"report", "reasons", "strict"},
    "C8_bare_numbers": {"document", "data_dir", "stats_index", "report", "min_integer",
                        "ignore_patterns", "extra_sources", "mode"},
    "C9_absolute_claims": {"paths", "path", "scope", "exclude", "strict", "report"},
    "C10_prisma_reconcile": {"root", "report"},
}
DOC_ENTRY_KEYS = {"path", "sources", "builder"}

# Anything else is a status this vocabulary does not know.
#
# 2026-09-03：原本 unknown 預設不擋，要專案自己 opt-in `strict_status: true`。
# 那個過渡期的代價已經兌現了——12 個專案有 9 個沒開，`partially_fixed` 就這樣
# 被當成結案，某專案 的三筆「嚴重」發現對看門狗完全隱形。
# 現在反過來：**strict 是預設**，unknown 一律當未結案；要關掉必須在該項檢查
# 明寫 `strict_status: false`（逃生門保留，但必須是刻意寫下的一行）。
LEGACY_STATUS_MIGRATION = {
    "resolved": "fixed",
    "accepted": "wontfix",
    "acknowledged": "wontfix",
    "deferred": "open",
    "in_progress": "open",
    "in progress": "open",
    "pending": "open",
    "todo": "open",
    # 2026-09-03：`partially_fixed` 是「改了一半」，不是結案。它以前落在 unknown、
    # 而 strict 又預設關著，於是 某專案 的三筆「嚴重」發現一直隱形。
    "partially_fixed": "open",
    "partially fixed": "open",
    "partial": "open",
    "": "open",
}


def status_class(status) -> str:
    """One of 'open' / 'closed' / 'unknown'."""
    s = str(status or "").strip().lower()
    if s in CLOSED_STATUSES:
        return "closed"
    if s in OPEN_STATUSES:
        return "open"
    return "unknown"


def is_open(status, strict: bool = True) -> bool:
    """True when a finding should block.

    `strict` decides what an unrecognised status means. On (the default since
    2026-09-03), unknown blocks: an invented status is not a decision, and reading
    it as one is how a register goes quiet while still holding real problems. Off
    — which now takes an explicit `strict_status: false` — only a literal `open`
    blocks, for a project still mid-migration off `resolved` / `accepted`.
    """
    cls = status_class(status)
    return cls == "open" or (strict and cls == "unknown")


def unknown_statuses(rows) -> dict:
    """{status: count} for every value outside the vocabulary."""
    tally: dict[str, int] = {}
    for r in rows:
        if status_class(r.get("status")) == "unknown":
            tally[str(r.get("status") or "(missing)")] = \
                tally.get(str(r.get("status") or "(missing)"), 0) + 1
    return tally


def report_unknown(where: str, tally: dict, strict: bool, sink: list,
                   outside_block_on: bool = False) -> None:
    """Say what was found and exactly what to change it to.

    2026-09-03（第三輪）：以前 unknown 一律直接寫進 problems，完全不看該項自己宣告
    的 `block_on`——一筆「輕微」的 `partially_fixed` 就能擋交付，而同一筆改成 `open`
    反而放行（某專案 therapy choice EDA 唯一的紅燈來源）。現在呼叫端先依 block_on
    分流：嚴重度在 block_on 內的 unknown 才可能擋；不在的只警告（狀態欄寫壞仍是
    登記簿的缺陷，要遷移，但不是阻擋級）。
    """
    if not tally:
        return
    parts = [f"{v}×{n} → {LEGACY_STATUS_MIGRATION.get(v.strip().lower(), 'open')}"
             for v, n in sorted(tally.items())]
    if outside_block_on:
        why = ("NOT blocking —— 這些發現的嚴重度不在本項 block_on 內，本來就不擋交付；"
               "但狀態欄寫在詞彙表之外是登記簿寫壞的訊號，請遷移成建議值。")
    elif strict:
        why = "Blocking — unknown 一律當未結案（strict 為預設）。"
    else:
        why = ("NOT blocking，因為這項檢查明寫了 `strict_status: false`。遷移完就把那行"
               "拿掉，讓 unknown 恢復阻擋。")
    sink.append(
        f"{where}: {sum(tally.values())} finding(s) carry a status outside "
        f"(open | {' | '.join(CLOSED_STATUSES)}): {'; '.join(parts)}. " + why)


def strict_flag(cfg: dict, where: str, sink: list) -> bool:
    """`strict_status` 只有明寫 false 才算關閉；寫壞的值一律當「設定壞了」。

    2026-09-03：原本寫 `bool(c.get("strict_status", True))`。`.get` 的預設值只在
    **鍵不存在**時生效；鍵在而值是 YAML null（`strict_status:` 冒號後留空）、0 或
    空字串時，`bool()` 一律是 False —— 於是「有人把 true 刪掉但沒刪鍵」這種半途
    編輯會靜默把 strict 關掉，實測三種寫法都能把 exit 1 洗成 exit 0。那不是刻意
    寫下的逃生門，是設定寫壞了。
    現在：沒有這個鍵 → True（strict 是預設）；明寫 true / false → 照辦；其餘任何
    值 → 不猜，回報「無法進行」（exit 2），本輪先以 strict 執行。
    """
    if "strict_status" not in cfg:
        return True
    v = cfg["strict_status"]
    if isinstance(v, bool):
        return v
    sink.append(
        f"{where}: strict_status 的值是 {v!r}，不是 true / false —— 這一項的阻擋"
        f"強度無法判斷。要關掉 strict 必須明寫 `strict_status: false`；空值 / 0 / "
        f"空字串是「把 true 刪掉但沒刪鍵」的半途編輯，不當成關閉；YAML 布林別名"
        f"（no / off / False / yes / on）一律不接受——`grep 'strict_status: false'` 抓不到它們。")
    return True


# 比對池是空的時候，該檢查為什麼等於沒跑 —— 訊息要說得出下一步該補什麼。
ZERO_COMPARISON_HINT = {
    "C1": "（stats_index 的 files 是空的，或裡面每一筆都不是 .py 產生的）",
    "C2": "（決策紀錄裡沒有任何 active 列指向 `xxx.py`）",
    "C3": "（驗收報告或被驗文件讀不到內容）",
    "C4": "（登記簿一筆發現都沒有 —— 從未寫進任何發現，不等於驗過而且乾淨）",
    "C5": "（沒有 stats_index，或索引裡沒有任何可比對的 stats 檔）",
    "C6": "（沒有 stats_index，或索引裡沒有任何可比對的 stats 檔）",
    "C7": "（coverage_diff.json 的 executed 是空的 —— 一個估計都沒跑過的涵蓋率"
          "稽核擋不住選擇性呈現）",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_lint(script: str, argv: list[str], cwd: Path) -> tuple[int, str]:
    """跑 assets/ 底下的 lint，回 (exit_code, 合併輸出)。找不到腳本回 (2, 說明)。

    C8 / C9 的判斷邏輯刻意不寫在這裡，而是各自獨立的 lint 腳本：它們要能單獨跑
    （寫作當下反覆掃一份 md），也要能被看門狗當閘用。這個函式只做三件事——確認
    腳本在、跑它、把它的 exit code 翻成本檔的 cannot_run / problems。

    為什麼一定要接上來：這個 domain 的問題不是缺工具，是工具的執行不是強制的。
    某專案的涵蓋率差集算得出來但閘關著、某 MA 專案 的 prisma_flow.py 存在但沒人
    跑——兩支新 lint 若只放在 assets/ 沒接進閘，三個月後就是第三、第四個實例。
    """
    path = Path(__file__).parent / script
    if not path.exists():
        return 2, (f"找不到 {path} —— 這一項無法進行（lint 腳本不在 assets/ 底下）。"
                   "這不是通過：沒有腳本就沒有跑過任何檢查。")
    proc = subprocess.run(
        [sys.executable, str(path), *argv],
        cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def lint_status(root: Path, checks: dict) -> int:
    """`--lint-status`: the one-off migration report. Changes nothing.

    Exists so that "migrate, then turn on strict_status" is an instruction someone
    can follow, rather than an instruction to go and read every register by hand.
    """
    seen = 0
    for key in ("C4_open_findings", "C6_stats_gate"):
        cfg = checks.get(key)
        if not isinstance(cfg, dict):
            continue
        # C6 inherits C4's register when it does not name one — mirror the
        # runtime fallback, or the lint quietly reports on half the checks.
        rel = cfg.get("register") or (checks.get("C4_open_findings") or {}).get("register")
        if not rel:
            continue
        reg = root / rel
        print(f"\n{key} → {rel}")
        if not reg.exists():
            print("  (register not on disk)")
            continue
        raw = json.loads(reg.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else raw.get("findings", [])
        classes: dict[str, int] = {}
        for r in rows:
            classes[status_class(r.get("status"))] = \
                classes.get(status_class(r.get("status")), 0) + 1
        print(f"  {len(rows)} finding(s): "
              + ", ".join(f"{k} {v}" for k, v in sorted(classes.items())))
        tally = unknown_statuses(rows)
        if not tally:
            print("  ✓ every status is in the vocabulary — 這項檢查可以拿掉 "
                  "`strict_status: false`（strict 已是預設）")
            continue
        seen += sum(tally.values())
        print("  rows to migrate (id → current → suggested):")
        for r in rows:
            if status_class(r.get("status")) != "unknown":
                continue
            cur = str(r.get("status") or "(missing)")
            print(f"    {str(r.get('id', '?')):<10s} {cur:<14s} → "
                  f"{LEGACY_STATUS_MIGRATION.get(cur.strip().lower(), 'open')}")
    print(f"\n{seen} finding(s) need migrating. Nothing was changed; edit the "
          f"register(s)，改完再跑一次。strict 自 2026-09-03 起是預設，所以"
          f"未遷移的狀態現在就會擋——臨時要放行請在該項檢查明寫 "
          f"`strict_status: false`，並記得遷移完拿掉。")
    return 0 if seen == 0 else 1


USAGE = """用法：check_freshness.py [PROJECT_DIR] [--quiet] [--stage analysis|all] [--lint-status]

腐爛看門狗：十項檢查 C1–C10，啟用哪幾項由 PROJECT_DIR/research-checks.yaml 決定
（沒有那個檔 = 未受保護 = exit 2，不是通過）。C8/C9/C10 委派給同目錄的
lint_bare_numbers.py / lint_absolute_claims.py / reconcile_prisma.py。

  PROJECT_DIR      專案根目錄（放 research-checks.yaml 的那層）；省略時用目前目錄
  --stage analysis 只跑統計層的檢查（C1、C2、C4、C6），組文件之前先擋
  --stage all      全部（預設）
  --quiet          只印結論
  --lint-status    一次性遷移報告：列出登記簿裡看不懂的 status 字，什麼都不改

退出碼： 0 = 啟用的檢查全過 ／ 1 = 有紅燈 ／ 2 = 跑不起來（沒設定檔、
        沒啟用任何檢查、YAML 壞掉、--stage 值不合法）——2 不是通過。

說明文件：<RESEARCH_PLAN_DIR>/references/delivery_discipline.md §2
"""


def main() -> int:
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    quiet = "--quiet" in argv
    stage = "all"
    if "--stage" in argv:
        i = argv.index("--stage")
        if i + 1 >= len(argv) or argv[i + 1] not in ("analysis", "all"):
            print("✗ --stage 只接受 analysis 或 all")
            return 2
        stage = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    args = [a for a in argv if not a.startswith("-")]
    root = Path(args[0]).resolve() if args else Path.cwd()

    def say(msg: str = "") -> None:
        if not quiet:
            print(msg)

    def head(title: str) -> None:
        say("")
        say("=" * 78)
        say(title)
        say("=" * 78)

    def tail(text: str, n: int = 2) -> str:
        """委派 lint 的結論那幾行——收尾清單要看得出「為什麼紅」，不是只有項目名。

        分隔線與「報告寫到哪」這種行不帶進來：它們會把結論擠出這 n 行，讓收尾清單
        只剩一串路徑，等於沒說原因。
        """
        drop = ("報告：", "JSON 已寫入：")
        lines = [ln.strip() for ln in (text or "").splitlines()
                 if ln.strip() and set(ln.strip()) != {"="}
                 and not ln.strip().startswith(drop)]
        return " ／ ".join(lines[-n:]) if lines else "(lint 無輸出)"

    cfg_path = root / CONFIG_NAME
    if not cfg_path.exists():
        print(f"✗ {root} 沒有 {CONFIG_NAME} —— 這個專案未受看門狗保護。")
        print(f"  範本：{Path(__file__).parent / 'templates' / CONFIG_NAME}")
        print("  （未設定不等於通過。沒有設定就沒有任何保證。）")
        return 2

    # 丁：壞掉的 YAML 以前直接 traceback（exit 1），與本檔自己定義的「跑不起來 = 2」矛盾。
    try:
        raw_yaml = cfg_path.read_text(encoding="utf-8")
        cfg = yaml.safe_load(raw_yaml) or {}
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as e:
        print(f"✗ {cfg_path} 解析失敗（{type(e).__name__}）—— 設定檔壞了，等於沒有設定。")
        print(f"  {str(e).splitlines()[0][:200] if str(e) else ''}")
        return 2
    if not isinstance(cfg, dict) or not isinstance(cfg.get("checks", {}) or {}, dict):
        print(f"✗ {cfg_path} 的頂層或 checks 不是鍵值對 —— 設定檔壞了，等於沒有設定。")
        return 2
    checks = cfg.get("checks", {}) or {}
    problems: list[str] = []
    notes: list[str] = []
    # 「檢查根本跑不起來」與「檢查跑了、發現問題」是兩件事，退出碼也不同：
    # cannot_run → exit 2（未受保護），problems → exit 1（有問題）。
    cannot_run: list[str] = []

    def jload(path: Path, short: str):
        """讀 JSON。壞掉的檔回 {} 並記 cannot_run：讀不到是「無法檢查」，不是通過、也不是「有問題」。"""
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            cannot_run.append(
                f"{short}: {path} 讀不動（{type(e).__name__}: {str(e)[:80]}）—— "
                f"壞掉的 JSON 不是通過，這一項無法進行。")
            return {}

    # 丁：鍵名驗證。未知的檢查鍵 / 子鍵 → 無法進行（exit 2）：打錯的那項不是「沒開」，
    # 是「以為開了其實沒開」。頂層多餘的鍵只提醒。
    import difflib
    for k in list(checks):
        if k not in CHECK_KEYS_ALL:
            near = difflib.get_close_matches(str(k), CHECK_KEYS_ALL, n=1, cutoff=0.6)
            cannot_run.append(
                f"設定: 未知的檢查鍵 `{k}`" + (f"（是不是 `{near[0]}`？）" if near else "")
                + " —— 打錯鍵名的檢查會被靜默當成沒開，與刻意關掉一模一樣。")
            continue
        v = checks[k]
        if not isinstance(v, dict):
            continue
        bad_sub = sorted(str(s) for s in v if s not in ALLOWED_KEYS[k])
        if bad_sub:
            cannot_run.append(
                f"{k.split('_')[0]}: 未知的設定鍵 {bad_sub}（{k} 只接受 "
                f"{sorted(ALLOWED_KEYS[k])}）—— 打錯的鍵會被靜默忽略，這一項無法確認有照設定跑。")
        docs_v = v.get("document")
        for d in (docs_v if isinstance(docs_v, list) else []):
            if isinstance(d, dict):
                bad_e = sorted(str(s) for s in d if s not in DOC_ENTRY_KEYS)
                if bad_e:
                    cannot_run.append(
                        f"{k.split('_')[0]}: document 清單裡 {d.get('path')!r} 有未知的鍵 "
                        f"{bad_e}（只接受 {sorted(DOC_ENTRY_KEYS)}）。")
    for k in cfg:
        if k not in ("project", "checks"):
            notes.append(f"設定: 頂層多了一個看門狗不認識的鍵 `{k}`（只讀 project / checks）")

    # 丁：strict_status 的 YAML 布林別名。`no` / `off` / `False` 被 PyYAML 解析成 False，
    # 與明寫的 `false` 在記憶體裡無法區分，所以回頭掃原文：字面不是 true / false 的，
    # 把原文塞回設定，讓 strict_flag 用同一條「寫壞了」路徑報出來（本輪以 strict 執行）。
    cur_key = None
    for line in raw_yaml.splitlines():
        s = line.split("#", 1)[0].rstrip()
        m = re.match(r"^\s*(C\d+_\w+):", s)
        if m:
            cur_key = m.group(1)
            continue
        m = re.match(r"^\s+strict_status:\s*(.*)$", s)
        if m and isinstance(checks.get(cur_key), dict):
            lit = m.group(1).strip()
            if lit not in ("true", "false"):
                checks[cur_key]["strict_status"] = lit
    # 2026-09-03：每一項檢查都必須自報「這次實際比對了幾個對象」。
    # 假綠燈的共同形狀不是幾個具名入口的個別 bug，而是「比較池是空的就走 note」：
    # 索引裡沒有檔、決策紀錄沒有指標、coverage 沒有 executed、沒有 stats_index——
    # 舊版一律印一句「跳過」或「檢查了 0 個」然後回 0。比對 0 個對象的檢查沒有能力
    # 發現任何問題，它的「通過」不帶任何資訊。收尾統一判定，見檔尾 verdict 段。
    compared: dict[str, int] = {}
    # 判斷邏輯在獨立 lint 裡的三項：掃不到東西時由該 lint 自己回 exit 2（本檔翻成
    # cannot_run），所以這裡不重複計數，也不套 0 個對象的規則。
    DELEGATED = {"C8", "C9", "C10"}

    def counted(short: str, n: int) -> None:
        compared[short] = compared.get(short, 0) + int(n)

    # 2026-09-03（第三輪）：只堵「比對 0 個」還不夠。宣告 N 項而每一項都指向不存在
    # 的檔案，counted 照樣是 N——某專案七項路徑全指向不存在的 analysis/…，
    # 卻長期綠燈；三筆 source 指向不存在 xlsx 的 executed 也能讓 C7 印「比對 3 個」。
    # 所以 compared 只算「真的解析得動」的項：檔案存在、格式讀得動、沒被濾掉。
    # 讀不到的另外記進 invalid（哪個路徑、為什麼），收尾逐條列出；宣告了 N 項而
    # 有效 0 項 → exit 2，不是通過。
    # （命名成 n_declared 是因為 C5 已有一個區域變數叫 declared——每份文件宣告的來源。）
    n_declared: dict[str, int] = {}
    invalid: dict[str, list[str]] = {}

    def declare(short: str, n: int) -> None:
        n_declared[short] = n_declared.get(short, 0) + int(n)

    def invalid_item(short: str, what: str, why: str) -> None:
        invalid.setdefault(short, []).append(f"{what}（{why}）")

    if "--lint-status" in argv:
        return lint_status(root, checks)

    def p(rel: str | None) -> Path | None:
        return (root / rel) if rel else None

    # 只在 documents 存在之後才有意義的檢查。--stage analysis 時跳過它們：
    # 此時文件還沒組，拿它們當失敗理由是假警報。
    # C8 / C9 讀的是文件裡的字，文件還沒組起來時跑它們等於掃空氣，所以同屬文件階段。
    # C10 對帳的是稿件裡宣稱的 PRISMA 數字，稿件還沒寫時同樣沒東西可對。
    DOCUMENT_STAGE_CHECKS = {"C3_verification_coverage", "C5_document_vs_stats",
                             "C8_bare_numbers", "C9_absolute_claims", "C10_prisma_reconcile"}

    CHECK_KEYS = CHECK_KEYS_ALL

    def enabled(key: str):
        """Return the check's config dict, or None if the check is off (or out of stage)."""
        if stage == "analysis" and key in DOCUMENT_STAGE_CHECKS:
            return None
        v = checks.get(key)
        if v in (None, False):
            return None
        return v if isinstance(v, dict) else {}

    # 收尾訊息一定要說清楚「跑了哪幾項、跳過哪幾項、為什麼跳過」。
    # 少了這一段，exit 0 有兩種完全不同的意思（七項全過 / 零項啟用），而訊息長得一樣
    # ——這是本檔所有假綠燈的共同根源。（2026-09-03 稽核）
    def check_roster() -> tuple[list[str], list[str]]:
        on, off = [], []
        for k in CHECK_KEYS:
            short = k.split("_")[0]
            if stage == "analysis" and k in DOCUMENT_STAGE_CHECKS:
                off.append(f"{short}（--stage analysis：文件階段，本階段不跑）")
            elif checks.get(k) in (None, False):
                off.append(f"{short}（{CONFIG_NAME} 沒開）")
            else:
                on.append(short)
        return on, off

    def compared_label(short: str) -> str:
        if short in DELEGATED:
            return "委派 lint 自報"
        bad = len(invalid.get(short) or [])
        return f"比對 {compared.get(short, 0)} 個對象" + (f"，另 {bad} 項無效" if bad else "")

    def print_roster() -> None:
        # 名冊只報開關是不夠的：「啟用但比了 0 個」看起來與「啟用且真的比過」一模一樣。
        on, off = check_roster()
        shown = [f"{s}（{compared_label(s)}）" for s in on]
        print(f"啟用 {len(on)} 項：{'、'.join(shown) if shown else '（無）'}")
        print(f"跳過 {len(off)} 項：{'、'.join(off) if off else '（無）'}")

    def print_notes() -> None:
        # notes 以前只在 exit 0 印。於是紅燈時，status 遷移提示（「這幾筆狀態不在
        # 詞彙表裡」）整段消失——正好是最需要看到它的時候。
        if notes and not quiet:
            print()
            for n in notes:
                print("  (note)", n)

    say(f"專案：{cfg.get('project', root.name)}    ({root})")

    # A1：啟用 0 項時印「✓ 全部通過（啟用 0 項）」+ exit 0，等於「清空 yaml = 一鍵轉綠」。
    if not check_roster()[0]:
        print(f"✗ {cfg_path} 沒有啟用任何檢查 —— 這個專案未受看門狗保護。")
        # 唯一那項鍵名打錯時，真正的原因是鍵名錯了，要先講出來（丁）。
        for x in cannot_run:
            print("  •", x)
        print_roster()
        print("  （啟用 0 項不等於通過。沒有跑任何檢查就沒有任何保證。）")
        print(f"  範本：{Path(__file__).parent / 'templates' / CONFIG_NAME}")
        if stage == "analysis":
            print("  （若本專案只設定了文件階段的檢查，改跑不帶 --stage 的完整版。）")
        return 2

    # ─────────────────────────────────────────────── C1 stats freshness
    c = enabled("C1_stats_freshness")
    if c is not None:
        head("C1  stats 檔是否比它的產生腳本與資料集新")
        idx_p = p(c.get("stats_index"))
        scripts_dir = p(c.get("scripts_dir")) or root
        data_dir = p(c.get("data_dir")) or root
        # dataset 可以是單一路徑、路徑清單，或含 glob（例如逐 SNP 一個 JSON 的抓取結果）。
        # 取所有命中檔案裡最新的 mtime —— 只要有任何一份原始資料比 stats 新就該重跑。
        spec = c.get("dataset")
        pats = spec if isinstance(spec, list) else ([spec] if spec else [])
        hits: list[Path] = []
        for pat in pats:
            hits.extend(sorted(root.glob(pat)) if any(ch in pat for ch in "*?[")
                        else ([root / pat] if (root / pat).exists() else []))
        if not idx_p or not idx_p.exists():
            problems.append(f"C1: 找不到 stats_index（{c.get('stats_index')}）")
        elif not hits:
            problems.append(f"C1: 找不到資料集（{spec}）")
        else:
            ds_mt = max(h.stat().st_mtime for h in hits)
            if len(hits) > 1:
                say(f"  （資料集：{len(hits)} 個檔，取最新者為基準）")
            for name, meta in sorted((jload(idx_p, "C1").get("files", {})).items()):
                gen, f = meta.get("產生者") or meta.get("generated_by"), data_dir / name
                declare("C1", 1)
                if not f.exists():
                    problems.append(f"C1: {name} 不存在（索引有列，檔案不見了）")
                    invalid_item("C1", str(f), "索引有列但檔案不存在")
                    continue
                if not gen or not str(gen).endswith(".py"):
                    notes.append(f"C1: {name} 非程式產生（{gen}），跳過")
                    continue
                # 稽核檔記錄的是「某份交付物含什麼」，屬於 document 階段。跑 --stage analysis
                # 時文件依設計還沒組，抱怨它們過期是每次都會出現的假警報 —— 而每次都出現的
                # 警報會訓練使用者忽略整個閘門。（2026-08-10，第一次跑 stage A 就踩到。）
                if stage == "analysis" and (meta.get("稽核檔") or meta.get("audit_only")):
                    continue
                script, mt, bad = scripts_dir / gen, f.stat().st_mtime, []
                if mt < ds_mt:
                    bad.append(f"比資料集舊 {(ds_mt - mt) / 60:.0f} 分鐘")
                # 產生腳本不存在時，以前照樣記數、只比資料集那一半。半個比對證明不了
                # 「比腳本新」，不算有效項；資料集那一半照比，過期仍然會擋。
                if not script.exists():
                    invalid_item("C1", name, f"產生腳本 {script} 不存在，「比腳本新」無從比對")
                else:
                    counted("C1", 1)
                    if mt < script.stat().st_mtime:
                        bad.append(f"比 {gen} 舊 {(script.stat().st_mtime - mt) / 60:.0f} 分鐘")
                if bad:
                    problems.append(f"C1: {name} 過期（{'；'.join(bad)}）→ 重跑 {gen}")
                    say(f"  ✗ {name:32s} {'；'.join(bad)}")
                else:
                    say(f"  ✓ {name:32s} fresh")

    # ── C1b stats-to-stats dependencies ───────────────────────────────────────
    # C1 compares each stats file against its own script and the dataset. It has no
    # notion of one analysis reading another analysis's output, so a script that runs
    # too early either crashes on a clean checkout or silently reuses last round's
    # numbers — and C1 calls it fresh either way. Declare the edges in stats_index
    # ("讀取自": ["weighting_stats.json", ...]) and they get checked here.
    # (Added 2026-08-10 after exactly that failure mode was found in a real pipeline.)
    c = enabled("C1_stats_freshness")
    if c is not None:
        idx_p = p(c.get("stats_index"))
        data_dir = p(c.get("data_dir")) or root
        if idx_p and idx_p.exists():
            files = jload(idx_p, "C1").get("files", {})
            edges, backwards = 0, []
            for name, meta in sorted(files.items()):
                deps = meta.get("讀取自") or meta.get("reads_from") or []
                f = data_dir / name
                if not f.exists() or not deps:
                    continue
                for dep in deps:
                    d = data_dir / dep
                    if not d.exists():
                        backwards.append(f"{name} 宣告讀取 {dep}，但該檔不存在")
                        continue
                    edges += 1
                    if f.stat().st_mtime < d.stat().st_mtime:
                        backwards.append(
                            f"{name} 比它讀取的 {dep} 舊 "
                            f"{(d.stat().st_mtime - f.stat().st_mtime) / 60:.0f} 分鐘")
            if edges or backwards:
                head("C1b  stats 檔之間的相依：讀別人輸出的，有沒有比對方舊")
                if backwards:
                    problems.append("C1b: " + "；".join(backwards)
                                    + " —— 執行順序錯了，該檔用的是上一輪的值。")
                    for b in backwards:
                        say(f"  ✗ {b}")
                else:
                    say(f"  ✓ {edges} 條相依全部方向正確")

    # ──────────────────────────────────── C2 decision-log pointer integrity
    c = enabled("C2_decision_log_pointers")
    if c is not None:
        head("C2  決策紀錄的「要改就改這裡」是否還指得到東西")
        dl, scripts_dir = p(c.get("file")), p(c.get("scripts_dir")) or root
        if not dl or not dl.exists():
            problems.append(f"C2: 找不到決策紀錄（{c.get('file')}）")
        else:
            checked = 0
            for line in dl.read_text(encoding="utf-8").split("\n"):
                if not line.startswith("|") or "`" not in line:
                    continue
                cells = [x.strip() for x in line.split("|")]
                if len(cells) < 3:
                    continue
                # 2026-08-11：只檢查 active 列。決策紀錄是 append-only 的——superseded /
                # withdrawn 的列描述「被取代的舊做法」，它們指向的程式碼本來就已經刪掉了，
                # 符號必然不存在。檢查它們會製造永久紅燈，等於懲罰正確的簿記。
                # 觸發事故：放寬檔名正則的同一天，某專案第一篇的 A1（`load_raw`）與 A2
                # （`TEMP_TEXT_RULE`）兩列翻紅，兩者都是 superseded、都是 A4 取代掉的舊路徑。
                if any(c.strip() in ("superseded", "withdrawn") for c in cells[:4]):
                    continue
                target = cells[-2]          # 最後一欄；新增欄位務必插在它之前
                # 2026-08-11：放寬為任何 .py。原本只吃 `NN_*.py`，於是決策紀錄裡指向共用模組
                # （`_common.py`、`firth.py` 之類）的列會被**整列靜默跳過**——某專案第二篇有 19 列、
                # 第一篇的 C4 列（`_common.py` `FILTER_COLS`）也從未被檢查過。規格常數往往正是
                # 住在共用模組裡，漏掉它們等於漏掉最該檢查的一批。
                # 觸發事故：第二輪複驗發現 6 個決策指標指向不存在的符號（SPLINE_KNOTS /
                # fit_primary / STOPPING_RULE / BIAS / SOURCE / 「檔頭說明」），而 C2 當時對那些
                # 列完全沒有意見。使用者 2026-08-11 明確同意放寬。
                files = re.findall(r"`([A-Za-z0-9_]+\.py)`", target)
                if not files:
                    continue
                bodies = {}
                for fn in files:
                    declare("C2", 1)
                    fp = scripts_dir / fn
                    if not fp.exists():
                        problems.append(f"C2: 決策紀錄指向不存在的腳本 {fn}")
                        invalid_item("C2", str(fp), "決策紀錄指向的腳本不存在")
                        say(f"  ✗ {fn} 不存在")
                        continue
                    checked += 1
                    bodies[fn] = fp.read_text(encoding="utf-8")
                if not bodies:
                    continue
                for sym in [t for t in re.findall(r"`([^`]+)`", target)
                            if t not in files and not t.endswith(".py")]:
                    key = re.sub(r'^df\["|"\]$', "", sym).strip().split("(")[0].strip().rstrip(" =.")
                    if not key or len(key) < 3 or " " in key:
                        continue            # prose, not a symbol
                    if not any(key in b for b in bodies.values()):
                        problems.append(f"C2: {'/'.join(bodies)} 裡都找不到 `{sym}`")
                        say(f"  ✗ {'/'.join(bodies)}: 找不到 `{sym}`")
            counted("C2", checked)
            say(f"  檢查了 {checked} 個腳本指標")

    # ───────────────────────────────────────── C3 verification coverage drift
    c = enabled("C3_verification_coverage")
    if c is not None:
        head("C3  驗收涵蓋的版本 vs 現行文件")
        # 乙（第四輪）：以前只要兩檔都在、驗收報告裡有「NNNNN 行版本」字樣就 counted 1，
        # 而且只擋「文件比宣告的長」——填 99999 行、一行都沒驗照樣 ✓。現在宣告行數與
        # 文件實際行數雙向比對，差距超過 tolerance 就報。行數來源支援兩種：
        #   (a) verification 指向 md，找第一個「N 行版本」字樣（原格式）
        #   (b) verification（或 register）指向 .json，讀 register_field 欄位
        #       （預設 verified_report_lines；0813 AF 把行數記在登記簿裡而不是 md）
        ver = p(c.get("verification") or c.get("register"))
        doc = p(c.get("document"))
        tol = float(c.get("tolerance", 1.02))
        declare("C3", 1)
        missing3 = [str(q) if q else f"（設定沒寫 {k}）"
                    for k, q in (("verification", ver), ("document", doc))
                    if not q or not q.exists()]
        if missing3:
            problems.append(f"C3: 驗收報告或被驗文件不存在（{'、'.join(missing3)}）")
            for m in missing3:
                invalid_item("C3", m, "檔案不存在")
        else:
            cur = len(doc.read_text(encoding="utf-8").split("\n"))
            claimed3 = None
            if ver.suffix.lower() == ".json":
                field3 = str(c.get("register_field") or "verified_report_lines")
                raw3 = jload(ver, "C3")
                where3 = f"{ver.name} 的 {field3}"
                try:
                    claimed3 = int(raw3.get(field3)) if isinstance(raw3, dict) \
                        and raw3.get(field3) is not None else None
                except (TypeError, ValueError):
                    claimed3 = None
            else:
                m = re.search(r"(\d{3,5})\s*行版本", ver.read_text(encoding="utf-8"))
                where3 = f"{ver.name} 的「N 行版本」字樣"
                claimed3 = int(m.group(1)) if m else None
            if claimed3 is None:
                problems.append(f"C3: 驗收報告沒寫明驗過的版本行數（找不到 {where3}），"
                                f"無法判斷覆蓋範圍")
            elif claimed3 <= 0:
                cannot_run.append(f"C3: {where3} 是 {claimed3}（範本預設值）—— 沒填過，"
                                  f"等於沒有驗收紀錄。")
                say("  ✗ 宣告的驗收行數是 0 —— 這一項無法進行")
            else:
                counted("C3", 1)
                if cur > claimed3 * tol:
                    problems.append(f"C3: 文件已成長到 {cur} 行，驗收只涵蓋 {claimed3} 行版本 —— "
                                    f"約 {cur - claimed3} 行未經第三方驗收。"
                                    f"不可對外宣稱『已完成數字驗收』。")
                    say(f"  ✗ 現行 {cur} 行 vs 驗收 {claimed3} 行")
                elif cur * tol < claimed3:
                    problems.append(f"C3: {where3} 宣告驗過 {claimed3} 行，但被驗文件現在只有 "
                                    f"{cur} 行（差 {claimed3 - cur} 行，超過 "
                                    f"{(tol - 1) * 100:.0f}% 容忍）—— 宣告的行數對不上這份文件："
                                    f"要嘛驗的是另一份、要嘛數字是填的。不算驗過。")
                    say(f"  ✗ 宣告 {claimed3} 行 vs 現行只有 {cur} 行")
                else:
                    say(f"  ✓ 現行 {cur} 行，驗收涵蓋 {claimed3} 行（來源：{where3}）")

    # ─────────────────────────────────────── C4 unresolved verification findings
    c = enabled("C4_open_findings")
    if c is not None:
        head("C4  驗收發現是否還有未結案的阻擋項")
        reg = p(c.get("register"))
        blocking = c.get("block_on") or ["嚴重"]
        if isinstance(blocking, str):
            blocking = [blocking]
        # 丙-3：嚴重度比對一律先正規化（去空白、小寫），"Severe " 不再靠尾隨空白逃出 block_on。
        blocking_n = {sev(b) for b in blocking}
        if not reg or not reg.exists():
            # 2026-09-03：以前這裡只 append 一句 note 就 say "(skip)"，不進 problems，
            # 於是「從來沒做過驗收」的專案照樣 exit 0。從未驗收 ≠ 通過——這是
            # 「無法進行檢查」，退出碼 2。
            cannot_run.append(
                f"C4: 找不到驗收發現登記簿（{c.get('register') or '設定裡沒寫 register'}）"
                f" —— 沒有登記簿就無法判斷有沒有未結案的阻擋項。從未做過驗收不等於通過。"
                f"骨架：{Path(__file__).parent / 'templates' / 'verification_findings.json'}")
            say("  ✗ 找不到 findings register —— 這一項無法進行")
        else:
            raw4 = jload(reg, "C4")
            findings = raw4 if isinstance(raw4, list) else raw4.get("findings", [])
            declare("C4", len(findings))
            # 只有「判得出擋不擋」的列才算有效項：五個 `{}` 以前算五個對象。
            # 缺 id 或 severity 的列連該不該擋都判不了，記進 invalid，不進計數。
            valid4 = []
            for i, f in enumerate(findings):
                if (not isinstance(f, dict) or not str(f.get("id") or "").strip()
                        or not str(f.get("severity") or "").strip()):
                    invalid_item("C4", f"{reg.name} 第 {i + 1} 列", "不是物件、或缺 id / severity")
                else:
                    valid4.append(f)
            findings = valid4
            counted("C4", len(findings))
            strict = strict_flag(c, "C4", cannot_run)

            # 丙-3：嚴重度白名單。讀不懂的嚴重度不能被當成「不嚴重」——它既不在 block_on
            # 也不在詞彙表，代表登記簿寫壞了（打錯、或用了本專案沒宣告的詞）。
            vocab4 = {sev(x) for x in (c.get("severity_vocab") or DEFAULT_SEVERITY_VOCAB)} | blocking_n
            bad_sev4 = sorted({repr(f.get("severity")) for f in findings
                               if sev(f.get("severity")) not in vocab4})
            if bad_sev4:
                problems.append(
                    f"C4: {len(bad_sev4)} 種嚴重度不在詞彙表也不在 block_on：{'、'.join(bad_sev4[:8])}"
                    f" —— 看門狗讀不懂的嚴重度不能被當成不嚴重。改回詞彙表內的值，或在 C4 用 "
                    f"`severity_vocab:` 宣告本專案的詞彙。")
                say(f"  ✗ 讀不懂的嚴重度：{'、'.join(bad_sev4[:8])}")

            # 丙-2：superseded 必須指名登記簿裡存在的繼任者（superseded_by，或 fixed_note /
            # note 裡提到的 id）。沒說被誰取代的 superseded 是無聲關案。
            ids4 = [str(f.get("id")).strip() for f in findings]
            all_ids4 = set(ids4)
            dup4 = sorted({i for i in ids4 if ids4.count(i) > 1})
            if dup4:
                problems.append(f"C4: 登記簿有重複的 id（{'、'.join(dup4[:8])}）—— id 永不重用，"
                                f"重複代表兩筆發現互相冒充。")
            for f in findings:
                if str(f.get("status") or "").strip().lower() != "superseded":
                    continue
                pool = " ".join(str(f.get(k) or "") for k in ("superseded_by", "fixed_note", "note"))
                refs = [r for r in re.findall(r"[A-Za-z][\w-]*\d+", pool) if r != str(f.get("id"))]
                if not any(r in all_ids4 for r in refs):
                    problems.append(
                        f"C4: {f.get('id')} 標了 superseded 卻沒指名登記簿裡存在的繼任者 —— "
                        f"在 superseded_by 寫繼任者的 id（fixed_note 提到也可）。沒說被誰取代的"
                        f" superseded 等於無聲關案。")
                    say(f"  ✗ {f.get('id')} superseded 但沒指名繼任者")

            # 丙-1：登記簿高水位檔（自 0813 AF 分支版回流；同一個檔名與欄位，兩支腳本可共用）。
            # 放在登記簿旁邊、登記簿之外：每個 id 前綴的最大號只能長不能縮，被記成阻擋級的
            # id 只能增不能減。刪掉前綴末尾的紀錄、或把嚴重度往下改，都會在這裡被抓到。
            # 刻意不對稱——成長不需要許可，縮水一律報問題；真要降級就在同一個 commit 裡
            # 明說並手改這個檔。
            hwm_p = p(c.get("highwater")) or reg.parent / "findings_id_highwater.json"
            by_pre: dict[str, list[int]] = {}
            unparsed4 = []
            for f in findings:
                m = re.match(r"^(.*?)(\d+)$", str(f.get("id")).strip())
                if m:
                    by_pre.setdefault(m.group(1).rstrip("-_") or "(無前綴)", []).append(int(m.group(2)))
                else:
                    unparsed4.append(str(f.get("id")))
            if unparsed4:
                notes.append(f"C4: {len(unparsed4)} 個 id 沒有結尾流水號（{'、'.join(unparsed4[:5])}），"
                             f"高水位檔追蹤不到它們")
            cur_max = {k: max(v) for k, v in by_pre.items()}
            cur_sev = sorted(str(f.get("id")) for f in findings if sev(f.get("severity")) in blocking_n)
            hwm = jload(hwm_p, "C4") if hwm_p.exists() else {}
            hwm = hwm if isinstance(hwm, dict) else {}
            prev_max = hwm.get("max_id_per_prefix") or {}
            prev_sev = set(hwm.get("severe_ids") or [])
            shrunk = [f"{k}: 曾到 {v}，現在 {cur_max.get(k, 0)}"
                      for k, v in prev_max.items() if cur_max.get(k, 0) < v]
            lost_sev = sorted(prev_sev - set(cur_sev))
            if shrunk:
                problems.append(f"C4: 登記簿縮水了 —— {'；'.join(shrunk)}。id 永不重用、紀錄永不刪除；"
                                f"把紀錄還原（高水位檔：{hwm_p}）。")
                say(f"  ✗ 登記簿縮水：{'；'.join(shrunk)}")
            if lost_sev:
                problems.append(f"C4: {len(lost_sev)} 筆曾記為阻擋級的發現現在不是阻擋級、或已不在登記簿"
                                f"（{'、'.join(lost_sev[:12])}{' …' if len(lost_sev) > 12 else ''}）"
                                f"—— 嚴重度不能被這道閘自己的紀錄默默往下改；真要降級就在發現裡說明，"
                                f"並在同一個 commit 裡手改 {hwm_p.name}。")
                say(f"  ✗ {len(lost_sev)} 筆阻擋級發現被降級或消失")
            if not shrunk and not lost_sev and findings:
                new_hwm = {"max_id_per_prefix": {**{k: v for k, v in prev_max.items()},
                                                 **{k: max(v, prev_max.get(k, 0))
                                                    for k, v in cur_max.items()}},
                           "severe_ids": sorted(prev_sev | set(cur_sev))}
                if {k: hwm.get(k) for k in new_hwm} != new_hwm:
                    try:
                        hwm_p.write_text(json.dumps(
                            {"_what": hwm.get("_what") or (
                                "High-water mark kept OUTSIDE verification_findings.json so that "
                                "deleting a record from the END of a prefix, or downgrading a "
                                "blocking-severity finding, cannot pass unnoticed. Written by "
                                "check_freshness.py (C4) whenever the register grows; never "
                                "written when it shrinks."), **new_hwm},
                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        notes.append(f"C4: 高水位檔已更新（{hwm_p}）")
                    except OSError as e:
                        notes.append(f"C4: 高水位檔寫不進去（{hwm_p}：{e}）")

            # 乙：unknown 依本項 block_on 分流——嚴重度在 block_on 內才可能擋，
            # 不在的只警告。以前不分，一筆輕微的 partially_fixed 就能擋交付。
            in_block = [f for f in findings if sev(f.get("severity")) in blocking_n]
            out_block = [f for f in findings if sev(f.get("severity")) not in blocking_n]
            report_unknown("C4", unknown_statuses(in_block), strict,
                           problems if strict else notes)
            report_unknown("C4", unknown_statuses(out_block), strict, notes,
                           outside_block_on=True)
            tally: dict[str, int] = {}
            for f in findings:
                if is_open(f.get("status"), strict):
                    tally[f.get("severity", "?")] = tally.get(f.get("severity", "?"), 0) + 1
            n_block = sum(v for k, v in tally.items() if sev(k) in blocking_n)
            if not tally:
                say(f"  ✓ {len(findings)} 項發現全部結案" if findings else
                    "  ✗ 登記簿裡一筆發現都沒有 —— 沒有東西可判斷（見收尾）")
            else:
                brk = "、".join(f"{k} {v} 項" for k, v in tally.items())
                if n_block:
                    problems.append(f"C4: 尚有 {n_block} 項阻擋級發現未結案（未結案總計：{brk}）"
                                    f" —— 清單見 {c.get('register')}。"
                                    f"不可對外宣稱數字已通過驗收。")
                    say(f"  ✗ 未結案：{brk}")
                else:
                    say(f"  ✓ 無未結案阻擋項（尚有 {brk}，不擋交付）")

    # ────────────────────────────────────────── C5 document vs stats freshness
    c = enabled("C5_document_vs_stats")
    if c is not None:
        head("C5  文件是否比它引用的 stats 檔新")
        # `document` 接受三種寫法，三者可混用：
        #   1. 單一路徑字串（最早的格式）
        #   2. 路徑字串清單（2026-08-10 新增）
        #   3. 清單元素寫成 {path: <文件>, sources: [<stats 檔名>, ...]}（2026-09-03 新增）
        # 前兩種維持原行為：拿該文件比對 stats_index 裡**全部**的 stats 檔。
        # 第三種只比對該文件自己宣告的來源檔——因為「每份文件比對每一個 stats 檔」會讓
        # 新增任何一個與該文件無關的 stats 檔，就把所有較舊的文件一起判成過期。
        # 未宣告 sources 的文件行為完全不變，既有專案不受影響。
        raw = c.get("document")
        doc_specs = raw if isinstance(raw, list) else [raw]
        docs, declared = [], {}
        bad_spec = []
        builders5: dict[str, list[str]] = {}
        for d in doc_specs:
            if not d:
                continue
            if isinstance(d, dict):
                path_val = d.get("path")
                if not path_val:
                    bad_spec.append(repr(d))
                    continue
                docs.append((str(path_val), p(path_val)))
                b = d.get("builder")
                if b:
                    builders5[str(path_val)] = [str(x) for x in (b if isinstance(b, list) else [b])]
                src = d.get("sources")
                if src is not None:
                    # 2026-09-03：`sources: []` 會讓比對池變成空集合，於是這份文件
                    # 必然通過——宣告空來源等於自我豁免。**完全沒有 sources 鍵**
                    # 的舊寫法不受影響（那是刻意保留的向後相容：比對所有 stats 檔）。
                    if not src:
                        cannot_run.append(
                            f"C5: {path_val} 宣告了 sources 但清單是空的 —— 比對 0 個 "
                            f"stats 檔必然通過，等於把這份文件排除在檢查之外。"
                            f"要嘛列出它真正引用的 stats 檔，要嘛整個拿掉 sources 鍵"
                            f"（拿掉＝回到比對所有 stats 檔）。")
                    declared[str(path_val)] = [str(s) for s in src]
            else:
                docs.append((str(d), p(d)))
        idx_p = p(c.get("stats_index") or (checks.get("C1_stats_freshness") or {}).get("stats_index"))
        data_dir = p(c.get("data_dir") or (checks.get("C1_stats_freshness") or {}).get("data_dir")) or root
        missing = [name for name, path in docs if not path or not path.exists()]
        declare("C5", len(docs))
        for m in missing:
            invalid_item("C5", str(root / m), "宣告的文件不存在")
        if bad_spec:
            problems.append(f"C5: document 的對照式寫法缺少 path：{'、'.join(bad_spec)}")
        # 丙-4（C5b，自 0813 AF 分支版 C2b 回流）：產物必須比產生它的 builder 腳本新。
        # C5 只比「文件 vs stats 檔」，看不到 builder 本身被改了但沒重跑——分支版第 6 輪
        # 發現的洞正是這個：改了 19/24/31/40 的 builder，每一道閘都還是綠的。
        # 在 document 條目加 `builder: 24_build_advisor_interim.py`（可給清單）即啟用；
        # 相對 C5 的 scripts_dir（省略時沿用 C1 的）。沒宣告的文件不受此保護。
        if docs and not missing and builders5:
            scripts5 = p(c.get("scripts_dir") or (checks.get("C1_stats_freshness") or {}).get("scripts_dir")) or root
            for name, path in docs:
                for b in builders5.get(name) or []:
                    bp = scripts5 / b
                    if not bp.exists():
                        invalid_item("C5", f"{name} 的 builder {bp}", "builder 腳本不存在")
                        continue
                    counted("C5", 1)
                    if path.stat().st_mtime < bp.stat().st_mtime:
                        problems.append(
                            f"C5b: {name} 比產生它的 {b} 舊 "
                            f"{(bp.stat().st_mtime - path.stat().st_mtime) / 60:.0f} 分鐘 —— "
                            f"builder 改了但沒重跑，產物裡的是上一版邏輯的輸出。重跑 {b}。")
                        say(f"  ✗ {name} 比 builder {b} 舊")
        if not docs:
            problems.append("C5: 設定裡沒有 document")
        elif missing:
            problems.append(f"C5: 找不到文件：{'、'.join(missing)}")
        elif not idx_p or not idx_p.exists():
            notes.append("C5: 沒有 stats_index，跳過")
        else:
            stats_mt = []
            for name, meta in sorted((jload(idx_p, "C5").get("files", {})).items()):
                f, gen = data_dir / name, str(meta.get("產生者") or meta.get("generated_by") or "")
                if not f.exists() or not gen.endswith(".py"):
                    continue
                # 稽核檔記錄的是「某份交付物做了什麼」，不是文件引用的估計來源。
                # 它必然在該交付物之後寫出，拿它比對任何文件都只會製造假警報。
                # 在 stats_index.json 該檔的條目加 "稽核檔": true（或 audit_only）即跳過。
                if meta.get("稽核檔") or meta.get("audit_only"):
                    continue
                stats_mt.append((name, f.stat().st_mtime))
            # 宣告的來源檔必須真的在 stats_index 裡，否則是設定寫錯而不是通過。
            known = {sname for sname, _ in stats_mt}
            for dname, srcs in declared.items():
                unknown = [s for s in srcs if s not in known]
                if unknown:
                    invalid_item("C5", f"{dname} 宣告的來源 {'、'.join(unknown)}",
                                 "不在 stats_index、沒有 .py 產生者、或檔案不存在")
                    problems.append(
                        f"C5: {dname} 宣告的來源檔不在 stats_index（或沒有 .py 產生者、或檔案不存在）："
                        f"{'、'.join(unknown)} —— 宣告錯的來源等於沒有守住這份文件")
            any_stale = False
            for name, path in docs:
                doc_mt = path.stat().st_mtime
                srcs = declared.get(name)
                pool = [(s, m) for s, m in stats_mt if s in set(srcs)] if srcs is not None else stats_mt
                counted("C5", len(pool))
                stale = [f"{sname}（新 {(smt - doc_mt) / 60:.0f} 分鐘）"
                         for sname, smt in pool if doc_mt < smt]
                if stale:
                    any_stale = True
                    problems.append(f"C5: {name} 比 {len(stale)} 個 stats 檔舊 —— "
                                    f"文字寫在最後一次重跑之前，數字可能沒對照現行檔案核過："
                                    f"{'、'.join(stale)}")
                    say(f"  ✗ {name} 比 {len(stale)} 個 stats 檔舊")
            if not any_stale:
                label = "文件" if len(docs) == 1 else f"{len(docs)} 份文件"
                n_dec = sum(1 for n, _ in docs if n in declared)
                scope = ("所有 stats 檔" if not n_dec
                         else f"各自宣告的來源檔（{n_dec}/{len(docs)} 份有宣告，其餘比對所有 stats 檔）")
                say(f"  ✓ {label}都比{scope}新")

    # ───────────────────────────────── C6 stats gate: were the numbers verified?
    c = enabled("C6_stats_gate")
    if c is not None:
        head("C6  統計輸出是否已經被獨立驗收過（且驗收發生在最後一次重跑之後）")
        rec_p = p(c.get("record"))
        reg_p = p(c.get("register") or (checks.get("C4_open_findings") or {}).get("register"))
        idx_p = p(c.get("stats_index") or (checks.get("C1_stats_freshness") or {}).get("stats_index"))
        data_dir = p(c.get("data_dir") or (checks.get("C1_stats_freshness") or {}).get("data_dir")) or root
        block_on = c.get("block_on") or ["嚴重"]
        if not rec_p or not rec_p.exists():
            problems.append(f"C6: 找不到統計驗收紀錄（{c.get('record')}）—— "
                            "統計輸出還沒被獨立驗收過，不可以在上面寫任何文字。")
            say("  ✗ 沒有統計驗收紀錄")
        else:
            # 2026-09-03：沒有 stats_index 以前只留一句 note，然後**整段跳過**——
            # verdict、hash 比對、未結案發現三項全都不執行，於是一份寫著 "block"
            # 的驗收紀錄配一筆未結案的「嚴重」發現照樣 exit 0。缺索引只讓「這次要
            # 驗的是哪幾個 stats 檔」做不到，擋不住其餘三項，所以現在只把新鮮度與
            # hash 那一段收起來並報 cannot_run，其餘照跑。
            rec_mt, stale, stats_seen = rec_p.stat().st_mtime, [], []
            if not idx_p or not idx_p.exists():
                cannot_run.append(
                    f"C6: 沒有 stats_index（{c.get('stats_index') or '本項沒寫，也沒從 C1 繼承到'}）"
                    f" —— 列不出這次要驗的是哪些 stats 檔，新鮮度與內容 hash 兩項比對都做不了。"
                    f"以下 verdict 與未結案檢查仍照跑，但比對 0 個檔不是通過。")
                say("  ✗ 沒有 stats_index —— 新鮮度與 hash 比對無法進行")
            else:
                for name, meta in sorted((jload(idx_p, "C6").get("files", {})).items()):
                    f, gen = data_dir / name, str(meta.get("產生者") or meta.get("generated_by") or "")
                    if not f.exists() or not gen.endswith(".py"):
                        continue
                    # 稽核檔記錄的是交付物本身，不是被驗收的統計輸出。
                    if meta.get("稽核檔") or meta.get("audit_only"):
                        continue
                    stats_seen.append((name, f))
                    if rec_mt < f.stat().st_mtime:
                        stale.append(f"{name}（新 {(f.stat().st_mtime - rec_mt) / 60:.0f} 分鐘）")
                if stale:
                    problems.append(f"C6: 統計驗收紀錄比 {len(stale)} 個 stats 檔舊 —— "
                                    f"這些數字在最後一次驗收之後又變過，等於沒驗："
                                    f"{'、'.join(stale)}")
                    say(f"  ✗ 驗收紀錄比 {len(stale)} 個 stats 檔舊")
                else:
                    say("  ✓ 統計驗收紀錄比所有 stats 檔新")
            counted("C6", len(stats_seen))

            # mtime 只證明「有個比較新的檔案說沒問題」。要證明驗的是「這一批數字」，
            # 驗收紀錄必須帶下每個被驗檔案的 SHA-256，由這裡逐一比對。
            # 沒帶 hash 的紀錄一律視為未通過 —— 否則 C6 只是在信任一張簽名紙。
            rec = jload(rec_p, "C6")
            rec = rec if isinstance(rec, dict) else {}
            # 紀錄自己說了不通過就是不通過。少了這一條，一份寫著 "block" 的紀錄
            # 只要夠新、hash 對得上就會被放行 —— 那是最荒謬的一種通過。
            v = str(rec.get("verdict", "")).lower()
            if v and v not in ("pass", "通過"):
                problems.append(f"C6: 統計驗收紀錄的判定是「{rec.get('verdict')}」，不是通過。")
                say(f"  ✗ 驗收判定為 {rec.get('verdict')}")
            elif not v:
                problems.append("C6: 統計驗收紀錄沒有 verdict 欄位，無法判斷驗收結論。")
                say("  ✗ 驗收紀錄沒有 verdict")
            claimed = rec.get("verified_artifacts") or rec.get("已驗檔案") or {}
            if not isinstance(claimed, dict) or not claimed:
                problems.append("C6: 統計驗收紀錄沒有 verified_artifacts（檔名 → SHA-256）"
                                " —— 無法證明驗的是現在這批數字，不予採信。")
                say("  ✗ 驗收紀錄沒有帶 hash")
            else:
                checked = {n for n, _ in stats_seen}
                missing = sorted(checked - set(claimed))
                changed = [n for n, f in stats_seen
                           if n in claimed and claimed[n] != sha256(f)]
                if missing:
                    problems.append(f"C6: 驗收紀錄沒有涵蓋 {len(missing)} 個 stats 檔"
                                    f"（{'、'.join(missing)}）—— 這些數字沒有被驗過。")
                    say(f"  ✗ 未涵蓋 {len(missing)} 個 stats 檔")
                if changed:
                    problems.append(f"C6: {len(changed)} 個 stats 檔的內容與驗收當時不同"
                                    f"（{'、'.join(changed)}）—— 驗收已失效，要重驗。")
                    say(f"  ✗ {len(changed)} 個 stats 檔內容已改變")
                if not missing and not changed:
                    # 講「實際比對了幾個」，不是「紀錄裡宣稱有幾個」：沒有 stats_index 時
                    # stats_seen 是空的，舊寫法會印「N 個 hash 相符」，其實一個都沒比。
                    n_cmp = len({n for n, _ in stats_seen} & set(claimed))
                    say(f"  ✓ 實際比對了 {n_cmp} 個 stats 檔的內容 hash，與驗收紀錄相符"
                        + ("" if n_cmp else "（沒有可比對的 stats 檔 —— 見上方 C6 無法進行）"))

            # 只擋 stats 階段的未結案發現；文件階段的發現由 C4 管。
            if reg_p and reg_p.exists():
                reg = jload(reg_p, "C6")
                rows = reg if isinstance(reg, list) else reg.get("findings", [])
                rows = [x for x in rows if isinstance(x, dict)]
                strict6 = strict_flag(c, "C6", cannot_run)
                # 丙-3：嚴重度正規化後再比 block_on（與 C4 同）。
                block6 = {sev(b) for b in (block_on if isinstance(block_on, list) else [block_on])}
                stats_rows = [x for x in rows
                              if str(x.get("stage", "stats")).lower() == "stats"]
                # 乙：與 C4 同一個分流——unknown 只有嚴重度在 block_on 內才可能擋。
                report_unknown("C6", unknown_statuses(
                    [x for x in stats_rows if sev(x.get("severity")) in block6]),
                    strict6, problems if strict6 else notes)
                report_unknown("C6", unknown_statuses(
                    [x for x in stats_rows if sev(x.get("severity")) not in block6]),
                    strict6, notes, outside_block_on=True)
                open_stats = [x for x in stats_rows
                              if is_open(x.get("status"), strict6)
                              and sev(x.get("severity")) in block6]
                if open_stats:
                    ids = "、".join(str(x.get("id", "?")) for x in open_stats)
                    problems.append(f"C6: 尚有 {len(open_stats)} 項統計階段的阻擋級發現未結案（{ids}）"
                                    "—— 先修統計，不要組報告。")
                    say(f"  ✗ 統計階段未結案：{ids}")
                else:
                    say("  ✓ 統計階段無未結案阻擋項")

    # ────────────── C7 estimates that were run but never reported ────────────
    # C1–C6 all ask whether what IS written down is current and verified. None of
    # them asks what was left out — and selective presentation is this domain's
    # actual failure mode: of 543 numbers checked, 9 were wrong, but three of the
    # nine severe findings were "ran six, reported two"
    # (references/delivery_discipline.md). estimate_inventory.py computes that set
    # difference; this turns it into a gate.
    #
    # An omission is not a defect — plenty of estimates are run and rightly not
    # reported. An *unexplained* omission is, because it cannot be told apart from
    # one dropped for being inconvenient.
    c = enabled("C7_coverage")
    # 2026-09-03：`C7_coverage: {}` 之前是「啟用但什麼都沒設」——report 落回根目錄的
    # coverage_diff.json、沒有 reasons 檔、strict 預設關，於是未說明的遺漏只會變成
    # 一句 note，整支照樣 exit 0。空設定不是設定。
    if c is not None and not c:
        head("C7  跑過但沒進交付物的估計，有沒有寫下不列的理由")
        cannot_run.append(
            "C7: 設定是空的（`C7_coverage: {}`）—— 沒有 report、沒有 reasons、沒有 strict，"
            "這一項等於掛著名字但不檢查任何東西。補上 report / reasons / strict 三個欄位"
            f"（範本：{Path(__file__).parent / 'templates' / CONFIG_NAME}），"
            "或整項設成 false 明確關掉。")
        say("  ✗ C7 設定是空的 —— 這一項無法進行")
        c = None
    if c is not None:
        head("C7  跑過但沒進交付物的估計，有沒有寫下不列的理由")
        rep_p = p(c.get("report") or "coverage_diff.json")
        reasons_rel = c.get("reasons")
        reasons_p = p(reasons_rel)
        strict7 = bool(c.get("strict", False))
        # A check that names a file without saying what goes in it is a check
        # people turn off. Every C7 failure carries the path to the skeleton.
        tmpl = Path(__file__).parent / "templates" / "omission_reasons.json"
        if not rep_p or not rep_p.exists():
            problems.append(
                f"C7: 找不到 {c.get('report') or 'coverage_diff.json'} —— 沒有人比對過"
                f"「跑了幾個」與「報了幾個」。先跑 "
                f"`python3 <RESEARCH_PLAN_DIR>/scripts/estimate_inventory.py <OUTPUT_DIR>` 產生"
                f"涵蓋差集，再把 omitted 清單逐筆寫進 "
                f"{reasons_rel or 'omission_reasons.json'}（骨架：{tmpl}）。")
            say("  ✗ 沒有 coverage_diff.json")
        else:
            cov = jload(rep_p, "C7")
            cov = cov if isinstance(cov, dict) else {}
            omitted = cov.get("omitted") or []
            executed7 = cov.get("executed") or []
            declare("C7", len(executed7))
            # Is this coverage audit about the CURRENT outputs, or left over from a
            # previous run? A stale coverage_diff.json reporting "0 omitted" passes
            # C7 while describing workbooks that have since been rebuilt: the audit
            # never ran for these numbers and nothing said so. Same failure shape
            # C1/C5/C6 exist to catch, one file further along the chain.
            #
            # Content beats mtime wherever the audit records hashes. mtime only
            # says "touched later", which a restore, a copy or a clock skew all
            # defeat — an output can be rewritten with different numbers and an
            # OLDER timestamp, and mtime calls that fresh.
            prov = cov.get("provenance") or {}
            source_hashes = prov.get("source_hashes") or {}
            search_root = Path(cov.get("output_dir") or root)
            if not search_root.exists():
                search_root = root
            scanned = {str(r.get("source")) for r in executed7
                       if isinstance(r, dict) and r.get("source")}
            # 以前 counted 的是 executed 的長度：三筆 source 指向不存在 xlsx 的項、五個
            # 空物件，都能印「比對 N 個對象」然後綠燈。一筆 executed 要算有效，必須
            # 有 estimate_id、有 source、而且 source 在 output_dir 底下真的找得到。
            src_hits = {name: bool(next(search_root.rglob(name), None)) for name in scanned}
            n_valid7 = 0
            for i, r in enumerate(executed7):
                if not isinstance(r, dict) or not str(r.get("estimate_id") or "").strip():
                    invalid_item("C7", f"executed 第 {i + 1} 筆", "不是物件、或缺 estimate_id")
                elif not r.get("source"):
                    invalid_item("C7", str(r.get("estimate_id"))[:60], "沒有 source，對不到任何輸出檔")
                elif not src_hits.get(str(r.get("source"))):
                    invalid_item("C7", str(r.get("estimate_id"))[:60],
                                 f"來源檔 {search_root / str(r.get('source'))} 不存在")
                else:
                    n_valid7 += 1
            counted("C7", n_valid7)

            # 甲（第四輪）：三份清單要算得起來。以前 omitted 直接讀檔、從不與
            # executed − reported 對帳，於是「跑過 3 個、報了 0 個、未出現 0 個」這種算術上
            # 不可能的組合是綠燈——把 omitted 清空就能轉綠。現在：每一個跑過的估計
            # 要嘛在 reported、要嘛在 omitted；同時在兩邊、或兩邊都沒有的 id，一律報出來。
            status7 = str(cov.get("status") or "")
            if status7 and status7 != "compared":
                cannot_run.append(
                    f"C7: {rep_p.name} 的 status 是「{status7}」，不是 compared —— "
                    f"estimate_inventory 沒讀到任何交付物，omitted 為空只是因為沒有東西可以被"
                    f"遺漏（讀 status，不要讀清單長度）。這不是通過。")
                say(f"  ✗ 涵蓋率稽核的 status 是 {status7}，沒有比對過交付物")

            def ids7(rows) -> set[str]:
                out = set()
                for r in rows:
                    v = r.get("estimate_id") if isinstance(r, dict) else r
                    if str(v or "").strip():
                        out.add(str(v).strip())
                return out

            exec_ids = {str(r.get("estimate_id")).strip() for r in executed7
                        if isinstance(r, dict) and str(r.get("estimate_id") or "").strip()}
            rep_ids, om_ids = ids7(cov.get("reported") or []), ids7(omitted)
            unaccounted = sorted(exec_ids - rep_ids - om_ids)
            both7 = sorted(rep_ids & om_ids)
            ghosts7 = sorted((rep_ids | om_ids) - exec_ids)

            def show7(ids) -> str:
                return "、".join(i[:60] for i in ids[:5]) + (" …" if len(ids) > 5 else "")

            if unaccounted:
                problems.append(
                    f"C7: 算術對不上 —— 跑過 {len(exec_ids)} 個估計、reported {len(rep_ids)} 個、"
                    f"omitted {len(om_ids)} 個，有 {len(unaccounted)} 個既不在 reported 也不在 "
                    f"omitted（{show7(unaccounted)}）。清空 omitted 不等於沒有遺漏；"
                    f"重跑 estimate_inventory.py，不要手改清單。")
                say(f"  ✗ {len(unaccounted)} 個跑過的估計兩邊都不在（omitted 少算了）")
            if both7:
                problems.append(
                    f"C7: {len(both7)} 個估計同時列在 reported 與 omitted（{show7(both7)}）"
                    f"—— 同一個估計不可能既出現又未出現，清單被動過。")
            if ghosts7:
                problems.append(
                    f"C7: reported / omitted 裡有 {len(ghosts7)} 個 executed 沒有的 id"
                    f"（{show7(ghosts7)}）—— 沒跑過的估計不可能被報告或被省略。")
            counters7 = cov.get("counters") or {}
            actual7 = {"executed_estimates": len(executed7),
                       "reported_estimates": len(cov.get("reported") or []),
                       "omitted_estimates": len(omitted)}
            mism7 = [f"{k}: counters 寫 {counters7[k]}、清單實際 {v}"
                     for k, v in actual7.items() if k in counters7 and counters7[k] != v]
            if mism7:
                problems.append(
                    f"C7: {rep_p.name} 的 counters 與清單長度對不上（{'；'.join(mism7)}）—— "
                    f"清單被手改過，或檔案是拼出來的。重跑 estimate_inventory.py。")
                say("  ✗ counters 與清單長度不一致")
            changed, unverifiable, checked = [], [], 0
            if source_hashes:
                for name in sorted(set(source_hashes) | scanned):
                    hits = sorted(search_root.rglob(name))
                    recorded = source_hashes.get(name)
                    if not hits or not recorded:
                        unverifiable.append(name)
                        continue
                    checked += 1
                    if sha256(hits[0]) != recorded:
                        changed.append(name)
                if changed:
                    problems.append(
                        f"C7: {rep_p.name} 記錄的 {len(changed)} 個輸出檔內容已經變了"
                        f"（{'、'.join(changed[:5])}{' …' if len(changed) > 5 else ''}）"
                        f"—— 這份涵蓋率稽核描述的不是現在磁碟上的數字，等於這一輪沒稽核過。"
                        f"重跑 `python3 <RESEARCH_PLAN_DIR>/scripts/estimate_inventory.py "
                        f"<OUTPUT_DIR>`。")
                    say(f"  ✗ 涵蓋率稽核已失效（{len(changed)}/{checked + len(changed)} "
                        f"個輸出檔內容改變）")
                if unverifiable:
                    problems.append(
                        f"C7: 涵蓋率稽核提到的 {len(unverifiable)} 個檔案現在找不到、"
                        f"或沒有記錄雜湊（{'、'.join(unverifiable[:5])}）—— 無法確認"
                        f"它稽核的是哪一批數字。")
                    say(f"  ✗ {len(unverifiable)} 個來源檔無法比對")
                if not changed and not unverifiable:
                    say(f"  ✓ 涵蓋率稽核的 {checked} 個輸出檔內容 hash 相符")
            else:
                # No hashes recorded: fall back to mtime, and say that the weaker
                # check is the one that ran. An audit written before provenance
                # existed is still worth comparing — just not worth trusting as far.
                cov_mt = rep_p.stat().st_mtime
                newer = []
                for name in sorted(scanned):
                    hits = list(search_root.rglob(name))
                    if not hits:
                        continue
                    checked += 1
                    mt = max(h.stat().st_mtime for h in hits)
                    if cov_mt < mt:
                        newer.append(f"{name}（新 {(mt - cov_mt) / 60:.0f} 分鐘）")
                if newer:
                    problems.append(
                        f"C7: {rep_p.name} 比它掃描過的 {len(newer)} 個輸出檔舊"
                        f"（{'、'.join(newer[:5])}{' …' if len(newer) > 5 else ''}）—— "
                        f"這份涵蓋率稽核描述的是上一輪的產物。重跑 "
                        f"`python3 <RESEARCH_PLAN_DIR>/scripts/estimate_inventory.py "
                        f"<OUTPUT_DIR>`。")
                    say(f"  ✗ 涵蓋率稽核過期（比 {len(newer)}/{checked} 個輸出檔舊）")
                elif checked:
                    notes.append(
                        f"C7: {rep_p.name} 沒有 provenance.source_hashes，只能用 mtime "
                        f"比對；mtime 擋不掉「內容變了但時間戳更舊」（還原、複製、時鐘"
                        f"偏移都會這樣）。重跑 estimate_inventory.py 取得帶雜湊的版本。")
                    say(f"  · 涵蓋率稽核比 {checked} 個輸出檔新（僅 mtime，無雜湊）")

            # The audit records which plan it was computed for; if it says, check.
            if "plan_fingerprint" in prov and prov.get("plan_fingerprint") is None:
                problems.append(
                    f"C7: {rep_p.name} 的 plan_fingerprint 是 null"
                    f"（{prov.get('plan_fingerprint_error') or '未記錄原因'}）—— "
                    f"無法確認這份稽核屬於哪一版計畫。算不出來不等於通過。")
                say("  ✗ 涵蓋率稽核的 plan_fingerprint 為 null")
            reasons = {}
            # 2026-09-03：原封不動的範本不是理由。兩種「等於未填」：
            #   (a) 檔案與 templates/omission_reasons.json 逐位元組相同；
            #   (b) 理由的值還是 `<...>` 佔位字串——今天會通過，因為它只看非空字串。
            # 兩者都代表沒有人真的寫過理由，所以 strict 沒開也要擋。
            reasons_untouched = False
            if reasons_p and reasons_p.exists():
                raw = jload(reasons_p, "C7")
                reasons = raw.get("reasons", raw) if isinstance(raw, dict) else {}
                if tmpl.exists() and reasons_p.read_bytes() == tmpl.read_bytes():
                    reasons_untouched, reasons = True, {}
                else:
                    placeholder = [k for k, v in reasons.items()
                                   if str(v).strip().startswith("<")
                                   and str(v).strip().endswith(">")]
                    for k in placeholder:
                        reasons.pop(k, None)
                    if placeholder:
                        reasons_untouched = True
            unexplained = [o for o in omitted
                           if not str(reasons.get(o.get("estimate_id"), "")).strip()]
            say(f"  跑過 {len(cov.get('executed') or [])} 個估計，交付物涵蓋 "
                f"{len(cov.get('reported') or [])} 個，未出現 {len(omitted)} 個"
                f"（其中 {len(unexplained)} 個沒寫理由）")
            if unexplained:
                ids = "、".join(str(o.get("estimate_id"))[:60] for o in unexplained[:5])
                where = reasons_rel or "omission_reasons.json"
                msg = (f"C7: {len(unexplained)} 個跑過的估計沒有出現在交付物裡，也沒有在 "
                       f"{where} 說明為什麼（{ids}"
                       f"{' …' if len(unexplained) > 5 else ''}）。"
                       f"逐一寫下不列的理由，或把它們列進去。"
                       + ("" if reasons_p and reasons_p.exists()
                          else f" 還沒有這個檔的話，從骨架複製：cp {tmpl} <專案>/{where}"))
                if reasons_untouched:
                    problems.append(
                        msg + f" ⚠ {where} 目前還是未填的範本（內容與骨架相同，或理由"
                              f"仍是 `<...>` 佔位字串）—— 有這個檔不等於寫過理由，"
                              f"因此 strict 沒開也擋。")
                    say(f"  ✗ {len(unexplained)} 個未說明的遺漏，且 {where} 是未填的範本")
                elif strict7:
                    problems.append(msg)
                    say(f"  ✗ {len(unexplained)} 個未說明的遺漏")
                else:
                    notes.append(msg + "（strict 未開，本次不擋）")
                    say(f"  · {len(unexplained)} 個未說明的遺漏（strict 未開，不擋）")
            elif reasons_untouched:
                notes.append(f"C7: {reasons_rel or 'omission_reasons.json'} 還是未填的範本，"
                             f"但這一輪沒有需要說明的遺漏，因此不擋。")
                say("  ✓ 沒有未說明的遺漏（reasons 檔仍是未填範本，但本輪無遺漏）")
            else:
                say("  ✓ 沒有未說明的遺漏")

    # ────────── C8 交付物裡的數字，在宣告的來源裡找不找得到 ──────────────────
    # C1–C7 比的都是檔案與檔案（誰比誰新、誰有沒有被涵蓋），沒有一項真的去讀文件
    # 裡的那個數字。規則 1「數字單一來源」因此一直沒有閘：0813 AF 交出去的 docx 裡
    # 「313 筆」是手打的錯值（登記簿當時是 315），七項檢查全部亮綠。
    # 判斷邏輯在 lint_bare_numbers.py，它自己讀同一份 research-checks.yaml。
    c = enabled("C8_bare_numbers")
    # 空設定不是設定 —— 與 C7 同一個道理（2026-09-03 稽核）。`C8_bare_numbers: {}`
    # 會讓 lint 沿用 C5 的 document，看起來有在守，實際上沒有人宣告過要守什麼；
    # C5 一關就整項靜默失效。要沿用 C5 就明寫 report: 這一行，把它變成刻意的選擇。
    if c is not None and not c:
        head("C8  交付物裡的數字，在宣告的 stats 來源裡找不找得到")
        cannot_run.append(
            "C8: 設定是空的（`C8_bare_numbers: {}`）—— 空設定不是設定。至少寫一個 "
            "report:（document 省略時才會沿用 C5 的 document），欄位見範本 "
            f"{Path(__file__).parent / 'templates' / CONFIG_NAME}，"
            "或整項設成 false 明確關掉。")
        say("  ✗ C8 設定是空的 —— 這一項無法進行")
        c = None
    if c is not None:
        head("C8  交付物裡的數字，在宣告的 stats 來源裡找不找得到")
        argv8 = [str(root), "--config", str(cfg_path)]
        if quiet:
            argv8.append("--quiet")
        rc8, out8 = run_lint("lint_bare_numbers.py", argv8, root)
        counted("C8", 1)
        say(out8 or "(lint 無輸出)")
        if rc8 == 2:
            cannot_run.append(
                "C8: lint_bare_numbers.py 回 exit 2 —— 這一項無法進行（設定缺 document、"
                "要掃的文件不存在，或宣告的來源檔不存在）。"
                f"訊息：{tail(out8)}")
        elif rc8 == 1:
            problems.append(
                "C8: 交付物裡有數字在宣告的來源裡找不到 —— 每一個要嘛改成從 JSON 讀出來，"
                f"要嘛在該行標明來源，要嘛就是手打錯值。訊息：{tail(out8)}")
        else:
            say("  ✓ C8 通過（詳見上方 lint 輸出）")

    # ────────── C9 絕對句 / 新穎性宣稱有沒有帶檢索範圍限定 ────────────────────
    # 交付紀律規則 5 是唯一一條到 2026-09-03 為止零工具的規則，而它已經在 production
    # 失效過：`Project Lit Rev/PE EKG MLDL` 的 introduction 寫「至今沒有 narrative
    # synthesis 做過 X」，它自己的 Methods 卻只記了單一資料庫 85 筆、沒有檢索式也沒有
    # 檢索日期。沒有任何東西擋住。
    # lint_absolute_claims.py 吃路徑參數、不讀 yaml，所以設定在這裡翻成它的旗標。
    c = enabled("C9_absolute_claims")
    if c is not None and not c:
        head("C9  絕對句 / 新穎性宣稱有沒有帶檢索範圍限定")
        cannot_run.append(
            "C9: 設定是空的（`C9_absolute_claims: {}`）—— 沒有 paths 就沒有要掃的文件，"
            "這不是通過。補上 paths（相對專案根目錄的目錄或檔案清單），欄位見範本 "
            f"{Path(__file__).parent / 'templates' / CONFIG_NAME}，"
            "或整項設成 false 明確關掉。")
        say("  ✗ C9 設定是空的 —— 這一項無法進行")
        c = None
    if c is not None:
        head("C9  絕對句 / 新穎性宣稱有沒有帶檢索範圍限定")
        paths9 = c.get("paths") or c.get("path")
        if isinstance(paths9, str):
            paths9 = [paths9]
        if not paths9:
            cannot_run.append(
                "C9: 設定沒有 paths —— 沒有宣告要掃哪些文件，無法檢查。"
                "paths 寫成清單，例如 [analysis/report]。")
            say("  ✗ C9 沒有 paths —— 這一項無法進行")
        else:
            argv9 = [str(root / str(q)) for q in paths9]
            # 預設 file：dir 會讓同目錄任何一份檔案的檢索範圍區塊被整個目錄共用
            # （「借鄰居的證據」），0813 AF 的真陽性絕對句就是這樣被放過的。
            # 寬鬆的 dir 保留為明確 opt-in。（2026-09-04）
            argv9 += ["--scope", str(c.get("scope") or "file")]
            for ex in (c.get("exclude") or []):
                argv9 += ["--exclude", str(ex)]
            if c.get("strict"):
                argv9.append("--strict")
            if c.get("report"):
                argv9 += ["--json", str(root / str(c["report"]))]
            if quiet:
                argv9.append("--quiet")
            rc9, out9 = run_lint("lint_absolute_claims.py", argv9, root)
            counted("C9", 1)
            say(out9 or "(lint 無輸出)")
            if rc9 == 2:
                cannot_run.append(
                    "C9: lint_absolute_claims.py 回 exit 2 —— 這一項無法進行（設定的 paths "
                    "不存在、或該路徑底下沒有可掃的 md / qmd / docx）。"
                    f"訊息：{tail(out9)}")
            elif rc9 == 1:
                problems.append(
                    "C9: 有絕對句 / 新穎性宣稱沒帶完整檢索範圍（資料庫、檢索日期、命中筆數"
                    "三者缺一）—— 補上檢索範圍，或把絕對句改成有限定的說法。"
                    f"訊息：{tail(out9)}")
            else:
                say("  ✓ C9 通過（詳見上方 lint 輸出）")

    # ────────── C10 稿件宣稱的 PRISMA 數字 vs 磁碟上的實際筆數 ─────────────────
    # reconcile_prisma.py 2026-09-03 寫好後零引用——與稽核發現 4 抓的 prisma_flow.py
    # 「存在但沒人跑」處於同一狀態。它從 03_screening / 04_fulltext / 05_extraction 清點
    # 每一個 PRISMA 階段，再對 07_manuscript/*.qmd 與 09_qa/*.md 裡宣稱的整數逐一對帳
    # （某 MA 專案：宣稱 47 進全文、磁碟上 185）。判斷全在該腳本，這裡只翻旗標與退出碼。
    c = enabled("C10_prisma_reconcile")
    if c is not None and not c:
        head("C10  稿件宣稱的 PRISMA 數字，與磁碟上的篩選 / 全文 / 抽取檔對不對得起來")
        cannot_run.append(
            "C10: 設定是空的（`C10_prisma_reconcile: {}`）—— 沒有 root 就不知道要對帳哪個 "
            "MA 專案，這不是通過。補上 root:（MA 專案根，相對本 yaml 所在目錄；本專案"
            "自己就是 MA 時寫 `.`），欄位見範本 "
            f"{Path(__file__).parent / 'templates' / CONFIG_NAME}，"
            "或整項設成 false 明確關掉。")
        say("  ✗ C10 設定是空的 —— 這一項無法進行")
        c = None
    if c is not None:
        head("C10  稿件宣稱的 PRISMA 數字，與磁碟上的篩選 / 全文 / 抽取檔對不對得起來")
        root10 = c.get("root")
        if not root10:
            cannot_run.append(
                "C10: 設定沒有 root —— 沒有宣告要對帳哪個 MA 專案，無法檢查。"
                "root 寫成相對本 yaml 的目錄，本專案自己就是 MA 時寫 `.`。")
            say("  ✗ C10 沒有 root —— 這一項無法進行")
        else:
            argv10 = [str(root / str(root10))]
            if c.get("report"):
                argv10 += ["--json", str(root / str(c["report"]))]
            if quiet:
                argv10.append("--quiet")
            rc10, out10 = run_lint("reconcile_prisma.py", argv10, root)
            say(out10 or "(lint 無輸出)")
            if rc10 == 2:
                cannot_run.append(
                    "C10: reconcile_prisma.py 回 exit 2 —— 這一項無法進行（root 不是 MA 版面、"
                    "03_screening/ 沒有裁定過的決策檔、稿件裡沒有 PRISMA 數字、或某個環節"
                    f"解析不了）。訊息：{tail(out10)}")
            elif rc10 == 1:
                problems.append(
                    "C10: 稿件宣稱的 PRISMA 數字與磁碟上的檔案對不起來（或篩選版本混用、"
                    "有清點到卻從未報告的階段）—— 修稿件或重跑篩選，不要手改數字。"
                    f"訊息：{tail(out10)}")
            else:
                say("  ✓ C10 通過（詳見上方對帳表）")

    # ─────────────────────────────────────────────────────────────── verdict
    # 一項檢查「跑完了、沒抱怨」與「它根本沒有東西可比」在舊版的輸出上長得一樣，
    # 兩者都回 0。這是本檔全部假綠燈的共同根因（2026-09-03 第二輪稽核：六個入口、
    # 一個結構）。所以在這裡統一問每一項：你這次實際比對了幾個對象？答 0 就是
    # 無法進行（exit 2），不是通過。
    # 合法的 0 只有兩類，都在別處另有交代：C1b（stats 檔之間沒有相依是正常的，
    # 它併在 C1 底下不單獨計數）與 C8 / C9 / C10（判斷在獨立 lint，掃不到東西時由該
    # lint 自己回 exit 2）。其餘一律不放行。
    # 第三輪：compared 只算有效項。宣告 N 項、有效 0 項 → exit 2 並逐條列出無效項；
    # 有效 >0 但夾雜無效項 → exit 1（無效項是設定或資料的缺陷，也要逐條列出）。
    for short in check_roster()[0]:
        if short in DELEGATED:
            continue
        bad = invalid.get(short) or []
        n_ok = compared.get(short, 0)
        shown_bad = "；".join(bad[:8]) + (f" …（共 {len(bad)} 項）" if len(bad) > 8 else "")
        if n_ok > 0:
            if bad:
                problems.append(
                    f"{short}: 宣告了 {n_declared.get(short, n_ok + len(bad))} 項，其中 "
                    f"{len(bad)} 項無效（有效 {n_ok} 項已比對）：{shown_bad}")
            continue
        if bad:
            cannot_run.append(
                f"{short}: 宣告了 {n_declared.get(short, len(bad))} 項，其中 0 項有效 —— "
                f"每一項都指向讀不到的對象，等於比對 0 個對象，這不是通過。無效項：{shown_bad}")
            continue
        if any(x.startswith(short + ":") for x in cannot_run + problems):
            continue        # 這一項已經自己說明過跑不動 / 跑出了什麼，不重複報
        cannot_run.append(
            f"{short}: 這一項啟用了，但實際比對了 0 個對象 —— 比較池是空的，它不可能"
            f"發現任何問題，所以這不是通過"
            f"{ZERO_COMPARISON_HINT.get(short, '')}。")

    say("")
    say("=" * 78)
    # 三條退出路徑都先印同一份名冊，讓退出碼永遠對得上「到底跑了什麼」。
    print_roster()
    print("")
    if cannot_run:
        print(f"✗ {len(cannot_run)} 項檢查無法進行 —— 這些面向未受保護：\n")
        for x in cannot_run:
            print("  •", x)
        if problems:
            print(f"\n此外還有 {len(problems)} 項已經跑出來的問題：\n")
            for x in problems:
                print("  •", x)
        print_notes()
        print("\n未受保護不等於通過。補齊缺的檔案或設定，再跑一次。")
        return 2
    if problems:
        print(f"✗ 發現 {len(problems)} 項問題：\n")
        for x in problems:
            print("  •", x)
        print_notes()
        print("\n處理完之前，不要相信文件裡的數字，也不要對外宣稱結果。")
        return 1
    # 收尾訊息本身就是一種宣稱，它必須對得上實際做過的事：舊版那句「上列啟用項
    # 全部實際跑過並通過」在比對 0 個對象時是不實陳述。現在逐項附上比對數，讓這句
    # 話可以被讀者當場否證。
    print("✓ 全部通過（每一項啟用的檢查都實際比對過對象："
          + "、".join(f"{s} {compared_label(s)}" for s in check_roster()[0]) + "）")
    print_notes()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Absolute-claim linter — enforces delivery-discipline rule 5 across md / qmd / docx.

Why this exists
---------------
Rule 5 says: 絕對句一律帶檢索範圍限定 —— 查了哪些資料庫、有無年代限制、每條檢索式
命中幾筆、實際篩了幾筆。而且「零命中」與「篩選後零篇符合」不可混寫。

Until now rule 5 was the only delivery-discipline rule with zero tooling, and it has
already failed in production: `Project Lit Rev/PE EKG MLDL` writes "No comprehensive
narrative synthesis has yet mapped ..." in its introduction while its own Methods
section records a single-database PubMed search with 85 hits, no query string, and
no search date. Nothing caught it.

What it checks
--------------
  A1  absolute / novelty claims are located at all (中英文樣式)
  A2  every located claim is backed by a 檢索範圍區塊 carrying all three of
        - 資料庫名稱 (PubMed / Embase / Cochrane / ...)
        - 檢索日期   (a real date literal, in a sentence that is about searching)
        - 命中筆數   (how many records the search returned)
      預設（--scope file）證據必須在**宣稱所在的那份文件裡**，或在該文件用路徑
      明確指名的檢索紀錄檔裡。--scope dir / tree 是**寬鬆模式**，要明確 opt-in：
      dir 會把同目錄每一份檔案的證據併成同一個池（Quarto 稿件把 Introduction 與
      Methods 拆兩檔時才需要），代價是同目錄裡任何一份檔案提過資料庫 + 日期 + 筆數
      就會讓整個目錄的絕對句全部免罪。
      -> missing any of the three = violation
  B1  「零命中」and「零篇符合」stated in the same paragraph as if interchangeable
  B2  a zero-result claim phrased so ambiguously that neither reading is excluded,
      with no hit count and no screening count anywhere in the document
      -> B1/B2 are warnings; they only fail the run under --strict

Two modes (2026-09-03 第三輪；理由見 ABSOLUTE_PATTERNS 上方註解)
    --mode lenient（預設）  只抓 core 樣式（對文獻整體的新穎性／空白斷言，精確度高）；
                            預設排除驗收工作檔 / LLM 暫存 / 筆記 / 制度檔（DEFAULT_EXCLUDES，
                            會印出跳過幾檔）；不掃 .txt；同目錄借來的證據只記 evidence-borrowed 警告。
    --mode strict           core + extended 樣式（unprecedented、generic has yet to、從未…）；
                            不預設排除；--scope dir 下靠鄰居補齊的證據算違規。
    每一個被抑制的樣式命中（noqa / 豁免 / 引述 / ignore-pattern / extended）都計數並印出，
    不再靜默丟掉（前一輪 73% 的命中被靜默抑制，輸出只說「偵測到 59 句」）。
    證據端也修了：「877 筆命中」「回傳 0 筆」與表格「| 命中 |」欄現在都算命中筆數 ——
    前一輪把兩份自己帶完整檢索表的文件報成違規，是抽取器漏了表格。

Ground truth（改動後必須仍命中）
    Project Lit Rev/PE EKG MLDL/output/sections/01-introduction.qmd:11
    「No comprehensive narrative synthesis has yet mapped …」→ file 與 dir scope 都 exit 1。

Exit codes (shared convention across research-plan assets)
    2  check could not run — a path does not exist, or nothing scannable was found
    1  check ran and found violations (or, with --strict, warnings)
    0  check ran and everything passed; the summary names what ran and what was skipped

Usage
-----
    python3 lint_absolute_claims.py DIR_OR_FILE [DIR_OR_FILE ...]
    python3 lint_absolute_claims.py . --json findings.json
    python3 lint_absolute_claims.py . --scope dir        # 寬鬆：同目錄互相採認（opt-in）
    python3 lint_absolute_claims.py . --strict           # warnings fail the run
    python3 lint_absolute_claims.py . --mode strict      # core + extended 樣式、不預設排除
    python3 lint_absolute_claims.py . --ignore-pattern "regex"   # 句子符合就不算（抑制數會印）

逐條抑制：在該行寫 `lint-absolute-claims: ignore`（markdown 註解裡即可），整行不掃。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "absolute-claims-lint/1"

TEXT_SUFFIXES = {".md", ".qmd", ".markdown", ".txt", ".rmd"}
# lenient 模式不掃 .txt：本 domain 的 .txt 幾乎都是 LLM 暫存（judge_tasks/*.prompt.txt，內容是
# 別人論文的摘要）；檢索紀錄 .txt 仍會經由文件內的路徑指標被讀進來當證據。
LENIENT_SUFFIXES = {".md", ".qmd", ".markdown", ".rmd"}
# lenient 模式預設排除的路徑片段：驗收工作檔、LLM 暫存、備份、專案內部筆記、制度檔。
# 規則 5 守的是交付物；這些檔大量「引述」絕對句（驗收表、禁令、反例），不是主張。
# 排除幾檔會印出來，不是靜默丟掉。strict 模式不套用。
DEFAULT_EXCLUDES = ["_verify", "judge_tasks", "output_backup", "/notes/", "CLAUDE.md", "HANDOFF",
                    "decision_log", "VERIFICATION", "/.claude/", "/build/", "_merged"]
DOCX_SUFFIX = ".docx"
SCANNABLE = TEXT_SUFFIXES | {DOCX_SUFFIX}

# 掃描時直接跳過的目錄：版本控制、快取、套件樹。build 輸出（_output/ 之類）不跳過，
# 因為交付出去的正是那些檔案。
SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules",
    ".quarto", ".Rproj.user", ".ipynb_checkpoints", ".pytest_cache", ".mypy_cache",
}

# --------------------------------------------------------------------------------------
# 樣式：絕對句 / 新穎性宣稱
# --------------------------------------------------------------------------------------

# 每條樣式帶一個 tier：
#   core     = 對「文獻整體」的新穎性／空白斷言，精確度高，lenient 與 strict 都抓。
#   extended = 語意較寬（unprecedented 當形容詞、has yet to 當一般語氣、從未／填補空白），
#              只有 strict 才抓。2026-09-03 第三輪實測：前兩輪為了壓中文誤報把樣式縮到 12/12
#              專案恆綠，同時英文材料上的誤報主體正是這批 extended 樣式。寧可只抓得準的。
#
# 英文「has/have (not) yet」只有主語是文獻名詞（study / synthesis / review / evidence …）
# 才算 core：「No comprehensive narrative synthesis has yet mapped …」是；「patients who have
# not yet been diagnosed」「strategies have not yet been established」不是。
LIT_NOUN = r"(?:stud(?:y|ies)|trials?|reviews?|synthes[ie]s|meta-analys[ie]s|analys[ie]s|evidence|literature|research|data|tools?|models?|work|reports?|investigations?|comparisons?)"

ABSOLUTE_PATTERNS: list[tuple[str, str, str]] = [
    # --- 英文 core ---
    ("EN-first-to", "core", r"\b(?:the\s+)?first\s+(?:study|report|review|trial|analysis|work|paper|series|synthesis|meta-analysis)\b"),
    ("EN-first-to", "core", r"\bfirst\s+to\s+(?:report|describe|demonstrate|show|examine|map|characteri[sz]e|evaluate|assess|apply|quantify|address|investigate|synthesi[sz]e|test|compare)\b"),
    ("EN-first-to", "core", r"\b(?:we|this\s+(?:study|review|work|paper|analysis))\s+(?:are|is)\s+the\s+first\b"),
    ("EN-no-prior", "core", r"\bno\s+(?:prior|previous|earlier|published|existing|comprehensive|systematic)\s+\w*\s*(?:stud(?:y|ies)|trial|review|synthesis|analysis|report|work|tool|system|literature|investigation)\b"),
    ("EN-no-prior", "core", r"\bno\s+(?:stud(?:y|ies)|trial|review|analysis|report|work|tool|synthesis)\s+(?:has|have)\s+(?:yet\s+)?(?:been\s+)?\w*"),
    ("EN-no-prior", "core", r"\bthere\s+(?:is|are|has\s+been|have\s+been)\s+no\s+(?:prior|previous|published|existing|comprehensive|head-to-head|direct|randomi[sz]ed)?\s*\w*\s*(?:stud(?:y|ies)|trial|review|synthesis|analysis|report|comparison)\b"),
    ("EN-to-our-knowledge", "core", r"\bto\s+(?:our|the\s+authors'?)\s+knowledge\b"),
    ("EN-to-our-knowledge", "core", r"\bto\s+the\s+best\s+of\s+(?:our|the\s+authors'?)\s+knowledge\b"),
    ("EN-has-yet-to", "core", r"\b" + LIT_NOUN + r"\b[^.;:]{0,60}?\b(?:has|have)\s+(?:not\s+)?yet\s+(?:to\s+)?(?:be\s+|been\s+)?\w+"),
    ("EN-never", "core", r"\b(?:has|have|had)\s+never\s+been\s+(?:studied|reported|examined|described|evaluated|tested|assessed|investigated|quantified|compared|synthesi[sz]ed)\b"),
    ("EN-never", "core", r"\bnever\s+(?:been\s+)?(?:studied|reported|examined|described|evaluated|tested|assessed|investigated)\b"),
    ("EN-unexplored", "core", r"\bremains?\s+(?:largely\s+|entirely\s+|wholly\s+|completely\s+)?(?:unexplored|unexamined|uninvestigated|unaddressed|uncharacteri[sz]ed|unstudied|unreported|untested)\b"),
    ("EN-unexplored", "core", r"\b(?:entirely|wholly|completely|hitherto|previously)\s+(?:unexplored|unexamined|unaddressed|uncharacteri[sz]ed|unreported|unstudied)\b"),
    ("EN-gap", "core", r"\bno\s+(?:such\s+)?(?:comprehensive|systematic|narrative|pooled|quantitative)\s+(?:synthesis|review|meta-analysis|comparison|assessment)\s+(?:has|have|exists?)\b"),
    ("EN-only-none", "core", r"\b(?:only|sole)\s+(?:stud(?:y|ies)|trial|report|randomi[sz]ed\s+\w+\s+trial)\s+(?:to\s+date|published|available|that\s+has)\b"),
    ("EN-only-none", "core", r"\bthe\s+first\s+and,?\s+to\s+date,?\s+(?:the\s+)?only\b"),
    # --- 英文 extended（strict 才抓）---
    ("EN-no-prior", "extended", r"\bthere\s+(?:is|are)\s+no\s+(?:evidence|data)\b"),
    ("EN-no-prior", "extended", r"\bno\s+(?:evidence|data)\s+(?:has|have|exists?)\b"),
    ("EN-has-yet-to", "extended", r"\b(?:has|have)\s+yet\s+to\s+be\b"),
    ("EN-has-yet-to", "extended", r"\b(?:has|have)\s+not\s+yet\s+been\s+\w+"),
    ("EN-never", "extended", r"\b(?:has|have|had)\s+never\s+been\s+\w+"),
    ("EN-unexplored", "extended", r"\bremains?\s+(?:largely\s+|entirely\s+)?(?:unknown|undefined|unclear)\b"),
    ("EN-unprecedented", "extended", r"\bunprecedented\b"),
    # --- 中文 core ---
    # 「首次」「第一篇」在一般敘述裡太常見（首次住院、第一個主結果、第一篇的 433 人世代）。
    # core 只抓「自稱主語 / 文獻整體 + 首次／第一 + 研究動作」到齊的句式；不再要求系詞
    # （前一輪要求「是／為」，害「本研究首次將…」「這是文獻上第一次以…回答」全部漏掉）。
    ("ZH-first", "core",
     r"(?:本(?:研究|文|篇|分析|回顧|計畫)|我們|此(?:研究|文|分析)|這是|本篇(?:論文)?)[^。；，\n]{0,14}?"
     r"(?:\*\*|「|『|\s)*(?:第一(?:個|篇|次|份)|首(?:篇|次|度|例|創))(?:\*\*|」|』|\s)*"
     r"[^。；，\n]{0,8}?(?:研究|報告|檢定|檢驗|做|報導|提出|描述|證實|評估|分析|探討|使用|應用|納入|以|"
     r"回答|量化|比較|建立|檢視|驗證|揭示|把|將|對|把|在)"),
    ("ZH-first", "core", r"(?:文獻上|文獻中|國內外|國際|全球|世界|亞洲|台灣|國內)(?:上)?(?:第一(?:個|篇|次|份)|首(?:創|例|見|篇|次|度))"),
    ("ZH-first", "core", r"第一(?:篇|個|份)(?:探討|檢定|報告|量化|評估|研究|回答|把|將|對|以|做|在|同時|系統性)"),
    ("ZH-to-our-knowledge", "core", r"(?:據|就)(?:我們|作者|本文|本研究)(?:所)?知"),
    ("ZH-none", "core", r"尚[無未](?:有)?(?:任何)?(?:相關)?(?:研究|文獻|報告|試驗|資料|證據|分析|回顧|人)"),
    ("ZH-none", "core", r"[至迄]今(?:仍)?(?:沒有|未有|無)(?:任何)?(?:研究|文獻|報告|試驗|資料|證據)"),
    ("ZH-none", "core", r"目前(?:仍)?(?:並)?[無沒](?:有)?(?:任何)?(?:研究|文獻|報告|試驗|資料|證據|相關)"),
    ("ZH-none", "core", r"(?:亦|也|均|皆)無(?:任何)?(?:研究|文獻|報告|試驗)"),
    ("ZH-none", "core", r"無人(?:曾)?(?:做過|研究|報告|探討|提出|嘗試|檢定|評估|量化)"),
    ("ZH-none", "core", r"沒有(?:任何)?(?:研究|文獻|試驗)(?:曾|曾經)?(?:做過|報告|探討|檢定|評估|發現|直接)"),
    ("ZH-none", "core", r"從未有(?:人|任何)|(?:文獻|前人|學界|國內外)[^。；，\n]{0,8}(?:從未|未曾)"),
    ("ZH-none", "core", r"(?:文獻|研究)(?:中)?(?:付之闕如|闕如|空白)"),
    # --- 中文 extended ---
    ("ZH-none", "extended", r"(?:仍|尚)屬(?:未知|空白|未明)"),
    ("ZH-none", "extended", r"從未(?:被)?(?:以|用|做|檢定|報告|探討|研究|量化)"),
    ("ZH-first", "extended", r"前所未有|填補[^。；，\n]{0,6}空白"),
]

COMPILED_ABSOLUTE = [(cid, tier, re.compile(pat, re.IGNORECASE)) for cid, tier, pat in ABSOLUTE_PATTERNS]

# 明顯不是宣稱自己的新穎性、只是描述別人研究缺口以外用法的豁免。保守起見只放
# 真正無害的樣式，寧可誤報也不要漏掉真違規。
ABSOLUTE_EXEMPT = re.compile(
    r"|".join([
        r"\bfirst\s+(?:study|report)\s+day\b",
        r"\bfirst\s+author\b",
        r"\bfirst\s+line\b",
        r"\bfirst-line\b",
        r"\bfirst\s+(?:study|review)\s+visit\b",
        r"\bthe\s+first\s+(?:study|analysis|report)\s+(?:is|was|of\s+the\s+two|and\s+the\s+second)\b",   # 序數指涉：the first study is …
        r"第一(?:篇|個)(?:的|主結果|問題|排除框|節點|失敗|會|是)",                     # 第一篇的、第一個主結果
    ]),
    re.IGNORECASE,
)

# 逐條抑制：整行寫了這個標記就不掃。沒有抑制機制的 lint 只能整檔排除，等於被關掉。
NOQA_RE = re.compile(r"lint-absolute-claims:\s*ignore|noqa:\s*absolute-claims", re.IGNORECASE)

# --- mention vs use ---------------------------------------------------------
# 這個 domain 的筆記大量在「談論」絕對句本身（規則條文、禁令、反例、驗收表），
# 那些是引用不是主張。兩道判準：
#   (1) 命中字串整個被一對引號包住 → 是在引述這個句式
#   (2) 句子裡有禁令 / 規則 / 可寫不可寫的討論用語 → 是在講寫作規範
QUOTED_SPAN_RE = re.compile(r"「[^「」]*」|『[^『』]*』|“[^“”]*”")
META_TALK_RE = re.compile(
    r"不(?:可|能|要|得|應|宜|准)(?:以)?(?:寫|說|講|主張|宣稱|描述|讀成|用)"
    r"|(?:勿|禁止|嚴禁|避免)(?:寫|說|主張|宣稱|使用|用)"
    r"|可(?:以)?(?:寫|主張|宣稱)"
    r"|不等於|不足以支撐|只能讀成|不能讀成"
    r"|硬規則|規則第|domain 規則"
    r"|一律(?:要|帶|附)|必須(?:帶|附|人工|主動引用)"
    r"|宣稱[^。；\n]{0,24}之前"
    r"|措辭(?:必須|應|要|改)|改成|改為|改寫|收窄|降級|撤回|推翻|不成立|已失效",
)
# 句首的清單標籤 ❌ / ✅ / ⚠ 是檢核表在「談論」這個句式（❌「我們是第一個…」）。
# 只認句首；句中出現的 emoji 不算——前一輪整句只要含 emoji 就免驗，73% 的命中被靜默丟掉。
CHECKLIST_LEAD_RE = re.compile(r"^\s*[-*>•]*\s*(?:\*\*)?\s*[❌✅⚠]")


def _is_mention(sent: str, span: tuple[int, int]) -> bool:
    """這句是在『引用/討論』這個絕對句式，而不是在主張它。"""
    for q in QUOTED_SPAN_RE.finditer(sent):
        if q.start() < span[0] and span[1] <= q.end():
            return True
    # 引號沒收尾就被句號切斷的情況（引用外文原句最常見）：命中落在未閉合的引號之後
    head = sent[: span[0]]
    for opener, closer in (("「", "」"), ("『", "』"), ("“", "”")):
        if head.count(opener) > head.count(closer):
            return True
    if META_TALK_RE.search(sent):
        return True
    return bool(CHECKLIST_LEAD_RE.match(sent))

# --------------------------------------------------------------------------------------
# 樣式：檢索範圍證據（資料庫 / 檢索日期 / 命中筆數 / 篩選筆數）
# --------------------------------------------------------------------------------------

DATABASE_RE = re.compile(
    r"\b(PubMed|MEDLINE|Embase|EMBASE|Cochrane(?:\s+(?:Library|CENTRAL|Database))?|CENTRAL|"
    r"Web\s+of\s+Science|Scopus|CINAHL|PsycINFO|PsycInfo|ClinicalTrials\.gov|WHO\s+ICTRP|"
    r"Google\s+Scholar|Semantic\s+Scholar|Europe\s+PMC|OpenAlex|Dimensions|Lens\.org|"
    r"arXiv|medRxiv|bioRxiv|IEEE\s+Xplore|ACM\s+Digital\s+Library|EBSCO|ProQuest|Ovid|"
    r"Scielo|SciELO|LILACS|KoreaMed|CNKI|萬方|華藝|臺灣期刊論文索引)\b"
)

# 檢索語境：只有句子帶這些詞，日期 / 筆數才算「檢索範圍」的一部分。
# 少了這道，隨便一句「January 2021 到 December 2023 收案」就會被當成檢索日。
SEARCH_CONTEXT_RE = re.compile(
    r"\b(search(?:ed|es|ing)?|queri(?:ed|es)|query|retriev(?:ed|al)|screen(?:ed|ing)|"
    r"identif(?:ied|ication)|yield(?:ed)?|record(?:s)?|citation(?:s)?|database(?:s)?|"
    r"eligib(?:le|ility)|inclusion|de-?duplicat\w*|PRISMA|title(?:s)?\s+and\s+abstract(?:s)?)\b"
    r"|檢索|搜尋|查詢|資料庫|命中|去重|篩選|納入|排除",
    re.IGNORECASE,
)

MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t)?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
DATE_RE = re.compile(
    r"\b(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])\b"      # 2026-04-23
    r"|\b(?:0?[1-9]|[12]\d|3[01])\s+(?:" + MONTHS + r")\.?,?\s+(?:19|20)\d{2}\b"    # 23 April 2026
    r"|\b(?:" + MONTHS + r")\.?\s+(?:0?[1-9]|[12]\d|3[01]),?\s+(?:19|20)\d{2}\b"    # April 23, 2026
    r"|\b(?:" + MONTHS + r")\.?\s+(?:19|20)\d{2}\b"                                  # April 2026
    r"|(?:19|20)\d{2}\s*年\s*(?:0?[1-9]|1[0-2])\s*月(?:\s*(?:0?[1-9]|[12]\d|3[01])\s*日)?",
    re.IGNORECASE,
)
# 「searched ... through 2026」這種只給年份、但明講是檢索截止的寫法也算數。
BARE_YEAR_SEARCH_RE = re.compile(
    r"\b(?:search(?:ed|es)?|queri(?:ed|es)|coverage|indexed?)\b[^.;]{0,80}?"
    r"\b(?:from|through|to|until|up\s+to|between)\b[^.;]{0,30}?\b((?:19|20)\d{2})\b"
    r"|檢索(?:範圍|期間|區間)[^。；]{0,30}?((?:19|20)\d{2})\s*年",
    re.IGNORECASE,
)

COUNT_NOUN = (
    r"records?|citations?|articles?|papers?|references?|studies|study|reports?|"
    r"abstracts?|titles?|hits?|results?|publications?|entries"
)
HIT_COUNT_RE = re.compile(
    r"\b(\d[\d,]*)\s+(?:unique\s+|non-duplicate\s+|potentially\s+(?:relevant|eligible)\s+)?"
    r"(?:" + COUNT_NOUN + r")\b"
    r"|\b(?:n\s*=\s*)(\d[\d,]*)\b"
    r"|(?:命中|檢索(?:到|出)|共\s*(?:得|獲)?)\s*(\d[\d,]*)\s*[筆篇則件]"
    r"|\b(\d[\d,]*)\s*[筆篇]\s*(?:文獻|紀錄|記錄|文章|研究)"
    r"|(\d[\d,]*)\s*[筆篇則件]\s*(?:命中|結果|紀錄|記錄)"
    r"|(?:回傳|傳回|得到|找到|取回)\s*(\d[\d,]*)\s*[筆篇則件]",
    re.IGNORECASE,
)
# 表格：表頭有這些字的欄位，底下的數字就是命中數（某專案 的檢索紀錄寫成
# 「| # | 資料庫 | 檢索式 | 命中 | 篩入 |」，逐列只有數字，沒有「筆」）。
HIT_HEADER_RE = re.compile(r"^(?:命中(?:數|筆數)?|hits?|records?|results?|retrieved|n\s*retrieved|yield)$", re.IGNORECASE)
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}")
HIT_VERB_RE = re.compile(
    r"\b(search(?:ed|es)?|queri(?:ed|es)|yield(?:ed)?|identif(?:ied)?|retriev(?:ed)?|"
    r"return(?:ed)?|generat(?:ed)?|produc(?:ed)?|found)\b|檢索|搜尋|命中|查得",
    re.IGNORECASE,
)
SCREEN_VERB_RE = re.compile(
    r"\b(screen(?:ed|ing)?|exclud(?:ed|ing)?|includ(?:ed|ing)?|retain(?:ed)?|assess(?:ed)?|"
    r"eligible|full[-\s]?text|de-?duplicat\w*|remov(?:ed|al))\b|篩選|排除|納入|去重|全文",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------------------
# 樣式：零命中 vs 零篇符合
# --------------------------------------------------------------------------------------

ZERO_HITS_RE = re.compile(
    r"\b(?:no|zero|0)\s+(?:records?|citations?|hits?|results?|references?)\s+"
    r"(?:were\s+|was\s+|been\s+)?(?:retrieved|returned|identified|found|yielded)\b"
    r"|\b(?:search|query|queries)\s+(?:\w+\s+){0,3}?(?:returned|yielded|retrieved|produced)\s+"
    r"(?:no|zero|0)\s+(?:records?|citations?|hits?|results?|articles?)?\b"
    r"|零\s*命中|命中\s*0\s*[筆篇]|檢索(?:結果)?為\s*0|無(?:任何)?命中",
    re.IGNORECASE,
)
ZERO_ELIGIBLE_RE = re.compile(
    r"\b(?:no|zero|none\s+of\s+the)\s+(?:\w+\s+){0,2}?(?:studies|articles|trials|papers|reports?|records?)\s+"
    r"(?:met|fulfilled|satisfied|meeting)\b"
    r"|\bnone\s+(?:met|fulfilled|satisfied)\s+(?:the\s+)?(?:inclusion|eligibility|criteria)\b"
    r"|\bno\s+(?:eligible|includable|qualifying)\s+(?:studies|articles|trials|papers|records?)\b"
    r"|\bno\s+(?:studies|articles|trials|papers)\s+(?:remained|were\s+retained|were\s+included)\b"
    r"|零\s*篇\s*符合|(?:無|沒有)(?:任何)?(?:研究|文獻|試驗)符合|篩選後(?:並)?無(?:任何)?(?:研究|文獻)",
    re.IGNORECASE,
)
AMBIGUOUS_ZERO_RE = re.compile(
    r"\bno\s+(?:relevant\s+|applicable\s+)?(?:studies|research|articles|literature|papers|trials)\s+"
    r"(?:were?\s+|was\s+|has\s+been\s+|have\s+been\s+)?(?:found|identified|available|located|exist|existed)\b"
    r"|\bwe\s+(?:found|identified)\s+no\s+(?:studies|articles|trials|literature|papers)\b"
    r"|(?:沒有|未)(?:找到|發現)(?:任何)?(?:研究|文獻|報告)"
    r"|找不到(?:任何)?(?:研究|文獻|報告)",
    re.IGNORECASE,
)

# 文件內指向的檢索紀錄檔（某 MA 專案 就是這樣寫：`02_search/round-01/queries.txt`）
POINTER_RE = re.compile(
    r"`([^`\n]{3,160}?\.(?:txt|md|yaml|yml|json|csv|tsv|log))`"
    r"|(?<![\w/`])((?:[\w.\-]+/){1,6}[\w.\-]+\.(?:txt|md|yaml|yml|json|csv|tsv|log))\b"
)

CHECK_LABELS = {
    "A1": "A1 絕對句偵測（中英文樣式）",
    "A2": "A2 檢索範圍區塊完整性（資料庫 + 檢索日期 + 命中筆數）",
    "B1": "B1 「零命中」與「零篇符合」同段混寫",
    "B2": "B2 零結果語意曖昧且全文無筆數可判別",
}

ELEMENT_LABELS = {
    "database": "資料庫名稱",
    "search_date": "檢索日期",
    "hit_count": "命中筆數",
}


# --------------------------------------------------------------------------------------
# 讀檔
# --------------------------------------------------------------------------------------

def _strip_xml(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    for ent, ch in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        text = text.replace(ent, ch)
    return text


def read_docx_paragraphs(path: Path) -> list[str]:
    """把 .docx 讀成段落清單；段落序號即為回報用的行號。"""
    with zipfile.ZipFile(path) as zf:
        names = [n for n in ("word/document.xml",) if n in zf.namelist()]
        if not names:
            raise ValueError("docx 內找不到 word/document.xml")
        xml = zf.read(names[0]).decode("utf-8", errors="replace")
    body = xml.split("<w:body")[-1]
    paras = re.split(r"</w:p\s*>", body)
    out = []
    for para in paras:
        para = re.sub(r"<w:tab\b[^>]*/>", "\t", para)
        para = re.sub(r"<w:br\b[^>]*/>", " ", para)
        out.append(_strip_xml(para).strip())
    return out


def read_lines(path: Path) -> list[str]:
    if path.suffix.lower() == DOCX_SUFFIX:
        return read_docx_paragraphs(path)
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def collect_files(roots: list[Path], excludes: list[str],
                  scannable: set[str]) -> tuple[list[Path], list[str], list[str]]:
    """回傳 (可掃描檔案, 不存在的路徑, 被 exclude 樣式跳過的檔案)。"""
    found: list[Path] = []
    missing: list[str] = []
    excluded: list[str] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            missing.append(str(root))
            continue
        if root.is_file():
            if root.suffix.lower() in scannable and root not in seen:
                seen.add(root)
                found.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if p.suffix.lower() not in scannable:
                    continue
                if name.startswith("~$") or name.startswith("."):
                    continue
                rel = str(p)
                if any(pat in rel for pat in excludes):
                    excluded.append(rel)
                    continue
                if p not in seen:
                    seen.add(p)
                    found.append(p)
    return found, missing, excluded


# --------------------------------------------------------------------------------------
# 句子切分
# --------------------------------------------------------------------------------------

SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？；;])\s+|(?<=[。！？])")


def sentences_of(line: str) -> list[str]:
    parts = [s.strip() for s in SENT_SPLIT_RE.split(line) if s and s.strip()]
    return parts or ([line.strip()] if line.strip() else [])


def clip(text: str, width: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


# --------------------------------------------------------------------------------------
# 證據抽取
# --------------------------------------------------------------------------------------

class Evidence:
    """一份檔案裡找得到的檢索範圍元素。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.database: list[dict] = []
        self.search_date: list[dict] = []
        self.hit_count: list[dict] = []
        self.screen_count: list[dict] = []

    def merge_from(self, other: "Evidence") -> None:
        self.database += other.database
        self.search_date += other.search_date
        self.hit_count += other.hit_count
        self.screen_count += other.screen_count

    def missing(self) -> list[str]:
        return [k for k in ("database", "search_date", "hit_count") if not getattr(self, k)]


def _record(path: Path, lineno: int, sentence: str, matched: str) -> dict:
    return {
        "file": str(path),
        "line": lineno,
        "matched": clip(matched, 80),
        "sentence": clip(sentence),
        "locator": f"{path}:{lineno}",
    }


def table_hit_counts(path: Path, lines: list[str]) -> list[dict]:
    """markdown / docx 表格裡「命中」欄的數字。"""
    out: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        if lines[i].count("|") < 2:
            i += 1
            continue
        header = [c.strip().strip("*").strip() for c in lines[i].strip().strip("|").split("|")]
        cols = [j for j, c in enumerate(header) if HIT_HEADER_RE.match(c)]
        j = i + 1
        while j < n and lines[j].count("|") >= 2:
            if cols and not TABLE_SEP_RE.match(lines[j]):
                cells = [c.strip().strip("*").strip() for c in lines[j].strip().strip("|").split("|")]
                for col in cols:
                    if col < len(cells) and re.fullmatch(r"\d[\d,]*", cells[col]):
                        out.append(_record(path, j + 1, lines[j], f"{header[col]}={cells[col]}"))
            j += 1
        i = j
    return out


def extract_evidence(path: Path, lines: list[str]) -> Evidence:
    ev = Evidence(path)
    ev.hit_count.extend(table_hit_counts(path, lines))
    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        for sent in sentences_of(line):
            has_ctx = bool(SEARCH_CONTEXT_RE.search(sent))

            if has_ctx:
                m = DATABASE_RE.search(sent)
                if m:
                    ev.database.append(_record(path, idx, sent, m.group(0)))

                dm = DATE_RE.search(sent)
                if dm:
                    ev.search_date.append(_record(path, idx, sent, dm.group(0)))
                else:
                    bm = BARE_YEAR_SEARCH_RE.search(sent)
                    if bm:
                        ev.search_date.append(_record(path, idx, sent, bm.group(0)))

            if HIT_VERB_RE.search(sent):
                hm = HIT_COUNT_RE.search(sent)
                if hm:
                    ev.hit_count.append(_record(path, idx, sent, hm.group(0)))
            if SCREEN_VERB_RE.search(sent):
                sm = HIT_COUNT_RE.search(sent)
                if sm:
                    ev.screen_count.append(_record(path, idx, sent, sm.group(0)))
    return ev


def resolve_pointers(path: Path, lines: list[str]) -> list[Path]:
    """文件裡指名的檢索紀錄檔（`02_search/round-01/queries.txt` 這種）解析成實際路徑。"""
    candidates: set[str] = set()
    for line in lines:
        for m in POINTER_RE.finditer(line):
            token = m.group(1) or m.group(2)
            if token:
                candidates.add(token.strip())
    bases = [path.parent, *path.parents]
    resolved: list[Path] = []
    for token in sorted(candidates):
        if token.startswith(("http://", "https://")):
            continue
        for base in bases[:6]:
            cand = (base / token).resolve()
            if cand.is_file() and cand.stat().st_size <= 2_000_000:
                if cand not in resolved:
                    resolved.append(cand)
                break
    return resolved


# --------------------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------------------

SUPPRESS_KEYS = ("noqa", "exempt", "mention", "ignore_pattern", "extended_tier")


def find_absolute_claims(path: Path, lines: list[str], mode: str,
                         ignore_patterns: list[re.Pattern],
                         suppressed: dict[str, int]) -> list[dict]:
    """回傳絕對句命中；被抑制的每一筆都計進 suppressed（印出來，不靜默丟）。"""
    hits: list[dict] = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("```", "~~~", "|", "<!--")):
            continue
        if NOQA_RE.search(line):
            suppressed["noqa"] += 1
            continue
        for sent in sentences_of(line):
            if ABSOLUTE_EXEMPT.search(sent):
                if any(rx.search(sent) for _, _, rx in COMPILED_ABSOLUTE):
                    suppressed["exempt"] += 1
                continue
            if ignore_patterns and any(rx.search(sent) for rx in ignore_patterns):
                if any(rx.search(sent) for _, _, rx in COMPILED_ABSOLUTE):
                    suppressed["ignore_pattern"] += 1
                continue
            matched_ids: list[str] = []
            matched_txt: list[str] = []
            tiers: list[str] = []
            mention = False
            for cid, tier, rx in COMPILED_ABSOLUTE:
                m = rx.search(sent)
                if not m:
                    continue
                if mode == "lenient" and tier == "extended":
                    suppressed["extended_tier"] += 1
                    continue
                if _is_mention(sent, m.span()):
                    mention = True
                    continue
                if cid not in matched_ids:
                    matched_ids.append(cid)
                    matched_txt.append(m.group(0).strip())
                    tiers.append(tier)
            if mention and not matched_ids:
                suppressed["mention"] += 1
            if matched_ids:
                hits.append({
                    "file": str(path),
                    "line": idx,
                    "locator": f"{path}:{idx}",
                    "pattern_ids": matched_ids,
                    "tiers": tiers,
                    "matched": [clip(t, 80) for t in matched_txt],
                    "sentence": clip(sent, 400),
                })
    return hits


def zero_claim_checks(path: Path, lines: list[str], ev: Evidence) -> list[dict]:
    warnings: list[dict] = []
    doc_has_counts = bool(ev.hit_count) or bool(ev.screen_count)
    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        zh = ZERO_HITS_RE.search(line)
        ze = ZERO_ELIGIBLE_RE.search(line)
        if zh and ze:
            warnings.append({
                "check": "B1",
                "file": str(path),
                "line": idx,
                "locator": f"{path}:{idx}",
                "kind": "zero-conflation",
                "message": "同一段同時出現「零命中」與「零篇符合」語意，兩者不可互換書寫",
                "matched": [clip(zh.group(0), 80), clip(ze.group(0), 80)],
                "sentence": clip(line, 400),
            })
            continue
        for sent in sentences_of(line):
            am = AMBIGUOUS_ZERO_RE.search(sent)
            if not am:
                continue
            if ZERO_HITS_RE.search(sent) or ZERO_ELIGIBLE_RE.search(sent):
                continue  # 已經講清楚是哪一種
            if doc_has_counts:
                continue  # 文件裡有筆數可據以判別
            warnings.append({
                "check": "B2",
                "file": str(path),
                "line": idx,
                "locator": f"{path}:{idx}",
                "kind": "ambiguous-zero",
                "message": "零結果語意曖昧（分不出「零命中」還是「篩選後零篇符合」），且文件內無命中／篩選筆數可判別",
                "matched": [clip(am.group(0), 80)],
                "sentence": clip(sent, 400),
            })
    return warnings


def run(roots: list[Path], scope: str, excludes: list[str], mode: str = "lenient",
        ignore_patterns: list[re.Pattern] | None = None) -> dict:
    ignore_patterns = ignore_patterns or []
    if mode == "lenient":
        excludes = list(excludes) + DEFAULT_EXCLUDES
        scannable = LENIENT_SUFFIXES | {DOCX_SUFFIX}
    else:
        scannable = SCANNABLE
    files, missing, excluded = collect_files(roots, excludes, scannable)
    suppressed: dict[str, int] = {k: 0 for k in SUPPRESS_KEYS}
    skipped: list[dict] = []
    lines_by_file: dict[Path, list[str]] = {}

    for path in files:
        try:
            lines_by_file[path] = read_lines(path)
        except Exception as exc:  # noqa: BLE001 — 壞檔不該讓整個 lint 掛掉
            skipped.append({"file": str(path), "reason": f"讀檔失敗：{exc}"})

    scanned = list(lines_by_file)
    evidence: dict[Path, Evidence] = {
        p: extract_evidence(p, lines_by_file[p]) for p in scanned
    }

    # 同一目錄的檔案視為同一份文件（Quarto 把 Introduction 與 Methods 拆成兩檔）
    by_dir: dict[Path, list[Path]] = {}
    for p in scanned:
        by_dir.setdefault(p.parent, []).append(p)

    violations: list[dict] = []
    warnings: list[dict] = []
    claim_total = 0
    pointer_cache: dict[Path, Evidence] = {}

    for path in scanned:
        lines = lines_by_file[path]
        claims = find_absolute_claims(path, lines, mode, ignore_patterns, suppressed)
        claim_total += len(claims)
        if not claims:
            warnings.extend(zero_claim_checks(path, lines, evidence[path]))
            continue

        pool = Evidence(path)
        pool.merge_from(evidence[path])
        sources = [str(path)]

        if scope in ("dir", "tree"):
            for sib in by_dir.get(path.parent, []):
                if sib != path:
                    pool.merge_from(evidence[sib])
                    sources.append(str(sib))
        if scope == "tree":
            for other in scanned:
                if other != path and other.parent != path.parent:
                    pool.merge_from(evidence[other])
            sources.append(f"<整棵掃描樹，共 {len(scanned)} 檔>")

        # 文件指向的檢索紀錄檔
        for ptr in resolve_pointers(path, lines):
            if ptr in pointer_cache:
                pool.merge_from(pointer_cache[ptr])
                sources.append(str(ptr))
                continue
            try:
                ptr_lines = ptr.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:  # noqa: BLE001
                continue
            pev = extract_evidence(ptr, ptr_lines)
            pointer_cache[ptr] = pev
            pool.merge_from(pev)
            sources.append(str(ptr))

        # 同目錄借來的證據：自己這份（含指名的檢索紀錄檔）補不齊、靠鄰居補齊的，
        # 在 lenient 記成警告（evidence-borrowed），strict 直接算違規。dir 是閘門的預設
        # 值，而「同目錄任何一份檔提過資料庫＋日期＋筆數就整目錄免罪」正是它恆綠的原因。
        if scope in ("dir", "tree"):
            own = Evidence(path)
            own.merge_from(evidence[path])
            for ptr in resolve_pointers(path, lines):
                if ptr in pointer_cache:
                    own.merge_from(pointer_cache[ptr])
            own_missing = own.missing()
            if own_missing and not pool.missing():
                for claim in claims:
                    entry = {
                        "check": "A2",
                        "file": claim["file"],
                        "line": claim["line"],
                        "locator": claim["locator"],
                        "kind": "evidence-borrowed",
                        "pattern_ids": claim["pattern_ids"],
                        "matched": claim["matched"],
                        "sentence": claim["sentence"],
                        "message": "這句的檢索範圍證據不在它自己的檔裡（缺：" + "、".join(ELEMENT_LABELS[k] for k in own_missing)
                                   + "），是靠同目錄其他檔補齊的；scope: file 下會是違規",
                        "borrowed_from": [src for src in sources if src != str(path)][:4],
                    }
                    if mode == "strict":
                        entry.update({"severity": "violation",
                                      "missing_elements": own_missing,
                                      "missing_elements_zh": [ELEMENT_LABELS[k] for k in own_missing],
                                      "evidence_present": {k: [e["locator"] for e in getattr(own, k)][:3]
                                                           for k in ("database", "search_date", "hit_count", "screen_count")},
                                      "evidence_scope": [str(path)]})
                        violations.append(entry)
                    else:
                        warnings.append(entry)

        missing_elems = pool.missing()
        present = {
            k: [e["locator"] for e in getattr(pool, k)][:3]
            for k in ("database", "search_date", "hit_count", "screen_count")
        }
        if missing_elems:
            for claim in claims:
                violations.append({
                    "check": "A2",
                    "severity": "violation",
                    "file": claim["file"],
                    "line": claim["line"],
                    "locator": claim["locator"],
                    "pattern_ids": claim["pattern_ids"],
                    "matched": claim["matched"],
                    "sentence": claim["sentence"],
                    "missing_elements": missing_elems,
                    "missing_elements_zh": [ELEMENT_LABELS[k] for k in missing_elems],
                    "evidence_present": present,
                    "evidence_scope": sources,
                })

        warnings.extend(zero_claim_checks(path, lines, pool))

    status_note = None
    if missing:
        status_note = "有指定路徑不存在"
    elif not scanned:
        status_note = "沒有任何可掃描的 md / qmd / docx"

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "roots": [str(r) for r in roots],
        "scope_mode": scope,
        "mode": mode,
        "checks_enabled": list(CHECK_LABELS),
        "missing_paths": missing,
        "skipped_files": skipped,
        "excluded_files": excluded,
        "files_scanned": len(scanned),
        "absolute_claims_found": claim_total,
        "suppressed": suppressed,
        "suppressed_total": sum(suppressed.values()),
        "violations": violations,
        "warnings": warnings,
        "status_note": status_note,
        "summary": {
            "violations": len(violations),
            "warnings": len(warnings),
            "files_with_violations": len({v["file"] for v in violations}),
        },
    }


# --------------------------------------------------------------------------------------
# 人看的輸出
# --------------------------------------------------------------------------------------

def render(report: dict, strict: bool, root_hint: Path | None) -> str:
    out: list[str] = []
    add = out.append

    def rel(p: str) -> str:
        if root_hint:
            try:
                return str(Path(p).relative_to(root_hint))
            except ValueError:
                return p
        return p

    add("=" * 78)
    add("絕對句 lint —— delivery discipline 規則 5")
    add("=" * 78)
    add(f"掃描根目錄  : {', '.join(report['roots'])}")
    add(f"證據涵蓋範圍: {report['scope_mode']}"
        + {"file": "（預設，嚴格：同檔 + 該檔指名的檢索紀錄檔）",
           "dir": "（寬鬆 opt-in：再加同目錄所有檔案的證據）",
           "tree": "（整棵樹，最寬鬆）"}[report["scope_mode"]])
    add(f"模式        : {report['mode']}"
        + {"lenient": "（只抓 core 樣式；預設排除驗收工作檔／LLM 暫存／筆記；.txt 不掃）",
           "strict": "（core + extended 樣式；不預設排除任何檔；同目錄借來的證據算違規）"}[report["mode"]])
    add(f"掃描檔案數  : {report['files_scanned']}（依 exclude 樣式跳過 {len(report['excluded_files'])} 檔）")
    add(f"偵測到絕對句: {report['absolute_claims_found']} 句；另有 {report['suppressed_total']} 個樣式命中被抑制"
        + "（" + "、".join(f"{k} {v}" for k, v in report["suppressed"].items() if v) + "）" if report["suppressed_total"] else
        f"偵測到絕對句: {report['absolute_claims_found']} 句；樣式命中被抑制 0 個")
    add("")
    add("啟用的檢查：")
    for cid, label in CHECK_LABELS.items():
        add(f"  [啟用] {label}")
    if report["skipped_files"]:
        add("跳過的檔案：")
        for s in report["skipped_files"]:
            add(f"  [跳過] {rel(s['file'])} —— {s['reason']}")
    else:
        add("跳過的檔案：無")
    if report["missing_paths"]:
        add("不存在的路徑：")
        for m in report["missing_paths"]:
            add(f"  [缺] {m}")
    add("")

    if report["violations"]:
        add("-" * 78)
        add(f"違規（{len(report['violations'])} 筆）—— 絕對句缺檢索範圍限定")
        add("-" * 78)
        for i, v in enumerate(report["violations"], 1):
            add(f"[{i}] {rel(v['file'])}:{v['line']}")
            add(f"    命中樣式 : {', '.join(v['pattern_ids'])} → {' / '.join(v['matched'])}")
            add(f"    原句     : {v['sentence']}")
            add(f"    缺少元素 : {'、'.join(v['missing_elements_zh'])}")
            for k in ("database", "search_date", "hit_count"):
                got = v["evidence_present"][k]
                mark = "○ 缺" if not got else "● 有"
                shown = "、".join(rel(g) for g in got) if got else "（找不到）"
                add(f"      {mark} {ELEMENT_LABELS[k]}: {shown}")
            extra = v["evidence_present"]["screen_count"]
            add(f"      {'●' if extra else '○'} 篩選筆數（參考，不計入判定）: "
                f"{'、'.join(rel(g) for g in extra) if extra else '（找不到）'}")
            add("")

    if report["warnings"]:
        add("-" * 78)
        add(f"警告（{len(report['warnings'])} 筆）—— 零命中／零篇符合"
            + ("；--strict 下計入失敗" if strict else "；不影響 exit code"))
        add("-" * 78)
        for i, w in enumerate(report["warnings"], 1):
            add(f"[{i}] {rel(w['file'])}:{w['line']}  ({w['check']} {w['kind']})")
            add(f"    {w['message']}")
            if w.get("borrowed_from"):
                add(f"    借自 : {'、'.join(rel(b) for b in w['borrowed_from'])}")
            add(f"    原句 : {w['sentence']}")
            add("")

    add("=" * 78)
    fails = len(report["violations"]) + (len(report["warnings"]) if strict else 0)
    if report["status_note"]:
        add(f"結果：無法完成檢查 —— {report['status_note']}（exit 2）")
    elif fails:
        add(f"結果：不通過 —— 違規 {len(report['violations'])} 筆、"
            f"警告 {len(report['warnings'])} 筆（exit 1）")
    else:
        add(f"結果：通過 —— 啟用 {len(CHECK_LABELS)} 項檢查（"
            + "、".join(CHECK_LABELS) + f"），跳過 {len(report['skipped_files'])} 檔，"
            f"掃了 {report['files_scanned']} 個檔案，違規 0 筆、警告 {len(report['warnings'])} 筆（exit 0）")
    add("=" * 78)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="絕對句 lint：偵測缺檢索範圍限定的新穎性宣稱（delivery discipline 規則 5）",
    )
    ap.add_argument("paths", nargs="+", help="要掃描的目錄或檔案（md / qmd / docx）")
    ap.add_argument("--json", dest="json_out", help="把完整結果寫成 JSON 檔")
    ap.add_argument("--scope", choices=("file", "dir", "tree"), default="file",
                    help="檢索範圍證據的採認範圍。預設 file（嚴格：只認同一份文件本身 + "
                         "該文件明確指名的檢索紀錄檔）；dir / tree 是寬鬆模式，需明確 opt-in")
    ap.add_argument("--exclude", action="append", default=[],
                    help="路徑含此字串就跳過，可重複給")
    ap.add_argument("--strict", action="store_true", help="把 B1/B2 警告也算成失敗")
    ap.add_argument("--mode", choices=("lenient", "strict"), default="lenient",
                    help="lenient（預設）：只抓 core 樣式、預設排除驗收工作檔與 LLM 暫存；"
                         "strict：core + extended、不排除、同目錄借來的證據算違規")
    ap.add_argument("--ignore-pattern", action="append", default=[],
                    help="句子符合此正則就不算絕對句（可重複給；抑制數會印出來）")
    ap.add_argument("--quiet", action="store_true", help="只印結論那幾行")
    args = ap.parse_args(argv)

    roots = [Path(p).expanduser().resolve() for p in args.paths]
    ignore_patterns = [re.compile(p, re.IGNORECASE) for p in args.ignore_pattern]
    report = run(roots, args.scope, args.exclude, args.mode, ignore_patterns)

    if args.json_out:
        out_path = Path(args.json_out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["json_written_to"] = str(out_path)

    root_hint = roots[0] if len(roots) == 1 and roots[0].is_dir() else None
    text = render(report, args.strict, root_hint)
    if args.quiet:
        text = "\n".join(text.splitlines()[-3:])
    print(text)
    if args.json_out:
        print(f"JSON 已寫入：{report['json_written_to']}")

    if report["status_note"]:
        return 2
    if report["violations"] or (args.strict and report["warnings"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

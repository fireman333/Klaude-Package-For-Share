"""裸數字 lint —— 把交付紀律規則 1「數字單一來源」變成擋得住的閘。

為什麼有這支
------------
規則 1 說「報告的每個數字都從程式產生的檔讀出，不手打」，但在這支之前沒有任何
工具在擋。實際後果：某專案交給老師的 docx 裡有一批數字在任何 stats
JSON 都找不到來源，其中「313 筆」是手打的**錯值**（登記簿當時是 315 筆、現在是
323 筆），27.4% / 55.6% / 72.6% 則是拿兩個世代人數在腦內相除得到的。C1–C7 全部
看不見這一類：它們檢查的是「檔案之間的新舊與涵蓋」，沒有一項去讀文件裡的數字。

這支就是去讀。對文件裡每一個數字字面問一句：**它在這份文件自己宣告的 stats JSON
來源裡找得到嗎？** 找不到就報。

設計上最重要的一件事：**寧可漏報，不要吵**
--------------------------------------------
一個每次都亮紅燈的 lint 會被關掉，關掉之後強制力等於零 —— 這在本 domain 已經是
寫進 check_freshness.py 註解的教訓（「每次都會響的警報會訓練人忽略整個閘門」）。
2026-09-03 第三輪實測：照範本啟用會讓 12/12 專案全紅、三個綠燈全滅，某專案
誤報率 5.7%（181/3173）。逐條人工分類之後，誤報幾乎全落在下面這幾類：

  1. 文獻裡別人的數字（PARAGON-HF n = 1,097、Chang 2026 n = 6,438）—— 本來就不該在
     stats JSON 裡，但它們是「有來源」的，來源是那篇論文。
  2. 識別碼：沒帶前綴的 PMID（36340256）、病人編號欄、基因座標。
  3. 章節號（「見 4.8 節」「§3」「4.6.1」）、百分位慣例（2.5–97.5 百分位）、
     比較門檻（p < 0.0001、≥ 3000 pg/mL、Python <3.11）。
  4. 驗收敘事的計數（「約 430 個數值」「28,512 格逐格比對」「1,141 行」）。
  5. **比對本身的漏洞**：JSON 存比例 0.294、文件寫「29.4 個百分點」或表格裡沒帶 %
     的「71.2」；科學記號 2.1×10⁻⁵ 被拆成 2.1。
  6. **來源宣告太窄**：0813 AF 的 116.5、1,272、1,774 都在 `analysis/data` 的其他
     stats 檔裡，只是那份文件的 sources 清單沒列。

第 2、3、5 類是「這不是統計量」或「比對做錯」，直接修（遮罩 / 縮放 / 科學記號）。
第 1、4、6 類**不能靜默跳過**——那是第一輪犯過的錯（把難判的情況跳掉讓數字好看）。
所以本工具把「找不到來源」的數字分成兩層：

  * **blocking**：真的在任何來源都找不到、也沒有任何可辨識的外部出處。
  * **advisory**：找不到，但有可辨識的理由 —— 同一句帶文獻引用標記（`[[PMID]]`、
    Author 2026、et al.、「作者原值」）；只在來源檔的散文欄位裡出現；在宣告範圍外的
    其他 stats 檔找得到；帶「約 / 近」的近似值；行內明講是母世代／姊妹專案的數字。
    **每一筆都印出來、都進 JSON，只是不擋交付。**

兩檔：`mode: lenient`（預設）只有 blocking 才 exit 1；`mode: strict` 任何找不到的都
exit 1。rollout 從 lenient 開始，跑穩了再切 strict。

「放行」分兩種，**只有第一種可以免驗**
------------------------------------------
1. **「這不是統計量」** —— 頁碼、圖表編號、DOI、年份、CI 水準、章節號、識別碼。
   這類與來源池無關，直接遮掉（`MASKS`）。
2. **「這個數字有來源」** —— 行內提到某個 `.json`、寫了「來源：」、或住在
   `<!-- AUTO -->` 區塊裡。這是一個**關於來源池的宣稱**，本身就是要被查證的對象，
   所以**照樣比對來源池**，比不到就報，並標成 `claimed_source: true`。

比對是**數值容差**比對，不是字串比對：JSON 存 0.8412、文件寫 0.84 視為找得到
（容差取文件自己的小數位數）。文件寫得比來源精細（JSON 0.84、文件 0.8412）則**不**
算找得到。百分比與比例互通（27.4% ↔ 0.274；表格裡沒帶 % 的 71.2 ↔ 0.712，這種
會在 JSON 標 `matched_via: percent_scaled`）；科學記號以相對容差 5% 比對。

設定
----
沿用 `research-checks.yaml`，新增一項 check：

    checks:
      C8_bare_numbers:
        document:                       # 與 C5 完全相同的三種寫法
          - path: report/x.md
            sources: [a_stats.json, ../其他專案/data/b_stats.json]
          - report/y.md                 # 未宣告 sources → 用 stats_index / data_dir 全部
        data_dir: data                  # 省略時沿用 C5 → C1 的設定
        stats_index: data/stats_index.json
        report: bare_number_lint.json   # 輸出 JSON 的位置（相對專案根目錄）
        mode: lenient                   # lenient（預設）/ strict
        min_integer: 1000               # 大於三位數的整數才檢查（預設 1000）
        extra_sources: []               # 加進**每一份**文件來源池的檔（母世代 stats 之類）
        ignore_patterns: []             # 專案自訂的額外豁免正則

`document` 省略時直接沿用 `C5_document_vs_stats` 的 document —— 兩者要守的是同一批
交付物，分開維護只會漂開。

已知極限（**不要**把「通過」當成「數字都對」）
------------------------------------------------
1. 比對的是「這個值在來源池裡存不存在」，不是「這個值是不是這句話該用的那一個」。
   池子動輒幾千個數，撞號會發生（百分比縮放後更會）。**通過只代表沒有明顯的無來源
   數字，不代表數字用對了。**
2. 只掃得到文件裡的文字。圖表繪圖區、docx 內嵌圖片裡的數字掃不到。
3. lenient 模式下，一句同時引用文獻又寫自己結果的話，自己那個數字也會被降成
   advisory。要抓這種，看 advisory 清單或切 strict。
4. 未宣告 sources 的文件拿「全部 stats 檔」當池子，撞號機率上升。要守得住就逐文件
   宣告來源；找得到但在宣告範圍外的數字會以 `found_outside_declared` 列出，順手補。

用法
----
    python3 lint_bare_numbers.py [PROJECT_DIR] [--config PATH] [--json PATH]
                                 [--mode lenient|strict] [--quiet] [--max-list N]

Exit code
---------
    2 = 檢查無法進行 / 未受保護（沒有設定檔、沒有 C8 設定、document 為空、
        要掃的文件或宣告的來源檔不存在、文件讀不開）
    1 = 檢查跑了，且發現無來源的數字（lenient：只算 blocking；strict：全算）
    0 = 真的跑過而且全過；訊息會列出掃了哪幾份文件、跳過哪幾份、豁免了幾個字面、
        advisory 幾個
"""
from __future__ import annotations

import bisect
import html
import json
import math
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 pyyaml：python3 -m pip install pyyaml")

CONFIG_NAME = "research-checks.yaml"
CHECK_KEY = "C8_bare_numbers"
DEFAULT_REPORT = "bare_number_lint.json"
DEFAULT_MIN_INTEGER = 1000
DEFAULT_MODE = "lenient"

# ─────────────────────────────────────────────────────────── 遮罩（豁免）規則
#
# 每條都是「這裡的數字不是統計量，是編號 / 慣例 / 識別碼」。遮罩的作法是把命中的
# 字元換成等量空白 —— 位置不變，後面回報行號欄位時才對得上。
#
# 順序有意義：識別碼與網址要先遮，否則裡面的數字會被日期或版本規則拆走一半。
MASKS: list[tuple[str, re.Pattern]] = [
    # 網址、DOI、PMID、NCT、markdown 連結目標：整段都是識別碼
    ("url", re.compile(r"https?://\S+|www\.\S+")),
    ("doi", re.compile(r"\b10\.\d{4,}/\S+|\bdoi:\s*\S+", re.I)),
    ("pmid", re.compile(r"\b(?:PMID|PMCID|PMC|NCT|ISRCTN)[:\s]*\d+", re.I)),
    # 沒帶前綴的 PMID：1xxxxxxx–4xxxxxxx 八位整數、不帶千分位。本 domain 稿件把 PMID
    # 直接寫在括號裡（Abe 2022（36340256））、或在表格裡列一串。八位不帶逗號的整數
    # 不會是本 domain 任何一個統計量（世代最大也才幾千）。
    ("pmid_bare", re.compile(r"(?<![\d.,])[1-4]\d{7}(?![\d.,])")),
    # 基因座標 chr3:30,837,866、病人編號 no.1469、#12
    ("coordinate", re.compile(r"\bchr\w*:\s*\d[\d,]*(?:\s*[-–]\s*\d[\d,]*)?", re.I)),
    ("id_ref", re.compile(r"(?:\bno\.|№|#|編號|病歷號|識別碼|\bID)\s*[:：]?\s*\d+", re.I)),
    ("link", re.compile(r"\]\([^)]*\)")),
    # 參考文獻編號：[12]、[1,3]、[[37994616]]（本 domain 稿件用雙括號帶 PMID）
    ("citation", re.compile(r"\[\[[^\]]*\]\]|\[\s*\d[\d,;\s–\-]*\]")),
    # 行內程式碼：檢索式、欄位名、檔名住在這裡，裡面的數字不是報告的數字。
    # 但「整段只有數字＋中文單位」不是程式碼 —— 那是有人把數字宣稱包進反引號，
    # 等於一個誰都能用的逃生門（`9999 筆病人` 就免驗了）。這種不遮，照樣驗來源。
    ("code", re.compile(r"`(?![\d.,%\s　-鿿–—~±]*`)[^`]*`")),
    # 日期與年份
    ("date", re.compile(r"\d{4}\s*[-/年]\s*\d{1,2}(?:\s*[-/月]\s*\d{1,2}\s*日?)?")),
    ("year", re.compile(r"(?<![\d.])(?:19|20)\d{2}(?![\d.])")),
    # 版本號
    ("version", re.compile(r"\bv\.?\s?\d+(?:\.\d+)*\b|"
                           r"\b(?:Python|R|pandas|numpy|scipy|lifelines|statsmodels)\s*[<>=≥≤]*\s*\d+(?:\.\d+)*",
                           re.I)),
    # 分組標籤：Q1–Q4 四分位、T1–T3 三分位、FU1–FU4 追蹤訪次、P1–P5 優先度
    ("group_label", re.compile(r"\b(?:[QT]|FU|P)[1-9]\b")),
    # 圖表 / 章節 / 頁碼 / 步驟編號：數字在名詞後面
    ("figure_ref", re.compile(
        r"(?:Figure|Fig\.?|Table|Supp\w*|Appendix|Section|Sec\.|Step|Stage|Round|Block|Model|"
        r"附錄|附表|附圖|表|圖|第|步驟|輪|頁|節|章|條|欄|列|區塊)\s*\d+(?:[-–.]\d+)*[a-z]?")),
    ("page_ref", re.compile(r"\bpp?\.\s*\d+(?:\s*[-–]\s*\d+)?")),
    # 章節號，數字在名詞前面（中文寫法）：「4.8 節」「3.1a 小節」「§3」「4.6.1」「見 1.3」
    ("section_ref", re.compile(
        r"§\s*\d+(?:\.\d+)*[a-z]?"
        r"|(?<![\d.])\d+(?:\.\d+){2,}[a-z]?(?![\d.])"                       # 4.6.1
        r"|(?<![\d.])\d+\.\d+[a-z](?![\w])"                                 # 3.1a
        r"|(?<![\d.])\d+\.\d+[a-z]?(?:\s*[、,]\s*\d+(?:\.\d+)?[a-z]?)*\s*(?:節|章|小節|款|項)"   # 4.8 節、3.1a、4.2、5、6 節
        r"|(?:見|詳見|參見|依|照|自|於|與)\s*\d+(?:\.\d+)*[a-z]?\s*(?:節|章|小節)?(?=[^\d]|$)")),
    # markdown 有序清單的項目編號、標題的節次編號（docx 標題沒有 #，靠「1.1 資料」這種
    # 行首多層編號 + 空白／全形空白辨認）
    ("list_marker", re.compile(r"^\s{0,6}\d+[.)](?=\s)")),
    ("heading_no", re.compile(r"^#{1,6}\s*\d+(?:\.\d+)*(?=\s)|^\s*\d+(?:\.\d+)+[a-z]?(?=[　\s]\S)")),
    # 信賴水準：「95% CI」的 95 是慣例，不是這份分析算出來的
    ("ci_level", re.compile(r"\b(?:90|95|99)\s*%(?=\s*(?:CI|C\.I\.|信賴))")),
    # 百分位慣例：2.5–97.5 百分位、P25/P75、第 25 百分位
    ("percentile_conv", re.compile(
        r"(?:2\.5|97\.5|25|50|75)\s*(?:[–\-~至]\s*(?:2\.5|97\.5|25|50|75))?\s*(?:th\s*)?(?:百分位|percentile|pct)"
        r"|\bP(?:2\.5|97\.5|25|50|75)\b")),
    # 顯著水準與 p 值截斷慣例：「P < 0.05」「P < 0.001」的那個數字是門檻／截斷符號，
    # 不是估計值。留著它只會製造一個永遠無法滿足的紅燈（來源檔存的是 0.0003）。
    ("threshold", re.compile(r"[Pp<≤α]\s*[<≤=]?\s*0?\.(?:0001|001|01|05|1|10|2|20)\b")),
    # 比較門檻：任何緊跟在 < > ≤ ≥ 後面的數字都是設計常數（≥ 3000 pg/mL、pH < 7.2、
    # Python <3.11、LVEF ≥ 45%），不是這份分析算出來的。「=」刻意不算：p = 0.002 是結果。
    ("comparison", re.compile(r"[<>≥≤＜＞]\s*=?\s*\d[\d,]*(?:\.\d+)?\s*%?")),
    # 文字型比較門檻：「低於慣用的 10」「below 1e-14」「超過 400 倍」
    ("comparison_word", re.compile(
        r"(?:below|above|under|over|exceed(?:s|ed|ing)?|less\s+than|more\s+than|at\s+least|at\s+most|"
        r"至少|至多|超過|低於|高於|大於|小於|不到|不足|未滿|不超過)\s*(?:慣用的|the\s+)?\s*"
        r"\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?\s*%?", re.I)),
    # 帶單位的區間是設計用的分箱（1000–2999 pg/mL、age 60–80、追蹤 24–36 個月），不是估計值。
    ("unit_range", re.compile(
        r"\d[\d,]*(?:\.\d+)?\s*[–\-~至]\s*\d[\d,]*(?:\.\d+)?\s*"
        r"(?:pg/mL|ng/mL|ng/L|mg/dL|mmol/L|μmol/L|mmHg|g/m²|g/m2|mL|kg|cm|歲|years?|yrs?|個月|months?|"
        r"分鐘|min|小時|hr|hours?|h|°C|℃|bpm|%)(?![A-Za-z])", re.I)),
    # 公式常數：√(身高cm × 體重kg / 3600)
    ("formula", re.compile(r"(?:√|sqrt)\s*\([^)]*\)")),
    # 驗收 / 文件本身的敘事計數：「約 430 個數值」「28,512 格逐格比對」「1,141 行」
    # 「449 個葉節點」——這些數的是文件與 JSON 的格子，不是病人。
    ("meta_count", re.compile(
        r"\d[\d,]*\s*(?:個\s*|項\s*|條\s*)?(?:數值|葉節點|節點|欄位|格|行版|行|列|處|字面|key|keys|檔案|檔|發現|"
        r"數字型陳述|個值|斷言|測試|test cases?)(?![A-Za-z0-9])")),
]

# 科學記號：2.1×10⁻⁵、5×10^-8、1e-14。要在 MASKS 之前處理，否則會被拆成「2.1」與「10」。
SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
SCI = re.compile(
    r"(\d+(?:\.\d+)?)\s*[×x✕*]\s*10\s*(?:\^|\*\*)?\s*\(?\s*([⁻−\-+]?)\s*([\d⁰¹²³⁴⁵⁶⁷⁸⁹]+)\)?"
    r"|(\d+(?:\.\d+)?)[eE]([-+]?\d+)\b")
SCI_REL_TOL = 0.05

# 帶單位的整數：這類是「數了幾個」的宣稱，即使小於 min_integer 也要查來源。
# 「313 筆」正是靠這條被抓到。刻意不含時間單位（天/月/年/週）與「歲」——
# 那些幾乎都是設計常數（追蹤 12 個月、年齡 ≥ 65 歲），列進來只會製造噪音。
COUNT_UNITS = "筆例人位名項篇個次份組家場者"
COUNT_SUFFIX = re.compile(rf"^[\s*）)」』]*[{COUNT_UNITS}](?![月年日天週])")
COUNT_PREFIX = re.compile(r"(?:[nN]\s*=|共|計|合計|總計)\s*[\s*]*$")
MIN_COUNT_INTEGER = 10          # 個位數的「3 個理由」是散文，不是資料

# 「百分點」：風險差的單位。JSON 幾乎都存比例（0.294），文件寫 29.4 個百分點。
PCT_POINT_SUFFIX = re.compile(r"^\s*(?:個\s*)?(?:百分點|percentage\s+points?|pp\b)")
# 近似詞：「約 430」「近 70」——近似值不是從 JSON 讀出來的精確值，但也不是手打錯值。
APPROX_PREFIX = re.compile(r"(?:約|近|大約|約莫|將近|約為|roughly|approximately|about|circa|~|≈)\s*$", re.I)

# 來源 JSON 的字串欄位超過這個長度就當散文，不當值（理由見 collect_numbers）。
# 120 是實測出來的：某份已通過五輪驗收的報告，設 120 與不設限的
# 誤報數完全一樣（1110 個字面裡都是 1 個），但 0813 AF 的手打錯值 313 只有設限
# 之後才抓得到。
MAX_VALUE_STRING = 120

# 登記簿 / 稽核檔：裡面的數字是被「引用」的，不是被「產生」的。這類檔不進 wide pool，
# 散文欄位也不拿來背書（verification_findings.json 的敘述裡就寫過那個錯的 313）。
REGISTER_FILE = re.compile(r"verification|findings|audit|incident|citation|manifest|stats_index|_lint\b", re.I)

# 一行裡出現這些就當作「這行宣稱有來源」。**宣稱不等於查證**：這種行的數字照樣
# 比對來源池，比不到就報（並標成 claimed_source）。整行跳過是原本的逃生門。
SOURCED_LINE = re.compile(r"\.json\b|來源[:：]|出處[:：]|\bsource[s]?[:：]", re.I)

# `<!-- AUTO -->` … `<!-- /AUTO -->`：由程式寫入的區塊，本來就是從 JSON 讀出來的
# —— 正因為如此，區塊內的數字**一定**在來源池裡找得到；找不到就代表這個區塊
# 早就被手改過或已過期，那正是要抓的東西，所以同樣列入比對而不是跳過。
AUTO_MARK = re.compile(r"<!--\s*(/|END\s+|AUTO:END)?\s*(?:AUTO|自動)\b[^>]*-->", re.I)
AUTO_END = re.compile(r"<!--\s*(?:/\s*(?:AUTO|自動)|END\s+(?:AUTO|自動)|AUTO:END)[^>]*-->", re.I)
FENCE = re.compile(r"^\s*(?:```|~~~)")

# 文獻引用標記。**不豁免，降成 advisory**：印出來、進 JSON、不擋。
#  強標記（整段落適用）：引用括號、PMID、et al.、Author 2026、「作者原值」、Cochrane／系統性回顧。
#    一段落既然在講某篇論文，段落裡的 n = 1,097、aHR 1.53 幾乎都是那篇論文的數字。
#  弱標記（只管同一個子句）：試驗縮寫（PARAGON-HF）、「該研究」「前案」——這些在自己
#    結果的段落裡也會出現，只影響同一子句。
LIT_STRONG_CI = re.compile(
    r"\[\[\d|\[\s*\d{1,3}(?:\s*[,;–-]\s*\d{1,3})*\s*\]"              # [[PMID]]、[12]
    r"|\bPMID\b|\bPMC\d|\bdoi\b|\bet\s+al\b"
    r"|作者原值|作者既有|原著|Cochrane|systematic\s+review|meta-analys[ie]s|系統性回顧|統合分析|隨機試驗|\bRCTs?\b"
    r"|research\s+database|研究資料庫|健保資料庫",
    re.I)
# 人名一定大小寫敏感：re.I 會讓「registry 的」「apixaban 的」也命中（2026-09-03 實測）。
LIT_STRONG_CS = re.compile(
    r"\b[A-Z][a-zà-ž'’]+(?:[A-Z][a-zà-ž]+)?(?:-[A-Z][a-zà-ž]+)?"          # Chang、McMurray、Rodríguez-Muñoz
    r"(?:\s+(?:and|&)\s+[A-Z][a-zà-ž]+)?\s*(?:等人?|et\s+al\.?)?\s*[（(]?\s*(?:19|20)\d{2}[a-z]?\b"   # Chang 2026
    r"|\b[A-Z][a-z]{2,}\s*(?:等人?|用|發現|報告|指出|主張|認為|證明|納入)"      # Nutma 用、Fagard 等人
    r"|\b[A-Z][a-z]{3,}\s*的(?!\s*[a-z])")                                    # Mazzone 的（大小寫敏感，registry 的不算）
LIT_WEAK = re.compile(
    r"\b[A-Z][A-Z0-9]{2,}(?:-[A-Za-z0-9]+)+\b"                       # PARAGON-HF、STEP-HFpEF（大小寫敏感：log-rank 不算）
    r"|\b[A-Z]{4,}\b[^。；;]{0,12}?[（(]\s*n\s*="                     # CGRD（n = 6,092）
    r"|前案|該研究|該試驗|該文|該篇|原文|文獻上|已發表的|發表於|其\s*Table|其\s*Figure"
    r"|\b(?:trial|cohort)\b[^。；;]{0,40}?\bn\s*=")


def lit_strong(text: str) -> bool:
    return bool(LIT_STRONG_CI.search(text) or LIT_STRONG_CS.search(text))


# 明講是別的世代 / 專案的數字。
CROSS_PROJECT = re.compile(r"母世代|母專案|姊妹|第一篇|第二篇|上一篇|前一篇|parent:|sister", re.I)

# 表格：header 有這些字的欄位是識別碼欄，整欄的數字都不是統計量。
ID_HEADER = re.compile(r"編號|病歷號|識別碼|序號|\bID\b|\bno\.?$|\bcode\b|PMID|rsID|\brs\b", re.I)
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}")

# 數字字面本身。逗號千分位、小數、百分比都在這一條裡。
NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(%)?")

SEGMENT_SPLIT = re.compile(r"[。；;]")


def blank(m: re.Match) -> str:
    """把命中的區段換成等量空白，保住欄位位置。"""
    return " " * len(m.group(0))


# ────────────────────────────────────────────────────────────── 文件讀取
def read_docx(path: Path) -> str:
    """讀 .docx 的可見文字。稽核抓到的手打數字就在 docx 裡，不支援等於守不到交付物。

    表格保留列結構：同一列的儲存格用「 | 」接起來成一行，表頭才對得上它底下的欄
    （病人編號欄要靠表頭辨認）。
    """
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")

    def row(m: re.Match) -> str:
        r = m.group(0)
        r = re.sub(r"</w:p>", " ", r)
        r = re.sub(r"</w:tc>", " | ", r)
        return "| " + r + "\n"

    xml = re.sub(r"<w:tr\b.*?</w:tr>", row, xml, flags=re.S)
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/?>", "\t", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return html.unescape(xml)


def read_document(path: Path) -> list[str]:
    if path.suffix.lower() == ".docx":
        return read_docx(path).split("\n")
    return path.read_text(encoding="utf-8", errors="replace").split("\n")


# ────────────────────────────────────────────────────── 來源池（JSON 數值）
class Pool:
    """一組來源檔的數值池 + 散文欄位索引。"""

    def __init__(self) -> None:
        self.values: list[float] = []
        self.origin: dict[float, str] = {}       # 值 → 第一個提供它的檔名
        self.prose: list[tuple[str, str]] = []   # (檔名, 長字串) —— 只用來標 advisory
        self.files: list[str] = []

    def add_file(self, p: Path, label: str, register: bool) -> None:
        sink: list[float] = []
        prose: list[str] = []
        collect_numbers(json.loads(p.read_text(encoding="utf-8")), sink, prose)
        for v in sink:
            self.origin.setdefault(v, label)
        self.values.extend(sink)
        if not register:
            self.prose.extend((label, s) for s in prose)
        self.files.append(label)

    def finalize(self) -> None:
        self.values = sorted(set(self.values))

    def __len__(self) -> int:
        return len(self.values)


def collect_numbers(node, sink: list[float], prose: list[str] | None = None) -> None:
    """把 JSON 裡所有數值收進來 —— 含字串裡的數字。

    stats JSON 常把結果存成已排版的字串（"0.84 (0.71–0.99)"、"1,732 (72.6%)"），
    只收 int/float 會漏掉一大半，然後把文件裡完全有來源的數字報成無來源。
    """
    if isinstance(node, bool) or node is None:
        return
    if isinstance(node, (int, float)):
        # NaN / Infinity 一定要擋掉。json 模組會照收，而只要池子裡混進一個 NaN，
        # sorted() 產生的順序就不再單調，後面的二分搜尋會**靜默**給出錯答案 ——
        # 實測就是這樣：amyloid_stats.json 有 4 個 NaN，害整池 4143 個數值裡連
        # 明明存在的 313 都查不到，把一份有來源的數字報成無來源。
        if math.isfinite(node):
            sink.append(float(node))
        return
    if isinstance(node, str):
        # 只挖**短的、像值的**字串。長字串是散文（驗收發現的敘述、備註、TODO），
        # 裡面的數字是被「引用」而不是被「產生」的，拿它當來源等於讓錯值自我背書：
        # 實測 0813 AF 的 verification_findings.json 有一條發現在敘述裡寫了
        # 「313 筆檢索結果」，而報告手打的錯值剛好也是 313 —— 不設這道界線，
        # 這支工具就會放行它要抓的那一個數字。長字串只留給 advisory 分類用。
        if len(node) > MAX_VALUE_STRING:
            if prose is not None:
                prose.append(node)
            return
        for m in re.finditer(r"-?\d+(?:\.\d+)?", node.replace(",", "")):
            try:
                v = float(m.group(0))
            except ValueError:
                continue
            if math.isfinite(v):
                sink.append(v)
        return
    if isinstance(node, dict):
        for k, v in node.items():
            collect_numbers(k, sink, prose)
            collect_numbers(v, sink, prose)
        return
    if isinstance(node, list):
        for v in node:
            collect_numbers(v, sink, prose)


def in_pool(pool: list[float], target: float, tol: float) -> float | None:
    """排序後二分搜尋：來源池動輒十萬個數，逐一比對會慢到沒人想跑。回傳命中的值。"""
    lo = bisect.bisect_left(pool, target - tol)
    if lo < len(pool) and pool[lo] <= target + tol:
        return pool[lo]
    return None


# ─────────────────────────────────────────────────────────── 表格處理
def table_id_columns(lines: list[str]) -> dict[int, list[int]]:
    """回傳 {行號(1-based): [識別碼欄的 index]}：markdown / docx 表格裡，表頭寫著
    「病人編號」「PMID」「ID」的那一欄，整欄都是識別碼。"""
    out: dict[int, list[int]] = {}
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].count("|") < 2:
            i += 1
            continue
        header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        id_cols = [j for j, c in enumerate(header) if ID_HEADER.search(c)]
        j = i + 1
        while j < n and lines[j].count("|") >= 2:
            if id_cols and not TABLE_SEP.match(lines[j]):
                out[j + 1] = id_cols
            j += 1
        i = j
    return out


def blank_cells(line: str, cols: list[int]) -> str:
    """把指定欄位的內容換成等量空白。"""
    stripped = line.strip()
    lead = len(line) - len(line.lstrip())
    body = stripped[1:] if stripped.startswith("|") else stripped
    offset = lead + (1 if stripped.startswith("|") else 0)
    parts = body.split("|")
    pos = offset
    chars = list(line)
    for j, part in enumerate(parts):
        if j in cols:
            for k in range(pos, pos + len(part)):
                if k < len(chars):
                    chars[k] = " "
        pos += len(part) + 1
    return "".join(chars)


# ─────────────────────────────────────────────────────────── 數字擷取
def mask_line(line: str, extra: list[re.Pattern]) -> tuple[str, dict[str, int]]:
    hits: dict[str, int] = {}
    for name, pat in MASKS:
        line, n = pat.subn(blank, line)
        if n:
            hits[name] = hits.get(name, 0) + n
    for pat in extra:
        line, n = pat.subn(blank, line)
        if n:
            hits["custom"] = hits.get("custom", 0) + n
    return line, hits


def looks_like_claim(raw: str, pct: bool, tail: str, head: str,
                     min_integer: int) -> str | None:
    """回傳這個字面被檢查的理由；不該檢查就回 None。"""
    if pct:
        return "percent"
    if "." in raw:
        return "decimal"
    if "," in raw:
        return "count"                      # 有千分位的一定是數量
    value = int(raw)
    if value >= min_integer:
        return "count"                      # 大於三位數的整數
    if value >= MIN_COUNT_INTEGER and (COUNT_SUFFIX.match(tail) or COUNT_PREFIX.search(head)):
        return "count"                      # 「313 筆」「n = 96」
    return None


OPEN_BR, CLOSE_BR = "（([「『【", "）)]」』】"


def segment_flags(raw_line: str) -> list[tuple[int, int, bool]]:
    """把一行切成子句，回傳 (start, end, 是否帶文獻引用標記)。

    括號內的 ；不切（「（竇性 1.86, p = 0.01；AF 1.71, p = 0.01）」是同一個子句）；
    表格列整列算一個子句（列首是論文名，整列都是那篇論文的數字）。
    強標記整行生效，弱標記只管自己的子句。
    """
    strong = lit_strong(raw_line)
    if raw_line.count("|") >= 2:
        return [(0, len(raw_line), strong or bool(LIT_WEAK.search(raw_line)))]
    out = []
    start = depth = 0
    for i, ch in enumerate(raw_line):
        if ch in OPEN_BR:
            depth += 1
        elif ch in CLOSE_BR:
            depth = max(0, depth - 1)
        elif ch in "。；;" and depth == 0:
            seg = raw_line[start:i + 1]
            out.append((start, i + 1, strong or bool(LIT_WEAK.search(seg))))
            start = i + 1
    seg = raw_line[start:]
    out.append((start, len(raw_line), strong or bool(LIT_WEAK.search(seg))))
    return out


def sci_items(line: str, i: int, raw_line: str) -> tuple[str, list[dict], int]:
    """先把科學記號抽成獨立字面，再把它從行裡遮掉。回傳 (遮掉後的行, items, 門檻數)。"""
    items: list[dict] = []
    thresholds = 0

    def repl(m: re.Match) -> str:
        nonlocal thresholds
        head = line[max(0, m.start() - 12):m.start()]
        if re.search(r"(?:[<>≥≤＜＞]\s*=?|below|above|under|over|低於|高於|大於|小於|超過)\s*(?:the\s+)?$", head, re.I):
            thresholds += 1
            return blank(m)
        if m.group(1) is not None:
            mant = float(m.group(1))
            sign = -1 if m.group(2) in ("⁻", "−", "-") else 1
            exp = int(m.group(3).translate(SUPERSCRIPT))
        else:
            mant = float(m.group(4))
            sign, exp = 1, int(m.group(5))
        items.append({"text": m.group(0).strip(), "value": mant * (10.0 ** (sign * exp)),
                      "decimals": 0, "percent": False, "kind": "sci",
                      "start": m.start()})
        return blank(m)

    line = SCI.sub(repl, line)
    return line, items, thresholds


def scan_document(lines: list[str], min_integer: int,
                  extra: list[re.Pattern]) -> tuple[list[dict], dict[str, int], int]:
    """回傳 (候選數字, 豁免統計, 宣稱有來源的行數)。"""
    found: list[dict] = []
    masked_tally: dict[str, int] = {}
    claimed_lines = 0
    in_fence = False
    in_auto = False
    id_cols = table_id_columns(lines)
    for i, raw_line in enumerate(lines, 1):
        if FENCE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # 以下三種是「宣稱有來源」，不是「不是統計量」：照樣比對，只是另外記號。
        claimed = False
        if AUTO_MARK.search(raw_line):
            in_auto = not AUTO_END.search(raw_line)
            claimed = True
        elif in_auto or SOURCED_LINE.search(raw_line):
            claimed = True
        if claimed:
            claimed_lines += 1
        line = raw_line
        if i in id_cols:
            before = line
            line = blank_cells(line, id_cols[i])
            if before != line:
                masked_tally["id_column"] = masked_tally.get("id_column", 0) + 1
        line, sci, thr = sci_items(line, i, raw_line)
        if thr:
            masked_tally["comparison"] = masked_tally.get("comparison", 0) + thr
        line, hits = mask_line(line, extra)
        for k, v in hits.items():
            masked_tally[k] = masked_tally.get(k, 0) + v
        segs = segment_flags(raw_line)
        cross = bool(CROSS_PROJECT.search(raw_line))

        def annotate(item: dict, start: int, end: int | None = None) -> dict:
            lit = next((flag for s, e, flag in segs if s <= start < e), False)
            end = start + len(item["text"]) if end is None else end
            item.update({
                "ctx_before": raw_line[max(0, start - 6):start],
                "ctx_after": raw_line[end:end + 6],
                "line": i,
                "claimed_source": claimed,
                "literature_context": lit,
                "cross_project": cross,
                "context": raw_line.strip()[:160],
            })
            return item

        for s in sci:
            s["approx"] = False
            s["pct_points"] = False
            found.append(annotate(s, s.pop("start")))
        for m in NUMBER.finditer(line):
            raw, pct = m.group(1), bool(m.group(2))
            tail = line[m.end():m.end() + 8]
            head = line[max(0, m.start() - 12):m.start()]
            reason = looks_like_claim(raw, pct, tail, head, min_integer)
            if reason is None:
                masked_tally["not_a_claim"] = masked_tally.get("not_a_claim", 0) + 1
                continue
            text = raw + ("%" if pct else "")
            decimals = len(raw.split(".")[1]) if "." in raw else 0
            found.append(annotate({
                "text": text,
                "value": float(raw.replace(",", "")),
                "decimals": decimals,
                "percent": pct,
                "pct_points": bool(PCT_POINT_SUFFIX.match(tail)),
                "approx": bool(APPROX_PREFIX.search(head)),
                "kind": reason,
            }, m.start(), m.end()))
    return found, masked_tally, claimed_lines


def lookup(item: dict, pool: Pool, allow_scale: bool = True) -> tuple[str, float] | None:
    """數值容差比對。回傳 (matched_via, 命中的值) 或 None。容差由**文件自己寫了幾位小數**決定。

    allow_scale=False 時不做百分比↔比例縮放：宣告範圍外的 wide pool 只准精確比對。
    縮放會把撞號機率再拉高一截（0813 AF 手算的 27.4% 在另一個 stats 檔裡剛好有個
    0.274），宣告範圍內的池子小、縮放是必要的（表格裡沒帶 % 的 71.2）；範圍外就免了。"""
    x = item["value"]
    if item["kind"] == "sci":
        tol = abs(x) * SCI_REL_TOL
        for c in (x, -x):
            hit = in_pool(pool.values, c, tol)
            if hit is not None:
                return ("exact", hit)
        return None
    tol = 0.5 * (10 ** -item["decimals"]) + 1e-9
    candidates: list[tuple[float, float, str]] = [(x, tol, "exact"), (-x, tol, "exact")]
    if not allow_scale:
        pass
    elif item["percent"] or item["pct_points"]:
        # 來源可能存成比例（0.274）也可能存成百分比（27.4）
        candidates += [(x / 100.0, tol / 100.0, "percent_scaled"), (-x / 100.0, tol / 100.0, "percent_scaled")]
    elif item["kind"] == "decimal" and 0 < x <= 100:
        # 表格裡沒帶 % 的 71.2、文中的 29.4（個百分點漏寫）：JSON 存 0.712 / 0.294。
        # 標 percent_scaled 讓人看得出這一筆是靠縮放才配對到的。
        candidates += [(x / 100.0, tol / 100.0, "percent_scaled"), (-x / 100.0, tol / 100.0, "percent_scaled")]
    for c, t, via in candidates:
        hit = in_pool(pool.values, c, t)
        if hit is not None:
            return (via, hit)
    return None


def specific_enough(item: dict) -> bool:
    """小整數（313、683）在幾千個數的池子裡撞號機率太高，不准靠宣告範圍外的檔或散文
    欄位「救回來」——只有夠特定的值（百分比、小數、帶千分位的整數、科學記號）才可以。
    0813 AF 的手打錯值 313 在 analysis/data 的另一個 stats 檔裡剛好有一個 n = 313：
    沒有這條規則，這支工具就會把它要抓的那個數字降成 advisory。"""
    if item["kind"] in ("percent", "sci"):
        return True
    if item["kind"] == "decimal":
        return True
    return "," in item["text"] or item["value"] >= 1000


def _norm(s: str) -> str:
    return re.sub(r"[\s,*_`（）()「」]", "", s)


def prose_hit(item: dict, pool: Pool) -> str | None:
    """數字只出現在來源檔的長字串（散文）裡：回傳檔名。

    小整數要連同前後文一起對得上（「n=669，死亡率」在文件與 JSON 散文裡都出現）才算，
    這代表那句話是從 JSON 逐字抄過來的；夠特定的值直接比對數字本身。"""
    if item["kind"] == "sci":
        return None
    needle = item["text"].rstrip("%").replace(",", "")
    if specific_enough(item):
        pat = re.compile(r"(?<![\d.])" + re.escape(needle) + r"(?![\d.])")
        for label, text in pool.prose:
            if pat.search(text.replace(",", "")):
                return label
        return None
    ctx = _norm(item.get("ctx_before", "")) + needle + _norm(item.get("ctx_after", ""))
    if len(ctx) < len(needle) + 4:
        return None
    for label, text in pool.prose:
        if ctx in _norm(text):
            return label
    return None


def classify(item: dict, declared: Pool, wide: Pool) -> dict:
    """決定這個字面的下場：sourced / advisory / blocking，並記下理由。"""
    hit = lookup(item, declared)
    if hit:
        via, val = hit
        return {"status": "sourced", "matched_via": via, "found_in": declared.origin.get(val)}
    hint: dict = {}
    hit = lookup(item, wide, allow_scale=False)
    if hit:
        via, val = hit
        if specific_enough(item):
            return {"status": "advisory", "reason": "found_outside_declared",
                    "matched_via": via, "found_in": wide.origin.get(val)}
        # 小整數：撞號機率太高，不降級，只附提示
        hint = {"hint_found_in": wide.origin.get(val)}
    src = prose_hit(item, declared) or prose_hit(item, wide)
    if src:
        return {"status": "advisory", "reason": "prose_in_source", "found_in": src}
    if item["literature_context"]:
        return {"status": "advisory", "reason": "literature"}
    if item["cross_project"]:
        return {"status": "advisory", "reason": "cross_project"}
    if item["approx"]:
        return {"status": "advisory", "reason": "approx"}
    return {"status": "blocking", **hint}


REASON_LABEL = {
    "found_outside_declared": "在宣告範圍外的 stats 檔找得到（補進 sources 就變 sourced）",
    "prose_in_source": "只出現在來源檔的散文欄位，不是數值葉節點",
    "literature": "同一子句帶文獻引用標記（別人論文的數字）",
    "cross_project": "行內明講是母世代／姊妹專案的數字",
    "approx": "帶「約／近」的近似值",
}


# ─────────────────────────────────────────────────────────── 設定解析
def parse_documents(spec) -> tuple[list[tuple[str, list[str] | None]], list[str]]:
    """沿用 C5 的 document 語意：字串 / 字串清單 / {path, sources} 清單，可混用。"""
    items = spec if isinstance(spec, list) else [spec]
    out: list[tuple[str, list[str] | None]] = []
    bad: list[str] = []
    for d in items:
        if not d:
            continue
        if isinstance(d, dict):
            path_val = d.get("path")
            if not path_val:
                bad.append(repr(d))
                continue
            src = d.get("sources")
            out.append((str(path_val), [str(s) for s in src] if src is not None else None))
        else:
            out.append((str(d), None))
    return out, bad


def resolve_source(name: str, root: Path, data_dir: Path) -> Path | None:
    """來源檔名的解析順序：帶路徑的照路徑走，純檔名走 data_dir → 專案根 → 全樹搜尋。"""
    if "/" in name:
        p = (root / name).resolve()
        return p if p.exists() else None
    for cand in (data_dir / name, root / name):
        if cand.exists():
            return cand
    hits = sorted(root.rglob(name))
    return hits[0] if hits else None


def audit_files(stats_index: Path | None) -> set[str]:
    if not (stats_index and stats_index.exists()):
        return set()
    try:
        files = json.loads(stats_index.read_text(encoding="utf-8")).get("files", {})
    except (json.JSONDecodeError, UnicodeDecodeError):
        return set()
    return {n for n, meta in files.items() if meta.get("稽核檔") or meta.get("audit_only")}


def default_sources(root: Path, data_dir: Path, stats_index: Path | None) -> tuple[list[str], str]:
    """文件沒宣告 sources 時的退路，語意與 C5 一致：拿全部 stats 檔比。"""
    if stats_index and stats_index.exists():
        files = json.loads(stats_index.read_text(encoding="utf-8")).get("files", {})
        names = [n for n, meta in sorted(files.items())
                 if str(meta.get("產生者") or meta.get("generated_by") or "").endswith(".py")
                 # stats_index 也登記 .py 產生的 .csv，那些不是 JSON，讀了會炸成 exit 2
                 # （therapy choice EDA 就是因此才要手動明列 sources）。（2026-09-04）
                 and n.endswith(".json")
                 and not (meta.get("稽核檔") or meta.get("audit_only"))]
        if names:
            return names, "stats_index"
    if data_dir.exists():
        return sorted(p.name for p in data_dir.glob("*.json")), "data_dir 全部 *.json"
    return [], "（找不到任何來源）"


def is_register(p: Path, audits: set[str]) -> bool:
    return p.name in audits or bool(REGISTER_FILE.search(p.name))


def rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


# ────────────────────────────────────────────────────────────────── main
USAGE = """用法：lint_bare_numbers.py [PROJECT_DIR] [--config PATH] [--json PATH]
                            [--mode strict|lenient | --strict | --lenient]
                            [--max-list N] [--quiet]

裸數字 lint（看門狗 C8 的判斷邏輯，也可單獨跑）：交付物裡印出來的每個數字，
在它自己宣告的 stats 來源裡找不找得到。抓的是手打值與漏宣告來源。

  PROJECT_DIR   專案根目錄（放 research-checks.yaml 的那層）；省略時用目前目錄
  --config PATH 指定設定檔（預設 PROJECT_DIR/research-checks.yaml）
  --json PATH   把結果整份寫成 JSON
  --strict / --lenient / --mode  嚴格度；預設讀設定檔
  --max-list N  最多列出幾筆（預設 25）
  --quiet       只印結論

設定寫在 research-checks.yaml 的 C8_bare_numbers：逐份文件宣告 document[].sources，
不要讓它拿全部 stats 檔當池子（池子越寬越容易撞號）。

退出碼： 0 = 通過 ／ 1 = 有對不到來源的數字 ／ 2 = 跑不起來（沒設定檔、
        沒有 C8_bare_numbers 設定）——2 不是通過。
"""


def main() -> int:
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    quiet = "--quiet" in argv
    max_list = 25
    cfg_override = json_override = mode_override = None
    for flag, setter in (("--config", "cfg"), ("--json", "json"), ("--max-list", "max"), ("--mode", "mode")):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                print(f"✗ {flag} 後面要接一個值")
                return 2
            val = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
            if setter == "cfg":
                cfg_override = val
            elif setter == "json":
                json_override = val
            elif setter == "mode":
                mode_override = val
            else:
                max_list = int(val)
    if "--strict" in argv:
        mode_override = "strict"
    if "--lenient" in argv:
        mode_override = "lenient"
    args = [a for a in argv if not a.startswith("-")]
    root = Path(args[0]).resolve() if args else Path.cwd()

    def say(msg: str = "") -> None:
        if not quiet:
            print(msg)

    cfg_path = Path(cfg_override).resolve() if cfg_override else root / CONFIG_NAME
    if not cfg_path.exists():
        print(f"✗ 找不到 {cfg_path} —— 這個專案的裸數字 lint 未受保護。")
        print("  （未設定不等於通過。沒有設定就沒有任何保證。）")
        return 2

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    checks = cfg.get("checks", {}) or {}
    c = checks.get(CHECK_KEY)
    if c in (None, False):
        print(f"✗ {cfg_path} 沒有 {CHECK_KEY} 設定 —— 沒有宣告要掃哪些文件，無法檢查。")
        print(f"  在 checks: 底下加 {CHECK_KEY}:，document 寫法與 C5 相同。")
        return 2
    c = c if isinstance(c, dict) else {}

    c5 = checks.get("C5_document_vs_stats") or {}
    c1 = checks.get("C1_stats_freshness") or {}
    doc_spec = c.get("document", c5.get("document") if isinstance(c5, dict) else None)
    if not doc_spec:
        print(f"✗ {CHECK_KEY} 沒有 document（也沒有可沿用的 C5 document）——"
              " 沒有要掃的文件，這不是通過。")
        return 2

    docs, bad_spec = parse_documents(doc_spec)
    if bad_spec:
        print(f"✗ document 的對照式寫法缺少 path：{'、'.join(bad_spec)}")
        return 2
    if not docs:
        print(f"✗ {CHECK_KEY} 的 document 解析後是空的 —— 沒有要掃的文件。")
        return 2

    mode = str(mode_override or c.get("mode") or DEFAULT_MODE).lower()
    if mode not in ("lenient", "strict"):
        print(f"✗ mode 只能是 lenient 或 strict，收到：{mode}")
        return 2
    data_dir = root / (c.get("data_dir") or c5.get("data_dir") or c1.get("data_dir") or ".")
    si_rel = c.get("stats_index") or c5.get("stats_index") or c1.get("stats_index")
    stats_index = (root / si_rel) if si_rel else None
    audits = audit_files(stats_index)
    min_integer = int(c.get("min_integer", DEFAULT_MIN_INTEGER))
    extra = [re.compile(p) for p in (c.get("ignore_patterns") or [])]
    extra_sources = [str(s) for s in (c.get("extra_sources") or [])]

    # 缺文件 / 缺來源檔 = 檢查做不到，不是通過 → exit 2
    blockers: list[str] = []
    for name, _ in docs:
        if not (root / name).exists():
            blockers.append(f"要掃的文件不存在：{name}")
    extra_resolved: list[Path] = []
    for s in extra_sources:
        hit = resolve_source(s, root, data_dir)
        (extra_resolved.append(hit) if hit else blockers.append(f"extra_sources 找不到：{s}"))

    say(f"專案：{cfg.get('project', root.name)}    ({root})")
    say(f"設定：{cfg_path}    模式：{mode}")
    say("=" * 78)

    wide_cache: dict[Path, Pool] = {}

    def wide_pool(resolved: list[Path]) -> Pool:
        """宣告範圍外的其他 stats 檔：data_dir + 每個宣告來源所在目錄的全部 *.json，
        登記簿 / 稽核檔除外。只用來把「找得到但沒宣告」降成 advisory。"""
        dirs = {data_dir.resolve()} | {p.parent.resolve() for p in resolved}
        key = Path("|".join(sorted(str(d) for d in dirs)))
        if key in wide_cache:
            return wide_cache[key]
        pool = Pool()
        declared_set = {p.resolve() for p in resolved}
        for d in sorted(dirs):
            if not d.exists():
                continue
            for p in sorted(d.glob("*.json")):
                if p.resolve() in declared_set or is_register(p, audits):
                    continue
                try:
                    pool.add_file(p, rel(p, root), register=False)
                except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                    continue
        pool.finalize()
        wide_cache[key] = pool
        return pool

    results: list[dict] = []
    total_checked = total_blocking = total_advisory = 0
    total_masked: dict[str, int] = {}
    advisory_reasons: dict[str, int] = {}
    for name, declared in docs:
        path = root / name
        if not path.exists():
            continue
        if declared is None:
            names, mode_src = default_sources(root, data_dir, stats_index)
        else:
            names, mode_src = declared, "宣告"
        resolved, missing = [], []
        for s in names:
            hit = resolve_source(s, root, data_dir)
            (resolved.append(hit) if hit else missing.append(s))
        if missing:
            blockers.append(f"{name} 宣告的來源檔找不到：{'、'.join(missing)}")
            continue
        resolved += [p for p in extra_resolved if p not in resolved]
        if not resolved:
            blockers.append(f"{name} 沒有任何可比對的來源檔（mode={mode_src}）")
            continue
        pool = Pool()
        try:
            for p in resolved:
                pool.add_file(p, rel(p, root), register=is_register(p, audits))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            blockers.append(f"{name} 的來源檔無法解析：{e}")
            continue
        pool.finalize()
        wide = wide_pool(resolved)

        # 讀不開的文件 = 這份沒被掃到 = 檢查做不到（exit 2），不是「有無來源數字」
        # （exit 1）。原本沒包 try/except：一份壞 docx 會 traceback 收在 rc=1，看門狗
        # 把它翻譯成「交付物裡有數字找不到來源」，診斷完全錯；而且崩在寫報告之前，
        # 磁碟上留著上一輪的舊 JSON，清單裡排在壞檔後面的文件也全部沒掃到。
        try:
            lines = read_document(path)
        except Exception as e:                       # noqa: BLE001 —— 壞檔的花樣太多
            blockers.append(f"{name} 讀檔失敗（{type(e).__name__}: {e}）")
            say(f"  ✗ {name}")
            say(f"      讀檔失敗，這份沒有被掃到：{type(e).__name__}: {e}")
            continue

        items, masked, claimed_lines = scan_document(lines, min_integer, extra)
        blocking: list[dict] = []
        advisory: list[dict] = []
        scaled = 0
        for x in items:
            verdict = classify(x, pool, wide)
            x.update(verdict)
            if verdict["status"] == "sourced":
                if verdict.get("matched_via") == "percent_scaled":
                    scaled += 1
            elif verdict["status"] == "advisory":
                advisory.append(x)
                advisory_reasons[verdict["reason"]] = advisory_reasons.get(verdict["reason"], 0) + 1
            else:
                blocking.append(x)
        for k, v in masked.items():
            total_masked[k] = total_masked.get(k, 0) + v
        total_checked += len(items)
        total_blocking += len(blocking)
        total_advisory += len(advisory)

        def export(x: dict) -> dict:
            return {k: v for k, v in x.items()
                    if k not in ("decimals", "pct_points", "approx", "cross_project", "ctx_before", "ctx_after")}

        results.append({
            "path": name,
            "source_mode": mode_src,
            "sources": pool.files,
            "pool_size": len(pool),
            "wide_pool_files": len(wide.files),
            "claimed_source_lines": claimed_lines,
            "numbers_checked": len(items),
            "sourced_via_percent_scaling": scaled,
            "unsourced_count": len(blocking) + len(advisory),
            "blocking_count": len(blocking),
            "advisory_count": len(advisory),
            "unsourced_claiming_source": sum(1 for x in blocking + advisory if x["claimed_source"]),
            "unsourced": [export(x) for x in blocking],
            "advisory": [export(x) for x in advisory],
        })
        fails = blocking if mode == "lenient" else blocking + advisory
        mark = "✗" if fails else ("△" if advisory else "✓")
        say(f"  {mark} {name}")
        say(f"      來源 {len(pool.files)} 檔（{mode_src}）／池 {len(pool)} 個數值／"
            f"查了 {len(items)} 個字面／其中 {claimed_lines} 行自稱有來源（照樣比對）／"
            f"blocking {len(blocking)}、advisory {len(advisory)}")
        for x in blocking[:max_list]:
            flag = "  ← 這行自稱有來源" if x["claimed_source"] else ""
            if x.get("hint_found_in"):
                flag += f"  （{x['hint_found_in']} 有同值，可能撞號、也可能是漏宣告的來源）"
            say(f"        L{x['line']:<5d} {x['text']:<12s} {x['context'][:88]}{flag}")
        if len(blocking) > max_list:
            say(f"        …… 另有 {len(blocking) - max_list} 個 blocking，完整清單見 JSON")
        if advisory:
            say(f"      advisory（{'不擋' if mode == 'lenient' else 'strict 下一樣擋'}）：")
            for x in advisory[:max_list]:
                where = f" → {x['found_in']}" if x.get("found_in") else ""
                say(f"        L{x['line']:<5d} {x['text']:<12s} [{x['reason']}{where}] {x['context'][:70]}")
            if len(advisory) > max_list:
                say(f"        …… 另有 {len(advisory) - max_list} 個 advisory，完整清單見 JSON")

    report = {
        "tool": "lint_bare_numbers",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "project": cfg.get("project", root.name),
        "config": str(cfg_path),
        "mode": mode,
        "summary": {
            "documents_scanned": len(results),
            "numbers_checked": total_checked,
            "unsourced": total_blocking + total_advisory,
            "blocking": total_blocking,
            "advisory": total_advisory,
            "advisory_by_reason": advisory_reasons,
            "exempted": total_masked,
            "blockers": blockers,
        },
        "documents": results,
    }
    out_rel = json_override or c.get("report") or DEFAULT_REPORT
    out_path = Path(out_rel) if Path(out_rel).is_absolute() else root / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    say("")
    say("=" * 78)
    say(f"報告：{out_path}")
    if blockers:
        print(f"✗ 檢查無法完成（{len(blockers)} 項）：")
        for b in blockers:
            print("  •", b)
        print("  缺文件或缺來源檔不等於通過 —— 補齊後重跑。")
        return 2
    failing = total_blocking if mode == "lenient" else total_blocking + total_advisory
    exempt = sum(v for k, v in total_masked.items() if k != "not_a_claim")
    claimed_total = sum(r["claimed_source_lines"] for r in results)
    adv_txt = "、".join(f"{REASON_LABEL.get(k, k).split('（')[0]} {v}" for k, v in sorted(advisory_reasons.items()))
    if failing:
        claiming = sum(r["unsourced_claiming_source"] for r in results)
        print(f"✗ {failing} 個數字在宣告的來源裡找不到（共查 {total_checked} 個字面，"
              f"{len(results)} 份文件；blocking {total_blocking}、advisory {total_advisory}，模式 {mode}）。")
        print("  每一個要嘛改成從 JSON 讀出來，要嘛在該行標明來源，要嘛就是手打錯值。")
        if claiming:
            print(f"  其中 {claiming} 個所在的行**自稱有來源**（提到 .json／寫了「來源：」／"
                  "在 AUTO 區塊內）卻在來源池裡找不到 —— 標了來源不等於來源真有這個值。")
        if advisory_reasons:
            print(f"  advisory 分類：{adv_txt}")
        return 1
    print(f"✓ 全部通過（{mode}）：{len(results)} 份文件、{total_checked} 個數字字面，"
          f"blocking 0、advisory {total_advisory}"
          f"（含 {claimed_total} 行自稱有來源的，也實際比對過）")
    print(f"  掃過：{'、'.join(r['path'] for r in results)}")
    print(f"  豁免：{exempt} 個編號／識別碼字面"
          f"（{'、'.join(f'{k} {v}' for k, v in sorted(total_masked.items()) if k != 'not_a_claim')}）"
          f"；另有 {total_masked.get('not_a_claim', 0)} 個小整數不屬於數量宣稱")
    if advisory_reasons:
        print(f"  advisory（不擋，逐筆在 JSON）：{adv_txt}")
    skipped_docs = [n for n, _ in docs if not (root / n).exists()]
    print(f"  跳過：{'、'.join(skipped_docs) if skipped_docs else '無'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

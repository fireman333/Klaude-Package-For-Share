# Delivery Discipline — 數字型研究的交付紀律

**這份是規則本體。** 本 skill 在**任何資料夾**都帶著這一套紀律。

**適用**：任何會交出「數字」的研究產物 —— 本 skill 跑出來的 pipeline、手工編號腳本的統計專案、一次性資料抽取與查表（PheWAS、健保資料庫撈數）。
**不適用**：lit review 與 meta-analysis 的流程本身（有自己的流程），但 §7 的三條仍然適用於它們的產物。

工具分兩處，**不是全部在 `assets/`**：看門狗、三支 lint 與範本在 `${CLAUDE_SKILL_DIR}/assets/`（下表）；規則 3 要人自己跑的 `check_numbers_sourced.py` 與 `estimate_inventory.py` 在 **`${CLAUDE_SKILL_DIR}/scripts/`**（見 §規則 3）。照 `assets/` 去找那兩支會找不到，然後就會退回 LLM 逐格比對——本檔下面自己說那是「這一層最純粹的浪費」。

| 路徑 | 是什麼 |
|---|---|
| `assets/check_freshness.py` | 腐爛看門狗，**C1–C10 十項**檢查。**canonical 版本**，所有專案共用一份。C8／C9／C10 的判斷邏輯委派給下面三支 lint |
| `assets/lint_bare_numbers.py` | **C8** 的判斷邏輯（規則 1 的閘）：交付物裡印出來的數字，在它宣告的 stats 來源裡找不找得到。也可單獨跑 |
| `assets/lint_absolute_claims.py` | **C9** 的判斷邏輯（規則 5 的閘）：絕對句有沒有帶資料庫／檢索日期／命中筆數。吃路徑參數，可單獨掃 |
| `assets/reconcile_prisma.py` | **C10** 的判斷邏輯：稿件宣稱的 PRISMA 整數 vs 磁碟上的篩選／全文／抽取檔。吃 MA 專案根目錄 |
| `assets/templates/research-checks.yaml` | 看門狗設定範本（放專案根目錄） |
| `assets/templates/PROJECT_STATE.yaml` | 專案現況的**人工維護**筆記。**零程式 reader**——它記的是別處沒有的東西（`environment` 的 python 版本／platform／lockfile／各腳本 seed、`last_full_run`、`verification.caveats`、`open_items`、交付前檢查清單），所以留著；但它的新鮮度**只靠人**，看門狗不會替你查 |
| `assets/templates/decision_log_skeleton.md` | 決策紀錄骨架，含永久 ID／狀態欄／§H 變更控制 |
| `assets/templates/verification_findings.json` | 驗收發現登記簿的 schema |
| `assets/templates/project_CLAUDE.md` | 專案級 CLAUDE.md 骨架 |
| `assets/templates/gitignore-medical` | 醫療研究專案的 `.gitignore` 起點 |


---

## 1. 六條硬規則

### 規則 1 — 數字單一來源

報告裡每個數字都從**程式產生的檔**（`*_stats.json` / `*.csv`）讀出，**不手打、不憑印象**。維護 `stats_index.json` 記錄「哪個數字在哪個檔的哪個 key」。

> **任何輸出檔裡都沒有的數字，就不該出現在報告裡。** 要用就先加進 pipeline 再重跑。

文件產生腳本要**讀** stats 檔填空，不要在 markdown 裡手寫數值——手打的數字一定會在重跑後 drift。

### 規則 2 — 決策用永久 ID + 狀態

決策紀錄每一列有**不重用、不重排**的 ID（`A1`、`B5`、`C3`…）與狀態欄：

| 狀態 | 意思 |
|---|---|
| `active` | 現行有效，報告的數字來自它 |
| `superseded` | 已被取代 —— 方法欄前面加 `~~已取代 → 見 <新 ID>~~` |
| `withdrawn` | 記錄過但從未採用（例如老師否決） |

老師或 reviewer 要改 → 標 `superseded`、**開新 ID**、補變更紀錄、重跑受影響腳本、跑看門狗。**永不覆寫既有列。** 完整五步流程見 `assets/templates/decision_log_skeleton.md` §H。

> ⚠️ **決策表要加新欄位一律插在最後一欄之前** —— 看門狗 C2 解析每列的最後一欄取腳本指標。

### 規則 3 — 驗收不自驗，且要查涵蓋範圍不只查數值

派**未參與原分析**的 fresh-context agent，一節一隻，彼此不通訊。

**什麼時候做**：分析結果要寫進 manuscript、交給指導教授 / reviewer / 共同作者之前。純自己看的中途結果可以跳過。

**這一步跟 `biostats-guardian`（pipeline 的 Step 4.5 / 6.5）不重複。** Guardian 稽核的是「設定對不對、程式跑得對不對、結果數值合不合理」；這一步稽核的是「**報告呈現的東西，跟實際跑出來的東西，涵蓋範圍一不一樣**」。

**怎麼派**：

1. 派**未參與原分析**的 fresh-context agent，**一節一隻**，彼此不通訊（互相看得到就會互相說服）。
2. 每隻的驗收條件 = 逐格核對該節數值 **＋ 下面〈驗收者的三題〉**。
3. 報告中出現、但 `<OUTPUT_DIR>` 任何輸出檔都找不到的數字 → 要求驗收者**自行重算並附程式片段**。找不到來源的數字就是不該存在的數字。

### 先跑腳本，再派人 —— 逐格核對已經不是 LLM 的工作

| 做什麼 | 誰做 |
|---|---|
| 「報告裡這個數字對得到哪個輸出檔的哪一格嗎」 | **`${CLAUDE_SKILL_DIR}/scripts/check_numbers_sourced.py`**，`0` 全部有來源／`1` 有 unsourced／`2` 跑不起來 |
| 「跑出來的估計有哪些沒出現在交付物裡」 | **`${CLAUDE_SKILL_DIR}/scripts/estimate_inventory.py`** → `coverage_diff.json`，餵 C7 |
| 上面兩份清單**代表什麼** | **LLM / 人** |

> **腳本把「543 個數字要逐格比對」縮成「這 12 個對不到來源、這 8 個跑了沒報」。** 派 agent 去重做集合運算是這一層最純粹的浪費，而且比腳本更容易漏。
>
> ⚠ **`unsourced` 與 `omitted` 都是給人讀的清單，不是判決。** 一個 unsourced 數字可能是合法的手算（兩個數字相減），一個 omitted 估計可能有正當的版面取捨理由——**腳本分不出來**。它們的價值是把注意力精準地放到該看的地方。

#### 報告裡的數字要對得到來源 —— `check_numbers_sourced.py`

逐格核對數值這件事**不要再靠人眼或 LLM**。交付前跑：

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/check_numbers_sourced.py <報告檔...> --output-dir <OUTPUT_DIR>
```

它把 `<OUTPUT_DIR>` 所有 workbook 的數字建成索引，再掃報告裡出現的每個數字，分成 `sourced` / `unsourced` / `structural`（表格編號、頁碼之類），寫出 `numbers_sourced_report.json`。

| exit | 意思 |
|---|---|
| `0` | 每個數字都對得到來源 |
| `1` | 有 `unsourced`，發 `[QC_WARNING] SOURCE:` |
| `2` | 跑不起來（沒給報告檔、`--output-dir` 不是目錄、或索引裡一個機器產生的數字都沒有） |

> **`unsourced` 是給人讀的清單，不是判決。** 一個數字可能是合法的手算（例如兩個數字相減），也可能是憑印象打上去的——腳本分不出來，**由人逐條看**。但它把「543 個數字要逐格比對」縮成「這 12 個對不到來源」，這是 LLM 驗收唯一該接手的地方。
>
> **這支腳本不在 `run_pipeline.py` 的呼叫鏈裡**，要自己跑。**沒有任何東西會在你忘記時提醒你。**

#### 跑了但沒報出來的估計 —— `estimate_inventory.py` 與 C7

選擇性呈現抓不到的原因是「沒被列出來的東西不會出現在報告裡」。這支腳本掃 `<OUTPUT_DIR>` 的 workbook 把**實際跑出來的每一個估計**盤點出來，跟報告引用的數字做差集，寫成 `coverage_diff.json`：

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/estimate_inventory.py <OUTPUT_DIR> --reported <報告檔...>
```

exit `0` = 全部都出現在交付物裡；exit `1` = 有 `omitted`，發 `[QC_WARNING] COVERAGE:`。**`omitted` 不等於作弊**——但每一條都必須有一個寫下來的不列出理由，這正是看門狗 **C7** 讀 `coverage_diff.json` 在擋的東西。

`precheck_configs.py --stage post` 會**自己呼叫它**（`check_estimate_inventory`）產出 `coverage_diff.json`，所以 post 階段跑過 precheck 就有這份檔；要單獨重算或改 `--reported` 清單時才手動跑。

### 驗收者的三題（腳本跑完之後才問）

1. 這個分析總共跑了幾個？報告列了幾個？**差額在哪、為什麼不列？**（把 `coverage_diff.json` 的 `omitted` 直接給他，不要叫他自己數）
2. 這個檢定有沒有**對照組／另一層／另一個 frame** 也該跑？沒跑就不能拿它論證特異性。
3. **專題報告與主報告的涵蓋範圍差在哪？** 專題通常較完整，差額就是主報告被裁掉的部分。

**這三題的共通點是它們都在問「為什麼」，不是「是多少」。** 「是多少」交給腳本。

報告中出現、但任何輸出檔都找不到的數字（= `scripts/check_numbers_sourced.py` 的 `unsourced`）→ 要求驗收者自行重算並附程式片段。

> **選擇性呈現是這個 domain 最常見的失效模式，不是算錯。** 一次獨立第二輪驗收：543 個數值裡真正算錯只有 9 個，但九項嚴重發現有三項是「跑六個只列兩個／跑三個 frame 只報兩個／跑兩個亞群只報一個」，而且方向一致地朝對假說有利的一邊。

### 規則 4 — 發現要進登記簿，不是進對話

```bash
cp ${CLAUDE_SKILL_DIR}/assets/templates/verification_findings.json <OUTPUT_DIR>/data/verification_findings.json
```

在 `research-checks.yaml` 打開 `C4_open_findings` 指向這個檔。

驗收發現寫成 `verification_findings.json`（schema 見範本），**`status` 欄是唯一真值來源**，看門狗 C4 讀它擋交付。修好改成 `fixed` 並寫 `fixed_note`，**不要刪紀錄**——刪掉就失去「這個問題曾經存在、怎麼修的」軌跡。決定不改寫 `wontfix` + 理由。

> **範本是空的登記簿**：`findings` 開出來就是 `[]`，欄位形狀放在 `_一筆發現的欄位長這樣` 這個以底線開頭的說明鍵裡。**加第一筆是往 `findings[]` 塞**，不是去改那個說明鍵，也不要把它當成真的發現留著。

### 規則 5 — 絕對句要帶檢索範圍限定

「無人做過 X」「文獻空白」「僅 Y 曾被做過」一律附上：**檢索了哪些資料庫、哪個年代、每條檢索式命中幾筆、實際篩了幾筆**。

### 規則 6 — 病人層級資料不進 git

`.gitignore` 預設排除原始資料檔與逐列為受試者的分析資料集（範本 `assets/templates/gitignore-medical`）。加 remote 前用 `git check-ignore -v <檔>` 再確認一次。

---

## 2. 看門狗

```bash
python3 ${CLAUDE_SKILL_DIR}/assets/check_freshness.py <PROJECT_DIR> [--quiet] [--stage analysis|all]
```

| 檢查 | 抓什麼 |
|---|---|
| **C1** `stats_freshness` | 每個機器產生的 stats 檔比它的產生腳本與資料集新嗎 |
| **C2** `decision_log_pointers` | 決策紀錄的「要改就改這裡」欄還指得到存在的腳本與符號嗎 |
| **C3** `verification_coverage` | 驗收報告聲稱涵蓋的版本 vs 被驗文件現在的長度 |
| **C4** `open_findings` | 登記簿裡還有沒有未結案的阻擋級項目 |
| **C5** `document_vs_stats` | 交付文件比它引用的 stats 檔新嗎（抓「文字寫在重跑之前」） |
| **C6** `stats_gate` | 專案自定的 stats 門檻閘 |
| **C7** `coverage` | **跑出來的每個估計，要嘛出現在交付物裡、要嘛有寫下來的不列出理由。** 讀 `scripts/estimate_inventory.py` 產的 `coverage_diff.json`（預設檔名，可用 `report:` 覆寫）；找不到那個檔就是紅燈——「沒有人比對過」不是通過 |
| **C8** `bare_numbers` | **交付物裡印出來的每個數字，在它自己宣告的 `sources` 裡找不找得到**（委派 `lint_bare_numbers.py`）。前七項比的都是檔案與檔案，沒有一項真的去讀文件裡的那個數字——這是規則 1 唯一的閘。事故：0813 AF 交給老師的 docx 手打「313 筆」，登記簿是 315，七項全綠 |
| **C9** `absolute_claims` | **絕對句／新穎性宣稱有沒有帶檢索範圍**——查了哪些資料庫、有無檢索日期、命中幾筆、篩了幾筆（委派 `lint_absolute_claims.py`）。這是規則 5 到 2026-09-03 為止唯一沒有工具的一條。事故：`Project Lit Rev/PE EKG MLDL` 的 introduction 寫了新穎性宣稱，自己的 Methods 只有單一資料庫 85 筆、沒有檢索式也沒有日期 |
| **C10** `prisma_reconcile` | **稿件宣稱的 PRISMA 整數 vs 磁碟上的篩選／全文／抽取檔實際筆數**（委派 `reconcile_prisma.py`，僅 MA 版面）。事故：某 MA 專案 稿件寫 47 筆進全文，`04_fulltext/fulltext_decisions.csv` 卻有 185 列——兩輪篩選被拼成一張流程圖 |

| exit | 意思 |
|---|---|
| `0` | 啟用的檢查全過 |
| `1` | **有問題**——包含「設定裡指到的檔不存在」。在處理完之前不要相信文件裡的數字，也不要對外宣稱結果 |
| `2` | **跑不起來 —— 這些面向未受保護**。來源有五類，見下面的 triage 表。**exit 2 不是「還沒設定」的同義詞**，也絕不是通過 |

> ⚠ **exit 2 ≠ 「補一份 yaml 就好」。先看輸出是哪一種。** 五類的修法完全不同，其中第 5 類（比對池是空的）最常被誤讀成第 1 類——那些專案設定檔明明在。

| # | 輸出長什麼樣 | 原因 | `check_freshness.py` | 怎麼修 |
|---|---|---|---|---|
| 1 | `✗ <root> 沒有 research-checks.yaml` | 專案未受看門狗保護 | `:456` | 從 `assets/templates/` 複製一份並填掉 `<...>` |
| 2 | `✗ --stage 只接受 analysis 或 all` | 參數打錯 | `:423` | 改參數 |
| 3 | `✗ <yaml> 解析失敗` ／ `頂層或 checks 不是鍵值對` | 設定檔壞了，等於沒有設定 | `:465`、`:468` | 修 YAML |
| 4 | `啟用 0 項` ＋`（啟用 0 項不等於通過。）` | 一項都沒開，或唯一那項鍵名打錯 | `:633` | 開啟至少一項；鍵名照名冊 |
| 5 | `✗ N 項檢查無法進行 —— 這些面向未受保護` | `cannot_run` 非空（下段展開） | `:1669` | 看逐條訊息，逐項補 |

**第 5 類（`cannot_run`）自己還有三個家族**，訊息都印在「✗ N 項檢查無法進行」底下：

- **設定寫了但等於沒寫**：鍵名／子鍵打錯（`:492`、`:501`、`:509`——打錯的檢查會被靜默當成沒開）、整項寫成 `{}`（C7 `:1245`、C8 `:1492`、C9 `:1528`、C10 `:1583`）、缺必填欄（C9 沒 `paths` `:1541`、C10 沒 `root` `:1595`、C5 的 `sources` 是空清單 `:1030`）。
- **讀不到判斷所需的檔**：JSON 讀不動（`:481`）、C4 找不到登記簿（`:860`）、C6 沒有 `stats_index`（`:1136`）、C3 宣告的驗收行數還是範本預設 0（`:827`）、C7 報告的 `status` 不是 `compared`（`:1315`）。委派的三支 lint 自己回 exit 2 也算這一類（C8 `:1508`、C9 `:1563`、C10 `:1608`），**其中包含 `run_lint()` 在自己所在目錄找不到那支 lint（`:336`）——vendored 副本只複製 `check_freshness.py` 一支時必然踩到**。
- **啟用了，但實際比對了 0 個對象**（`:1643`、`:1649`）**——這是「假通過」的正臉**：設定檔在、路徑也對、檢查跑了，只是比較池空的，它不可能發現任何問題。實例：某專案 有 `research-checks.yaml`、沒給 `--stage`，仍然 exit 2，訊息是「C1: 這一項啟用了，但實際比對了 0 個對象 —— 比較池是空的……（stats_index 的 files 是空的，或裡面每一筆都不是 .py 產生的）」。同一次還有 C7 的 372 個未說明遺漏走 exit 1，但 `cannot_run` 優先，最終碼是 2。**某專案 是同型的已知狀態，其 `CLAUDE.md` 已明令「不要為了轉綠編一筆假發現」。**

> **沒有 `research-checks.yaml` 會回 exit 2，不是「通過」。** 未設定的專案沒有任何保證，回報通過等於說謊。同理，上面五類任何一類都不是通過。
>
> ⚠ **exit 2 不代表「設定裡的路徑不存在」。** 設定檔在、但它指到的 stats／文件不在，會被當成**一項檢查失敗**走 **exit 1**（實測 `C1: 找不到 stats_index（None）` → exit 1）。修法不同：exit 1 要去把那個檔生出來或改路徑。

啟用哪幾項由專案根目錄的 `research-checks.yaml` 決定；用不到的整段刪掉。**範本裡 C8／C9／C10 是註解掉的**——不是因為可選，是因為它們各需專案才知道的宣告（C8 的 `sources:`、C9 的 `paths:`、C10 的 `root:`），而整項寫成 `{}` 會走 exit 2 不是通過。交付物會印數字就開 C8；文件裡有絕對句就開 C9；MA 版面（`01_protocol/`…`09_qa/`）才開 C10。專案可在自己的 `analysis/scripts/` 放一支薄 wrapper（例如 `16_check_freshness.py`）只呼叫這支共用腳本，既有交接文件裡「跑 16」的指令就不必改。

---

## 3. Bootstrap：開一個新的數字型研究專案

```bash
SKILL_ASSETS=${CLAUDE_SKILL_DIR}/assets
P=<專案路徑>
mkdir -p "$P"/analysis/{scripts,data,output,report} "$P"/reference
cp "$SKILL_ASSETS"/templates/research-checks.yaml      "$P"/
cp "$SKILL_ASSETS"/templates/PROJECT_STATE.yaml        "$P"/
cp "$SKILL_ASSETS"/templates/project_CLAUDE.md         "$P"/CLAUDE.md
cp "$SKILL_ASSETS"/templates/decision_log_skeleton.md  "$P"/analysis/report/decision_log.md
cp "$SKILL_ASSETS"/templates/gitignore-medical         "$P"/.gitignore
cd "$P" && git init -q
```

接著**把每個範本裡的 `<...>` 佔位符填掉**，用不到的檢查從 `research-checks.yaml` 刪掉。範本原樣留著佔位符等於沒做——看門狗會因為路徑不存在回 exit 2。

**pipeline 模式下這一步等同 SKILL.md 的 Step 3d**（`<OUTPUT_DIR>` 取代上面的 `$P`，`decision_log.md` 放 `<OUTPUT_DIR>/report/`），**必做，不是可選**：`research_plan.json` 只管統計怎麼跑，管不了交付出去的數字會不會腐爛。四個佔位符要怎麼填：

1. **`research-checks.yaml`** — 路徑對到本次的 output 結構；用不到的檢查整段刪掉。至少留 C1（stats 新鮮度）與 C5（文件 vs stats）。
2. **`CLAUDE.md`（專案級）** — 從 Step 1 的訪談與 Step 2 的欄位比對表直接填：這個專案在做什麼、檔案在哪、**這個專案一定會踩到的雷**（Step 2 發現的編碼陷阱、缺值型態、單位不一致全部寫進去）、目前狀態。
   > auto memory 不進版本控制也不跟著資料夾走。Step 2 辛苦問出來的資料陷阱只寫進對話 = 交出去就沒了。
3. **`decision_log.md`** — 把 Step 1–3 的每個決定登記成永久 ID 的列（世代定義、終點、追蹤時間、共變項、參考組、統計方法），狀態一律 `active`。**這是後面 Step 8 變更控制的起點**；沒有起始列，之後就沒有東西可以 supersede。
4. **`.gitignore` + git init** — 醫療專案預設排除病人層級資料。`git init -q` 後跑一次驗證：
   ```bash
   git -C <OUTPUT_DIR> check-ignore -v <資料檔路徑>
   ```
   沒有命中就是**沒擋住**，要當場修 `.gitignore`，不要等到加 remote 才發現。

已存在的檔一律不覆寫——列出差異問使用者。

---

## 4. 專案級 `CLAUDE.md` 是必要的，不是可選的

每個數字型研究專案自己要有 `CLAUDE.md`（骨架 `assets/templates/project_CLAUDE.md`），寫該專案的**資料陷阱、estimand、目前狀態**。

> **auto memory 不進版本控制、也不跟著資料夾走。** 交出去或換機器就沒了；資料陷阱寫在資料夾內的 CLAUDE.md 才活得下來。

骨架有九節，其中這四節不准留空：`硬規則`、`這個專案一定會踩到的雷`、`接手第一步：先跑看門狗`、`目前狀態`。

---

## 5. 交付給別人時（可攜性）

看門狗在專案資料夾**外面**，複製出去的資料夾跑不動它。交出去之前 vendor 一份：

```bash
# 複製整個 assets/，不要只複製 check_freshness.py
cp -R ${CLAUDE_SKILL_DIR}/assets \
      <專案>/analysis/scripts/_watchdog
# 入口：python3 <專案>/analysis/scripts/_watchdog/check_freshness.py <專案>
```

> **為什麼要整包，不能只挑那一支**：C8／C9／C10 是 `check_freshness.py` 用 subprocess 委派給 `lint_bare_numbers.py` / `lint_absolute_claims.py` / `reconcile_prisma.py` 跑的，而它找 lint 的方式是 `Path(__file__).parent / script`（`assets/check_freshness.py:334`）——**照自己所在目錄找**。單獨複製一支之後那三支不在旁邊，三項一律回 exit 2「找不到 lint 腳本，這不是通過」。至少要四支 `.py` 同在一個目錄；連 `templates/` 一起帶（`-R` 整包）還能讓對方看得到設定範本。

並在交接說明裡寫清楚 vendor 的是哪一版。**skill 內的 `assets/` 版為 canonical**（修一次所有專案受惠），vendored 副本只為可攜。

原始檔與 script 要跟交付物放在一起：raw JSON / CSV、fetch 與 build script 一併留在交付資料夾，並附「重跑方式」指令表。

---

## 6. 委外 / 代做型任務的附加要求

使用者常把產物轉交給指導老師，對方需要能替每個判斷辯護。除了決策紀錄，另附**操作流程與決策清單**文件，四欄：

`決策點 | 採用做法 | 理由 | 影響範圍與如何更改`

最後一欄要**指名改哪個檔的哪個變數**。判斷題的列要標 `direct` vs `borderline（待確認）`，不要靜默納入。

其餘資料交付硬規則（原始查詢紀錄不預設篩選、門檻要標示且參數化、被排除的另存參考表、空白格要有證據、多來源不合併成一張表）（略）。

---

## 7. lit review / MA 產物的三條（與本 skill 的統計流程平行）

看門狗與 `PROJECT_STATE.yaml` **不套用**於純 lit review / MA（沒有 `*_stats.json` + 編號腳本的結構，硬套只會空轉）。但下面三條必須遵守，都是實際踩過的坑：

1. **絕對句一律帶檢索範圍限定**（同 §1 規則 5）。**「零命中」與「篩選後零篇符合」是兩件事，不可混寫。**
2. **宣稱「無人做過 X」之前，必須人工調閱最相似那幾篇的圖表。** 關鍵結果可能**只存在於 figure 的繪圖區內**，正文與摘要完全不提，純文字檢索與全文 grep 都抓不到。（例：交互作用 p 值有時只出現在某張 figure 的圖內。）
3. **篩選程序的限制要寫進產物本身**：單一 reviewer、AI 輔助篩選、只用單一資料庫語料 —— 都要在報告裡揭露，不能只留在工作紀錄。

MA 的數字部分（extraction sheet → forest plot）仍適用 §1 的規則 1、3、4。

---

## 8. 措辭紀律（引用統計結果時）

未達統計顯著一律寫「**無統計顯著差異**」「未達顯著」「在此資料集中未偵測到差異」，**不寫**「沒有關聯」「兩組一樣」「證明沒效」。CI 跨 1 的效應量不可做主視覺大字。要證明「相同」需要 non-inferiority 設計與預設 margin；觀察性研究未達顯著寫「該 cohort 校正後未達顯著」，不寫「無因果關係」。

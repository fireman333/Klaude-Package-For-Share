# `assets/` —— 數字型研究的共用交付紀律工具

這裡放的是**跨研究主題共用**的東西。專案自己的資料陷阱、estimand、腳本細節留在各專案的 `CLAUDE.md`，不要往這裡搬。

**規則本體在 `../references/delivery_discipline.md`**（六條硬規則、驗收三題、絕對句限定、可攜性）。本檔只講「工具怎麼用」。

## 內容

| 檔案 | 是什麼 |
|---|---|
| `check_freshness.py` | **腐爛看門狗**，十項檢查 C1–C10。共用一份，各專案用設定檔呼叫。C8／C9／C10 自己不判斷，用 subprocess 委派給下面三支 lint |
| `lint_bare_numbers.py` | **C8**：交付物裡印出來的每個數字，在它自己宣告的 stats `sources` 裡找不找得到（交付紀律規則 1 的閘）。讀同一份 `research-checks.yaml`，也可單獨跑 |
| `lint_absolute_claims.py` | **C9**：絕對句／新穎性宣稱有沒有帶檢索範圍——資料庫、檢索日期、命中筆數、篩了幾筆（規則 5 的閘）。吃路徑參數不讀 yaml，看門狗負責翻譯 |
| `reconcile_prisma.py` | **C10**：稿件宣稱的 PRISMA 整數 vs 磁碟上的篩選／全文／抽取檔實際筆數。吃 MA 專案根目錄，**只適用 `01_protocol/`…`09_qa/` 版面** |
| `templates/research-checks.yaml` | 看門狗設定範本（放專案根目錄） |
| `templates/PROJECT_STATE.yaml` | 專案現況的**人工維護**筆記（環境／seed／上次全量重跑／caveats／未辦事項／交付前檢查）。**沒有任何程式讀它**——看門狗不查、pipeline 不查，過期不會有人告訴你 |
| `templates/decision_log_skeleton.md` | 決策紀錄骨架，含永久 ID／狀態欄／變更控制 H 節 |
| `templates/verification_findings.json` | 驗收發現登記簿的 schema（清單留空，不自帶示範資料） |
| `templates/omission_reasons.json` | C7 用：跑過但沒進交付物的估計，逐一寫下不列的理由（清單留空） |
| `templates/project_CLAUDE.md` | 專案級 CLAUDE.md 骨架 |
| `templates/gitignore-medical` | 醫療研究專案的 `.gitignore` 起點 |

## 開一個新的數字型研究專案

```bash
A=<RESEARCH_PLAN_DIR>/assets
P=<專案路徑>
mkdir -p "$P"/analysis/{scripts,data,output,report} "$P"/reference
cp "$A"/templates/research-checks.yaml       "$P"/
cp "$A"/templates/PROJECT_STATE.yaml         "$P"/
cp "$A"/templates/project_CLAUDE.md          "$P"/CLAUDE.md
cp "$A"/templates/decision_log_skeleton.md   "$P"/analysis/report/decision_log.md
cp "$A"/templates/omission_reasons.json      "$P"/analysis/report/
cp "$A"/templates/gitignore-medical          "$P"/.gitignore
cd "$P" && git init -q
```

把每個範本裡的 `<...>` 佔位符填掉，用不到的檢查從 `research-checks.yaml` 刪掉。

## 跑看門狗

```bash
python3 <RESEARCH_PLAN_DIR>/assets/check_freshness.py .
```

- `0` = 啟用的檢查全過
- `1` = 有問題，**在處理完之前不要相信文件裡的數字，也不要對外宣稱結果**
- `2` = 跑不起來 —— **這些面向未受保護**。來源有五類：沒有 `research-checks.yaml`、`--stage` 值錯、YAML 壞掉、
  啟用 0 項、以及 `cannot_run` 非空（設定寫了等於沒寫／讀不到判斷所需的檔／**啟用了但比對池是空的**）。
  **exit 2 ≠ 補一份 yaml 就好**，先看輸出是哪一種；完整 triage 表見 `references/delivery_discipline.md` §2「看門狗」。
  設定裡的**路徑不存在不是 exit 2，是 exit 1**（每一個都走 `problems.append()`）。

**沒有 `research-checks.yaml` 會回 exit 2，不會回「通過」。** 未設定的專案沒有任何保證，回報通過等於說謊。

專案可以在自己的 `analysis/scripts/` 放一支薄 wrapper（例如 `16_check_freshness.py`），內容只是呼叫這支共用腳本——這樣報告與交接文件裡既有的「跑 16」指令不必改。

## 交付給別人時（可攜性）

共用腳本在專案資料夾**外面**，所以複製出去的資料夾跑不動它。交出去之前：

```bash
# 複製整個 assets/，不要只複製 check_freshness.py
cp -R <RESEARCH_PLAN_DIR>/assets <專案>/analysis/scripts/_watchdog
# 入口：python3 <專案>/analysis/scripts/_watchdog/check_freshness.py <專案>
```

> **為什麼是整包**：C8／C9／C10 由 `check_freshness.py` 委派給旁邊那三支 lint，而它找 lint 的方式是 `Path(__file__).parent / script`（見 `check_freshness.py:334` 的 `run_lint()`）——**照自己所在目錄找**。只複製一支的話，vendored 副本的 C8／C9／C10 一律回 exit 2「找不到 lint 腳本，這不是通過」。最少四支 `.py` 要在同一個目錄；`-R` 整包還會帶上 `templates/`，對方看得到設定範本。

並在交接說明裡寫清楚 vendor 的是哪一版。**skill 內的這份為 canonical**（修一次所有專案受惠），vendored 副本只為可攜。

> 這是一個刻意的取捨：共用版好維護、但不可攜；vendored 副本可攜、但會漂移。選擇共用為主，是因為這些檢查的邏輯還在演化，讓修正能傳到所有專案比較重要。

## 改這裡的東西之前

`check_freshness.py` 一改，**所有專案的檢查行為同時改變**。所以：

1. 加檢查、放寬既有檢查 → 直接做，但要在本檔記一行為什麼。
2. **收緊或移除既有檢查** → 先確認沒有專案是靠它擋住已知問題。收緊會讓原本綠的專案變紅，那可能是對的，但要有人知道。
3. 改 C2 的解析邏輯要特別小心——它讀決策紀錄每列的**最後一欄**，任何專案在決策表尾端加欄位都會壞掉。這一點寫在範本註解裡，別拿掉。
4. 收緊檢查前，先用你自己手上的幾個既有專案回歸測試。

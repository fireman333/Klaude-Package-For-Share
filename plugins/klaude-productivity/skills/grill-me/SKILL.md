---
name: grill-me
description: >
  通用「拷問式釐清」skill — medium-stakes 計畫 / 決策前用結構化問題 grill 使用者。
  Quick（5–7 題、~5 min）給日常決策；Deep（15+ 題、recursive、~15–30 min）給專案 / 規格 / 長期計畫。
  Facet pack 依任務型別（software / learning / life / content / academic-medical / generic）抽題組。
  Trigger: `/grill`、`/grill-me`、「拷問我」「逼我想清楚」「幫我釐清」「逼問我」「審問我」。
  退讓：醫學研究統計規劃 → `/research-plan`。trivial 決策（午餐 / 回訊息）顯式呼叫尊重，主動 propose 不觸及。
---

# grill-me — 拷問式釐清 Skill

## 設計哲學

**問題**：使用者（非 CS 背景）開始新計畫 / 做 medium-stakes 決定時，常因為 AI 沒問到關鍵面向（audience、failure mode、reversibility、stakeholders…）導致後續產出方向錯。一般 AI 的專案 kickoff 通常只問一兩題，gap 很大。

**解法**：把「拷問機制」抽成獨立 primitive。Claude 主動依任務型別抽 facet 題組，**不止問還會 recursive 追問**到分支解開。其他 skill 可以用 thin wrapper 呼叫本 skill 取結構化輸出（見 Wrapper invocation contract）。

**核心鐵律**：
- **Curator 哲學**：只問、只寫 markdown 紀錄；不自動觸發下游 skill / 不自動 commit / 不自動 implement
- **Escape hatch 永遠開**：使用者任何題答「skip」/「不重要」/「不知道」立即跳下一題、不糾纏
- **退讓優先**：醫學研究統計規劃 → `/research-plan`；本 skill 不重複造輪
- **Anti-annoyance**：Claude 主動 propose 有嚴格 gate（見下方），使用者顯式呼叫永遠尊重
- **Medium-stakes only（主動觸發）**：Claude 主動 propose 的 threshold 是「≥ 1 hr 影響 / 後悔成本 > 10 min 思考」；trivial 不主動

---

## 觸發條件

| 場景 | 行為 |
|---|---|
| `/grill <topic>` | Quick 模式 + 自動偵測 facet pack |
| `/grill-me <topic>` | 同上（別名） |
| `/grill quick <topic>` | 強制 Quick |
| `/grill deep <topic>` | 強制 Deep |
| `/grill --pack=<name> <topic>` | 強制指定 pack（software-project / learning-plan / life-decision / content-creation / academic-medical / generic） |
| `/拷問我 <topic>`、「拷問我 <topic>」 | 中文觸發，預設 Quick |
| 「逼我想清楚」「幫我釐清」「逼問我」「審問我」 | 模糊觸發，預設 Quick + AskUserQuestion 確認 topic |
| Claude 主動 propose | 偵測 medium-stakes signal 時，**一句話**提議「要不要先 `/grill quick`？」（拒絕就閉嘴） |

---

## 兩模式規格

### Quick 模式（5–7 題、單輪、~5 min）

**用途**：日常 medium-stakes 決策（工作選擇、要不要接 paper、買大件、課後輔導教材方向、寫一篇公開文）

**流程**：

1. **Confirm topic + pack**（一句話）
   - Claude 從使用者輸入抽 topic + 偵測 pack（見「Pack 自動偵測」）
   - 一句話確認：「我理解你想釐清的是 **<topic>**，會用 **<pack>** 題組（<facet 簡述>）。對嗎？」
   - 使用者糾正 → 重新偵測；確認 → 進 step 2

2. **抽 5–7 題 baseline**
   - 從選定 pack 的 facets 抽 5–7 個最關鍵的（每 facet 一題；若 facet 數 < 5 則重複用同 facet 不同 angle）
   - 用 AskUserQuestion 一輪問完（**最多 4 題一批**，超過拆兩批）

3. **不 recursive**
   - 使用者答完即收尾，不追問子分支
   - 任何題回「skip」/「不重要」/「不知道」 → 該題標記 *(unresolved)* 並跳過

4. **寫出 summary**
   - 路徑：目前工作目錄 `./grilled-<slug>-<YYYY-MM-DD>.md`（使用者想放別處就照指定；不確定就問一句）
   - slug = topic 取前 30 char、空格換 `-`、去除特殊符號
   - 格式見下方「輸出格式」section
   - 結尾印「已寫入 `<path>`，建議下一步：<recommended next skill 或 action>」

### Deep 模式（15+ 題、多輪 recursive、~15–30 min）

**用途**：專案 / 規格 / 長期計畫；其他 skill 的 wrapper 也可呼叫此模式

**流程**：

1. **Confirm topic + pack**（同 Quick）

2. **跑 5–7 題 baseline**（同 Quick step 2）

3. **Branching pass（recursive 追問）**
   - 對每個收到的答案，Claude 判斷「這答案是否引入新的 uncertainty / contradiction / 隱含假設？」
   - **是** → 從 pack 的 follow-up triggers 抽 1–3 題深入（**深度上限 3 層**）
   - **否** → 該 facet 結案
   - 每輪用 AskUserQuestion 不超過 4 題；多輪串接時，每輪結束印「目前 N/M facet 結案、深度 D」進度條

4. **Stop condition**（任一）：
   - 所有 facet 結案
   - 達深度上限 3
   - 使用者打 `/done` / 「夠了」/「就這樣」

5. **寫出 summary**
   - **Standalone 呼叫**：`./grilled-<slug>-<YYYY-MM-DD>.md`（目前工作目錄）
   - **被 wrapper 呼叫**：由 wrapper 傳入的 `output` 路徑
   - 完整 markdown：每 facet 一段、含 sub-facet branches、Open uncertainties、Recommended next skill

---

## Wrapper invocation contract（when called by another skill）

當被其他 skill（例：你自己寫的專案 kickoff skill）透過 Skill tool invoke 時，本 skill 接受以下 override 參數。Override 一律由呼叫者顯式傳入；未傳則用 default。

| Param | Default | Override behavior |
|---|---|---|
| `mode` | 自動偵測（quick / deep） | 強制鎖定模式，不再讓使用者 confirm |
| `pack` | 自動偵測 | 跳過 pack 偵測流程 + skip「Pack 自動偵測」一句話確認 |
| `output` | `./grilled-<slug>-<YYYY-MM-DD>.md`（cwd） | 寫到指定路徑；wrapper 通常會傳專案內的路徑 |
| `recommended_next_skill` | 自動推薦（依 pack） | 寫死進 summary footer 的 Recommended next skill / action 區段 |
| `topic` | 從使用者訊息抽 | wrapper 直接傳入確切 topic（例：「project clarification for a new app」） |

**鐵律**：
- 不接受其他 override（避免 wrapper 過度耦合進 grill-me 內部邏輯）
- `output` 路徑若父目錄不存在 → 報錯停止（不自動 mkdir 給未明確存在的專案資料夾）
- Wrapper 呼叫時，本 skill 仍尊重使用者中途 `/done` / 「夠了」escape

**範例呼叫格式**（給其他 skill 寫 SKILL.md 用）：
```
透過 Skill tool invoke `grill-me` 並傳入：
  mode: deep
  pack: software-project
  output: <cwd>/project-clarifications.md
  recommended_next_skill: （由 wrapper 指定）
  topic: <使用者描述的專案>
```

---

## Pack 自動偵測

從 topic 描述 + 上下文（CWD / 使用者最近行為）抽訊號 → 比對 pack 關鍵詞 → 信心評估。

### Pack 關鍵詞速查（Claude 內部用）

| Pack | 觸發關鍵詞 / 訊號 |
|---|---|
| `software-project` | app / 寫程式 / 做工具 / refactor / framework / framework / API / 部署 / vibe-coding |
| `learning-plan` | 證照考試 / 在職學習 / 教材 / 課後輔導 / 補習 / 自學 / 弱點複習 / 學習計畫 |
| `life-decision` | 接 / 不接 / 選 / 要不要 / 該不該 / 買 / 換 / 申請 / 合作 / 轉職 / 進修 / 空檔期 |
| `content-creation` | 寫文章 / pptx / 投稿 / 公開文 / 部落格 / Threads / 報告 / 心得文 / 醫普 / Medium |
| `academic-medical` | journal club / JC / 書報討論 / 期刊報告 / case discussion / 案例討論 / 病例討論 / M&M / grand rounds / tumor board / CPC / EBM / 文獻評讀 |
| `generic` | 偵測不到任何上面的訊號時 fallback |

### 退讓 trigger（不啟動 grill-me，直接 redirect）

| 偵測訊號 | 退讓到 |
|---|---|
| 含 PICO / PECO / cohort / cox / KM / Kaplan-Meier / 統計 / 資料庫 / TTM / heart failure 資料庫 / outcome 變數 | `/research-plan` |
| `research_plan.json` 在 cwd | `/research-plan` resume |

退讓格式：
```
你的需求看起來該走 <skill>（已有同等的結構化釐清流程），不重複造輪。要切過去嗎？
```
使用者選 yes → 直接 invoke 對應 skill；選 no（少見）→ 才繼續用 grill-me。

### 信心評估

- 命中 ≥ 2 個關鍵詞 → 信心高，直接用
- 命中 1 個關鍵詞 → 信心中，confirm 一句話
- 0 命中 → 用 generic + 同步問使用者「比較像 software / learning / life-decision / content / academic-medical / 都不像？」

---

## 輸出格式

```markdown
---
mode: quick | deep
pack: <pack-name>
topic: <slug>
date: YYYY-MM-DD
duration_min: <估計分鐘>
follow_up_skill: <recommended next skill or "none">
---

# Grilled: <topic 全文>

## Facet 1: <facet name>

**Q**: <question>
**A**: <user answer>

<若為 Deep mode 且有 sub-facet：>
### Sub-facet 1.1: <sub-facet name>
**Q**: <follow-up question>
**A**: <user answer>

## Facet 2: ...

---

## Open uncertainties

- <facet 編號 + 簡述>: <為什麼還沒解開>
- ...

## Recommended next skill / action

- `<skill-or-command>`: <一句話為什麼適合接續>
```

**Slug 規則**（檔名用）：
- 取 topic 前 30 char
- 空格 / 標點換 `-`
- 連續 `-` 合併
- 結尾 trim `-`
- 中文保留（檔系統支援 UTF-8）
- 範例：`要不要接這個合作 paper` → `要不要接這個合作-paper`

---

## Proactive proposal 規則

Claude 主動建議 `/grill quick` 的條件 — **全部滿足才 propose**：

1. **使用者訊息含 medium-stakes signal**：
   - 直接訊號：「在考慮 X 跟 Y」「想做 Z」「下個月要 W」「該不該 V」「猶豫」「要不要」
   - 間接訊號：使用者描述新計畫但沒說怎麼做、scope 模糊

2. **不在跑其他 question-heavy skill**：`/research-plan`（active）→ 不 propose

3. **本 session 同 topic 沒 propose 過**：用本 session memory 判斷

4. **本日 grill-me 已用次數 < 3**：避免一日多次推銷

5. **退讓 trigger 沒命中**：若該命中 `/research-plan` 等，直接退讓不 propose grill

**Propose 格式**（一句話、不囉嗦）：
```
這個決定有點 medium-stakes — 要不要先 `/grill quick` 用 5 題框架性問題逼自己想清楚？（5 min 內）
```

---

## Anti-annoyance guards

| 訊號 | 行為 |
|---|---|
| 使用者拒絕 propose 一次 | 該 topic 本 session 不再提；換 topic OK |
| 連續 2 個 session 同類型 topic 都被拒絕 | 記下來降低該類型主動度（例如寫進專案 memory） |
| 使用者顯式呼叫 `/grill ...` | 永遠尊重，不被 guard 攔（顯式 > 主動） |
| 使用者答題中明顯不耐（「快點」「直接給結論」「你問太多」） | 立刻收尾，把已答的寫進 summary、未答的列為 unresolved；不追問 |
| 使用者打 `/done` / 「夠了」 | Deep 模式立刻收尾 |

---

## 使用範例

### 範例 1: Quick — 接不接合作 paper

```
USER: /grill 要不要接學長的這個合作 paper

CLAUDE: 我理解你想釐清的是「要不要接學長的合作 paper」，會用 life-decision 題組
         （stakes / reversibility / opportunity cost / constraints / stakeholders / 長短期視角）。對嗎？

USER: 對

CLAUDE: [一輪 AskUserQuestion 4 題]
   1. 這個 paper 在你的工作期間佔多少時間？(< 5 hr/wk / 5–10 hr/wk / > 10 hr/wk / 不確定)
   2. 接受後反悔成本？(隨時可退 / 半路退會破壞關係 / 一旦答應一定要做完)
   3. 機會成本：這時間原本會做什麼？(自己的專案 / 考試準備 / 休息 / 教學)
   4. 學長之前合作經驗如何？(順利 / 不順 / 沒合作過)

USER: [作答]

CLAUDE: [第二輪 3 題]
   5. 你期待從這 paper 拿到什麼？(co-authorship / 學東西 / 人情 / 都不重要)
   6. 3 個月後 vs 3 年後視角，哪個權重高？(3 個月 / 3 年 / 一樣)
   7. 有什麼 deal-breaker 條件？(自由文字)

USER: [作答]

CLAUDE: ✅ 寫入 `./grilled-要不要接學長合作-paper-2026-05-06.md`
        建議下一步：自己看一下 summary，跟學長談時帶著這份 framework 講。
```

### 範例 2: Deep — 新 app 專案

```
USER: /grill deep 我想做一個給同學用的排班 app

CLAUDE: 用 grill-me deep + software-project pack
[多輪 AskUserQuestion，含 baseline + branching follow-up]

CLAUDE: ✅ 寫入 `./grilled-排班-app-2026-05-06.md`
```

---

## 失敗模式

| 症狀 | 處理 |
|---|---|
| 使用者沒給 topic（只打 `/grill`） | AskUserQuestion 一句話收 topic |
| Topic 太抽象無法偵測 pack | 用 `generic` 並一句話確認 |
| 使用者命中退讓 trigger 但堅持要用 grill-me | 尊重，繼續走 grill-me（顯式 > 自動） |
| Quick 模式批次 AskUserQuestion 因 ≤ 4 題限制要拆批 | 拆兩批，每批前印「Q1–4 / Q5–7」標頭 |
| Deep 模式深度達 3 還沒解開 | 強制結案，把仍有疑問的記入 Open uncertainties |
| 目前目錄寫入失敗 | 問使用者要寫到哪，或直接把 summary 貼在對話中 |
| 使用者中途打 `/done` | 立刻收尾、寫入已答 + 列 unresolved |

---

## 與其他 skill 的互動

| skill | 互動方式 |
|---|---|
| `/research-plan` | grill-me 偵測醫學研究關鍵詞 → 退讓給 research-plan，不重複問 PICO |
| `/no-wheels` | grill-me 偵測 software-project topic → 完成後可建議「要不要先跑 `/no-wheels` 看有沒有現成輪子」 |
| `auto-git` | grill-me 不自動 commit；若使用者要把 grilled-*.md commit 進 repo，可用 auto-git |

---

## 不做的事（Out of Scope）

- **不自動觸發下游 skill** — summary 結尾建議，使用者自己決定是否走
- **不取代 `/research-plan` Step 1** — 它已有領域專屬問題集
- **不做 multi-day decision tracking** — 一次 grill 一個 topic；長期追蹤建議用 筆記軟體
- **不問 trivial decisions**（主動 propose 層面）— 午餐、回不回訊息、要不要去夜市等不主動觸發
- **不 sync 到雲端** — 純 local file
- **不取代使用者判斷** — grill-me 只 surface 面向，不下結論

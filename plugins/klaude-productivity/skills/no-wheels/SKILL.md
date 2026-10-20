---
name: no-wheels
description: "no-wheels: checks if a coding idea reinvents the wheel — searches GitHub/npm/PyPI/awesome lists/HN, shortlists candidates, scores overlap, outputs a Wheel Score + verdict. Trigger: /no-wheels, /wheel-check, /造輪, 有人做過嗎, 有現成的嗎, 有類似的嗎, 是不是造輪, 造輪程度, reinvent the wheel, is this a wheel, does this exist, existing open source; also for coding project ideas w/o prior-art check. Not for business/clinical/research ideas."
---

# No-Wheels — 造輪偵測與評估

## 哲學

Vibe coding 最大陷阱：興奮之下直接開幹，三天後 Google 才發現有 10k stars 的成熟方案。這個 skill 讓使用者在寫第一行 code 前花 5–10 分鐘系統性掃 prior art，避免重造輪子。

**但造輪不一定是錯的。** 有時候現成的太肥、太舊、許可證不合、或學習本身就是目的。這個 skill 的工作是**揭露事實**（有什麼、活不活、overlap 多少），最後的 build/不 build 決定留給使用者。

**不評估點子本身好不好。** 只評估「是不是已經有人做了」。研究點子的可行性請走 `hypothesis-generation`。

---

## 觸發情境

- 使用者提出要寫某個工具/app/library/CLI，問「有人做過嗎」「有現成的嗎」
- 貼 README/pitch 問「這算造輪嗎」
- 直接打 `/no-wheels` 或 `/wheel-check`
- 偵測到「我想做一個 XXX」「我打算寫一個 YYY」的 coding idea 而使用者還沒檢查過 prior art（可主動提議跑本 skill）

**不觸發**：研究題目、臨床問題、商業模式、社群想法 → 研究類走 `hypothesis-generation` / `research-plan` / `deep-research`。

---

## 工作流程

### Phase 1：Intake（點子拆解）

請使用者（或從上下文抽取）三件事：

1. **Core function**：一句話講這東西「做什麼」。動詞 + 名詞 + 輸入 → 輸出。
2. **Target user / use case**：誰會用、在什麼情境。
3. **Differentiators（若有）**：使用者自認為比想像中的現成方案好在哪（速度？體驗？特定 niche？整合？）。

模糊就追問。不要拿著「我想做一個筆記 app」去搜，搜不出有用結果。

產出一組 **search keywords**（英文為主，2–5 組同義詞變體），例如：
- 核心：`markdown note-taking CLI`
- 同義：`plain-text notes terminal`、`zettelkasten CLI`
- Niche 限定：`markdown notes with bidirectional links CLI`

### Phase 2：多源搜尋

**並行**跑以下來源（依點子性質取 2–4 個，不要全跑）：

**GitHub（必跑）** — 透過 `gh` CLI，認證、快、穩：
```bash
gh search repos "<keywords>" --sort=stars --limit=15 --json name,owner,stargazerCount,description,updatedAt,url
```
注意：`gh search repos` 會回 JSON；直接看 star + 最後更新時間。

**Package registries**（依語言）：
- npm：`WebSearch` `site:npmjs.com <keywords>` 或直接 `WebFetch` `https://www.npmjs.com/search?q=<keywords>`
- PyPI：`WebFetch` `https://pypi.org/search/?q=<keywords>`
- crates.io / pkg.go.dev / rubygems — 視語言

**Awesome lists**：
- `WebSearch` `awesome <topic> site:github.com`
- 找到後 `WebFetch` 對應 `awesome-xxx` README 掃目錄

**社群討論**（選用）：
- `WebSearch` `<idea> hacker news` 或 `site:news.ycombinator.com`
- `WebSearch` `<idea> reddit r/programming`

**Product Hunt / AlternativeTo**（選用，適合 end-user tool）。

**禁忌**：
- ❌ 不要只靠 WebSearch title snippet 下結論 — 要進 repo 看 README 和 last commit
- ❌ 不要信模糊描述「There are many tools that do this」— 要給**具體 repo**
- ❌ 不要拿一個舊 fork 當主流代表 — 找 canonical upstream

### Phase 3：Shortlist（3–5 個最近的）

從 Phase 2 候選挑 3–5 個**最接近 core function** 的。排除條件：
- 已 archive / 最後 commit > 3 年（除非真的沒別人做）
- Star 過低且無明確 niche 證據（< 50 star 且 README 寥寥幾行）
- 實際功能不相關（keyword match 但做的事不同）

對每個 shortlist 項目抓：
```bash
gh api repos/{owner}/{repo} --jq '{stars: .stargazers_count, forks: .forks_count, updated: .updated_at, lang: .language, license: .license.spdx_id, archived: .archived, topics: .topics}'
gh api repos/{owner}/{repo}/commits --jq '.[0].commit.author.date' | head -1   # last commit date
```

若需要比對功能，`gh api repos/{owner}/{repo}/readme --jq '.content' | base64 -d | head -100` 快速抓 README 前 100 行。

### Phase 4：Wheel Scoring

對**整個點子**（不是單個 repo）打一個 Wheel Score 0–100。組成：

| 面向 | 分數 | 如何評 |
|------|------|-------|
| **Core feature overlap** | 0–40 | 現成方案覆蓋點子核心功能的 %。100% 覆蓋 = 40 分 |
| **Maintenance health** | 0–15 | 最佳候選是否活躍（最近一年有 commit、issue 有回、有 release）。活躍 = 15，半死 = 7，archived = 0 |
| **Production readiness** | 0–15 | 有 1.0+ release、有 tests、有文檔、被 downstream 依賴。齊 = 15 |
| **License compatibility** | 0–10 | 可商用/可 fork 的許可證（MIT/Apache/BSD）= 10；GPL 視情況 5–8；無 license = 0 |
| **Ecosystem pull** | 0–10 | 社群/插件/整合生態強度。標竿（e.g. VSCode、React）= 10 |
| **Differentiation gap (inverse)** | 0–10 | 使用者列的 differentiators 能否真的站得住腳。完全站不住（現成已有）= 10；有明確 niche 空間 = 0 |

**總分 → Verdict**：

- **🟢 0–25：Build it**。真的沒人做過，或現成的太陽春/太舊/不活。放心寫。
- **🟡 26–55：Build with clear angle**。有類似但點子 differentiator 明顯站得住。寫之前在 README 第一段就講清楚「為什麼不用 X」。
- **🟠 56–80：Fork, contribute, or pivot**。高度重疊，從頭寫多半是浪費生命。選一：(a) fork 最近的一個改你要的、(b) 對 upstream 提 PR / feature request、(c) pivot 到真正沒人做的鄰近問題。
- **🔴 81–100：Just use the existing one**。純造輪。花一小時學現成的比花一個月自己寫划算。若仍要寫，理由應該是「為了學」而非「為了用」—— 明確標記這是練習專案。

### Phase 5：Report

輸出格式：

```markdown
## No-Wheels Report：`<idea 一句話>`

**Core function**：<動詞 + 名詞>
**Target**：<誰在什麼情境用>
**User's differentiators**：<使用者自認賣點；若無寫「未提供」>

### Top candidates

| # | Repo | ⭐ | Last commit | License | Overlap | 備註 |
|---|------|---|------------|---------|---------|------|
| 1 | [owner/name](url) | xxk | YYYY-MM | MIT | ~80% | <一句話> |
| 2 | ... | ... | ... | ... | ... | ... |
| 3 | ... | ... | ... | ... | ... | ... |

### Wheel Score：**XX / 100** → **{🟢/🟡/🟠/🔴} {verdict}**

| 面向 | 分數 | 理由 |
|------|------|------|
| Core feature overlap | XX/40 | ... |
| Maintenance health | XX/15 | ... |
| Production readiness | XX/15 | ... |
| License compatibility | XX/10 | ... |
| Ecosystem pull | XX/10 | ... |
| Differentiation gap (inverse) | XX/10 | ... |

### 建議

<一段具體建議：build / pivot / fork / use existing>。若 pivot，指出真正的空缺在哪。若 fork，指出最值得 fork 的那個。若 use existing，一句話講怎麼上手。

### 使用者的下一步決策

問使用者：是否仍要 build？要 build 的話是為了**用**還是為了**學**？這影響後續投入。
```

---

## 邊界與禁止事項

- ❌ 不評估點子本身**值不值得做**（商業/學習價值）— 只評估是不是造輪
- ❌ 不自動開始寫 code — Phase 5 之後等使用者決策
- ❌ 不編造 repo — 每個 shortlist 項目都要有可點擊 URL，搜不到就說搜不到
- ❌ 不只搜英文 — 中文/日文生態（e.g. 繁中工具、日本開發者的 niche lib）也要掃一輪
- ❌ 不省略 Phase 1 — 點子描述不清就搜不到對的東西，直接問比亂搜好
- ❌ 不把「大公司出的」當絕對否決 — 有時候大公司方案太笨重，個人輕量版反而有空間

---

## 邊角情境處理

- **點子是把 A+B 整合**：分別搜 A、B、以及「A B integration」三組。整合類點子造輪分數通常偏低，因為「整合」本身就是 differentiator。
- **點子是「給 X 的 Y」**（e.g. 給醫師的 markdown editor）：niche 特定性高，重點搜 niche 市場而非通用方案。通用方案 10k star 不代表 niche 市場已飽和。
- **點子是 LLM wrapper / AI feature**：2024+ LLM 類 idea 造輪率極高，要特別用力搜（每週都有新專案）。重點看是否真有不可取代的 prompt engineering / UX / 資料集。
- **點子是 CLI 工具**：GitHub + awesome-cli 類 list + Homebrew formula list 三個來源一起掃。
- **點子是 Claude Code / AI agent skill**：額外搜 GitHub 上的 skills / plugin marketplace 與 `awesome-claude-code` 類清單，再走本 skill 流程。

---

## Resources

本版暫無 references 子檔。若未來發現需要（e.g. 各語言 package registry 的搜尋技巧、license compatibility 表），再抽出來。

---

## 既有相關 skill

- `hypothesis-generation`：**研究**點子發想（非 coding）— 不同方向
- `deep-research`：**醫學/科學**深度調研 — 不同領域

本 skill 專責「coding idea → prior art 掃 → 造輪程度判定」，與上述都不衝突。

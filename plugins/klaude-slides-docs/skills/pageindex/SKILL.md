---
name: pageindex
description: 對單一長 PDF（guideline / textbook / paper / 考古題本）做精準 reasoning-based Q&A。用 PageIndex（VectifyAI 的 tree-index RAG，非 vector embedding）建文件結構樹，再以 LLM 推理定位 → 取頁 → 答題，回答附 [p.X] 頁碼引用。預設透過 Claude Code OAuth subscription（不需 API key），可一鍵切換到 Anthropic API key。Trigger - `/pageindex`、`/pi`、使用者提及「索引這份 PDF」「查 guideline 第幾頁有 X」「對這篇 paper 問 Q」「PDF 精準查」「textbook 速查」「ESC HF 對 NYHA III 怎麼建議」「NCCN sarcoma margin」「考古題本 atrial fibrillation 考過幾題」。
---

# PageIndex — Single-PDF Precision Q&A

## When to use

✅ **走這個 skill**：對**單一**長 PDF 問**特定問題**、要**頁碼引用**、文件已在你電腦上、你要的是事實查詢而非綜合創作。
- ESC HF Guideline 2023 → 「NYHA III 病人的 sacubitril/valsartan 建議是什麼」
- 歷年考古題本 PDF → 「atrial fibrillation 出過幾題」
- 內科教科書章節 PDF → 「acute MI 的 reperfusion 時間窗」
- NCCN Sarcoma v2.2026 → 「soft tissue sarcoma 切除 margin」
- 課程講義 → 「動量守恆題目分布在哪幾章」

❌ **不要走這個 skill**（路由到別處）：
- 跨 ≥3 文件的綜合 / podcast / video → NotebookLM（選用）
- 系統性文獻回顧（從零搜尋 + 篩選）→ `/deep-research`
- 即時臨床問題（不限定文件）→ `/openevidence` 或 `/medq`
- PDF → markdown 後人工閱讀 → `/marker-pdf-converter`

## 安裝（朋友第一次使用，只需一次）

需要：Python 3.10+、`git`、已登入的 Claude Code CLI（`claude` 在 PATH 上）。上游 PageIndex 是 VectifyAI 的開源專案（MIT license，https://github.com/VectifyAI/PageIndex）；本 skill 只附橋接與 CLI 包裝，**不含**上游程式碼，要自己 clone：

```bash
mkdir -p ~/PageIndex && cd ~/PageIndex
git clone https://github.com/VectifyAI/PageIndex.git repo
python3 -m venv .venv
.venv/bin/pip install -r repo/requirements.txt
# 驗證
.venv/bin/python ${CLAUDE_SKILL_DIR}/lib/run.py doctor
```

不用改上游任何檔案：`run.py` 會自己註冊 `claude-code/*` 這個 litellm provider（走 `claude -p`，用你的 Claude Code 訂閱，不需 API key）。若想改用 Anthropic API key：`/pageindex switch-llm api`，再編輯 `~/PageIndex/.env` 填入 `ANTHROPIC_API_KEY`（只存在你自己電腦上，勿提交到 git）。

Attribution：PageIndex © VectifyAI，MIT License；本 skill 為其非官方的 Claude Code 整合。

## Architecture

```
~/PageIndex/
├── repo/              git clone of VectifyAI/PageIndex
├── .venv/             Python venv (litellm, pymupdf, PyPDF2, dotenv, yaml)
├── .env               PAGEINDEX_MODEL + (optional) ANTHROPIC_API_KEY
├── library/           PDF storage by topic (cardio/exam/nccn/physics_chem/misc)
└── indexes/           cached tree JSON per doc (PageIndex workspace)

${CLAUDE_SKILL_DIR}/
├── SKILL.md           this file
└── lib/
    ├── claude_code_provider.py   litellm CustomLLM → claude -p subprocess
    ├── library.py                library directory + meta helpers
    └── run.py                    CLI dispatcher (index/ask/list/search/...)
```

**LLM auth**：預設走 Claude Code OAuth bridge（`PAGEINDEX_MODEL=claude-code/haiku`）— 透過 `claude -p` headless subprocess 呼叫 user 的 Claude Code 訂閱，**不需 API key**。要切 Anthropic API key 直接付費路線，跑 `/pageindex switch-llm api`。

## Subcommands

| 指令 | 用途 | 範例 |
|---|---|---|
| `/pageindex index <pdf-path>` | 建 tree index，PDF 自動歸類到 `library/<topic>/` | `/pageindex index ~/Downloads/ESC_HF_2023.pdf` |
| `/pageindex ask <pdf-name> <question>` | 對 indexed PDF 問問題（fuzzy match 名字）| `/pageindex ask ESC_HF "NYHA III 用藥"` |
| `/pageindex list [<topic>]` | 列出 indexed docs + library 檔案 | `/pageindex list cardio` |
| `/pageindex search <keyword>` | 跨所有 indexed docs 找關鍵字所在頁碼 | `/pageindex search "ejection fraction"` |
| `/pageindex remove <pdf-name>` | 移除 index + meta（PDF 仍留在 library/）| `/pageindex remove old_paper` |
| `/pageindex switch-llm <oauth\|api>` | 切換 LLM 路線（改 .env） | `/pageindex switch-llm api` |
| `/pageindex doctor` | 診斷環境（claude CLI / venv / deps / library count） | `/pageindex doctor` |

`/pi` 是 `/pageindex` 的 alias。

## How Claude executes a subcommand

當使用者打 `/pageindex <subcmd> <args>` 時，Claude 直接 Bash 呼叫：

```bash
~/PageIndex/.venv/bin/python ${CLAUDE_SKILL_DIR}/lib/run.py <subcmd> <args>
```

run.py 內部會：
1. 從 `~/PageIndex/.env` 載 `PAGEINDEX_MODEL`
2. `index` / `ask` / `search` / 等：實例化 `PageIndexClient(workspace=~/PageIndex/indexes/, model=..., retrieve_model=...)`
3. PageIndex 透過 litellm 呼叫 LLM → litellm 看到 `claude-code/...` model name → 路由到 `ClaudeCodeLLM` provider → subprocess `claude -p ...` → 回 JSON → 轉 ModelResponse
4. 回應印 stdout

不要繞過 run.py 直接呼叫 PageIndex CLI — 會少了 library 自動歸類、fuzzy match、env 載入等便利功能。

## Cookbook（依使用情境）

### 情境 1：guideline 速查 + paper 細節

```bash
# 一次性 indexing（200+ 頁 guideline 約需 5–15 分鐘）
/pageindex index ~/Downloads/ESC_HF_Guidelines_2023.pdf
# → 自動歸類 cardio/，cache 到 ~/PageIndex/indexes/

# 連續問問題（同一 cache window 內速度快）
/pageindex ask ESC_HF "NYHA III HFrEF 的 sacubitril/valsartan 建議是什麼"
/pageindex ask ESC_HF "loop diuretic 起始劑量與調整原則"
/pageindex ask ESC_HF "什麼時候考慮 ICD"

# 跨多份 cardio paper 找關鍵字
/pageindex search "primary endpoint"
```


### 情境 2：考試準備 — 考古題本 + 教科書速查

```bash
/pageindex index ~/Documents/exams/past-exam.pdf --topic exam
/pageindex ask past-exam "atrial fibrillation 考過幾題，分別是什麼"
/pageindex ask IM_Textbook_HF "acute decompensated HF 的 first-line 處置"

# 跨所有 exam PDFs 找一個主題
/pageindex search "atrial fibrillation"
```


### 情境 3：NCCN / 各類 guideline PDF

```bash
/pageindex index ~/Downloads/NCCN_Sarcoma_v2.2026.pdf --topic nccn
/pageindex ask NCCN_Sarcoma "soft tissue sarcoma 切除 margin 建議"
/pageindex ask NCCN_RCC "Stage III RCC 的 adjuvant therapy"
```

（NCCN PDF 需自行向 NCCN 取得，勿再散布。）

### 情境 4：課程講義

```bash
/pageindex index ~/Documents/lecture-notes.pdf --topic physics_chem
/pageindex ask lecture-notes "動量守恆相關題目 + 解答關鍵步驟"
/pageindex ask 化學課本 "電化學課本講到哪些反應方程式範例"
```

## Best practices（避坑）

1. **連續問完同一份 PDF 再切**：每個 `claude -p` cold call 約 6–7 秒、cache window 5 min–1 h。同一份 PDF 一次問完所有想知道的事，比分散 3 天每次重起更省時間 + 配額。
2. **長 indexing 一次跑完**：200 頁 guideline 索引可能要 5–15 分鐘。在你方便等的時段啟動，不要中途中斷（中斷後 PageIndex 沒 incremental resume）。
3. **scanned PDF 先轉 markdown**：PageIndex 用 PyPDF2 + pymupdf 抽 text，掃描檔抽不到字。先用 `/marker-pdf-converter`（marker 引擎）轉 markdown，再 `/pageindex index <md-path>` — PageIndex 也接 markdown。
4. **中文 PDF 先小規模驗證**：FinanceBench benchmark 是英文。中文長文件（考試教材、課程講義）建議先 index 一份小的、`ask` 一兩個你已知答案的問題確認 retrieval 品質，再 index 整套教材。
5. **配額警告就切 API**：Claude Code 訂閱配額快滿時 `/pageindex switch-llm api` + 設 `ANTHROPIC_API_KEY` → Haiku 處理單份長 guideline 估計低成本。

## Troubleshooting

| 症狀 | 處置 |
|---|---|
| `claude CLI failed (exit 1)` | 跑 `claude --version` 確認 binary 在 PATH；跑 `claude auth status` 確認 OAuth session 有效 |
| `litellm.exceptions.AuthenticationError: OPENAI_API_KEY` | utils.py 應該已經設 sentinel，跑 `/pageindex doctor` 看 .env 是否被某個地方 override |
| `FileNotFoundError: ~/PageIndex/.venv/bin/python` | venv 沒建好，重跑 `python3 -m venv ~/PageIndex/.venv && ~/PageIndex/.venv/bin/pip install -r ~/PageIndex/repo/requirements.txt` |
| Q&A 回答完全離題 | 先跑 `/pageindex search <關鍵字>` 看 PageIndex 找不找得到該關鍵字。找不到 = retrieval 失敗，檢查 PDF 是否為 scanned / OCR 差 |
| 中文 PDF 回答品質差 | 切 sonnet：改 `.env` 的 `PAGEINDEX_RETRIEVE_MODEL=claude-code/sonnet`（locate 仍可保 haiku） |
| `claude -p` cold call 超過 30 秒 | 網路 / Anthropic API 端慢；不是 bug。可考慮切 API 路線（直連 API 通常 < 5s） |

## Cross-reference

- 上游 repo：https://github.com/VectifyAI/PageIndex
- 跟 NotebookLM（選用）的分工：單文件精準查 → PageIndex；多文件知識整合 → NotebookLM
- LLM 切 API 路線後跟 Anthropic API 文件：https://docs.claude.com/en/docs/api-reference/messages

## Why PageIndex（簡述厲害之處）

- **不切 chunk、不算 embedding**：直接讀整本 PDF → LLM 推理建出階層樹（章節 → 子節 → 段落），保留**結構語意**
- **Retrieval = 樹搜索 + LLM 推理**：query 進來後 LLM 看 tree 決定該去哪個 page range，比向量相似度更接近人類「翻 TOC 找章節」的直覺
- **避開 vector RAG 的兩個陷阱**：(a) similarity ≠ relevance（語義相似不等於問題答案）、(b) chunk boundary 切爛上下文
- **FinanceBench 98.7%** vs 一般 vector RAG 70–85%，特別擅長財報 / guideline / textbook 這類**結構強烈的長文件**
- **MIT license**：個人 / 商用都 OK

---
name: medq
description: "即時醫學問答 + OE citation 驗證。Claude 用本身模型依 IM / Surgery / Biostat persona 內部草擬答案與 atomic claims（不輸出給使用者），送 OpenEvidence MCP 驗證（沒有 OE MCP 時自動改用 PubMed MCP / 網路搜尋驗證）後整合成**單一回覆**：citation 以 inline `[N]` 標在句後，被 OE 反對或補強的 claim 以 inline 散文呈現（不另開 Verification 區塊），文末附 AMA references。觸發關鍵詞：/medq、幫我查一下 XXX、XXX first-line 是什麼、XXX 要怎麼處理（要 citation）、需要 citation 的即時臨床問題。"
---

# MedQ — 即時醫學問答 + OE 驗證

## 定位

Claude 用本身模型答（結構化、速度快），同步用 OE 驗證並附 citation。**使用者只看到一份整合版**：Claude 的內部草稿不輸出，citation 與衝突註記直接 inline 寫進最終回覆，大幅節省 context。

**與 OE 家族分工**：
| Skill | 速度 | 輸出 | 用途 |
|-------|-----|------|------|
| `/openevidence`（`/oe`） | 中 | OE 原文整理 | 純 evidence 查詢 |
| `/medq` | **中（單次 OE）** | **單一整合回覆（inline citation）** | 即時 Q&A + citation |
| `/oe-triangulate` | 最慢（dual + PubMed） | 三角驗證報告 | 重大決策 / paper |

---

## 工作流程（3 Stage，Claude 主 session inline 執行）

### Stage 0 — Routing

#### 手動 override（最高優先）
| Prefix | 路由 | 範例 |
|--------|------|------|
| `im:` | 內科 | `/medq im: SGLT2 in HFrEF` |
| `sx:` | 外科 | `/medq sx: Calot triangle` |
| `stat:` | 生統 | `/medq stat: competing risk vs Cox` |

#### 自動偵測（無 override，順序 sx → stat → im）

**外科（sx）** keywords：
`-ectomy`, `-otomy`, `-plasty`, `-ostomy`, `-pexy`, `-orrhaphy`, `laparoscopic`, `robotic`, `thoracoscopic`, `bypass`, `graft`, `anastomosis`, `resection`, `excision`, `dissection`, `CABG`, `Whipple`, `transplant surgery`, 手術, 切除, 修補, 重建, 縫合, 跟刀, 術式

**生統（stat）** keywords：
`regression`, `survival`, `meta-analysis`, `RCT`, `Cox`, `Kaplan`, `propensity`, `PSM`, `odds ratio`, `hazard ratio`, `confidence interval`, `AUC`, `ROC`, `p-value`, `CI`, `Bayesian`, `logistic`, `ANOVA`, `t-test`, `chi-square`, `Fisher`, `Wilcoxon`, `Mann-Whitney`, `GEE`, `competing risk`, `IPW`, `IPTW`, `forest plot`, `funnel plot`, `heterogeneity`, `subgroup`, 統計, 回歸, 存活

**內科（im）**：default。

---

### Stage 1 — 內部草稿（**不輸出給使用者**，必須在 Stage 2 前完成）

#### Step 1.1 — 組 self-prompt（persona priming）

```bash
PROMPT=$(python3 ${CLAUDE_SKILL_DIR}/scripts/assemble_medq_prompt.py \
  --gem {im|sx|stat} --topic "{原問題}")
```

Prompt 結構：`<Context>persona</Context>` + `<OutputFormat>compact template + CLAIMS block + TERM_RULES</OutputFormat>` + `<Task>原問題</Task>`。

#### Step 1.2 — Claude 內部草擬答案 + CLAIMS

**在主 session 回覆中「不輸出」這份草稿**。**草稿必須持久化到 scratch file**（thinking block 不 persist，session evict / context 壓力下會遺失，無法在 Stage 2 preflight 驗證 Stage 1 已完成）：

1. **（強制）Scratch file 寫入**：`Write` 到 `/tmp/medq_draft_<timestamp>_<pid>.md`。即使用 thinking block 先展開推理，**thinking 完必須把答案骨架 + CLAIMS flush 到 scratch file**，否則 Stage 2 preflight 會 fail。
2. **Thinking block 輔助（選用）**：可在 extended thinking 內先推理 / 拆解，但只做中間過程；最終 commit 一定要落到 scratch file。

草稿內容必填：
- 主段骨架（依 persona template：IM = Answer/Key Points/Caveats；SX = Summary/Indication/Key Steps/Complications；STAT = When to Use/How/Interpretation/Pitfalls）
- `<!-- MEDQ_CLAIMS_START -->` ... `<!-- MEDQ_CLAIMS_END -->` block，≤5 條 atomic claim

**Why flush 硬規則**：thinking block 會隨 context 壓縮消失，Stage 2 無法檢查 Stage 1 是否完成；草稿落成檔案才能確保「先 commit 自己的判斷、再看外部證據」。

#### Step 1.3 — 獨立性硬規則

**Stage 1 必須完整寫完才能啟動 Stage 2 `oe_ask`**。不可 parallel、不可讓 OE 結果先進 context prime Stage 1。這是「整合時能誠實標 CONTRADICTED」的前提——Claude 必須先 commit 到自己的判斷，再看 OE 說什麼。

完成判定（硬性）：`/tmp/medq_draft_<ts>_<pid>.md` 檔案已 Write 成功、含完整答案骨架 + 完整 `MEDQ_CLAIMS_START/END` block。Stage 2 preflight 會 Read 此檔驗證。

---

### Stage 2 — OE 驗證（單次）

#### Step 2.1 — Preflight

**2.1a. Stage 1 artifact 存在性硬檢查（必跑）**：

```
# 1. 找最新 scratch file
LATEST_DRAFT=$(ls -t /tmp/medq_draft_*.md 2>/dev/null | head -1)
if [ -z "$LATEST_DRAFT" ]; then
  echo "ERROR: Stage 1 artifact missing. /tmp/medq_draft_*.md not found. Do not proceed to Stage 2."
  exit 2
fi
# 2. Read 並驗證 CLAIMS block
Read "$LATEST_DRAFT"
# Must contain both MEDQ_CLAIMS_START and MEDQ_CLAIMS_END markers with non-empty content between
```

若檔案不存在或 CLAIMS block 缺失／為空 → **STOP**，回報「Stage 1 未完成：scratch file $LATEST_DRAFT 缺 CLAIMS block」。不 fall through，不繼續發 oe_ask（避免 OE 結果 prime Stage 1，違反獨立性）。

**2.1b. 選驗證來源（OE 優先，缺才降級）**：

1. 若有 `mcp__openevidence__*` 工具（deferred 時先用 ToolSearch 載入）→ 呼叫 `mcp__openevidence__oe_auth_status`，通過就走下方 Step 2.2–2.5（OE 路徑）。
2. OE MCP **未安裝**或 auth 失敗 → 走 **Step 2-alt（PubMed / 網路搜尋降級路徑）**，並在最終輸出文末加一行：`ℹ️ 本次未使用 OpenEvidence 驗證（未安裝或未登入）；citation 來自 PubMed / 網路搜尋。` 安裝方式見 `${CLAUDE_SKILL_DIR}/../openevidence/SETUP.md`。
3. 三者（OE、PubMed MCP、網路搜尋）皆不可用 → skip Stage 2、3，把草稿整理成最終輸出，文末加 `⚠️ 驗證來源皆不可用，以下內容未經 citation 驗證。`，**不 abort**。

#### Step 2-alt — 降級驗證（無 OE 時）

1. 從 CLAIMS 中挑最關鍵的 2–3 條（治療決策 / 數值 / 絕對字眼優先）。
2. 對每條用 `mcp__pubmed__pubmed_search_articles`（英文 PICO query，偏好 guideline / meta-analysis / RCT，近年優先）→ `mcp__pubmed__pubmed_fetch_articles` 取 abstract。沒有 PubMed MCP → 用網路搜尋（優先 guideline 官網、PubMed、PMC）。
3. 以 abstract 原文對照 claim 判 verdict（規則同 Stage 3）；**只能依 abstract 能讀到的內容判斷**，沒讀到全文的數值標 `（僅依摘要）`。
4. 整理成與 OE 路徑相同格式的 `[N]` inline citation 與 References（PMID / DOI），直接進 Stage 3。覆蓋有限時在 Caveats 說明「驗證僅涵蓋 N 條關鍵 claim」。
5. 此路徑的 citation 品質低於 OE 整理過的答案，不要宣稱「經 OE 驗證」。

#### Step 2.2 — 把原問題改寫成英文 query

**不逐字翻譯**。保留 PICO 三要素：population / intervention（或 exposure）/ outcome。例：

- 原：「糖尿病合併 HFrEF 該用哪類降血糖藥？」
- 英：`"In patients with type 2 diabetes and heart failure with reduced ejection fraction, which glucose-lowering agents improve cardiovascular outcomes?"`

英文 query 不再獨立開一行給使用者看；若與原題旨有明顯 drift，在最終輸出的 Caveats / Pitfalls 段以一句話說明。

#### Step 2.3 — Cache hit check（先查 history，命中就跳過新查詢）

送 `oe_ask` 前**一律**先跑：

```
mcp__openevidence__oe_history_list
```

掃回傳結果，找出符合**兩個條件**的舊 article：

1. **Time window**：建立時間在**過去 30 分鐘**內（UTC `datetime_created` 比對 `date -u +%s` - 1800）
2. **Semantic similarity**：舊 query 與當前英文 query 的核心 PICO token（藥名 / 手術名 / 族群 / outcome）**交集 ≥ 3 個主要 token**，或完全相同子句 ≥ 70%

命中時：
```
mcp__openevidence__oe_article_get(article_id="<hit_uuid>")
```
（< 5 秒），跳過 Step 2.4 的 `oe_ask`，直接進 Step 2.5 parse。整合時在 Caveats / Pitfalls 段加一句「此回覆復用 <N> 分鐘前的 OE article」。

未命中 → 繼續 Step 2.4。

#### Step 2.4 — 呼叫 OE（僅 cache 未命中時）

```
mcp__openevidence__oe_ask(question="<english query>", timeout_sec=120, poll_interval_ms=1200)
```

不帶 `original_article_id`（單次查詢）。Response 超 MCP limit 會 auto-save `.txt`，路徑在 tool result 的訊息裡。

**🖼 Figure handling（必跑）**：OE 回應若 `article.json` 含 `REACTCOMPONENT!:!PublicationFigure` → 依 `${CLAUDE_SKILL_DIR}/../openevidence/SKILL.md` step 6+7 處理（`download_figures.py` 下載 → 輸出最後列表 → 呼叫 `AskUserQuestion` 問去向）。medq 產物是 inline 回覆，預設選項 `markdown`（直接嵌進最終回覆 body）；NCCN flowchart 特別 surface 給使用者看。

#### Step 2.5 — Parse（立即鏈接，不穿插其他 tool）

**拿到 OE tool result 後，下一個 tool call 必須是 parse_oe.py Bash**，中間不 Read、不 Glob、不檢查檔案是否存在（parse_oe.py 內建 check）。這條規則是為了避免多跑 1–2 次 tool round trip（每次 ~1–2 秒）。

> **OE artifact path 安全性**：medq 走 `parse_oe.py <raw_json>` 路徑，**parse_oe.py 內建從原始 JSON 自己 dedup citations + 重新編號**，所以**不會踩** `answer.md + citations.json` 的 orphan citation 陷阱。若未來 medq 改走 artifact path 讀 `answer.md`，inline `[N]` 超出 citations.json 範圍的 re-cite 會被誤判 → 必須改用 `${CLAUDE_SKILL_DIR}/../openevidence/scripts/unify_artifacts.py` 從 `article.json` 重建。詳見 OE SKILL.md「Artifacts 路徑」section。

```bash
python3 ${CLAUDE_SKILL_DIR}/../openevidence/scripts/parse_oe.py <saved_txt_path>
```

輸出：
- Line 1: `ARTICLE_ID: <uuid>`
- Body: cleaned text（inline `[N]` citation 已編號）
- Tail: `---\nReferences\n\n1. ...\n2. ...`

若 MCP 回 inline JSON（罕見），在**同一個 Bash call** 裡先 heredoc 寫 `/tmp/medq_oe_$$.json` 再 parse，不開第二個 Bash。

---

### Stage 3 — Integration（把 Stage 1 草稿與 OE 結果合併成單一回覆）

#### Step 3.1 — 取 CLAIMS + semantic match

從 Stage 1 scratch（thinking 或 `/tmp/medq_draft_*.md`）抽 CLAIMS。若漏產，從草稿正文 fallback 重挑：
1. 含數值句優先（HR、% reduction、cutoff、劑量）
2. 含藥名 / 手術名 / 診斷標準名的句子
3. 含 `contraindicated / first-line / do not / recommended` 絕對字眼
4. 純定義、背景鋪陳句跳過

對每個 CLAIM_i：
1. 在 parse_oe.py body 找最相關 2–3 句（用藥名 / 英文 keyword / 數值當 anchor，不要只比中文字串）
2. 抓句後緊跟的 `[N]` 或 `[N,M]` 當 citation 編號
3. 對回文末 References AMA line

#### Step 3.2 — 三種 verdict 的 inline 呈現

**不輸出 verdict 表格**。三種情況分別以自然語言融入內文：

| Verdict | OE body 對照結果 | Inline 呈現方式 |
|---------|----------------|---------------|
| ✅ **SUPPORTED** | 方向一致、數值相符 ±20% | 句末直接加 `[N]`，不加額外註解 |
| ❌ **CONTRADICTED** | 反方向 / 數值差 >2x | 保留 Claude 原句，緊接一句 inline 衝突註記：**「⚠️ 此點與近期證據不一致：〔OE 具體數據〕[N]」** |
| ⚠️ **NOT_MENTIONED** | OE 完全沒提到 claim 主體 | 句末加 `[未被 OE 覆蓋]` 或保持原樣不加 citation（若非關鍵 claim 可靜默） |

Critical claim（治療決策、dose、cutoff）被標 NOT_MENTIONED 時，**必須** 顯式註明未覆蓋；非關鍵背景句可省略。

#### Step 3.3 — 關鍵規則

遇到 ❌ CONTRADICTED **不自動改 Stage 1 原句**。把 Claude 原答保留、緊接一句 inline 衝突註記呈現兩造，讓使用者自己判斷。避免被 OE 單一來源牽著走。

---

## 最終輸出格式

**單一整合回覆，無 Verification 區塊、無 verdict 表格**。依 persona template 輸出主段，citation 以 inline `[N]` 標記，文末附 References。

### IM / SX / STAT 共用外框

```markdown
## <persona 段標題 1，例如 Summary / Answer / When to Use>
<主段內文，句末加 [N] citation；遇 CONTRADICTED 在原句後接一句「⚠️ 此點與近期證據不一致：…[M]」；critical NOT_MENTIONED claim 加 `[未被 OE 覆蓋]`>

## <段標題 2>
- bullet 1 [N]
- bullet 2（⚠️ 此點與近期證據不一致：…[M]）

## <段標題 3>
- ...

## Caveats / Pitfalls
- ...
- 若 OE 對此主題覆蓋薄弱（>50% claim 為 NOT_MENTIONED），在此段加一句：「本題 OE 覆蓋不足，建議以教科書補強。」
- 若英文 query 與原題旨有明顯 drift，在此段註明。

---

## References

1. <parse_oe.py 文末 AMA line，含 PMID / DOI link>
2. ...
```

### 段標題對應 persona

| Persona | 段標題（依序） |
|---------|---------------|
| IM | `## Answer` / `## Key Points` / `## Caveats` |
| SX | `## Summary` / `## Indication` / `## Key Steps` / `## Complications` / `## Caveats` |
| STAT | `## When to Use` / `## How` / `## Interpretation` / `## Pitfalls` |

### 長度

整合後主段 < 800 字（比舊版 < 600 字略放寬，因為 inline citation 與衝突註記佔字數）。References 不計入字數。

---

## Edge Cases

1. **OE auth fail / 未安裝 / 空回**：走 Step 2-alt 降級路徑；降級也不可用才直接輸出主段，文末加 `⚠️ 驗證來源皆不可用，以下內容未經 citation 驗證。`，省略 References 段。
2. **全 NOT_MENTIONED**：常見於 sx 技術步驟、stat 方法學。Caveats 段提示「建議對照教科書」；主段 inline 不加 citation，保持乾淨。
3. **OE contradicts Claude**：`⚠️ 此點與近期證據不一致` inline 註記，原句保留不改。
4. **Stage 1 漏產 CLAIMS**：用 Step 3.1 fallback 規則重抓（從草稿正文挑含數值 / 藥名 / 絕對字眼的句子）。
5. **Query drift**：英文轉譯改變題旨時，在 Caveats / Pitfalls 段明示「OE 驗證僅覆蓋臨床面，原題術式細節未被覆蓋」。
6. **Citation 編號**：parse_oe.py 已 dedup + counter，直接沿用 `[N]`，不重編號。
7. **獨立性**：Stage 1 草稿必須在 `oe_ask` 呼叫前完整 commit（thinking 或 scratch file），絕不可看完 OE 才寫草稿。
8. **Scratch file 清理**：Stage 3 完成後，`/tmp/medq_draft_*.md` 可留著當 session audit trail，不強制刪除；使用者看不到內容，不佔主 context。
9. **Cache hit（Step 2.3）**：命中時 `oe_article_get` < 5 秒拿到舊 article，整合時 Caveats 段須明示「此回覆復用 N 分鐘前的 OE article」讓使用者知道 citation 不是剛生成的。若舊 article 年份 / 數據在 30 分鐘內仍合理則可用；若使用者明說「要最新證據」則 bypass cache 直接 `oe_ask`。
10. **Parse 鏈接規則**：`oe_ask` 與 `parse_oe.py` 之間若穿插 Read / Glob / 檔案存在檢查，視為違反 Step 2.5；parse_oe.py 自己會 handle 所有 edge case。

---

## 不做的事

- ❌ 不輸出 Stage 1 原始草稿給使用者（context 節省的核心）
- ❌ 不另開 `## OpenEvidence Verification` 區塊或 verdict 表格
- ❌ 不呼叫其他外部模型、不派生成 subagent
- ❌ 不做 per-citation 的多 agent 稽核（太慢；要深度驗證升級走 `/oe-triangulate`，或選用上游 `audit-oe`）
- ❌ 不做完整 cross-check（有 OE 時只做單次 OE；降級路徑才用 PubMed 驗最關鍵的 2–3 條）
- ❌ 不自動改 Claude Answer 去配合 OE（CONTRADICTED 以 inline 註記呈現兩造）

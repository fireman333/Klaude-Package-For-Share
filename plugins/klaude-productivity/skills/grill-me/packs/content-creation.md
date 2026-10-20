---
pack: content-creation
triggers: [寫文章, pptx, 投稿, 公開文, 部落格, Threads, 報告, 心得文, 醫普, Medium, 粉專, 投影片, 簡報, 演講稿, 講稿]
applicable_modes: [quick, deep]
default_callers: [使用者直接呼叫，pre-write 階段]
---

# Content Creation Facet Pack

對寫公開文 / 報告 / pptx / 投影片 / 演講稿 / 投稿等 content artifact 的「動筆前」階段。重點：把讀者、目的、最強 claim、反方意見釘下來，才不會寫到一半才發現「方向錯了」。

---

## Facets（按重要性排序）

### F1: Audience（讀者是誰）

**Why it matters**: 決定 vocabulary、深度、引用密度、tone

**Baseline questions**:
- 主要讀者是？（同領域醫師 / 跨領域醫師 / 護理 / 醫學生 / 一般大眾 / 病人 / 家人朋友）
- 他們的領域熟悉度：完全外行 / 略懂 / 同行 / 大師
- 他們現在對這 topic 的態度：感興趣 / 中立 / 抗拒 / 不知道有這 topic

**Follow-up triggers**:
- 答「一般大眾」 → 「醫療術語得換成生活語，有沒有具體一個讀者人物可以想像？」（可搭配你自己的寫作風格 skill，例如 writing-style-builder 產生的）
- 答「同行」 → 「他們已經知道什麼？你的 added value 是？」
- 答「混合」 → 「那要拆兩篇，還是寫一篇但 tier 化？」

---

### F2: Goal / Call to Action（你要他們做什麼）

**Why it matters**: 沒 CTA 的文章 = 寫了沒結果

**Baseline questions**:
- 看完後你希望讀者做什麼？（記得一個重點 / 改變看法 / 採取行動 / 分享 / 私訊你 / 沒打算）
- 一週後他們還記得 1 件事，你希望是什麼？（一句話）
- 文章成功的 metric：閱讀數 / 留言 / 轉發 / 私訊 / 自己滿意 / 沒設

**Follow-up triggers**:
- 答「沒打算」/「沒設 metric」→ 「那為什麼寫？是不是『純記錄』就好不該公開發？」
- 答「改變看法」→ 「需要 evidence 撐，引用密度要拉高」
- 答「採取行動」→ 「具體什麼行動？文末有沒有 step-by-step？」

---

### F3: Strongest Claim（最強的 claim）

**Why it matters**: 讀者會記住的就那 1 句

**Baseline questions**:
- 全文一句話總結：____（30 字內）
- 這句話有多 controversial？（沒爭議 / 略反直覺 / 強烈反主流）
- 你有 evidence 撐這句話嗎？（個人經驗 / 文獻 / 共識 / 沒有）

**Follow-up triggers**:
- 答「30 字寫不出來」 → 「那是還沒想清楚 — 先去想，回來再寫」
- 答「強烈反主流 + 沒 evidence」 → 「這篇會被打很慘，要不要先補文獻或降強度？」
- 答「沒爭議」 → 「沒人會記得 — 要不要找一個更尖的 angle？」

---

### F4: Counter-arguments（反方意見）

**Why it matters**: 預防被質疑時當場語塞

**Baseline questions**:
- 同行最可能怎麼反駁這文章？（具體 1–3 條）
- 你的回應是什麼？（已經寫進文章 / 沒寫但能口頭答 / 答不出來）
- 最 hostile 讀者會抓什麼點？

**Follow-up triggers**:
- 答「答不出來」 → 「先想清楚再發，不然之後會被 KO」
- 答「沒寫進文章」 → 「至少加一段 'one might argue X, but...'」
- 答「不知道誰會反駁」 → 「找一個身邊看法跟你不同的人，先讓他讀」

---

### F5: Platform / Format（發表平台與格式）

**Why it matters**: 不同平台讀者注意力 / 期待 / 演算法不同

**Baseline questions**:
- 發表在哪：個人 blog / Medium / Threads / 粉專 / 學術期刊 / 報告書 / 演講 / 私下分享
- 長度限制：一句話 / 短文（<500 字）/ 中文（500–2000）/ 長文（> 2000）/ 沒限制
- 圖 / 影片 / 互動有沒有計畫？

**Follow-up triggers**:
- 答「Threads」+ 長文 → 「Threads 最佳是 ≤ 500 字短篇，要不要拆連發 thread 或改平台？」
- 答「學術期刊」 → 「目標期刊？impact factor？這應該走 `/academic-paper` 全套」
- 答「演講」 → 「演講稿節奏跟文章不同，需要 spoken language version，建議走 pptx skill 配套」

---

### F6: Tone & Style（語氣風格）

**Why it matters**: 跟 audience / platform 必須一致

**Baseline questions**:
- 風格傾向：學術 / 半學術 / 大眾科普 / 個人觀感 / 諷刺 / 訪談 / 教學
- 第一人稱「我」用多少？（很多 / 適度 / 完全不用）
- 引用密度：每段都要引 / 關鍵 claim 引 / 完全不引

**Follow-up triggers**:
- 答「學術」+ 平台 = 粉專 → 「粉專讀者吃不下學術 tone，要降」
- 答「個人觀感」+ 強 claim → 「需不需要警示讀者『以下個人意見』？」
- 答「完全不引」+ 強 claim → 「容易被當口嗨，引一兩條撐」

---

## 退讓 sentinel

- 「pptx」 + 病例討論 → `/case-discussion-pptx`
- 「pptx」 + 書報討論 / paper 介紹 → `/journal-club-discussion-pptx`
- 「academic paper」（投稿期刊） → `/academic-paper` / `/academic-pipeline`
- 「medical ethics 報告」 → `/ethics-report`
- 「IRB plan」 → `/irb-plan-helper`
- 「manuscript results section」 → `/manuscript-results`

---

## 適用範例

- 「想寫一篇關於工作一年的反思」 → 6 facet 全跑（Quick 版）
- 「醫普文：講低溫療法給家人聽」 → F1 / F2 / F3 / F6
- 「演講稿：分享證照考試準備心得」 → 6 facet

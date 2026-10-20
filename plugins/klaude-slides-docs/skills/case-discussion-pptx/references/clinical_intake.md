# Clinical Intake (Shared)

Canonical 6-question intake spec for any Claude Code skill that produces a clinical case `.pptx` (case discussion, journal club with case anchor, M&M, grand rounds). Answers are written to `CONTENT.clinicalContext` (or equivalent) and drive Slide 9 / 10 strategy.

**Consuming skills**: `case-discussion-pptx` (Step 2.5), `journal-club-discussion-pptx`.

---

## Fixed assumption (do NOT ask)

- **Audience = 師長（attending）（attending / senior）** → 術語用縮寫不展開、假設聽者熟悉 common pathway、Discussion Questions 傾向開放式而非教學 recall

## The 6 questions

Ask all six in one round (e.g. `AskUserQuestion`, or a single numbered list in chat):

| # | 問題 | 輸入類型 | 預設 | 用途 |
|---|---|---|---|---|
| 1 | 這是在哪一個科別遇到的病人？ | free text | — | Slide 1 副標；Tentative Dx 排序；Lab/Image 重點切換（e.g. 心臟科 → 強調 ECG / TnI / Echo） |
| 2 | 病人這次來住院主要處理的問題是？ | free text | — | Slide 1 副標錨點；Slide 3 timeline 以此事件為 anchor 加粗；Slide 7 active problem 置頂 |
| 3 | 有什麼有興趣探討或值得聽者注意的主題？（1–3 條） | free text（多行） | — | 自動帶進 Slide 9 Discussion Questions；相關關鍵字在前 8 張 slide bold |
| 4 | 其他補充？ | free text（可空） | — | Slide 9 旁註 / speaker notes |
| 5 | 預估簡報時長？ | single-choice | `15 min` | `10` / `15` / `20` / `30` min。`≥20 min` 觸發 Slide 10 |
| 6 | Case 類型？（可多選） | multi-choice | 不預選，至少挑 1 | `teaching` / `diagnostic-challenge` / `mnm` / `academic-review` / `management-dilemma` |

## clinicalContext schema

```js
clinicalContext: {
  specialty: "GI / Colorectal surgery",       // Q1
  primaryIssue: "Newly dx sigmoid CA ...",    // Q2
  highlights: ["...", "..."],                 // Q3，1–3 條
  notes: "...",                               // Q4，可空
  duration: "20",                             // Q5: "10" | "15" | "20" | "30"
  caseType: ["mnm", "academic-review"],       // Q6，可多選
  audience: "attending",                      // 固定
}
```

---

## Slide 9 / 10 strategy (auto-decide from answers)

| 條件 | Slide 9 | Slide 10 |
|---|---|---|
| 時長 `10` 或 `15` min **且** highlights ≤ 3 **且** caseType 單選 | Discussion Questions（3 題，由 Q3 highlights 轉寫） | **不產** |
| 時長 `≥ 20 min` **或** highlights > 3 **或** caseType 多選（≥2） **或** caseType 含 `mnm` / `academic-review` | Discussion Questions（3 題） | **產 Slide 10**，內容依 caseType 決定 |

### Slide 9 寫法

用 Q3 highlights 轉寫成**開放式**問題（聽眾 = 師長（attending） → 避免教學 recall 型）。範例：

- highlights `"preop workup for colorectal CA"` → Q: "What preoperative workup do you consider essential for this case, beyond the current CT/CEA?"
- 無 highlights → 保留 `[Discussion question N]` placeholder（不捏造）

### Slide 10 內容模板（caseType → 標題 + bullet）

多選衝突時取**優先序最高者**為主題，其餘 caseType 併入 bullet。

優先序：`mnm` > `academic-review` > `diagnostic-challenge` > `management-dilemma` > `teaching`

| caseType | Slide 10 標題 | Bullet 內容（3–5 點） |
|---|---|---|
| `mnm` | Complication Analysis | root cause / timeline of events / system factor / preventability assessment / action items |
| `academic-review` | Guideline & Literature Anchors | 相關 guideline（NCCN / ESC / ADA…）/ landmark trial / consensus / open questions |
| `diagnostic-challenge` | Differential Diagnosis Deep-dive | top-3 DDx with pros/cons / key distinguishing feature / next test that resolves |
| `management-dilemma` | Decision Framework | option A vs B trade-off / risk-benefit / 病人 preference / SDM key questions |
| `teaching` | Key Teaching Points | 3–5 條 take-home teaching pearls（由 highlights 轉寫） |

### CONTENT.extraSlide schema (when Slide 10 triggered)

```js
extraSlide: {
  title: "Complication Analysis",   // 依 caseType 對照表選
  subtitle: "M&M review",           // optional
  bullets: [
    "Root cause: ...",
    "Timeline of events: ...",
    "System factor: ...",
    "Preventability: ...",
    "Action items: ...",
  ],
}
```

---

## Delegation note

If the calling skill is itself delegated (an upstream skill that already collected the answers), the upstream skill **already collected these 6 answers** and packed them into the intake payload under `clinical_context`. The downstream skill must **not re-ask** — read from the intake payload and proceed.

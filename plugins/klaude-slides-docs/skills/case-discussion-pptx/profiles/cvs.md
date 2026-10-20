---
key: cvs
name: "CVS (Cardiovascular Surgery)"
rotation_display: "範例：心臟外科 (CVS) profile"
# source: /absolute/path/to/your_profile_spec.md   # optional: point to your teacher's spec file
aliases: ["CVS", "cardiovascular surgery", "cardio surgery", "心臟外科", "心血管外科", "心臟血管外科"]

structure: three_act
talk_minutes: 10

slides:
  intro_section_dividers: false
  imaging_emphasis:
    - "valve disease"
    - "coronary lesion"
    - "aortic size"
    - "ascending aorta"
    - "calcification"
    - "regurgitation"
    - "stenosis"
    - "ejection fraction"
    - "EF"
  operative_procedure:
    enabled: true
    title: "Operative Procedure"
    subtitle: "Approach · Key Steps · Reconstruction"
    photo_slots: 3
    require: ["approach", "keySteps"]
  postop_course:
    enabled: true
    title: "Postoperative Course"
    subtitle: "ICU / Ward · Outcome vs Expected · Complications"
  back_to_patient:
    enabled: true
    title: "Back to the Patient"
    subtitle: "Alternative plans · Reflection · Lessons"
  take_home_summary:
    enabled: true
    title: "Take-Home Summary"

intake_extras:
  - id: surgicalIndication
    prompt: "本次手術的 indication — 影像 / 病人表現如何支持「為什麼要開這刀」？（會放進 Operative Procedure slide 的開場）"
    required: true
  - id: operativeApproach
    prompt: "Surgical approach + 關鍵步驟（median sternotomy / minimally invasive / on-pump vs off-pump、CPB time、key reconstruction steps）"
    required: true
  - id: postopOutcome
    prompt: "術後 ICU / ward immediate outcome — extubation timing、hemodynamics、有沒有 complication"
    required: true
  - id: alternativePlans
    prompt: "依文獻 / guideline 還有哪些 alternative 治療？或目前做法 already optimal？"
    required: false
  - id: takeHomeBullets
    prompt: "最後一張 Take-Home Summary 的 3–5 條 take-home message（用條列）"
    required: true

discussion_style: "問題 → 文獻 → 分析 → 回到本例（CVS spec 結構：Case Discussion 段必須走這個流程）"
---

# CVS Case Discussion — Notes for Claude

> 本 body 是 CVS rotation 常見要求的摘要（範例 profile，請依你的老師實際要求調整）；若有 `source:` 指向完整 spec，以該檔為準。

## 報告整體架構

10 分鐘 talk，三段式：

1. **Patient Data** — 基本資料 / 臨床表現 / 檢查影像 / 手術 indication / 手術內容 / 術後狀況
2. **Case Discussion** — 從病人特殊之處 → 提出臨床問題 → 文獻探討 → 分析（問題 → 文獻 → 分析 → 回到本例）
3. **Back to the Patient** — 結論 + 反思 + Take-home message

## 重點要求

- **影像優先於文字報告**：心臟超音波 / 心導管 / CT 不能只貼文字，要附影像並用影像說明 valve disease / coronary lesion / aortic size 等術前判斷
- **手術內容詳細**：照片越多越好（看刀時收集），流程詳細（開胸 → 處理病灶 → 重建）
- **手術 indication 明確**：影像 + 病人表現如何支持「為什麼開這刀」
- **找出病人特殊之處**：不要只是「standard textbook case」，要找 decision making 的爭議點
- **文獻探討**：至少幾篇 evidence，guideline / study 怎麼建議 → 這個病人的選擇合理嗎
- **Back to the Patient**：alternative plans? Or current already optimal? + 反思 + Summary
- **時間掌握**：剩 2 分鐘提醒，10 分鐘到要求跳最後一張 summary
- **取捨大於塞滿**：投影片不限數量但要取捨

## Claude 在 intake 階段要做的

- 確認 `clinicalContext.specialty` 是 CVS / 心臟外科
- 跑 `intake_extras` 收 surgicalIndication / operativeApproach / postopOutcome / alternativePlans / takeHomeBullets
- 把答案 map 進 `CONTENT.operativeProcedure` / `postopCourse` / `backToPatient` / `takeHomeSummary`
- Slide 5 imaging 自動 bold `imaging_emphasis` 列出的 phrase

---
# ============================================================
# Rotation Profile Template
# ============================================================
# Copy this file to profiles/<key>.md, fill in the frontmatter,
# then add an alias entry in profiles/_index.json so Step 2.4
# detection can find it.
#
# Frontmatter = structured generator flags. Body = free-form
# LLM context (paste the teacher's spec here, or set `source:`
# to an external .md path).
# ============================================================

# Required identity ---------------------------------------------
key: <short-key>                       # e.g. "cvs", "neurosurgery", "ob_gyn"
name: <human-readable name>            # e.g. "CVS (Cardiovascular Surgery)"
rotation_display: <subtitle text>      # optional — rendered on Slide 1 under reporter
aliases: []                            # also add to profiles/_index.json

# Source of truth pointer (optional) ----------------------------
# If set, Step 2.4 reads this file's content and uses it as LLM
# context (in place of this profile's body). Lets a teacher's
# original spec stay as the single source of truth.
# source: /absolute/path/to/teacher_spec.md

# Talk structure ------------------------------------------------
structure: default                     # "default" | "three_act"
talk_minutes: 10                       # for slide-count guard

# Slide toggles -------------------------------------------------
slides:
  intro_section_dividers: false        # 3 full-bleed section dividers
                                       # (Patient Data / Discussion / Back to Patient)
  imaging_emphasis: []                 # phrases bolded in Slide 5 imaging cards
  operative_procedure:
    enabled: false                     # insert after Pathology
    title: "Operative Procedure"
    subtitle: "Approach · Key Steps · Reconstruction"
    photo_slots: 0                     # 0-4 dashed photo placeholders
    require: []                        # intake_extras IDs that gate this slide
  postop_course:
    enabled: false                     # insert after Management
    title: "Postoperative Course"
    subtitle: "ICU / Ward · Outcome vs Expected · Complications"
  back_to_patient:
    enabled: false                     # insert after Discussion / extraSlide
    title: "Back to the Patient"
    subtitle: "Alternative plans · Reflection · Lessons"
  take_home_summary:
    enabled: false                     # always the very last slide
    title: "Take-Home Summary"

# Extra intake questions (run after the 6-question canonical intake) ----
# Each entry produces one AskUserQuestion bullet. Answers map into
# CONTENT fields per Step 4 "Profile field mapping" in SKILL.md.
intake_extras: []
# intake_extras:
#   - id: surgicalIndication
#     prompt: "本次手術的 indication（影像/病人表現如何支持「為什麼要開這刀」）"
#     required: true
#   - id: alternativePlans
#     prompt: "依文獻 / guideline 還有哪些可能治療？或目前做法已 optimal？"
#     required: false

# Discussion framing hint (LLM-only, not generator-consumed) ----
# Free-form string explaining how Step 3.5 should phrase Slide 9.
discussion_style: ""
# discussion_style: "問題 → 文獻 → 分析 → 回到本例"
---

# <Rotation Name> — Notes for Claude

Paste the teacher's full spec here, OR set `source:` above to point
to an external `.md`. Claude reads this body during Step 2.4 to
inform intake questions and CONTENT phrasing.

Tips for authoring:

- Keep the body **descriptive, not prescriptive** — Claude reads it
  as context, not as JSON instructions. Use prose, bullet lists, or
  copy-paste the teacher's notes verbatim.
- The frontmatter flags above are what actually toggle slides on /
  off; the body just gives Claude flavor for how to *fill* the
  slides.
- If the teacher updates the original spec, edit the `source:` file
  rather than this body — Step 2.4 always re-reads source on each
  run.

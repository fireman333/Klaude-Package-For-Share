---
pack: software-project
triggers: [app, 寫程式, 做工具, refactor, framework, API, 部署, vibe-coding, frontend, backend, CLI, library, npm, pip, 安裝, deploy, hosting]
applicable_modes: [quick, deep]
default_callers: [vibe-coding 自由發起]
---

# Software Project Facet Pack

對 vibe-coding / 自由開發場景。重點：補上非 CS 背景使用者最容易漏的「audience / NFR / failure mode / scope」面向。

---

## Facets（按重要性排序）

### F1: Audience（誰會用這個 app）

**Why it matters**: 決定 auth、access control、UX polish、文件量

**Baseline questions**:
- 這 app / tool 主要給誰用？（自己 / 實驗室幾個人 / 同學 / 醫師同事 / 公開 / 不確定）
- 預期使用者數：1 / 2–10 / 11–100 / > 100 / 不確定
- 使用者技術程度：跟你一樣 / 比你不熟 / 比你熟 / 混合

**Follow-up triggers**:
- 答「公開」或 > 100 → 「需要 auth / 註冊嗎？多少 user 算 success？」
- 答「不確定」→ 「最樂觀情境 vs 最保守情境分別多少 user？」
- 答「比你不熟」→ 「他們需要什麼程度的 onboarding？單頁 README / 影片 / 互動 tutorial？」

---

### F2: Scope（MVP 範圍 vs 完整版）

**Why it matters**: 防止 scope creep；決定第一版能不能在合理時間內完成

**Baseline questions**:
- 第一版 MVP 必須有的功能（≤ 3 條）？
- 「nice to have 但不阻塞 MVP」的功能？
- 你預期完成 MVP 要多久？（一週 / 兩週 / 一個月 / 三個月+）

**Follow-up triggers**:
- 答 ≥ 4 條 MVP 必須功能 → 「真的都不能砍嗎？砍掉哪一條最不痛？」
- 答 > 1 個月 → 「中間有沒有 milestone 可以拆？拆掉後第一個 deliverable 是什麼？」
- 沒明確 timeline → 「現在每週可以投入幾小時？」

---

### F3: Non-Functional Requirements（NFR）

**Why it matters**: 影響架構選型；非 CS 背景使用者最常完全沒想過

**Baseline questions**:
- 效能要求：互動 < 1 秒 / 容忍 < 5 秒 / batch 跑一晚都可以 / 完全不在乎
- 跨平台：只 Mac / 只 Win / 兩者 / 跨手機 / Web only
- 資料量級：< 1k 筆 / 1k–100k / > 100k / 真的不知道
- 維護期限：用一次就丟 / 用半年 / 維持 1+ 年 / 永久

**Follow-up triggers**:
- 答「跨手機」→ 「響應式網頁可以，還是需要 native iOS / Android？」
- 答「永久」→ 「之後誰維護？只你 / 還會有別人接手？」
- 答「< 1 秒」+ 大資料量 → 「考慮過快取 / index / pagination 嗎？」

---

### F4: Failure Tolerance（失敗模式）

**Why it matters**: 決定 error handling、backup、testing 嚴謹度

**Baseline questions**:
- 如果 app 突然壞掉，最壞情況是什麼？（資料遺失 / 浪費時間 / 病人安全 / 學業成績 / 沒差）
- 資料來源是？（自己手動輸 / 連線資料庫 / 解析檔案 / 第三方 API）
- 如果輸入有 BOM / 編碼錯 / 缺欄位，期望行為？（直接報錯停下 / skip 該筆 / 用 default 值）

**Follow-up triggers**:
- 答「病人安全」/「資料遺失」→ 「需要 audit log 嗎？要不要先做最小可用 prototype 驗證再加複雜度？」
- 答「skip 該筆」→ 「需要在最後印出 skip 總數嗎？」（debugging_principles.md No Silent Errors 規則）
- 答「第三方 API」→ 「API 掛掉時 app 該怎樣？fallback / cache / 直接報錯？」

---

### F5: Tech Constraints（技術約束）

**Why it matters**: 縮小選型範圍、避免後期改架構

**Baseline questions**:
- 必須用什麼語言 / framework？（如果有偏好或熟悉度）
- 必須避免什麼？（成本上限、依賴上限、團隊不熟的 stack）
- 部署環境：本機 / VPS / Vercel / Cloudflare / 公司內網 / 還沒想

**Follow-up triggers**:
- 答「還沒想」+ 預期 > 10 user → 「是時候想了，這影響 auth / data persistence 設計」
- 答「成本上限」→ 「具體月預算？」
- 答「Cloudflare / Vercel」→ 「serverless 限制（10s timeout / cold start）你能接受嗎？」

---

### F6: Deploy Model（怎麼讓使用者用到）

**Why it matters**: 影響 install UX / update 機制

**Baseline questions**:
- 使用者如何取得這 app？（git clone / homebrew / dmg / web URL / Chrome ext / 我自己幫他裝）
- 更新機制：手動 git pull / 自動 / dmg 重新下載 / 不需要更新（一次性）
- 安裝門檻容忍度：要使用者跑 terminal OK / 必須點兩下安裝 / 必須完全 zero-config

**Follow-up triggers**:
- 答「必須點兩下」+ 跨平台 → 「考慮過 Tauri / Electron 的 dmg + msi 嗎？」
- 答「web URL」→ 「需要使用者註冊嗎？資料存哪？」

---

## 輸出 section 建議

輸出的 markdown 依 facet 分段（Audience / Scope（MVP 與 Out of Scope 分開寫）/ NFR / Failure Tolerance / Tech Constraints / Deploy Model）。Failure mode 屬於 runtime behavior，獨立一段，不要混進 Tech Constraints。

---

## 退讓 sentinel

若 topic 含這些訊號 → 退讓不啟動：
- 「PICO / cohort / cox / KM」 → `/research-plan`

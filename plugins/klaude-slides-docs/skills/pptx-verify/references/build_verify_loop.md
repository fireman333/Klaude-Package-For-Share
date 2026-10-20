## PPTX Build → Verify Loop（投影片製作三段式工作流）

任何用 pptxgenjs / python-pptx / 其他 generative 工具產出的投影片，都必須走這套流程，不可跳。教訓來自一份 16-slide 懶人包的製作 — 第一輪 build 後一次性 visual QA 抓到 5 個 P1 critical（包含 dark-on-dark icon 全 8 張概念頁不可見、footer 全 deck 切到底邊、text overflow 出 box）。

### 三段式流程

1. **Build** — 寫 script、生成 .pptx
2. **Render** — pptx → PDF（soffice headless）→ JPG（pdftoppm）
3. **Verify** — **派 sub-agent**（不是自己看）做 visual QA

### Verify 必須派 sub-agent，不可自己看

- 你寫 build script 時心中的「應該是這樣」會 override 你看圖時的「實際是這樣」— 認知盲點
- Sub-agent 沒看過 code，只看 image，會抓到你看不見的 layout 問題
- Brief sub-agent 時把預期的 layout 列出來、要求它「假設有問題、找出來」
- 一次給它全部 N 張的絕對路徑，叫它逐張掃，回 prioritized issue list

### 修完一定要再 verify 一輪

- 一輪 fix 沒做 verify 等於沒做。修 layout 常會引發新問題（例如縮小 card → bullet 被切）
- 第二輪 verify 比第一輪 fix 更重要

### Build 階段的常見 layout 陷阱（都被 visual QA 抓出來才會發現）

| 陷阱 | 教訓 |
|------|------|
| Footer 元素貼到 slide 邊界 | 16:9 = 5.625" 高，footer 要留 ≥ 0.15" buffer 不要貼 5.55 |
| 同色系疊在一起（navy icon on navy circle） | Render icon 前先想「最後會被放在什麼底色上」再決定 fill color；deck 內維護兩套（dark/light）icon set |
| 中英混排 text box 寬度 | 中文字寬 ≠ 英文字寬，wrap 邏輯不同；text box 預留 30–50% 寬度緩衝，不要「剛好放得下」就停 |
| Card 內 bullet 太長 | 4 個 bullet 都長就會疊到 card 底邊；先拆成短句或拉高 card |
| 中央元素 + halo 蓋到旁邊卡片 | Halo 比預想大、會跑出 disc 邊界；除非真的需要不要加 halo |

### Bug 修復策略

- **先抓所有問題再一次性批次修**，不要「修一個 build 一次」
- 第一輪 visual QA 一次抓 15+ 個問題、批次 Edit、再 verify — 比逐個 fix 省至少 5 倍時間

### 適用範圍

- pptx 製作（pptxgenjs / python-pptx / 內建 pptx skill）
- 推廣到所有 generated visual artifact：Excel（formatting / chart layout）、PDF（marker-pdf / Quarto）、SVG、HTML（frontend rendering）— 共通模式都是「build → render → spawn QA subagent → fix → re-verify」

### Why（背景）

曾製作 16-slide 懶人包，第一輪 build 後做這個流程，sub-agent 抓到：
- Slide 2 text overflow 出 equation card
- Slides 5–12 hero icon dark-on-dark 全部不可見（系統性問題）
- Slides 4–14 footer 撞到底邊（template 性問題）
- Slide 15 中心 halo 蓋到旁邊 card
- Slide 1 cover 圖示與 title 重疊

這些都是寫 code 時用算術看不出來、必須 render 才看得到的問題。第二輪 verify 又抓到一個 fix 引發的新 bug（Slide 9 縮小 card 後第四個 bullet 被切）— 證明「修完一定要再 verify」這條規則的價值。

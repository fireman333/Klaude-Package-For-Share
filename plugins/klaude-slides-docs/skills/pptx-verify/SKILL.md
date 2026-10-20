---
name: pptx-verify
description: "PPTX visual QA loop：對剛生成的 .pptx 做 preflight → soffice 轉圖 → 派 sub-agent 目視檢查，回 P1–P4 issue list；只診斷不修圖。Trigger: `/pptx-verify <path>`、`/pv <path>`、「檢查投影片」「驗證 pptx」「QA 一下這 deck」。其他 pptx 生成 skill（case-discussion-pptx / journal-club-discussion-pptx / notebooklm-pptx / 其他 pptx skill）build 完應自動觸發。"
---

# pptx-verify — 投影片視覺品保 loop

## 設計哲學

寫 pptx build script 時，code 裡用算術算 layout 都對，但 render 出來常因 text auto-wrap、字型寬度、box padding、color contrast 等 build-time 看不到的問題出包。**主 agent 自己看 render 圖會被「我寫的 code 應該是這樣」的認知盲點 override**，看不到實際 layout 問題。所以：

1. **必須 render 才能驗收**（不能用 text extract 代替）
2. **必須派 sub-agent 看**（主 agent 自己看會 miss）
3. **修完必須 re-verify**（fix 常引發新 bug，例如縮 card → bullet 被切）

教訓來自一份 16-slide 投影片製作 — 第一輪 sub-agent QA 抓到 5 個 P1（dark-on-dark icon 全 8 張不可見、footer 全 deck 切到底邊、text overflow），第二輪 re-verify 又抓到一個 fix 引發的新 bug。

詳細背景見 `${CLAUDE_SKILL_DIR}/references/build_verify_loop.md`（含 build 階段常見 layout 陷阱表、bug 修復策略、案例完整紀錄）。

---

## 觸發條件

| 場景 | 行為 |
|---|---|
| `/pptx-verify <path>` 或 `/pv <path>` | 使用者手動觸發 |
| 使用者說「檢查投影片」「驗證 pptx」「QA 一下這 deck」「投影片看一下有沒有問題」 | 視為觸發 |
| 其他 pptx-生成 skill 完成後（`case-discussion-pptx` / `journal-club-discussion-pptx` / `notebooklm-pptx` / 其他 pptx skill / 即興 build） | 自動觸發 — 不問使用者 |
| 使用者明說「不用 verify」「skip QA」「先這樣就好」 | 跳過 |

---

## 參數

```
/pptx-verify <path-to-pptx> [--re-verify] [--focus <slide-numbers>]
```

- `<path>` — 必填，絕對路徑或相對於 CWD。**支援 glob**：若給目錄，找 CWD 下最新的 `.pptx`
- `--re-verify` — 修完後重跑第二輪。會比對 issue list，只報新增 / 殘留問題
- `--focus 3,7,15` — 只 verify 指定頁（用於修完局部後快速確認）

---

## 主流程（4 步）

### Step 1: Preflight

```bash
# 確認檔案存在、是合法 zip-based pptx、頁數合理
test -f "$PPTX" || die "PPTX not found: $PPTX"
unzip -t "$PPTX" >/dev/null 2>&1 || die "PPTX corrupted (zip integrity failed)"
SLIDE_COUNT=$(unzip -l "$PPTX" | grep -c "ppt/slides/slide[0-9]*.xml$")
[ "$SLIDE_COUNT" -gt 0 ] || die "No slides found in pptx"
echo "Preflight OK: $SLIDE_COUNT slides"
```

若 preflight 失敗 → 立即停、告訴使用者，不進入 render。

### Step 2: Render（pptx → PDF → JPG）

呼叫 `scripts/render.sh`：

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/render.sh "$PPTX"
```

它會：
1. 用 `soffice --headless --convert-to pdf` 轉 PDF（若偵測到 Claude 內建 pptx skill 的 `soffice.py` wrapper 會優先用，否則直接呼叫系統 `soffice`；沒裝請 `brew install --cask libreoffice`，且需 `brew install poppler` 提供 `pdftoppm`）
2. 用 `pdftoppm -jpeg -r 130` 轉 JPG（一頁一張，命名 `slide-NN.jpg`）
3. 輸出絕對路徑清單到 stdout

輸出位置：`<pptx-dir>/.pptx-verify/slide-*.jpg`（不污染原資料夾）

### Step 3: Visual QA via Sub-agent

**必須派 sub-agent，主 agent 不可自己看。**

呼叫 `Agent` tool，派一個具視覺能力的 sub-agent（`general-purpose`，可指定較便宜的模型如 sonnet），prompt 模板見 `${CLAUDE_SKILL_DIR}/qa_prompt_template.md`。要把以下傳給 sub-agent：

- 全部 `slide-NN.jpg` 的**絕對路徑**清單
- 每張 slide 的 expected layout（一句話描述，從 build script 或使用者口述抽取；若無就略）
- Priority rubric：P1 = critical（文字被切 / 溢出 / 看不清 / 內容錯）、P2 = 明顯缺陷影響理解、P3 = 可容忍的小瑕疵、P4 = 純美觀
- Common pitfall checklist（見 prompt template）

**Model choice**：版面 QA 屬機械式視覺檢查，中階模型即可勝任，不必用最貴的模型。

Sub-agent 必須：
1. 假設「有問題、找出來」（adversarial mindset）
2. 逐張掃，回 issue list group by slide
3. 每個 issue 標 priority + 類別（overflow / overlap / contrast / alignment / margin / chinese-rendering）
4. 給可執行修復建議（哪個元素、改什麼參數）

### Step 4: Report

主 agent 收到 sub-agent 回報後：
1. 整理成 markdown table（slide # | priority | category | issue | suggested fix）
2. 寫到 `<pptx-dir>/.pptx-verify/verify_report.md`
3. 在 chat 顯示 P1 / P2 issue（P3 / P4 折疊起來，可選展開）
4. 詢問使用者：要 (a) 我直接修 build script (b) 你自己改 (c) 跳過

若使用者選 (a)：修完後**自動再呼叫 `/pptx-verify --re-verify`**，不問。第二輪通過才算結案。

---

## Re-verify Mode（`--re-verify`）

第二輪 verify 比第一輪 fix 更重要。流程：

1. 比對 `verify_report.md` 中前一輪 issue list
2. 派 sub-agent，prompt 加上「先驗證以下 N 個 issue 是否修復、再做完整 fresh scan」
3. 輸出三段：
   - **Fixed** — 哪些前輪 issue 已修
   - **Remaining** — 哪些前輪 issue 仍在
   - **New** — 修復過程引入的新 bug
4. New issue 出現 → 必須再修一輪（不可放行）；只剩 P3 / P4 → 詢問使用者要不要繼續

---

## 與其他 skill 的關係

| Skill | 關係 |
|---|---|
| 內建 pptx skill | 上游 — 它做 build；本 skill 做 verify |
| `case-discussion-pptx` / `journal-club-discussion-pptx` / `notebooklm-pptx` | build 完應在自己 skill 末尾自動 invoke `/pptx-verify` |

---

## 不該做的事（Anti-scope）

- ❌ 自己改 pptx 內容（純診斷器，不修圖）
- ❌ 用 `python-pptx` 解析後給 text-only QA（必須 render 看圖）
- ❌ 主 agent 自己看 render 圖（必須派 sub-agent）
- ❌ 一輪 fix 後就放行（必須 re-verify）
- ❌ 跳過 preflight 直接 render（壞檔會浪費 soffice 時間）

---

## Output 結構

```
<pptx-dir>/.pptx-verify/
├── slide-01.jpg ... slide-NN.jpg     # render 結果
├── <basename>.pdf                     # 中介 PDF（debug 用）
├── verify_report.md                   # 整理後的 issue list
└── verify_log.json                    # 機器可讀（含 timestamp / agent id / issue count）
```

每次 verify 會 overwrite。歷史想留就 rename 資料夾。

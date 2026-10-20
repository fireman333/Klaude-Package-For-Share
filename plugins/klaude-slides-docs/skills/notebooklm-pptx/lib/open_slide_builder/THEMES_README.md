# Open-slide academic themes

3 個學術風格 theme bundle，從 `templates/themes.py`（pptx 用）轉存而來；用於 journal-club-discussion-pptx / notebooklm-pptx 的 open-slide mode。

| Theme id              | pptx 對應          | 視覺定位                                              |
| --------------------- | ------------------ | ---------------------------------------------------- |
| `journal-classic`     | `journal_classic`  | NEJM / Lancet 雙刊白底 navy + crimson + Georgia serif |
| `grand-rounds-warm`   | `grand_rounds_warm`| Harvard / Notion editorial 米紙 + rust/copper        |
| `clinical-modern`     | `clinical_modern`  | JAMA / Stripe light gray + teal-dark + coral sans    |

每個 theme 含 2 個檔案：

- `<id>.md` — agent-facing 文件（palette、typography、layout、paste-ready Title/Footer/Eyebrow components、motion、aesthetic）
- `<id>.demo.tsx` — 3-page 可 render 的 demo slide module（Cover + Content + Closer），讓 open-slide 的 Themes panel 自動載入預覽

## open-slide mode 使用流程（builder 會自動複製 themes，以下為手動測試用）

```
1. scaffold open-slide deck: `npx @open-slide/cli init <slug>`
2. cp -r <this-folder>/*.md <slug>/themes/
3. cp -r <this-folder>/*.demo.tsx <slug>/themes/
4. 主 slide 在 slides/journal-club/index.tsx，import 對應 theme palette + components
5. 主 slide 的 `meta.theme` 寫對應 theme id（journal-classic / grand-rounds-warm / clinical-modern）
```

`DATA.meta.theme` 從 `journal_classic` 等 pptx id 對應到本資料夾 kebab-case id：

```python
PPTX_TO_OPEN_SLIDE_THEME = {
    "journal_classic": "journal-classic",
    "grand_rounds_warm": "grand-rounds-warm",
    "clinical_modern": "clinical-modern",
}
```

## Diff vs pptx themes.py

1. **clinical-modern 拆 primary / accent** — pptx 版本 `primary` == `accent` == `#0E5E6F`（會讓 accent 文字在 primary 底上隱形）。Open-slide 版改 `primary=#0E5E6F` + `accent=#C0392B`（原 accent2 升級）。
2. **加 useSlidePageNumber hook** — open-slide 用 `useSlidePageNumber()` 取 current/total；pptx 直接寫死。
3. **加 `design` const** — open-slide 的 Design panel runtime-tweakable token；pptx 沒有對應概念。
4. **Motion philosophy 標示** — open-slide theme 必填 static / subtle / rich；pptx 無此欄位。

## How to test a theme bundle

```bash
cd /tmp && rm -rf test-jc-deck && npx @open-slide/cli init test-jc-deck
cp -r <this-folder>/*.md test-jc-deck/themes/
cp -r <this-folder>/*.demo.tsx test-jc-deck/themes/
cd test-jc-deck && pnpm dev
# 開瀏覽器到 http://localhost:5173/themes/journal-classic 看 demo slide
```

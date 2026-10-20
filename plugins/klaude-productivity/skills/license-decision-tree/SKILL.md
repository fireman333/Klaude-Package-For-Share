---
name: license-decision-tree
description: 開源授權決策樹（Open Source License Decision Tree）。透過 4 個 Yes/No 問題（商用 / copyleft / SaaS / 專利）導出最適授權：MIT / Apache 2.0 / GPL v3 / AGPL v3 / CC BY-NC。支援 Interactive（單 repo 逐一問）與 Batch（一次問完套多 repo）兩種模式，會實際寫入 LICENSE 檔並 local commit（預設不 push）。觸發關鍵詞：/license-decision-tree、/license、選擇 license、該用什麼授權、授權評估、choose a license、pick a license、license compatibility、MIT vs Apache、GPL vs AGPL、補 license、加上 license。使用者若問「我這個專案要用什麼授權」「幫我選 license」「我的 repo 該加什麼 license」一律用此 skill。
---

# License Decision Tree

開源授權選擇決策樹。4 個 Yes/No 問題 → 推薦 1 種 license → 寫入 LICENSE 檔 + local commit。

## 何時使用

- 建 repo 初期選 license
- 既有 repo 補 license（預設 `All Rights Reserved` 擋所有外部使用者）
- 對多個 repo 一次套同一 license（Batch 模式）
- 使用者說「幫我選 license」「該用什麼授權」「加上 license」

## 核心流程（4 個問題）

依序問使用者，用 `AskUserQuestion` 一次丟完 4 題（Batch 模式）或逐題問（Interactive 模式）。

```
Q1. 你希望別人能商用嗎？
 ├─ 否 → CC BY-NC  ⚠️ 警告：不適用於程式碼，僅用於文件/教材/圖片
 └─ 是 → Q2

Q2. 你希望別人修改後的衍生物也必須開源嗎？
 ├─ 是 → Q3
 └─ 否 → Q4

Q3. 這個專案會以 SaaS / 網路服務提供嗎？
 ├─ 是 → AGPL v3
 └─ 否 → GPL v3

Q4. 你需要明確的專利授權與專利終止條款嗎？
 ├─ 是 → Apache 2.0
 └─ 否 → MIT
```

## License 一句話說明

| License | SPDX Key | 適用情境 |
|---------|----------|---------|
| **MIT** | `mit` | 最寬鬆、最常見。只要保留版權聲明即可任意用。你不在乎別人怎麼用時選 |
| **Apache 2.0** | `apache-2.0` | MIT + 顯式專利授權 + 專利終止條款。有專利考量（大公司 / 機敏技術）選 |
| **GPL v3** | `gpl-3.0` | 強 copyleft，衍生物必須同樣開源。CLI / desktop 工具常用 |
| **AGPL v3** | `agpl-3.0` | GPL v3 + 堵 SaaS loophole（透過網路服務也算 distribute，也要開源）。web service / API 常用 |
| **CC BY-NC 4.0** | (非 SPDX code license) | 文件 / 教材 / 圖片 / 素材禁止商用。**程式碼不建議**：CC 系列非為軟體設計、無專利條款、無衍生物定義細節 |

## 執行模式

### Interactive 模式（單 repo）

1. 問使用者 repo 路徑 + 4 題 + 版權人全名（`[fullname]`）
2. 依決策樹推導 license
3. 若 repo 已有 `LICENSE` / `LICENSE.md`：**先問**是否覆蓋；預設不覆蓋
4. 用 `gh api /licenses/<spdx-key> -q .body` 取得模板（見下方「取得模板」）
5. 替換 `[year]` → 當前年份、`[fullname]` → 使用者全名（其他 placeholder 依 API 回傳為準）
6. 寫入 `<repo>/LICENSE`
7. `cd <repo> && git add LICENSE && git commit -m "Add <LICENSE_NAME> LICENSE"`
8. **不 push**（除非使用者明確要求）
9. 回報 commit hash + 手動 push 指令

### Batch 模式（多 repo 套同一 license）

1. 問使用者 repo 路徑列表 + 4 題一次問完 + 版權人全名
2. 依決策樹推導 **1 個** license
3. 取得模板（一次）
4. 對每個 repo 重複 Interactive 步驟 3–7
5. 最後彙整表格：每個 repo 的 commit hash + license + 手動 push 指令

## 取得 License 模板

### 首選：本機 cache（offline、零網路依賴）

Skill 目錄下已預先下載 4 份主流 license 模板到 `templates/`：

```
${CLAUDE_SKILL_DIR}/templates/
├── mit.txt          (22 lines)
├── apache-2.0.txt   (202 lines)
├── gpl-3.0.txt      (675 lines)
└── agpl-3.0.txt     (662 lines)
```

使用方式：
```bash
cp ${CLAUDE_SKILL_DIR}/templates/<key>.txt <repo>/LICENSE
# 然後用 sed 替換 placeholder
sed -i '' "s/\[year\]/$(date +%Y)/g; s/\[fullname\]/<使用者全名>/g" <repo>/LICENSE
```

模板內建 placeholder：
- `[year]` → 當前年份
- `[fullname]` → 使用者全名（GitHub 名稱 or 真名）
- 其他罕見 placeholder 保留原樣

### 備援：重新下載模板（若 templates/ 不存在或損壞）

```bash
cd ${CLAUDE_SKILL_DIR}/templates/
for key in mit apache-2.0 gpl-3.0 agpl-3.0; do
  gh api /licenses/$key -q .body > "$key.txt"
done
```

### CC BY-NC 4.0（不在 `gh api` 列表）

若使用者堅持用在非程式碼：
- 官方 legal code: https://creativecommons.org/licenses/by-nc/4.0/legalcode.txt
- 實務最簡：`LICENSE` 檔寫 `This work is licensed under CC BY-NC 4.0.\nhttps://creativecommons.org/licenses/by-nc/4.0/legalcode` 兩行即可

### 資安備註

所有 4 份本機 template 是首次建 skill 時從 GitHub 官方 `/licenses/<key>` endpoint（HTTPS）一次性下載。之後使用完全 offline，不依賴網路，避免：
- API 掛掉影響執行
- 供應鏈漂移（GitHub 若改文字不會悄悄影響已 commit 的 LICENSE）
- 不必要的網路 traffic

若擔心初始下載被污染，可手動比對 SPDX 官方版本：https://spdx.org/licenses/

## Pitfalls / 注意事項

1. **程式碼 repo 不要用 CC BY-NC**：CC 系列非為軟體設計，無專利條款、無衍生物定義細節、與 OSI approved license 不相容
2. **已有 LICENSE 不要覆蓋**：先 `ls <repo>/LICENSE* <repo>/COPYING*`，有就問
3. **依賴的 license 會限縮你的選擇**：若 repo 直接 link GPL 函式庫（不是 LGPL），你的 license 不能比 GPL 寬鬆
4. **`[fullname]` 預設值**：首次執行時問使用者，用 GitHub 名稱 or 真名皆可；可以存 memory 下次沿用
5. **GitHub 顯示時機**：commit 後要 push，GitHub 才會在 repo 頁面顯示 license badge
6. **AGPL 不是 default**：只有「別人自建 SaaS 提供服務」你也想要求開源時才選；一般 web app 如果你不在意別人魔改自架站 → 用 MIT / Apache
7. **Dual license / multi-license**：超出本 skill 範圍，若使用者提到直接告知「需要人工設計，建議諮詢」

## 輸出格式（Batch 模式範例）

```
決策路徑：Q1=是 → Q2=否 → Q4=否 → **MIT**

已套用到以下 repo：
| Repo | LICENSE | Commit | 手動 push |
|------|---------|--------|----------|
| foo  | MIT     | abc123 | `cd /tmp/license-apply/foo && git push` |
| bar  | MIT     | def456 | `cd /tmp/license-apply/bar && git push` |
```

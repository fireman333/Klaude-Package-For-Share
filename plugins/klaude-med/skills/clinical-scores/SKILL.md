---
name: clinical-scores
description: "臨床評分系統記憶庫，儲存研究中實際使用過的 clinical score 的計算方式、組成變數、切點、預後意義、欄位對應。**目前只收錄 rCAST**；其他分數（GCS / SOFA / APACHE / CLAPPP 等）未收錄請走文獻查證（PubMed 等），**不要憑模型知識回答 cutoff / 權重**。Trigger: `/clinical-scores`、`/score-lookup`、「rCAST 怎麼算」「分數切點」「score 計算」「score cutoff」「分數組成」。對 rCAST 以外的分數先檢查 references/ 是否已收錄。"
---

# Clinical Scoring System Reference

臨床評分系統記憶庫 — 儲存研究中使用到的各種 clinical score 的完整計算方式與研究背景。

## 使用方式

當使用者詢問某個 clinical score 的計算方式、組成變數、切點或欄位對應時：

1. **查詢 references/** 資料夾中對應的分數檔案
2. **直接回答**：公式、各組成的計分邏輯、分層標準、AUC 等已驗證數據
3. 如需計算某位病人的分數，依照公式逐步算出並說明每個組成

## 目前收錄的分數

| Score | 檔案 | 適用情境 |
|-------|------|---------|
| **rCAST** | `references/rCAST.md` | OHCA/IHCA 心跳停止後預後評估 |

> 新增分數時，在 `references/` 新增 `{score-name}.md`，並更新此表格。

## 新增分數的格式規範

每個分數檔案應包含：
- 來源文獻 / 適用對象
- 計算公式（含各組成的權重）
- 各組成的計分對應表（0/1/2/3 等）
- 嚴重度分層與對應預後數據
- AUC / OR 等已驗證的判別力數據
- 資料庫欄位對應（如使用 TIMECARD 或其他資料庫）

# Literature Guard: Biomedical Citation Standards

## 何時載入
當文獻回顧涉及醫學、藥學、臨床研究文獻時。

---

## 證據等級標記（必做）
每個引用必須標記其證據等級：
```
Level 1a: Systematic review of RCTs
Level 1b: Individual RCT
Level 2a: Systematic review of cohort studies
Level 2b: Individual cohort study / Ecological study
Level 3:  Case-control study
Level 4:  Case series / Cross-sectional
Level 5:  Expert opinion / Mechanism-based reasoning

規則：結論強度不得超過其最弱的支持證據等級。
```

## 指引與共識文件
```
□ 臨床指引是否引用最新版本？（WHO, NICE, AHA/ACC, ESMO）
□ 是否區分了「強烈建議」和「條件性建議」？
□ GRADE 系統等級是否標記？（High/Moderate/Low/Very Low）
```

## 藥物/介入引用
```
□ 藥物使用通用名（generic name）？
□ Phase III 試驗完整結果（不只摘要）？
□ 安全性資料和不良反應有引用？
□ 已撤回的論文已檢查？（Retraction Watch）
□ 臨床試驗登記號已引用？（NCT number）
```

## 驗證工具
```
必查：PubMed, DOI resolver, Retraction Watch, ClinicalTrials.gov
紅旗：predatory journals ⚠ / erratum 未引用 ⚠ / expression of concern 🔴
```

## 新近性標準
```
Clinical evidence:        最近 5 年
Foundational pathophys:   可較舊（需確認未被推翻）
Drug safety:              最新版本
Clinical guidelines:      最新版本
Epidemiological data:     最近 3 年
```

## 系統性回顧引用規範
```
□ 優先引用 Cochrane Reviews
□ SR 搜索策略是否完整報告？
□ PRISMA 流程圖是否被引用？
□ 異質性 I² 是否被討論？（I² > 75% = 高異質性 → 結論需謹慎）
□ SR 是否有更新版本？
```

## Retraction Check（強制步驟）
```
對於 biomedical 領域的所有引用，retraction 檢查是強制步驟，不是可選：

每篇引用必須：
  1. 搜索 Retraction Watch database
  2. 檢查期刊網站是否有 retraction notice
  3. 如果第一作者有撤回歷史 → 對該作者所有引用提高警戒

如果 evaluator 未做 retraction check → 整個 Literature Guard 標記為 INCOMPLETE。
```

## 輸出格式
```
## Biomedical 文獻驗證補充
- 證據等級分佈：L1=[N] L2=[N] L3=[N] L4=[N] L5=[N]
- 指引版本：[最新 ✅ / 過時 ⚠]
- Retraction 檢查：[N] 篇已查，[N] 篇問題
```

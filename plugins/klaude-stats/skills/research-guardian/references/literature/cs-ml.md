# Literature Guard: CS/ML Citation Standards

## 何時載入
當文獻回顧涉及機器學習、AI、軟體工程文獻時。

---

## 預印本 vs. 同行審查
```
□ 每篇引用標記狀態？
  - peer-reviewed / preprint / workshop / tech report
□ 核心論點是否依賴未審查預印本？→ 標記 lower confidence
  例外：被廣泛引用(>100 citations)的預印本可接受
□ 預印本是否有後續正式版本？→ 引用正式版本
```

## 版本問題
```
□ arXiv 論文是否引用最新版本？（v1 和 v5 可能差異很大）
□ 模型引用是否具體？
  ❌ "GPT" → ✅ "GPT-4o-2024-11-20"
  ❌ "BERT" → ✅ "BERT-large-uncased"
□ 開源軟體是否引用版本號？
```

## SOTA 引用時效性
```
□ SOTA 結果是否在 6 個月內確認？
□ 是否引用了「曾經的 SOTA」而非「現在的 SOTA」？
□ 比較條件是否一致？（同 benchmark 版本、同 eval protocol、同資料分割）
必查：Papers With Code SOTA 排行
```

## 公司研究 vs. 學術研究
```
□ 科技公司論文是否標記？
  - 可能使用不公開的計算/資料 → 難以重現
  - 可能有商業偏誤
  → 標記 "industry research" + 討論重現性限制
```

## 驗證工具
```
Semantic Scholar, Papers With Code, DBLP, Connected Papers
特別檢查：GitHub repo 是否還在維護？引用的 API/service 是否還存在？
```

## 新近性標準
```
SOTA comparisons:  最近 6 個月
Method descriptions: 最近 2 年
Foundational papers: 無限制
Survey papers:      最近 2 年
```

## 輸出格式
```
## CS/ML 文獻驗證補充
- 同行審查比例：[N]% reviewed / [N]% preprint
- SOTA 時效：[確認日期]
- Code 可用性：[N]% 有公開代碼
```

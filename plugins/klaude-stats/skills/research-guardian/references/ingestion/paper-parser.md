# Paper Parser — 論文解析與錨點建立

## 何時載入
在任何 gate 執行之前。這是整個 pipeline 的第一步——將原始文字轉為結構化資料。

---

## 目的
將研究輸出切割為帶有穩定 ID 的結構化段落，讓所有 gate 的 issue 都能精確指向原文位置。

## 解析輸出格式
```
{
  "paper_id": "sha256-based-hash",
  "sections": [
    {
      "id": "SEC-INTRO",
      "title": "Introduction",
      "paragraphs": [
        {"id": "SEC-INTRO-P1", "text": "..."},
        {"id": "SEC-INTRO-P2", "text": "..."}
      ]
    }
  ],
  "figures": [{"id": "FIG-01", "caption": "...", "referenced_in": ["SEC-RESULTS-P3"]}],
  "tables": [{"id": "TBL-01", "caption": "...", "referenced_in": ["SEC-RESULTS-P5"]}],
  "equations": [{"id": "EQ-01", "content": "...", "context": "SEC-METHODS-P4"}],
  "references": [{"id": "REF-01", "raw_text": "...", "cited_in": ["SEC-INTRO-P2"]}],
  "metadata": {},
  "parse_quality": "good|partial|poor"
}
```

## 錨點命名規則
```
SEC-{SECTION_NAME}-P{N}  → 段落級
FIG-{NN}                 → 圖表
TBL-{NN}                 → 表格
EQ-{NN}                  → 方程式
REF-{NN}                 → 參考文獻

所有 issue 的 location.anchor_id 必須使用這些 ID。
如果原文不是結構化的（如純文字），按每 3-5 句切割為段落單元。
```

## 解析品質判定
```
good:    所有章節可辨識、圖表有 caption、引用可提取
partial: 部分章節缺失或模糊、某些圖表無法解析
poor:    無法辨識章節結構 → 所有 gate 的 confidence 自動降 0.2
```

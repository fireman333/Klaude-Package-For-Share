# SOP + decision-log document (繁體中文, for the supervisor)

Build with `python-docx`. Set the Normal style's east-Asian font to `Microsoft JhengHei`
(`style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft JhengHei")`) — it renders on both
Windows and macOS Word. Pull every number from `<prefix>build_stats.json` rather than
retyping it, so the document cannot drift from the workbook.

## Sections

1. **交付物** — table: file → what it contains (workbook, results docx, this SOP, raw JSON, scripts, verification JSON).
2. **資料來源與門檻** — table: database, population, traits per variant, genome build, per-row fields, table a row count, the cut-off and who set it, how many rows reach it. If the cut-off was the user's or the advisor's instruction, say so explicitly.
3. **操作流程** — one sub-heading per step (rsID→coordinate incl. the prefix-matching trap; download; browser-vs-API verification and its result; table a; table b merge rules with concrete examples; table c and the direct/borderline distinction; the targeted-lookup sheet and why it exists).
4. **決策清單** — 4-column table: 決策點 / 採用做法 / 理由 / 影響範圍與如何更改. One row per choice the original instruction did not specify. The last column must name the file and variable to change, so the advisor can ask for a different answer cheaply.
5. **已知限制與待裁決事項** — variants absent from the database; traits the database does not carry; domains with no signal (worded as 未達統計顯著, never 沒有關聯); what the threshold excluded, with the two or three most clinically notable examples; the borderline rows awaiting a decision; ancestry / linkage-disequilibrium caveats.
6. **重跑方式** — numbered table of the commands, and where the threshold and the mapping live.

When more than one database was queried, add a comparison table (row counts, hit counts,
which variants each carries) and state plainly that the p-values are not directly comparable
and that the outputs are deliberately kept in separate files.

## Wording rules

- 繁體中文; medical and statistical terms in English, Chinese gloss on first use.
- No 高/中/低 grading; no English filler jargon (caveat, per se, ad hoc).
- Statistics: 「未達統計顯著」/「在此資料集中未偵測到差異」, never 「沒有差異」or 「證明無關」.
- Conservative, non-imperative phrasing for anything clinical: 建議 / 可考慮 / 宜, not 必須 / 一定.

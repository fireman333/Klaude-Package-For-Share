# PubMed subagent prompt template

Used at Step 3 when the main thread dispatches n general-purpose subagents in a
SINGLE message (parallel). Each subagent owns exactly ONE discussion question.

Substitute `{}` placeholders before sending.

---

You are a PubMed literature search subagent for a journal club pptx. Your job is
to find the best 3–5 PubMed citations that address ONE specific discussion
question. Output structured JSON for the main thread to aggregate.

## Your assignment

- **Question ID**: {QID}   (e.g. Q2)
- **Question text**: "{QUESTION_TEXT}"
- **Primary PubMed query (start here)**: {QUERY_STRING}
- **Candidate MeSH terms**: {MESH_LIST}
- **Paper under discussion (DO NOT re-cite as evidence)**:
  PMID {PAPER_PMID} — {PAPER_TITLE}

### Other subagents are handling these questions — DO NOT overlap

{SIBLING_QUESTIONS_LIST}

If your search returns a PMID that clearly answers someone else's question
more than yours, skip it.

## Steps

1. Call `mcp__pubmed__pubmed_search_articles` with:
   - `query` = {QUERY_STRING}
   - `retmax` = 15
   - date filter: last 10 years (or last 5 if guideline/controversy question)
2. Skim returned titles + abstracts. Pick **3–5** that directly address
   `{QID}: {QUESTION_TEXT}`.
3. Call `mcp__pubmed__pubmed_fetch_articles` with your picked PMIDs (batch).
4. For each pick, extract:
   - `pmid`, `doi`, `title` (verbatim article title), `authors_short` (first author + "et al"), `year`,
     `journal`, full author list
   - `study_type`: one of `RCT`, `RCT (multicenter)`, `Prospective cohort`,
     `Retrospective cohort`, `Case-control`, `Cross-sectional`,
     `Systematic review`, `Meta-analysis`, `SR+MA`, `Guideline`,
     `Mechanism review`, `In-vitro`, `Animal study`, `Other`
   - `country`: primary enrollment country, or "Multinational" if multi-site
   - `n`: sample size (number; use `"N/A"` only for reviews/guidelines)
   - `take_home`: one line ≤ 25 words, English, what this study concludes re `{QID}`
   - `relevance_score`: 0.0–1.0 (subjective — how directly this answers `{QID}`)

## Output (write to `{OUTPUT_PATH}` as JSON)

```json
{
  "question_id": "{QID}",
  "question_text": "{QUESTION_TEXT}",
  "search_query": "{QUERY_STRING}",
  "mesh_used": [...],
  "picks": [
    {
      "pmid": "...",
      "doi": "...",
      "title": "Verbatim article title",
      "authors_short": "Smith et al",
      "full_author_list": "Smith J, Lee K, Chen W, et al.",
      "year": 2024,
      "journal": "N Engl J Med",
      "study_type": "RCT (multicenter)",
      "country": "US",
      "n": 1234,
      "take_home": "Drug X reduced 30-day mortality by 18% vs placebo.",
      "relevance_score": 0.9
    },
    ...
  ],
  "notes_for_main": "<1 sentence summarising the landscape for this Q>",
  "failures": []
}
```

## Retry policy

- `pubmed_search` returns 0 hits → broaden query by dropping one term, retry.
- Max 3 attempts. If still 0 after 3, write `"picks": []` and
  `"failures": ["no_hits_after_broaden"]` — DO NOT fabricate.
- Fetch fails on a PMID → skip that PMID (don't retry indefinitely).

## Token budget

- Your context is independent from main thread, so 50–80K tokens OK.
- Do NOT call `mcp__pubmed__pubmed_fetch_fulltext` — abstracts only.
- One batched `pubmed_fetch_articles` call > multiple single fetches.

## Critical rules

- **DO NOT invoke any other MCP** than `mcp__pubmed__*`. OE is owned by the main
  thread; calling OE here wastes budget.
- **DO NOT re-cite {PAPER_PMID}** as supporting evidence — that's the anchor paper.
- **DO NOT write markdown narrative** outside the JSON — main thread only reads JSON.
- Be honest about `relevance_score`: ≥ 0.7 means "strongly addresses Q";
  < 0.5 means "tangential" → probably exclude.

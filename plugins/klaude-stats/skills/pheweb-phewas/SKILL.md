---
name: pheweb-phewas
description: "pheweb-phewas: rsID list × a PheWeb instance (UK Biobank / BioBank Japan) → full PheWAS record + deduplicated phenotype functions + target-domain filter, as Excel + Word + Chinese SOP/decision log. Trigger: /pheweb, /phewas, PheWeb, PheWAS, pheweb.jp, pheweb.org, BioBank Japan, UKB-Neale, sentinel SNP, 查 SNP 的 phenotype, SNP 表型查詢, 這些 rs 號查一下功能, gene bank 查 SNP, 查基因功能表格, 幫我查這些 SNP 對應什麼疾病, checking genes functions."
---

# PheWeb PheWAS — SNP list → phenotype function tables

Given a list of rsIDs and a PheWeb instance, retrieve **every** phenotype result for each
variant, then build three tables an advisor can audit:

| Table | Content |
|---|---|
| **a** | the complete PheWAS record — every phenotype code, unfiltered, ranked by p-value |
| **b** | table a's significant rows with near-duplicate phenotypes merged into one "phenotype function" per group |
| **c** | table b restricted to the target disease domains the user cares about |

Plus a below-cut-off reference sheet, a targeted-lookup sheet that documents *absence* of
signal, a 5-column summary, and a Chinese SOP + decision-log document for a supervisor.

## Hard-won facts about PheWeb — read before touching the site

1. **The API and the web page are the same data.** A PheWeb variant page is server-rendered:
   the entire result set is embedded in the HTML as `window.variant = {...}`, and the
   First / Previous / Next / Last controls only re-paginate that object client-side — no
   further network request. So `/api/variant/<id>` returns exactly what the table shows, all
   pages at once. **Never hand-copy pages; never claim "the API only gives page 1".**
   `pheweb_verify.py` proves it row-by-row and produces the evidence sheet — always run it,
   because "did you only read the first page?" is the first question a reviewer asks.
2. **`/api/autocomplete` does prefix matching.** Querying `rs11207982` also returns
   `rs112079820` and `rs112079827`. Take the hit whose `display` starts with
   `"<rsid> ("` — never the first element.
3. **A missing variant returns `null`, not a 404.** HTTP 200 + body `null` means the
   instance does not carry that variant (usually QC / allele-frequency filtering). Fall back
   to the Ensembl GRCh37 coordinate and probe allele pairs before declaring it absent —
   `pheweb_fetch.py` does this automatically and it is how rs17026651 was found on PheWeb.jp
   after failing on UKB-Neale.
4. **Coordinates are GRCh37 on the instances above.** Ensembl's default REST endpoint returns
   GRCh38; use `grch37.rest.ensembl.org`.
5. **Each instance has a different phenotype vocabulary — the domain map is NOT portable.**
   UK Biobank (Neale) has *no* serum-biomarker GWAS at all (no LDL/HDL/TG/HbA1c/BMI), only
   questionnaire and ICD-10 traits. BioBank Japan has all of them as first-class traits plus
   separate codes for stable vs unstable angina, atrial flutter, ventricular arrhythmia and
   peripheral arterial disease. Always run `pheweb_vocab.py` and write a fresh config.
6. **Phenotype count can vary per variant** on some instances (BBJ: 300–332), because a trait
   is listed only where it has data at that position. UKB-Neale is a constant 2418.
7. Be polite: one request every 2 seconds. The fetch script caches, so re-runs are free.

## Workflow

**Step 0 — settle three things with the user before fetching.**
(a) the SNP list; (b) which instance(s) — if more than one, **keep the outputs in separate
files**, never merge, because population, trait definitions, sample sizes and models differ
and the p-values are not comparable; (c) the significance cut-off. If they have no view,
propose genome-wide `5e-8` and say what a laxer threshold would add. State the choice
explicitly in every deliverable — an unstated filter is what makes the first draft wrong.

**Step 1 — fetch.**
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pheweb_fetch.py --site https://pheweb.jp --snps snps.txt --out ./pheweb_jp_raw
```

**Step 2 — verify browser vs API.**
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pheweb_verify.py --site https://pheweb.jp --raw ./pheweb_jp_raw --out BBJ_verification.json
```

**Step 3 — read the vocabulary, then author the config.** This is the judgement step and it
is yours, not the script's.
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pheweb_vocab.py --raw ./pheweb_jp_raw                 # everything, by category
python3 ${CLAUDE_SKILL_DIR}/scripts/pheweb_vocab.py --raw ./pheweb_jp_raw --pcut 1e-3     # only what has signal
```
Write `config.json` (schema in `reference/config_schema.md`; working examples in
`reference/config_example_bbj.json` and `config_example_ukb.json`). Two judgement calls:

- **Grouping for table b.** Merge only *redundant codings of one phenotype* — e.g. simvastatin
  / atorvastatin / rosuvastatin / "cholesterol lowering medication" / its "none of the above"
  complement all become one lipid-lowering-medication group; type-2-diabetes ancestry
  meta-analyses merge with the cohort's own T2D trait; GxE tests merge with their parent trait.
  Do **not** merge distinct measurements (LDL vs HDL vs triglycerides) — they are different
  phenotypes and their effects can point in opposite directions.
- **Domain assignment.** Mark a row `direct` when the trait literally is one of the user's
  listed domains, `borderline` when it is a judgement call (resting pulse rate under
  arrhythmia; arterial stiffness under blood pressure; family-history traits, which are
  proxies for a relative's disease; lean mass under anthropometry; a drug used as a proxy for
  its indication). Never silently include a borderline row — put it in with the flag and ask.

The builder prints any cut-off-reaching phenocode missing from `groups`. **Never ship with a
non-empty UNMAPPED list** — every significant hit must be a deliberate classification.

**Step 4 — build.**
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/pheweb_build.py --raw ./pheweb_jp_raw --config config.json \
    --out-dir . --prefix "BBJ-PheWeb.jp_" --verification BBJ_verification.json
```

**Step 5 — write the SOP / decision log** (Traditional Chinese, for the supervisor).
Follow `reference/sop_outline.md`. It is not optional when the work is for someone else: the
user is usually relaying results to an advisor and needs to defend every judgement call.

**Step 6 — report.** Give the user: what was found per SNP; which domains came up empty and
that this means *no association was detected in this dataset*, not that none exists; the
threshold and what it excluded; and the open questions for the advisor.

## Reporting rules that keep this defensible

- Table a is **never filtered**. It is the raw query record and must line up with the website
  row-for-row. Filtering belongs to tables b and c, with the threshold stated.
- An empty cell in table c must be backed by the targeted-lookup sheet, so "no signal" is
  evidenced rather than looking like a missed query.
- Use "未達統計顯著 / no association detected in this dataset", never "沒有關聯 / no
  association exists". A negative PheWAS result is not evidence of no effect — especially for
  low-prevalence endpoints (heart failure, PAD, intracranial haemorrhage) where power is poor.
- Report beta on the source's own scale. Neale-lab betas for binary traits are linear-model
  coefficients, not log-odds; do not convert.
- Never merge two instances into one table. A side-by-side comparison table is fine; a merged
  p-value column is not.
- Keep the raw JSON and the scripts alongside the deliverables so the whole thing re-runs.

## Files

```
scripts/pheweb_fetch.py    rsID → variant id (exact match + Ensembl GRCh37 fallback) → raw JSON
scripts/pheweb_verify.py   page HTML vs API, row-by-row, per SNP → evidence JSON
scripts/pheweb_vocab.py    phenotype vocabulary of a downloaded set, by category / by p-value
scripts/pheweb_build.py    config + raw → xlsx (8 sheets) + docx + build_stats.json
reference/config_schema.md          config.json fields
reference/config_example_bbj.json   BioBank Japan, 9 cardiometabolic domains
reference/config_example_ukb.json   UK Biobank (Neale), same 9 domains
reference/pheweb_instances.md       known instances and what they do / do not carry
reference/sop_outline.md            Chinese SOP + decision-log structure
```

Requires `openpyxl` and `python-docx`.

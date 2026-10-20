# Known PheWeb instances

| Instance | URL | Traits/variant | Population | Verified |
|---|---|---|---|---|
| UK Biobank, Neale lab | `https://pheweb.org/UKB-Neale` | 2418 (constant) | UK, mostly European ancestry | 2026-08 |
| BioBank Japan | `https://pheweb.jp` | 300–332 (varies) | Japanese, ~260k BBJ participants | 2026-08 |

Others exist on the same platform (`pheweb.org/<cohort>`, FinnGen-style deployments). The
scripts are instance-agnostic: pass `--site` and re-derive the phenotype vocabulary. Anything
serving `/api/autocomplete` and `/api/variant/<chr:pos-ref-alt>` will work.

## What each instance does and does not carry

**UK Biobank (Neale)** — questionnaire, medication-code, ICD-10 and body-composition traits.
**No serum biomarkers at all**: LDL, HDL, triglycerides, total cholesterol, HbA1c and BMI do
not exist as traits. Dyslipidaemia can only be proxied by self-reported "high cholesterol" and
lipid-lowering medication codes; adiposity by weight, fat mass and waist circumference. Also
no separate codes for stable vs unstable angina, atrial flutter, ventricular arrhythmia, or
peripheral artery disease. If the target list contains quantitative biomarkers, say so up
front rather than silently substituting proxies.

**BioBank Japan** — quantitative biomarkers (LDLC, HDLC, TG, TC, Glucose, HbA1c, BMI, BW,
Height), blood pressure (SBP, DBP, PP, MAP), ATC drug classes (`ATC_C10AA` = HMG CoA reductase
inhibitors, `ATC_C02/C03/C07/C08/C09` = antihypertensives, `ATC_A10` = diabetes drugs), and
fine-grained cardiovascular codes (CAD, MI, SAP, UAP, CHF, Atrial_Flutter,
Ventricular_Arrhythmia, IS, Intracerebral_Hemorrhage, Subarachnoid_Hemorrhage, PAD). Some
hosted traits are multi-ancestry meta-analyses including non-Japanese cohorts (Suzuki2024
T2D, Ishigaki2022 RA, Sato2023 cancer, Shirai2022 autoimmune/allergy) — the `citation` field
identifies them. Traits ending "(GxE, combination tests across environments)" are
gene-environment interaction tests, not main-effect GWAS.

## When a variant is missing

Missing from one instance does not mean missing everywhere — rs17026651 returns `null` on
UKB-Neale but resolves to `3:30879358-C-G` (GADL1) on PheWeb.jp. If it is absent everywhere
you need, the alternatives are Open Targets Genetics, the GWAS Catalog, or a proxy SNP in
high linkage disequilibrium. Do not silently fill the gap from a different database — mixing
sources makes the p-values incomparable. Ask.

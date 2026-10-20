# config.json schema (pheweb_build.py)

| Field | Type | Required | Meaning |
|---|---|---|---|
| `cohort` | string | yes | display name, e.g. `"BioBank Japan (PheWeb.jp)"` |
| `site` | string | yes | base URL |
| `population` | string | no | one line on ancestry / sample size — goes into the README sheet |
| `retrieved` | string | no | ISO date of the fetch |
| `build` | string | no | genome build, default `"GRCh37 / hg19"` |
| `p_cut` | number | yes | cut-off feeding tables b and c, e.g. `5e-8` |
| `p_cut_label` | string | no | how it is written in prose, e.g. `"5e-8"` |
| `header_colour` | string | no | Excel header fill, 6-digit hex without `#` |
| `snps` | string[] | no | fixes row order; defaults to the filenames in `--raw` |
| `domains` | string[] | yes | target domains, in the order they should appear. Prefix with a number (`"1. Coronary artery disease / MI / angina"`) so sorting is stable |
| `groups` | object | yes | `phenocode -> [group_label, domain_or_null, "direct"\|"borderline — advisor to confirm"\|null]` |
| `panel` | array | no | `[[domain, phenocode], ...]` — the targeted-lookup sheet, listed regardless of significance |
| `notes` | string[] | no | free-text caveats; appended to the README sheet and to the Word notes |

## groups

Several phenocodes mapping to the same `group_label` are merged into one row of table b;
the most significant member becomes the representative and the rest are listed in the
"Merged from" column. `domain = null` keeps the group out of table c.

```json
"groups": {
  "LDLC":  ["LDL-cholesterol", "7. Dyslipidaemia / lipids / statins", "direct"],
  "TC":    ["Total cholesterol", "7. Dyslipidaemia / lipids / statins", "direct"],
  "102":   ["Pulse rate (resting heart rate)", "3. Arrhythmia / AF / flutter",
            "borderline — advisor to confirm"],
  "CRP":   ["C-reactive protein", null, null]
}
```

Every phenocode that reaches `p_cut` must appear here. The builder prints an UNMAPPED list
when one does not; treat a non-empty list as a build failure.

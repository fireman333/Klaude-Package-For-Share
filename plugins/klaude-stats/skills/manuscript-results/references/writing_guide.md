# Medical Manuscript Results Section — Writing Guide

This guide provides standard phrases, templates, and conventions for writing the Results section of clinical research manuscripts. Follow these patterns to produce publication-quality prose.

## Table of Contents
1. [Number Formatting Rules](#number-formatting)
2. [Study Population Paragraphs](#study-population)
3. [Survival / Time-to-Event Analysis](#survival-analysis)
4. [Regression Analysis](#regression-analysis)
5. [Interaction / Subgroup Analysis](#interaction-analysis)
6. [Propensity Score Matching](#psm-analysis)
7. [Predictive Performance](#predictive-performance)
8. [Chinese (繁體中文) Templates](#chinese-templates)
9. [Common Pitfalls to Avoid](#pitfalls)

---

## Number Formatting Rules <a name="number-formatting"></a>

### P-values
- P < 0.001 → write `P < 0.001`
- 0.001 ≤ P < 1.0 → 3 decimal places: `P = 0.034`
- Always capitalize P when standing alone, lowercase p when in-line as part of a compound phrase
- Use en-dash in ranges, not hyphen

### Effect Estimates
- HR/OR with 95% CI: `HR, 1.45; 95% CI, 1.12–1.88; P = 0.005`
- Alternative format: `HR 1.45 (95% CI 1.12 to 1.88, P = 0.005)`
- Follow journal style if specified

### Percentages and Counts
- Percentages to 1 decimal: `245 (34.2%)`
- For small samples (N < 100), consider whole percentages: `12 (24%)`

### Survival Rates
- Express as percentage: `The 5-year survival rate was 72.3% (95% CI, 68.1%–76.5%)`

### CIF Values
- Express as percentage: `The 5-year cumulative incidence of cardiovascular death was 15.2% (95% CI, 12.1%–18.3%)`

---

## Study Population Paragraphs <a name="study-population"></a>

### Opening Paragraph Template (English)

```
A total of [N_total] patients met the inclusion criteria. After excluding
[N_excluded] patients ([reasons]), [N_final] patients were included in
the final analysis ([Table/Figure reference for flowchart]). Of these,
[N_group1] ([%]) were in the [group1_name] and [N_group2] ([%]) were
in the [group2_name]. The [follow_up_description].
```

### Baseline Characteristics Paragraph

```
Baseline characteristics of the study population are presented in
[Table 1]. Compared with [group2_name], [group1_name] were [older/younger]
(mean age, [X] vs [Y] years; P = [value]), more likely to be [male/female]
([X%] vs [Y%]; P = [value]), and had a higher prevalence of [condition]
([X%] vs [Y%]; P = [value]). There were no significant differences between
groups in [list of non-significant variables].
```

**Key conventions:**
- List the most clinically important differences first (age, sex, comorbidities)
- Group non-significant variables together rather than listing each one
- Use "Compared with [reference group]" to establish direction

---

## Survival / Time-to-Event Analysis <a name="survival-analysis"></a>

### Kaplan-Meier Results

```
During [follow_up_description], [N_events] patients ([%]) experienced
[outcome]. The event rate was higher in the [group1_name] compared with
the [group2_name] ([N1_events] [[%1]] vs [N2_events] [[%2]]).
Kaplan-Meier analysis demonstrated significantly [lower/higher] survival
in the [group1_name] (log-rank P [= value / < 0.001]) ([Figure reference]).
The [X]-year survival rates were [rate1]% (95% CI, [ci]) in the [group1_name]
and [rate2]% (95% CI, [ci]) in the [group2_name].
```

For non-significant results:
```
There was no significant difference in [outcome] between the [group1_name]
and [group2_name] (log-rank P = [value]) ([Figure reference]).
```

### Competing Risk Results

```
Accounting for the competing risk of [competing_event], the [X]-year
cumulative incidence of [primary_event] was [CIF1]% (95% CI, [ci])
in the [group1_name] and [CIF2]% (95% CI, [ci]) in the [group2_name]
(Gray's test P [= value / < 0.001]) ([Figure reference]).
```

---

## Regression Analysis <a name="regression-analysis"></a>

### Univariate Results

```
In univariate [Cox regression / logistic regression] analysis,
[variable1] (HR, [value]; 95% CI, [range]; P = [value]),
[variable2] (HR, [value]; 95% CI, [range]; P = [value]),
and [variable3] (HR, [value]; 95% CI, [range]; P = [value])
were significantly associated with [outcome] ([Table reference]).
```

### Multivariate Results

```
After adjustment for [list of covariates], [variable_of_interest]
remained independently associated with [increased/decreased] risk of
[outcome] (adjusted HR, [value]; 95% CI, [range]; P = [value])
([Table reference]).
```

For non-significant adjusted results:
```
After multivariable adjustment, the association between
[variable_of_interest] and [outcome] was no longer statistically
significant (adjusted HR, [value]; 95% CI, [range]; P = [value]).
```

### Multiple Significant Predictors

```
In the multivariate model, independent predictors of [outcome] included
[variable1] (adjusted HR, [value]; 95% CI, [range]; P = [value]),
[variable2] (adjusted HR, [value]; 95% CI, [range]; P = [value]),
and [variable3] (adjusted HR, [value]; 95% CI, [range]; P = [value])
([Table reference]).
```

---

## Interaction / Subgroup Analysis <a name="interaction-analysis"></a>

### Significant Interaction

```
There was a significant interaction between [grouping_variable] and
[modifier_variable] on the risk of [outcome] (P for interaction = [value]).
The association between [grouping_variable] and [outcome] was more
pronounced in patients with [subgroup_description] (HR, [value]; 95% CI,
[range]) compared with those without (HR, [value]; 95% CI, [range])
([Figure reference]).
```

### No Significant Interaction

```
The association between [grouping_variable] and [outcome] was consistent
across prespecified subgroups, with no significant interactions observed
(all P for interaction > 0.05) ([Figure reference]).
```

---

## Propensity Score Matching <a name="psm-analysis"></a>

### PSM Paragraph Template

```
To account for potential confounding, propensity score matching was
performed. After [1:1 / 1:N] nearest-neighbor matching with a caliper
of [X] standard deviations of the logit of the propensity score,
[N_matched] matched pairs were identified ([Table reference]).
Standardized mean differences for all covariates were below [threshold]
after matching, indicating adequate balance ([Figure reference for love plot]).
In the matched cohort, [group1_name] was associated with [significantly
higher/lower / no significant difference in] risk of [outcome]
(HR, [value]; 95% CI, [range]; P = [value]), consistent with the
findings from the unmatched analysis.
```

---

## Predictive Performance <a name="predictive-performance"></a>

### C-statistics / AUC Paragraph

```
The discriminative performance of the clinical model for predicting
[outcome] yielded a C-index of [value] (95% CI, [range]). Addition of
[variable] to the clinical model significantly improved discrimination
(C-index, [new_value]; 95% CI, [range]; ΔC-index, [delta]; P = [value])
([Table reference]).
```

For non-significant improvement:
```
Addition of [variable] to the clinical model did not significantly
improve discrimination (ΔC-index, [delta]; P = [value]).
```

---

## Chinese (繁體中文) Templates <a name="chinese-templates"></a>

### 研究族群

```
共 [N_total] 名患者符合納入條件。排除 [N_excluded] 名患者後（[排除原因]），
最終 [N_final] 名患者納入分析（[表/圖參照]）。其中 [N_group1] 名（[%]）為
[group1]，[N_group2] 名（[%]）為 [group2]。[追蹤時間描述]。
```

### 基線特徵

```
研究族群之基線特徵如[表1]所示。與[group2]相比，[group1]年齡較
[大/小]（平均年齡 [X] vs [Y] 歲；P = [value]），[男/女]性比例較高
（[X%] vs [Y%]；P = [value]），且 [疾病] 盛行率較高（[X%] vs [Y%]；
P = [value]）。兩組在 [變數列表] 方面無顯著差異。
```

### 存活分析

```
追蹤期間共 [N_events] 名患者（[%]）發生 [結局事件]。Kaplan-Meier 分析
顯示 [group1] 之存活率顯著[低/高]於 [group2]（log-rank P [= value / < 0.001]）
（[圖參照]）。[X] 年存活率於 [group1] 為 [rate1]%（95% CI, [ci]），
於 [group2] 為 [rate2]%（95% CI, [ci]）。
```

### 迴歸分析

```
經多變量 [Cox 迴歸 / 邏輯斯迴歸] 校正 [共變數列表] 後，[變數] 仍為
[結局事件] 之獨立預測因子（校正後 HR, [value]；95% CI, [range]；
P = [value]）（[表參照]）。
```

---

## Common Pitfalls to Avoid <a name="pitfalls"></a>

1. **Don't interpret in Results** — Save "This may be due to..." for Discussion
2. **Don't say "trend toward significance"** — If P ≥ 0.05, it's not significant. Period.
3. **Don't use "dramatically" or "markedly"** — Let the numbers speak
4. **Don't repeat the Methods** — Don't explain what Cox regression is; just report results
5. **Don't use causal language for observational studies** — Use "was associated with", not "caused" or "led to"
6. **Don't report every non-significant result** — Summarize as "no significant differences were observed in..."
7. **Don't mix effect measures** — If using HR throughout, don't suddenly switch to OR
8. **Always report both point estimate AND CI** — Never report just the P-value
9. **Present results in consistent order** — Unadjusted → adjusted → sensitivity → subgroup
10. **Use past tense** — "The HR was 1.45" not "The HR is 1.45"

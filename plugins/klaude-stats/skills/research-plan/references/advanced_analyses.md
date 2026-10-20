# Advanced Analyses — reviewer 會要、pipeline 原本沒有的七項

2026-08-11 對抗式健檢列出的統計覆蓋缺口。每一項在這裡都給**方法學規格**（估的是什麼、必須報什麼、什麼情況不該做），實作照這份走。

**共通原則**：這七項全部是**額外的分析路線**，不替換既有 step。主分析是哪一條，是要事前指定並登記進 `decision_log.md` 的決策，pipeline 只負責算出來給人看。缺失資料的部分見 `missing_data_protocol.md`，同一個原則。

| # | 步驟 id | 缺什麼 | 群組 |
|---|---|---|---|
| 1 | `evalue` | 未測量干擾的量化 | supplementary |
| 2 | `strobe` | 報告完整性 checklist | manuscript 前 |
| 3 | `rcs_{outcome}` | 非線性（連續變項被強制線性） | outcome |
| 4 | `robust_{outcome}` | 群集 / 重複量測（變異被低估） | outcome |
| 5 | `calibration_{outcome}` | 只有 discrimination，沒有 calibration | supplementary |
| 6 | `weighting_{outcome}` | 只有 PSM，沒有加權法 | supplementary |
| 7 | `landmark_{outcome}` | immortal time / time-varying exposure | outcome |

---

## 1. E-value —— 未測量干擾要多強才能推翻結論

**估的是什麼**：一個未測量的干擾因子，必須同時與暴露、與結果關聯到什麼強度（風險比尺度），才足以把觀察到的效應解釋掉。**不是**「有沒有未測量干擾」的檢定——它不檢定任何東西，它是把「我們無法排除干擾」這句話量化成一個數字。

**公式**（VanderWeele & Ding 2017）。令 RR 為風險比尺度的效應量：

- RR > 1：`E = RR + sqrt(RR × (RR − 1))`
- RR < 1：先取倒數 `RR' = 1/RR`，再套上式
- **CI 的 E-value**：對靠近虛無的那一端界限套同一公式；若該端已跨過 1，E-value = 1（代表不需要任何干擾就能解釋掉）

**HR 與 OR 必須先轉成 RR 尺度，不可直接代入**：
- 罕見結果（< 15%）：OR ≈ RR，可直接用
- 常見結果的 OR：用 `RR ≈ sqrt(OR)`（VanderWeele 的近似）
- HR：罕見結果時 `RR ≈ HR`；常見結果用 `RR ≈ (1 − 0.5^sqrt(HR)) / (1 − 0.5^sqrt(1/HR))`

**必須跟著報的東西**（只給一個數字是沒有意義的）：
1. 點估計的 E-value **與 CI 界限的 E-value**——後者才是「證據能撐多遠」
2. 用哪個轉換、結果發生率是多少（決定了用哪個近似）
3. **一句話的解讀**：「要推翻這個結論，未測量干擾必須與暴露和結果各自關聯到 RR ≥ X，這比已知最強的已測量干擾（例如年齡的 RR = Y）還強／還弱」。**沒有這個對照，E-value 只是一個沒有尺度感的數字。**

**不要做的事**：不要把 E-value 大就說成「所以沒有干擾」。它衡量的是脆弱度，不是不存在。

### 1.1 兩個程式強制的排除條件

| 情況 | 行為 |
|---|---|
| outcome 的 `type` 是 **`competing_risk`** | **硬擋。** `gen_evalue()` 直接 `raise ValueError`，config 產不出來 |
| 計畫的 `estimand_type` 不是 `"causal"`（含未填） | **不擋**，但記一條 `evalue_without_declared_causal_estimand` method warning |

**為什麼 competing risk 是硬擋而不是警告**：這個 pipeline 的每一條迴歸路線遇到 competing-risk outcome 都走 cause-specific Cox（競爭事件當 censoring），所以 `Multi_{id}.xlsx` 裡放的是**病因學 hazard ratio**。E-value 的公式要的是**風險比尺度**的效應，而 HR→RR 的近似前提是「這個 HR 對應到一個真實的風險對比」——competing events 下的 cause-specific HR 不是。算出來的 E-value 會**量化一個不存在的東西的脆弱度**，而它的輸出是一個看起來完全正常的單一數字。**一個會安靜產出無意義 headline 數字的路徑，只能用擋的。**

出路：拿掉這個 step，或把 outcome 重新指定成 cause-specific 的單一終點，並在論文裡說明這個 E-value 指的是那個病因學對比。

**為什麼 estimand 只是警告**：對一個關聯性估計算 E-value 不是算錯，只是回答了沒有人問的問題（「未測量干擾要多強才能解釋掉這個**因果**效應」預設了因果解讀）。要嘛在 `study.estimand_type` 填 `"causal"` 並在討論裡辯護，要嘛拿掉這個 step。**generator 從來不會自己替你加 E-value step**，正是因為這個判斷不該由程式代做。

---

## 2. STROBE checklist —— 產物能不能填滿投稿要求

**做什麼**：把 22 項 STROBE（官方條目 22 條，展開 a/b/c 子項後共 **34 列**），三種版本 cohort / case-control / cross-sectional 依 `study.design` 選，逐項對應到 pipeline 的實際產物，產出 `STROBE_checklist.xlsx` 與 `.md`。

每一項四種狀態：

| 狀態 | 意思 |
|---|---|
| `covered` | 有具體產物可指——**必須寫出檔名與位置**（哪個 xlsx 的哪個分頁、哪張圖） |
| `partial` | 有部分材料，但還要人補文字 |
| `missing` | pipeline 產不出來，必須人自己寫（例如 funding、ethics approval） |
| `n/a` | 官方 checklist 於**該設計**留白，本研究不適用 |

**依設計分版的是哪五項**（其餘 29 列三種設計共用）：

| 項目 | cohort | case-control | cross-sectional |
|---|---|---|---|
| 6a 參與者 | 納入條件 + 來源 + **追蹤方式** | 納入條件 + **病例確認與對照選取及其理由** | 納入條件 + 來源 |
| 6b 配對 | 配對條件 + 暴露／非暴露人數 | 配對條件 + **每病例幾個對照** | `n/a` |
| 12d 統計 | **追蹤流失**如何處理 | **配對**在分析中如何處理（條件式迴歸／配對層分層） | **抽樣策略**如何反映在分析 |
| 14c 描述 | **追蹤時間**（平均與總量） | `n/a` | `n/a` |
| 15 結果資料 | 結果事件數／隨時間摘要 | **各暴露類別人數** | 結果事件數／摘要 |

`study.design` 無法對應到這三種（未填、`rct`、自由文字）→ 發 QC warning、**列出全部項目，且不因設計把任何一格標成 `n/a`**（6b 改標 `partial` 並要求先補 `study.design`）。猜設計比列錯項目更危險，因為它會把不該留白的格子標成不適用。**注意 `n/a` 仍可能因為資料而出現**（例如 16b 沒有連續變項被分類），那是資料事實、不是設計推論。

**硬性要求**：`covered` 一定要有指標，不能只打勾。**打勾但指不出東西的 checklist 比沒有 checklist 更糟**——它會讓人以為做過了。

pipeline 天然能對應的（各自指向產物）：參與者流程 → `Flowchart.xlsx`；描述性資料 → `Table1.xlsx`；結果資料與主要結果 → `KM_*`／`Uni_*`／`Multi_*`；缺失資料 → `Missingness.xlsx`／`MI_*.xlsx`；其他分析（亞群、交互作用、sensitivity）→ 對應各步驟產物；限制 → `decision_log.md` 的 F 節。

**必須標成 `missing` 而不是硬湊的**：研究場域與招募期間、偏差來源的敘述、樣本數的事前理由、資金來源、倫理審查。這些 pipeline 不知道，硬填就是造假。

---

## 3. RCS —— 連續變項不要預設線性

**問題**：目前 `covariates[].scale` 只做除法，等於強制假設 log-hazard（或 log-odds）與該變項成線性。年齡、eGFR、BMI、血壓在臨床上幾乎都不是。

**規格**：
- 用 restricted cubic spline，**預設 4 knots**，位置取 Harrell 建議的百分位（4 knots → 5th, 35th, 65th, 95th）。n < 100 降為 3 knots
- **非線性檢定**：檢定第 2 個之後的 spline 項是否同時為 0（likelihood ratio test）。報 `p-nonlinear`
- **必產圖**：以參考值為中心的 HR / OR 曲線加 95% 信賴帶，x 軸標出 knot 位置與該變項的分布（rug 或直方圖）
- **參考值必須指定且寫出來**：曲線的形狀不變，但「相對於誰」的 HR 完全取決於參考值。預設用中位數，並在圖與表上明寫

**判讀規則寫進產物**：`p-nonlinear ≥ 0.05` **不等於**「線性是對的」——它只代表這個樣本數沒偵測到偏離。要說線性合理，要同時看曲線與信賴帶的形狀。

**什麼時候不要做**：事件數太少（每個 spline 參數 < 10 events）時 RCS 會過擬合，改報線性並在限制寫明。

### 3.1 knots 數不要往上加 —— 實測

2026-08-11 用**已知真值** `log-HR = 0.02×(age−60)²`（n=8000、6929 events、x 均勻分布於 50–70、參考值固定 60）掃 knots 3–7，把輸出的曲線讀回來逐點對照解析真值：

| knots | max\|誤差\| | mean\|誤差\| | 中段(55–65) mean\|誤差\| | 曲線最低點（真值 60） |
|---|---|---|---|---|
| 3 | 0.175 | 0.091 | 0.061 | 59.92 |
| **4（預設）** | **0.115** | **0.053** | **0.031** | **59.92** |
| 5 | 0.123 | 0.060 | 0.039 | 59.92 |
| 6 | 0.118 | 0.058 | 0.042 | 59.33 |
| 7 | **1.562** | 0.545 | 0.135 | 59.73 |

**誤差不是隨 knots 單調縮小，預設的 4 knots 在這個掃描裡最好。** k=7 的誤差集中在兩尾（左尾與右尾的 mean\|誤差\| 各約 1.33），而該處 SE 只有 0.059 —— **是「有把握地錯」，不是「不確定」**。x=69.8 估出 0.35，真值 1.91，而且信賴帶不涵蓋真值。

> 所以：**「配得不夠好就多加 knots」在這裡是錯的建議。** 腳本在 knots > 5 時會發 `[QC_WARNING]`。真的要加，先看曲線兩尾對不對得上資料再報。
>
> 這個掃描沒有做到的：只驗了一種資料生成過程（單一連續變項、均勻分布、二次真值）。k=7 兩尾崩掉的**機制**未經根因分析——可能是高 knot 數下 basis 近共線，也可能是外側 knot 之外線性外推的斜率被估歪。若日後要在真實資料用 >5 knots，這一段要重驗。

---

## 4. 群集與重複量測 —— 變異不要被低估

**問題**：同一家醫院、同一位醫師、同一個病人的多次測量，彼此不獨立。忽略它會讓標準誤偏小、CI 偏窄、p 偏小——**方向永遠是讓結果看起來比實際更顯著**。

**三條路，依資料結構選**：

| 資料結構 | 方法 | 實作 |
|---|---|---|
| 群集（中心 / 醫師），只要修正變異 | **cluster-robust SE**（`method: "cluster_robust"`，預設） | Cox：`lifelines.CoxPHFitter.fit(..., cluster_col=)`；logistic：`statsmodels` `cov_type='cluster'` |
| 重複量測（同一人多筆） | **GEE**（`method: "gee"`） | `statsmodels.GEE`，correlation structure 要指定並寫出來 |
| 群集，且想估群集間的變異 | **本 pipeline 不提供** | 見下方 `mixed` 撤除說明——那是 R `lme4::glmer` 的工作 |

**硬性要求**：
- **群集數 < 30 時 cluster-robust SE 本身會偏低**，要標註並考慮 wild bootstrap 或改報 mixed model
- correlation structure（exchangeable / AR(1) / independent）**必須寫進產物**，不可用預設值而不提
- 與未修正版本並排比較，讓人看得到修正前後 CI 差多少——**這個對照本身就是說服 reviewer 的材料**

**`mixed` 已於 2026-08-11 撤除，現在給它會直接 `ValueError`（不是警告、不是降級）。** 理由：Python 這邊沒有可靠的 GLMM。`statsmodels` 的變分貝氏近似區間偏窄是已知性質；在一份有真實中心效應的測試資料上，它把暴露的 SE 只放大 **4.8%**，而 cluster-robust sandwich 放大了 **148%**——同一個群集結構，兩者差 30 倍。一個會系統性低估變異的方法，留著當選項只會被選到。

> **撤除的形式是「拒絕」不是「警告」，這是刻意的。** 舊版是選到 `mixed` 記一條 method warning 然後照跑——但 method warning 的處置全靠人念出來，而這個選項錯的方向剛好是**讓結果看起來更顯著**。真的需要 random-effect 變異估計 → R `lme4::glmer`，在 pipeline 外跑完把結果帶進來。
>
> ⚠ `method` **沒有白名單**：`cluster_robust` 與 `gee` 是有文件的兩個值，`mixed` 被明確擋掉，但**其他任意字串會被原樣傳下去、不做驗證**。拼錯不會有人擋你。

**GEE 未驗到的極端**：測試顯示 exchangeable 比 cluster-robust 有效率（涵蓋率兩者都 92%，機制是 working correlation 正確時的 GLS 效率增益）。但那份資料的暴露是**個人層級**。多中心研究常見的是**暴露完全在群集層級**（整家醫院都做或都不做），此時 exchangeable 沒有群集內對比可用，行為可能完全不同——**這個極端沒測過**，真實資料上兩種方法都跑一次再比。

**與 Step 3.5 診斷的關係**：`survival-diagnostics` 若標了 clustering，這一步就不是可選的。同一個 flag 也會讓 MI 步驟擋下來（見 `missing_data_protocol.md` §6）。

---

## 5. Calibration —— discrimination 不等於模型好用

**問題**：目前只有 AUC / C-index。**AUC 高的模型可能系統性高估或低估風險**，而臨床決策看的是絕對風險。只報 discrimination 是預測模型論文最常被打回的理由之一。

**必產**：

| 項目 | 內容 |
|---|---|
| **Calibration plot** | 預測風險 vs 觀測風險，分十分位；存活結果要在指定時間點用 KM 估觀測值 |
| **Calibration slope / intercept** | slope < 1 = 過度擬合（極端預測太極端）；intercept ≠ 0 = 整體偏移 |
| **Brier score** | 兼顧 discrimination 與 calibration 的整體準確度；存活資料用 IPCW 加權版本 |
| **Optimism-corrected 內部驗證** | **bootstrap（預設 500 次；200 是協議下限與快速模式，輸出會標 FAST MODE）**，回報 optimism-corrected 的 C-index 與 slope。split-sample 在典型臨床樣本數下不穩定，不要用 |

**必須分流，而且現在有程式強制**：這一整套是**預測模型研究**才需要。若研究問題是「X 與 Y 有沒有關聯」（病因學），報 C-index 是可以的，但**不要把它說成模型效能**，也不需要 calibration。產物要明寫這個分流判斷。

> **2026-08-11 起 `gen_calibration()` 會 raise**，除非計畫解析出來的 `model_purpose` 是 `"prediction"`。這一條在本文件從第一版就寫著，但在那之前**沒有任何東西強制它**——所以 calibration step 可以安靜地生在一個病因學研究上。現在產 config 就會失敗（`generate_configs.py` 以 exit 2 收場）。
>
> `model_purpose` 的宣告位置，**最窄的贏**：
> 1. `pipeline[].model_purpose`（該 step 自己）
> 2. `advanced_analyses.calibration.study_purpose`
> 3. `study.model_purpose`，再來是計畫頂層 `model_purpose`
>
> 正規化：`prediction`/`predictive`/`prognostic_model` → `prediction`；`etiologic`/`aetiologic`/`association`/`associational`/`descriptive` → `etiologic`；`unspecified`/`unknown`/`""` → 未指定。**其他值 → FATAL。**
>
> ⚠ `model_purpose` **進計畫指紋**（以決策形式雜湊）。為了讓 calibration 跑得起來而把它從 `etiologic` 改成 `prediction`，會讓既有的 reviewer challenge 失效——**那是刻意的**，因為那個改動改變了整篇論文在主張什麼。

**Decision curve analysis** 為選配：要做就必須指定臨床上合理的門檻機率範圍，不要掃 0–1 全域。

---

## 6. IPTW 與 overlap weighting —— PSM 不是唯一的傾向分數用法

**問題**：目前只有配對。配對會丟掉配不到的人，改變了推論母體（估的是 ATT，且是「有配對到的那群人」的 ATT），而且沒有 positivity 診斷。

**必產**：

| 項目 | 為什麼 |
|---|---|
| **傾向分數分布圖（依組別）** | positivity 的第一手證據。沒有重疊就沒有可比性，加權救不了 |
| **Stabilized weights** | 未穩定化的權重變異極大，會讓 CI 爆炸 |
| **權重分布與極端值** | 最大權重、權重 > 10 的人數。**單一個案主導結果是加權法最常見的失效模式** |
| **ESS（有效樣本數）** | 加權後真正的資訊量，通常遠小於 N。不報 ESS 等於誇大精確度 |
| **加權前後 SMD** | 全部 < 0.1 才算平衡；要逐變項列，不要只給平均 |
| **Overlap weighting** | 極端權重嚴重時的替代方案，且它的目標母體有明確定義（overlap population） |
| **Trimming 的影響** | 有 trim 就要說明門檻、被 trim 掉幾人、trim 前後結果差多少 |

**estimand 必須寫出來**：IPTW 預設估 ATE、PSM 估 ATT、overlap weighting 估 ATO。**這三個回答的是不同的臨床問題**，不可混談，也不可因為哪個 p 值比較小就選哪個。

### 6.1 positivity 怎麼處理（2026-08-11 定案）

**blocking 只有兩種結構性失效**：完全無共同支持（兩組傾向分數範圍不相交）、傾向分數模型配不出來。這兩個是事實不是選出來的數字，加權在此無論如何都產不出有意義的估計。

`overlap_coefficient < 0.10` 與 `> 20% 落在共同支持外`是**篩選門檻不是效度門檻**——文獻沒有共識切點。它們**不擋**，但會觸發一件事：

> **邊際 positivity 時，同一個 step 內自動加算 ATO companion。** 同一個傾向分數模型、只換成 overlap weights，成本近乎零，兩個估計寫進同一本 workbook 的 `Outcome_model` 分頁，各自標明 estimand。

為什麼是這個設計，而不是「擋下」或「只發警告」：

| 做法 | 問題 |
|---|---|
| 兩個門檻維持 blocking | 沒有共識的數字當硬門檻，設錯的代價是**整個分析被擋下** |
| 只發 warning | warning 不擋 manuscript，邊際重疊的 ATE 會單獨走進論文 |
| **加算 companion（採用）** | 門檻設錯的代價變成**多跑一個分析**（成本近零）；且沒有任何邊際重疊的估計會單獨存在 |

**「不准單獨報」由建構保證，不是靠規則。** 不用另開 pipeline step、不靠 `depends_on`——companion 在同一個 step 裡算完就在檔案裡，plan 寫不出繞過它的形狀。

三種情況：

| 情況 | 行為 |
|---|---|
| `method: iptw` + 邊際 positivity | 加算 ATO companion，兩列並排，QC warning 明講「兩個一起報，單報任一個就是選擇性呈現」 |
| `method: overlap` + 邊際 positivity | **不加**——它估的本來就是 ATO。照樣發 warning |
| positivity 正常 | 不加，也不警告 |
| companion 算不出來 | **blocking**。邊際重疊下不允許單獨報 ATE |

**trimming 不能替代 companion**：trim 後的 ATE 仍然是 ATE，只是換成一個由資料（而非研究問題）定義的母體。而且 `trim.enabled: true` 但實際 trim 掉 0 人是可能的，用旗標判斷會被騙。

**兩個診斷值在 trim 之前算，且 trim 不會解除旗標**——丟掉個案改變的是母體，不會創造出原本不存在的重疊。

**抽取端也成對**：`manuscript-results` 的 `weighting` extractor 把 `Outcome_model` 分頁的每一列**整組**抽出（各自帶 estimand），有 companion 時把 `must_report_together` 設為 true，並一併帶出 ESS 與 positivity 診斷——加權效應量離開 ESS 與重疊診斷就沒法讀。**只抽 headline 那一列，等於把選擇性呈現搬進草稿材料裡**，所以 extractor 不提供只拿一半的介面。

> **（已過時的說法已移除）** 這裡原本寫「其餘七個進階分析（RCS / robust / calibration / landmark / E-value / STROBE / MI）仍然沒有 extractor」。**現在全部都有了** —— `manuscript-results/scripts/extract_data.py` 的 `EXTRACTORS` 含 `nonlinearity`、`robust-variance`、`calibration`、`immortal-time`、`evalue`、`strobe`、`missing-data`，共 15 種。**不需要再手動去讀那些 workbook。**
>
> 只有 `flowchart`、`reviewer-challenge`、`missing-data` 在推導抽取清單時被標成「不抽取」，那是一行資訊、不是警告。合法的 `type` 字串（底線與連字號混用，照抄）見 `plan_template.md` 的〈`manuscript.analysis_files[].type` 的合法值〉。

**加權後的 outcome model 要用 robust SE**（權重讓觀察值不再獨立）。

---

## 7. Landmark 與 time-varying —— immortal time bias

**問題**：如果暴露分組用了 time zero 之後才知道的資訊（例如「有沒有在住院期間接受手術」），那麼被分到暴露組的人**必須活到接受手術的那一刻**——這段時間他們不可能有事件。忽略它會讓暴露組看起來受到保護，而那是憑空生出來的。

**兩種處置**：

| 方法 | 做法 | 適用 |
|---|---|---|
| **Landmark analysis** | 選一個 landmark 時點 t；排除在 t 之前發生事件或失去追蹤的人；暴露狀態以 t 當下判定；追蹤時間從 t 重新起算 | 簡單、好解釋、reviewer 熟悉 |
| **Extended Cox（time-varying covariate）** | 資料轉成 counting-process 格式（`tstart`, `tstop`, `event`），暴露隨時間改變 | 用到全部資訊，但資料重塑容易出錯 |

**硬性要求**：
- **landmark 時點必須事前指定並說明理由**，不可掃很多時點挑最顯著的那個。做敏感度就一次報多個時點的**全部**結果，不要只報一個
- 要報 landmark 排除了多少人、他們的事件率是多少——**被排除的人不是隨機的**
- extended Cox 的 counting-process 資料要輸出可核對的樣本列（幾個病人的完整 tstart/tstop/event 展開），否則沒有人能驗證重塑是否正確
- **兩種都做時要說明為什麼結果不同**，不可只挑一個報

**偵測**：Step 3.5 的 `survival-diagnostics` 若標了 **`time_varying`**，這一步是必須的、不是選配——`immortal-time` 就是它在閘門表裡指定的補救 step。此時**要擋住把暴露當基線共變項的 naive Cox**，或至少在產物首頁標明該結果有 immortal time 風險。

> ⚠ **`left_truncation` 不一樣，這一步救不了它。** 閘門表把 `left_truncation` 的補救 skill 列為 `None`：**pipeline 裡沒有任何 skill 處理延遲進入**，加一個 `immortal-time` step **不會**讓 Step 3.5 的閘門放行（訊息仍然是「沒有補救」，那不是 bug）。
>
> 兩者常被混為一談，因為都跟「時間軸沒對齊」有關，但失效機制不同：immortal time 是**分組用了 time zero 之後的資訊**（landmark 或 extended Cox 可解）；left truncation 是**個案在進入觀察之前就被放進 risk set**，那要在 risk set 的建構層面處理，本 pipeline 的 KM 與 Cox 都沒有 delayed-entry 介面。
>
> `left_truncation` 的三條出路：① 改 time origin 成每個人都被觀察到的時點 ② 在 pipeline 外處理完把結果帶進來 ③ 走 `diagnostics.overrides.left_truncation`（要真實存在的 decision-log ID + 涵蓋所有 outcome）。**寫進 limitations 不算處置**——那是發表一個附註解的錯數字。

---

## 全部共通的產物要求

1. **每個步驟都要能回答「這個估的是什麼 estimand」**，寫在輸出檔的第一個分頁
2. **與主分析並排對照**，讓人看得到差異，而不是另外一份孤立的表
3. QC 訊號照既有慣例寫 **stderr** 的 `[QC_WARNING]` / `[QC_BLOCKING]`
4. 所有方法學替代與預設值（knots 數、bootstrap 次數、landmark 時點、correlation structure、trimming 門檻）**寫進輸出檔並登記進 `decision_log.md`**——照 `delivery_discipline.md` 規則 2，這些都是有永久 ID 的決策
5. 措辭：未達顯著寫「無統計顯著差異」，不寫「沒有關聯」

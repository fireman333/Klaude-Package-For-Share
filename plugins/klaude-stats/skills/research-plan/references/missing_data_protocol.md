# Missing Data Protocol — 缺失資料評估與多重插補

**為什麼有這份**：2026-08-11 健檢前，這條 pipeline 的每一個回歸模型都是 listwise deletion（`generate_configs.py` 硬寫 `missing_data_handling: "listwise"`），而 Stage Reflector 只會「建議考慮 multiple imputation」——建議了但沒有任何一步能做。這是 reviewer 一定會問、而且會改變結論的缺口。

**核心立場**：complete-case 不是中性的預設值，它是一個**有假設的統計決定**（要求 MCAR，或缺失只與納入模型的共變項有關）。這份協議要求把那個假設寫出來、檢驗它、並且在它站不住時提供替代分析。

---

## 1. 三個步驟

| 步驟 | id | 何時跑 | 產物 |
|---|---|---|---|
| **缺失評估** | `missingness` | Foundation group，**永遠跑** | `Missingness.xlsx` + `Missingness_pattern.png` |
| **多重插補 + 合併分析** | `mi_{outcome_id}` | 評估建議 MI 且使用者採納時 | `MI_{outcome}.xlsx` + `MI_{outcome}_diagnostics.png` |
| **CC vs MI 對照** | 併入上一步 | 同上 | `MI_{outcome}.xlsx` 的 `CC_vs_MI` 分頁 |

**缺失評估永遠跑**，因為「這份資料沒有缺失問題」本身就是需要證據的宣稱，不能靠印象。

這條由 `generate_configs.validate_plan()` 強制（2026-08-11 起）：pipeline 只要有任何**會配模型**的步驟（KM / competing-risk / uni / multi / PSM / AUC / RCS / robust / calibration / weighting / landmark），就必須有一個沒有 `outcome` 的 `missing-data` 步驟，否則 FATAL 退出。理由：那些步驟每一個都會丟掉不完整的列，丟了多少、跟結果有沒有關係，不是可選資訊。**`mi_{outcome}` 不算**——它是插補，不是評估。（此前這條只寫在 SKILL.md，手改的 plan 漏掉不會有任何警告。）

---

## 2. 何時需要 MI —— 決策規則

評估步驟依下表給出 verdict，**但不自動改變 pipeline**（照 Stage Reflector 的原則：只建議、不自動改）：

| 情況 | verdict | 建議 |
|---|---|---|
| 所有分析變項缺失 < 5%，且缺失與暴露／結果皆無關聯 | `complete_case_ok` | 用 complete-case，在論文寫明缺失比例 |
| 任一分析變項缺失 5–40% | `mi_recommended` | MI 為主分析、complete-case 為 sensitivity（或反過來，但要**事前指定**） |
| 任一分析變項缺失 > 40% | `mi_with_caution` | MI 仍可做，但該變項的插補值高度依賴模型假設。優先考慮**移除該變項**或改用有輔助資訊的來源；若保留，必須做「含 / 不含該變項」的 sensitivity |
| 缺失與**已觀測的結果**顯著相關 | `mcar_refuted` | MCAR 被推翻，但**這不等於 MNAR**——缺失取決於「觀測得到的資料」正是 MAR 的情形。complete-case 會有偏差；正確回應是讓 MAR 站得住：結果進插補模型（本流程有做）＋加入能同時預測缺失值與其缺失機率的輔助變項。**只有在有外部資訊指出缺失取決於「沒觀測到的值」時，才需要 MNAR 的 sensitivity（delta-adjustment / tipping point）**，本流程不產生它 |
| 結果變項本身缺失 | `outcome_missing` | 見 §6 |

**判定順序**（`missing_data.py`，先命中先決定）：`outcome_missing` → `mcar_refuted` → `mi_with_caution` → `mi_recommended` → `complete_case_ok`。與分組／追蹤時間的關聯只在前兩者**沒有**命中時才附加說明。

> **MAR 與 MNAR 都不能由資料檢定。** 能檢定的只有 MCAR。任何宣稱「資料顯示是 MNAR」的說法都站不住——把缺失指標對已觀測變項做檢定，只能拒絕 MCAR。（2026-08-11 審查修正：原本這一列叫 `mnar_risk` 並要求必做 MNAR sensitivity，是把 MAR 的情形誤升級了。）

> **> 50% 缺失不等於自動剔除該變項。** 只要 MAR 成立且有夠強的輔助變項，MI 仍可用（Madley-Dowd 2019）。要剔除是可以的，但那是一個要登記進決策紀錄的決定，不是自動化行為。

### 三個地方會對缺失率發話，門檻不一樣 —— 這是預期的

一個 42% 缺失的共變項會同時觸發下面兩三條，**不是重複、也不是矛盾**，它們問的是不同的問題：

| 出處 | 門檻 | 問的是 |
|---|---|---|
| `missing_data.py` 的 verdict（上表） | `low = 5` / `high = 40`，**協議定值、非使用者可調** | 「這份資料**該不該**做 MI」 |
| `precheck_configs.py` 的 **COL-005** | 20% / 40% / 60% 三級 | 「這個共變項的缺失**值不值得在跑之前先講一聲**」 |
| `precheck_configs.py` 的 **Stage Reflector** | 20% / 50% 兩級 | 「要不要**改計畫**（移除或插補）」 |

**三者都只是警告，沒有一個會擋。** 真正擋下來的只有 §6 的三種結構性失效。共變項可以帶 `allow_high_missing: true` 讓 COL-005 的高缺失警告閉嘴（**不影響** verdict 與 Reflector）。

> ⚠ **已知小瑕疵**：COL-005 那條訊息文字寫「（>50%）」，但實際條件是 `miss >= 0.60`。門檻本身偏保守（該叫的一定叫得到），但一個 55% 缺失的變項只會落到 40% 那一級，訊息卻讓人以為 50% 那條檢查過了。**判讀高缺失時以 Stage Reflector 的 50% 那條為準。**

---

## 3. 缺失評估要產出什麼

1. **每個分析變項的缺失 n / %**，並**依分組拆開**（兩組缺失率差很多本身就是訊號）
2. **缺失樣態**：完整個案數與比例、樣態是否 monotone、前 10 個最常見的樣態組合
3. **listwise 會損失多少**：如果照現行做法跑，N 從多少掉到多少、掉了幾 %——**這個數字要直接呈現給使用者**，因為它是「什麼都不做」的實際代價
4. **缺失機制的可檢驗部分**：每個有缺失的變項，建一個缺失指標（1 = 缺），檢定它與 ① 分組／暴露 ② 結果事件 ③ 追蹤時間 的關聯。任何一項顯著 → MCAR 不成立
5. **輔助變項候選**：與「有缺失的變項」相關、且與「該變項的缺失指標」相關的其他欄位。這些應該進插補模型即使它們不在分析模型裡
6. **verdict + 建議**（§2 的表）

---

## 4. 插補模型規格（硬性要求）

### 4.1 引擎

R `mice`（已驗證可用：mice 3.18.0、survival 3.8.3）。Python 端負責讀 config、套 filters、寫 Excel 與圖；R 端負責 MICE 與合併。R 不可用時 → `[QC_BLOCKING]`，**不可靜默退回 complete-case**。

呼叫時比照 Step 3.5 的 R driver 加 `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8`（非 ASCII 路徑在 macOS 上會壞）。

> **執行時間不是問題，不要為此犧牲 m。** runner 的 step timeout 是硬寫的 600 秒，看起來像個限制，實測不是。2026-08-11 於本機（mice 3.18.0）實測 `missing_data.py` **端到端**（含讀檔、MICE、合併、complete-case 對照、寫 Excel、畫圖）：
>
> | 分析後 N | 變項 | m | wall time |
> |---|---|---|---|
> | 292 | 5 + 2 aux | 20 | **15 秒** |
> | 2,911 | 5 + 2 aux | 20 | **44 秒** |
>
> 所以 §4.4 的 m 該多少就多少，**不要因為「怕跑太久」而退回 m=5**。真的撞到 600 秒，那代表變項數或資料量遠超典型臨床世代，該檢查的是插補模型是不是塞了不該塞的東西。

### 4.2 插補模型必須包含結果變項

這是最常被做錯的一點。**把結果排除在插補模型外，會把共變項與結果的關聯往 null 拉**（Moons 2006）。

| 結果型態 | 插補模型要放什麼 |
|---|---|
| **time-to-event** | 事件指標 `status` **與 `mice::nelsonaalen(data, time, status)` 算出的累積風險估計**。**不可以直接放原始存活時間**（White & Royston 2009） |
| **binary** | 結果變項本身 |

### 4.3 每個變項的插補方法

| 變項型態 | method | 理由 |
|---|---|---|
| continuous | `pmm`（predictive mean matching） | 保留原始分布與邊界，不會生出負數年齡或 0–1 之外的比例 |
| binary | `logreg` | |
| unordered categorical | `polyreg` | |
| ordered categorical | `polr` | |

不要對沒有缺失的變項指定 method（`mice` 會自動留空）。

### 4.4 m（插補次數）

`m = max(20, ceil(最大缺失百分比))`，上限 100。

**「最大缺失百分比」只算分析變項，不含輔助變項**（2026-08-11 起）。理由：White 2011 把 m 綁在**被估計的量**的 fraction of missing information 上；輔助變項進插補模型是為了借力，它自己的缺失率不會進入任何被報告的估計值。把輔助變項算進去只會讓一個觀測很差的輔助欄把 m 拉高、跑更久，不會讓估計更準。輔助變項的最大缺失率照樣印出來——那是判斷「這個輔助變項是不是稀疏到幫不上忙」的依據，只是不決定 m。

依據：m ≈ 缺失百分比可讓 Monte Carlo 誤差降到可忽略（White 2011）。下限 20 是因為 m=5 的老慣例在 FMI 高時會讓 p-value 不穩定。**m 與 seed 都要寫進輸出檔**，否則結果不可重現。

**上限 100 約束的是這條自動規則，不是分析者。** `mi_settings.m` 明確指定時照給的值跑（那是刻意的覆寫，不該被程式否決），但超過 100 會發 `[QC_WARNING]`——上限存在的理由是讓執行時間有界，而手動設定時沒有別的東西會提醒這件事。理由要進 `decision_log.md`。

### 4.5 收斂與分布診斷（必產，不可選）

- **收斂**：每個被插補變項的 chain mean / sd trace（`plot(imp)`）。看有沒有系統性趨勢或 chain 之間分離
- **分布**：observed vs imputed 的密度圖 / 長條圖。插補值分布跟觀測值差很多本身不是錯（MAR 下本來就可能不同），但**差到不合理**（超出生理範圍、類別比例翻轉）就是插補模型設定有問題
- 這兩張圖要一起輸出，並且在報告裡被實際看過——不是產完就丟

---

## 5. 合併與報告

- 用 `mice::pool()`（Rubin's rules，Barnard–Rubin 自由度）
- 每個係數報：**pooled estimate（HR / OR）、95% CI、p、df、FMI、RIV**
  - **FMI（fraction of missing information）要報出來**：它才是「缺失實際上讓你損失多少資訊」的量，跟缺失百分比不是同一件事
- **`CC_vs_MI` 對照分頁**：同一個模型的 complete-case 與 MI 結果並排，附 N（CC 的 N 與總 N）、效應量、CI、p，並標出：
  - 方向翻轉
  - 顯著性跨越 0.05
  - 效應量變動 > 20%

  這張表本身就是 reviewer 想看的 sensitivity analysis，不必另外做一個。

### 5.1 論文裡必須寫的（產物要能填滿這幾格）

1. 每個變項的缺失比例
2. 用了什麼方法、m 是多少、seed 是多少
3. **插補模型裡有哪些變項**（含輔助變項與結果）
4. MAR 假設的理由——為什麼在這個資料裡「缺失可由觀測到的變項解釋」是合理的
5. 軟體與版本（R x.y.z、mice x.y.z）
6. CC 與 MI 結果是否一致；不一致時怎麼解讀

---

## 6. 明確不支援的情況（要擋，不要假裝做得到）

| 情況 | 為什麼 | 該怎麼辦 |
|---|---|---|
| **結果變項本身缺失** | 把結果插補進來再當觀測值分析會虛增精確度 | 走 MI-then-delete（von Hippel 2007）：結果進插補模型幫忙插共變項，但分析時**排除結果缺失的個案**。目前實作**不自動做**，偵測到就 `[QC_BLOCKING]` 並說明 |
| **competing risk 的 MI** | 需要每個事件型態各自的 Nelson-Aalen，單一 `na_cumhaz` 不夠 | `[QC_BLOCKING]`，請使用者改用 cause-specific 單一終點或手動處理 |
| **群集 / 重複量測資料** | 需要 multilevel 插補（`2l.pmm` 等），忽略群集會低估變異 | `[QC_WARNING]` + 在 limitations 揭露；診斷若偵測到 clustering 則升級為 `[QC_BLOCKING]` |
| **MNAR 的 delta-adjustment** | 需要事前指定 delta 的範圍 | 不自動做；`mcar_refuted` verdict 時提示使用者這是缺的一塊（此 verdict 於 2026-08-11 由 `mnar_risk` 改名，理由見 §2） |
| **PSM 與 MI 併用** | 在插補內配對 vs 跨插補配對是未定論的方法學問題 | `[QC_WARNING]`：明講 PSM 步驟仍是 complete-case，兩者結果不可直接混談。**若 `primary_analysis: "mi"`**（2026-08-11 起）再加兩件事：`generate_configs` 記一條 `psm_complete_case_under_mi_primary` 進 `manifest.json$.methodological_warnings`，且 MI 所在的 outcome group 的 checkpoint 從 `FULL` 升為 `MANDATORY`——PSM 不是 MI 主分析的同 estimand sensitivity，這個對照必須有人看過才能簽收 |

---

## 7. 這一步不做的事

- **不自動把 MI 變成主分析**。主分析是 complete-case 還是 MI，是要事前指定並登記進 `decision_log.md` 的決策（帶永久 ID）。pipeline 兩個都算給你看，選哪個是人的責任。
- **不自動移除高缺失變項**。
- **不改寫其他 step 的 `missing_data_handling`**。KM、Table 1、PSM、AUC 維持原行為；MI 是**額外**的一條分析路線，不是替換。這一點要在報告裡講清楚，否則會出現「Table 1 的 N 跟回歸模型的 N 對不起來」而沒人解釋。

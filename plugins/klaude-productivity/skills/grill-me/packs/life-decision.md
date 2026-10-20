---
pack: life-decision
triggers: [接, 不接, 選, 要不要, 該不該, 買, 換, 申請, 合作, 轉職, 進修, 空檔期, 出國, 接 paper, 跳槽, 換 job, 做副業, 結婚, 搬家]
applicable_modes: [quick, deep]
default_callers: [使用者直接呼叫]
---

# Life Decision Facet Pack

對「接 / 不接 X」「選 A 還是 B」這類非 reversible 或半 reversible 個人決策。重點：強迫使用者面對 stakes、reversibility、機會成本、長短期視角。

---

## Facets（按重要性排序）

### F1: Stakes（賭注大小）

**Why it matters**: 重大決策值得花更多時間想

**Baseline questions**:
- 做錯這決定，最壞情況是什麼？（一句話）
- 影響時間長度：一週 / 一個月 / 一年 / 五年+ / 一輩子
- 影響範圍：只你 / 你 + 1 個人 / 你 + 家人 / 你 + 多人

**Follow-up triggers**:
- 答「一輩子」/「家人」 → 「這值得花一週多 grill 一次 / 找人聊聊，現在這 5 分鐘是不是太快下結論？」
- 答「一週」 → 「這個 stakes 要不要乾脆直接試試看？」
- 答 vague → 「具體想像一下：3 個月後做錯後悔的場景長什麼樣？」

---

### F2: Reversibility（能不能反悔）

**Why it matters**: 高 reversibility = 試試看；低 reversibility = 慢慢想

**Baseline questions**:
- 答應後反悔的成本：隨時可退無代價 / 半路退會破壞關係 / 一旦答應一定要做完 / 法律上不可逆
- 反悔需要付出什麼？（金錢 / 時間 / 人情 / 名聲 / 自我形象）
- 別人對你反悔的接受度？（高 / 低 / 不知道）

**Follow-up triggers**:
- 答「隨時可退」→ 「那答應它的成本很低，不是該直接試？」
- 答「破壞關係」 → 「跟這人關係的長期 value 多大？」
- 答「不知道」→ 「能直接問對方嗎？例：『如果中途要退我會...』」

---

### F3: Opportunity Cost（機會成本）

**Why it matters**: 答應 X 等於拒絕在這時段做 Y

**Baseline questions**:
- 接受後，你必須放棄什麼時間 / 機會？（具體列）
- 如果拒絕，這時段你會做什麼？（自己的專案 / 考試準備 / 休息 / 教學 / 別的合作）
- 那個 alternative 的 value 評估：高於 / 等於 / 低於這個 X

**Follow-up triggers**:
- 答「不知道會做什麼」 → 「那其實 opportunity cost 接近 0，可能該答應」
- 答「Alternative value 高於」 → 「為什麼還在猶豫？是不是有面子 / 義務 / 害怕拒絕的感受在干擾？」
- 答「休息」 → 「過去一個月實際休息夠嗎？如果不夠，休息本身就是高 value alternative」

---

### F4: Constraints（硬限制）

**Why it matters**: 有些 deal-breaker 一出現直接結束討論

**Baseline questions**:
- 時間限制：必須 yes/no by 何時？（具體日期）
- 預算限制：上限多少？
- 健康限制：影響睡眠 / 運動 / 生活品質可以接受到什麼程度？
- Deal-breaker：什麼條件出現就絕對不接？

**Follow-up triggers**:
- 答 deal-breaker 在現場 → 「那為什麼還在 grill？已經是 no 了」
- 答「沒時間限制」 → 「真的沒？還是你假設沒？建議去確認」
- 答「健康可以妥協」 → 「過去類似 trade-off 結果如何？」

---

### F5: Stakeholders（牽涉到誰）

**Why it matters**: 別人的視角你沒想到

**Baseline questions**:
- 這決定會影響誰？（除了你自己）
- 他們的偏好你問過嗎？（問過 / 沒問過 / 不需要問）
- 他們對這事的 stake 跟你一樣大嗎？

**Follow-up triggers**:
- 答「沒問過」+ 影響到家人 / 伴侶 → 「先 grill 完自己，去問問再回來？」
- 答「不需要問」 → 「真的不需要？還是你假設他們會 OK？」
- 答 stakeholder 偏好跟你不同 → 「衝突的部分怎麼處理？妥協 / 說服 / 各做各的？」

---

### F6: Long vs Short View（長短期視角）

**Why it matters**: 你 3 個月後 vs 3 年後的權衡可能不同

**Baseline questions**:
- 3 個月後你會怎麼看這決定？（後悔 / 慶幸 / 沒差）
- 3 年後呢？
- 哪個視角你比較信任？（短 / 長 / 一樣）

**Follow-up triggers**:
- 兩個視角答案不同 → 「衝突點是什麼？通常長期視角比較準，但要看你 priority」
- 答「3 個月慶幸 + 3 年後悔」 → 「典型 short-term win + long-term loss，停一下」
- 答「都不知道」 → 「找一個 5 年前做過類似決定的人聊聊？」

---

## 退讓 sentinel

- 若是醫學決策（要不要做某 procedure / 用什麼藥） → 走 `/medq` 或 `/oe` 查實證
- 若是 IRB / 研究 ethics 決策 → 走 `/irb-plan-helper`

---

## 適用範例

- 「要不要接學長的合作 paper」 → 全 6 facet
- 「換 Mac 還是 Win」 → F3 / F4 / F5（家人有沒有意見）
- 「要不要去美國 fellow」 → 6 facet 全部 + Deep mode（reversibility 低、stakes 高、stakeholders 多）
- 「下個合約要不要再續一年」 → F1 / F2 / F3 / F6

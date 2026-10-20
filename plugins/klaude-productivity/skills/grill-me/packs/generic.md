---
pack: generic
triggers: []  # fallback only
applicable_modes: [quick, deep]
default_callers: [偵測不到任何專屬 pack 時]
---

# Generic Facet Pack（fallback）

當 topic 不命中其他 4 個 pack 任何 trigger 時用這個。題目刻意保持通用，避免 false-positive。

---

## Facets

### F1: What

**Baseline questions**:
- 一句話描述這件事是什麼？
- 這事的 specific 部分（不是 abstract）：時間 / 地點 / 對象 / 數量

### F2: Why now

**Baseline questions**:
- 為什麼現在做（不是上週、不是下個月）？
- 如果不做會怎樣？

### F3: Who benefits

**Baseline questions**:
- 誰會受益？
- 誰會受害 / 被影響？

### F4: What could go wrong

**Baseline questions**:
- 最可能出錯的點是？
- 出錯的代價多大？
- 你的 fallback plan？

### F5: How would you know it worked

**Baseline questions**:
- 成功的具體 metric / signal？
- 多久後檢查？
- 失敗時的調整機制？

---

## Follow-up triggers（共用）

- 任何答案太 vague（< 5 字 / 全 abstract） → 「具體一點：你能舉一個例子嗎？」
- 任何「不知道」 → 「先擱置這 facet，等其他 facet 回答完再回來」
- 任何答案跟前面 facet 矛盾 → 直接 surface 矛盾請使用者澄清

---

## Pack 升級建議

如果在 generic 跑了一半，發現使用者其實在做 software / learning / life-decision / content → 主動建議切到 specific pack：

```
我聽起來你說的其實偏 <pack>，要不要切到 <pack> pack？問題會更精準。
```

使用者選 yes → 重啟 grill；選 no → 繼續用 generic。

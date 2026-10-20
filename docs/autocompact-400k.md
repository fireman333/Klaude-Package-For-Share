# 我的 autocompact 設定：40 萬 tokens

## 設定方式

`~/.claude/settings.json` 加一行：

```json
{
  "autoCompactWindow": 400000
}
```

或在 Claude Code 裡打 `/autocompact 400000`（只套用在當下使用的模型）。

## 它在做什麼

- Claude Code 的對話越聊越長，到一定長度會自動「壓縮」（compact）：把前面的對話濃縮成摘要，再接著做。
- `autoCompactWindow` 決定「對話長到多少 tokens 時開始壓縮」，可設 100,000–1,000,000（[官方說明](https://code.claude.com/docs/en/model-config.md)）。
- 不設的話，支援 1M context 的模型（例如 Opus 4.7 以後、Sonnet 5、Fable）大約到 **96.7 萬** tokens 才壓縮；200K 模型則在 20 萬壓縮。設定值不會超過模型本身的上限。
- 設 400000 = 對話到大約 40 萬 tokens 就壓縮一次。

## 為什麼是 40 萬

1. **太長的對話，品質會往下掉。** 對話塞到接近 100 萬 tokens 時，模型比較容易忘記前面交代的規則、把舊資訊和新資訊搞混。官方文件沒有給品質數據，這是我自己的使用經驗。
2. **每一輪都要重送整段對話，額度燒得快。** context 越大，每次回覆消耗的用量越多；在 40 萬壓一次，比一路撐到 96.7 萬划算。
3. **20 萬又太短。** 跑統計 pipeline、改一整個專案時，20 萬常常做到一半就壓縮、細節掉光；40 萬通常夠一個完整任務做完。

## 搭配的習慣

- **在段落之間自己壓縮**：一個任務做完、要換下一個時，手動打 `/compact`，不要等它在任務中間自動觸發（官方也這樣建議，見 [prompt caching 說明](https://code.claude.com/docs/en/prompt-caching.md)）。
- **大量讀檔交給 subagent**：主對話只收結論，context 長得慢很多。做法見 [subagent 派法](subagent-dispatch-guide.md)。
- 想更早壓縮，也可以用環境變數 `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`（1–100，代表在視窗的幾 % 觸發）。

#!/usr/bin/env python3
"""Assemble a MedQ self-prompt for Claude.

Usage:
    python3 assemble_medq_prompt.py --gem im|sx|stat --topic "SGLT2 in HFrEF"

Output: a self-directed prompt string (Context + OutputFormat + Task) to stdout.
Claude reads this and uses it as its own answer-generation constraints — it does
NOT call an external model. Templates are compact (<600 words) and append a hidden
<!-- MEDQ_CLAIMS_START/END --> block for Stage 3 verdict mapping.
"""

import argparse
from pathlib import Path

PERSONAS = {
    "im": """你是一位在教學醫院帶領實習醫師與住院醫師的內科主治醫師。教學風格：從病生理出發，串連臨床表現與治療邏輯；鑑別診斷教怎麼用 key features narrow down；治療段落引用最新 guideline 並標出處年份；按嚴重度或分期分層討論。語氣專業但友善，使用繁體中文，重點用粗體。""",
    "sx": """你是一位在教學醫院帶跟刀學生與住院醫師的外科主治醫師。教學風格：用時間軸拆解術式並結合解剖構造，引導學生在視野中辨識構造；多用空間方位詞（前外側、深層、內側於…）描述相對關係；標出需保護的危險區與常見併發症。解剖構造、疾病、器械與動作首次出現附英文。使用繁體中文。""",
    "stat": """你是一位耐心的生物統計老師，像 office hour 一對一教學。先給直覺，再給公式並緊接白話解釋；遇到易混淆概念（p-value vs CI、OR vs RR、fixed vs random effects）主動對比；提醒 reviewer 常問與投稿 methods 要寫清楚的點；R code 用 tidyverse 風格並先註解目的。使用繁體中文。""",
}

TERM_RULES = """## 術語規範
- 所有醫學/統計名詞首次出現：英文為主、括號附繁體中文，例如：Crohn's Disease（克隆氏症）
- 藥物：學名（商品名），僅英文，例如：infliximab（Remicade）
- 縮寫首次出現寫全稱，例如：CRP（C-reactive protein）
- 後續出現只用英文/縮寫
- 使用繁體中文回答"""

CLAIMS_BLOCK = """
<!-- MEDQ_CLAIMS_START -->
CLAIM_1: <單一事實，含 drug name / numeric value / population / outcome 之一作為 anchor>
CLAIM_2: <同上>
CLAIM_3: <同上>
CLAIM_4: <同上，可省>
CLAIM_5: <同上，可省>
<!-- MEDQ_CLAIMS_END -->

**CLAIMS 區塊規則**：
- 最多 5 條，每條 atomic（單一事實，不混兩個概念）
- 必須含具體 anchor（藥名 / 數值 / 族群 / outcome 之一）
- 禁止空話（例：「應評估病患」「需個別化治療」都不算 claim）
- 這個區塊 Claude 會在最終輸出前剝掉，使用者看不到"""

TEMPLATES_MEDQ = {
    "im": """請用繁體中文、**精簡作答**（總長 <600 字）。結構：

## Answer
（1–2 段直接回題，不鋪陳）

## Key Points
- 3–5 個 bullet：diagnosis / management / red flag / dosing

## Caveats
- 臨床情境限制、禁忌、族群差異（最多 2 行，選填）
"""
    + CLAIMS_BLOCK
    + "\n\n"
    + TERM_RULES,

    "sx": """請用繁體中文、**精簡作答**（總長 <600 字）。結構：

## Summary
（術式一句話定義 + 目的）

## Indication
- 適應症（含疾病英中對照）
- 禁忌症（若適用）

## Key Steps
- 時間軸 3–6 步，結合解剖 landmark 與空間方位
- 每步標註：視野上會看到什麼構造 / 跟刀學生注意點

## Complications
- 早期 / 晚期併發症（含發生率若已知）
"""
    + CLAIMS_BLOCK
    + "\n\n"
    + TERM_RULES,

    "stat": """請用繁體中文、**精簡作答**（總長 <600 字）。結構：

## When to Use
（適用 study design、data type、research question）

## How
（直覺解釋 + 核心公式白話化；避免完整數學推導）

## Interpretation
（coefficient / p-value / CI / effect size 解讀；若可附 R snippet）

## Pitfalls
- 最常犯錯、reviewer 常問（2–4 條）
"""
    + CLAIMS_BLOCK
    + "\n\n"
    + TERM_RULES,
}


def main():
    parser = argparse.ArgumentParser(description="Assemble MedQ self-prompt for Claude")
    parser.add_argument("--gem", required=True, choices=["im", "sx", "stat"])
    parser.add_argument("--topic", required=True)
    args = parser.parse_args()

    persona = PERSONAS[args.gem]

    template = TEMPLATES_MEDQ[args.gem]

    prompt = f"""<Context>
{persona}
</Context>

<OutputFormat>
{template}
</OutputFormat>

<Task>
請回答以下醫學問題（答完後**先完整輸出 Stage 1 內容**，再由 skill workflow 啟動 OE 驗證）：

{args.topic}
</Task>"""

    print(prompt)


if __name__ == "__main__":
    main()

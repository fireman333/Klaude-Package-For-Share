---
name: Journal Classic
description: NEJM / Lancet 風 — 白底、navy 主、crimson 重點、Georgia serif 通透；journal-club 預設 academic 視覺
---

# Journal Classic

正統醫學期刊風格，源自 NEJM / Lancet 排版基因 — 白底大留白、navy 為主色、crimson 用在 key data / call-out、Georgia serif 從標題到內文一致。氣質保守但 timeless，適合「給師長 / 期刊式書面 presentation」場合。

## Palette

| Role         | Value     | Notes                              |
| ------------ | --------- | ---------------------------------- |
| bg           | `#FFFFFF` | 整片白，純期刊紙感                  |
| text         | `#1A1A1A` | 正文 near-black（不全黑減少對比刺眼） |
| textSoft     | `#5B5B5B` | metadata / caption / 次要說明        |
| accent       | `#A51C30` | crimson — 重點 stat / call-out      |
| primary      | `#1E3A5F` | navy — 章節標題 / banner bar         |
| cardBg       | `#F8F8F8` | 內框 panel 底                       |
| rule         | `#CCCCCC` | 分隔線 / 邊框                       |
| watermark    | `#ECECEC` | 章節分頁的大字浮水印                 |

## Typography

- Display font: `Georgia, "Source Serif Pro", "Times New Roman", serif` — 期刊報頭 vibe，weight 600–700。
- Body font: `Georgia, "Source Serif Pro", "Times New Roman", serif` — 內文也 serif，保持期刊一致性。
- Mono font: `"JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace` — citation key / DOI 用。
- Type-scale overrides:
  - Hero title: 132 px（cover）
  - Section title: 88 px
  - Heading: 56 px
  - Body: 32 px
  - Caption / footer: 22 px

## Layout

- Content padding: 120 px from canvas edges（1920×1080）。
- 章節 banner bar: 頂端 navy fill 12 px，左 124 px 起 white text。
- Alignment: left-aligned 主軸；數字 / take-home 句可置中。
- 內框 cardBg #F8F8F8 + rule #CCCCCC 1px border，圓角 0（直角期刊感）。

## Fixed components

### Title

```tsx
const Title = ({ children }: { children: React.ReactNode }) => (
  <h1
    style={{
      fontFamily: 'Georgia, "Source Serif Pro", "Times New Roman", serif',
      fontSize: 132,
      fontWeight: 700,
      lineHeight: 1.05,
      letterSpacing: '-0.015em',
      margin: 0,
      color: '#1A1A1A',
    }}
  >
    {children}
  </h1>
);
```

### Footer

Pull the page number from `useSlidePageNumber()` — never hardcode `pageNum` / `total`.

```tsx
import { useSlidePageNumber } from '@open-slide/core';

const Footer = () => {
  const { current, total } = useSlidePageNumber();
  return (
    <div
      style={{
        position: 'absolute',
        left: 120,
        right: 120,
        bottom: 60,
        display: 'flex',
        justifyContent: 'space-between',
        fontFamily: 'Georgia, "Source Serif Pro", "Times New Roman", serif',
        fontSize: 22,
        color: '#5B5B5B',
        letterSpacing: '0.04em',
      }}
    >
      <span style={{ fontVariant: 'small-caps' }}>Journal Club</span>
      <span>{current} / {total}</span>
    </div>
  );
};
```

### Eyebrow

```tsx
const Eyebrow = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      fontFamily: 'Georgia, "Source Serif Pro", "Times New Roman", serif',
      fontSize: 24,
      letterSpacing: '0.22em',
      textTransform: 'uppercase',
      color: '#A51C30',
      fontWeight: 600,
    }}
  >
    {children}
  </div>
);
```

### Section Banner

章節 divider 用 navy banner bar：

```tsx
const SectionBanner = ({ label, number }: { label: string; number: string }) => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      right: 0,
      top: 360,
      padding: '32px 120px',
      background: '#1E3A5F',
      color: '#FFFFFF',
      display: 'flex',
      alignItems: 'baseline',
      gap: 36,
    }}
  >
    <span style={{ fontSize: 36, letterSpacing: '0.1em', opacity: 0.7 }}>{number}</span>
    <span style={{ fontSize: 72, fontFamily: 'Georgia, serif', fontWeight: 600 }}>{label}</span>
  </div>
);
```

## Motion

- Philosophy: **subtle** — 期刊風保守，僅入場 fade-up。避免高 motion 干擾學術氣質。
- Reusable keyframe:

```css
@keyframes jc-fadeUp {
  from { opacity: 0; transform: translateY(18px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

Results figure walkthrough 可選擇性加 data-point highlight blink（持續 1.2s 後停）— 用在強調 key statistic 那張。

## Aesthetic

NEJM / Lancet 雙刊報頭 DNA：白底 + navy 主視覺 + crimson 點睛 + Georgia 全 serif。**禁忌**：圓角 > 4 px、漸層底、emoji 裝飾、霓虹色、漫畫字。給聽者「這是一份正式的書報討論」的氣質，不是 startup pitch。Cover 上 paper title + author + journal + year 三行就夠，不要 hero 圖。

## Example usage

```tsx
const Cover: Page = () => (
  <div style={{ width: '100%', height: '100%', background: '#FFFFFF', color: '#1A1A1A', padding: 120, display: 'flex', flexDirection: 'column', justifyContent: 'center', position: 'relative' }}>
    <Eyebrow>JOURNAL CLUB · 2026</Eyebrow>
    <Title>Effect of Empagliflozin in Patients with Heart Failure</Title>
    <p style={{ fontFamily: 'Georgia, serif', fontSize: 36, color: '#5B5B5B', maxWidth: 1500, marginTop: 32, lineHeight: 1.4 }}>
      Anker SD, Butler J, Filippatos G, et al. <em>N Engl J Med</em>. 2021;385(16):1451-1461.
    </p>
    <Footer />
  </div>
);
```

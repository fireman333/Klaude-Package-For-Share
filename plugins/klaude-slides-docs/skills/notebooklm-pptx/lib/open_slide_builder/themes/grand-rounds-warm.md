---
name: Grand Rounds Warm
description: Harvard / Notion editorial 風 — 紙質米色底、rust 紅 + 銅色配、深棕字 + Georgia 標題 + Calibri 內文；溫暖博雅
---

# Grand Rounds Warm

Harvard 醫學院 grand rounds 拼貼 + Notion editorial 排版 = 紙質米色底、深棕字、rust red + 銅色雙 accent、Georgia 標題 + Calibri 內文。氣質是「資深主治拿著紙本 case 講的早晨 conference」— 溫暖、學術、講求論述大於資料密度。適合醫學人文 / 教育性 case 報告 / journal 主題偏 narrative review 的場合。

## Palette

| Role         | Value     | Notes                                  |
| ------------ | --------- | -------------------------------------- |
| bg           | `#F5F1EA` | 紙感米底，比純白溫暖                    |
| text         | `#2B2318` | 深棕褐字，比純黑柔                      |
| textSoft     | `#6E5B43` | 銅褐 caption / metadata                 |
| accent       | `#8B1A1A` | rust red — call-out / 重點 stat         |
| accent2      | `#B87333` | 銅色 — eyebrow / 次要 highlight        |
| cardBg       | `#FCFAF5` | 內框 paper card                         |
| rule         | `#D9C8A9` | 紙邊棕條分隔線                          |
| watermark    | `#E8DFC8` | 章節數字浮水印                          |

## Typography

- Display font: `Georgia, "Source Serif Pro", "Times New Roman", serif` — Harvard editorial 標題感，weight 600。
- Body font: `"Calibri", "Open Sans", "Inter", system-ui, sans-serif` — 內文 sans 提升可讀性，避開「教科書字海」。
- Mono font: `"JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace`。
- Type-scale overrides:
  - Hero title: 144 px（cover 用 Georgia serif 顯眼）
  - Section title: 84 px
  - Heading: 56 px
  - Body: 32 px
  - Caption: 22 px

## Layout

- Content padding: 120 px from canvas edges。
- 章節 divider: 大字浮水印「01」「02」#E8DFC8 1px 邊外延伸到 canvas 邊。
- Alignment: 左對齊主軸；title slide 可置中；body 文字段落最大 1500 px width。
- 內框 cardBg + 1px D9C8A9 邊框 + radius 4px（微圓角呼應 paper 質感）。

## Fixed components

### Title

```tsx
const Title = ({ children }: { children: React.ReactNode }) => (
  <h1
    style={{
      fontFamily: 'Georgia, "Source Serif Pro", "Times New Roman", serif',
      fontSize: 144,
      fontWeight: 600,
      lineHeight: 1.05,
      letterSpacing: '-0.02em',
      margin: 0,
      color: '#2B2318',
    }}
  >
    {children}
  </h1>
);
```

### Footer

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
        fontFamily: '"Calibri", "Open Sans", system-ui, sans-serif',
        fontSize: 22,
        color: '#6E5B43',
        letterSpacing: '0.03em',
      }}
    >
      <span style={{ fontVariant: 'small-caps' }}>Grand Rounds</span>
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
      fontFamily: '"Calibri", "Open Sans", system-ui, sans-serif',
      fontSize: 24,
      letterSpacing: '0.22em',
      textTransform: 'uppercase',
      color: '#B87333',
      fontWeight: 600,
    }}
  >
    {children}
  </div>
);
```

### Watermark Number（section divider 用）

```tsx
const SectionNumber = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      position: 'absolute',
      right: 80,
      top: 80,
      fontFamily: 'Georgia, serif',
      fontSize: 360,
      fontWeight: 700,
      color: '#E8DFC8',
      lineHeight: 1,
      pointerEvents: 'none',
    }}
  >
    {children}
  </div>
);
```

## Motion

- Philosophy: **subtle** — 紙質溫暖風不需要 flashy；僅 fade-up 入場 + 偶爾 watermark 字慢慢浮現。
- Reusable keyframes:

```css
@keyframes gr-fadeUp {
  from { opacity: 0; transform: translateY(20px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes gr-watermarkIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}
```

## Aesthetic

Harvard / Notion editorial — 紙質米底 + Georgia 標題 + 棕褐字 + 銅 / rust 配色。**禁忌**：純白底、霓虹色、無 serif 標題、emoji 裝飾、漸層底。氣質「resident 翻開 paper 跟 attending 報告」— 溫暖、文人感、講求論述完整大於資料堆疊。Cover 上常用大 Georgia serif title + small-caps subtitle。

## Example usage

```tsx
const Cover: Page = () => (
  <div style={{ width: '100%', height: '100%', background: '#F5F1EA', color: '#2B2318', padding: 120, display: 'flex', flexDirection: 'column', justifyContent: 'center', position: 'relative' }}>
    <Eyebrow>Grand Rounds · Cardiology</Eyebrow>
    <Title>A 67-Year-Old Man with Recurrent Heart Failure</Title>
    <p style={{ fontFamily: '"Calibri", system-ui, sans-serif', fontSize: 36, color: '#6E5B43', maxWidth: 1500, marginTop: 32, lineHeight: 1.45 }}>
      Yang J, Smith R. <em>The New England Journal of Medicine</em> · 2025.
    </p>
    <Footer />
  </div>
);
```

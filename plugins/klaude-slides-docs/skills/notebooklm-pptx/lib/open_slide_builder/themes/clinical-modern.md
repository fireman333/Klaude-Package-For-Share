---
name: Clinical Modern
description: JAMA / Stripe 風 — light gray 底、teal-dark 主、coral accent、Calibri sans-serif；現代醫學期刊 minimal aesthetic
---

# Clinical Modern

JAMA Network + Stripe documentation 雙重 DNA — light gray 底、teal-dark 主色、coral 紅當 accent、Calibri / Open Sans 全程 sans-serif。氣質「新版 JAMA viewpoint + Stripe API doc」— minimal、現代、強調資訊密度。適合 evidence-based update / RCT 報告 / 偏向 data-forward 的書報討論。

> **Palette divergence from pptx**: pptx themes.py 把 primary 跟 accent 都設成 #0E5E6F（teal）造成「accent 文字在 primary 底上隱形」的 bug。Open-slide 版本拆開：primary = teal-dark、accent = coral red、避免該失敗模式。

## Palette

| Role         | Value     | Notes                                  |
| ------------ | --------- | -------------------------------------- |
| bg           | `#FAFAFA` | 微灰底，比純白 modern                   |
| text         | `#1A1A1A` | 正文 near-black                         |
| textSoft     | `#595959` | 中灰 — caption / metadata               |
| accent       | `#C0392B` | coral red — call-out / 重點 stat        |
| primary      | `#0E5E6F` | teal-dark — section header / chart axis |
| primarySoft  | `#4A8C99` | teal lighter — hover / secondary fill   |
| cardBg       | `#FFFFFF` | 內框純白                                |
| rule         | `#E5E5E5` | 細灰分隔                                |
| watermark    | `#EEEEEE` | 章節數字浮水印                          |

## Typography

- Display font: `"Calibri", "Open Sans", "Inter", system-ui, sans-serif` — sans 標題，weight 600。
- Body font: `"Calibri", "Open Sans", "Inter", system-ui, sans-serif` — 全 sans 一致。
- Mono font: `"JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace` — 統計值 / DOI / trial code 用 mono。
- Type-scale overrides:
  - Hero title: 128 px
  - Section title: 84 px
  - Heading: 52 px
  - Body: 30 px
  - Caption: 20 px

## Layout

- Content padding: 96 px from canvas edges（比 jc serif 風格稍緊湊，提升資訊密度）。
- 章節 banner: 細 teal 直線 left edge 8 px + 章節 label。
- Alignment: 左對齊；data card 可置中。
- 內框 cardBg + rule 1px + radius 8px（現代 web app 風的微圓角）。
- Chart-friendly：留 plot area 至少 1100×620 px 給 results figure walkthrough。

## Fixed components

### Title

```tsx
const Title = ({ children }: { children: React.ReactNode }) => (
  <h1
    style={{
      fontFamily: '"Calibri", "Open Sans", "Inter", system-ui, sans-serif',
      fontSize: 128,
      fontWeight: 600,
      lineHeight: 1.05,
      letterSpacing: '-0.025em',
      margin: 0,
      color: '#1A1A1A',
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
        left: 96,
        right: 96,
        bottom: 48,
        display: 'flex',
        justifyContent: 'space-between',
        fontFamily: '"Calibri", "Open Sans", system-ui, sans-serif',
        fontSize: 20,
        color: '#595959',
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
      }}
    >
      <span>Clinical Update · 2026</span>
      <span style={{ fontFamily: '"JetBrains Mono", monospace', letterSpacing: '0.04em' }}>
        {String(current).padStart(2, '0')} / {String(total).padStart(2, '0')}
      </span>
    </div>
  );
};
```

### Eyebrow

```tsx
const Eyebrow = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      fontFamily: '"JetBrains Mono", monospace',
      fontSize: 22,
      letterSpacing: '0.15em',
      textTransform: 'uppercase',
      color: '#0E5E6F',
      fontWeight: 500,
    }}
  >
    {children}
  </div>
);
```

### Stat Card

JAMA-style 大數字 + 註解：

```tsx
const StatCard = ({ value, label, ci }: { value: string; label: string; ci?: string }) => (
  <div
    style={{
      background: '#FFFFFF',
      border: '1px solid #E5E5E5',
      borderLeft: '4px solid #0E5E6F',
      borderRadius: 8,
      padding: '32px 40px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}
  >
    <div style={{ fontSize: 72, fontWeight: 700, color: '#C0392B', lineHeight: 1, fontFamily: '"Calibri", system-ui, sans-serif' }}>
      {value}
    </div>
    <div style={{ fontSize: 24, color: '#1A1A1A', fontWeight: 500 }}>{label}</div>
    {ci && (
      <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 18, color: '#595959' }}>
        {ci}
      </div>
    )}
  </div>
);
```

## Motion

- Philosophy: **subtle to rich** — modern web app 允許更多 motion。Cover fade-up + results figure 用 data-point highlight blink + curve draw-in。
- Reusable keyframes:

```css
@keyframes cm-fadeUp {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes cm-statPulse {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(1.04); }
}
@keyframes cm-drawIn {
  from { stroke-dashoffset: 1000; }
  to   { stroke-dashoffset: 0; }
}
```

## Aesthetic

JAMA Network viewpoint 排版 + Stripe documentation 視覺 = light gray + teal-dark + coral 點睛 + sans-serif minimal。**禁忌**：serif 標題、漸層底、紙質紋理、超過 4 個 callout 色、emoji 裝飾、暗黑底（除非作為對比 hero slide）。氣質是「資料量大但讀起來爽」— 高 information density + 清晰 hierarchy。Cover 上 paper title 可以加 mono 字 trial code（例 `NCT04503616`）增加 technical feel。

## Example usage

```tsx
const Cover: Page = () => (
  <div style={{ width: '100%', height: '100%', background: '#FAFAFA', color: '#1A1A1A', padding: 96, display: 'flex', flexDirection: 'column', justifyContent: 'center', position: 'relative' }}>
    <Eyebrow>Clinical Update · 2026 · RCT</Eyebrow>
    <Title>Dapagliflozin in Patients with Heart Failure and Mildly Reduced or Preserved Ejection Fraction</Title>
    <p style={{ fontFamily: '"Calibri", system-ui, sans-serif', fontSize: 32, color: '#595959', maxWidth: 1500, marginTop: 24, lineHeight: 1.45 }}>
      DELIVER trial · <span style={{ fontFamily: '"JetBrains Mono", monospace', color: '#0E5E6F' }}>NCT03619213</span> · <em>N Engl J Med</em> 2022;387:1089-1098.
    </p>
    <Footer />
  </div>
);
```

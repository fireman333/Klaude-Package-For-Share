import { type Page, useSlidePageNumber, type DesignSystem } from '@open-slide/core';

export const design: DesignSystem = {
  palette: {
    bg: '#F5F1EA',
    text: '#2B2318',
    accent: '#8B1A1A',
  },
  fonts: {
    display: 'Georgia, "Source Serif Pro", "Times New Roman", serif',
    body: '"Calibri", "Open Sans", "Inter", system-ui, sans-serif',
  },
  typeScale: {
    hero: 144,
    body: 32,
  },
  radius: 4,
};

const palette = {
  bg: '#F5F1EA',
  text: '#2B2318',
  textSoft: '#6E5B43',
  accent: '#8B1A1A',
  accent2: '#B87333',
  cardBg: '#FCFAF5',
  rule: '#D9C8A9',
  watermark: '#E8DFC8',
};

const fontDisplay = 'Georgia, "Source Serif Pro", "Times New Roman", serif';
const fontBody = '"Calibri", "Open Sans", "Inter", system-ui, sans-serif';

const Title = ({ children }: { children: React.ReactNode }) => (
  <h1
    style={{
      fontFamily: fontDisplay,
      fontSize: 144,
      fontWeight: 600,
      lineHeight: 1.05,
      letterSpacing: '-0.02em',
      margin: 0,
      color: palette.text,
    }}
  >
    {children}
  </h1>
);

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
        fontFamily: fontBody,
        fontSize: 22,
        color: palette.textSoft,
        letterSpacing: '0.03em',
      }}
    >
      <span style={{ fontVariant: 'small-caps' }}>Grand Rounds</span>
      <span>
        {current} / {total}
      </span>
    </div>
  );
};

const Eyebrow = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      fontFamily: fontBody,
      fontSize: 24,
      letterSpacing: '0.22em',
      textTransform: 'uppercase',
      color: palette.accent2,
      fontWeight: 600,
    }}
  >
    {children}
  </div>
);

const SectionNumber = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      position: 'absolute',
      right: 80,
      top: 80,
      fontFamily: fontDisplay,
      fontSize: 360,
      fontWeight: 700,
      color: palette.watermark,
      lineHeight: 1,
      pointerEvents: 'none',
    }}
  >
    {children}
  </div>
);

const styles = `
  @keyframes gr-fadeUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes gr-watermarkIn {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  .gr-fadeUp { opacity: 0; animation: gr-fadeUp 0.75s cubic-bezier(.2,.7,.2,1) forwards; }
  .gr-watermarkIn { opacity: 0; animation: gr-watermarkIn 1.4s ease forwards; }
`;

const fill: React.CSSProperties = {
  width: '100%',
  height: '100%',
  background: palette.bg,
  color: palette.text,
  fontFamily: fontBody,
  position: 'relative',
  overflow: 'hidden',
};

const Cover: Page = () => (
  <div style={fill}>
    <style>{styles}</style>
    <div
      style={{
        position: 'absolute',
        inset: 0,
        padding: 120,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
      }}
    >
      <div className="gr-fadeUp" style={{ animationDelay: '0.05s' }}>
        <Eyebrow>Grand Rounds · Cardiology</Eyebrow>
      </div>
      <div className="gr-fadeUp" style={{ animationDelay: '0.2s', marginTop: 24 }}>
        <Title>A 67-Year-Old Man with Recurrent Heart Failure</Title>
      </div>
      <p
        className="gr-fadeUp"
        style={{
          animationDelay: '0.4s',
          fontFamily: fontBody,
          fontSize: 36,
          color: palette.textSoft,
          maxWidth: 1500,
          marginTop: 32,
          lineHeight: 1.45,
        }}
      >
        Yang J, Smith R. <em>The New England Journal of Medicine</em> · 2025.
      </p>
    </div>
    <Footer />
  </div>
);

const Content: Page = () => (
  <div style={fill}>
    <style>{styles}</style>
    <SectionNumber>02</SectionNumber>
    <div
      style={{
        position: 'absolute',
        inset: 0,
        padding: 120,
        display: 'flex',
        flexDirection: 'column',
        gap: 36,
      }}
    >
      <div className="gr-fadeUp" style={{ animationDelay: '0.05s' }}>
        <Eyebrow>Background</Eyebrow>
        <h2
          style={{
            fontFamily: fontDisplay,
            fontSize: 84,
            fontWeight: 600,
            margin: '20px 0 0',
            color: palette.text,
            letterSpacing: '-0.015em',
            lineHeight: 1.1,
          }}
        >
          HFpEF: an evolving therapeutic landscape.
        </h2>
      </div>
      <div
        className="gr-fadeUp"
        style={{
          animationDelay: '0.25s',
          background: palette.cardBg,
          border: `1px solid ${palette.rule}`,
          borderRadius: 4,
          padding: '40px 48px',
          fontFamily: fontBody,
          fontSize: 30,
          lineHeight: 1.6,
          color: palette.text,
          maxWidth: 1500,
        }}
      >
        Until 2020, no pharmacologic therapy had demonstrated mortality benefit in HFpEF. The advent
        of <span style={{ color: palette.accent, fontWeight: 600 }}>SGLT2 inhibitors</span> changed
        the landscape — first with empagliflozin in EMPEROR-Preserved, later with dapagliflozin in
        DELIVER. Together they reframed our approach to a syndrome long considered intractable.
      </div>
    </div>
    <Footer />
  </div>
);

const Closer: Page = () => (
  <div style={fill}>
    <style>{styles}</style>
    <div
      style={{
        position: 'absolute',
        inset: 0,
        padding: 120,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
      }}
    >
      <div className="gr-fadeUp" style={{ animationDelay: '0.05s' }}>
        <Eyebrow>Take-home</Eyebrow>
      </div>
      <h2
        className="gr-fadeUp"
        style={{
          animationDelay: '0.25s',
          fontFamily: fontDisplay,
          fontSize: 96,
          fontWeight: 600,
          letterSpacing: '-0.02em',
          lineHeight: 1.1,
          margin: '24px 0 32px',
          color: palette.text,
          maxWidth: 1500,
        }}
      >
        Empagliflozin reduces the composite of CV death or HF hospitalization in HFpEF.
      </h2>
      <p
        className="gr-fadeUp"
        style={{
          animationDelay: '0.45s',
          fontFamily: fontBody,
          fontSize: 36,
          color: palette.textSoft,
          maxWidth: 1500,
          lineHeight: 1.5,
        }}
      >
        Hazard ratio <span style={{ color: palette.accent, fontWeight: 700 }}>0.79</span> (95% CI,
        0.69 – 0.90; P&lt;0.001) — a clinically meaningful reduction across the EF spectrum.
      </p>
    </div>
    <Footer />
  </div>
);

export default [Cover, Content, Closer] satisfies Page[];

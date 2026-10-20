import { type Page, useSlidePageNumber, type DesignSystem } from '@open-slide/core';

export const design: DesignSystem = {
  palette: {
    bg: '#FFFFFF',
    text: '#1A1A1A',
    accent: '#A51C30',
  },
  fonts: {
    display: 'Georgia, "Source Serif Pro", "Times New Roman", serif',
    body: 'Georgia, "Source Serif Pro", "Times New Roman", serif',
  },
  typeScale: {
    hero: 132,
    body: 32,
  },
  radius: 0,
};

const palette = {
  bg: '#FFFFFF',
  text: '#1A1A1A',
  textSoft: '#5B5B5B',
  accent: '#A51C30',
  primary: '#1E3A5F',
  cardBg: '#F8F8F8',
  rule: '#CCCCCC',
  watermark: '#ECECEC',
};

const fontStack = 'Georgia, "Source Serif Pro", "Times New Roman", serif';

const Title = ({ children }: { children: React.ReactNode }) => (
  <h1
    style={{
      fontFamily: fontStack,
      fontSize: 132,
      fontWeight: 700,
      lineHeight: 1.05,
      letterSpacing: '-0.015em',
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
        fontFamily: fontStack,
        fontSize: 22,
        color: palette.textSoft,
        letterSpacing: '0.04em',
      }}
    >
      <span style={{ fontVariant: 'small-caps' }}>Journal Club</span>
      <span>
        {current} / {total}
      </span>
    </div>
  );
};

const Eyebrow = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      fontFamily: fontStack,
      fontSize: 24,
      letterSpacing: '0.22em',
      textTransform: 'uppercase',
      color: palette.accent,
      fontWeight: 600,
    }}
  >
    {children}
  </div>
);

const styles = `
  @keyframes jc-fadeUp {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .jc-fadeUp { opacity: 0; animation: jc-fadeUp 0.7s cubic-bezier(.2,.7,.2,1) forwards; }
`;

const fill: React.CSSProperties = {
  width: '100%',
  height: '100%',
  background: palette.bg,
  color: palette.text,
  fontFamily: fontStack,
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
      <div className="jc-fadeUp" style={{ animationDelay: '0.05s' }}>
        <Eyebrow>Journal Club · 2026</Eyebrow>
      </div>
      <div className="jc-fadeUp" style={{ animationDelay: '0.2s', marginTop: 24 }}>
        <Title>Effect of Empagliflozin in Patients with Heart Failure</Title>
      </div>
      <p
        className="jc-fadeUp"
        style={{
          animationDelay: '0.4s',
          fontFamily: fontStack,
          fontSize: 36,
          color: palette.textSoft,
          maxWidth: 1500,
          marginTop: 32,
          lineHeight: 1.4,
        }}
      >
        Anker SD, Butler J, Filippatos G, et al. <em>N Engl J Med</em>. 2021;385(16):1451-1461.
      </p>
    </div>
    <Footer />
  </div>
);

const Content: Page = () => (
  <div style={fill}>
    <style>{styles}</style>
    <div
      style={{
        position: 'absolute',
        inset: 0,
        padding: 120,
        display: 'flex',
        flexDirection: 'column',
        gap: 48,
      }}
    >
      <div className="jc-fadeUp" style={{ animationDelay: '0.05s' }}>
        <Eyebrow>03 · Methods</Eyebrow>
        <h2
          style={{
            fontFamily: fontStack,
            fontSize: 88,
            fontWeight: 600,
            margin: '20px 0 0',
            color: palette.text,
            letterSpacing: '-0.01em',
          }}
        >
          Randomized, double-blind trial design.
        </h2>
      </div>
      <div
        className="jc-fadeUp"
        style={{
          animationDelay: '0.25s',
          background: palette.cardBg,
          border: `1px solid ${palette.rule}`,
          padding: '40px 48px',
          fontSize: 32,
          lineHeight: 1.6,
          color: palette.text,
          flex: 1,
        }}
      >
        <ul style={{ margin: 0, paddingLeft: 28 }}>
          <li>
            <strong>Population:</strong> 5,988 patients with HFpEF (EF &gt; 40%).
          </li>
          <li>
            <strong>Intervention:</strong> Empagliflozin 10 mg vs. placebo, daily.
          </li>
          <li>
            <strong>Primary outcome:</strong> Composite of CV death or HF hospitalization.
          </li>
          <li>
            Median follow-up <span style={{ color: palette.accent, fontWeight: 600 }}>26.2 months</span>.
          </li>
        </ul>
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
        padding: '120px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
      }}
    >
      <div className="jc-fadeUp" style={{ animationDelay: '0.05s' }}>
        <Eyebrow>Take-home</Eyebrow>
      </div>
      <h2
        className="jc-fadeUp"
        style={{
          animationDelay: '0.25s',
          fontFamily: fontStack,
          fontSize: 96,
          fontWeight: 600,
          letterSpacing: '-0.015em',
          lineHeight: 1.1,
          margin: '24px 0 32px',
          color: palette.text,
        }}
      >
        Empagliflozin reduces CV death or HF hospitalization in HFpEF.
      </h2>
      <p
        className="jc-fadeUp"
        style={{
          animationDelay: '0.45s',
          fontFamily: fontStack,
          fontSize: 36,
          color: palette.textSoft,
          maxWidth: 1500,
          lineHeight: 1.5,
        }}
      >
        Hazard ratio <span style={{ color: palette.accent, fontWeight: 700 }}>0.79</span> (95% CI, 0.69 – 0.90; P&lt;0.001).
      </p>
    </div>
    <Footer />
  </div>
);

export default [Cover, Content, Closer] satisfies Page[];

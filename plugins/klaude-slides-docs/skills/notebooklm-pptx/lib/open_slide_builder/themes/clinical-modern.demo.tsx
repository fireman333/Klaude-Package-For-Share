import { type Page, useSlidePageNumber, type DesignSystem } from '@open-slide/core';

export const design: DesignSystem = {
  palette: {
    bg: '#FAFAFA',
    text: '#1A1A1A',
    accent: '#C0392B',
  },
  fonts: {
    display: '"Calibri", "Open Sans", "Inter", system-ui, sans-serif',
    body: '"Calibri", "Open Sans", "Inter", system-ui, sans-serif',
  },
  typeScale: {
    hero: 128,
    body: 30,
  },
  radius: 8,
};

const palette = {
  bg: '#FAFAFA',
  text: '#1A1A1A',
  textSoft: '#595959',
  accent: '#C0392B',
  primary: '#0E5E6F',
  primarySoft: '#4A8C99',
  cardBg: '#FFFFFF',
  rule: '#E5E5E5',
  watermark: '#EEEEEE',
};

const fontSans = '"Calibri", "Open Sans", "Inter", system-ui, sans-serif';
const fontMono = '"JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace';

const Title = ({ children }: { children: React.ReactNode }) => (
  <h1
    style={{
      fontFamily: fontSans,
      fontSize: 128,
      fontWeight: 600,
      lineHeight: 1.05,
      letterSpacing: '-0.025em',
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
        left: 96,
        right: 96,
        bottom: 48,
        display: 'flex',
        justifyContent: 'space-between',
        fontFamily: fontSans,
        fontSize: 20,
        color: palette.textSoft,
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
      }}
    >
      <span>Clinical Update · 2026</span>
      <span style={{ fontFamily: fontMono, letterSpacing: '0.04em' }}>
        {String(current).padStart(2, '0')} / {String(total).padStart(2, '0')}
      </span>
    </div>
  );
};

const Eyebrow = ({ children }: { children: React.ReactNode }) => (
  <div
    style={{
      fontFamily: fontMono,
      fontSize: 22,
      letterSpacing: '0.15em',
      textTransform: 'uppercase',
      color: palette.primary,
      fontWeight: 500,
    }}
  >
    {children}
  </div>
);

const StatCard = ({ value, label, ci }: { value: string; label: string; ci?: string }) => (
  <div
    style={{
      background: palette.cardBg,
      border: `1px solid ${palette.rule}`,
      borderLeft: `4px solid ${palette.primary}`,
      borderRadius: 8,
      padding: '32px 40px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      flex: 1,
    }}
  >
    <div
      style={{
        fontSize: 72,
        fontWeight: 700,
        color: palette.accent,
        lineHeight: 1,
        fontFamily: fontSans,
      }}
    >
      {value}
    </div>
    <div style={{ fontSize: 24, color: palette.text, fontWeight: 500 }}>{label}</div>
    {ci && (
      <div style={{ fontFamily: fontMono, fontSize: 18, color: palette.textSoft }}>{ci}</div>
    )}
  </div>
);

const styles = `
  @keyframes cm-fadeUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes cm-statPulse {
    0%, 100% { transform: scale(1); }
    50%      { transform: scale(1.04); }
  }
  .cm-fadeUp { opacity: 0; animation: cm-fadeUp 0.65s cubic-bezier(.2,.7,.2,1) forwards; }
  .cm-statPulse { animation: cm-statPulse 2.4s ease-in-out 1.2s 2; }
`;

const fill: React.CSSProperties = {
  width: '100%',
  height: '100%',
  background: palette.bg,
  color: palette.text,
  fontFamily: fontSans,
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
        padding: 96,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
      }}
    >
      <div className="cm-fadeUp" style={{ animationDelay: '0.05s' }}>
        <Eyebrow>Clinical Update · 2026 · RCT</Eyebrow>
      </div>
      <div className="cm-fadeUp" style={{ animationDelay: '0.2s', marginTop: 24 }}>
        <Title>
          Dapagliflozin in Patients with Heart Failure and Mildly Reduced or Preserved EF
        </Title>
      </div>
      <p
        className="cm-fadeUp"
        style={{
          animationDelay: '0.4s',
          fontFamily: fontSans,
          fontSize: 32,
          color: palette.textSoft,
          maxWidth: 1500,
          marginTop: 24,
          lineHeight: 1.45,
        }}
      >
        DELIVER trial ·{' '}
        <span style={{ fontFamily: fontMono, color: palette.primary }}>NCT03619213</span> ·{' '}
        <em>N Engl J Med</em> 2022;387:1089-1098.
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
        padding: 96,
        display: 'flex',
        flexDirection: 'column',
        gap: 36,
      }}
    >
      <div className="cm-fadeUp" style={{ animationDelay: '0.05s' }}>
        <Eyebrow>Primary Outcome</Eyebrow>
        <h2
          style={{
            fontFamily: fontSans,
            fontSize: 84,
            fontWeight: 600,
            margin: '16px 0 0',
            color: palette.text,
            letterSpacing: '-0.015em',
            lineHeight: 1.1,
          }}
        >
          Composite of worsening HF or CV death.
        </h2>
      </div>
      <div
        className="cm-fadeUp"
        style={{
          animationDelay: '0.25s',
          display: 'flex',
          gap: 24,
          flex: 1,
        }}
      >
        <div className="cm-statPulse">
          <StatCard value="16.4%" label="Dapagliflozin event rate" ci="vs. 19.5% placebo" />
        </div>
        <StatCard value="0.82" label="Hazard ratio" ci="95% CI 0.73 – 0.92" />
        <StatCard value="P&lt;0.001" label="Statistical significance" ci="n = 6,263" />
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
        padding: 96,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
      }}
    >
      <div className="cm-fadeUp" style={{ animationDelay: '0.05s' }}>
        <Eyebrow>Take-home</Eyebrow>
      </div>
      <h2
        className="cm-fadeUp"
        style={{
          animationDelay: '0.25s',
          fontFamily: fontSans,
          fontSize: 92,
          fontWeight: 600,
          letterSpacing: '-0.02em',
          lineHeight: 1.1,
          margin: '20px 0 32px',
          color: palette.text,
          maxWidth: 1500,
        }}
      >
        Dapagliflozin extends the SGLT2-inhibitor benefit across the entire EF spectrum.
      </h2>
      <p
        className="cm-fadeUp"
        style={{
          animationDelay: '0.45s',
          fontFamily: fontSans,
          fontSize: 32,
          color: palette.textSoft,
          maxWidth: 1500,
          lineHeight: 1.5,
        }}
      >
        Combined with the EMPEROR-Preserved data, SGLT2 inhibitors are now Class I-IIa recommended
        for patients with HFpEF / HFmrEF regardless of diabetes status.
      </p>
    </div>
    <Footer />
  </div>
);

export default [Cover, Content, Closer] satisfies Page[];

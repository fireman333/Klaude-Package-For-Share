/**
 * Material Design 3 layout tokens for Tailwind.
 * Spread or merge this into your existing tailwind.config.js.
 *
 * @type {import('tailwindcss').Config}
 */
module.exports = {
  theme: {
    // Opinionated M3 breakpoints (uses min-width by default).
    // Add matching max-width variants by prefixing your util with `compact:` etc.
    screens: {
      compact:  { max: '599.98px' },
      medium:   { min: '600px',  max: '839.98px'  },
      expanded: { min: '840px',  max: '1199.98px' },
      large:    { min: '1200px', max: '1599.98px' },
      xlarge:   { min: '1600px' },

      // mobile-first min-width aliases
      'md-up': '600px',
      'ex-up': '840px',
      'lg-up': '1200px',
      'xl-up': '1600px',
    },
    extend: {
      // 4/8 spacing scale
      spacing: {
        '0.5': '4px',
        '1':   '8px',
        '1.5': '12px',
        '2':   '16px',
        '3':   '24px',
        '4':   '32px',
        '5':   '40px',
        '6':   '48px',
        '7':   '56px',
        '8':   '64px',
      },
      maxWidth: {
        prose: '75ch',
        body:  '1600px',
      },
      height: {
        topbar: '64px',
        'topbar-md': '112px',
        'topbar-lg': '152px',
        bottomnav: '80px',
      },
      width: {
        rail:     '80px',
        'rail-x': '256px',
        drawer:   '256px',
      },
    },
  },
};

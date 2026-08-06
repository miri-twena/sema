const path = require('path');

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    path.join(__dirname, 'app/**/*.{ts,tsx}'),
    path.join(__dirname, 'components/**/*.{ts,tsx}'),
    path.join(__dirname, 'lib/**/*.{ts,tsx}'),
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          // Was #6C74F0 (3.89:1 as white-text-on-fill and as text-on-white --
          // fails WCAG AA 4.5:1). Now the same value as `deep` below: passes
          // at 5.79:1, with comfortable margin (docs/website_qa_report.md
          // Decisions needed #1). `deep` is kept as its own token too since
          // other components reference it explicitly (text-brand-deep on
          // light bg-brand-50 tints) -- both now resolve to the same color.
          DEFAULT: '#4E56D6',
          hover: '#5B62DE',
          deep: '#4E56D6',
          400: '#949CFF',
          200: '#C7CDFF',
          50: '#EEEFFE',
        },
        coral: '#F2887C',
        yellow: '#F2C94C',
        mint: '#7DD4A8',
        ink: '#15161C',
        'ink-footer': '#0F1015',
        text: {
          DEFAULT: '#15161C',
          muted: '#5C6070',
          // Was #8A8FA3 (2.9:1 on white -- fails WCAG AA for the many small/bold
          // labels that use it: kickers, timestamps, price notes, the inactive
          // locale-switcher label). Darkened to clear 4.5:1 on white.
          faint: '#6E748C',
        },
        border: {
          DEFAULT: '#E7E8EF',
          soft: '#EDEEF4',
          faint: '#F0F1F6',
        },
        tint: {
          bg: '#FAFAFB',
          hero: '#F7F8FF',
        },
        pastel: {
          coral: { bg: '#FDEBE8', fg: '#C05A4E' },
          mint: { bg: '#E4F6EC', fg: '#2F8F63' },
          yellow: { bg: '#FBF3D9', fg: '#B48A0A' },
        },
      },
      fontFamily: {
        sans: ['Manrope', 'Heebo', 'system-ui', 'sans-serif'],
        wordmark: ['Montserrat', 'sans-serif'],
      },
      maxWidth: {
        container: '1140px',
      },
      borderRadius: {
        card: '16px',
        'card-lg': '18px',
        btn: '12px',
      },
      boxShadow: {
        hero: '0 18px 44px rgba(78,86,214,.10)',
        proactive: '0 24px 60px rgba(0,0,0,.35)',
        growth: '0 18px 40px rgba(78,86,214,.12)',
      },
    },
  },
  plugins: [],
};

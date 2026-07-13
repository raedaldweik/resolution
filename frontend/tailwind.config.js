/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0a1628',
        'ink-2': '#1e293b',
        muted: '#475569',
        faint: '#94a3b8',
        line: 'rgba(15,23,42,0.09)',
        brand: { DEFAULT: '#0b6e4f', hi: '#12925f', lo: '#084c37', soft: 'rgba(11,110,79,0.09)' },
        gold: { DEFAULT: '#b68a35', soft: 'rgba(182,138,53,0.13)' },
        // validated categorical palette — color follows the agent, everywhere
        agdoc: '#3a63a8',
        agknow: '#0b8a6d',
        agcase: '#a4660b',
        agres: '#6d4b9e',
        ok: '#047857',
        warn: '#b45309',
        crit: '#b91c2c',
      },
      fontFamily: {
        sans: ['Manrope', 'system-ui', 'sans-serif'],
        ar: ['"IBM Plex Sans Arabic"', '"Segoe UI"', 'Tahoma', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

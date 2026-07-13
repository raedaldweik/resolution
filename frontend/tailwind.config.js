/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#fcfcfb',
        panel: '#ffffff',
        ink: '#1d2a26',
        muted: '#62726c',
        line: '#e4e7e3',
        brand: { DEFAULT: '#0b6a4f', deep: '#0e3d2f', soft: '#e9f3ef' },
        gold: { DEFAULT: '#9a7b2d', soft: '#f6f0e2' },
        // validated categorical palette — color follows the agent, everywhere
        agdoc: '#3a63a8',
        agknow: '#0b8a6d',
        agcase: '#a4660b',
        agres: '#6d4b9e',
        ok: '#1a7f37',
        warn: '#b45309',
        crit: '#b3261e',
      },
      fontFamily: {
        sans: ['"Public Sans"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        ar: ['"IBM Plex Sans Arabic"', '"Segoe UI"', 'Tahoma', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

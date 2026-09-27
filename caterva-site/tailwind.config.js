/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        void: '#050607',
        panel: '#0A0C0D',
        raised: '#101314',
        line: '#1A1E20',
        lineBright: '#272D30',
        ink: '#E8EAEB',
        dim: '#8C9398',
        faint: '#555B5F',
        verified: '#6EE7B7',
        flagged: '#FBBF24',
        rejected: '#F87171',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

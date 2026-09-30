import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-geist-sans)', 'Inter', 'system-ui', 'sans-serif'],
        serif: ['var(--font-dm-serif)', 'Cormorant Garamond', 'serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        darkbg: '#F7F3E8',
        surface: '#FFFDF8',
        'surface-elevated': '#FFFFFF',
        'surface-border': '#DDD7C8',
        'surface-muted': '#F1ECDF',
        'text-main': '#1A2520',
        'text-secondary': '#4F5A53',
        'text-muted': '#7C7B71',
        accent: '#C9A24A',
        'deep-green': '#123C30',
        green: '#194C3D',
        'soft-green': '#E6EFE9',
        terracotta: '#9A533B',
        gold: '#C9A24A',
        ok: '#2F6B4F',
        'ok-bg': '#E3F0E8',
        warn: '#8A5A12',
        'warn-bg': '#FBF0D9',
        danger: '#A33B2F',
        'danger-bg': '#F8E3E0',
        info: '#2B5C8A',
        'info-bg': '#E2ECF5',
      },
    },
  },
  plugins: [],
};
export default config;

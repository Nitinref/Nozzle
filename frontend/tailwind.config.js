/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#0a0f1d',
          900: '#10172b',
          800: '#1a2340',
          700: '#273152',
          600: '#38486e',
          500: '#5b6d9a',
          400: '#8ea0cb',
          300: '#bac7eb',
          200: '#d8e1fb',
          100: '#eff4ff',
        },
        sea: {
          500: '#2dd4bf',
          400: '#4ade80',
          300: '#6ee7b7',
        },
        ember: {
          500: '#f97316',
          400: '#fb923c',
          300: '#fdba74',
        },
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(255,255,255,0.04), 0 20px 60px rgba(2,6,23,0.5)',
      },
      backgroundImage: {
        'radial-grid':
          'radial-gradient(circle at 1px 1px, rgba(148,163,184,0.18) 1px, transparent 0)',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '0.55' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        float: 'float 8s ease-in-out infinite',
        pulseGlow: 'pulseGlow 2.8s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}


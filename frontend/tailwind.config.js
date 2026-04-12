/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        'slide-in': {
          '0%':   { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        typing: {
          '0%, 80%, 100%': { transform: 'scale(0)' },
          '40%':            { transform: 'scale(1)' },
        },
      },
      animation: {
        'slide-in': 'slide-in 0.3s ease-out forwards',
        'fade-in':  'fade-in 0.25s ease-out forwards',
        'typing':   'typing 1.4s infinite ease-in-out both',
      },
    },
  },
  plugins: [],
}

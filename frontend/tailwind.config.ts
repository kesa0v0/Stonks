import type { Config } from 'tailwindcss'

export default {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#0d59f2',
        'background-light': '#f5f6f8',
        'background-dark': '#101622',
        up: '#ef4444',
        down: '#0d59f2',
      },
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
      },
    },
  },
  plugins: [require('@tailwindcss/forms')],
} satisfies Config

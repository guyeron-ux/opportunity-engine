/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        moonshot: '#7c3aed',
        pragmatic: '#0891b2',
      },
    },
  },
  plugins: [],
}

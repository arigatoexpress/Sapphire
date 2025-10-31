/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#1E3A8A',
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
        neutral: '#6B7280',
      },
    },
  },
  plugins: [],
};


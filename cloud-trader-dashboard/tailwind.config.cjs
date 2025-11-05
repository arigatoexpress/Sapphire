/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        surface: {
          50: '#020617',    // Deep navy, almost black
          75: '#081023',    // Slightly lighter for nested cards
          100: '#0f172a',   // Dark blue-slate (was surface-50)
          200: '#1e293b',   // Slate gray for borders
          300: '#334155',   // Lighter slate for interactive elements
        },
        accent: {
          ai: '#818cf8',        // Lavender for AI/model elements
          emerald: '#34d399',   // Keep vibrant emerald for P/L
          sapphire: '#38bdf8',  // Bright blue for key metrics
          aurora: '#f472b6',    // Pink/magenta for highlights
        },
        'security-shield': '#f59e0b', // Amber for security/warning elements
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
        neutral: '#94a3b8',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui'],
      },
      boxShadow: {
        glass: '0 20px 45px -20px rgba(15, 23, 42, 0.55)',
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
};


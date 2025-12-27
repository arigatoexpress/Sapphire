/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
        tech: ['Orbitron', 'sans-serif'], // Added for the "World Class" header
        code: ['JetBrains Mono', 'monospace'], // Explicit alias
      },
      colors: {
        sapphire: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
        },
        // Firedancer-inspired Neon Palette
        fd: {
          bg: '#000000',      // Deep Black
          card: '#121212',    // Card Background
          border: '#1E1E1E',  // Subtle Border
          success: '#00FF9D', // Neon Green
          purple: '#9D00FF',  // Electric Purple
          warning: '#FF9D00', // Warning Orange
          error: '#FF0055',   // Error Red
          blue: '#00D1FF',    // Cyan/Blue Accent
          muted: '#525252',   // Muted Text
        }
      },
      backgroundImage: {
        'fd-gradient': 'linear-gradient(to bottom, #000000, #0a0a0a)',
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 8s linear infinite',
        'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
      },
      keyframes: {
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        }
      }
    },
  },
  plugins: [],
}

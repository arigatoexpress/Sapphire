/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          midnight: '#01010f',
          depth: '#040927',
          abyss: '#07123d',
          trench: '#0b1f55',
          halo: '#6ec1ff',
          ice: '#dff4ff',
        },
        surface: {
          25: '#020514',
          50: '#050a1f',
          75: '#09173a',
          100: '#0e244f',
          200: '#1c366d',
        },
        accent: {
          sapphire: '#4da6ff',
          nebula: '#8f74ff',
          infinity: '#00f0ff',
          aurora: '#6de8ff',
          pulse: '#3cf8c9',
          emerald: '#3cf8c9',
          ai: '#8f74ff',
        },
        'brand-accent-blue': '#4da6ff',
        'brand-accent-green': '#3cf8c9',
        'brand-accent-purple': '#8f74ff',
        'brand-accent-teal': '#00f0ff',
        'brand-accent-orange': '#f5a623',
        'brand-border': '#1f3355',
        'brand-muted': '#95a8d8',
        warning: '#f5a623',
        success: '#38f1b9',
        error: '#ff6f91',
        neutral: '#7c90c0',
      },
      fontFamily: {
        sans: ['"Space Grotesk"', 'Inter', 'ui-sans-serif', 'system-ui'],
      },
      backgroundImage: {
        'sapphire-mesh': 'radial-gradient(circle at 20% 12%, rgba(77,166,255,0.22), transparent 55%), radial-gradient(circle at 85% 18%, rgba(143,116,255,0.18), transparent 60%), radial-gradient(circle at 42% 92%, rgba(0,240,255,0.16), transparent 60%)',
        'sapphire-strata': 'linear-gradient(140deg, rgba(3,8,32,0.95) 0%, rgba(8,20,58,0.94) 38%, rgba(11,29,76,0.92) 100%)',
        'sapphire-grid': 'linear-gradient(rgba(148,163,184,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.08) 1px, transparent 1px)',
      },
      boxShadow: {
        glass: '0 24px 60px -30px rgba(0, 240, 255, 0.45)',
        sapphire: '0 40px 120px -60px rgba(77, 166, 255, 0.55)',
        'inner-glow': 'inset 0 0 40px rgba(143, 116, 255, 0.22)',
      },
      dropShadow: {
        infinity: '0 0 15px rgba(0, 240, 255, 0.55)',
      },
      backdropBlur: {
        xs: '3px',
      },
      borderRadius: {
        '4xl': '2.5rem',
      },
    },
  },
  plugins: [],
};


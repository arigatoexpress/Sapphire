import { createTheme, ThemeOptions } from '@mui/material/styles';

/**
 * Mobile-Optimized Theme with Bold Contrast and High Readability
 */

export const mobileOptimizedTheme: ThemeOptions = {
  palette: {
    mode: 'dark',
    primary: {
      main: '#00ffff', // Neon cyan
      light: '#80ffff',
      dark: '#0080ff', // Electric blue
      contrastText: '#000000',
    },
    secondary: {
      main: '#a855f7', // Electric purple
      light: '#ff00ff', // Bright magenta
      dark: '#7c3aed',
      contrastText: '#FFFFFF',
    },
    background: {
      default: '#000000', // Pure black
      paper: '#0a0a0a', // Subtle dark gray
    },
    text: {
      primary: '#ffffff', // Pure white
      secondary: '#e2e8f0', // Light gray with high contrast
      disabled: '#64748b',
    },
    error: {
      main: '#ff0044', // Bright red
      contrastText: '#FFFFFF',
    },
    warning: {
      main: '#ffaa00', // Amber
      contrastText: '#000000',
    },
    success: {
      main: '#00ff00', // Bright green
      contrastText: '#000000',
    },
    divider: 'rgba(0, 255, 255, 0.2)', // Neon cyan divider
  },
  typography: {
    fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h1: {
      fontSize: 'clamp(2rem, 5vw, 3.5rem)',
      fontWeight: 900,
      lineHeight: 1.1,
      letterSpacing: '-0.02em',
      color: '#FFFFFF',
    },
    h2: {
      fontSize: 'clamp(1.75rem, 4vw, 2.75rem)',
      fontWeight: 800,
      lineHeight: 1.2,
      letterSpacing: '-0.01em',
      color: '#FFFFFF',
    },
    h3: {
      fontSize: 'clamp(1.5rem, 3.5vw, 2.25rem)',
      fontWeight: 800,
      lineHeight: 1.3,
      color: '#FFFFFF',
    },
    h4: {
      fontSize: 'clamp(1.25rem, 3vw, 1.875rem)',
      fontWeight: 700,
      lineHeight: 1.4,
      color: '#FFFFFF',
    },
    h5: {
      fontSize: 'clamp(1.125rem, 2.5vw, 1.5rem)',
      fontWeight: 700,
      lineHeight: 1.5,
      color: '#FFFFFF',
    },
    h6: {
      fontSize: 'clamp(1rem, 2vw, 1.25rem)',
      fontWeight: 700,
      lineHeight: 1.5,
      color: '#FFFFFF',
    },
    body1: {
      fontSize: 'clamp(1rem, 4vw, 1.125rem)',
      lineHeight: 1.8,
      color: '#FFFFFF',
      fontWeight: 400,
      letterSpacing: '0.01em',
    },
    body2: {
      fontSize: 'clamp(0.9rem, 3.5vw, 1rem)',
      lineHeight: 1.7,
      color: '#E2E8F0',
      fontWeight: 400,
      letterSpacing: '0.005em',
    },
    button: {
      fontSize: 'clamp(0.875rem, 2vw, 1rem)',
      fontWeight: 700,
      letterSpacing: '0.025em',
      textTransform: 'none',
    },
    caption: {
      fontSize: 'clamp(0.75rem, 1.5vw, 0.875rem)',
      lineHeight: 1.5,
      color: '#CBD5E1',
      fontWeight: 500,
    },
    // Monospace for metrics/numbers for improved legibility
    overline: {
      fontFamily: '"JetBrains Mono", "Fira Code", "Consolas", monospace',
      fontSize: 'clamp(0.7rem, 1.5vw, 0.8rem)',
      fontWeight: 600,
      letterSpacing: '0.05em',
    },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: '#000000',
          color: '#FFFFFF',
          fontSmooth: 'always',
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: '#000000', // Pure black
          border: '2px solid rgba(0, 255, 255, 0.4)', // Neon cyan border
          borderRadius: 16,
          padding: { xs: '1rem', sm: '1.5rem' },
          transition: 'all 0.2s ease',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.5)',
          '&:hover': {
            borderColor: '#00ffff', // Bright neon cyan on hover
            transform: 'translateY(-2px)',
            boxShadow: '0 12px 40px rgba(0, 255, 255, 0.3), 0 0 20px rgba(0, 255, 255, 0.2)',
          },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          padding: '14px 28px',
          fontSize: 'clamp(0.875rem, 2vw, 1rem)',
          fontWeight: 700,
          textTransform: 'none',
          borderWidth: '2px',
          '&:hover': {
            transform: 'translateY(-1px)',
          },
        },
        contained: {
          backgroundColor: '#00ffff', // Neon cyan
          color: '#000000',
          boxShadow: '0 4px 16px rgba(0, 255, 255, 0.4), 0 0 20px rgba(0, 255, 255, 0.2)',
          '&:hover': {
            backgroundColor: '#80ffff',
            boxShadow: '0 6px 24px rgba(0, 255, 255, 0.6), 0 0 30px rgba(0, 255, 255, 0.3)',
          },
        },
      },
    },
    MuiTypography: {
      styleOverrides: {
        root: {
          wordBreak: 'break-word',
        },
        h1: { color: '#FFFFFF', fontWeight: 900 },
        h2: { color: '#FFFFFF', fontWeight: 800 },
        h3: { color: '#FFFFFF', fontWeight: 800 },
        h4: { color: '#FFFFFF', fontWeight: 700 },
        h5: { color: '#FFFFFF', fontWeight: 700 },
        h6: { color: '#FFFFFF', fontWeight: 700 },
        body1: { color: '#E2E8F0', fontSize: 'clamp(1rem, 2vw, 1.125rem)' },
        body2: { color: '#E2E8F0', fontSize: 'clamp(0.875rem, 1.75vw, 1rem)' },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontSize: 'clamp(0.75rem, 1.5vw, 0.875rem)',
          fontWeight: 700,
          height: 'auto',
          padding: '6px 12px',
          borderRadius: 8,
          borderWidth: '2px',
        },
      },
    },
    MuiContainer: {
      styleOverrides: {
        root: {
          paddingLeft: 'clamp(16px, 4vw, 24px)',
          paddingRight: 'clamp(16px, 4vw, 24px)',
        },
      },
    },
  },
  breakpoints: {
    values: {
      xs: 0,
      sm: 600,
      md: 960,
      lg: 1280,
      xl: 1920,
    },
  },
};

export const mobileTheme = createTheme(mobileOptimizedTheme);

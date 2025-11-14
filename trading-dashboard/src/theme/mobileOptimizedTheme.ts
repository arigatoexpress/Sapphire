import { createTheme, ThemeOptions } from '@mui/material/styles';

/**
 * Mobile-Optimized Theme with Bold Contrast and High Readability
 */

export const mobileOptimizedTheme: ThemeOptions = {
  palette: {
    mode: 'dark',
    primary: {
      main: '#0EA5E9',
      light: '#38BDF8',
      dark: '#0284C7',
      contrastText: '#FFFFFF',
    },
    secondary: {
      main: '#8B5CF6',
      light: '#A78BFA',
      dark: '#6D28D9',
      contrastText: '#FFFFFF',
    },
    background: {
      default: '#000000',
      paper: '#0A0A0F',
    },
    text: {
      primary: '#FFFFFF',
      secondary: '#E2E8F0',
      disabled: '#94A3B8',
    },
    divider: 'rgba(255, 255, 255, 0.2)',
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
          backgroundColor: '#0A0A0F',
          border: '2px solid rgba(255, 255, 255, 0.2)',
          borderRadius: 16,
          padding: { xs: '1rem', sm: '1.5rem' },
          transition: 'all 0.2s ease',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
          '&:hover': {
            borderColor: 'rgba(14, 165, 233, 0.6)',
            transform: 'translateY(-2px)',
            boxShadow: '0 12px 40px rgba(14, 165, 233, 0.25)',
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
          backgroundColor: '#0EA5E9',
          color: '#FFFFFF',
          boxShadow: '0 4px 16px rgba(14, 165, 233, 0.4)',
          '&:hover': {
            backgroundColor: '#0284C7',
            boxShadow: '0 6px 24px rgba(14, 165, 233, 0.5)',
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


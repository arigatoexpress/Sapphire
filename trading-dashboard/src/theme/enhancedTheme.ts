import { createTheme, ThemeOptions } from '@mui/material/styles';

/**
 * Sapphire Trade - Enhanced Futuristic Theme
 * Professional, modern, sleek design with optimal readability and contrast
 */

export const enhancedThemeOptions: ThemeOptions = {
  palette: {
    mode: 'dark',
    primary: {
      main: '#0EA5E9', // Sapphire Blue
      light: '#38BDF8',
      dark: '#0284C7',
      contrastText: '#FFFFFF',
    },
    secondary: {
      main: '#8B5CF6', // Royal Purple
      light: '#A78BFA',
      dark: '#6D28D9',
      contrastText: '#FFFFFF',
    },
    success: {
      main: '#10B981', // Emerald
      light: '#34D399',
      dark: '#059669',
      contrastText: '#FFFFFF',
    },
    warning: {
      main: '#F59E0B', // Amber
      light: '#FBBF24',
      dark: '#D97706',
      contrastText: '#0A0A0F',
    },
    error: {
      main: '#EF4444', // Red
      light: '#F87171',
      dark: '#DC2626',
      contrastText: '#FFFFFF',
    },
    info: {
      main: '#06B6D4', // Cyan
      light: '#22D3EE',
      dark: '#0891B2',
      contrastText: '#FFFFFF',
    },
    background: {
      default: '#0A0A0F', // Deep black-blue
      paper: '#0F172A', // Slightly lighter for cards
    },
    text: {
      primary: '#F8FAFC', // High contrast white
      secondary: '#CBD5E1', // Light gray for secondary text
      disabled: '#64748B', // Medium gray for disabled
    },
    divider: 'rgba(148, 163, 184, 0.12)', // Subtle divider
  },
  typography: {
    fontFamily: [
      '"Inter"',
      '"SF Pro Display"',
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
    h1: {
      fontSize: '3.5rem',
      fontWeight: 800,
      lineHeight: 1.2,
      letterSpacing: '-0.02em',
      color: '#F8FAFC',
    },
    h2: {
      fontSize: '2.75rem',
      fontWeight: 800,
      lineHeight: 1.25,
      letterSpacing: '-0.01em',
      color: '#F8FAFC',
    },
    h3: {
      fontSize: '2.25rem',
      fontWeight: 700,
      lineHeight: 1.3,
      letterSpacing: '-0.01em',
      color: '#F8FAFC',
    },
    h4: {
      fontSize: '1.875rem',
      fontWeight: 700,
      lineHeight: 1.35,
      color: '#F8FAFC',
    },
    h5: {
      fontSize: '1.5rem',
      fontWeight: 600,
      lineHeight: 1.4,
      color: '#F8FAFC',
    },
    h6: {
      fontSize: '1.25rem',
      fontWeight: 600,
      lineHeight: 1.5,
      color: '#F8FAFC',
    },
    body1: {
      fontSize: '1.125rem', // 18px - larger for readability
      lineHeight: 1.75,
      color: '#CBD5E1',
      fontWeight: 400,
    },
    body2: {
      fontSize: '1rem', // 16px
      lineHeight: 1.6,
      color: '#CBD5E1',
      fontWeight: 400,
    },
    button: {
      fontSize: '1rem',
      fontWeight: 600,
      letterSpacing: '0.025em',
      textTransform: 'none',
    },
    caption: {
      fontSize: '0.875rem',
      lineHeight: 1.5,
      color: '#94A3B8',
    },
    subtitle1: {
      fontSize: '1.125rem',
      lineHeight: 1.6,
      fontWeight: 500,
      color: '#F8FAFC',
    },
    subtitle2: {
      fontSize: '1rem',
      lineHeight: 1.5,
      fontWeight: 500,
      color: '#CBD5E1',
    },
  },
  shape: {
    borderRadius: 12,
  },
  shadows: [
    'none',
    '0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24)',
    '0 3px 6px rgba(0, 0, 0, 0.16), 0 3px 6px rgba(0, 0, 0, 0.23)',
    '0 10px 20px rgba(0, 0, 0, 0.19), 0 6px 6px rgba(0, 0, 0, 0.23)',
    '0 14px 28px rgba(0, 0, 0, 0.25), 0 10px 10px rgba(0, 0, 0, 0.22)',
    '0 19px 38px rgba(0, 0, 0, 0.30), 0 15px 12px rgba(0, 0, 0, 0.22)',
    '0 25px 50px rgba(0, 0, 0, 0.35), 0 20px 15px rgba(0, 0, 0, 0.25)',
    '0 30px 60px rgba(0, 0, 0, 0.40), 0 25px 20px rgba(0, 0, 0, 0.30)',
    '0 35px 70px rgba(0, 0, 0, 0.45), 0 30px 25px rgba(0, 0, 0, 0.35)',
    '0 40px 80px rgba(0, 0, 0, 0.50), 0 35px 30px rgba(0, 0, 0, 0.40)',
    ...Array(15).fill('0 0 0 rgba(0, 0, 0, 0)'),
  ],
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: '#0A0A0F',
          color: '#F8FAFC',
          fontSmooth: 'always',
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
        },
        '*': {
          scrollbarWidth: 'thin',
          scrollbarColor: 'rgba(148, 163, 184, 0.3) transparent',
        },
        '*::-webkit-scrollbar': {
          width: '8px',
          height: '8px',
        },
        '*::-webkit-scrollbar-track': {
          background: 'transparent',
        },
        '*::-webkit-scrollbar-thumb': {
          backgroundColor: 'rgba(148, 163, 184, 0.3)',
          borderRadius: '4px',
          '&:hover': {
            backgroundColor: 'rgba(148, 163, 184, 0.5)',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: 'rgba(15, 23, 42, 0.8)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(148, 163, 184, 0.1)',
          borderRadius: 16,
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            borderColor: 'rgba(14, 165, 233, 0.3)',
            boxShadow: '0 8px 32px rgba(14, 165, 233, 0.15)',
            transform: 'translateY(-2px)',
          },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          padding: '12px 24px',
          fontSize: '1rem',
          fontWeight: 600,
          textTransform: 'none',
          transition: 'all 0.2s ease',
          '&:hover': {
            transform: 'translateY(-1px)',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
          },
        },
        contained: {
          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.2)',
          '&:hover': {
            boxShadow: '0 6px 20px rgba(0, 0, 0, 0.3)',
          },
        },
      },
    },
    MuiTypography: {
      styleOverrides: {
        root: {
          wordBreak: 'break-word',
        },
        h1: {
          fontWeight: 800,
          letterSpacing: '-0.02em',
        },
        h2: {
          fontWeight: 800,
          letterSpacing: '-0.01em',
        },
        h3: {
          fontWeight: 700,
          letterSpacing: '-0.01em',
        },
        body1: {
          color: '#CBD5E1',
          fontSize: '1.125rem',
          lineHeight: 1.75,
        },
        body2: {
          color: '#CBD5E1',
          fontSize: '1rem',
          lineHeight: 1.6,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontSize: '0.875rem',
          fontWeight: 600,
          height: '32px',
          borderRadius: 8,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundColor: 'rgba(15, 23, 42, 0.9)',
          backdropFilter: 'blur(20px)',
        },
      },
    },
    MuiInputBase: {
      styleOverrides: {
        root: {
          fontSize: '1rem',
          color: '#F8FAFC',
          '&::placeholder': {
            color: '#94A3B8',
            opacity: 0.7,
          },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          borderColor: 'rgba(148, 163, 184, 0.2)',
          '&:hover': {
            borderColor: 'rgba(14, 165, 233, 0.4)',
          },
          '&.Mui-focused': {
            borderColor: '#0EA5E9',
          },
        },
      },
    },
  },
};

export const enhancedTheme = createTheme(enhancedThemeOptions);


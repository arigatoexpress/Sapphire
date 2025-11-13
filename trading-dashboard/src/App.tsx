import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { CssBaseline, Box, Typography } from '@mui/material';
import { TradingProvider } from './contexts/TradingContext';
// import Sidebar from './components/Sidebar';
import Navbar from './components/Navbar';
import AnimatedBackground from './components/AnimatedBackground';
import Dashboard from './pages/Dashboard';
import Portfolio from './pages/Portfolio';
import Agents from './pages/Agents';
import Analytics from './pages/Analytics';

// Extend theme with custom agent colors
declare module '@mui/material/styles' {
  interface Theme {
    agent: {
      deepseek: string;
      qwen: string;
      fingpt: string;
      lagllama: string;
      vpin: string;
      freqtrade: string;
      hummingbot: string;
    };
  }
  interface ThemeOptions {
    agent?: {
      deepseek: string;
      qwen: string;
      fingpt: string;
      lagllama: string;
      vpin: string;
      freqtrade: string;
      hummingbot: string;
    };
  }
}

// 🎨 Clean Sapphire Theme - Readable, Uniform & Beautiful
const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#0ea5e9', // Clean sapphire blue
      light: '#38bdf8',
      dark: '#0284c7',
    },
    secondary: {
      main: '#06b6d4', // Cyan accent
      light: '#22d3ee',
      dark: '#0891b2',
    },
    background: {
      default: '#0f172a', // Deep navy background
      paper: 'rgba(30, 41, 59, 0.8)', // Semi-transparent slate
    },
    success: {
      main: '#10b981', // Emerald
    },
    error: {
      main: '#ef4444', // Clean red
    },
    warning: {
      main: '#f59e0b', // Amber
    },
    info: {
      main: '#8b5cf6', // Violet
    },
    text: {
      primary: '#f1f5f9', // Off-white for readability
      secondary: '#cbd5e1', // Light gray for secondary text
    },
  },
  // Custom agent colors - clean and distinct
  agent: {
    deepseek: '#06b6d4', // Cyan - Market Analysis
    qwen: '#8b5cf6', // Violet - Risk Management
    fingpt: '#ef4444', // Red - Financial Analysis
    lagllama: '#f59e0b', // Amber - Time Series
    vpin: '#ec4899', // Pink - VPIN Analysis
    freqtrade: '#3b82f6', // Blue - Algorithmic Execution
    hummingbot: '#10b981', // Emerald - Market Making
  },
  typography: {
    fontFamily: '"Inter", "SF Pro Display", "Segoe UI", system-ui, sans-serif',
    h1: {
      fontSize: '3rem',
      fontWeight: 800,
      letterSpacing: '-0.02em',
      lineHeight: 1.1,
    },
    h2: {
      fontSize: '2.25rem',
      fontWeight: 700,
      letterSpacing: '-0.01em',
      lineHeight: 1.2,
    },
    h3: {
      fontSize: '1.875rem',
      fontWeight: 600,
      letterSpacing: '-0.01em',
      lineHeight: 1.3,
    },
    h4: {
      fontSize: '1.5rem',
      fontWeight: 600,
      letterSpacing: '0em',
      lineHeight: 1.4,
    },
    h5: {
      fontSize: '1.25rem',
      fontWeight: 600,
      letterSpacing: '0em',
      lineHeight: 1.5,
    },
    h6: {
      fontSize: '1.125rem',
      fontWeight: 600,
      letterSpacing: '0em',
      lineHeight: 1.6,
    },
    body1: {
      fontSize: '1rem',
      lineHeight: 1.7,
      letterSpacing: '0.01em',
    },
    body2: {
      fontSize: '0.875rem',
      lineHeight: 1.6,
      letterSpacing: '0.02em',
    },
  },
  shape: {
    borderRadius: 16,
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: 'rgba(30, 41, 59, 0.6)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(148, 163, 184, 0.1)',
          borderRadius: '16px',
          boxShadow: '0 4px 24px rgba(0, 0, 0, 0.15)',
          transition: 'all 0.3s ease',
          '&:hover': {
            transform: 'translateY(-2px)',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.2)',
            borderColor: 'rgba(14, 165, 233, 0.2)',
          },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: '12px',
          textTransform: 'none',
          fontWeight: 600,
          fontSize: '0.95rem',
          padding: '10px 24px',
          transition: 'all 0.2s ease',
          '&:hover': {
            transform: 'translateY(-1px)',
          },
        },
        contained: {
          backgroundColor: '#0ea5e9',
          color: '#ffffff',
          boxShadow: '0 2px 8px rgba(14, 165, 233, 0.3)',
          '&:hover': {
            backgroundColor: '#0284c7',
            boxShadow: '0 4px 16px rgba(14, 165, 233, 0.4)',
          },
        },
        outlined: {
          borderColor: 'rgba(14, 165, 233, 0.5)',
          color: '#0ea5e9',
          '&:hover': {
            borderColor: '#0ea5e9',
            backgroundColor: 'rgba(14, 165, 233, 0.05)',
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
          fontWeight: 500,
          fontSize: '0.85rem',
          height: '28px',
        },
        filled: {
          backgroundColor: 'rgba(14, 165, 233, 0.1)',
          color: '#0ea5e9',
          border: '1px solid rgba(14, 165, 233, 0.2)',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundColor: 'rgba(30, 41, 59, 0.4)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(148, 163, 184, 0.08)',
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: '6px',
          backgroundColor: 'rgba(148, 163, 184, 0.2)',
          height: '8px',
        },
        bar: {
          borderRadius: '6px',
          backgroundColor: '#0ea5e9',
        },
      },
    },
  },
});


function AppContent() {
  return (
    <Router>
      <AnimatedBackground />
      <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'transparent' }}>
        <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          <Navbar />
          <Box
            component="main"
            sx={{
              flexGrow: 1,
              p: 3,
              overflow: 'auto',
              background: 'transparent',
            }}
          >
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>

            {/* Competition & DEX Footer */}
            <Box
              component="footer"
              sx={{
                mt: 'auto',
                py: 3,
                px: 3,
                borderTop: '2px solid rgba(255, 215, 0, 0.3)',
                background: 'linear-gradient(135deg, rgba(0, 0, 0, 0.4) 0%, rgba(138, 43, 226, 0.1) 100%)',
                backdropFilter: 'blur(15px)',
                textAlign: 'center'
              }}
            >
              <Box sx={{ mb: 2 }}>
                <Typography
                  variant="h6"
                  sx={{
                    fontWeight: 700,
                    fontSize: '1.1rem',
                    background: 'linear-gradient(45deg, #ffd700 0%, #ffed4e 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    mb: 1
                  }}
                >
                  🏆 Vibe Coding Competition Entry 🏆
                </Typography>
                <Typography
                  variant="body1"
                  sx={{
                    color: 'rgba(255, 255, 255, 0.8)',
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    mb: 2
                  }}
                >
                  Advanced AI-Powered Trading System
                </Typography>
              </Box>

              <Typography
                variant="body1"
                sx={{
                  color: 'rgba(255, 255, 255, 0.9)',
                  fontSize: '1rem',
                  fontWeight: 500,
                  mb: 1
                }}
              >
                🚀 <strong style={{ color: '#8a2be2', fontSize: '1.1em' }}>Sapphire Trade</strong> is proudly built on{' '}
                <strong style={{ color: '#00d4aa', fontSize: '1.1em' }}>Aster DEX</strong>
              </Typography>

              <Typography
                variant="body2"
                sx={{
                  color: 'rgba(255, 255, 255, 0.7)',
                  fontSize: '0.85rem',
                  fontStyle: 'italic'
                }}
              >
                The premier decentralized futures exchange for automated algorithmic trading
              </Typography>
            </Box>
          </Box>
        </Box>
      </Box>
    </Router>
  );
}

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <TradingProvider>
        <AppContent />
      </TradingProvider>
    </ThemeProvider>
  );
}

export default App;

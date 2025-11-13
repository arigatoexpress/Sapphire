import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { CssBaseline, Box, Typography } from '@mui/material';
import { TradingProvider } from './contexts/TradingContext';
import Sidebar from './components/Sidebar';
import Navbar from './components/Navbar';
import AnimatedBackground from './components/AnimatedBackground';
import Dashboard from './pages/Dashboard';
import Portfolio from './pages/Portfolio';
import Agents from './pages/Agents';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';

// 🎨 Premium Sapphire Theme - Artful & Sophisticated
const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#00d4aa', // Sapphire green
      light: '#00f5d4',
      dark: '#009d80',
    },
    secondary: {
      main: '#8a2be2', // Electric purple
      light: '#a855f7',
      dark: '#6b21a8',
    },
    background: {
      default: 'transparent', // Let CSS handle background
      paper: 'rgba(255, 255, 255, 0.08)',
    },
    success: {
      main: '#00d4aa',
    },
    error: {
      main: '#ff4757',
    },
    warning: {
      main: '#ffa502',
    },
    info: {
      main: '#3742fa',
    },
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
          background: 'rgba(255, 255, 255, 0.08)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: '16px',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            transform: 'translateY(-2px)',
            boxShadow: '0 12px 40px rgba(0, 0, 0, 0.4)',
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
          letterSpacing: '0.02em',
          transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        },
        contained: {
          background: 'linear-gradient(135deg, #00d4aa 0%, #00f5d4 100%)',
          boxShadow: '0 4px 16px rgba(0, 212, 170, 0.3)',
          '&:hover': {
            background: 'linear-gradient(135deg, #00f5d4 0%, #00d4aa 100%)',
            boxShadow: '0 6px 24px rgba(0, 212, 170, 0.4)',
            transform: 'translateY(-1px)',
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          background: 'rgba(255, 255, 255, 0.08)',
          backdropFilter: 'blur(20px)',
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
        <Sidebar />
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
              <Route path="/settings" element={<Settings />} />
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
                🚀 <strong style={{ color: '#8a2be2', fontSize: '1.1em' }}>Sapphire Trading</strong> is proudly built on{' '}
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

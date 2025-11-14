import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline, Box, Typography } from '@mui/material';
import { TradingProvider } from './contexts/TradingContext';
import Navbar from './components/Navbar';
import AnimatedBackground from './components/AnimatedBackground';
import Dashboard from './pages/Dashboard';
import Portfolio from './pages/Portfolio';
import Agents from './pages/Agents';
import Analytics from './pages/Analytics';
import MissionControl from './pages/MissionControl';
import { mobileTheme } from './theme/mobileOptimizedTheme';

// Using enhanced futuristic theme with optimal readability and contrast


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
              p: { xs: 2, sm: 3 },
              overflow: 'auto',
              background: 'transparent',
            }}
          >
            <Routes>
              <Route path="/" element={<Analytics />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/portfolio" element={<Portfolio />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/mission-control" element={<MissionControl />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>

            {/* Competition & DEX Footer */}
            <Box
              component="footer"
              sx={{
                mt: 'auto',
                py: { xs: 2, sm: 3 },
                px: { xs: 2, sm: 3 },
                borderTop: '2px solid rgba(255, 215, 0, 0.3)',
                background: 'linear-gradient(135deg, rgba(0, 0, 0, 0.4) 0%, rgba(138, 43, 226, 0.1) 100%)',
                backdropFilter: 'blur(15px)',
                textAlign: 'center'
              }}
            >
              <Box sx={{ mb: { xs: 1.5, sm: 2 } }}>
                <Typography
                  variant="h6"
                  sx={{
                    fontWeight: 700,
                    fontSize: { xs: '1rem', sm: '1.1rem' },
                    background: 'linear-gradient(45deg, #ffd700 0%, #ffed4e 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    mb: 1,
                    display: { xs: 'none', sm: 'block' }
                  }}
                >
                  🏆 Vibe Coding Competition Entry 🏆
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    color: 'rgba(255, 255, 255, 0.8)',
                    fontSize: { xs: '0.9rem', sm: '0.95rem' },
                    fontWeight: 600,
                    mb: { xs: 1, sm: 2 }
                  }}
                >
                  Advanced AI-Powered Trading System
                </Typography>
              </Box>

              <Typography
                variant="body2"
                sx={{
                  color: 'rgba(255, 255, 255, 0.9)',
                  fontSize: { xs: '0.9rem', sm: '1rem' },
                  fontWeight: 500,
                  mb: 1
                }}
              >
                🚀 <strong style={{ color: '#8a2be2' }}>Sapphire Trade</strong> on{' '}
                <strong style={{ color: '#00d4aa' }}>Aster DEX</strong>
              </Typography>

              <Typography
                variant="caption"
                sx={{
                  color: 'rgba(255, 255, 255, 0.7)',
                  fontSize: { xs: '0.75rem', sm: '0.85rem' },
                  fontStyle: 'italic',
                  display: { xs: 'none', sm: 'block' }
                }}
              >
                Premier decentralized futures exchange for automated algorithmic trading
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
    <ThemeProvider theme={mobileTheme}>
      <CssBaseline />
      <TradingProvider>
        <AppContent />
      </TradingProvider>
    </ThemeProvider>
  );
}

export default App;

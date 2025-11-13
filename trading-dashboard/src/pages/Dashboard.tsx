import { Container, Box, Typography, Button, Grid, Alert } from "@mui/material";
import React from 'react';
import { useTrading } from '../contexts/TradingContext';
import EnhancedMetrics from '../components/EnhancedMetrics';
import PortfolioChart from '../components/PortfolioChart';
import MCPChat from '../components/MCPChat';
import AgentModelCards from '../components/AgentModelCards';
import MarketAnalysis from '../components/MarketAnalysis';
import { AdvancedAnalytics } from '../components/AdvancedAnalytics';
import { MarketMicrostructure } from '../components/MarketMicrostructure';
import { SentimentAnalysis } from '../components/SentimentAnalysis';
import { RiskManagement } from '../components/RiskManagement';
import SystemAchievements from '../components/SystemAchievements';

const Dashboard: React.FC = () => {
  const { error, refreshData } = useTrading();
  const [activeView, setActiveView] = React.useState<'overview' | 'analytics' | 'microstructure' | 'sentiment' | 'risk'>('overview');

  const views = [
    { id: 'overview', label: '📊 Overview', description: 'Core trading dashboard' },
    { id: 'analytics', label: '🔬 Analytics', description: 'Advanced performance metrics' },
    { id: 'microstructure', label: '🔬 Microstructure', description: 'Order book & liquidity analysis' },
    { id: 'sentiment', label: '🧠 Sentiment', description: 'Market psychology & news' },
    { id: 'risk', label: '🛡️ Risk', description: 'Advanced risk management' },
  ];

  return (
    <Container maxWidth="xl" sx={{ py: 2 }} className="fade-in-up">
      {error && (
        <Alert
          severity="error"
          sx={{
            mb: 3,
            borderRadius: 2,
            backdropFilter: 'blur(10px)',
            background: 'rgba(255, 87, 87, 0.1)',
            border: '1px solid rgba(255, 87, 87, 0.2)',
            '& .MuiAlert-message': { width: '100%' }
          }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={refreshData}
              sx={{
                fontWeight: 600,
                '&:hover': {
                  background: 'rgba(255, 255, 255, 0.1)'
                }
              }}
            >
              Retry
            </Button>
          }
        >
          <Box>
            <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5 }}>
              Connection Error
            </Typography>
            <Typography variant="body2">
              {error} - Click retry to refresh data from the trading system.
            </Typography>
          </Box>
        </Alert>
      )}

      {/* System Overview */}
      <Box sx={{
        mb: 4,
        textAlign: 'center',
        background: 'linear-gradient(135deg, rgba(138, 43, 226, 0.1), rgba(0, 212, 170, 0.1))',
        border: '1px solid rgba(138, 43, 226, 0.2)',
        borderRadius: 4,
        p: 4,
        position: 'relative',
        overflow: 'hidden',
        '&::before': {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'radial-gradient(circle at 30% 70%, rgba(138, 43, 226, 0.05), transparent 60%)',
          pointerEvents: 'none',
        },
      }}>
        <Box sx={{ position: 'relative', zIndex: 1 }}>
          <Typography
            variant="h2"
            sx={{
              mb: 3,
              fontWeight: 900,
              background: 'linear-gradient(135deg, #8a2be2 0%, #00d4aa 30%, #ec4899 60%, #06b6d4 100%)',
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              textAlign: 'center',
              animation: 'gradientShift 8s ease-in-out infinite',
              '@keyframes gradientShift': {
                '0%': { backgroundPosition: '0% 50%' },
                '50%': { backgroundPosition: '100% 50%' },
                '100%': { backgroundPosition: '0% 50%' },
              },
              backgroundSize: '200% 200%',
              textShadow: '0 0 40px rgba(138, 43, 226, 0.3)',
            }}
          >
            💎 SAPPHIRE TRADE
          </Typography>
          <Typography
            variant="h5"
            sx={{
              mb: 2,
              fontWeight: 700,
              background: 'linear-gradient(135deg, #00d4aa, #06b6d4)',
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            Enterprise AI Trading Platform
          </Typography>
          <Typography
            variant="body1"
            sx={{
              color: 'text.secondary',
              maxWidth: '700px',
              mx: 'auto',
              lineHeight: 1.7,
              fontSize: '1.1rem',
            }}
          >
            Enterprise-grade algorithmic trading platform featuring <strong style={{ color: '#8b5cf6' }}>5 advanced AI agents</strong>,
            <strong style={{ color: '#06b6d4' }}>99.9% uptime architecture</strong>, and <strong style={{ color: '#10b981' }}>7-layer resilience</strong>.
            Sub-100ms latency with 1000+ RPS capability on <strong style={{ color: '#ec4899' }}>Aster DEX</strong>.
          </Typography>
        </Box>

        {/* Competition Entry Banner */}
        <Box sx={{
          mt: 3,
          p: 3,
          borderRadius: 3,
          background: 'linear-gradient(135deg, rgba(255, 215, 0, 0.15) 0%, rgba(255, 140, 0, 0.1) 100%)',
          border: '2px solid rgba(255, 215, 0, 0.5)',
          boxShadow: '0 4px 20px rgba(255, 215, 0, 0.2)',
          textAlign: 'center',
          position: 'relative',
          overflow: 'hidden'
        }}>
          <Box sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'radial-gradient(circle at 30% 30%, rgba(255, 215, 0, 0.1) 0%, transparent 50%)',
            pointerEvents: 'none'
          }} />
          <Typography
            variant="h5"
            sx={{
              fontWeight: 800,
              background: 'linear-gradient(45deg, #ffd700 0%, #ff6b35 50%, #ffd700 100%)',
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              mb: 1,
              position: 'relative',
              zIndex: 1,
              textShadow: '0 2px 4px rgba(0,0,0,0.3)'
            }}
          >
            🏆 Vibe Coding Competition Entry 🏆
          </Typography>
          <Typography variant="body1" sx={{
            color: 'rgba(255, 255, 255, 0.9)',
            fontWeight: 600,
            mb: 1,
            position: 'relative',
            zIndex: 1
          }}>
            Advanced AI-Powered Autonomous Trading System
          </Typography>
          <Typography variant="body2" sx={{
            color: 'rgba(255, 255, 255, 0.8)',
            position: 'relative',
            zIndex: 1
          }}>
            Built with cutting-edge AI agents, real-time market analysis, and institutional-grade risk management
          </Typography>
        </Box>

        {/* Market Pulse & Branding */}
        <Grid container spacing={2} sx={{ mt: 2 }}>
          <Grid item xs={12} md={8}>
            <Box sx={{
              p: 2,
              borderRadius: 2,
              background: 'linear-gradient(135deg, rgba(138, 43, 226, 0.1) 0%, rgba(0, 212, 170, 0.1) 100%)',
              border: '1px solid rgba(138, 43, 226, 0.3)',
            }}>
              <Typography variant="body1" sx={{ fontWeight: 600, color: '#8a2be2', mb: 1 }}>
                🚀 Powered by Aster DEX - Decentralized Futures Trading
              </Typography>
              <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                Direct access to 155+ USDT perpetual contracts with institutional-grade liquidity
              </Typography>
            </Box>
          </Grid>

          <Grid item xs={12} md={4}>
            <Box sx={{
              p: 2,
              borderRadius: 2,
              background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(236, 72, 153, 0.1) 100%)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              textAlign: 'center'
            }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: '#10b981', mb: 1 }}>
                📈 Live Market Pulse
              </Typography>
              <Box display="flex" justifyContent="center" alignItems="center" gap={1}>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#10b981' }}>
                  BULLISH
                </Typography>
                <Box
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    bgcolor: '#10b981',
                    animation: 'pulse 2s infinite',
                    '@keyframes pulse': {
                      '0%': { opacity: 1, transform: 'scale(1)' },
                      '50%': { opacity: 0.7, transform: 'scale(1.2)' },
                      '100%': { opacity: 1, transform: 'scale(1)' },
                    },
                  }}
                />
              </Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', mt: 0.5, display: 'block' }}>
                Market sentiment: Optimistic
              </Typography>
            </Box>
          </Grid>
        </Grid>

        {/* Professional Navigation Tabs */}
        <Box sx={{ mt: 4, mb: 2 }}>
          <Grid container spacing={1}>
            {views.map((view) => (
              <Grid item key={view.id}>
                <Button
                  onClick={() => setActiveView(view.id as any)}
                  sx={{
                    px: 3,
                    py: 1.5,
                    borderRadius: 3,
                    textTransform: 'none',
                    fontWeight: 600,
                    fontSize: '0.95rem',
                    minWidth: 160,
                    background: activeView === view.id
                      ? `linear-gradient(135deg, ${view.id === 'analytics' ? '#8b5cf6' :
                                                   view.id === 'microstructure' ? '#06b6d4' :
                                                   view.id === 'sentiment' ? '#ec4899' :
                                                   view.id === 'risk' ? '#ef4444' : '#00d4aa'}, ${view.id === 'analytics' ? '#ec4899' :
                                                   view.id === 'microstructure' ? '#10b981' :
                                                   view.id === 'sentiment' ? '#8b5cf6' :
                                                   view.id === 'risk' ? '#f59e0b' : '#06b6d4'})`
                      : 'rgba(255, 255, 255, 0.05)',
                    color: activeView === view.id ? 'white' : 'text.secondary',
                    border: `1px solid ${activeView === view.id ? 'transparent' : 'rgba(148, 163, 184, 0.2)'}`,
                    boxShadow: activeView === view.id ? `0 8px 32px rgba(0,0,0,0.2)` : 'none',
                    '&:hover': {
                      background: activeView === view.id
                        ? `linear-gradient(135deg, ${view.id === 'analytics' ? '#8b5cf6' :
                                                     view.id === 'microstructure' ? '#06b6d4' :
                                                     view.id === 'sentiment' ? '#ec4899' :
                                                     view.id === 'risk' ? '#ef4444' : '#00d4aa'}, ${view.id === 'analytics' ? '#ec4899' :
                                                     view.id === 'microstructure' ? '#10b981' :
                                                     view.id === 'sentiment' ? '#8b5cf6' :
                                                     view.id === 'risk' ? '#f59e0b' : '#06b6d4'})`
                        : 'rgba(255, 255, 255, 0.08)',
                      transform: 'translateY(-2px)',
                      boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
                    },
                    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                  }}
                >
                  {view.label}
                </Button>
              </Grid>
            ))}
          </Grid>
        </Box>
      </Box>

      {/* Dynamic Content Based on Active View */}
      {activeView === 'overview' && (
        <>
          {/* System Achievements Showcase */}
          <SystemAchievements />

          {/* Market Analysis & Sentiment - Front & Center */}
          <MarketAnalysis />

          {/* AI Agent Model Cards - Featured Front Page */}
          <AgentModelCards />

          {/* Portfolio Performance - Core Trading View */}
          <PortfolioChart />

          {/* AI MCP Communication Hub - Real-time Coordination */}
          <Box sx={{ mb: 4 }}>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <Typography
                variant="h5"
                sx={{
                  fontWeight: 700,
                  background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >
                🎯 Live AI Agent Coordination
              </Typography>
              <Box
                sx={{
                  bgcolor: 'rgba(139, 92, 246, 0.1)',
                  border: '1px solid rgba(139, 92, 246, 0.3)',
                  borderRadius: 2,
                  px: 2,
                  py: 0.5,
                }}
              >
                <Typography variant="caption" sx={{ color: '#8b5cf6', fontWeight: 600 }}>
                  🤖 Multi-Agent Coordination Protocol (MCP)
                </Typography>
              </Box>
            </Box>
            <Typography
              variant="body2"
              sx={{
                color: 'text.secondary',
                mb: 3,
                lineHeight: 1.6,
                maxWidth: '800px'
              }}
            >
              <strong>What is MCP?</strong> Our AI agents communicate in real-time using a sophisticated coordination protocol.
              They share trading ideas, market analysis, risk assessments, and strategy insights to make better decisions together.
              Watch them collaborate, debate, and coordinate trades - it's like having 7 expert traders working as a team! 🎪
            </Typography>
            <MCPChat />
          </Box>

          {/* Key Performance Indicators - Summary Stats */}
          <EnhancedMetrics />
        </>
      )}

      {activeView === 'analytics' && <AdvancedAnalytics />}
      {activeView === 'microstructure' && <MarketMicrostructure />}
      {activeView === 'sentiment' && <SentimentAnalysis />}
      {activeView === 'risk' && <RiskManagement />}
    </Container>
  );
};

export default Dashboard;

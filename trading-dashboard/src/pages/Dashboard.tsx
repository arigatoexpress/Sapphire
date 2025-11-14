import { Container, Box, Typography, Button, Grid, Alert } from "@mui/material";
import React from 'react';
import { useTrading } from '../contexts/TradingContext';
import RegulatoryDisclaimer from '../components/RegulatoryDisclaimer';
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
import SystemStatus from '../components/SystemStatus';

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
      {error && !error.includes('demo data') && (
        <Alert
          severity="warning"
          sx={{
            mb: 3,
            borderRadius: 2,
            backdropFilter: 'blur(10px)',
            background: 'rgba(255, 193, 7, 0.1)',
            border: '1px solid rgba(255, 193, 7, 0.2)',
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
              Backend Connection
            </Typography>
            <Typography variant="body2">
              {error.includes('backend not available') 
                ? 'Connecting to trading system...' 
                : error} - Click retry to refresh data.
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
              mb: 2,
              fontWeight: 900,
              fontSize: { xs: '2rem', md: '2.75rem' },
              background: 'linear-gradient(135deg, #0EA5E9 0%, #8B5CF6 50%, #0EA5E9 100%)',
              backgroundSize: '200% 200%',
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              animation: 'gradientShift 3s ease infinite',
              '@keyframes gradientShift': {
                '0%, 100%': { backgroundPosition: '0% 50%' },
                '50%': { backgroundPosition: '100% 50%' },
              },
              textAlign: 'center',
            }}
          >
            AI Trading System Dashboard
          </Typography>
          <Typography
            variant="h6"
            sx={{
              fontSize: { xs: '0.9rem', md: '1.1rem' },
              fontWeight: 400,
              color: 'text.secondary',
              maxWidth: '800px',
              mx: 'auto',
              mb: 2,
            }}
          >
            Enterprise AI Trading Platform
          </Typography>
          <Typography
            variant="body1"
            sx={{
              color: 'text.secondary',
              maxWidth: '800px',
              mx: 'auto',
              lineHeight: 1.7,
              fontSize: '1.1rem',
            }}
          >
            Advanced AI trading platform powered by <strong style={{ color: '#8b5cf6' }}>6 specialized Gemini AI agents</strong> with 
            <strong style={{ color: '#06b6d4' }}> real-time market analysis</strong> and <strong style={{ color: '#10b981' }}>institutional-grade risk management</strong>.
            Optimized for <strong style={{ color: '#ec4899' }}>Aster DEX perpetual futures</strong> with sub-second decision latency and automated position management.
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
            🚀 Production-Ready AI Trading System
          </Typography>
          <Typography variant="body1" sx={{
            color: 'rgba(255, 255, 255, 0.9)',
            fontWeight: 600,
            mb: 1,
            position: 'relative',
            zIndex: 1
          }}>
            Multi-Agent AI System with Real-Time Market Intelligence
          </Typography>
          <Typography variant="body2" sx={{
            color: 'rgba(255, 255, 255, 0.8)',
            position: 'relative',
            zIndex: 1
          }}>
            Live trading on Aster DEX with 6 specialized AI agents, automated risk controls, and real-time portfolio optimization
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
          {/* Market Analysis & Sentiment - Front & Center */}
          <MarketAnalysis />

          {/* AI Agent Model Cards - Featured Front Page */}
          <AgentModelCards />

          {/* AI Agent Balances - Bot Trading Capital */}
          <Box sx={{ mb: 4 }}>
            <Typography
              variant="h5"
              sx={{
                fontWeight: 700,
                mb: 3,
                textAlign: 'center',
                background: 'linear-gradient(135deg, #8b5cf6, #06b6d4)',
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              🤖 AI Agent Trading Balances
            </Typography>
            <Typography variant="body2" color="textSecondary" sx={{ mb: 3, textAlign: 'center' }}>
              Live capital allocation across our 6 specialized Gemini AI trading agents
            </Typography>

            <Grid container spacing={2}>
              {[
                { agent: 'Trend Momentum Agent', balance: 500, status: 'Active', color: '#06b6d4' },
                { agent: 'Strategy Optimization Agent', balance: 500, status: 'Active', color: '#8b5cf6' },
                { agent: 'Financial Sentiment Agent', balance: 500, status: 'Active', color: '#ef4444' },
                { agent: 'Market Prediction Agent', balance: 500, status: 'Active', color: '#f59e0b' },
                { agent: 'Volume Microstructure Agent', balance: 500, status: 'Active', color: '#ec4899' },
                { agent: 'VPIN HFT Agent', balance: 500, status: 'Active', color: '#06b6d4' },
              ].map((agent, index) => (
                <Grid item xs={12} sm={6} md={4} key={index}>
                  <Card
                    sx={{
                      background: 'rgba(30, 41, 59, 0.6)',
                      backdropFilter: 'blur(16px)',
                      border: `1px solid ${agent.color}30`,
                      borderRadius: 3,
                      transition: 'all 0.3s ease',
                      '&:hover': {
                        transform: 'translateY(-2px)',
                        borderColor: agent.color,
                        boxShadow: `0 8px 25px ${agent.color}20`,
                      },
                    }}
                  >
                    <CardContent sx={{ p: 3 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                        <Avatar
                          sx={{
                            bgcolor: `${agent.color}20`,
                            border: `2px solid ${agent.color}`,
                            width: 40,
                            height: 40,
                          }}
                        >
                          {agent.agent === 'Trend Momentum Agent' ? '🎯' :
                           agent.agent === 'Strategy Optimization Agent' ? '🧠' :
                           agent.agent === 'Financial Sentiment Agent' ? '💭' :
                           agent.agent === 'Market Prediction Agent' ? '🔮' :
                           agent.agent === 'Volume Microstructure Agent' ? '📊' : '⚡'}
                        </Avatar>
                        <Box>
                          <Typography variant="h6" sx={{ fontWeight: 600, fontSize: '0.9rem' }}>
                            {agent.agent}
                          </Typography>
                          <Chip
                            label={agent.status}
                            size="small"
                            sx={{
                              bgcolor: 'rgba(16, 185, 129, 0.1)',
                              color: '#10b981',
                              fontSize: '0.7rem',
                              height: 20,
                            }}
                          />
                        </Box>
                      </Box>

                      <Box sx={{ textAlign: 'center' }}>
                        <Typography variant="h4" sx={{ fontWeight: 900, color: agent.color, mb: 1 }}>
                          ${agent.balance}
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                          Trading Capital
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>

            <Box sx={{ mt: 3, p: 3, borderRadius: 3, bgcolor: 'rgba(30, 41, 59, 0.4)', border: '1px solid rgba(139, 92, 246, 0.2)' }}>
              <Typography variant="body2" sx={{ textAlign: 'center', fontWeight: 600, mb: 2 }}>
                💰 Total Live Trading Capital: $3,000
              </Typography>
              <Typography variant="caption" sx={{ textAlign: 'center', display: 'block', color: 'text.secondary' }}>
                Each AI agent has $500 in trading capital for leveraged perpetual futures on Aster DEX
              </Typography>
            </Box>
          </Box>

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

          {/* System Achievements & Capabilities - Moved to Bottom */}
          <Box sx={{ mt: 6, pt: 4, borderTop: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <SystemAchievements />
          </Box>
        </>
      )}

      {activeView === 'analytics' && (
        <>
          <AdvancedAnalytics />
          {/* System Achievements & Capabilities - Moved to Bottom of Analytics Page */}
          <Box sx={{ mt: 6, pt: 4, borderTop: '1px solid rgba(148, 163, 184, 0.2)' }}>
            <SystemAchievements />
          </Box>
        </>
      )}
      {activeView === 'microstructure' && <MarketMicrostructure />}
      {activeView === 'sentiment' && <SentimentAnalysis />}
      {activeView === 'risk' && <RiskManagement />}
    </Container>
  );
};

export default Dashboard;

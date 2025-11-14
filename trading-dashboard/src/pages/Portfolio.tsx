import React, { useEffect, useState, useRef } from 'react';
import { Box, Typography, Card, CardContent, Grid, Chip, Divider, LinearProgress, Container } from '@mui/material';
import { TrendingUp, TrendingDown, AccountBalance, ShowChart } from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';
import PortfolioChart from '../components/PortfolioChart';
import TradeAlertEffect from '../components/TradeAlertEffect';
import DiamondSparkle from '../components/DiamondSparkle';
import SapphireDust from '../components/SapphireDust';
import RegulatoryDisclaimer from '../components/RegulatoryDisclaimer';

const Portfolio: React.FC = () => {
  const { portfolio, agentActivities, recentSignals, loading } = useTrading();
  const [showTradeEffect, setShowTradeEffect] = useState(false);
  const [tradeEffectType, setTradeEffectType] = useState<'buy' | 'sell' | 'signal'>('signal');
  const previousSignalsCount = useRef(0);

  const calculateTotalValue = () => {
    // Always calculate from agent allocations (bot trading capital only)
    if (portfolio?.agent_allocations) {
      return Object.values(portfolio.agent_allocations).reduce((sum: number, val: any) => sum + (val || 0), 0);
    }
    // Fallback to $3,000 (6 agents × $500 each)
    return 3000;
  };

  const totalValue = calculateTotalValue();
  const activeAgents = agentActivities.filter(a => a.status === 'active' || a.status === 'trading').length;
  const totalTrades = agentActivities.reduce((sum, a) => sum + (a.trading_count || 0), 0);

  // Trigger trade alert effect when new signals arrive
  useEffect(() => {
    if (recentSignals.length > previousSignalsCount.current && recentSignals.length > 0) {
      const latestSignal = recentSignals[0];
      const signalType = latestSignal.side?.toLowerCase() === 'buy' ? 'buy' : 
                        latestSignal.side?.toLowerCase() === 'sell' ? 'sell' : 'signal';
      setTradeEffectType(signalType);
      setShowTradeEffect(true);
    }
    previousSignalsCount.current = recentSignals.length;
  }, [recentSignals]);

  return (
    <Container maxWidth="xl" sx={{ py: 4, position: 'relative', minHeight: '100vh' }}>
      {/* Sapphire dust background effect */}
      <SapphireDust intensity={0.3} speed={0.3} size="small" enabled={true} />
      
      {/* Trade alert effect */}
      <TradeAlertEffect 
        trigger={showTradeEffect} 
        type={tradeEffectType}
        onComplete={() => setShowTradeEffect(false)}
      />

      {/* Professional Header - Bold and Clean */}
      <Box sx={{ mb: { xs: 3, md: 4 }, position: 'relative', zIndex: 1 }}>
        <Typography 
          variant="h1" 
          gutterBottom 
          sx={{ 
            fontWeight: 900,
            fontSize: { xs: '2rem', md: '3rem' },
            color: '#FFFFFF',
            mb: { xs: 1, md: 1.5 },
            lineHeight: 1.1,
          }}
        >
          Trading Portfolio
        </Typography>
        <Typography 
          variant="h6" 
          sx={{ 
            fontSize: { xs: '1rem', md: '1.125rem' },
            fontWeight: 500,
            maxWidth: '900px',
            lineHeight: 1.6,
            color: '#E2E8F0',
          }}
        >
          Real-time AI agent trading capital and performance metrics
        </Typography>
      </Box>

      {/* Regulatory Disclaimer */}
      <RegulatoryDisclaimer />

      {/* Portfolio Summary Cards - Bold and Clean */}
      <Grid container spacing={{ xs: 2, md: 3 }} sx={{ mb: { xs: 3, md: 4 }, position: 'relative', zIndex: 1 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            background: '#0A0A0F',
            border: '2px solid rgba(14, 165, 233, 0.4)',
            position: 'relative',
            overflow: 'hidden',
            transition: 'all 0.2s ease',
            '&:hover': {
              borderColor: '#0EA5E9',
              boxShadow: '0 8px 32px rgba(14, 165, 233, 0.4)',
              transform: 'translateY(-4px)',
            }
          }}>
            <DiamondSparkle count={3} duration={3000} size={15} enabled={true} color="#0ea5e9" />
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography variant="body1" sx={{ color: '#CBD5E1', mb: 1.5, fontSize: { xs: '0.9rem', md: '1rem' }, fontWeight: 600 }}>
                    Total Bot Trading Capital
                  </Typography>
                  <Typography variant="h2" sx={{ fontWeight: 900, color: '#0EA5E9', fontSize: { xs: '2.5rem', md: '3rem' }, lineHeight: 1 }}>
                    ${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            background: '#0A0A0F',
            border: '2px solid rgba(16, 185, 129, 0.4)',
            transition: 'all 0.2s ease',
            '&:hover': {
              borderColor: '#10B981',
              boxShadow: '0 8px 32px rgba(16, 185, 129, 0.4)',
              transform: 'translateY(-4px)',
            }
          }}>
            <CardContent>
              <Typography variant="body1" sx={{ color: '#CBD5E1', mb: 1.5, fontSize: { xs: '0.9rem', md: '1rem' }, fontWeight: 600 }}>
                Active Agents
              </Typography>
              <Typography variant="h2" sx={{ fontWeight: 900, color: '#10B981', fontSize: { xs: '2.5rem', md: '3rem' }, lineHeight: 1 }}>
                {activeAgents} / {agentActivities.length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            background: '#0A0A0F',
            border: '2px solid rgba(6, 182, 212, 0.4)',
            transition: 'all 0.2s ease',
            '&:hover': {
              borderColor: '#06B6D4',
              boxShadow: '0 8px 32px rgba(6, 182, 212, 0.4)',
              transform: 'translateY(-4px)',
            }
          }}>
            <CardContent>
              <Typography variant="body1" sx={{ color: '#CBD5E1', mb: 1.5, fontSize: { xs: '0.9rem', md: '1rem' }, fontWeight: 600 }}>
                Total Trades
              </Typography>
              <Typography variant="h2" sx={{ fontWeight: 900, color: '#06B6D4', fontSize: { xs: '2.5rem', md: '3rem' }, lineHeight: 1 }}>
                {totalTrades}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            background: '#0A0A0F',
            border: '2px solid rgba(245, 158, 11, 0.4)',
            transition: 'all 0.2s ease',
            '&:hover': {
              borderColor: '#F59E0B',
              boxShadow: '0 8px 32px rgba(245, 158, 11, 0.4)',
              transform: 'translateY(-4px)',
            }
          }}>
            <CardContent>
              <Typography variant="body1" sx={{ color: '#CBD5E1', mb: 1.5, fontSize: { xs: '0.9rem', md: '1rem' }, fontWeight: 600 }}>
                Trading Signals
              </Typography>
              <Typography variant="h2" sx={{ fontWeight: 900, color: '#F59E0B', fontSize: { xs: '2.5rem', md: '3rem' }, lineHeight: 1 }}>
                {recentSignals.length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Portfolio Chart */}
      <Box sx={{ mb: 4 }}>
        <PortfolioChart />
      </Box>

      {/* Agent Allocations */}
      {portfolio?.agent_allocations && (
        <Card sx={{ 
          background: '#0A0A0F',
          border: '2px solid rgba(255, 255, 255, 0.2)',
          mb: { xs: 3, md: 4 },
        }}>
          <CardContent sx={{ p: { xs: 2, md: 3 } }}>
            <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontSize: { xs: '1.25rem', md: '1.5rem' }, mb: 3, color: '#FFFFFF' }}>
              Agent Capital Allocations
            </Typography>
            <Divider sx={{ mb: 3, borderColor: 'rgba(255,255,255,0.2)', borderWidth: 1 }} />
            <Grid container spacing={{ xs: 2, md: 2 }}>
              {Object.entries(portfolio.agent_allocations).map(([agentId, allocation]: [string, any]) => {
                const agent = agentActivities.find(a => a.agent_id.includes(agentId) || a.agent_type === agentId);
                const percentage = totalValue > 0 ? (allocation / totalValue) * 100 : 0;
                return (
                  <Grid item xs={12} sm={6} md={4} key={agentId}>
                    <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.05)', borderRadius: 2 }}>
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {agent?.agent_name || agentId.replace(/-/g, ' ').replace(/\b\w/g, char => char.toUpperCase())}
                        </Typography>
                        <Chip
                          label={`$${allocation.toFixed(2)}`}
                          size="small"
                          sx={{ bgcolor: 'rgba(0, 212, 170, 0.2)', color: '#00d4aa', fontWeight: 600 }}
                        />
                      </Box>
                      <LinearProgress
                        variant="determinate"
                        value={percentage}
                        sx={{
                          height: 8,
                          borderRadius: 4,
                          bgcolor: 'rgba(255,255,255,0.1)',
                          '& .MuiLinearProgress-bar': { bgcolor: agent?.color || '#00d4aa' }
                        }}
                      />
                      <Typography variant="caption" color="textSecondary" sx={{ mt: 0.5, display: 'block' }}>
                        {percentage.toFixed(1)}% of portfolio
                      </Typography>
                    </Box>
                  </Grid>
                );
              })}
            </Grid>
          </CardContent>
        </Card>
      )}

      {/* Recent Trading Signals */}
      {recentSignals.length > 0 && (
        <Card sx={{ 
          background: '#0A0A0F',
          border: '2px solid rgba(255, 255, 255, 0.2)',
        }}>
          <CardContent sx={{ p: { xs: 2, md: 3 } }}>
            <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontSize: { xs: '1.25rem', md: '1.5rem' }, mb: 3, color: '#FFFFFF' }}>
              Recent Trading Signals
            </Typography>
            <Divider sx={{ mb: 3, borderColor: 'rgba(255,255,255,0.2)', borderWidth: 1 }} />
            <Grid container spacing={{ xs: 2, md: 2 }}>
              {recentSignals.slice(0, 6).map((signal, index) => (
                <Grid item xs={12} sm={6} md={4} key={index}>
                  <Box sx={{ 
                    p: 2, 
                    bgcolor: 'rgba(255,255,255,0.05)', 
                    borderRadius: 2,
                    position: 'relative',
                    overflow: 'hidden',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      bgcolor: 'rgba(255,255,255,0.08)',
                      transform: 'translateY(-2px)',
                      boxShadow: `0 4px 20px ${signal.side.toLowerCase() === 'buy' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                    }
                  }}>
                    {/* Diamond sparkle effect on signal cards */}
                    {index === 0 && <DiamondSparkle count={2} duration={2000} size={12} enabled={true} 
                      color={signal.side.toLowerCase() === 'buy' ? '#10b981' : '#ef4444'} />}
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {signal.symbol}
                      </Typography>
                      <Chip
                        label={signal.side.toUpperCase()}
                        size="small"
                        color={signal.side.toLowerCase() === 'buy' ? 'success' : 'error'}
                        sx={{ 
                          fontWeight: 600,
                          animation: index === 0 ? 'pulse 2s ease-in-out infinite' : 'none',
                          '@keyframes pulse': {
                            '0%, 100%': { opacity: 1, transform: 'scale(1)' },
                            '50%': { opacity: 0.8, transform: 'scale(1.05)' },
                          },
                        }}
                      />
                    </Box>
                    <Typography variant="body2" color="textSecondary">
                      Price: ${signal.price.toFixed(2)}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      Size: ${signal.notional.toFixed(2)}
                    </Typography>
                    <Box display="flex" alignItems="center" mt={1}>
                      <Typography variant="caption" color="textSecondary" sx={{ mr: 1 }}>
                        Confidence:
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={signal.confidence * 100}
                        sx={{
                          flexGrow: 1,
                          height: 6,
                          borderRadius: 3,
                          bgcolor: 'rgba(255,255,255,0.1)',
                          '& .MuiLinearProgress-bar': {
                            bgcolor: signal.confidence > 0.7 ? '#10b981' : signal.confidence > 0.5 ? '#f59e0b' : '#ef4444'
                          }
                        }}
                      />
                      <Typography variant="caption" sx={{ ml: 1, fontWeight: 600 }}>
                        {(signal.confidence * 100).toFixed(0)}%
                      </Typography>
                    </Box>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      )}
    </Container>
  );
};

export default Portfolio;

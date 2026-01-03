import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Button,
  Avatar,
  LinearProgress,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  Visibility,
  VisibilityOff,
} from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';

// Mock trading data for visualization
const generateMockTrades = () => {
  const agents = ['trend-momentum-agent', 'strategy-optimization-agent', 'financial-sentiment-agent', 'market-prediction-agent', 'volume-microstructure-agent', 'vpin-hft'];
  const trades = [];
  const now = Date.now();

  // Generate trades over the last 24 hours
  for (let i = 0; i < 50; i++) {
    const agent = agents[Math.floor(Math.random() * agents.length)];
    const timestamp = now - (Math.random() * 24 * 60 * 60 * 1000); // Random time in last 24h
    const pnl = (Math.random() - 0.5) * 100; // Random P&L between -50 and +50
    const size = Math.random() * 0.1 + 0.01; // Random size 0.01 to 0.11 BTC

    trades.push({
      id: `trade-${i}`,
      agent,
      timestamp,
      pnl,
      size,
      symbol: 'BTC/USDT',
    });
  }

  return trades.sort((a, b) => b.timestamp - a.timestamp);
};

const agentColors = {
  'trend-momentum-agent': '#06b6d4',
  'strategy-optimization-agent': '#8b5cf6',
  'financial-sentiment-agent': '#ef4444',
  'market-prediction-agent': '#f59e0b',
  'volume-microstructure-agent': '#ec4899',
  'vpin-hft': '#06b6d4'
};

const agentNames = {
  'trend-momentum-agent': 'Trend Momentum',
  'strategy-optimization-agent': 'Strategy Optimization',
  'financial-sentiment-agent': 'Financial Sentiment',
  'market-prediction-agent': 'Market Prediction',
  'volume-microstructure-agent': 'Volume Microstructure',
  'vpin-hft': 'VPIN HFT'
};

export const AdvancedAnalytics: React.FC = () => {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { portfolio: _portfolio } = useTrading();
  const [trades] = useState(generateMockTrades());
  const [showTrades, setShowTrades] = useState(true);
  const [selectedTimeframe, setSelectedTimeframe] = useState<'1H' | '4H' | '1D' | '7D'>('1D');


  // Calculate agent performance
  const agentPerformance = trades.reduce((acc, trade) => {
    if (!acc[trade.agent]) {
      acc[trade.agent] = {
        totalTrades: 0,
        totalPnL: 0,
        winRate: 0,
        bestTrade: -Infinity,
        worstTrade: Infinity,
        avgTrade: 0,
      };
    }

    acc[trade.agent].totalTrades++;
    acc[trade.agent].totalPnL += trade.pnl;
    acc[trade.agent].bestTrade = Math.max(acc[trade.agent].bestTrade, trade.pnl);
    acc[trade.agent].worstTrade = Math.min(acc[trade.agent].worstTrade, trade.pnl);

    const winningTrades = trades.filter(t => t.agent === trade.agent && t.pnl > 0).length;
    acc[trade.agent].winRate = (winningTrades / acc[trade.agent].totalTrades) * 100;
    acc[trade.agent].avgTrade = acc[trade.agent].totalPnL / acc[trade.agent].totalTrades;

    return acc;
  }, {} as Record<string, any>);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 700, mb: 1 }}>
        Quantum Portfolio Dynamics
      </Typography>
      <Typography variant="body1" color="textSecondary" sx={{ mb: 4 }}>
        Advanced performance visualization with multi-agent trade tracking and real-time P&L analytics.
      </Typography>

      {/* Trading Battle Royale Section */}
      <Card
        sx={{
          mb: 4,
          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(139, 92, 246, 0.2)',
          borderRadius: 3,
        }}
      >
        <CardContent sx={{ p: 4 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Box>
              <Typography
                variant="h5"
                sx={{
                  fontWeight: 700,
                  background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  mb: 1,
                }}
              >
                🎮 Trading Battle Royale
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Watch your AI agents compete! Each colored dot represents a trade execution. Hover over dots to see agent performance, trade sizes, and P&L.
              </Typography>
            </Box>
            <Tooltip title={showTrades ? "Hide agent trades" : "Show agent trades"}>
              <IconButton
                onClick={() => setShowTrades(!showTrades)}
                sx={{
                  bgcolor: showTrades ? 'primary.main' : 'rgba(255, 255, 255, 0.1)',
                  color: showTrades ? 'primary.contrastText' : 'text.secondary',
                  '&:hover': {
                    bgcolor: showTrades ? 'primary.dark' : 'rgba(255, 255, 255, 0.2)',
                  },
                }}
              >
                {showTrades ? <Visibility /> : <VisibilityOff />}
              </IconButton>
            </Tooltip>
          </Box>

          {/* Timeframe Selector */}
          <Box sx={{ display: 'flex', gap: 1, mb: 3 }}>
            {(['1H', '4H', '1D', '7D'] as const).map((timeframe) => (
              <Button
                key={timeframe}
                variant={selectedTimeframe === timeframe ? 'contained' : 'outlined'}
                size="small"
                onClick={() => setSelectedTimeframe(timeframe)}
                sx={{
                  minWidth: 60,
                  fontWeight: 600,
                  fontSize: '0.75rem',
                }}
              >
                {timeframe}
              </Button>
            ))}
          </Box>

          {/* Trading Visualization Chart */}
          <Box
            sx={{
              height: 400,
              bgcolor: 'rgba(0, 0, 0, 0.2)',
              borderRadius: 2,
              border: '1px solid rgba(148, 163, 184, 0.1)',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            {/* Grid lines */}
            <Box sx={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, opacity: 0.1 }}>
              {Array.from({ length: 10 }, (_, i) => (
                <Box
                  key={i}
                  sx={{
                    position: 'absolute',
                    left: 0,
                    right: 0,
                    top: `${i * 10}%`,
                    height: '1px',
                    bgcolor: 'rgba(255, 255, 255, 0.2)',
                  }}
                />
              ))}
              {Array.from({ length: 10 }, (_, i) => (
                <Box
                  key={`v-${i}`}
                  sx={{
                    position: 'absolute',
                    top: 0,
                    bottom: 0,
                    left: `${i * 10}%`,
                    width: '1px',
                    bgcolor: 'rgba(255, 255, 255, 0.2)',
                  }}
                />
              ))}
            </Box>

            {/* Trade dots */}
            {showTrades && trades.slice(0, 30).map((trade, index) => {
              const x = (index / 29) * 90 + 5; // Spread across chart width
              const y = 50 - (trade.pnl / 50) * 40; // Center around 50%, scale by P&L

              return (
                <Tooltip
                  key={trade.id}
                  title={
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {agentNames[trade.agent as keyof typeof agentNames]}
                      </Typography>
                      <Typography variant="caption" display="block">
                        Size: {trade.size.toFixed(4)} BTC
                      </Typography>
                      <Typography variant="caption" display="block">
                        P&L: {trade.pnl > 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                      </Typography>
                      <Typography variant="caption" display="block">
                        {new Date(trade.timestamp).toLocaleTimeString()}
                      </Typography>
                    </Box>
                  }
                  arrow
                >
                  <Box
                    sx={{
                      position: 'absolute',
                      left: `${x}%`,
                      top: `${y}%`,
                      width: trade.size * 20 + 4, // Size based on trade size
                      height: trade.size * 20 + 4,
                      borderRadius: '50%',
                      bgcolor: agentColors[trade.agent as keyof typeof agentColors],
                      border: '2px solid rgba(255, 255, 255, 0.3)',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                      boxShadow: `0 0 8px ${agentColors[trade.agent as keyof typeof agentColors]}50`,
                      '&:hover': {
                        transform: 'scale(1.5)',
                        boxShadow: `0 0 16px ${agentColors[trade.agent as keyof typeof agentColors]}80`,
                      },
                    }}
                  />
                </Tooltip>
              );
            })}

            {/* Price line simulation */}
            <Box
              sx={{
                position: 'absolute',
                bottom: 10,
                left: 10,
                right: 10,
                height: '2px',
                bgcolor: 'primary.main',
                opacity: 0.6,
              }}
            />

            {/* Y-axis labels */}
            <Typography
              variant="caption"
              sx={{
                position: 'absolute',
                left: 5,
                top: 5,
                color: 'text.secondary',
                fontSize: '0.7rem',
              }}
            >
              +$50
            </Typography>
            <Typography
              variant="caption"
              sx={{
                position: 'absolute',
                left: 5,
                top: '45%',
                color: 'text.secondary',
                fontSize: '0.7rem',
              }}
            >
              $0
            </Typography>
            <Typography
              variant="caption"
              sx={{
                position: 'absolute',
                left: 5,
                bottom: 5,
                color: 'text.secondary',
                fontSize: '0.7rem',
              }}
            >
              -$50
            </Typography>
          </Box>

          {/* Legend */}
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mt: 3 }}>
            {Object.entries(agentNames).map(([key, name]) => (
              <Box key={key} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Box
                  sx={{
                    width: 12,
                    height: 12,
                    borderRadius: '50%',
                    bgcolor: agentColors[key as keyof typeof agentColors],
                  }}
                />
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  {name}
                </Typography>
              </Box>
            ))}
          </Box>
        </CardContent>
      </Card>

      {/* Agent Performance Cards */}
      <Grid container spacing={3}>
        {Object.entries(agentPerformance).map(([agentId, stats]) => (
          <Grid item xs={12} md={6} lg={4} key={agentId}>
            <Card
              sx={{
                background: 'rgba(30, 41, 59, 0.6)',
                backdropFilter: 'blur(16px)',
                border: '1px solid rgba(148, 163, 184, 0.1)',
                borderRadius: 3,
              }}
            >
              <CardContent sx={{ p: 3 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                  <Avatar
                    sx={{
                      bgcolor: `${agentColors[agentId as keyof typeof agentColors]}20`,
                      border: `2px solid ${agentColors[agentId as keyof typeof agentColors]}`,
                      width: 40,
                      height: 40,
                    }}
                  >
                    {agentId === 'trend-momentum-agent' ? '🎯' :
                      agentId === 'strategy-optimization-agent' ? '🧠' :
                        agentId === 'financial-sentiment-agent' ? '💭' :
                          agentId === 'market-prediction-agent' ? '🔮' :
                            agentId === 'volume-microstructure-agent' ? '📊' : '⚡'}
                  </Avatar>
                  <Box>
                    <Typography variant="h6" sx={{ fontWeight: 600, fontSize: '0.9rem' }}>
                      {agentNames[agentId as keyof typeof agentNames]}
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      {stats.totalTrades} trades
                    </Typography>
                  </Box>
                </Box>

                <Box sx={{ mb: 2 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Total P&L</Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 600,
                        color: stats.totalPnL >= 0 ? 'success.main' : 'error.main'
                      }}
                    >
                      {stats.totalPnL >= 0 ? '+' : ''}${stats.totalPnL.toFixed(2)}
                    </Typography>
                  </Box>

                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Win Rate</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {stats.winRate.toFixed(1)}%
                    </Typography>
                  </Box>

                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Best Trade</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: 'success.main' }}>
                      +${stats.bestTrade.toFixed(2)}
                    </Typography>
                  </Box>

                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2">Avg Trade</Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 600,
                        color: stats.avgTrade >= 0 ? 'success.main' : 'error.main'
                      }}
                    >
                      {stats.avgTrade >= 0 ? '+' : ''}${stats.avgTrade.toFixed(2)}
                    </Typography>
                  </Box>
                </Box>

                <LinearProgress
                  variant="determinate"
                  value={stats.winRate}
                  sx={{
                    height: 6,
                    borderRadius: 3,
                    bgcolor: 'rgba(255, 255, 255, 0.1)',
                    '& .MuiLinearProgress-bar': {
                      bgcolor: agentColors[agentId as keyof typeof agentColors],
                      borderRadius: 3,
                    },
                  }}
                />
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

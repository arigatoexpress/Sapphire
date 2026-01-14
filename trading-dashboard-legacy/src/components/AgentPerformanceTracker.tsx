import React, { useMemo } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  Avatar,
  Tooltip,
  Divider,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Assessment,
  Speed,
  ShowChart,
  EmojiEvents,
  Whatshot,
} from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';
import { getDynamicAgentColor } from '../constants/dynamicAgentColors';

interface AgentPerformance {
  agent_id: string;
  agent_name: string;
  agent_type: string;
  color: string;
  trades: number;
  win_rate: number;
  total_pnl: number;
  avg_confidence: number;
  activity_score: number;
  positions: Array<{
    symbol: string;
    side: string;
    size: number;
    entry_price: number;
    current_price: number;
    pnl: number;
  }>;
}

const AgentPerformanceTracker: React.FC = () => {
  const { agentActivities, recentSignals, portfolio } = useTrading();

  // Calculate performance metrics for each agent
  const agentPerformance = useMemo<AgentPerformance[]>(() => {
    return agentActivities.map((agent) => {
      // Get agent-specific signals
      const agentSignals = recentSignals.filter(
        (s) => s.source?.toLowerCase().includes(agent.agent_type.replace(/-/g, ' '))
      );

      // Calculate performance metrics
      const trades = agent.trading_count || 0;
      const winRate = trades > 0 ? Math.min(0.7 + Math.random() * 0.2, 0.95) : 0; // Simulated 70-95%
      const totalPnl = trades * (Math.random() - 0.2) * 50; // Simulated P&L
      const avgConfidence = agentSignals.length > 0
        ? agentSignals.reduce((sum, s) => sum + (s.confidence || 0), 0) / agentSignals.length
        : agent.activity_score || 0.5;

      // Generate mock positions (in real app, this would come from backend)
      const positions = agentSignals.slice(0, 3).map((signal) => ({
        symbol: signal.symbol,
        side: signal.side || 'BUY',
        size: signal.notional || 100,
        entry_price: signal.price || 0,
        current_price: (signal.price || 0) * (1 + (Math.random() - 0.4) * 0.02), // ±2% variation
        pnl: (signal.notional || 0) * (Math.random() - 0.3) * 0.1, // Simulated P&L
      }));

      const colors = getDynamicAgentColor(
        agent.agent_type,
        agent.status,
        agent.activity_score,
        agent.communication_count > 0
      );

      return {
        agent_id: agent.agent_id,
        agent_name: agent.agent_name,
        agent_type: agent.agent_type,
        color: colors.primary,
        trades,
        win_rate: winRate,
        total_pnl: totalPnl,
        avg_confidence: avgConfidence,
        activity_score: agent.activity_score || 0,
        positions,
      };
    });
  }, [agentActivities, recentSignals]);

  // Sort by total P&L for leaderboard
  const sortedAgents = [...agentPerformance].sort((a, b) => b.total_pnl - a.total_pnl);

  const getAgentIcon = (agentType: string) => {
    switch (agentType) {
      case 'trend-momentum-agent': return '🎯';
      case 'strategy-optimization-agent': return '🧠';
      case 'financial-sentiment-agent': return '💭';
      case 'market-prediction-agent': return '🔮';
      case 'volume-microstructure-agent': return '📊';
      case 'vpin-hft': return '⚡';
      default: return '🤖';
    }
  };

  const getRankIcon = (rank: number) => {
    switch (rank) {
      case 0: return <EmojiEvents sx={{ fontSize: 20, color: '#ffd700' }} />;
      case 1: return <Whatshot sx={{ fontSize: 20, color: '#c0c0c0' }} />;
      case 2: return <Assessment sx={{ fontSize: 20, color: '#cd7f32' }} />;
      default: return null;
    }
  };

  return (
    <Paper
      elevation={0}
      sx={{
        background: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(24px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: 3,
        overflow: 'hidden',
        mb: 4,
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 3,
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(236, 72, 153, 0.1))',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          <Box
            sx={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 16px rgba(139, 92, 246, 0.3)',
            }}
          >
            <ShowChart sx={{ color: 'white', fontSize: 28 }} />
          </Box>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, color: '#FFFFFF', mb: 0.5 }}>
              Agent Performance Leaderboard
            </Typography>
            <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
              Compare AI agent trading performance in real-time
            </Typography>
          </Box>
        </Box>

        {/* Summary Stats */}
        <Grid container spacing={2}>
          <Grid item xs={4}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#8b5cf6', mb: 0.5 }}>
                {agentPerformance.reduce((sum, a) => sum + a.trades, 0)}
              </Typography>
              <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)' }}>
                Total Trades
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={4}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#10b981', mb: 0.5 }}>
                ${agentPerformance.reduce((sum, a) => sum + a.total_pnl, 0).toFixed(2)}
              </Typography>
              <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)' }}>
                Total P&L
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={4}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#06b6d4', mb: 0.5 }}>
                {(agentPerformance.reduce((sum, a) => sum + a.win_rate, 0) / agentPerformance.length * 100).toFixed(1)}%
              </Typography>
              <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)' }}>
                Avg Win Rate
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </Box>

      {/* Agent Performance Cards */}
      <Box sx={{ p: 3 }}>
        <Grid container spacing={3}>
          {sortedAgents.map((agent, index) => (
            <Grid item xs={12} md={6} key={agent.agent_id}>
              <Card
                sx={{
                  height: '100%',
                  background: `linear-gradient(135deg, ${agent.color}10, ${agent.color}05)`,
                  border: `2px solid ${agent.color}40`,
                  borderRadius: 2,
                  position: 'relative',
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    transform: 'translateY(-4px)',
                    borderColor: agent.color,
                    boxShadow: `0 8px 24px ${agent.color}30`,
                  },
                  ...(index < 3 && {
                    '&::before': {
                      content: '""',
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      right: 0,
                      height: 4,
                      background: `linear-gradient(90deg, ${agent.color}, transparent)`,
                    },
                  }),
                }}
              >
                <CardContent sx={{ p: 2.5 }}>
                  {/* Agent Header */}
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                    <Box sx={{ position: 'relative' }}>
                      <Avatar
                        sx={{
                          width: 48,
                          height: 48,
                          bgcolor: `${agent.color}20`,
                          border: `2px solid ${agent.color}`,
                          fontSize: '1.25rem',
                          boxShadow: `0 0 16px ${agent.color}40`,
                        }}
                      >
                        {getAgentIcon(agent.agent_type)}
                      </Avatar>
                      {index < 3 && (
                        <Box
                          sx={{
                            position: 'absolute',
                            top: -8,
                            right: -8,
                            width: 24,
                            height: 24,
                            borderRadius: '50%',
                            bgcolor: index === 0 ? '#ffd700' : index === 1 ? '#c0c0c0' : '#cd7f32',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            border: '2px solid #000',
                          }}
                        >
                          {getRankIcon(index)}
                        </Box>
                      )}
                    </Box>
                    <Box sx={{ flexGrow: 1 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="h6" sx={{ fontWeight: 700, color: '#FFFFFF', fontSize: '1rem' }}>
                          {agent.agent_name}
                        </Typography>
                        {index === 0 && (
                          <Chip
                            icon={<EmojiEvents />}
                            label="Leader"
                            size="small"
                            sx={{
                              height: 20,
                              fontSize: '0.65rem',
                              bgcolor: 'rgba(255, 215, 0, 0.2)',
                              color: '#ffd700',
                              border: '1px solid #ffd700',
                              fontWeight: 700,
                            }}
                          />
                        )}
                      </Box>
                      <Typography variant="caption" sx={{ color: agent.color, fontWeight: 600 }}>
                        Rank #{index + 1}
                      </Typography>
                    </Box>
                    <Chip
                      label={`${(agent.activity_score * 100).toFixed(0)}%`}
                      size="small"
                      sx={{
                        bgcolor: `${agent.color}20`,
                        color: agent.color,
                        border: `1px solid ${agent.color}40`,
                        fontWeight: 700,
                      }}
                    />
                  </Box>

                  {/* Performance Metrics */}
                  <Grid container spacing={2} sx={{ mb: 2 }}>
                    <Grid item xs={6}>
                      <Box>
                        <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)', display: 'block', mb: 0.5 }}>
                          Trades
                        </Typography>
                        <Typography variant="h6" sx={{ fontWeight: 700, color: '#FFFFFF', fontSize: '1.25rem' }}>
                          {agent.trades}
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6}>
                      <Box>
                        <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)', display: 'block', mb: 0.5 }}>
                          Win Rate
                        </Typography>
                        <Typography variant="h6" sx={{ fontWeight: 700, color: '#10b981', fontSize: '1.25rem' }}>
                          {(agent.win_rate * 100).toFixed(1)}%
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={12}>
                      <Box>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                          <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)' }}>
                            Total P&L
                          </Typography>
                          <Typography
                            variant="body2"
                            sx={{
                              fontWeight: 700,
                              color: agent.total_pnl >= 0 ? '#10b981' : '#ef4444',
                            }}
                          >
                            {agent.total_pnl >= 0 ? '+' : ''}${agent.total_pnl.toFixed(2)}
                          </Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(100, Math.abs(agent.total_pnl) / 10)}
                          sx={{
                            height: 6,
                            borderRadius: 3,
                            bgcolor: 'rgba(255, 255, 255, 0.1)',
                            '& .MuiLinearProgress-bar': {
                              bgcolor: agent.total_pnl >= 0 ? '#10b981' : '#ef4444',
                              borderRadius: 3,
                            },
                          }}
                        />
                      </Box>
                    </Grid>
                    <Grid item xs={12}>
                      <Box>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                          <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)' }}>
                            Avg Confidence
                          </Typography>
                          <Typography variant="caption" sx={{ color: agent.color, fontWeight: 600 }}>
                            {(agent.avg_confidence * 100).toFixed(0)}%
                          </Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={agent.avg_confidence * 100}
                          sx={{
                            height: 4,
                            borderRadius: 2,
                            bgcolor: 'rgba(255, 255, 255, 0.1)',
                            '& .MuiLinearProgress-bar': {
                              bgcolor: agent.color,
                              borderRadius: 2,
                            },
                          }}
                        />
                      </Box>
                    </Grid>
                  </Grid>

                  {/* Active Positions */}
                  {agent.positions.length > 0 && (
                    <>
                      <Divider sx={{ my: 2, borderColor: 'rgba(255, 255, 255, 0.1)' }} />
                      <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)', fontWeight: 600, mb: 1, display: 'block' }}>
                        Active Positions ({agent.positions.length})
                      </Typography>
                      <List dense sx={{ p: 0 }}>
                        {agent.positions.map((position, posIndex) => (
                          <ListItem
                            key={posIndex}
                            sx={{
                              p: 1,
                              mb: 0.5,
                              bgcolor: 'rgba(255, 255, 255, 0.03)',
                              borderRadius: 1,
                              border: `1px solid ${position.pnl >= 0 ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`,
                            }}
                          >
                            <ListItemAvatar>
                              <Box
                                sx={{
                                  width: 8,
                                  height: 8,
                                  borderRadius: '50%',
                                  bgcolor: position.side === 'BUY' ? '#10b981' : '#ef4444',
                                  boxShadow: `0 0 8px ${position.side === 'BUY' ? '#10b981' : '#ef4444'}`,
                                }}
                              />
                            </ListItemAvatar>
                            <ListItemText
                              primary={
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <Typography variant="body2" sx={{ fontWeight: 600, color: '#FFFFFF' }}>
                                    {position.symbol}
                                  </Typography>
                                  <Typography
                                    variant="caption"
                                    sx={{
                                      fontWeight: 700,
                                      color: position.pnl >= 0 ? '#10b981' : '#ef4444',
                                    }}
                                  >
                                    {position.pnl >= 0 ? '+' : ''}${position.pnl.toFixed(2)}
                                  </Typography>
                                </Box>
                              }
                              secondary={
                                <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)', fontSize: '0.7rem' }}>
                                  {position.side} • ${position.size.toFixed(0)} • ${position.entry_price.toFixed(4)}
                                </Typography>
                              }
                            />
                          </ListItem>
                        ))}
                      </List>
                    </>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>
    </Paper>
  );
};

export default AgentPerformanceTracker;

import React, { useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  LinearProgress,
  Chip,
  Tooltip,
  IconButton,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Assessment,
  ShowChart,
  Refresh,
  Timeline,
  BarChart,
} from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  LineChart,
  Line,
} from 'recharts';

interface AgentPerformance {
  agent_id: string;
  agent_name: string;
  agent_type: string;
  color: string;
  trades: number;
  winRate: number;
  avgPnl: number;
  totalPnl: number;
  activityScore: number;
  communicationCount: number;
  capitalAllocation: number;
  positions: number;
}

const AgentPerformanceComparison: React.FC = () => {
  const { agentActivities, portfolio, recentSignals } = useTrading();
  const [viewMode, setViewMode] = useState<'cards' | 'chart' | 'radar'>('cards');
  const [sortBy, setSortBy] = useState<'trades' | 'pnl' | 'activity' | 'capital'>('pnl');

  // Calculate performance metrics for each agent
  const calculatePerformance = (): AgentPerformance[] => {
    return agentActivities.map((agent) => {
      // Calculate win rate (simulated based on activity score)
      const winRate = Math.min(0.95, 0.5 + agent.activity_score * 0.45);

      // Calculate average P&L per trade (simulated)
      const avgPnl = (Math.random() - 0.2) * 50; // Slight positive bias

      // Total P&L based on trade count
      const totalPnl = avgPnl * (agent.trading_count || 0);

      // Get capital allocation
      const capital = portfolio?.agent_allocations?.[agent.agent_id] ||
                      portfolio?.agent_allocations?.[agent.agent_type] || 500;

      // Count positions from recent signals
      const positions = recentSignals.filter(s =>
        s.source?.toLowerCase().includes(agent.agent_type) ||
        agent.agent_id.includes(s.source?.toLowerCase() || '')
      ).length;

      return {
        agent_id: agent.agent_id,
        agent_name: agent.agent_name,
        agent_type: agent.agent_type,
        color: agent.color,
        trades: agent.trading_count || 0,
        winRate,
        avgPnl,
        totalPnl,
        activityScore: agent.activity_score,
        communicationCount: agent.communication_count || 0,
        capitalAllocation: capital,
        positions,
      };
    });
  };

  const performances = calculatePerformance();

  // Sort performances
  const sortedPerformances = [...performances].sort((a, b) => {
    switch (sortBy) {
      case 'trades': return b.trades - a.trades;
      case 'pnl': return b.totalPnl - a.totalPnl;
      case 'activity': return b.activityScore - a.activityScore;
      case 'capital': return b.capitalAllocation - a.capitalAllocation;
      default: return b.totalPnl - a.totalPnl;
    }
  });

  // Prepare chart data
  const chartData = sortedPerformances.map(p => ({
    name: p.agent_name.replace(' Agent', ''),
    trades: p.trades,
    pnl: p.totalPnl,
    winRate: p.winRate * 100,
    activity: p.activityScore * 10,
    capital: p.capitalAllocation / 100,
  }));

  const radarData = sortedPerformances.map(p => ({
    agent: p.agent_name.replace(' Agent', ''),
    trades: p.trades,
    winRate: p.winRate * 100,
    pnl: Math.max(0, p.totalPnl + 100), // Normalize for radar chart
    activity: p.activityScore * 100,
    communication: Math.min(100, p.communicationCount * 2),
  }));

  const COLORS = sortedPerformances.map(p => p.color);

  const formatCurrency = (value: number) => {
    if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
    return `$${value.toFixed(2)}`;
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
          background: 'linear-gradient(135deg, rgba(14, 165, 233, 0.1), rgba(139, 92, 246, 0.1))',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Box
              sx={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #0ea5e9, #8b5cf6)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 16px rgba(14, 165, 233, 0.3)',
              }}
            >
              <ShowChart sx={{ color: 'white', fontSize: 24 }} />
            </Box>
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 700, color: '#FFFFFF', mb: 0.5 }}>
                Agent Performance Comparison
              </Typography>
              <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                Side-by-side comparison of AI agent trading performance
              </Typography>
            </Box>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <ToggleButtonGroup
              value={viewMode}
              exclusive
              onChange={(_, value) => value && setViewMode(value)}
              size="small"
            >
              <Tooltip title="Card View" arrow>
                <ToggleButton value="cards">
                  <BarChart sx={{ fontSize: 16 }} />
                </ToggleButton>
              </Tooltip>
              <Tooltip title="Bar Chart" arrow>
                <ToggleButton value="chart">
                  <Timeline sx={{ fontSize: 16 }} />
                </ToggleButton>
              </Tooltip>
              <Tooltip title="Radar Chart" arrow>
                <ToggleButton value="radar">
                  <Assessment sx={{ fontSize: 16 }} />
                </ToggleButton>
              </Tooltip>
            </ToggleButtonGroup>
            <ToggleButtonGroup
              value={sortBy}
              exclusive
              onChange={(_, value) => value && setSortBy(value)}
              size="small"
            >
              <Tooltip title="Sort by Trades" arrow>
                <ToggleButton value="trades">Trades</ToggleButton>
              </Tooltip>
              <Tooltip title="Sort by P&L" arrow>
                <ToggleButton value="pnl">P&L</ToggleButton>
              </Tooltip>
              <Tooltip title="Sort by Activity" arrow>
                <ToggleButton value="activity">Activity</ToggleButton>
              </Tooltip>
              <Tooltip title="Sort by Capital" arrow>
                <ToggleButton value="capital">Capital</ToggleButton>
              </Tooltip>
            </ToggleButtonGroup>
          </Box>
        </Box>
      </Box>

      {/* Performance Cards View */}
      {viewMode === 'cards' && (
        <Box sx={{ p: 3 }}>
          <Grid container spacing={3}>
            {sortedPerformances.map((perf, index) => (
              <Grid item xs={12} sm={6} md={4} key={perf.agent_id}>
                <Card
                  sx={{
                    height: '100%',
                    background: `linear-gradient(135deg, ${perf.color}15, ${perf.color}05)`,
                    border: `2px solid ${perf.color}40`,
                    borderRadius: 3,
                    transition: 'all 0.3s ease',
                    position: 'relative',
                    overflow: 'hidden',
                    '&:hover': {
                      transform: 'translateY(-4px)',
                      borderColor: perf.color,
                      boxShadow: `0 8px 24px ${perf.color}30`,
                    },
                  }}
                >
                  {/* Rank Badge */}
                  {index < 3 && (
                    <Box
                      sx={{
                        position: 'absolute',
                        top: 8,
                        right: 8,
                        width: 32,
                        height: 32,
                        borderRadius: '50%',
                        bgcolor: index === 0 ? '#ffd700' : index === 1 ? '#c0c0c0' : '#cd7f32',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        zIndex: 1,
                        boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                      }}
                    >
                      <Typography
                        variant="caption"
                        sx={{
                          fontWeight: 900,
                          fontSize: '0.9rem',
                          color: index === 0 ? '#000' : '#fff',
                        }}
                      >
                        {index + 1}
                      </Typography>
                    </Box>
                  )}

                  {/* Agent Color Dot */}
                  <Box
                    sx={{
                      position: 'absolute',
                      top: 12,
                      left: 12,
                      width: 12,
                      height: 12,
                      borderRadius: '50%',
                      bgcolor: perf.color,
                      boxShadow: `0 0 12px ${perf.color}`,
                      animation: 'pulse 2s ease-in-out infinite',
                      '@keyframes pulse': {
                        '0%, 100%': { opacity: 1, transform: 'scale(1)' },
                        '50%': { opacity: 0.7, transform: 'scale(1.2)' },
                      },
                    }}
                  />

                  <CardContent sx={{ p: 3, pt: 4 }}>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        color: perf.color,
                        mb: 2,
                        fontSize: '1.1rem',
                      }}
                    >
                      {perf.agent_name}
                    </Typography>

                    {/* Key Metrics */}
                    <Box sx={{ mb: 2 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                          Total P&L
                        </Typography>
                        <Typography
                          variant="h6"
                          sx={{
                            fontWeight: 700,
                            color: perf.totalPnl >= 0 ? '#10b981' : '#ef4444',
                          }}
                        >
                          {perf.totalPnl >= 0 ? '+' : ''}{formatCurrency(perf.totalPnl)}
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                          Trades
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: '#FFFFFF' }}>
                          {perf.trades}
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                          Win Rate
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: '#FFFFFF' }}>
                          {(perf.winRate * 100).toFixed(1)}%
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                          Positions
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: '#FFFFFF' }}>
                          {perf.positions}
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                          Capital
                        </Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: '#FFFFFF' }}>
                          {formatCurrency(perf.capitalAllocation)}
                        </Typography>
                      </Box>
                    </Box>

                    {/* Activity Score */}
                    <Box sx={{ mb: 2 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                        <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)' }}>
                          Activity Score
                        </Typography>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: perf.color }}>
                          {(perf.activityScore * 10).toFixed(1)}/10
                        </Typography>
                      </Box>
                      <LinearProgress
                        variant="determinate"
                        value={perf.activityScore * 100}
                        sx={{
                          height: 6,
                          borderRadius: 3,
                          bgcolor: 'rgba(255, 255, 255, 0.1)',
                          '& .MuiLinearProgress-bar': {
                            bgcolor: perf.color,
                            borderRadius: 3,
                          },
                        }}
                      />
                    </Box>

                    {/* Communication */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                      <Chip
                        icon={<Assessment sx={{ fontSize: 14 }} />}
                        label={`${perf.communicationCount} Messages`}
                        size="small"
                        sx={{
                          height: 24,
                          fontSize: '0.7rem',
                          bgcolor: 'rgba(139, 92, 246, 0.1)',
                          color: '#8b5cf6',
                          border: '1px solid rgba(139, 92, 246, 0.3)',
                        }}
                      />
                      {perf.avgPnl !== undefined && (
                        <Chip
                          label={`Avg: ${formatCurrency(perf.avgPnl)}`}
                          size="small"
                          sx={{
                            height: 24,
                            fontSize: '0.7rem',
                            bgcolor: `${perf.totalPnl >= 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)'}`,
                            color: perf.totalPnl >= 0 ? '#10b981' : '#ef4444',
                            border: `1px solid ${perf.totalPnl >= 0 ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                          }}
                        />
                      )}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {/* Bar Chart View */}
      {viewMode === 'chart' && (
        <Box sx={{ p: 3 }}>
          <Box sx={{ height: 400, mb: 2 }}>
            <ResponsiveContainer width="100%" height="100%">
              <RechartsBarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis
                  dataKey="name"
                  angle={-45}
                  textAnchor="end"
                  height={100}
                  stroke="#888"
                  fontSize={12}
                />
                <YAxis stroke="#888" fontSize={12} />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    borderRadius: 8,
                  }}
                />
                <Legend />
                <Bar dataKey="trades" fill="#06b6d4" name="Trades" />
                <Bar dataKey="pnl" fill="#10b981" name="Total P&L ($)" />
                <Bar dataKey="winRate" fill="#f59e0b" name="Win Rate (%)" />
              </RechartsBarChart>
            </ResponsiveContainer>
          </Box>
        </Box>
      )}

      {/* Radar Chart View */}
      {viewMode === 'radar' && (
        <Box sx={{ p: 3 }}>
          <Box sx={{ height: 500, mb: 2 }}>
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="#333" />
                <PolarAngleAxis dataKey="agent" stroke="#888" fontSize={12} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} stroke="#888" />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    borderRadius: 8,
                  }}
                />
                <Legend />
                {sortedPerformances.map((perf, index) => (
                  <Radar
                    key={perf.agent_id}
                    name={perf.agent_name.replace(' Agent', '')}
                    dataKey="trades"
                    stroke={perf.color}
                    fill={perf.color}
                    fillOpacity={0.6}
                  />
                ))}
              </RadarChart>
            </ResponsiveContainer>
          </Box>
        </Box>
      )}
    </Paper>
  );
};

export default AgentPerformanceComparison;

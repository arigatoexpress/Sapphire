import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  ToggleButton,
  ToggleButtonGroup,
  Chip,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Timeline,
  BarChart,
  Download,
  Refresh,
} from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  Bar,
  BarChart as RechartsBarChart,
  ScatterChart,
  Scatter,
  Cell,
} from 'recharts';

const PortfolioChart: React.FC = () => {
  const { portfolio, loading, refreshData, agentActivities } = useTrading();
  const [chartType, setChartType] = useState<'line' | 'area' | 'bar'>('area');
  const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d' | '30d'>('24h');
  const [showAgentTrades, setShowAgentTrades] = useState(true);

  // Mock portfolio performance data - in real app, this would come from backend
  const generatePortfolioData = () => {
    const data = [];
    const points = timeRange === '1h' ? 60 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 : 30;

    let currentValue = portfolio?.portfolio_value || 10000;

    // Generate data chronologically: oldest (past) to newest (present)
    // Chart will display left-to-right: past → present
    for (let i = points; i >= 0; i--) {
      const change = (Math.random() - 0.48) * 50; // Slight upward bias
      currentValue += change;

      data.push({
        time: timeRange === '1h' ? `${i}m ago` :
          timeRange === '24h' ? `${i}h ago` :
            timeRange === '7d' ? `Day ${points - i + 1}` :
              `Day ${points - i + 1}`,
        value: Math.max(0, currentValue),
        pnl: currentValue - (portfolio?.portfolio_value || 10000),
        change: change,
      });
    }

    return data;
  };

  const portfolioData = generatePortfolioData();

  // Generate agent trade data for visualization
  const generateAgentTradeData = () => {
    const agentColors = {
      deepseek: '#06b6d4',
      qwen: '#8b5cf6',
      fingpt: '#ef4444',
      lagllama: '#f59e0b',
      vpin: '#ec4899',
      freqtrade: '#3b82f6',
      hummingbot: '#10b981'
    };

    const trades: any[] = [];
    const points = timeRange === '1h' ? 60 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 : 30;

    // Generate trades for each agent
    Object.entries(agentColors).forEach(([agentType, color]) => {
      const agentActivity = agentActivities.find(a => a.agent_type === agentType);
      const tradeCount = agentActivity?.trading_count || Math.floor(Math.random() * 5) + 1;

      for (let i = 0; i < tradeCount; i++) {
        const timeIndex = Math.floor(Math.random() * points);
        const portfolioPoint = portfolioData[timeIndex];
        if (portfolioPoint) {
          const priceOffset = (Math.random() - 0.5) * 100; // Random price variation
          const tradeSize = Math.random() * 100 + 50; // Trade size 50-150

          trades.push({
            time: portfolioPoint.time,
            price: portfolioPoint.value + priceOffset,
            size: tradeSize,
            agent: agentType,
            color: color,
            pnl: (Math.random() - 0.4) * 50, // Random P&L with slight positive bias
            timestamp: portfolioPoint.time,
          });
        }
      }
    });

    return trades;
  };

  const agentTradeData = generateAgentTradeData();

  const formatValue = (value: number) => {
    if (value >= 1000000) {
      return `$${(value / 1000000).toFixed(2)}M`;
    } else if (value >= 1000) {
      return `$${(value / 1000).toFixed(1)}K`;
    }
    return `$${value.toFixed(0)}`;
  };

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <Box
          sx={{
            bgcolor: 'background.paper',
            p: 2,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2,
            boxShadow: '0 8px 16px rgba(0,0,0,0.3)',
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
            {label}
          </Typography>
          <Typography variant="body2" sx={{ color: 'primary.main', fontWeight: 600 }}>
            Value: {formatValue(data.value)}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              color: data.pnl >= 0 ? 'success.main' : 'error.main',
              fontWeight: 600
            }}
          >
            P&L: {data.pnl >= 0 ? '+' : ''}{formatValue(data.pnl)}
          </Typography>
        </Box>
      );
    }
    return null;
  };

  const renderChart = () => {
    const commonProps = {
      data: portfolioData,
      margin: { top: 20, right: 30, left: 20, bottom: 20 },
    };

    const renderAgentTrades = () => {
      if (!showAgentTrades) return null;

      return (
        <ScatterChart
          data={agentTradeData}
          margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
          width={0}
          height={0}
        >
          <XAxis
            type="category"
            dataKey="time"
            hide
          />
          <YAxis
            type="number"
            dataKey="price"
            hide
          />
          <Scatter
            dataKey="price"
            fill="#8884d8"
          >
            {agentTradeData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Scatter>
          <RechartsTooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                const data = payload[0].payload;
                return (
                  <Box
                    sx={{
                      bgcolor: 'background.paper',
                      p: 2,
                      border: '1px solid',
                      borderColor: 'divider',
                      borderRadius: 2,
                      boxShadow: '0 8px 16px rgba(0,0,0,0.3)',
                    }}
                  >
                    <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                      Agent Trade - {data.agent.toUpperCase()}
                    </Typography>
                    <Typography variant="body2" sx={{ color: data.color, fontWeight: 600 }}>
                      Price: {formatValue(data.price)}
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                      Size: ${data.size.toFixed(0)}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: data.pnl >= 0 ? 'success.main' : 'error.main',
                        fontWeight: 600
                      }}
                    >
                      P&L: {data.pnl >= 0 ? '+' : ''}${data.pnl.toFixed(2)}
                    </Typography>
                  </Box>
                );
              }
              return null;
            }}
          />
        </ScatterChart>
      );
    };

    switch (chartType) {
      case 'line':
        return (
          <>
            <LineChart {...commonProps}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="time" stroke="#888" fontSize={12} />
              <YAxis tickFormatter={formatValue} stroke="#888" fontSize={12} />
              <RechartsTooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#00d4aa"
                strokeWidth={3}
                dot={{ fill: '#00d4aa', strokeWidth: 2, r: 4 }}
                activeDot={{ r: 6, stroke: '#00d4aa', strokeWidth: 2, fill: '#fff' }}
              />
            </LineChart>
            {renderAgentTrades()}
          </>
        );

      case 'area':
        return (
          <>
            <AreaChart {...commonProps}>
              <defs>
                <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00d4aa" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00d4aa" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="time" stroke="#888" fontSize={12} />
              <YAxis tickFormatter={formatValue} stroke="#888" fontSize={12} />
              <RechartsTooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#00d4aa"
                strokeWidth={2}
                fill="url(#portfolioGradient)"
              />
            </AreaChart>
            {renderAgentTrades()}
          </>
        );

      case 'bar':
        return (
          <>
            <RechartsBarChart {...commonProps}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="time" stroke="#888" fontSize={12} />
              <YAxis tickFormatter={formatValue} stroke="#888" fontSize={12} />
              <RechartsTooltip content={<CustomTooltip />} />
              <Bar
                dataKey="value"
                fill="#00d4aa"
                radius={[4, 4, 0, 0]}
              />
            </RechartsBarChart>
            {renderAgentTrades()}
          </>
        );

      default:
        return (
          <AreaChart {...commonProps}>
            <defs>
              <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00d4aa" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#00d4aa" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey="time" stroke="#888" fontSize={12} />
            <YAxis tickFormatter={formatValue} stroke="#888" fontSize={12} />
            <RechartsTooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#00d4aa"
              strokeWidth={2}
              fill="url(#portfolioGradient)"
            />
          </AreaChart>
        );
    }
  };

  const calculatePerformance = () => {
    if (portfolioData.length < 2) return { change: 0, changePercent: 0 };

    const first = portfolioData[0].value;
    const last = portfolioData[portfolioData.length - 1].value;
    const change = last - first;
    const changePercent = (change / first) * 100;

    return { change, changePercent };
  };

  const performance = calculatePerformance();

  return (
    <Card sx={{ mb: 4 }}>
      <CardContent sx={{ p: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={3}>
          <Box>
            <Box display="flex" alignItems="center" gap={3} mb={1}>
              <Box
                sx={{
                  width: 60,
                  height: 60,
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #00d4aa, #06b6d4)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 8px 32px rgba(0, 212, 170, 0.3)',
                  position: 'relative',
                  '&::before': {
                    content: '""',
                    position: 'absolute',
                    top: -2,
                    left: -2,
                    right: -2,
                    bottom: -2,
                    borderRadius: '50%',
                    background: 'linear-gradient(45deg, #00d4aa, #06b6d4, #10b981)',
                    zIndex: -1,
                    opacity: 0.3,
                    animation: 'rotate 10s linear infinite',
                  },
                  '@keyframes rotate': {
                    '0%': { transform: 'rotate(0deg)' },
                    '100%': { transform: 'rotate(360deg)' },
                  },
                }}
              >
                <Timeline sx={{ fontSize: 28, color: 'white' }} />
              </Box>
              <Box>
                <Typography
                  variant="h4"
                  sx={{
                    fontWeight: 800,
                    background: 'linear-gradient(135deg, #00d4aa, #06b6d4, #10b981)',
                    backgroundClip: 'text',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    mb: 1,
                  }}
                >
                  💎 Quantum Portfolio Dynamics
                </Typography>
                <Typography variant="body1" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                  Advanced performance visualization with multi-agent trade tracking and real-time P&L analytics.
                </Typography>
              </Box>
            </Box>
            <Typography
              variant="body2"
              sx={{
                color: 'text.secondary',
                mb: 2,
                lineHeight: 1.5,
                maxWidth: '600px'
              }}
            >
              <strong>🎮 Trading Battle Royale:</strong> Watch your AI agents compete! Each colored dot represents a trade execution.
              Hover over dots to see agent performance, trade sizes, and P&L. Toggle the 🎯 button to show/hide agent trades!
            </Typography>
            <Box display="flex" alignItems="center" gap={2}>
              <Typography variant="h3" sx={{ fontWeight: 700, color: 'primary.main' }}>
                {formatValue(portfolio?.portfolio_value || 0)}
              </Typography>
              <Box display="flex" alignItems="center">
                {performance.changePercent >= 0 ? (
                  <TrendingUp sx={{ color: 'success.main', mr: 0.5 }} />
                ) : (
                  <TrendingDown sx={{ color: 'error.main', mr: 0.5 }} />
                )}
                <Typography
                  variant="h6"
                  sx={{
                    color: performance.changePercent >= 0 ? 'success.main' : 'error.main',
                    fontWeight: 600
                  }}
                >
                  {performance.changePercent >= 0 ? '+' : ''}{performance.changePercent.toFixed(2)}%
                </Typography>
              </Box>
            </Box>
          </Box>

          <Box display="flex" gap={2} alignItems="center">
            <ToggleButtonGroup
              value={timeRange}
              exclusive
              onChange={(_, value) => value && setTimeRange(value)}
              size="small"
            >
              <ToggleButton value="1h">1H</ToggleButton>
              <ToggleButton value="24h">24H</ToggleButton>
              <ToggleButton value="7d">7D</ToggleButton>
              <ToggleButton value="30d">30D</ToggleButton>
            </ToggleButtonGroup>

            <ToggleButtonGroup
              value={chartType}
              exclusive
              onChange={(_, value) => value && setChartType(value)}
              size="small"
            >
              <ToggleButton value="line">
                <Timeline sx={{ fontSize: 16 }} />
              </ToggleButton>
              <ToggleButton value="area">
                <BarChart sx={{ fontSize: 16 }} />
              </ToggleButton>
              <ToggleButton value="bar">
                <BarChart sx={{ fontSize: 16 }} />
              </ToggleButton>
            </ToggleButtonGroup>

            <Tooltip title={showAgentTrades ? "Hide Agent Trades" : "Show Agent Trades"} arrow>
              <ToggleButton
                value="trades"
                selected={showAgentTrades}
                onChange={() => setShowAgentTrades(!showAgentTrades)}
                size="small"
                sx={{
                  border: '1px solid',
                  borderColor: showAgentTrades ? 'primary.main' : 'divider',
                  '&.Mui-selected': {
                    bgcolor: 'primary.main',
                    color: 'primary.contrastText',
                    '&:hover': {
                      bgcolor: 'primary.dark',
                    },
                  },
                }}
              >
                🎯
              </ToggleButton>
            </Tooltip>

            <Tooltip title="Refresh Data" arrow>
              <IconButton onClick={refreshData} disabled={loading}>
                <Refresh sx={{ fontSize: 20 }} />
              </IconButton>
            </Tooltip>

            <Tooltip title="Export Chart" arrow>
              <IconButton>
                <Download sx={{ fontSize: 20 }} />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        <Box sx={{ height: 400, mb: 2 }}>
          <ResponsiveContainer width="100%" height="100%">
            {renderChart()}
          </ResponsiveContainer>
        </Box>

        {/* Performance Summary */}
        <Box display="flex" gap={2} flexWrap="wrap">
          <Chip
            label={`Best: ${formatValue(Math.max(...portfolioData.map(d => d.value)))}`}
            sx={{
              bgcolor: 'success.main',
              color: 'success.contrastText',
              fontWeight: 600,
            }}
          />
          <Chip
            label={`Worst: ${formatValue(Math.min(...portfolioData.map(d => d.value)))}`}
            sx={{
              bgcolor: 'error.main',
              color: 'error.contrastText',
              fontWeight: 600,
            }}
          />
          <Chip
            label={`Volatility: ${((Math.max(...portfolioData.map(d => d.value)) - Math.min(...portfolioData.map(d => d.value))) / portfolioData[0].value * 100).toFixed(1)}%`}
            sx={{
              bgcolor: 'warning.main',
              color: 'warning.contrastText',
              fontWeight: 600,
            }}
          />
        </Box>
      </CardContent>
    </Card>
  );
};

export default PortfolioChart;

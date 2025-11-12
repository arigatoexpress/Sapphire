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
  PieChart,
  Pie,
  Cell,
} from 'recharts';

const PortfolioChart: React.FC = () => {
  const { portfolio, agentActivities, loading, refreshData } = useTrading();
  const [chartType, setChartType] = useState<'line' | 'area' | 'bar'>('area');
  const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d' | '30d'>('24h');

  // Mock portfolio performance data - in real app, this would come from backend
  const generatePortfolioData = () => {
    const data = [];
    const points = timeRange === '1h' ? 60 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 : 30;
    const multiplier = timeRange === '1h' ? 1 : timeRange === '24h' ? 60 : timeRange === '7d' ? 1440 : 10080;

    let currentValue = portfolio?.portfolio_value || 10000;

    for (let i = points; i >= 0; i--) {
      const change = (Math.random() - 0.48) * 50; // Slight upward bias
      currentValue += change;

      data.push({
        time: timeRange === '1h' ? `${points - i}m ago` :
              timeRange === '24h' ? `${points - i}h ago` :
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

    switch (chartType) {
      case 'line':
        return (
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
        );

      case 'area':
        return (
          <AreaChart {...commonProps}>
            <defs>
              <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00d4aa" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#00d4aa" stopOpacity={0}/>
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

      case 'bar':
        return (
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
        );

      default:
        return null;
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
            <Box display="flex" alignItems="center" gap={2} mb={1}>
              <Timeline sx={{ fontSize: 28, color: 'primary.main' }} />
      <Typography variant="h5" sx={{ fontWeight: 600 }}>
        Portfolio Value
      </Typography>
            </Box>
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

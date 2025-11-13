import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  LinearProgress,
  Chip,
  IconButton,
  Tooltip,
  CircularProgress,
  useTheme,
  Paper,
  Avatar,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Assessment,
  Analytics,
  Timeline,
  PieChart,
  BarChart,
  ScatterPlot,
  Refresh,
  Info,
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart as RechartsBarChart,
  Bar,
  ScatterChart,
  Scatter,
  Cell,
  PieChart as RechartsPieChart,
  Pie,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from 'recharts';

interface RiskMetrics {
  sharpeRatio: number;
  sortinoRatio: number;
  maxDrawdown: number;
  valueAtRisk: number;
  expectedShortfall: number;
  volatility: number;
  beta: number;
  alpha: number;
}

interface PerformanceData {
  date: string;
  portfolio: number;
  benchmark: number;
  sharpe: number;
  drawdown: number;
}

interface CorrelationData {
  asset: string;
  correlation: number;
  volatility: number;
}

const AdvancedAnalytics: React.FC = () => {
  const theme = useTheme();
  const [loading, setLoading] = useState(false);
  const [selectedTimeframe, setSelectedTimeframe] = useState<'1W' | '1M' | '3M' | '6M' | '1Y'>('1M');
  const [lastUpdate, setLastUpdate] = useState(new Date());

  // Mock advanced analytics data
  const [riskMetrics] = useState<RiskMetrics>({
    sharpeRatio: 2.34,
    sortinoRatio: 3.12,
    maxDrawdown: -12.8,
    valueAtRisk: -8.5,
    expectedShortfall: -11.2,
    volatility: 18.7,
    beta: 0.87,
    alpha: 5.3,
  });

  const [performanceData] = useState<PerformanceData[]>([
    { date: '2024-01', portfolio: 100, benchmark: 100, sharpe: 2.1, drawdown: 0 },
    { date: '2024-02', portfolio: 108, benchmark: 103, sharpe: 2.3, drawdown: -2 },
    { date: '2024-03', portfolio: 115, benchmark: 106, sharpe: 2.4, drawdown: -1 },
    { date: '2024-04', portfolio: 122, benchmark: 109, sharpe: 2.2, drawdown: 0 },
    { date: '2024-05', portfolio: 118, benchmark: 112, sharpe: 2.1, drawdown: -3.5 },
    { date: '2024-06', portfolio: 135, benchmark: 115, sharpe: 2.5, drawdown: 0 },
  ]);

  const [correlationData] = useState<CorrelationData[]>([
    { asset: 'BTC', correlation: 0.85, volatility: 65 },
    { asset: 'ETH', correlation: 0.72, volatility: 58 },
    { asset: 'SOL', correlation: 0.68, volatility: 72 },
    { asset: 'ADA', correlation: 0.45, volatility: 48 },
    { asset: 'DOT', correlation: 0.52, volatility: 55 },
    { asset: 'LINK', correlation: 0.38, volatility: 42 },
  ]);

  const [factorData] = useState([
    { factor: 'Momentum', exposure: 0.25, contribution: 2.1 },
    { factor: 'Value', exposure: -0.15, contribution: -0.8 },
    { factor: 'Size', exposure: 0.35, contribution: 1.9 },
    { factor: 'Quality', exposure: 0.45, contribution: 3.2 },
    { factor: 'Volatility', exposure: -0.28, contribution: -1.5 },
  ]);

  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setLastUpdate(new Date());
    }, 2000);
  };

  const getRiskColor = (value: number, type: string) => {
    switch (type) {
      case 'ratio':
        return value >= 2 ? '#10b981' : value >= 1.5 ? '#f59e0b' : '#ef4444';
      case 'drawdown':
        return value > -10 ? '#10b981' : value > -20 ? '#f59e0b' : '#ef4444';
      case 'volatility':
        return value <= 20 ? '#10b981' : value <= 35 ? '#f59e0b' : '#ef4444';
      default:
        return '#6b7280';
    }
  };

  const formatPercentage = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
  const formatDecimal = (value: number, decimals: number = 2) => value.toFixed(decimals);

  return (
    <Box sx={{ mb: 4 }}>
      {/* Header */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(6, 182, 212, 0.1))',
          border: '1px solid rgba(139, 92, 246, 0.2)',
          borderRadius: 4,
          p: 4,
          mb: 4,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Box display="flex" alignItems="center" gap={3}>
            <Box
              sx={{
                width: 60,
                height: 60,
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #8b5cf6, #06b6d4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 8px 32px rgba(139, 92, 246, 0.3)',
                position: 'relative',
                '&::before': {
                  content: '""',
                  position: 'absolute',
                  top: -2,
                  left: -2,
                  right: -2,
                  bottom: -2,
                  borderRadius: '50%',
                  background: 'linear-gradient(45deg, #8b5cf6, #06b6d4, #10b981)',
                  zIndex: -1,
                  opacity: 0.3,
                  animation: 'rotate 8s linear infinite',
                },
                '@keyframes rotate': {
                  '0%': { transform: 'rotate(0deg)' },
                  '100%': { transform: 'rotate(360deg)' },
                },
              }}
            >
              <Analytics sx={{ fontSize: 28, color: 'white' }} />
            </Box>
            <Box>
              <Typography
                variant="h4"
                sx={{
                  fontWeight: 800,
                  background: 'linear-gradient(135deg, #8b5cf6, #06b6d4, #10b981)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  mb: 1,
                }}
              >
                🔬 Advanced Performance Analytics
              </Typography>
              <Typography variant="body1" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                Institutional-grade quantitative analysis with risk metrics, factor attribution, and performance attribution.
                Advanced statistical models for portfolio optimization and risk management.
              </Typography>
            </Box>
          </Box>

          <Box display="flex" alignItems="center" gap={2}>
            <Box display="flex" gap={1}>
              {['1W', '1M', '3M', '6M', '1Y'].map((period) => (
                <Chip
                  key={period}
                  label={period}
                  onClick={() => setSelectedTimeframe(period as any)}
                  sx={{
                    cursor: 'pointer',
                    bgcolor: selectedTimeframe === period ? 'rgba(139, 92, 246, 0.2)' : 'rgba(255,255,255,0.05)',
                    color: selectedTimeframe === period ? '#8b5cf6' : 'text.secondary',
                    fontWeight: selectedTimeframe === period ? 700 : 500,
                    '&:hover': {
                      bgcolor: 'rgba(139, 92, 246, 0.1)',
                    },
                  }}
                />
              ))}
            </Box>

            <Tooltip title="Refresh Analytics" arrow>
              <IconButton
                onClick={handleRefresh}
                disabled={loading}
                sx={{
                  bgcolor: 'rgba(139, 92, 246, 0.1)',
                  color: '#8b5cf6',
                  '&:hover': {
                    bgcolor: 'rgba(139, 92, 246, 0.2)',
                  },
                  '&:disabled': {
                    opacity: 0.5,
                  },
                }}
              >
                {loading ? <CircularProgress size={20} /> : <Refresh />}
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        <Typography variant="caption" sx={{ color: 'text.secondary', mt: 2, display: 'block' }}>
          Last updated: {lastUpdate.toLocaleString()}
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Risk Metrics Dashboard */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(139, 92, 246, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#8b5cf6' }}>
                🛡️ Risk Management Dashboard
              </Typography>

              <Grid container spacing={2}>
                {[
                  { label: 'Sharpe Ratio', value: riskMetrics.sharpeRatio, type: 'ratio', format: formatDecimal },
                  { label: 'Sortino Ratio', value: riskMetrics.sortinoRatio, type: 'ratio', format: formatDecimal },
                  { label: 'Max Drawdown', value: riskMetrics.maxDrawdown, type: 'drawdown', format: formatPercentage },
                  { label: 'Value at Risk (95%)', value: riskMetrics.valueAtRisk, type: 'drawdown', format: formatPercentage },
                  { label: 'Expected Shortfall', value: riskMetrics.expectedShortfall, type: 'drawdown', format: formatPercentage },
                  { label: 'Annual Volatility', value: riskMetrics.volatility, type: 'volatility', format: formatPercentage },
                  { label: 'Beta', value: riskMetrics.beta, type: 'ratio', format: formatDecimal },
                  { label: 'Alpha', value: riskMetrics.alpha, type: 'ratio', format: formatPercentage },
                ].map((metric, index) => (
                  <Grid item xs={12} sm={6} key={index}>
                    <Box
                      sx={{
                        p: 2,
                        borderRadius: 2,
                        bgcolor: 'rgba(30, 41, 59, 0.4)',
                        border: '1px solid rgba(148, 163, 184, 0.1)',
                      }}
                    >
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                        {metric.label}
                      </Typography>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          color: getRiskColor(metric.value, metric.type),
                          mb: 1
                        }}
                      >
                        {metric.format(metric.value)}
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={metric.type === 'ratio' ? Math.min(metric.value * 25, 100) :
                              metric.type === 'drawdown' ? Math.max(0, 100 + metric.value) :
                              Math.max(0, 100 - metric.value)}
                        sx={{
                          height: 4,
                          borderRadius: 2,
                          bgcolor: 'rgba(255,255,255,0.1)',
                          '& .MuiLinearProgress-bar': {
                            bgcolor: getRiskColor(metric.value, metric.type),
                            borderRadius: 2,
                          },
                        }}
                      />
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Performance Attribution */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(6, 182, 212, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#06b6d4' }}>
                📊 Performance Attribution
              </Typography>

              <Box sx={{ height: 300, mb: 3 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={performanceData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="date" stroke="#888" fontSize={12} />
                    <YAxis tickFormatter={(value) => `${value}%`} stroke="#888" fontSize={12} />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: '#1a1a1a',
                        border: '1px solid #333',
                        borderRadius: 8,
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="sharpe"
                      stroke="#06b6d4"
                      strokeWidth={2}
                      name="Sharpe Ratio"
                    />
                    <Line
                      type="monotone"
                      dataKey="drawdown"
                      stroke="#ef4444"
                      strokeWidth={2}
                      name="Drawdown %"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Box>

              {/* Factor Attribution */}
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2, color: '#06b6d4' }}>
                🎯 Factor Attribution
              </Typography>
              <Box sx={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={factorData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="factor" stroke="#888" fontSize={12} />
                    <YAxis stroke="#888" fontSize={12} />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: '#1a1a1a',
                        border: '1px solid #333',
                        borderRadius: 8,
                      }}
                    />
                    <Bar dataKey="contribution" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Correlation Analysis */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(16, 185, 129, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#10b981' }}>
                🔗 Asset Correlation Matrix
              </Typography>

              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart data={correlationData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis
                      type="number"
                      dataKey="correlation"
                      domain={[-1, 1]}
                      tickFormatter={(value) => `${(value * 100).toFixed(0)}%`}
                      stroke="#888"
                      fontSize={12}
                    />
                    <YAxis
                      type="number"
                      dataKey="volatility"
                      tickFormatter={(value) => `${value}%`}
                      stroke="#888"
                      fontSize={12}
                    />
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
                                {data.asset}
                              </Typography>
                              <Typography variant="body2">
                                Correlation: {(data.correlation * 100).toFixed(1)}%
                              </Typography>
                              <Typography variant="body2">
                                Volatility: {data.volatility}%
                              </Typography>
                            </Box>
                          );
                        }
                        return null;
                      }}
                    />
                    <Scatter dataKey="volatility" fill="#10b981" />
                  </ScatterChart>
                </ResponsiveContainer>
              </Box>

              <Typography variant="caption" sx={{ color: 'text.secondary', mt: 2, display: 'block', textAlign: 'center' }}>
                Risk-adjusted correlation analysis • Lower correlation = better diversification
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Portfolio Optimization */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(245, 158, 11, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#f59e0b' }}>
                🎯 Portfolio Optimization
              </Typography>

              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={factorData}>
                    <PolarGrid stroke="#333" />
                    <PolarAngleAxis dataKey="factor" tick={{ fill: '#888', fontSize: 12 }} />
                    <PolarRadiusAxis
                      angle={90}
                      domain={[-0.5, 0.5]}
                      tick={{ fill: '#888', fontSize: 10 }}
                      tickFormatter={(value) => `${(value * 100).toFixed(0)}%`}
                    />
                    <Radar
                      name="Factor Exposure"
                      dataKey="exposure"
                      stroke="#f59e0b"
                      fill="#f59e0b"
                      fillOpacity={0.3}
                      strokeWidth={2}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </Box>

              <Box sx={{ mt: 3, p: 2, bgcolor: 'rgba(245, 158, 11, 0.1)', borderRadius: 2 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, color: '#f59e0b', mb: 1 }}>
                  💡 Optimization Insights
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1.5 }}>
                  Current portfolio shows strong exposure to Quality and Size factors, with slight underweight in Momentum.
                  Consider rebalancing to optimize the risk-return profile based on your investment objectives.
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default AdvancedAnalytics;

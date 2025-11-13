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
  Button,
  Slider,
  Alert,
  Divider,
} from '@mui/material';
import {
  Shield,
  Warning,
  TrendingDown,
  TrendingUp,
  Assessment,
  Refresh,
  Settings,
  Notifications,
  Lock,
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
  BarChart,
  Bar,
  ScatterChart,
  Scatter,
  Cell,
  ReferenceLine,
} from 'recharts';

interface RiskPosition {
  symbol: string;
  exposure: number;
  valueAtRisk: number;
  stopLoss: number;
  takeProfit: number;
  leverage: number;
  liquidationPrice: number;
  marginUsed: number;
}

interface RiskAlert {
  id: string;
  type: 'warning' | 'critical' | 'info';
  message: string;
  threshold: number;
  current: number;
  timestamp: string;
}

interface StressTest {
  scenario: string;
  probability: number;
  impact: number;
  description: string;
}

const RiskManagement: React.FC = () => {
  const theme = useTheme();
  const [loading, setLoading] = useState(false);
  const [riskLimit, setRiskLimit] = useState<number>(5); // 5% max risk
  const [autoStopLoss, setAutoStopLoss] = useState<boolean>(true);
  const [lastUpdate, setLastUpdate] = useState(new Date());

  // Mock risk positions
  const [positions] = useState<RiskPosition[]>([
    {
      symbol: 'BTC/USDT',
      exposure: 5000,
      valueAtRisk: 125,
      stopLoss: 44500,
      takeProfit: 46500,
      leverage: 5,
      liquidationPrice: 43200,
      marginUsed: 1000,
    },
    {
      symbol: 'ETH/USDT',
      exposure: 3000,
      valueAtRisk: 90,
      stopLoss: 2850,
      takeProfit: 3150,
      leverage: 3,
      liquidationPrice: 2720,
      marginUsed: 1000,
    },
    {
      symbol: 'SOL/USDT',
      exposure: 2000,
      valueAtRisk: 80,
      stopLoss: 145,
      takeProfit: 165,
      leverage: 4,
      liquidationPrice: 135,
      marginUsed: 500,
    },
  ]);

  const [riskAlerts] = useState<RiskAlert[]>([
    {
      id: '1',
      type: 'warning',
      message: 'Portfolio VaR approaching 5% limit',
      threshold: 5,
      current: 4.8,
      timestamp: '2 min ago',
    },
    {
      id: '2',
      type: 'info',
      message: 'BTC/USDT liquidation distance: 3.2%',
      threshold: 5,
      current: 3.2,
      timestamp: '5 min ago',
    },
  ]);

  const [stressTests] = useState<StressTest[]>([
    {
      scenario: 'Flash Crash (-20%)',
      probability: 0.05,
      impact: -18.5,
      description: 'Sudden market drop of 20%'
    },
    {
      scenario: 'High Volatility (+50%)',
      probability: 0.15,
      impact: 8.2,
      description: 'Increased market volatility'
    },
    {
      scenario: 'Liquidity Crisis',
      probability: 0.03,
      impact: -25.0,
      description: 'Reduced market liquidity'
    },
  ]);

  const [portfolioRisk] = useState({
    totalExposure: 10000,
    totalVaR: 295,
    marginUsed: 2500,
    marginAvailable: 7500,
    maxDrawdown: -8.5,
    currentDrawdown: -2.1,
    sharpeRatio: 2.34,
    riskAdjustedReturn: 12.8,
  });

  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setLastUpdate(new Date());
    }, 2000);
  };

  const getRiskColor = (value: number, type: 'percentage' | 'currency' = 'percentage') => {
    if (type === 'currency') {
      return value > 100 ? '#ef4444' : value > 50 ? '#f59e0b' : '#10b981';
    }
    const absValue = Math.abs(value);
    if (absValue > 10) return '#ef4444';
    if (absValue > 5) return '#f59e0b';
    return '#10b981';
  };

  const getAlertColor = (type: string) => {
    switch (type) {
      case 'critical': return '#ef4444';
      case 'warning': return '#f59e0b';
      case 'info': return '#06b6d4';
      default: return '#6b7280';
    }
  };

  const formatCurrency = (value: number) => {
    if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
    return `$${value.toFixed(0)}`;
  };

  const calculateLiquidationDistance = (position: RiskPosition) => {
    // Mock current price - in real app this would come from live data
    const currentPrice = position.symbol === 'BTC/USDT' ? 45000 :
                        position.symbol === 'ETH/USDT' ? 3000 : 150;
    return ((currentPrice - position.liquidationPrice) / currentPrice) * 100;
  };

  return (
    <Box sx={{ mb: 4 }}>
      {/* Header */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.1), rgba(245, 158, 11, 0.1))',
          border: '1px solid rgba(239, 68, 68, 0.2)',
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
                background: 'linear-gradient(135deg, #ef4444, #f59e0b)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 8px 32px rgba(239, 68, 68, 0.3)',
                position: 'relative',
                '&::before': {
                  content: '""',
                  position: 'absolute',
                  top: -2,
                  left: -2,
                  right: -2,
                  bottom: -2,
                  borderRadius: '50%',
                  background: 'linear-gradient(45deg, #ef4444, #f59e0b, #10b981)',
                  zIndex: -1,
                  opacity: 0.3,
                  animation: 'rotate 12s linear infinite',
                },
                '@keyframes rotate': {
                  '0%': { transform: 'rotate(0deg)' },
                  '100%': { transform: 'rotate(360deg)' },
                },
              }}
            >
              <Shield sx={{ fontSize: 28, color: 'white' }} />
            </Box>
            <Box>
              <Typography
                variant="h4"
                sx={{
                  fontWeight: 800,
                  background: 'linear-gradient(135deg, #ef4444, #f59e0b, #10b981)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  mb: 1,
                }}
              >
                🛡️ Advanced Risk Management
              </Typography>
              <Typography variant="body1" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                Institutional-grade risk monitoring with real-time position management, VaR calculations,
                and automated risk controls. Enterprise-level protection for algorithmic trading.
              </Typography>
            </Box>
          </Box>

          <Box display="flex" alignItems="center" gap={2}>
            <Box sx={{ minWidth: 200 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', mb: 1, display: 'block' }}>
                Risk Limit: {riskLimit}%
              </Typography>
              <Slider
                value={riskLimit}
                onChange={(_, value) => setRiskLimit(value as number)}
                min={1}
                max={10}
                step={0.5}
                sx={{
                  color: '#ef4444',
                  '& .MuiSlider-thumb': {
                    boxShadow: '0 2px 8px rgba(239, 68, 68, 0.3)',
                  },
                }}
              />
            </Box>

            <Tooltip title="Refresh Risk Data" arrow>
              <IconButton
                onClick={handleRefresh}
                disabled={loading}
                sx={{
                  bgcolor: 'rgba(239, 68, 68, 0.1)',
                  color: '#ef4444',
                  '&:hover': {
                    bgcolor: 'rgba(239, 68, 68, 0.2)',
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
          Last updated: {lastUpdate.toLocaleString()} • Real-time risk monitoring active
        </Typography>
      </Box>

      {/* Risk Alerts */}
      {riskAlerts.length > 0 && (
        <Box sx={{ mb: 4 }}>
          {riskAlerts.map((alert) => (
            <Alert
              key={alert.id}
              severity={alert.type === 'critical' ? 'error' : alert.type === 'warning' ? 'warning' : 'info'}
              sx={{
                mb: 2,
                borderRadius: 2,
                '& .MuiAlert-icon': {
                  color: getAlertColor(alert.type),
                },
              }}
              action={
                <Button color="inherit" size="small">
                  {alert.type === 'critical' ? 'Take Action' : 'Acknowledge'}
                </Button>
              }
            >
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {alert.message}
              </Typography>
              <Typography variant="caption" sx={{ mt: 0.5, display: 'block' }}>
                Threshold: {alert.threshold}% • Current: {alert.current}% • {alert.timestamp}
              </Typography>
            </Alert>
          ))}
        </Box>
      )}

      <Grid container spacing={3}>
        {/* Portfolio Risk Overview */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#ef4444' }}>
                📊 Portfolio Risk Overview
              </Typography>

              <Grid container spacing={2} sx={{ mb: 3 }}>
                {[
                  { label: 'Total Exposure', value: portfolioRisk.totalExposure, format: formatCurrency, color: '#ef4444' },
                  { label: 'Portfolio VaR', value: portfolioRisk.totalVaR, format: formatCurrency, color: '#f59e0b' },
                  { label: 'Margin Used', value: portfolioRisk.marginUsed, format: formatCurrency, color: '#06b6d4' },
                  { label: 'Margin Available', value: portfolioRisk.marginAvailable, format: formatCurrency, color: '#10b981' },
                  { label: 'Current Drawdown', value: portfolioRisk.currentDrawdown, format: (v: number) => `${v}%`, color: getRiskColor(portfolioRisk.currentDrawdown) },
                  { label: 'Max Drawdown', value: portfolioRisk.maxDrawdown, format: (v: number) => `${v}%`, color: getRiskColor(portfolioRisk.maxDrawdown) },
                  { label: 'Sharpe Ratio', value: portfolioRisk.sharpeRatio, format: (v: number) => v.toFixed(2), color: portfolioRisk.sharpeRatio >= 2 ? '#10b981' : '#f59e0b' },
                  { label: 'Risk-Adj Return', value: portfolioRisk.riskAdjustedReturn, format: (v: number) => `${v}%`, color: '#8b5cf6' },
                ].map((metric, index) => (
                  <Grid item xs={6} key={index}>
                    <Box
                      sx={{
                        p: 2,
                        borderRadius: 2,
                        bgcolor: 'rgba(30, 41, 59, 0.4)',
                        border: '1px solid rgba(148, 163, 184, 0.1)',
                      }}
                    >
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                        {metric.label}
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 700, color: metric.color }}>
                        {metric.format(metric.value)}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>

              {/* Risk Limit Indicator */}
              <Box sx={{ mb: 2 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    Risk Utilization
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: '#ef4444' }}>
                    {(portfolioRisk.totalVaR / portfolioRisk.totalExposure * 100).toFixed(1)}% / {riskLimit}%
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={(portfolioRisk.totalVaR / portfolioRisk.totalExposure * 100) / riskLimit * 100}
                  sx={{
                    height: 8,
                    borderRadius: 4,
                    bgcolor: 'rgba(255,255,255,0.1)',
                    '& .MuiLinearProgress-bar': {
                      bgcolor: (portfolioRisk.totalVaR / portfolioRisk.totalExposure * 100) > riskLimit * 0.8 ? '#ef4444' : '#f59e0b',
                      borderRadius: 4,
                    },
                  }}
                />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Position Risk Details */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(245, 158, 11, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#f59e0b' }}>
                🎯 Position Risk Analysis
              </Typography>

              {positions.map((position, index) => (
                <Box key={index} sx={{ mb: 3, p: 2, bgcolor: 'rgba(30, 41, 59, 0.4)', borderRadius: 2 }}>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      {position.symbol}
                    </Typography>
                    <Chip
                      label={`${position.leverage}x`}
                      sx={{
                        bgcolor: position.leverage > 5 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                        color: position.leverage > 5 ? '#ef4444' : '#f59e0b',
                        fontWeight: 600,
                      }}
                    />
                  </Box>

                  <Grid container spacing={2} sx={{ mb: 2 }}>
                    <Grid item xs={6}>
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                        Exposure
                      </Typography>
                      <Typography variant="body2" sx={{ color: '#06b6d4', fontWeight: 700 }}>
                        {formatCurrency(position.exposure)}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                        VaR (95%)
                      </Typography>
                      <Typography variant="body2" sx={{ color: getRiskColor(position.valueAtRisk, 'currency'), fontWeight: 700 }}>
                        {formatCurrency(position.valueAtRisk)}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                        Stop Loss
                      </Typography>
                      <Typography variant="body2" sx={{ color: '#ef4444', fontWeight: 700 }}>
                        ${position.stopLoss.toLocaleString()}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                        Liquidation Distance
                      </Typography>
                      <Typography variant="body2" sx={{
                        color: calculateLiquidationDistance(position) < 5 ? '#ef4444' : '#10b981',
                        fontWeight: 700
                      }}>
                        {calculateLiquidationDistance(position).toFixed(1)}%
                      </Typography>
                    </Grid>
                  </Grid>

                  {/* Risk Bar */}
                  <Box sx={{ mb: 1 }}>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        Position Risk
                      </Typography>
                      <Typography variant="caption" sx={{ fontWeight: 600, color: getRiskColor(position.valueAtRisk / position.exposure * 100) }}>
                        {(position.valueAtRisk / position.exposure * 100).toFixed(1)}%
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={position.valueAtRisk / position.exposure * 100}
                      sx={{
                        height: 4,
                        borderRadius: 2,
                        bgcolor: 'rgba(255,255,255,0.1)',
                        '& .MuiLinearProgress-bar': {
                          bgcolor: getRiskColor(position.valueAtRisk / position.exposure * 100),
                          borderRadius: 2,
                        },
                      }}
                    />
                  </Box>
                </Box>
              ))}

              {/* Auto Risk Controls */}
              <Box sx={{ mt: 3, p: 2, bgcolor: 'rgba(16, 185, 129, 0.1)', borderRadius: 2 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2" sx={{ fontWeight: 600, color: '#10b981' }}>
                    Auto Risk Controls
                  </Typography>
                  <Button
                    size="small"
                    startIcon={<Lock />}
                    onClick={() => setAutoStopLoss(!autoStopLoss)}
                    sx={{
                      color: autoStopLoss ? '#10b981' : '#ef4444',
                      fontSize: '0.75rem',
                    }}
                  >
                    {autoStopLoss ? 'Active' : 'Inactive'}
                  </Button>
                </Box>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  Automatic position reduction when risk thresholds are exceeded
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Stress Testing */}
        <Grid item xs={12}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(139, 92, 246, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#8b5cf6' }}>
                ⚠️ Stress Testing Scenarios
              </Typography>

              <Grid container spacing={3}>
                {stressTests.map((scenario, index) => (
                  <Grid item xs={12} md={4} key={index}>
                    <Box sx={{
                      p: 3,
                      borderRadius: 3,
                      bgcolor: 'rgba(30, 41, 59, 0.4)',
                      border: '1px solid rgba(148, 163, 184, 0.1)',
                      position: 'relative',
                      overflow: 'hidden',
                    }}>
                      <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={2}>
                        <Typography variant="h6" sx={{ fontWeight: 700, color: '#8b5cf6' }}>
                          {scenario.scenario}
                        </Typography>
                        <Chip
                          label={`${(scenario.probability * 100).toFixed(1)}%`}
                          size="small"
                          sx={{
                            bgcolor: scenario.probability > 0.1 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                            color: scenario.probability > 0.1 ? '#ef4444' : '#10b981',
                            fontWeight: 600,
                          }}
                        />
                      </Box>

                      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2, lineHeight: 1.5 }}>
                        {scenario.description}
                      </Typography>

                      <Box sx={{ mb: 2 }}>
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            Impact on Portfolio
                          </Typography>
                          <Typography variant="body2" sx={{
                            fontWeight: 700,
                            color: scenario.impact < -10 ? '#ef4444' : scenario.impact < 0 ? '#f59e0b' : '#10b981'
                          }}>
                            {scenario.impact > 0 ? '+' : ''}{scenario.impact}%
                          </Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={Math.max(0, 50 + scenario.impact)}
                          sx={{
                            height: 6,
                            borderRadius: 3,
                            bgcolor: 'rgba(255,255,255,0.1)',
                            '& .MuiLinearProgress-bar': {
                              bgcolor: scenario.impact < -10 ? '#ef4444' : scenario.impact < 0 ? '#f59e0b' : '#10b981',
                              borderRadius: 3,
                            },
                          }}
                        />
                      </Box>

                      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                        Expected loss: {formatCurrency(Math.abs(scenario.impact / 100 * portfolioRisk.totalExposure))}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default RiskManagement;

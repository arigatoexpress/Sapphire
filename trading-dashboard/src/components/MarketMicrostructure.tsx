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
  Slider,
} from '@mui/material';
import {
  Analytics,
  TrendingUp,
  TrendingDown,
  Timeline,
  BarChart,
  ScatterPlot,
  Refresh,
  ZoomIn,
  ZoomOut,
  CenterFocusStrong,
} from '@mui/icons-material';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Area,
  Bar,
  Scatter,
  Cell,
  ReferenceLine,
} from 'recharts';

interface OrderBookEntry {
  price: number;
  size: number;
  side: 'bid' | 'ask';
  orders: number;
}

interface LiquidityMetrics {
  spread: number;
  depth: number;
  slippage: number;
  volume: number;
  volatility: number;
}

interface TradeFlow {
  timestamp: string;
  price: number;
  size: number;
  direction: 'buy' | 'sell';
  aggression: number;
}

const MarketMicrostructure: React.FC = () => {
  const theme = useTheme();
  const [loading, setLoading] = useState(false);
  const [selectedDepth, setSelectedDepth] = useState<number>(50);
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [lastUpdate, setLastUpdate] = useState(new Date());

  // Mock order book data
  const [orderBook] = useState<OrderBookEntry[]>([
    // Bids (buy orders)
    { price: 45000, size: 2.5, side: 'bid', orders: 12 },
    { price: 44950, size: 3.2, side: 'bid', orders: 8 },
    { price: 44900, size: 4.1, side: 'bid', orders: 15 },
    { price: 44850, size: 2.8, side: 'bid', orders: 6 },
    { price: 44800, size: 5.5, side: 'bid', orders: 20 },
    // Asks (sell orders)
    { price: 45100, size: 1.8, side: 'ask', orders: 9 },
    { price: 45150, size: 3.7, side: 'ask', orders: 14 },
    { price: 45200, size: 2.3, side: 'ask', orders: 7 },
    { price: 45250, size: 4.2, side: 'ask', orders: 11 },
    { price: 45300, size: 3.9, side: 'ask', orders: 16 },
  ]);

  const [liquidityMetrics] = useState<LiquidityMetrics>({
    spread: 100, // $100 spread
    depth: 125000, // $125K total depth
    slippage: 0.15, // 0.15% slippage for $1000 order
    volume: 2500000, // $2.5M daily volume
    volatility: 2.8, // 2.8% daily volatility
  });

  const [tradeFlow] = useState<TradeFlow[]>([
    { timestamp: '10:30', price: 45050, size: 0.5, direction: 'buy', aggression: 0.8 },
    { timestamp: '10:31', price: 45045, size: 1.2, direction: 'sell', aggression: 0.6 },
    { timestamp: '10:32', price: 45060, size: 0.8, direction: 'buy', aggression: 0.9 },
    { timestamp: '10:33', price: 45040, size: 2.1, direction: 'sell', aggression: 0.3 },
    { timestamp: '10:34', price: 45070, size: 0.3, direction: 'buy', aggression: 1.0 },
    { timestamp: '10:35', price: 45035, size: 1.8, direction: 'sell', aggression: 0.4 },
  ]);

  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setLastUpdate(new Date());
    }, 2000);
  };

  const formatCurrency = (value: number) => {
    if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`;
    return `$${value.toFixed(0)}`;
  };

  const formatPrice = (value: number) => `$${value.toLocaleString()}`;

  const getSpreadColor = (spread: number) => {
    if (spread <= 50) return '#10b981'; // Tight spread
    if (spread <= 150) return '#f59e0b'; // Normal spread
    return '#ef4444'; // Wide spread
  };

  const getDepthColor = (depth: number) => {
    if (depth >= 100000) return '#10b981'; // Deep liquidity
    if (depth >= 50000) return '#f59e0b'; // Moderate liquidity
    return '#ef4444'; // Shallow liquidity
  };

  // Prepare chart data
  const chartData = orderBook.map(entry => ({
    price: entry.price,
    bidSize: entry.side === 'bid' ? entry.size : 0,
    askSize: entry.side === 'ask' ? entry.size : 0,
    bidOrders: entry.side === 'bid' ? entry.orders : 0,
    askOrders: entry.side === 'ask' ? entry.orders : 0,
  }));

  return (
    <Box sx={{ mb: 4 }}>
      {/* Header */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.1), rgba(16, 185, 129, 0.1))',
          border: '1px solid rgba(6, 182, 212, 0.2)',
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
                background: 'linear-gradient(135deg, #06b6d4, #10b981)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 8px 32px rgba(6, 182, 212, 0.3)',
                position: 'relative',
                '&::before': {
                  content: '""',
                  position: 'absolute',
                  top: -2,
                  left: -2,
                  right: -2,
                  bottom: -2,
                  borderRadius: '50%',
                  background: 'linear-gradient(45deg, #06b6d4, #10b981, #f59e0b)',
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
              <ScatterPlot sx={{ fontSize: 28, color: 'white' }} />
            </Box>
            <Box>
              <Typography
                variant="h4"
                sx={{
                  fontWeight: 800,
                  background: 'linear-gradient(135deg, #06b6d4, #10b981, #f59e0b)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  mb: 1,
                }}
              >
                🔬 Market Microstructure Analysis
              </Typography>
              <Typography variant="body1" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                Deep dive into order book dynamics, liquidity analysis, and trade flow patterns.
                Advanced market microstructure metrics for institutional-grade analysis.
              </Typography>
            </Box>
          </Box>

          <Box display="flex" alignItems="center" gap={2}>
            <Box sx={{ minWidth: 150 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', mb: 1, display: 'block' }}>
                Order Book Depth: {selectedDepth}%
              </Typography>
              <Slider
                value={selectedDepth}
                onChange={(_, value) => setSelectedDepth(value as number)}
                min={10}
                max={100}
                step={10}
                sx={{
                  color: '#06b6d4',
                  '& .MuiSlider-thumb': {
                    boxShadow: '0 2px 8px rgba(6, 182, 212, 0.3)',
                  },
                }}
              />
            </Box>

            <Tooltip title="Refresh Market Data" arrow>
              <IconButton
                onClick={handleRefresh}
                disabled={loading}
                sx={{
                  bgcolor: 'rgba(6, 182, 212, 0.1)',
                  color: '#06b6d4',
                  '&:hover': {
                    bgcolor: 'rgba(6, 182, 212, 0.2)',
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
          Last updated: {lastUpdate.toLocaleString()} • Real-time order book analysis
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Order Book Visualization */}
        <Grid item xs={12} lg={8}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(6, 182, 212, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#06b6d4' }}>
                📊 Live Order Book Depth
              </Typography>

              <Box sx={{ height: 400, mb: 2 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis
                      dataKey="price"
                      tickFormatter={formatPrice}
                      stroke="#888"
                      fontSize={12}
                    />
                    <YAxis
                      yAxisId="size"
                      orientation="left"
                      tickFormatter={(value) => `${value} BTC`}
                      stroke="#888"
                      fontSize={12}
                    />
                    <YAxis
                      yAxisId="orders"
                      orientation="right"
                      tickFormatter={(value) => `${value}`}
                      stroke="#666"
                      fontSize={12}
                    />
                    <RechartsTooltip
                      content={({ active, payload, label }) => {
                        if (active && payload && payload.length) {
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
                                Price: {formatPrice(label)}
                              </Typography>
                              {payload.map((entry, index) => (
                                <Typography key={index} variant="body2" sx={{ color: entry.color }}>
                                  {entry.name}: {entry.value}
                                </Typography>
                              ))}
                            </Box>
                          );
                        }
                        return null;
                      }}
                    />

                    {/* Bid bars (green) */}
                    <Bar
                      yAxisId="size"
                      dataKey="bidSize"
                      fill="#10b981"
                      opacity={0.7}
                      name="Bid Size"
                    />

                    {/* Ask bars (red) */}
                    <Bar
                      yAxisId="size"
                      dataKey="askSize"
                      fill="#ef4444"
                      opacity={0.7}
                      name="Ask Size"
                    />

                    {/* Spread reference line */}
                    <ReferenceLine
                      x={45050}
                      stroke="#f59e0b"
                      strokeDasharray="5 5"
                      label={{ value: "Mid Price", position: "top" }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </Box>

              {/* Order Book Table */}
              <Box sx={{ display: 'flex', gap: 2 }}>
                {/* Bids */}
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" sx={{ color: '#10b981', fontWeight: 600, mb: 1 }}>
                    🟢 Bids (Buy Orders)
                  </Typography>
                  <Box sx={{ maxHeight: 200, overflow: 'auto' }}>
                    {orderBook.filter(entry => entry.side === 'bid').slice(0, 5).map((entry, index) => (
                      <Box
                        key={index}
                        sx={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          p: 1,
                          borderRadius: 1,
                          bgcolor: 'rgba(16, 185, 129, 0.1)',
                          mb: 0.5,
                        }}
                      >
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {formatPrice(entry.price)}
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                          {entry.size} BTC ({entry.orders} orders)
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Box>

                {/* Asks */}
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" sx={{ color: '#ef4444', fontWeight: 600, mb: 1 }}>
                    🔴 Asks (Sell Orders)
                  </Typography>
                  <Box sx={{ maxHeight: 200, overflow: 'auto' }}>
                    {orderBook.filter(entry => entry.side === 'ask').slice(0, 5).map((entry, index) => (
                      <Box
                        key={index}
                        sx={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          p: 1,
                          borderRadius: 1,
                          bgcolor: 'rgba(239, 68, 68, 0.1)',
                          mb: 0.5,
                        }}
                      >
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {formatPrice(entry.price)}
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                          {entry.size} BTC ({entry.orders} orders)
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Liquidity Metrics */}
        <Grid item xs={12} lg={4}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(16, 185, 129, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#10b981' }}>
                💧 Liquidity Metrics
              </Typography>

              <Box sx={{ mb: 3 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    Bid-Ask Spread
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: getSpreadColor(liquidityMetrics.spread) }}>
                    ${liquidityMetrics.spread}
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={Math.max(0, 100 - (liquidityMetrics.spread / 2))}
                  sx={{
                    height: 6,
                    borderRadius: 3,
                    bgcolor: 'rgba(255,255,255,0.1)',
                    '& .MuiLinearProgress-bar': {
                      bgcolor: getSpreadColor(liquidityMetrics.spread),
                      borderRadius: 3,
                    },
                  }}
                />
              </Box>

              <Box sx={{ mb: 3 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    Market Depth
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: getDepthColor(liquidityMetrics.depth) }}>
                    {formatCurrency(liquidityMetrics.depth)}
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={(liquidityMetrics.depth / 200000) * 100}
                  sx={{
                    height: 6,
                    borderRadius: 3,
                    bgcolor: 'rgba(255,255,255,0.1)',
                    '& .MuiLinearProgress-bar': {
                      bgcolor: getDepthColor(liquidityMetrics.depth),
                      borderRadius: 3,
                    },
                  }}
                />
              </Box>

              {/* Additional Metrics */}
              <Grid container spacing={2}>
                {[
                  { label: 'Price Impact (1K)', value: `${liquidityMetrics.slippage}%`, color: '#06b6d4' },
                  { label: '24h Volume', value: formatCurrency(liquidityMetrics.volume), color: '#f59e0b' },
                  { label: 'Volatility', value: `${liquidityMetrics.volatility}%`, color: '#ef4444' },
                ].map((metric, index) => (
                  <Grid item xs={12} key={index}>
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
                      <Typography variant="body1" sx={{ fontWeight: 700, color: metric.color }}>
                        {metric.value}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Trade Flow Analysis */}
        <Grid item xs={12}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(245, 158, 11, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#f59e0b' }}>
                🌊 Trade Flow Analysis
              </Typography>

              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={tradeFlow}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="timestamp" stroke="#888" fontSize={12} />
                    <YAxis
                      yAxisId="price"
                      orientation="left"
                      tickFormatter={formatPrice}
                      stroke="#888"
                      fontSize={12}
                    />
                    <YAxis
                      yAxisId="size"
                      orientation="right"
                      tickFormatter={(value) => `${value} BTC`}
                      stroke="#666"
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
                                {data.timestamp} - {data.direction.toUpperCase()}
                              </Typography>
                              <Typography variant="body2">
                                Price: {formatPrice(data.price)}
                              </Typography>
                              <Typography variant="body2">
                                Size: {data.size} BTC
                              </Typography>
                              <Typography variant="body2">
                                Aggression: {(data.aggression * 100).toFixed(0)}%
                              </Typography>
                            </Box>
                          );
                        }
                        return null;
                      }}
                    />

                    <Line
                      yAxisId="price"
                      type="monotone"
                      dataKey="price"
                      stroke="#f59e0b"
                      strokeWidth={2}
                      dot={{ fill: '#f59e0b', strokeWidth: 2, r: 4 }}
                    />

                    <Bar
                      yAxisId="size"
                      dataKey="size"
                      fill="#06b6d4"
                      opacity={0.6}
                    >
                      {tradeFlow.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={entry.direction === 'buy' ? '#10b981' : '#ef4444'}
                        />
                      ))}
                    </Bar>
                  </ComposedChart>
                </ResponsiveContainer>
              </Box>

              <Box sx={{ mt: 2, display: 'flex', gap: 2, justifyContent: 'center' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: '#10b981' }} />
                  <Typography variant="caption">Buy Orders</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: '#ef4444' }} />
                  <Typography variant="caption">Sell Orders</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ width: 2, height: 12, bgcolor: '#f59e0b' }} />
                  <Typography variant="caption">Price Action</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default MarketMicrostructure;

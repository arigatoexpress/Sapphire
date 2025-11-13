import React, { useState } from 'react';
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
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  Analytics,
  Refresh,
  SentimentSatisfied,
  SentimentDissatisfied,
  SentimentNeutral,
} from '@mui/icons-material';

interface MarketIndicator {
  name: string;
  value: number;
  change: number;
  status: 'bullish' | 'bearish' | 'neutral';
  description: string;
}

interface SentimentData {
  overall: number;
  social: number;
  news: number;
  technical: number;
}

const MarketAnalysis: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date());

  // Mock market indicators - in real app, this would come from APIs
  const [indicators] = useState<MarketIndicator[]>([
    {
      name: 'BTC/USDT Momentum',
      value: 68.5,
      change: 2.3,
      status: 'bullish',
      description: 'Strong upward momentum detected'
    },
    {
      name: 'Market Volatility (VIX)',
      value: 23.4,
      change: -1.2,
      status: 'neutral',
      description: 'Moderate volatility levels'
    },
    {
      name: 'Order Flow Imbalance',
      value: 12.8,
      change: 5.7,
      status: 'bullish',
      description: 'Buy orders dominating'
    },
    {
      name: 'Liquidity Score',
      value: 84.2,
      change: 1.8,
      status: 'bullish',
      description: 'High market liquidity'
    },
    {
      name: 'Fear & Greed Index',
      value: 45.6,
      change: -3.2,
      status: 'neutral',
      description: 'Market sentiment balanced'
    },
    {
      name: 'Volume Profile',
      value: 91.3,
      change: 4.1,
      status: 'bullish',
      description: 'Strong volume confirmation'
    }
  ]);

  const [sentiment] = useState<SentimentData>({
    overall: 65,
    social: 72,
    news: 58,
    technical: 68
  });

  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setLastUpdate(new Date());
    }, 2000);
  };

  const getIndicatorColor = (status: string) => {
    switch (status) {
      case 'bullish': return '#10b981';
      case 'bearish': return '#ef4444';
      case 'neutral': return '#f59e0b';
      default: return '#6b7280';
    }
  };

  const getIndicatorIcon = (status: string) => {
    switch (status) {
      case 'bullish': return <TrendingUp sx={{ fontSize: 16 }} />;
      case 'bearish': return <TrendingDown sx={{ fontSize: 16 }} />;
      case 'neutral': return <TrendingFlat sx={{ fontSize: 16 }} />;
      default: return <Analytics sx={{ fontSize: 16 }} />;
    }
  };

  const getSentimentIcon = (value: number) => {
    if (value >= 70) return <SentimentSatisfied sx={{ color: '#10b981' }} />;
    if (value <= 30) return <SentimentDissatisfied sx={{ color: '#ef4444' }} />;
    return <SentimentNeutral sx={{ color: '#f59e0b' }} />;
  };

  const getSentimentLabel = (value: number) => {
    if (value >= 70) return 'Bullish';
    if (value <= 30) return 'Bearish';
    return 'Neutral';
  };

  return (
    <Card sx={{
      mb: 4,
      background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
      backdropFilter: 'blur(20px)',
      border: '1px solid rgba(59, 130, 246, 0.2)',
      borderRadius: '20px',
      position: 'relative',
      overflow: 'hidden',
      boxShadow: '0 20px 40px rgba(0, 0, 0, 0.1)',
      '&::before': {
        content: '""',
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '4px',
        background: 'linear-gradient(90deg, #3b82f6, #06b6d4, #10b981, #f59e0b)',
      },
    }}>
      <CardContent sx={{ p: 4 }}>
        <Box
          sx={{
            background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(6, 182, 212, 0.1))',
            border: '1px solid rgba(59, 130, 246, 0.2)',
            borderRadius: 3,
            p: 3,
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
                  background: 'linear-gradient(135deg, #3b82f6, #06b6d4)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 8px 32px rgba(59, 130, 246, 0.3)',
                  position: 'relative',
                  '&::before': {
                    content: '""',
                    position: 'absolute',
                    top: -2,
                    left: -2,
                    right: -2,
                    bottom: -2,
                    borderRadius: '50%',
                    background: 'linear-gradient(45deg, #3b82f6, #06b6d4, #10b981)',
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
                    background: 'linear-gradient(135deg, #3b82f6, #06b6d4, #10b981)',
                    backgroundClip: 'text',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    mb: 1,
                  }}
                >
                  🌟 Quantum Market Intelligence
                </Typography>
                <Typography variant="body1" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                  Advanced algorithmic analysis of market microstructure, sentiment patterns, and institutional flows.
                  Real-time insights powered by multi-dimensional data fusion and predictive analytics.
                </Typography>
              </Box>
            </Box>

            {/* Live Status Indicator */}
            <Box sx={{ textAlign: 'center' }}>
              <Box
                sx={{
                  width: 20,
                  height: 20,
                  borderRadius: '50%',
                  background: '#10b981',
                  mx: 'auto',
                  mb: 1,
                  boxShadow: '0 0 20px rgba(16, 185, 129, 0.6)',
                  animation: 'pulse 2s ease-in-out infinite',
                  '@keyframes pulse': {
                    '0%': { boxShadow: '0 0 20px rgba(16, 185, 129, 0.6)' },
                    '50%': { boxShadow: '0 0 30px rgba(16, 185, 129, 0.9)' },
                    '100%': { boxShadow: '0 0 20px rgba(16, 185, 129, 0.6)' },
                  },
                }}
              />
              <Typography variant="caption" sx={{ color: '#10b981', fontWeight: 600, fontSize: '0.75rem' }}>
                LIVE DATA
              </Typography>
            </Box>
          </Box>

          <Box display="flex" alignItems="center" gap={2} sx={{ mt: 2 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              Last updated: {lastUpdate.toLocaleTimeString()}
            </Typography>
            <Tooltip title="Refresh Market Data" arrow>
              <IconButton
                onClick={handleRefresh}
                disabled={loading}
                sx={{
                  bgcolor: 'rgba(59, 130, 246, 0.1)',
                  color: '#3b82f6',
                  '&:hover': {
                    bgcolor: 'rgba(59, 130, 246, 0.2)',
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

        <Grid container spacing={3}>
          {/* Market Indicators */}
          <Grid item xs={12} lg={8}>
            <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, color: '#3b82f6' }}>
              🏷️ Key Market Indicators
            </Typography>
            <Grid container spacing={2}>
              {indicators.map((indicator, index) => (
                <Grid item xs={12} sm={6} key={index}>
                  <Box
                    sx={{
                      p: 2,
                      borderRadius: 2,
                      bgcolor: 'rgba(30, 41, 59, 0.4)',
                      border: '1px solid rgba(148, 163, 184, 0.1)',
                      transition: 'all 0.2s ease',
                      '&:hover': {
                        bgcolor: 'rgba(30, 41, 59, 0.6)',
                        borderColor: getIndicatorColor(indicator.status),
                      },
                    }}
                  >
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {indicator.name}
                      </Typography>
                      <Chip
                        icon={getIndicatorIcon(indicator.status)}
                        label={`${indicator.change >= 0 ? '+' : ''}${indicator.change}%`}
                        size="small"
                        sx={{
                          height: 20,
                          bgcolor: `${getIndicatorColor(indicator.status)}20`,
                          color: getIndicatorColor(indicator.status),
                          fontSize: '0.7rem',
                          fontWeight: 600,
                        }}
                      />
                    </Box>

                    <Box display="flex" alignItems="center" gap={2} mb={1}>
                      <Typography variant="h6" sx={{ fontWeight: 700, color: getIndicatorColor(indicator.status) }}>
                        {indicator.value.toFixed(1)}
                      </Typography>
                      <Box sx={{ flex: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={indicator.value}
                          sx={{
                            height: 6,
                            borderRadius: 3,
                            bgcolor: 'rgba(255, 255, 255, 0.1)',
                            '& .MuiLinearProgress-bar': {
                              bgcolor: getIndicatorColor(indicator.status),
                              borderRadius: 3,
                            },
                          }}
                        />
                      </Box>
                    </Box>

                    <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1.3 }}>
                      {indicator.description}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </Grid>

          {/* Market Sentiment */}
          <Grid item xs={12} lg={4}>
            <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, color: '#ec4899' }}>
              💭 Market Sentiment Analysis
            </Typography>

            <Box sx={{ mb: 3 }}>
              <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Overall Sentiment
                </Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  {getSentimentIcon(sentiment.overall)}
                  <Typography variant="body2" sx={{ fontWeight: 700, color: sentiment.overall >= 70 ? '#10b981' : sentiment.overall <= 30 ? '#ef4444' : '#f59e0b' }}>
                    {sentiment.overall}
                  </Typography>
                </Box>
              </Box>
              <LinearProgress
                variant="determinate"
                value={sentiment.overall}
                sx={{
                  height: 8,
                  borderRadius: 4,
                  bgcolor: 'rgba(255, 255, 255, 0.1)',
                  '& .MuiLinearProgress-bar': {
                    bgcolor: sentiment.overall >= 70 ? '#10b981' : sentiment.overall <= 30 ? '#ef4444' : '#f59e0b',
                    borderRadius: 4,
                  },
                }}
              />
              <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
                {getSentimentLabel(sentiment.overall)} market sentiment
              </Typography>
            </Box>

            <Grid container spacing={2}>
              {[
                { label: 'Social Media', value: sentiment.social, color: '#8b5cf6' },
                { label: 'News Flow', value: sentiment.news, color: '#f59e0b' },
                { label: 'Technical', value: sentiment.technical, color: '#06b6d4' },
              ].map((item, index) => (
                <Grid item xs={12} key={index}>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {item.label}
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: item.color }}>
                      {item.value}
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={item.value}
                    sx={{
                      height: 4,
                      borderRadius: 2,
                      bgcolor: 'rgba(255, 255, 255, 0.1)',
                      '& .MuiLinearProgress-bar': {
                        bgcolor: item.color,
                        borderRadius: 2,
                      },
                    }}
                  />
                </Grid>
              ))}
            </Grid>

            <Box sx={{ mt: 3, p: 2, bgcolor: 'rgba(236, 72, 153, 0.1)', borderRadius: 2, border: '1px solid rgba(236, 72, 153, 0.2)' }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: '#ec4899', mb: 1 }}>
                🤖 AI Analysis
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1.4 }}>
                Our agents are analyzing market sentiment across social media, news sources, and technical indicators to identify trading opportunities.
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

export default MarketAnalysis;

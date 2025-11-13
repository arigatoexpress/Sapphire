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
  Divider,
} from '@mui/material';
import {
  SentimentSatisfied,
  SentimentDissatisfied,
  SentimentNeutral,
  TrendingUp,
  TrendingDown,
  Analytics,
  Refresh,
  Psychology,
  Article,
  Twitter,
  Forum,
} from '@mui/icons-material';
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
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

interface SentimentData {
  timestamp: string;
  overall: number;
  social: number;
  news: number;
  technical: number;
  fearGreed: number;
}

interface SocialMetrics {
  platform: string;
  sentiment: number;
  volume: number;
  mentions: number;
  icon: React.ReactNode;
}

interface NewsAnalysis {
  title: string;
  sentiment: number;
  impact: 'high' | 'medium' | 'low';
  source: string;
  timestamp: string;
}

const SentimentAnalysis: React.FC = () => {
  const theme = useTheme();
  const [loading, setLoading] = useState(false);
  const [selectedTimeframe, setSelectedTimeframe] = useState<'1H' | '4H' | '24H' | '7D'>('24H');
  const [lastUpdate, setLastUpdate] = useState(new Date());

  // Mock sentiment data over time
  const [sentimentHistory] = useState<SentimentData[]>([
    { timestamp: '00:00', overall: 45, social: 52, news: 38, technical: 48, fearGreed: 35 },
    { timestamp: '04:00', overall: 48, social: 55, news: 42, technical: 50, fearGreed: 38 },
    { timestamp: '08:00', overall: 52, social: 58, news: 48, technical: 54, fearGreed: 45 },
    { timestamp: '12:00', overall: 58, social: 62, news: 55, technical: 59, fearGreed: 52 },
    { timestamp: '16:00', overall: 62, social: 65, news: 58, technical: 64, fearGreed: 58 },
    { timestamp: '20:00', overall: 65, social: 68, news: 62, technical: 67, fearGreed: 62 },
  ]);

  const [socialMetrics] = useState<SocialMetrics[]>([
    { platform: 'Twitter', sentiment: 68, volume: 12500, mentions: 8500, icon: <Twitter /> },
    { platform: 'Reddit', sentiment: 72, volume: 8200, mentions: 6200, icon: <Forum /> },
    { platform: 'News', sentiment: 58, volume: 3400, mentions: 1200, icon: <Article /> },
    { platform: 'Telegram', sentiment: 75, volume: 5600, mentions: 4100, icon: <Psychology /> },
  ]);

  const [newsAnalysis] = useState<NewsAnalysis[]>([
    {
      title: 'Major Institutional Investor Announces Bitcoin Accumulation',
      sentiment: 85,
      impact: 'high',
      source: 'CoinDesk',
      timestamp: '2 hours ago'
    },
    {
      title: 'Regulatory Clarity Expected for Crypto Markets',
      sentiment: 78,
      impact: 'high',
      source: 'Bloomberg',
      timestamp: '4 hours ago'
    },
    {
      title: 'Ethereum Network Upgrade Successfully Completed',
      sentiment: 82,
      impact: 'medium',
      source: 'Cointelegraph',
      timestamp: '6 hours ago'
    },
    {
      title: 'Market Analysis: BTC Showing Bullish Divergence',
      sentiment: 65,
      impact: 'medium',
      source: 'TradingView',
      timestamp: '8 hours ago'
    },
  ]);

  const [marketPsychology] = useState({
    fearGreed: 62,
    putCallRatio: 0.85,
    vixLevel: 18.5,
    institutionalFlow: 1.2, // Billion USD
  });

  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setLastUpdate(new Date());
    }, 2000);
  };

  const getSentimentColor = (value: number) => {
    if (value >= 70) return '#10b981';
    if (value >= 50) return '#f59e0b';
    return '#ef4444';
  };

  const getSentimentLabel = (value: number) => {
    if (value >= 70) return 'Bullish';
    if (value >= 50) return 'Neutral';
    return 'Bearish';
  };

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case 'high': return '#ef4444';
      case 'medium': return '#f59e0b';
      case 'low': return '#10b981';
      default: return '#6b7280';
    }
  };

  // Prepare pie chart data for social sentiment distribution
  const pieData = socialMetrics.map(metric => ({
    name: metric.platform,
    value: metric.sentiment,
    color: getSentimentColor(metric.sentiment),
  }));

  const COLORS = ['#10b981', '#06b6d4', '#f59e0b', '#8b5cf6'];

  return (
    <Box sx={{ mb: 4 }}>
      {/* Header */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, rgba(236, 72, 153, 0.1), rgba(168, 85, 247, 0.1))',
          border: '1px solid rgba(236, 72, 153, 0.2)',
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
                background: 'linear-gradient(135deg, #ec4899, #8b5cf6)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 8px 32px rgba(236, 72, 153, 0.3)',
                position: 'relative',
                '&::before': {
                  content: '""',
                  position: 'absolute',
                  top: -2,
                  left: -2,
                  right: -2,
                  bottom: -2,
                  borderRadius: '50%',
                  background: 'linear-gradient(45deg, #ec4899, #8b5cf6, #06b6d4)',
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
              <SentimentSatisfied sx={{ fontSize: 28, color: 'white' }} />
            </Box>
            <Box>
              <Typography
                variant="h4"
                sx={{
                  fontWeight: 800,
                  background: 'linear-gradient(135deg, #ec4899, #8b5cf6, #06b6d4)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  mb: 1,
                }}
              >
                🧠 Market Sentiment Intelligence
              </Typography>
              <Typography variant="body1" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                AI-powered sentiment analysis combining social media, news, and market psychology.
                Real-time emotional intelligence for institutional-grade decision making.
              </Typography>
            </Box>
          </Box>

          <Box display="flex" alignItems="center" gap={2}>
            <Box display="flex" gap={1}>
              {['1H', '4H', '24H', '7D'].map((period) => (
                <Chip
                  key={period}
                  label={period}
                  onClick={() => setSelectedTimeframe(period as any)}
                  sx={{
                    cursor: 'pointer',
                    bgcolor: selectedTimeframe === period ? 'rgba(236, 72, 153, 0.2)' : 'rgba(255,255,255,0.05)',
                    color: selectedTimeframe === period ? '#ec4899' : 'text.secondary',
                    fontWeight: selectedTimeframe === period ? 700 : 500,
                    '&:hover': {
                      bgcolor: 'rgba(236, 72, 153, 0.1)',
                    },
                  }}
                />
              ))}
            </Box>

            <Tooltip title="Refresh Sentiment Data" arrow>
              <IconButton
                onClick={handleRefresh}
                disabled={loading}
                sx={{
                  bgcolor: 'rgba(236, 72, 153, 0.1)',
                  color: '#ec4899',
                  '&:hover': {
                    bgcolor: 'rgba(236, 72, 153, 0.2)',
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
          Last updated: {lastUpdate.toLocaleString()} • AI-powered sentiment analysis
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Overall Sentiment Dashboard */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(236, 72, 153, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#ec4899' }}>
                📊 Overall Market Sentiment
              </Typography>

              <Box sx={{ textAlign: 'center', mb: 4 }}>
                <Box
                  sx={{
                    width: 120,
                    height: 120,
                    borderRadius: '50%',
                    background: `conic-gradient(${getSentimentColor(sentimentHistory[sentimentHistory.length - 1].overall)} ${sentimentHistory[sentimentHistory.length - 1].overall}%, rgba(255,255,255,0.1) 0deg)`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    mx: 'auto',
                    mb: 2,
                    position: 'relative',
                  }}
                >
                  <Box
                    sx={{
                      width: 100,
                      height: 100,
                      borderRadius: '50%',
                      bgcolor: 'rgba(30, 41, 59, 0.8)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Typography variant="h3" sx={{ fontWeight: 900, color: getSentimentColor(sentimentHistory[sentimentHistory.length - 1].overall) }}>
                      {sentimentHistory[sentimentHistory.length - 1].overall}
                    </Typography>
                  </Box>
                </Box>
                <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
                  {getSentimentLabel(sentimentHistory[sentimentHistory.length - 1].overall)}
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  Market sentiment score (0-100)
                </Typography>
              </Box>

              {/* Sentiment Breakdown */}
              <Grid container spacing={2}>
                {[
                  { label: 'Social Media', value: sentimentHistory[sentimentHistory.length - 1].social, color: '#8b5cf6' },
                  { label: 'News Flow', value: sentimentHistory[sentimentHistory.length - 1].news, color: '#f59e0b' },
                  { label: 'Technical', value: sentimentHistory[sentimentHistory.length - 1].technical, color: '#06b6d4' },
                  { label: 'Fear & Greed', value: sentimentHistory[sentimentHistory.length - 1].fearGreed, color: '#ec4899' },
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
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                        {metric.label}
                      </Typography>
                      <Box display="flex" alignItems="center" gap={1} mb={1}>
                        <Typography variant="h6" sx={{ fontWeight: 700, color: metric.color }}>
                          {metric.value}
                        </Typography>
                        <Chip
                          label={getSentimentLabel(metric.value)}
                          size="small"
                          sx={{
                            height: 18,
                            fontSize: '0.6rem',
                            bgcolor: `${metric.color}20`,
                            color: metric.color,
                          }}
                        />
                      </Box>
                      <LinearProgress
                        variant="determinate"
                        value={metric.value}
                        sx={{
                          height: 4,
                          borderRadius: 2,
                          bgcolor: 'rgba(255,255,255,0.1)',
                          '& .MuiLinearProgress-bar': {
                            bgcolor: metric.color,
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

        {/* Sentiment Timeline */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(168, 85, 247, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#8b5cf6' }}>
                📈 Sentiment Evolution
              </Typography>

              <Box sx={{ height: 300 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={sentimentHistory}>
                    <defs>
                      <linearGradient id="socialGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="newsGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="technicalGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="timestamp" stroke="#888" fontSize={12} />
                    <YAxis stroke="#888" fontSize={12} domain={[0, 100]} />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: '#1a1a1a',
                        border: '1px solid #333',
                        borderRadius: 8,
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="social"
                      stackId="1"
                      stroke="#8b5cf6"
                      fill="url(#socialGradient)"
                      name="Social"
                    />
                    <Area
                      type="monotone"
                      dataKey="news"
                      stackId="1"
                      stroke="#f59e0b"
                      fill="url(#newsGradient)"
                      name="News"
                    />
                    <Area
                      type="monotone"
                      dataKey="technical"
                      stackId="1"
                      stroke="#06b6d4"
                      fill="url(#technicalGradient)"
                      name="Technical"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </Box>

              <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', mt: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: '#8b5cf6' }} />
                  <Typography variant="caption">Social</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: '#f59e0b' }} />
                  <Typography variant="caption">News</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: '#06b6d4' }} />
                  <Typography variant="caption">Technical</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Social Media Sentiment */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(59, 130, 246, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#3b82f6' }}>
                🌐 Social Media Sentiment
              </Typography>

              <Box sx={{ mb: 3 }}>
                <Box sx={{ height: 200, mb: 2 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={40}
                        outerRadius={80}
                        paddingAngle={5}
                        dataKey="value"
                      >
                        {pieData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
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
                                  {data.name}
                                </Typography>
                                <Typography variant="body2">
                                  Sentiment: {data.value}
                                </Typography>
                              </Box>
                            );
                          }
                          return null;
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </Box>

                {socialMetrics.map((platform, index) => (
                  <Box key={index} sx={{ mb: 2 }}>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Avatar sx={{ width: 24, height: 24, bgcolor: `${getSentimentColor(platform.sentiment)}20` }}>
                          {platform.icon}
                        </Avatar>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {platform.platform}
                        </Typography>
                      </Box>
                      <Typography variant="body2" sx={{ fontWeight: 700, color: getSentimentColor(platform.sentiment) }}>
                        {platform.sentiment}%
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={platform.sentiment}
                      sx={{
                        height: 6,
                        borderRadius: 3,
                        bgcolor: 'rgba(255,255,255,0.1)',
                        '& .MuiLinearProgress-bar': {
                          bgcolor: getSentimentColor(platform.sentiment),
                          borderRadius: 3,
                        },
                      }}
                    />
                    <Typography variant="caption" sx={{ color: 'text.secondary', mt: 0.5, display: 'block' }}>
                      {platform.mentions.toLocaleString()} mentions • {platform.volume.toLocaleString()} posts
                    </Typography>
                  </Box>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* News Analysis & Market Psychology */}
        <Grid item xs={12} lg={6}>
          <Card sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(16, 185, 129, 0.2)',
            borderRadius: '20px',
          }}>
            <CardContent sx={{ p: 4 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, color: '#10b981' }}>
                📰 News Analysis & Market Psychology
              </Typography>

              {/* News Headlines */}
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2, color: '#10b981' }}>
                  Latest High-Impact News
                </Typography>
                <Box sx={{ maxHeight: 200, overflow: 'auto' }}>
                  {newsAnalysis.map((news, index) => (
                    <Box key={index} sx={{ mb: 2, p: 2, bgcolor: 'rgba(30, 41, 59, 0.4)', borderRadius: 2 }}>
                      <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
                        <Typography variant="body2" sx={{ fontWeight: 600, flex: 1, mr: 2 }}>
                          {news.title}
                        </Typography>
                        <Chip
                          label={news.impact.toUpperCase()}
                          size="small"
                          sx={{
                            height: 18,
                            fontSize: '0.6rem',
                            bgcolor: `${getImpactColor(news.impact)}20`,
                            color: getImpactColor(news.impact),
                            fontWeight: 700,
                          }}
                        />
                      </Box>
                      <Box display="flex" justifyContent="space-between" alignItems="center">
                        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                          {news.source} • {news.timestamp}
                        </Typography>
                        <Box display="flex" alignItems="center" gap={1}>
                          <SentimentSatisfied sx={{ fontSize: 14, color: getSentimentColor(news.sentiment) }} />
                          <Typography variant="caption" sx={{ fontWeight: 600, color: getSentimentColor(news.sentiment) }}>
                            {news.sentiment}%
                          </Typography>
                        </Box>
                      </Box>
                    </Box>
                  ))}
                </Box>
              </Box>

              <Divider sx={{ my: 3, bgcolor: 'rgba(148, 163, 184, 0.2)' }} />

              {/* Market Psychology */}
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2, color: '#10b981' }}>
                🧠 Market Psychology Indicators
              </Typography>
              <Grid container spacing={2}>
                {[
                  { label: 'Fear & Greed Index', value: marketPsychology.fearGreed, unit: '/100', color: getSentimentColor(marketPsychology.fearGreed) },
                  { label: 'Put/Call Ratio', value: marketPsychology.putCallRatio, unit: '', color: marketPsychology.putCallRatio > 1 ? '#ef4444' : '#10b981' },
                  { label: 'VIX Level', value: marketPsychology.vixLevel, unit: '%', color: marketPsychology.vixLevel > 20 ? '#ef4444' : '#10b981' },
                  { label: 'Institutional Flow', value: marketPsychology.institutionalFlow, unit: 'B USD', color: '#06b6d4' },
                ].map((metric, index) => (
                  <Grid item xs={6} key={index}>
                    <Box
                      sx={{
                        p: 2,
                        borderRadius: 2,
                        bgcolor: 'rgba(30, 41, 59, 0.4)',
                        border: '1px solid rgba(148, 163, 184, 0.1)',
                        textAlign: 'center',
                      }}
                    >
                      <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                        {metric.label}
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 700, color: metric.color, mb: 0.5 }}>
                        {metric.value}{metric.unit}
                      </Typography>
                      <Chip
                        label={metric.value > 50 ? 'High' : metric.value > 25 ? 'Medium' : 'Low'}
                        size="small"
                        sx={{
                          height: 16,
                          fontSize: '0.6rem',
                          bgcolor: `${metric.color}20`,
                          color: metric.color,
                        }}
                      />
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

export default SentimentAnalysis;

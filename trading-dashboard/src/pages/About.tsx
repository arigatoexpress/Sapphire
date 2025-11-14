import React from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, Chip, Divider } from '@mui/material';
import RegulatoryDisclaimer from '../components/RegulatoryDisclaimer';
import {
  Psychology,
  Speed,
  Shield,
  CloudQueue,
  Analytics,
  TrendingUp,
  Security,
  Verified,
  Timeline,
  Memory,
  Bolt,
  SmartToy,
} from '@mui/icons-material';

const About: React.FC = () => {
  const features = [
    {
      icon: <Psychology sx={{ fontSize: 40, color: '#8b5cf6' }} />,
      title: '6 Specialized AI Agents',
      description: 'Each agent powered by Google\'s latest Gemini models, optimized for specific market analysis tasks. From momentum detection to sentiment analysis, each agent brings unique intelligence to trading decisions.',
      details: [
        'Trend Momentum Agent: Gemini 2.0 Flash Experimental for fast momentum signals',
        'Strategy Optimization Agent: Gemini Experimental 1206 for advanced reasoning',
        'Financial Sentiment Agent: Gemini 2.0 Flash Experimental for NLP analysis',
        'Market Prediction Agent: Gemini Experimental 1206 for time series forecasting',
        'Volume Microstructure Agent: Codey for mathematical volume analysis',
        'VPIN HFT Agent: Gemini 2.0 Flash Experimental for high-frequency order flow analysis'
      ]
    },
    {
      icon: <Speed sx={{ fontSize: 40, color: '#06b6d4' }} />,
      title: 'Real-Time Market Analysis',
      description: 'Direct integration with Aster DEX Futures API provides live market data, order book depth, and real-time price streaming for perpetual futures contracts.',
      details: [
        'Live price feeds for BTCUSDT, ETHUSDT, and other perpetual futures',
        'Real-time order book depth analysis for liquidity assessment',
        'Sub-second decision latency with optimized async processing',
        'Automated position management with intelligent entry/exit timing'
      ]
    },
    {
      icon: <Shield sx={{ fontSize: 40, color: '#10b981' }} />,
      title: 'Institutional-Grade Risk Management',
      description: 'Multi-layer risk controls with real-time portfolio analytics, automated position sizing, and dynamic risk parameter adjustment based on market conditions.',
      details: [
        'Value at Risk (VaR) and Expected Shortfall calculations',
        'Sharpe and Sortino ratio tracking for risk-adjusted returns',
        'Maximum drawdown monitoring and correlation analysis',
        'ATR-based stop losses with liquidation prevention',
        'Per-agent capital limits and leverage controls'
      ]
    },
    {
      icon: <CloudQueue sx={{ fontSize: 40, color: '#8b5cf6' }} />,
      title: 'Cloud-Native Architecture',
      description: 'Built on Google Cloud Platform with Kubernetes orchestration, enabling automatic scaling, high availability, and cost-optimized resource allocation.',
      details: [
        'Kubernetes-based microservices architecture',
        'Automatic horizontal pod autoscaling',
        'Multi-level caching for performance optimization',
        'Event-driven processing with Pub/Sub messaging',
        'Distributed system with fault tolerance'
      ]
    },
    {
      icon: <Security sx={{ fontSize: 40, color: '#f59e0b' }} />,
      title: 'Enterprise Security & Compliance',
      description: 'Comprehensive security measures including API authentication, audit trails, data retention policies, and regulatory compliance monitoring.',
      details: [
        'HMAC SHA256 API authentication with IP whitelisting',
        'Tamper-proof transaction logging and audit trails',
        'Automated compliance monitoring and reporting',
        'Multi-level access controls and data encryption',
        'Secure credential management via Kubernetes secrets'
      ]
    },
    {
      icon: <Bolt sx={{ fontSize: 40, color: '#ec4899' }} />,
      title: 'Self-Healing & Resilient',
      description: 'Advanced fault tolerance with circuit breakers, automatic recovery systems, and graceful degradation to maintain operation during component failures.',
      details: [
        'Circuit breaker protection for automatic failure isolation',
        'Self-healing architecture with automated recovery',
        'Graceful degradation maintains core functionality',
        'Comprehensive health monitoring and alerting',
        '24/7 system health tracking with Prometheus metrics'
      ]
    }
  ];

  const stats = [
    { label: 'AI Agents', value: '6', description: 'Specialized trading agents' },
    { label: 'Live Capital', value: '$3,000', description: 'Active trading funds' },
    { label: 'AI Models', value: '3', description: 'Gemini model variants' },
    { label: 'Market Data', value: 'Real-Time', description: 'Aster DEX integration' },
  ];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box sx={{ textAlign: 'center', mb: 6 }}>
        <Typography
          variant="h2"
          sx={{
            fontWeight: 900,
            mb: 2,
            fontSize: { xs: '2rem', md: '3rem' },
            background: 'linear-gradient(135deg, #0EA5E9 0%, #8B5CF6 50%, #0EA5E9 100%)',
            backgroundSize: '200% 200%',
            backgroundClip: 'text',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            animation: 'gradientShift 3s ease infinite',
            '@keyframes gradientShift': {
              '0%, 100%': { backgroundPosition: '0% 50%' },
              '50%': { backgroundPosition: '100% 50%' },
            },
          }}
        >
          Sapphire AI Trading System
        </Typography>
        <Typography
          variant="h6"
          sx={{
            color: 'text.secondary',
            maxWidth: '900px',
            mx: 'auto',
            lineHeight: 1.8,
            mb: 4,
            fontSize: { xs: '1rem', md: '1.125rem' },
            fontWeight: 400,
          }}
        >
          An enterprise-grade AI-powered algorithmic trading platform designed for institutional performance. 
          Built on Google Cloud Platform with cutting-edge Gemini AI models, the system executes automated 
          trades on Aster DEX with sophisticated risk management, real-time market analysis, and multi-agent 
          collaboration through the Multi-Component Protocol (MCP).
        </Typography>

        {/* Key Stats */}
        <Grid container spacing={3} sx={{ mb: 6 }}>
          {stats.map((stat, index) => (
            <Grid item xs={6} md={3} key={index}>
              <Card sx={{
                background: 'rgba(255, 255, 255, 0.08)',
                backdropFilter: 'blur(10px)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: 3,
                p: 2
              }}>
                <Typography variant="h3" sx={{ fontWeight: 900, color: 'primary.main', mb: 0.5 }}>
                  {stat.value}
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.primary', mb: 0.5 }}>
                  {stat.label}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {stat.description}
                </Typography>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>

      {/* Features Grid */}
      <Grid container spacing={4}>
        {features.map((feature, index) => (
          <Grid item xs={12} md={6} key={index}>
            <Card sx={{
              height: '100%',
              background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
              backdropFilter: 'blur(20px)',
              border: '1px solid rgba(139, 92, 246, 0.2)',
              borderRadius: 3,
              transition: 'all 0.3s ease',
              '&:hover': {
                transform: 'translateY(-4px)',
                border: '1px solid rgba(139, 92, 246, 0.4)',
                boxShadow: '0 20px 40px rgba(139, 92, 246, 0.1)',
              }
            }}>
              <CardContent sx={{ p: 3 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  {feature.icon}
                  <Typography variant="h5" sx={{ fontWeight: 700, ml: 2 }}>
                    {feature.title}
                  </Typography>
                </Box>
                <Typography variant="body1" sx={{ color: 'text.secondary', mb: 3, lineHeight: 1.7 }}>
                  {feature.description}
                </Typography>
                <Divider sx={{ mb: 2, borderColor: 'rgba(255,255,255,0.1)' }} />
                <Box>
                  {feature.details.map((detail, idx) => (
                    <Box key={idx} sx={{ mb: 1.5, display: 'flex', alignItems: 'flex-start' }}>
                      <Typography variant="body2" sx={{ color: 'text.secondary', lineHeight: 1.6, pl: 1 }}>
                        • {detail}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Technology Stack */}
      <Box sx={{ mt: 6, p: 4, borderRadius: 3, background: 'rgba(30, 41, 59, 0.4)', border: '1px solid rgba(139, 92, 246, 0.2)' }}>
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, textAlign: 'center' }}>
          Technology Stack
        </Typography>
        <Grid container spacing={2}>
          {[
            'Google Cloud Platform (GKE)',
            'Kubernetes Orchestration',
            'Gemini AI Models (2.0 Flash Exp, Exp-1206, Codey)',
            'Aster DEX Futures API',
            'Python Async/Await',
            'FastAPI & Uvicorn',
            'Redis Caching',
            'Prometheus Monitoring',
            'Firebase Hosting',
            'React + TypeScript',
            'Material-UI',
            'BigQuery Analytics'
          ].map((tech, index) => (
            <Grid item xs={6} sm={4} md={3} key={index}>
              <Chip
                label={tech}
                sx={{
                  bgcolor: 'rgba(139, 92, 246, 0.1)',
                  color: '#8b5cf6',
                  border: '1px solid rgba(139, 92, 246, 0.3)',
                  width: '100%',
                  '&:hover': {
                    bgcolor: 'rgba(139, 92, 246, 0.2)',
                  }
                }}
              />
            </Grid>
          ))}
        </Grid>
      </Box>

      {/* Regulatory Disclaimer */}
      <Box sx={{ mt: 6 }}>
        <RegulatoryDisclaimer />
      </Box>
    </Container>
  );
};

export default About;


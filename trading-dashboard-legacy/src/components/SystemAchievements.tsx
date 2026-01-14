import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  Avatar,
  LinearProgress,
  Badge,
} from '@mui/material';
import {
  Psychology,
  TrendingUp,
  Assessment,
  Memory,
  Speed,
  SmartToy,
  Analytics,
  EmojiEvents,
  Whatshot,
  Star,
  Bolt,
  Shield,
  CloudQueue,
  Security,
  Timeline,
  Verified,
  Rocket,
  PrecisionManufacturing,
  Biotech,
  Psychology as BrainIcon,
  MilitaryTech,
  Architecture,
  Engineering,
} from '@mui/icons-material';

const SystemAchievements: React.FC = () => {
  const achievements = [
    {
      category: "AI & Machine Learning",
      icon: <BrainIcon sx={{ color: '#8b5cf6' }} />,
      items: [
        { name: "6-Specialized AI Agent Ensemble", description: "Each agent optimized for specific market analysis: Momentum (Gemini 2.0 Flash Exp), Strategy (Gemini Exp-1206), Sentiment (Gemini 2.0 Flash Exp), Prediction (Gemini Exp-1206), Volume (Codey), VPIN HFT (Gemini 2.0 Flash Exp)", status: "active" },
        { name: "Latest Gemini AI Models", description: "Powered by Google's latest experimental models: Gemini 2.0 Flash Experimental for speed, Gemini Experimental 1206 for advanced reasoning, Codey for mathematical analysis", status: "active" },
        { name: "Multi-Component Protocol (MCP)", description: "Real-time inter-agent communication system enabling collaborative trading decisions and shared market intelligence", status: "active" },
        { name: "Elastic Resource Scaling", description: "Intelligent resource allocation with automatic scaling based on market volatility and trading activity", status: "active" },
        { name: "Model-Specific Optimization", description: "Each agent configured with optimal temperature, token limits, and inference parameters for maximum performance", status: "active" },
        { name: "Circuit Breaker Protection", description: "Multi-layer fault tolerance with automatic failure isolation and graceful degradation", status: "active" },
      ]
    },
    {
      category: "Enterprise Performance",
      icon: <Bolt sx={{ color: '#06b6d4' }} />,
      items: [
        { name: "Sub-Second Decision Latency", description: "Real-time market analysis and trade execution with optimized async processing pipelines", status: "active" },
        { name: "Kubernetes Orchestration", description: "Cloud-native deployment on GKE with automatic scaling and resource optimization", status: "active" },
        { name: "Cost-Optimized AI Inference", description: "Efficient model deployment with selective acceleration for high-frequency operations", status: "active" },
        { name: "Multi-Level Caching", description: "Intelligent caching layers for market data, AI responses, and trading signals to minimize latency", status: "active" },
        { name: "Live Trading Capital", description: "$500 equity allocation per agent for leveraged perpetual futures trading on Aster DEX", status: "active" },
      ]
    },
    {
      category: "Risk Management",
      icon: <Shield sx={{ color: '#10b981' }} />,
      items: [
        { name: "Advanced Portfolio Analytics", description: "Real-time calculation of Value at Risk (VaR), Sharpe/Sortino ratios, maximum drawdown, and correlation analysis", status: "active" },
        { name: "Real-time Risk Monitoring", description: "Continuous portfolio exposure assessment with per-agent capital limits and position sizing controls", status: "active" },
        { name: "Market Regime Adaptation", description: "Dynamic risk parameter adjustment based on volatility regimes and market conditions", status: "active" },
        { name: "Automated Risk Controls", description: "Intelligent position management with ATR-based stops, leverage limits, and liquidation prevention", status: "active" },
      ]
    },
    {
      category: "System Resilience",
      icon: <Security sx={{ color: '#f59e0b' }} />,
      items: [
        { name: "Circuit Breaker Protection", description: "Automatic failure isolation", status: "active" },
        { name: "Self-Healing Architecture", description: "Automated recovery systems", status: "active" },
        { name: "Graceful Degradation", description: "Maintains operation during failures", status: "active" },
        { name: "Comprehensive Monitoring", description: "24/7 system health tracking", status: "active" },
      ]
    },
    {
      category: "Live Market Data Integration",
      icon: <Timeline sx={{ color: '#06b6d4' }} />,
      items: [
        { name: "Aster DEX Official API", description: "Direct integration with Aster DEX Futures API for live market data and trade execution", status: "active" },
        { name: "Real-Time Price Data", description: "Live price streaming for perpetual futures contracts with real-time order book updates", status: "active" },
        { name: "Order Book Depth Analysis", description: "Full market depth analysis for liquidity assessment and optimal entry/exit timing", status: "active" },
        { name: "Secure Authentication", description: "Enterprise-grade API authentication with HMAC SHA256 signing and IP whitelisting", status: "active" },
      ]
    },
    {
      category: "Cloud-Native Architecture",
      icon: <CloudQueue sx={{ color: '#8b5cf6' }} />,
      items: [
        { name: "Kubernetes Orchestration", description: "Container-native deployment", status: "active" },
        { name: "Microservices Design", description: "Modular, scalable architecture", status: "active" },
        { name: "Event-Driven Processing", description: "Real-time data pipelines", status: "active" },
        { name: "Distributed Caching", description: "High-performance data access", status: "active" },
      ]
    },
    {
      category: "Regulatory Compliance",
      icon: <Verified sx={{ color: '#059669' }} />,
      items: [
        { name: "Audit Trail Integrity", description: "Tamper-proof transaction logging", status: "active" },
        { name: "Automated Compliance", description: "Real-time regulatory monitoring", status: "active" },
        { name: "Data Retention Policies", description: "Secure record management", status: "active" },
        { name: "Access Control Framework", description: "Multi-level security controls", status: "active" },
      ]
    }
  ];

  return (
    <Box sx={{ mb: 4 }}>
      <Typography
        variant="h4"
        sx={{
          mb: 3,
          fontWeight: 700,
          textAlign: 'center',
          background: 'linear-gradient(135deg, #8b5cf6, #ec4899, #06b6d4)',
          backgroundClip: 'text',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
        }}
      >
        🏆 System Achievements & Capabilities
      </Typography>

        <Typography
          variant="body1"
          sx={{
            mb: 4,
            textAlign: 'center',
            color: 'text.secondary',
            maxWidth: '900px',
            mx: 'auto',
            lineHeight: 1.7,
            fontSize: '1.1rem'
          }}
        >
          Enterprise-grade algorithmic trading platform featuring cutting-edge AI technology,
          military-level resilience, and institutional-grade risk management.
          <br />
          <Box sx={{ mt: 2, fontSize: '0.9rem', opacity: 0.8 }}>
            Built with 6 specialized Gemini AI agents, real-time Aster DEX integration, and comprehensive risk controls.
          </Box>
        </Typography>

      <Grid container spacing={3}>
        {achievements.map((category, categoryIndex) => (
          <Grid item xs={12} md={6} lg={4} key={categoryIndex}>
            <Card
              sx={{
                height: '100%',
                background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.4))',
                backdropFilter: 'blur(20px)',
                border: '1px solid rgba(139, 92, 246, 0.2)',
                borderRadius: '20px',
                transition: 'all 0.3s ease',
                '&:hover': {
                  transform: 'translateY(-4px)',
                  border: '1px solid rgba(139, 92, 246, 0.4)',
                  boxShadow: '0 20px 40px rgba(139, 92, 246, 0.1)',
                }
              }}
            >
              <CardContent sx={{ p: 3 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
                  <Avatar
                    sx={{
                      bgcolor: 'rgba(139, 92, 246, 0.1)',
                      border: '1px solid rgba(139, 92, 246, 0.3)',
                      mr: 2,
                      width: 48,
                      height: 48
                    }}
                  >
                    {category.icon}
                  </Avatar>
                  <Box>
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
                      {category.category}
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                      {category.items.length} Advanced Features
                    </Typography>
                  </Box>
                </Box>

                <Box sx={{ spaceY: 2 }}>
                  {category.items.map((item, itemIndex) => (
                    <Box
                      key={itemIndex}
                      sx={{
                        mb: 2,
                        p: 2,
                        borderRadius: 2,
                        bgcolor: 'rgba(30, 41, 59, 0.3)',
                        border: '1px solid rgba(148, 163, 184, 0.1)',
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {item.name}
                        </Typography>
                        <Chip
                          size="small"
                          label={item.status}
                          sx={{
                            bgcolor: item.status === 'active' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                            color: item.status === 'active' ? '#10b981' : '#f59e0b',
                            fontSize: '0.7rem',
                            height: 20
                          }}
                        />
                      </Box>
                      <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1.4 }}>
                        {item.description}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* System Status Overview */}
      <Box sx={{ mt: 4 }}>
        <Card
          sx={{
            background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.9), rgba(30, 41, 59, 0.6))',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(6, 182, 212, 0.3)',
            borderRadius: '20px',
          }}
        >
          <CardContent sx={{ p: 4 }}>
            <Typography
              variant="h5"
              sx={{
                mb: 3,
                fontWeight: 700,
                textAlign: 'center',
                background: 'linear-gradient(135deg, #06b6d4, #8b5cf6)',
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              🚀 Enterprise-Grade Trading Platform
            </Typography>

            <Grid container spacing={3}>
              <Grid item xs={12} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h3" sx={{ fontWeight: 900, color: '#10b981', mb: 1 }}>
                    6
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                    Specialized AI Agents
                  </Typography>
                </Box>
              </Grid>

              <Grid item xs={12} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h3" sx={{ fontWeight: 900, color: '#06b6d4', mb: 1 }}>
                    Real-Time
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                    Market Analysis
                  </Typography>
                </Box>
              </Grid>

              <Grid item xs={12} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h3" sx={{ fontWeight: 900, color: '#8b5cf6', mb: 1 }}>
                    $3,000
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                    Live Trading Capital
                  </Typography>
                </Box>
              </Grid>

              <Grid item xs={12} md={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h3" sx={{ fontWeight: 900, color: '#f59e0b', mb: 1 }}>
                    Multi-Layer
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                    Risk Management
                  </Typography>
                </Box>
              </Grid>
            </Grid>

            <Box sx={{ mt: 4, p: 3, borderRadius: 2, bgcolor: 'rgba(30, 41, 59, 0.4)' }}>
              <Typography variant="body1" sx={{ textAlign: 'center', fontWeight: 600, mb: 2 }}>
                🎯 Production-Ready Features
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'center' }}>
                {[
                  'Real-time AI Analysis',
                  'Advanced Risk Management',
                  'Self-Healing Architecture',
                  'Enterprise Security',
                  'Regulatory Compliance',
                  'High-Frequency Trading',
                  'Cloud-Native Design',
                  '24/7 Monitoring'
                ].map((feature, index) => (
                  <Chip
                    key={index}
                    label={feature}
                    size="small"
                    sx={{
                      bgcolor: 'rgba(139, 92, 246, 0.1)',
                      color: '#8b5cf6',
                      border: '1px solid rgba(139, 92, 246, 0.3)',
                      '&:hover': {
                        bgcolor: 'rgba(139, 92, 246, 0.2)',
                      }
                    }}
                  />
                ))}
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
};

export default SystemAchievements;

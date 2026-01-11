import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Avatar,
  Chip,
  LinearProgress,
  Badge,
  CircularProgress,
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
} from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';

// Advanced Agent Descriptions and Features
const getAgentRoleDescription = (agentType: string): string => {
  const descriptions: Record<string, string> = {
    'trend-momentum-agent': '🎯 Momentum Analyzer - Gemini 2.0 Flash Exp',
    'strategy-optimization-agent': '🧠 Strategy Optimizer - Gemini Exp-1206',
    'financial-sentiment-agent': '💭 Sentiment Analyst - Gemini 2.0 Flash Exp',
    'market-prediction-agent': '🔮 Market Predictor - Gemini Exp-1206',
    'volume-microstructure-agent': '📊 Volume Analyst - Codey Model',
    'vpin-hft': '⚡ VPIN HFT Agent - Gemini 2.0 Flash Exp'
  };
  return descriptions[agentType] || 'Unknown Agent';
};

const getAgentAdvancedFeatures = (agentType: string): string => {
  const features: Record<string, string> = {
    'trend-momentum-agent': 'Fast momentum detection using TPU-optimized inference. Analyzes price action, volume, and technical indicators for short-term trading signals.',
    'strategy-optimization-agent': 'Advanced reasoning for complex strategy optimization. Uses experimental Gemini models for portfolio rebalancing and risk-adjusted position sizing.',
    'financial-sentiment-agent': 'Real-time NLP analysis of news, social media, and financial reports. Detects market psychology shifts and sentiment-driven opportunities.',
    'market-prediction-agent': 'Time series forecasting with advanced ML models. Predicts price movements using historical patterns and macroeconomic indicators.',
    'volume-microstructure-agent': 'High-frequency volume analysis using Codey for mathematical processing. Detects order book imbalances and institutional activity.',
    'vpin-hft': 'Ultra-fast order flow toxicity detection using Gemini 2.0 Flash Exp. Analyzes market microstructure for high-frequency trading signals.'
  };
  return features[agentType] || 'Advanced AI-powered trading agent with specialized market analysis capabilities.';
};

interface AgentModelCardProps {
  agent: {
    agent_id: string;
    agent_type: 'trend-momentum-agent' | 'strategy-optimization-agent' | 'financial-sentiment-agent' | 'market-prediction-agent' | 'volume-microstructure-agent' | 'vpin-hft';
    agent_name: string;
    activity_score: number;
    communication_count: number;
    trading_count: number;
    last_activity: string;
    participation_threshold: number;
    specialization: string;
    color: string;
    status: 'active' | 'idle' | 'analyzing' | 'trading';
    gpu_utilization?: number;
    memory_usage?: number;
  };
  onAgentClick?: (agentId: string) => void;
}

const AgentModelCard: React.FC<AgentModelCardProps> = ({ agent, onAgentClick }) => {

  const getAgentIcon = () => {
    switch (agent.agent_type) {
      case 'trend-momentum-agent': return '🎯';
      case 'strategy-optimization-agent': return '🧠';
      case 'financial-sentiment-agent': return '💭';
      case 'market-prediction-agent': return '🔮';
      case 'volume-microstructure-agent': return '📊';
      case 'vpin-hft': return '⚡';
      default: return '🎯';
    }
  };

  const getStatusIcon = () => {
    switch (agent.status) {
      case 'trading': return <Bolt sx={{ fontSize: 16, color: '#10b981' }} />;
      case 'analyzing': return <Analytics sx={{ fontSize: 16, color: '#f59e0b' }} />;
      case 'active': return <SmartToy sx={{ fontSize: 16, color: '#8b5cf6' }} />;
      default: return <Shield sx={{ fontSize: 16, color: '#6b7280' }} />;
    }
  };

  const getSpecializationIcon = () => {
    const spec = agent.specialization || '';
    if (spec.includes('Momentum')) return <TrendingUp sx={{ fontSize: 14 }} />;
    if (spec.includes('Risk')) return <Shield sx={{ fontSize: 14 }} />;
    if (spec.includes('Financial')) return <Assessment sx={{ fontSize: 14 }} />;
    if (spec.includes('Time Series')) return <Analytics sx={{ fontSize: 14 }} />;
    if (spec.includes('VPIN')) return <Memory sx={{ fontSize: 14 }} />;
    if (spec.includes('Algorithmic')) return <Speed sx={{ fontSize: 14 }} />;
    if (spec.includes('Market Making')) return <Psychology sx={{ fontSize: 14 }} />;
    return <SmartToy sx={{ fontSize: 14 }} />;
  };

  const getPerformanceBadge = () => {
    const score = agent.activity_score;
    if (score >= 0.9) return { icon: <EmojiEvents />, label: '🏆 Elite', color: '#ffd700', glow: true };
    if (score >= 0.8) return { icon: <Star />, label: '⭐ Pro', color: '#c0c0c0', glow: false };
    if (score >= 0.7) return { icon: <Whatshot />, label: '🔥 Active', color: '#ff6b35', glow: false };
    return { icon: <SmartToy />, label: '🧠 Learning', color: '#8b5cf6', glow: false };
  };

  const performanceBadge = getPerformanceBadge();

  return (
    <Card
      sx={{
        height: '100%',
        cursor: 'pointer',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        border: '1px solid',
        borderColor: 'divider',
        background: `linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(30, 41, 59, 0.4) 100%)`,
        backdropFilter: 'blur(16px)',
        position: 'relative',
        overflow: 'hidden',
        ...(performanceBadge.glow && {
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: `linear-gradient(45deg, ${agent.color}10, transparent, ${agent.color}10)`,
            animation: 'shimmer 3s ease-in-out infinite',
            pointerEvents: 'none',
          },
          '@keyframes shimmer': {
            '0%': { transform: 'translateX(-100%)' },
            '100%': { transform: 'translateX(100%)' },
          },
        }),
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: `0 12px 24px ${agent.color}30`,
          borderColor: agent.color,
        },
      }}
      onClick={() => onAgentClick?.(agent.agent_id)}
    >
      <CardContent sx={{ p: 3 }}>
        {/* Header */}
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
          <Box display="flex" alignItems="center" gap={2}>
            <Badge
              overlap="circular"
              anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
              badgeContent={getStatusIcon()}
            >
              <Avatar
                sx={{
                  width: 48,
                  height: 48,
                  bgcolor: `${agent.color}20`,
                  border: `2px solid ${agent.color}`,
                  fontSize: '1.5rem',
                  boxShadow: `0 0 16px ${agent.color}40`,
                }}
              >
                {getAgentIcon()}
              </Avatar>
            </Badge>
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1rem' }}>
                {agent.agent_name}
              </Typography>
              <Box display="flex" alignItems="center" gap={1}>
                {getSpecializationIcon()}
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 500 }}>
                  {agent.specialization.split(' & ')[0]}
                </Typography>
              </Box>
            </Box>
          </Box>

          <Box display="flex" flexDirection="column" alignItems="flex-end" gap={0.5}>
            <Chip
              icon={performanceBadge.icon}
              label={performanceBadge.label}
              size="small"
              sx={{
                height: 24,
                bgcolor: `${performanceBadge.color}20`,
                color: performanceBadge.color,
                border: `1px solid ${performanceBadge.color}40`,
                fontSize: '0.7rem',
                fontWeight: 600,
                ...(performanceBadge.glow && {
                  boxShadow: `0 0 12px ${performanceBadge.color}60`,
                  animation: 'eliteGlow 2s ease-in-out infinite alternate',
                  '@keyframes eliteGlow': {
                    '0%': { boxShadow: `0 0 8px ${performanceBadge.color}40` },
                    '100%': { boxShadow: `0 0 16px ${performanceBadge.color}80` },
                  },
                }),
              }}
            />
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
              {new Date(agent.last_activity).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </Typography>
          </Box>
        </Box>

        {/* Activity Score */}
        <Box sx={{ mb: 2 }}>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
            <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
              Activity Score
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, color: agent.color }}>
              {agent.activity_score.toFixed(1)}
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={(agent.activity_score / 10) * 100}
            sx={{
              height: 6,
              borderRadius: 3,
              bgcolor: 'rgba(255, 255, 255, 0.1)',
              '& .MuiLinearProgress-bar': {
                bgcolor: agent.color,
                borderRadius: 3,
              },
            }}
          />
        </Box>

        {/* Agent Role Description */}
        <Box sx={{ mb: 2, p: 1, bgcolor: 'rgba(139, 92, 246, 0.05)', borderRadius: 1, border: '1px solid rgba(139, 92, 246, 0.1)' }}>
          <Typography variant="caption" sx={{ fontSize: '0.7rem', fontWeight: 600, color: agent.color, mb: 0.5 }}>
            {getAgentRoleDescription(agent.agent_type)}
          </Typography>
          <Typography variant="caption" sx={{ fontSize: '0.65rem', color: 'text.secondary', lineHeight: 1.3 }}>
            {getAgentAdvancedFeatures(agent.agent_type)}
          </Typography>
        </Box>

        {/* Stats Grid */}
        <Grid container spacing={1} sx={{ mb: 2 }}>
          <Grid item xs={4}>
            <Box textAlign="center">
              <Typography variant="h6" sx={{ fontWeight: 700, color: agent.color, fontSize: '1rem' }}>
                {agent.trading_count}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                Trades
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={4}>
            <Box textAlign="center">
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#8b5cf6', fontSize: '1rem' }}>
                {agent.communication_count}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                Messages
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={4}>
            <Box textAlign="center">
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#f59e0b', fontSize: '1rem' }}>
                {agent.participation_threshold.toFixed(1)}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
                Threshold
              </Typography>
            </Box>
          </Grid>
        </Grid>

        {/* System Metrics */}
        {(agent.gpu_utilization || agent.memory_usage) && (
          <Box display="flex" gap={1} flexWrap="wrap">
            {agent.gpu_utilization && (
              <Chip
                label={`GPU: ${agent.gpu_utilization.toFixed(0)}%`}
                size="small"
                sx={{
                  height: 20,
                  bgcolor: 'rgba(245, 158, 11, 0.1)',
                  color: '#f59e0b',
                  fontSize: '0.65rem',
                  fontWeight: 600,
                }}
              />
            )}
            {agent.memory_usage && (
              <Chip
                label={`RAM: ${agent.memory_usage.toFixed(1)}GB`}
                size="small"
                sx={{
                  height: 20,
                  bgcolor: 'rgba(14, 165, 233, 0.1)',
                  color: '#0ea5e9',
                  fontSize: '0.65rem',
                  fontWeight: 600,
                }}
              />
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

const AgentModelCards: React.FC = () => {
  const { agentActivities, loading } = useTrading();
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [leaderboardMode, setLeaderboardMode] = useState(false);
  const [sortBy, setSortBy] = useState<'activity' | 'trades' | 'communication'>('activity');

  const handleAgentClick = (agentId: string) => {
    setSelectedAgent(selectedAgent === agentId ? null : agentId);
  };

  // Sort agents by performance for leaderboard
  const sortedAgents = [...agentActivities].sort((a, b) => {
    switch (sortBy) {
      case 'activity':
        return b.activity_score - a.activity_score;
      case 'trades':
        return b.trading_count - a.trading_count;
      case 'communication':
        return b.communication_count - a.communication_count;
      default:
        return b.activity_score - a.activity_score;
    }
  });

  const topPerformers = sortedAgents.slice(0, 3);
  const displayAgents = leaderboardMode ? sortedAgents : agentActivities;

  if (loading) {
    return (
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" sx={{ fontWeight: 600, mb: 3 }}>
          🤖 AI Agent Models
        </Typography>
        <Grid container spacing={3}>
          {[1, 2, 3, 4, 5, 6, 7].map((i) => (
            <Grid item xs={12} sm={6} md={4} lg={3} key={i}>
              <Card sx={{ height: 280 }}>
                <CardContent sx={{ p: 3, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CircularProgress size={40} />
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  }

  return (
    <Box sx={{ mb: 4 }}>
      {/* Enhanced Header with Leaderboard Controls */}
      <Box
        sx={{
          background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(236, 72, 153, 0.1))',
          border: '1px solid rgba(139, 92, 246, 0.2)',
          borderRadius: 3,
          p: 3,
          mb: 4,
          position: 'relative',
          overflow: 'hidden',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'radial-gradient(circle at 20% 80%, rgba(139, 92, 246, 0.05), transparent 50%)',
            pointerEvents: 'none',
          },
        }}
      >
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" sx={{ position: 'relative', zIndex: 1 }}>
          <Box display="flex" alignItems="center" gap={3}>
            <Box
              sx={{
                width: 60,
                height: 60,
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 8px 32px rgba(139, 92, 246, 0.3)',
              }}
            >
              <Psychology sx={{ fontSize: 28, color: 'white' }} />
            </Box>
            <Box>
              <Typography
                variant="h4"
                sx={{
                  fontWeight: 800,
                  background: 'linear-gradient(135deg, #8b5cf6, #ec4899, #06b6d4)',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  mb: 1,
                }}
              >
                🤖 Neural Trading Matrix
              </Typography>
              <Typography variant="body1" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                Enterprise-grade AI ensemble with 5 specialized agents using latest Google Gemini models:
                Trend Momentum Agent (Gemini 2.0 Flash Experimental), Strategy Optimization Agent (Gemini Experimental 1206),
                Financial Sentiment Agent (Gemini 2.0 Flash Experimental), Market Prediction Agent (Gemini Experimental 1206),
                and Volume Microstructure Agent (Codey).
                Advanced risk management, real-time coordination, and institutional-grade performance monitoring.
              </Typography>
            </Box>
          </Box>

          {/* Top Performers Showcase */}
          {topPerformers.length > 0 && (
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: '#ffd700', mb: 2 }}>
                🏆 Elite Performers
              </Typography>
              <Box display="flex" gap={1}>
                {topPerformers.slice(0, 3).map((agent, index) => (
                  <Box key={agent.agent_id} sx={{ textAlign: 'center' }}>
                    <Box
                      sx={{
                        width: 40,
                        height: 40,
                        borderRadius: '50%',
                        background: `linear-gradient(135deg, ${agent.color}, ${agent.color}80)`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        mb: 1,
                        boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                        position: 'relative',
                      }}
                    >
                      {index === 0 && <EmojiEvents sx={{ fontSize: 16, color: '#ffd700' }} />}
                      {index === 1 && <Star sx={{ fontSize: 16, color: '#c0c0c0' }} />}
                      {index === 2 && <Whatshot sx={{ fontSize: 16, color: '#cd7f32' }} />}
                      <Typography
                        variant="caption"
                        sx={{
                          position: 'absolute',
                          bottom: -8,
                          left: '50%',
                          transform: 'translateX(-50%)',
                          fontSize: '10px',
                          fontWeight: 700,
                          color: agent.color,
                        }}
                      >
                        {index + 1}
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </Box>
            </Box>
          )}
        </Box>

        {/* Control Panel */}
        <Box
          display="flex"
          gap={2}
          mt={3}
          sx={{
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Chip
            label={`${agentActivities.length} Active AI Agents`}
            sx={{
              bgcolor: 'rgba(6, 182, 212, 0.1)',
              color: '#06b6d4',
              fontWeight: 600,
              border: '1px solid rgba(6, 182, 212, 0.3)',
            }}
          />

          <Chip
            label={leaderboardMode ? "🏆 Ranked Mode" : "🎯 Standard View"}
            onClick={() => setLeaderboardMode(!leaderboardMode)}
            sx={{
              cursor: 'pointer',
              bgcolor: leaderboardMode ? 'rgba(255, 215, 0, 0.1)' : 'rgba(139, 92, 246, 0.1)',
              color: leaderboardMode ? '#ffd700' : '#8b5cf6',
              fontWeight: 600,
              border: `1px solid ${leaderboardMode ? 'rgba(255, 215, 0, 0.3)' : 'rgba(139, 92, 246, 0.3)'}`,
              '&:hover': {
                bgcolor: leaderboardMode ? 'rgba(255, 215, 0, 0.2)' : 'rgba(139, 92, 246, 0.2)',
              },
            }}
          />

          {leaderboardMode && (
            <Box display="flex" gap={1}>
              {[
                { key: 'activity', label: '⚡ Activity', color: '#06b6d4' },
                { key: 'trades', label: '📈 Trades', color: '#10b981' },
                { key: 'communication', label: '💬 Comm', color: '#8b5cf6' },
              ].map((option) => (
                <Chip
                  key={option.key}
                  label={option.label}
                  onClick={() => setSortBy(option.key as any)}
                  sx={{
                    cursor: 'pointer',
                    bgcolor: sortBy === option.key ? `${option.color}20` : 'rgba(255,255,255,0.05)',
                    color: sortBy === option.key ? option.color : 'text.secondary',
                    fontWeight: sortBy === option.key ? 700 : 500,
                    border: `1px solid ${sortBy === option.key ? option.color : 'rgba(255,255,255,0.1)'}`,
                    '&:hover': {
                      bgcolor: `${option.color}10`,
                    },
                  }}
                />
              ))}
            </Box>
          )}
        </Box>
      </Box>

      <Grid container spacing={3}>
        {displayAgents.map((agent, index) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={agent.agent_id}>
            <Box sx={{ position: 'relative' }}>
              {leaderboardMode && index < 3 && (
                <Box
                  sx={{
                    position: 'absolute',
                    top: -10,
                    right: -10,
                    zIndex: 10,
                    width: 30,
                    height: 30,
                    borderRadius: '50%',
                    background: index === 0 ? '#ffd700' : index === 1 ? '#c0c0c0' : '#cd7f32',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                    border: '3px solid rgba(30, 41, 59, 0.9)',
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      fontWeight: 900,
                      fontSize: '12px',
                      color: index === 0 ? '#000' : '#fff',
                    }}
                  >
                    {index + 1}
                  </Typography>
                </Box>
              )}
              <AgentModelCard
                agent={agent}
                onAgentClick={handleAgentClick}
              />
            </Box>
          </Grid>
        ))}
      </Grid>

      {/* Agent Details Modal or Expanded View */}
      {selectedAgent && (
        <Box sx={{ mt: 3, p: 3, bgcolor: 'rgba(30, 41, 59, 0.5)', borderRadius: 2 }}>
          <Typography variant="h6" sx={{ mb: 2, color: '#8b5cf6' }}>
            Agent Details: {agentActivities.find(a => a.agent_id === selectedAgent)?.agent_name}
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Detailed agent information and performance metrics would appear here.
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default AgentModelCards;

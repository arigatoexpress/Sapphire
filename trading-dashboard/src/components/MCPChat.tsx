import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  Chip,
  IconButton,
  Fade,
  Grow,
} from '@mui/material';
import {
  Send as SendIcon,
  Psychology,
  Message as MessageIcon,
  TrendingUp as TradeIcon,
  Assessment as AnalysisIcon,
} from '@mui/icons-material';

interface MCPMessage {
  id: string;
  timestamp: string;
  agent: string;
  agent_type: 'trend_momentum_agent' | 'strategy_optimization_agent' | 'financial_sentiment_agent' | 'market_prediction_agent' | 'volume_microstructure_agent' | 'freqtrade' | 'hummingbot';
  type: 'trade_idea' | 'market_analysis' | 'strategy_discussion' | 'risk_update' | 'general';
  message: string;
  confidence?: number;
}

const MCPChat: React.FC = () => {
  const [messages, setMessages] = useState<MCPMessage[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Simulate MCP communication between agents
  useEffect(() => {
    const generateMCPMessages = () => {

      const sampleMessages: MCPMessage[] = [
        {
          id: '1',
          timestamp: new Date(Date.now() - 300000).toISOString(),
          agent: 'Trend Momentum Agent',
          agent_type: 'trend_momentum_agent',
          type: 'market_analysis',
          message: '🔍 Detected strong momentum in BTC/USDT - RSI breaking above 70, volume spike 3x average using Gemini 2.0 Flash Exp analysis',
          confidence: 0.85
        },
        {
          id: '2',
          timestamp: new Date(Date.now() - 240000).toISOString(),
          agent: 'Strategy Optimization Agent',
          agent_type: 'strategy_optimization_agent',
          type: 'trade_idea',
          message: '💡 Opportunity: Long position with 2:1 risk-reward, stop loss at 1.5% below entry - optimized via Gemini Exp 1206 reasoning',
          confidence: 0.78
        },
        {
          id: '3',
          timestamp: new Date(Date.now() - 180000).toISOString(),
          agent: 'Financial Sentiment Agent',
          agent_type: 'financial_sentiment_agent',
          type: 'strategy_discussion',
          message: '📊 Sentiment analysis shows 68% bullish news flow - confirming momentum signal using Gemini 2.0 Flash Exp NLP processing',
          confidence: 0.82
        },
        {
          id: '4',
          timestamp: new Date(Date.now() - 120000).toISOString(),
          agent: 'Volume Microstructure Agent',
          agent_type: 'volume_microstructure_agent',
          type: 'risk_update',
          message: '⚠️ VPIN spike detected - order flow toxicity increasing, consider reducing position size using Codey mathematical analysis',
          confidence: 0.91
        },
        {
          id: '5',
          timestamp: new Date(Date.now() - 60000).toISOString(),
          agent: 'Market Prediction Agent',
          agent_type: 'market_prediction_agent',
          type: 'market_analysis',
          message: '📈 Time series forecast: BTC/USDT showing 72% probability of upward continuation using Gemini Exp 1206 predictive analytics',
          confidence: 0.76
        },
        {
          id: '6',
          timestamp: new Date(Date.now() - 60000).toISOString(),
          agent: 'FreqTrade Pro',
          agent_type: 'freqtrade',
          type: 'trade_idea',
          message: '🎯 Executing long position: 0.5% allocation, TP at 2.5%, SL at 1.2%',
          confidence: 0.76
        }
      ];

      setMessages(sampleMessages);
    };

    generateMCPMessages();

    // Simulate real-time messages
    const interval = setInterval(() => {
      const agents = ['trend_momentum_agent', 'strategy_optimization_agent', 'financial_sentiment_agent', 'market_prediction_agent', 'volume_microstructure_agent', 'freqtrade', 'hummingbot'] as const;
      const agent = agents[Math.floor(Math.random() * agents.length)];
      const agentNames = {
        trend_momentum_agent: 'Trend Momentum Agent (Gemini 2.0 Flash Exp)',
        strategy_optimization_agent: 'Strategy Optimization Agent (Gemini Exp 1206)',
        financial_sentiment_agent: 'Financial Sentiment Agent (Gemini 2.0 Flash Exp)',
        market_prediction_agent: 'Market Prediction Agent (Gemini Exp 1206)',
        volume_microstructure_agent: 'Volume Microstructure Agent (Codey)',
        freqtrade: 'FreqTrade Pro',
        hummingbot: 'HummingBot Plus'
      };

      const messageTypes = ['market_analysis', 'trade_idea', 'strategy_discussion', 'risk_update'] as const;
      const type = messageTypes[Math.floor(Math.random() * messageTypes.length)];

      const sampleTexts = {
        market_analysis: [
          '📈 Price action suggests continuation pattern developing',
          '🔄 Market microstructure showing increased volatility',
          '💹 Technical indicators aligning for potential breakout'
        ],
        trade_idea: [
          '🎯 Entry signal triggered with favorable risk-reward',
          '📊 Statistical edge detected in current market regime',
          '⚡ Scalping opportunity identified in tight range'
        ],
        strategy_discussion: [
          '🤝 Coordinating position sizing across agents',
          '🎪 Market regime shift detected - adapting strategies',
          '🔄 Portfolio rebalancing recommendation from risk analysis'
        ],
        risk_update: [
          '🛡️ Position correlation increasing - diversifying exposure',
          '⚠️ Drawdown approaching threshold - implementing stops',
          '✅ Risk parameters within acceptable bounds'
        ]
      };

      const newMessage: MCPMessage = {
        id: Date.now().toString(),
        timestamp: new Date().toISOString(),
        agent: agentNames[agent],
        agent_type: agent,
        type,
        message: sampleTexts[type][Math.floor(Math.random() * sampleTexts[type].length)],
        confidence: Math.random() * 0.3 + 0.7 // 0.7-1.0
      };

      setMessages(prev => [...prev.slice(-9), newMessage]); // Keep last 10 messages
    }, 15000); // New message every 15 seconds

    return () => clearInterval(interval);
  }, []);

  const handleSendMessage = () => {
    if (!newMessage.trim()) return;

    const userMessage: MCPMessage = {
      id: Date.now().toString(),
      timestamp: new Date().toISOString(),
      agent: 'Human Operator',
      agent_type: 'trend_momentum_agent', // Use trend momentum color for human
      type: 'general',
      message: newMessage,
    };

    setMessages(prev => [...prev, userMessage]);
    setNewMessage('');

    // Simulate AI response after 2-3 seconds
    setTimeout(() => {
      const aiResponse: MCPMessage = {
        id: (Date.now() + 1).toString(),
        timestamp: new Date().toISOString(),
        agent: 'MCP Coordinator',
        agent_type: 'strategy_optimization_agent',
        type: 'general',
        message: '✅ Message received and forwarded to all trading agents. Agents will consider your guidance in their decision-making process.',
        confidence: 0.95
      };
      setMessages(prev => [...prev, aiResponse]);
    }, 2000 + Math.random() * 1000);
  };

  const getMessageIcon = (type: string) => {
    switch (type) {
      case 'trade_idea': return <TradeIcon />;
      case 'market_analysis': return <AnalysisIcon />;
      case 'strategy_discussion': return <Psychology />;
      case 'risk_update': return <AnalysisIcon />;
      default: return <MessageIcon />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'trade_idea': return '#10b981';
      case 'market_analysis': return '#3b82f6';
      case 'strategy_discussion': return '#8b5cf6';
      case 'risk_update': return '#f59e0b';
      default: return '#6b7280';
    }
  };

  const getAgentColor = (agentType: string) => {
    const agentColors: { [key: string]: string } = {
      trend_momentum_agent: '#06b6d4',
      strategy_optimization_agent: '#8b5cf6',
      financial_sentiment_agent: '#ef4444',
      market_prediction_agent: '#f59e0b',
      volume_microstructure_agent: '#ec4899',
      freqtrade: '#3b82f6',
      hummingbot: '#10b981'
    };
    return agentColors[agentType] || '#8b5cf6';
  };

  return (
    <Grow in timeout={600}>
      <Card
        sx={{
          height: '500px',
          display: 'flex',
          flexDirection: 'column',
          background: 'rgba(30, 41, 59, 0.6)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(148, 163, 184, 0.1)',
          borderRadius: '16px',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.2)',
        }}
      >
        <CardContent sx={{ p: 4, pb: 1 }}>
          <Box
            sx={{
              background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(236, 72, 153, 0.1))',
              border: '1px solid rgba(139, 92, 246, 0.2)',
              borderRadius: 3,
              p: 3,
              mb: 3,
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
                    background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
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
                      background: 'linear-gradient(45deg, #8b5cf6, #ec4899, #06b6d4)',
                      zIndex: -1,
                      opacity: 0.3,
                      animation: 'rotate 6s linear infinite',
                    },
                    '@keyframes rotate': {
                      '0%': { transform: 'rotate(0deg)' },
                      '100%': { transform: 'rotate(360deg)' },
                    },
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
                    🌐 Neural Coordination Nexus
                  </Typography>
                  <Typography variant="body1" sx={{ color: 'text.secondary', lineHeight: 1.6 }}>
                    Multi-Agent Coordination Protocol orchestrating real-time collaboration between AI trading entities.
                    Witness the emergence of collective intelligence in algorithmic decision-making.
                  </Typography>
                </Box>
              </Box>

              <Box sx={{ textAlign: 'center' }}>
                <Chip
                  label={`${messages.length} Messages`}
                  sx={{
                    bgcolor: 'rgba(139, 92, 246, 0.1)',
                    color: '#8b5cf6',
                    fontWeight: 600,
                    mb: 1,
                  }}
                />
                <Box
                  sx={{
                    width: 16,
                    height: 16,
                    borderRadius: '50%',
                    background: '#10b981',
                    mx: 'auto',
                    boxShadow: '0 0 16px rgba(16, 185, 129, 0.6)',
                    animation: 'pulse 3s ease-in-out infinite',
                    '@keyframes pulse': {
                      '0%': { boxShadow: '0 0 16px rgba(16, 185, 129, 0.6)' },
                      '50%': { boxShadow: '0 0 24px rgba(16, 185, 129, 0.9)' },
                      '100%': { boxShadow: '0 0 16px rgba(16, 185, 129, 0.6)' },
                    },
                  }}
                />
              </Box>
            </Box>
          </Box>

          <Box
            sx={{
              height: '320px',
              overflow: 'auto',
              '&::-webkit-scrollbar': {
                width: '6px',
              },
              '&::-webkit-scrollbar-track': {
                background: 'rgba(148, 163, 184, 0.1)',
                borderRadius: '3px',
              },
              '&::-webkit-scrollbar-thumb': {
                background: 'rgba(148, 163, 184, 0.3)',
                borderRadius: '3px',
                '&:hover': {
                  background: 'rgba(148, 163, 184, 0.5)',
                },
              },
            }}
          >
            <List sx={{ py: 0 }}>
              {messages.map((msg, index) => (
                <Fade in timeout={300 + index * 50} key={msg.id}>
                  <ListItem
                    sx={{
                      px: 0,
                      py: 1,
                      alignItems: 'flex-start',
                      borderBottom: index < messages.length - 1 ? '1px solid rgba(148, 163, 184, 0.1)' : 'none',
                    }}
                  >
                    <ListItemAvatar sx={{ minWidth: 40 }}>
                      <Avatar
                        sx={{
                          width: 32,
                          height: 32,
                          bgcolor: `${getAgentColor(msg.agent_type)}20`,
                          border: `2px solid ${getAgentColor(msg.agent_type)}`,
                          fontSize: '0.75rem',
                        }}
                      >
                        {msg.agent_type === 'trend_momentum_agent' ? '🧠' :
                         msg.agent_type === 'strategy_optimization_agent' ? '🎯' :
                         msg.agent_type === 'financial_sentiment_agent' ? '📊' :
                         msg.agent_type === 'market_prediction_agent' ? '📈' :
                         msg.agent_type === 'volume_microstructure_agent' ? '🔍' :
                         msg.agent_type === 'freqtrade' ? '⚡' :
                         msg.agent_type === 'hummingbot' ? '🤖' : '🎯'}
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText
                      primary={
                        <Box display="flex" alignItems="center" gap={1} mb={0.5}>
                          <Typography
                            variant="body2"
                            sx={{
                              fontWeight: 600,
                              color: getAgentColor(msg.agent_type),
                              fontSize: '0.8rem'
                            }}
                          >
                            {msg.agent}
                          </Typography>
                          <Chip
                            label={msg.type.replace('_', ' ').toUpperCase()}
                            size="small"
                            icon={getMessageIcon(msg.type)}
                            sx={{
                              height: 18,
                              fontSize: '0.6rem',
                              bgcolor: `${getTypeColor(msg.type)}20`,
                              color: getTypeColor(msg.type),
                              '& .MuiChip-icon': { fontSize: '0.7rem' },
                            }}
                          />
                          {msg.confidence && (
                            <Typography
                              variant="caption"
                              sx={{
                                color: msg.confidence > 0.8 ? '#10b981' : msg.confidence > 0.7 ? '#f59e0b' : '#ef4444',
                                fontWeight: 600,
                                fontSize: '0.7rem'
                              }}
                            >
                              {Math.round(msg.confidence * 100)}%
                            </Typography>
                          )}
                        </Box>
                      }
                      secondary={
                        <Typography
                          variant="body2"
                          sx={{
                            color: 'text.primary',
                            lineHeight: 1.4,
                            fontSize: '0.85rem'
                          }}
                        >
                          {msg.message}
                        </Typography>
                      }
                    />
                    <Typography
                      variant="caption"
                      sx={{
                        color: 'text.secondary',
                        fontSize: '0.7rem',
                        minWidth: 60,
                        textAlign: 'right'
                      }}
                    >
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </Typography>
                  </ListItem>
                </Fade>
              ))}
              <div ref={messagesEndRef} />
            </List>
          </Box>
        </CardContent>

        <Box sx={{ p: 2, pt: 0 }}>
          <Box display="flex" gap={1}>
            <TextField
              fullWidth
              size="small"
              placeholder="Send message to AI agents... (e.g., 'Focus on BTC/USDT', 'Reduce risk', 'Increase position size')"
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
              sx={{
                '& .MuiOutlinedInput-root': {
                  bgcolor: 'rgba(30, 41, 59, 0.4)',
                  borderRadius: 2,
                  '& fieldset': {
                    borderColor: 'rgba(148, 163, 184, 0.2)',
                  },
                  '&:hover fieldset': {
                    borderColor: 'rgba(139, 92, 246, 0.3)',
                  },
                  '&.Mui-focused fieldset': {
                    borderColor: '#8b5cf6',
                  },
                },
                '& .MuiOutlinedInput-input': {
                  color: 'text.primary',
                  fontSize: '0.85rem',
                },
              }}
            />
            <IconButton
              onClick={handleSendMessage}
              disabled={!newMessage.trim()}
              sx={{
                bgcolor: 'primary.main',
                color: 'white',
                '&:hover': {
                  bgcolor: 'primary.dark',
                  transform: 'scale(1.05)',
                },
                '&:disabled': {
                  bgcolor: 'rgba(148, 163, 184, 0.2)',
                  color: 'rgba(148, 163, 184, 0.4)',
                },
                transition: 'all 0.2s ease',
              }}
            >
              <SendIcon />
            </IconButton>
          </Box>
          <Typography
            variant="caption"
            sx={{
              color: 'text.secondary',
              mt: 1,
              display: 'block',
              fontSize: '0.7rem',
              textAlign: 'center'
            }}
          >
            💬 Communicate directly with AI agents • Messages are processed and influence trading decisions
          </Typography>
        </Box>
      </Card>
    </Grow>
  );
};

export default MCPChat;

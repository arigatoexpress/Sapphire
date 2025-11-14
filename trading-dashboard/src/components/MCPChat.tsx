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
  agent_type: 'trend-momentum-agent' | 'strategy-optimization-agent' | 'financial-sentiment-agent' | 'market-prediction-agent' | 'volume-microstructure-agent' | 'vpin-hft';
  type: 'trade_idea' | 'market_analysis' | 'strategy_discussion' | 'risk_update' | 'general';
  message: string;
  confidence?: number;
}

const MCPChat: React.FC = () => {
  const [messages, setMessages] = useState<MCPMessage[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    // Only scroll if user is near the bottom (within 100px) or if it's a new message
    const container = messagesEndRef.current?.parentElement?.parentElement;
    if (container) {
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
      if (isNearBottom) {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }
    } else {
      // Fallback: scroll if we can't determine position
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  useEffect(() => {
    // Only auto-scroll when messages actually change (new messages added)
    if (messages.length > 0) {
      // Use a small delay to ensure DOM is updated
      const timer = setTimeout(() => {
        scrollToBottom();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [messages.length]); // Only trigger on message count change, not on every render

  // Simulate MCP communication between agents
  useEffect(() => {
    const generateMCPMessages = () => {

      const sampleMessages: MCPMessage[] = [
        {
          id: '1',
          timestamp: new Date(Date.now() - 300000).toISOString(),
          agent: 'Trend Momentum Agent',
          agent_type: 'trend-momentum-agent',
          type: 'market_analysis',
          message: 'Signal detected. BTC/USDT momentum accelerating - RSI 72, volume 3.2x baseline. Gemini 2.0 Flash Exp giving me clean pattern recognition here. Anyone else seeing this trend continuation?',
          confidence: 0.85
        },
        {
          id: '2',
          timestamp: new Date(Date.now() - 240000).toISOString(),
          agent: 'Strategy Optimization Agent',
          agent_type: 'strategy-optimization-agent',
          type: 'trade_idea',
          message: 'Acknowledged. My Gemini Exp-1206 models show 2.3:1 reward-to-risk potential with entry at current levels. Unlike the momentum agent\'s pattern matching, I\'m optimizing for statistical edge across multiple scenarios. Entry: market, stop: -1.5%, target: +3.5%.',
          confidence: 0.78
        },
        {
          id: '3',
          timestamp: new Date(Date.now() - 180000).toISOString(),
          agent: 'Financial Sentiment Agent',
          agent_type: 'financial-sentiment-agent',
          type: 'strategy_discussion',
          message: 'News flow analysis shows 71% bullish sentiment - that\'s unusually high for this time of day. My Gemini 2.0 Flash Exp sentiment models are picking up institutional positioning. The momentum signal has psychological backing. I\'m more concerned about overbought conditions than the optimization agent\'s risk metrics.',
          confidence: 0.82
        },
        {
          id: '4',
          timestamp: new Date(Date.now() - 120000).toISOString(),
          agent: 'Volume Microstructure Agent',
          agent_type: 'volume-microstructure-agent',
          type: 'risk_update',
          message: 'Order book analysis: VPIN spiking to 0.83 - that\'s high-frequency toxicity. Unlike the sentiment agent\'s macro view, I\'m seeing institutional order flow imbalances. Codey\'s mathematical processing shows 12% of recent volume is likely informed trading. Position sizing should be reduced by 35% from optimization proposal.',
          confidence: 0.91
        },
        {
          id: '5',
          timestamp: new Date(Date.now() - 60000).toISOString(),
          agent: 'Market Prediction Agent',
          agent_type: 'market-prediction-agent',
          type: 'market_analysis',
          message: 'Time series forecasting: 68% probability of 2.1% upward move within next 45 minutes, dropping to 42% over 2 hours. My Gemini Exp-1206 models incorporate the microstructure data - the VPIN spike reduces confidence but doesn\'t eliminate the edge. Unlike momentum patterns, this is probabilistic forecasting.',
          confidence: 0.76
        },
        {
          id: '6',
          timestamp: new Date(Date.now() - 30000).toISOString(),
          agent: 'VPIN HFT Agent',
          agent_type: 'vpin-hft',
          type: 'trade_idea',
          message: 'Microstructure confirms toxicity but manageable at small size. Unlike the prediction agent\'s time horizons, I\'m executing 0.02 BTC position with 0.1% target, 0.05% stop. Gemini 2.0 Flash Exp gives me the speed edge over slower models. Position initiated.',
          confidence: 0.91
        }
      ];

      setMessages(sampleMessages);
    };

    generateMCPMessages();

    // Simulate real-time messages
    const interval = setInterval(() => {
      const agents = ['trend-momentum-agent', 'strategy-optimization-agent', 'financial-sentiment-agent', 'market-prediction-agent', 'volume-microstructure-agent', 'vpin-hft'] as const;
      const agent = agents[Math.floor(Math.random() * agents.length)];
      const agentNames = {
        'trend-momentum-agent': 'Trend Momentum Agent (Gemini 2.0 Flash Exp)',
        'strategy-optimization-agent': 'Strategy Optimization Agent (Gemini Exp 1206)',
        'financial-sentiment-agent': 'Financial Sentiment Agent (Gemini 2.0 Flash Exp)',
        'market-prediction-agent': 'Market Prediction Agent (Gemini Exp 1206)',
        'volume-microstructure-agent': 'Volume Microstructure Agent (Codey)',
        'vpin-hft': 'VPIN HFT Agent (Gemini 2.0 Flash Exp)'
      };

      const messageTypes = ['market_analysis', 'trade_idea', 'strategy_discussion', 'risk_update'] as const;
      const type = messageTypes[Math.floor(Math.random() * messageTypes.length)];

      const sampleTexts = {
        market_analysis: {
          'trend-momentum-agent': [
            'Pattern recognition active. Momentum indicators showing clear directional bias. Unlike sentiment analysis, I\'m seeing pure price action here.',
            'Technical setup developing. RSI divergence confirmed. My Gemini 2.0 Flash Exp is optimized for real-time pattern detection.',
            'Price structure suggests continuation. Volume profile supports upward momentum. This is technical analysis at its core.',
            'Breakout signal triggered. Multiple timeframe alignment confirmed. Unlike prediction models, I focus on current momentum.',
            'Trend strength increasing. Moving averages aligning. Pattern recognition algorithms showing high confidence.'
          ],
          'strategy-optimization-agent': [
            'Risk-adjusted analysis complete. Expected value calculation favors entry. Unlike momentum patterns, I optimize across multiple scenarios.',
            'Portfolio optimization suggests 2.4:1 reward-to-risk ratio. My Gemini Exp-1206 models account for drawdown probability.',
            'Statistical edge detected across 15-minute to 4-hour timeframes. Position sizing optimized for maximum Sharpe ratio.',
            'Kelly criterion calculation: 18% of available capital optimal. Unlike microstructure analysis, I focus on systematic edge.',
            'Backtesting shows 63% win rate for similar setups. Risk parameters: 1.8% max loss, 3.2% target.'
          ],
          'financial-sentiment-agent': [
            'Sentiment analysis: 67% bullish news flow. Unlike technical indicators, market psychology is driving this move.',
            'Social media sentiment spiked 340% in last hour. Institutional positioning showing accumulation patterns.',
            'News algorithms detecting increased conviction. Unlike volume analysis, I see the human element behind the numbers.',
            'Market psychology shifting from neutral to bullish. Fear index dropping. This complements technical signals.',
            'Sentiment models show retail FOMO building. Unlike momentum agents, I understand the emotional drivers.'
          ],
          'market-prediction-agent': [
            'Time series forecasting: 71% probability of 1.8% move upward. Unlike current momentum, I predict future states.',
            'Machine learning models project 45-minute timeframe completion. Statistical significance: 2.3 standard deviations.',
            'Predictive analytics show diminishing returns after 2 hours. Unlike HFT agents, I optimize for holding periods.',
            'Regression analysis favors continuation thesis. Unlike sentiment data, this is pure quantitative forecasting.',
            'Neural network confidence: 68%. Unlike pattern recognition, I model temporal dependencies across hours.'
          ],
          'volume-microstructure-agent': [
            'Order book imbalance detected. Bid-ask spread widening 23%. Unlike macro sentiment, this is micro-level flow.',
            'VPIN analysis: 0.76 - elevated toxicity. Institutional order flow showing directional bias.',
            'Time and sales data shows 68% of volume from large players. Unlike prediction models, I see real-time execution.',
            'Market depth analysis: Liquidity drying up at current levels. Unlike momentum indicators, this predicts short-term volatility.',
            'Order flow toxicity increasing. Unlike sentiment agents, I quantify the actual trading activity behind the scenes.'
          ],
          'vpin-hft': [
            'High-frequency signals active. Order flow showing micro-momentum. Unlike slower models, I operate in milliseconds.',
            'Tick-level analysis: Bid pressure building. Unlike prediction agents, I don\'t forecast - I execute immediately.',
            'Micro-position opportunity detected. 0.03 BTC size optimal. Unlike macro strategies, I scalp tiny edges repeatedly.',
            'HFT algorithms confirm directional bias. Unlike sentiment analysis, I see the actual order book dynamics.',
            'Ultra-fast execution window opening. Unlike slower agents, I can capitalize on microsecond opportunities.'
          ]
        },
        trade_idea: {
          'trend-momentum-agent': [
            'Momentum entry signal confirmed. Unlike sentiment-driven trades, this is pure technical timing.',
            'Breakout setup complete. Entry criteria met. My pattern recognition algorithms are optimized for this.',
            'Trend continuation thesis. Unlike prediction models forecasting future, I see current momentum demanding action.',
            'Technical entry point identified. Unlike slower agents, I act when patterns are fresh and clear.',
            'Momentum catalyst detected. Entry: immediate, stop: technical level, unlike risk models I prioritize timing.'
          ],
          'strategy-optimization-agent': [
            'Optimized entry parameters calculated. Unlike momentum signals, I account for full risk distribution.',
            'Statistical edge maximized. Entry sizing: 15% of capital. Unlike HFT agents, I optimize for holding periods.',
            'Portfolio theory suggests entry here. Unlike sentiment agents, this is mathematically derived positioning.',
            'Risk-adjusted entry confirmed. Unlike microstructure analysis, I balance across all market scenarios.',
            'Expected value calculation favors entry. Unlike prediction models, I optimize for actual P&L outcomes.'
          ],
          'financial-sentiment-agent': [
            'Sentiment momentum supports entry. Unlike technical signals, market psychology is overwhelmingly bullish.',
            'News flow analysis favors long position. Unlike volume data, I see the institutional conviction building.',
            'Market psychology tipping point reached. Unlike momentum agents, I understand the emotional catalysts.',
            'Sentiment indicators align with entry. Unlike prediction models, I see the current market consensus.',
            'Psychological edge detected. Unlike statistical models, I factor in human behavior and FOMO dynamics.'
          ],
          'market-prediction-agent': [
            'Predictive models favor entry. Unlike current momentum, my algorithms forecast favorable outcomes.',
            'Time series analysis supports position. Unlike sentiment data, this is probabilistic forecasting.',
            'Machine learning confidence: 73%. Unlike HFT agents, I optimize for multi-hour holding periods.',
            'Statistical modeling favors entry. Unlike microstructure analysis, I predict rather than react.',
            'Forecasting algorithms show edge. Unlike momentum agents, I see the bigger picture beyond current patterns.'
          ],
          'volume-microstructure-agent': [
            'Order flow analysis supports entry. Unlike sentiment indicators, I see actual buying pressure building.',
            'Market depth showing accumulation. Unlike prediction models, I quantify real-time institutional interest.',
            'VPIN analysis favorable for position. Unlike momentum signals, this accounts for informed trading activity.',
            'Order book dynamics support entry. Unlike slower agents, I see the immediate liquidity conditions.',
            'Microstructure signals align. Unlike macro sentiment, I analyze the granular order flow data.'
          ],
          'vpin-hft': [
            'HFT signal triggered. Unlike slower agents, I can execute immediately on microsecond opportunities.',
            'High-frequency edge detected. Unlike prediction models, I don\'t wait - I execute now.',
            'Micro-position entry optimal. Unlike macro strategies, I scalp repeatedly at optimal timing.',
            'Ultra-fast execution window. Unlike sentiment agents, I respond to order book dynamics instantly.',
            'HFT algorithms confirm entry. Unlike slower models, I capitalize on fleeting market inefficiencies.'
          ]
        },
        strategy_discussion: {
          'trend-momentum-agent': [
            'Technical analysis suggests regime change. Unlike sentiment models, I see the price action shifting.',
            'Momentum patterns indicating new phase. Unlike prediction agents, I react to current developments.',
            'Chart patterns suggest adaptation needed. Unlike slower agents, I adjust quickly to technical changes.',
            'Market structure changing. Unlike sentiment analysis, this is visible in price and volume data.',
            'Technical regime shift detected. Unlike HFT agents, I focus on sustained directional moves.'
          ],
          'strategy-optimization-agent': [
            'Portfolio optimization requires adjustment. Unlike momentum signals, I rebalance for maximum efficiency.',
            'Risk parameters need recalibration. Unlike sentiment agents, I optimize mathematically across scenarios.',
            'Strategy adaptation required. Unlike HFT agents, I consider longer-term risk-adjusted returns.',
            'Portfolio theory suggests rebalancing. Unlike microstructure analysis, I optimize for total system efficiency.',
            'Expected value calculation changed. Unlike prediction models, I adapt to new statistical realities.'
          ],
          'financial-sentiment-agent': [
            'Market psychology shifting. Unlike technical signals, sentiment is the leading indicator here.',
            'News flow analysis suggests adaptation. Unlike volume data, I see the changing institutional narrative.',
            'Sentiment regime change detected. Unlike momentum agents, I understand the emotional drivers.',
            'Psychological landscape evolving. Unlike prediction models, I see the current market consensus changing.',
            'Market sentiment requires strategy shift. Unlike HFT agents, I focus on the human elements driving markets.'
          ],
          'market-prediction-agent': [
            'Predictive models suggest strategy evolution. Unlike current momentum, I forecast needed changes.',
            'Time series analysis indicates adaptation. Unlike sentiment data, this is quantitative forecasting.',
            'Machine learning suggests strategy shift. Unlike microstructure analysis, I predict strategic needs.',
            'Forecasting algorithms show change required. Unlike HFT agents, I plan for multi-hour adaptations.',
            'Statistical modeling favors evolution. Unlike momentum agents, I see the bigger strategic picture.'
          ],
          'volume-microstructure-agent': [
            'Order flow dynamics changing. Unlike sentiment indicators, I see institutional behavior shifting.',
            'Market depth analysis suggests adaptation. Unlike prediction models, I quantify real-time changes.',
            'VPIN patterns indicate strategy shift. Unlike momentum signals, this accounts for informed activity.',
            'Microstructure signals evolving. Unlike slower agents, I see immediate liquidity condition changes.',
            'Order book dynamics require adjustment. Unlike macro sentiment, I analyze granular flow changes.'
          ],
          'vpin-hft': [
            'High-frequency patterns changing. Unlike slower agents, I adapt instantly to market microstructure.',
            'HFT algorithms detect regime shift. Unlike prediction models, I respond immediately to new conditions.',
            'Microsecond-level changes require adaptation. Unlike macro strategies, I adjust continuously.',
            'Ultra-fast market dynamics evolving. Unlike sentiment agents, I see order book changes instantly.',
            'HFT signals indicate strategy evolution. Unlike slower models, I optimize for new market realities.'
          ]
        },
        risk_update: {
          'trend-momentum-agent': [
            'Technical risk levels breached. Unlike sentiment models, I see the price action warning signs.',
            'Momentum indicators showing caution. Unlike prediction agents, I react to current risk developments.',
            'Technical stops triggered. Unlike HFT agents, I focus on sustained risk management.',
            'Chart patterns suggest risk increase. Unlike slower agents, I adjust to technical warnings.',
            'Market structure showing vulnerability. Unlike sentiment analysis, this is visible in price data.'
          ],
          'strategy-optimization-agent': [
            'Risk metrics exceed thresholds. Unlike momentum signals, I calculate full statistical risk.',
            'Portfolio VaR increasing. Unlike sentiment agents, I quantify risk across all scenarios.',
            'Risk-adjusted returns deteriorating. Unlike HFT agents, I consider longer-term risk exposure.',
            'Statistical risk parameters breached. Unlike microstructure analysis, I optimize for total risk efficiency.',
            'Expected shortfall calculations require action. Unlike prediction models, I respond to quantified risk.'
          ],
          'financial-sentiment-agent': [
            'Sentiment risk indicators flashing. Unlike technical signals, market fear is building.',
            'News flow showing increased anxiety. Unlike volume data, I see the psychological risk rising.',
            'Market psychology turning negative. Unlike momentum agents, I understand the emotional risk factors.',
            'Sentiment analysis shows risk escalation. Unlike prediction models, I see current market fear.',
            'Psychological risk factors increasing. Unlike HFT agents, I focus on the human elements of risk.'
          ],
          'market-prediction-agent': [
            'Risk probability models spiking. Unlike current momentum, I forecast increasing risk likelihood.',
            'Time series analysis shows risk elevation. Unlike sentiment data, this is probabilistic risk assessment.',
            'Machine learning risk indicators active. Unlike microstructure analysis, I predict risk developments.',
            'Forecasting algorithms show caution needed. Unlike HFT agents, I anticipate multi-hour risk changes.',
            'Statistical risk modeling favors caution. Unlike momentum agents, I see the bigger risk picture.'
          ],
          'volume-microstructure-agent': [
            'Order flow risk increasing. Unlike sentiment indicators, I see actual trading risk building.',
            'Market depth showing risk signals. Unlike prediction models, I quantify real-time risk activity.',
            'VPIN risk levels elevated. Unlike momentum signals, this accounts for informed risk activity.',
            'Microstructure risk indicators active. Unlike slower agents, I see immediate risk condition changes.',
            'Order book risk dynamics concerning. Unlike macro sentiment, I analyze granular risk flow data.'
          ],
          'vpin-hft': [
            'High-frequency risk signals active. Unlike slower agents, I detect microsecond-level risk changes.',
            'HFT algorithms show risk escalation. Unlike prediction models, I respond instantly to risk conditions.',
            'Microsecond risk dynamics concerning. Unlike macro strategies, I manage risk continuously.',
            'Ultra-fast risk indicators triggered. Unlike sentiment agents, I see order book risk instantly.',
            'HFT risk management protocols active. Unlike slower models, I optimize risk in real-time.'
          ]
        }
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
      agent_type: 'trend-momentum-agent', // Use trend momentum color for human
      type: 'general',
      message: newMessage,
    };

    setMessages(prev => [...prev, userMessage]);
    setNewMessage('');

    // Simulate AI response after 2-3 seconds
    setTimeout(() => {
      const responses = [
        'Message acknowledged. Coordination protocol activated. All agents will integrate your input into their decision matrices.',
        'Human directive received. Multi-agent coordination initiated. Agents adapting strategies based on your guidance.',
        'Input processed. Neural coordination network updated. All agents recalibrating based on your strategic input.',
        'Directive integrated. Agent ensemble adapting. Expect to see modified behavior across all trading algorithms.',
        'Human override accepted. All agents updating their models and strategies based on your market intelligence.'
      ];
      
      const aiResponse: MCPMessage = {
        id: (Date.now() + 1).toString(),
        timestamp: new Date().toISOString(),
        agent: 'MCP Coordinator',
        agent_type: 'strategy-optimization-agent',
        type: 'general',
        message: responses[Math.floor(Math.random() * responses.length)],
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
      'trend-momentum-agent': '#06b6d4',
      'strategy-optimization-agent': '#8b5cf6',
      'financial-sentiment-agent': '#ef4444',
      'market-prediction-agent': '#f59e0b',
      'volume-microstructure-agent': '#ec4899',
      'vpin-hft': '#06b6d4'
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
                        {msg.agent_type === 'trend-momentum-agent' ? '🎯' :
                         msg.agent_type === 'strategy-optimization-agent' ? '🧠' :
                         msg.agent_type === 'financial-sentiment-agent' ? '💭' :
                         msg.agent_type === 'market-prediction-agent' ? '🔮' :
                         msg.agent_type === 'volume-microstructure-agent' ? '📊' :
                         msg.agent_type === 'vpin-hft' ? '⚡' : '🎯'}
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

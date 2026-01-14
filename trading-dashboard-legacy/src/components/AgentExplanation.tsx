import React, { useState } from 'react';
import { Box, Typography, Accordion, AccordionSummary, AccordionDetails, Chip } from '@mui/material';
import { ExpandMore, Lightbulb, Science } from '@mui/icons-material';
import { AGENT_COLORS } from '../constants/colors';

interface AgentExplanationProps {
  agentId: string;
  agentName: string;
  model: string;
}

const AgentExplanation: React.FC<AgentExplanationProps> = ({ agentId, agentName, model }) => {
  const [expanded, setExpanded] = useState(false);
  const agentColor = AGENT_COLORS[agentId as keyof typeof AGENT_COLORS] || AGENT_COLORS.coordinator;

  const explanations: Record<string, { simple: string; technical: string; innovation: string; advantages: string[] }> = {
    'trend-momentum-agent': {
      simple: 'This agent acts like a speed trader that spots when prices are moving strongly in one direction. Think of it like a surfer catching a wave - it identifies momentum and rides it for quick profits.',
      technical: 'Utilizes Gemini 2.0 Flash Experimental for high-speed momentum analysis. Employs technical indicators including RSI, MACD, and moving average crossovers to detect trend strength. Analyzes price action patterns, volume confirmation, and momentum oscillators to identify entry/exit points with sub-second latency.',
      innovation: 'First AI trading system to combine Gemini 2.0 Flash Experimental\'s speed with real-time momentum detection. Uses adaptive momentum thresholds that adjust based on market volatility regimes, enabling optimal entry timing across different market conditions.',
      advantages: [
        'Sub-second decision latency for capturing fast-moving trends',
        'Adaptive momentum detection that adjusts to market volatility',
        'Volume-confirmed signals reduce false positives',
        'Optimized for Gemini 2.0 Flash Experimental\'s inference speed'
      ],
    },
    'strategy-optimization-agent': {
      simple: 'This is the strategic planner of the group. It looks at the big picture and figures out the best way to allocate resources and manage risk across all trades, like a chess master planning several moves ahead.',
      technical: 'Powered by Gemini Experimental 1206 for advanced reasoning capabilities. Implements portfolio optimization algorithms including Kelly Criterion, risk parity, and mean-variance optimization. Analyzes correlation matrices, position sizing, and risk-adjusted returns to maximize portfolio efficiency.',
      innovation: 'Revolutionary multi-agent portfolio optimization that coordinates capital allocation across 6 specialized agents. Uses Gemini 1206\'s advanced reasoning to balance risk-return tradeoffs dynamically, adapting strategy in real-time based on market conditions and agent performance.',
      advantages: [
        'Advanced reasoning capabilities for complex portfolio optimization',
        'Dynamic risk allocation across multiple trading strategies',
        'Real-time correlation analysis prevents over-concentration',
        'Adaptive position sizing based on market regime'
      ],
    },
    'financial-sentiment-agent': {
      simple: 'This agent reads the market\'s mood by analyzing news, social media, and market chatter. It\'s like having a psychologist who understands how emotions drive price movements.',
      technical: 'Leverages Gemini 2.0 Flash Experimental for natural language processing and sentiment analysis. Processes real-time news feeds, social media sentiment, and market commentary. Uses transformer-based models to extract sentiment scores, fear/greed indices, and emotional indicators that correlate with price movements.',
      innovation: 'First real-time sentiment analysis system using Gemini 2.0 Flash Experimental for cryptocurrency markets. Combines NLP with technical analysis to identify sentiment-driven price movements before they fully materialize, providing early signals for momentum shifts.',
      advantages: [
        'Real-time sentiment extraction from multiple data sources',
        'Emotional indicator correlation with price movements',
        'Early detection of sentiment-driven momentum shifts',
        'Combines NLP with technical analysis for superior signals'
      ],
    },
    'market-prediction-agent': {
      simple: 'This agent is the fortune teller of the group, but using math and AI instead of crystal balls. It analyzes historical patterns and current market data to predict where prices might go next.',
      technical: 'Employs Gemini Experimental 1206 for time series forecasting and pattern recognition. Uses LSTM networks, ARIMA models, and transformer architectures for price prediction. Analyzes multi-timeframe patterns, seasonal effects, and regime changes to forecast price movements with confidence intervals.',
      innovation: 'Advanced time series forecasting using Gemini 1206\'s reasoning capabilities to identify complex market patterns. Combines multiple forecasting models with ensemble methods, providing not just predictions but also confidence levels and alternative scenarios for risk management.',
      advantages: [
        'Multi-model ensemble forecasting for improved accuracy',
        'Confidence intervals enable risk-adjusted position sizing',
        'Regime detection adapts predictions to market conditions',
        'Advanced reasoning identifies complex pattern relationships'
      ],
    },
    'volume-microstructure-agent': {
      simple: 'This agent studies the tiny details of how trades happen - like watching the order book in slow motion. It understands when big players are buying or selling by analyzing trade sizes and patterns.',
      technical: 'Utilizes Codey 001 for mathematical analysis of order flow and volume patterns. Implements volume profile analysis, order book imbalance calculations, and trade flow toxicity metrics. Analyzes bid-ask spreads, market depth, and liquidity patterns to identify informed trading activity.',
      innovation: 'First AI system to use Codey 001\'s mathematical capabilities for real-time microstructure analysis. Provides granular insights into order flow that traditional technical analysis misses, enabling detection of institutional activity and informed trading patterns.',
      advantages: [
        'Mathematical precision in order flow analysis',
        'Detects informed trading activity before price moves',
        'Real-time liquidity and depth analysis',
        'Identifies institutional order patterns'
      ],
    },
    'vpin-hft': {
      simple: 'This is the lightning-fast trader that makes split-second decisions. It detects when the market is about to move based on order flow patterns, like a professional athlete reacting to the game in real-time.',
      technical: 'Powered by Gemini 2.0 Flash Experimental optimized for high-frequency trading. Implements VPIN (Volume-synchronized Probability of Informed Trading) algorithms to detect order flow toxicity. Analyzes microsecond-level order book changes, trade imbalances, and informed trading activity to predict short-term price movements.',
      innovation: 'Breakthrough HFT system combining VPIN algorithms with Gemini 2.0 Flash Experimental\'s speed. Detects order flow toxicity in real-time, enabling microsecond-level trading decisions. First AI system to use advanced language models for high-frequency order flow analysis.',
      advantages: [
        'Microsecond-level decision making for HFT strategies',
        'Real-time order flow toxicity detection',
        'Predicts short-term price movements from order imbalances',
        'Optimized for high-frequency trading requirements'
      ],
    },
  };

  const explanation = explanations[agentId] || explanations['trend-momentum-agent'];

  return (
    <Accordion
      expanded={expanded}
      onChange={(_, isExpanded) => setExpanded(isExpanded)}
      sx={{
        bgcolor: 'rgba(15, 23, 42, 0.6)',
        border: `1px solid ${agentColor.primary}30`,
        borderRadius: 2,
        mb: 2,
        '&:before': { display: 'none' },
        '&.Mui-expanded': {
          borderColor: `${agentColor.primary}60`,
          boxShadow: `0 4px 20px ${agentColor.primary}20`,
        },
      }}
    >
      <AccordionSummary
        expandIcon={<ExpandMore sx={{ color: agentColor.primary }} />}
        sx={{
          '& .MuiAccordionSummary-content': {
            my: 2,
          },
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
          <Lightbulb sx={{ color: agentColor.primary, fontSize: 28 }} />
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.25rem', mb: 0.5 }}>
              Understanding {agentName}
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.95rem' }}>
              {model} • Click to learn more
            </Typography>
          </Box>
        </Box>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {/* Simple Explanation */}
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
              <Lightbulb sx={{ color: agentColor.primary, fontSize: 20 }} />
              <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem', color: agentColor.primary }}>
                Simple Explanation
              </Typography>
            </Box>
            <Typography variant="body1" sx={{ fontSize: '1.05rem', lineHeight: 1.8, color: 'text.primary' }}>
              {explanation.simple}
            </Typography>
          </Box>

          {/* Technical Explanation */}
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
              <Science sx={{ color: agentColor.primary, fontSize: 20 }} />
              <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem', color: agentColor.primary }}>
                Technical Deep Dive
              </Typography>
            </Box>
            <Typography variant="body1" sx={{ fontSize: '1.05rem', lineHeight: 1.8, color: 'text.primary', mb: 2 }}>
              {explanation.technical}
            </Typography>
          </Box>

          {/* Innovation */}
          <Box
            sx={{
              p: 2.5,
              borderRadius: 2,
              bgcolor: `${agentColor.primary}10`,
              border: `1px solid ${agentColor.primary}30`,
            }}
          >
            <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem', mb: 1.5, color: agentColor.primary }}>
              Innovation & Breakthrough
            </Typography>
            <Typography variant="body1" sx={{ fontSize: '1.05rem', lineHeight: 1.8, color: 'text.primary' }}>
              {explanation.innovation}
            </Typography>
          </Box>

          {/* Advantages */}
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.1rem', mb: 1.5, color: agentColor.primary }}>
              Key Advantages
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              {explanation.advantages.map((advantage, index) => (
                <Box
                  key={index}
                  sx={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 1.5,
                    p: 1.5,
                    borderRadius: 1.5,
                    bgcolor: 'rgba(255, 255, 255, 0.03)',
                  }}
                >
                  <Box
                    sx={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      bgcolor: agentColor.primary,
                      mt: 1,
                      flexShrink: 0,
                    }}
                  />
                  <Typography variant="body1" sx={{ fontSize: '1.05rem', lineHeight: 1.7, color: 'text.primary' }}>
                    {advantage}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>
        </Box>
      </AccordionDetails>
    </Accordion>
  );
};

export default AgentExplanation;

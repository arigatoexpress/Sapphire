import React from 'react';
import { Box, Typography, Card, CardContent, Grid, Chip, Avatar, Tabs, Tab, Container } from '@mui/material';
import AgentActivityGrid from '../components/AgentActivityGrid';
import AgentPerformanceMetrics from '../components/AgentPerformanceMetrics';
import AgentModelCards from '../components/AgentModelCards';
import BotAlerts from '../components/BotAlerts';
import ChatHistory from '../components/ChatHistory';
import RegulatoryDisclaimer from '../components/RegulatoryDisclaimer';
import AgentExplanation from '../components/AgentExplanation';
import { useTrading } from '../contexts/TradingContext';

const Agents: React.FC = () => {
  const [tabValue, setTabValue] = React.useState(0);
  const { agentActivities } = useTrading();

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const agentConfig = [
    { 
      id: 'trend-momentum-agent', 
      name: 'Trend Momentum', 
      model: 'Gemini 2.0 Flash Exp',
      capital: '$100',
      specialty: 'Lightning-fast momentum trading',
      status: 'active'
    },
    { 
      id: 'strategy-optimization-agent', 
      name: 'Strategy Optimization', 
      model: 'Gemini Exp-1206',
      capital: '$100',
      specialty: 'Advanced analytical reasoning',
      status: 'active'
    },
    { 
      id: 'financial-sentiment-agent', 
      name: 'Financial Sentiment', 
      model: 'Gemini 2.0 Flash Exp',
      capital: '$100',
      specialty: 'Real-time sentiment analysis',
      status: 'active'
    },
    { 
      id: 'market-prediction-agent', 
      name: 'Market Prediction', 
      model: 'Gemini Exp-1206',
      capital: '$100',
      specialty: 'Time series forecasting',
      status: 'active'
    },
    { 
      id: 'volume-microstructure-agent', 
      name: 'Volume Microstructure', 
      model: 'Codey 001',
      capital: '$100',
      specialty: 'Order flow analysis',
      status: 'active'
    },
    { 
      id: 'vpin-hft', 
      name: 'VPIN HFT', 
      model: 'Gemini 2.0 Flash Exp',
      capital: '$100',
      specialty: 'Toxicity detection HFT',
      status: 'active'
    },
  ];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box sx={{ mb: { xs: 3, md: 4 } }}>
        <Typography 
          variant="h1" 
          gutterBottom 
          sx={{ 
            fontWeight: 900,
            fontSize: { xs: '2rem', md: '3rem' },
            color: '#FFFFFF',
            mb: { xs: 1, md: 1.5 },
            lineHeight: 1.1,
          }}
        >
          AI Trading Agents
        </Typography>
        <Typography 
          variant="h6" 
          sx={{ 
            fontSize: { xs: '1rem', md: '1.125rem' },
            fontWeight: 500,
            color: '#E2E8F0',
            maxWidth: '900px',
            lineHeight: 1.6,
          }}
        >
          Six specialized AI agents powered by Google Gemini models, with Grok 4.1 arbitration resolving conflicts. 
          Each agent trades independently with $100 capital and competes for best performance.
        </Typography>
      </Box>

      {/* Regulatory Disclaimer */}
      <RegulatoryDisclaimer />

      {/* AI Agent Model Cards */}
      <Box sx={{ mb: 4 }}>
        <AgentModelCards />
      </Box>

      {/* Bot Alerts - Live below AI model information */}
      <BotAlerts />

      {/* Agent Explanations */}
      <Box sx={{ mb: 4 }}>
        <Typography 
          variant="h5" 
          sx={{ 
            fontWeight: 700, 
            mb: 3,
            fontSize: '1.5rem',
            color: 'text.primary',
          }}
        >
          Understanding Our AI Agents
        </Typography>
        <Grid container spacing={3}>
          {agentConfig.map((agent) => (
            <Grid item xs={12} key={agent.id}>
              <AgentExplanation 
                agentId={agent.id}
                agentName={agent.name}
                model={agent.model}
              />
            </Grid>
          ))}
        </Grid>
      </Box>

      <Tabs 
        value={tabValue} 
        onChange={handleTabChange} 
        sx={{ 
          mb: 4, 
          borderBottom: 1, 
          borderColor: 'divider',
          '& .MuiTab-root': {
            fontSize: '1.1rem',
            fontWeight: 600,
            minHeight: 56,
            textTransform: 'none',
          },
        }}
      >
        <Tab label="Agent Activity" />
        <Tab label="Performance Metrics" />
        <Tab label="Chat History" />
      </Tabs>

      {tabValue === 0 && (
        <AgentActivityGrid />
      )}

      {tabValue === 1 && (
        <AgentPerformanceMetrics />
      )}

      {tabValue === 2 && (
        <ChatHistory />
      )}
    </Container>
  );
};

export default Agents;

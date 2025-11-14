import React from 'react';
import { Box, Typography, Card, CardContent, Grid, Chip, Avatar, Tabs, Tab, Container } from '@mui/material';
import AgentActivityGrid from '../components/AgentActivityGrid';
import AgentPerformanceMetrics from '../components/AgentPerformanceMetrics';
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
    { id: 'trend-momentum-agent', name: 'Trend Momentum', model: 'Gemini 2.0 Flash Exp' },
    { id: 'strategy-optimization-agent', name: 'Strategy Optimization', model: 'Gemini Exp-1206' },
    { id: 'financial-sentiment-agent', name: 'Financial Sentiment', model: 'Gemini 2.0 Flash Exp' },
    { id: 'market-prediction-agent', name: 'Market Prediction', model: 'Gemini Exp-1206' },
    { id: 'volume-microstructure-agent', name: 'Volume Microstructure', model: 'Codey 001' },
    { id: 'vpin-hft', name: 'VPIN HFT', model: 'Gemini 2.0 Flash Exp' },
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
          Monitor six specialized AI agents powered by Google Gemini models
        </Typography>
      </Box>

      {/* Regulatory Disclaimer */}
      <RegulatoryDisclaimer />

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
      </Tabs>

      {tabValue === 0 && (
        <AgentActivityGrid />
      )}

      {tabValue === 1 && (
        <AgentPerformanceMetrics />
      )}
    </Container>
  );
};

export default Agents;

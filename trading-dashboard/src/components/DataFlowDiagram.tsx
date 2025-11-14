import React, { useEffect, useRef, useState } from 'react';
import { Box, Typography, Paper, Stepper, Step, StepLabel, StepContent, Card, CardContent } from '@mui/material';
import { ArrowForward, Cloud, Storage, Psychology, TrendingUp } from '@mui/icons-material';

const DataFlowDiagram: React.FC = () => {
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveStep((prev) => (prev + 1) % 6);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const steps = [
    {
      label: 'Market Data Ingestion',
      description: 'Aster DEX API provides real-time market data including price feeds, order book depth, and trade history.',
      icon: <Cloud sx={{ fontSize: 40, color: '#10B981' }} />,
      details: [
        'Real-time price streaming for perpetual futures',
        'Order book depth analysis',
        'Trade history and volume data',
        'WebSocket connections for low-latency updates',
      ],
    },
    {
      label: 'Data Processing & Caching',
      description: 'Cloud Trader service processes incoming data and stores frequently accessed information in Redis cache for fast retrieval.',
      icon: <Storage sx={{ fontSize: 40, color: '#0EA5E9' }} />,
      details: [
        'Data normalization and validation',
        'Redis caching for performance optimization',
        'Multi-level cache strategy',
        'Data aggregation and preprocessing',
      ],
    },
    {
      label: 'MCP Coordination',
      description: 'MCP Coordinator receives processed data and distributes relevant information to specialized AI agents based on their expertise.',
      icon: <Psychology sx={{ fontSize: 40, color: '#8B5CF6' }} />,
      details: [
        'Intelligent data routing to agents',
        'Inter-agent communication orchestration',
        'Workflow coordination',
        'Message queuing and prioritization',
      ],
    },
    {
      label: 'AI Agent Analysis',
      description: 'Each specialized AI agent analyzes the data using its unique model (Gemini 2.0 Flash, Exp-1206, or Codey) to generate trading insights.',
      icon: <TrendingUp sx={{ fontSize: 40, color: '#06B6D4' }} />,
      details: [
        'Momentum analysis (Gemini 2.0 Flash Exp)',
        'Strategy optimization (Gemini Exp-1206)',
        'Sentiment analysis (Gemini 2.0 Flash Exp)',
        'Market prediction (Gemini Exp-1206)',
        'Volume microstructure (Codey 001)',
        'VPIN HFT analysis (Gemini 2.0 Flash Exp)',
      ],
    },
    {
      label: 'Decision Aggregation',
      description: 'MCP Coordinator aggregates insights from all agents, applies risk management rules, and generates final trading signals.',
      icon: <Psychology sx={{ fontSize: 40, color: '#F59E0B' }} />,
      details: [
        'Multi-agent consensus building',
        'Risk assessment and position sizing',
        'Portfolio optimization',
        'Signal confidence scoring',
      ],
    },
    {
      label: 'Trade Execution',
      description: 'Cloud Trader executes trades on Aster DEX based on approved signals, with real-time monitoring and position management.',
      icon: <ArrowForward sx={{ fontSize: 40, color: '#EF4444' }} />,
      details: [
        'Order placement via Aster DEX API',
        'Position monitoring and management',
        'Stop-loss and take-profit execution',
        'Real-time P&L tracking',
      ],
    },
  ];

  return (
    <Box>
      <Paper
        elevation={0}
        sx={{
          p: 4,
          background: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(148, 163, 184, 0.1)',
          borderRadius: 3,
        }}
      >
        <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, fontSize: '1.25rem' }}>
          Data Flow Architecture
        </Typography>
        <Typography variant="body1" sx={{ color: 'text.secondary', mb: 4, fontSize: '1.05rem', lineHeight: 1.7 }}>
          Understanding how data flows through the system from market data ingestion to trade execution. 
          Each step represents a critical component in the trading pipeline.
        </Typography>

        <Stepper activeStep={activeStep} orientation="vertical">
          {steps.map((step, index) => (
            <Step key={step.label} active={index === activeStep} completed={index < activeStep}>
              <StepLabel
                StepIconComponent={() => (
                  <Box
                    sx={{
                      width: 56,
                      height: 56,
                      borderRadius: '50%',
                      bgcolor: index === activeStep ? step.icon.props.color : 'rgba(148, 163, 184, 0.2)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'all 0.3s ease',
                      boxShadow: index === activeStep ? `0 0 20px ${step.icon.props.color}40` : 'none',
                    }}
                  >
                    {React.cloneElement(step.icon, {
                      sx: {
                        fontSize: 40,
                        color: index === activeStep ? '#FFFFFF' : 'rgba(148, 163, 184, 0.5)',
                      },
                    })}
                  </Box>
                )}
              >
                <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.25rem', color: 'text.primary' }}>
                  {step.label}
                </Typography>
              </StepLabel>
              <StepContent>
                <Card
                  sx={{
                    mt: 2,
                    mb: 4,
                    bgcolor: 'rgba(15, 23, 42, 0.8)',
                    border: `1px solid ${step.icon.props.color}30`,
                    borderRadius: 2,
                  }}
                >
                  <CardContent>
                    <Typography variant="body1" sx={{ mb: 3, fontSize: '1.05rem', lineHeight: 1.8, color: 'text.primary' }}>
                      {step.description}
                    </Typography>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                      {step.details.map((detail, idx) => (
                        <Box key={idx} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
                          <Box
                            sx={{
                              width: 6,
                              height: 6,
                              borderRadius: '50%',
                              bgcolor: step.icon.props.color,
                              mt: 1,
                              flexShrink: 0,
                            }}
                          />
                          <Typography variant="body2" sx={{ fontSize: '0.95rem', lineHeight: 1.7, color: 'text.secondary' }}>
                            {detail}
                          </Typography>
                        </Box>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </StepContent>
            </Step>
          ))}
        </Stepper>
      </Paper>
    </Box>
  );
};

export default DataFlowDiagram;


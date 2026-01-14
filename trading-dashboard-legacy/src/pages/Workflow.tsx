import React, { useState } from 'react';
import {
  Container,
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  Paper,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Chip,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  LinearProgress,
  Alert,
  AlertTitle,
} from '@mui/material';
import {
  ExpandMore,
  ArrowForward,
  DataObject,
  Psychology,
  Memory,
  Speed,
  Cloud,
  Api,
  Storage,
  NetworkCheck,
  TrendingUp,
  Security,
  AutoAwesome,
  Code,
  Settings,
  ShowChart,
  FlashOn,
} from '@mui/icons-material';

const Workflow: React.FC = () => {
  const [activeStep, setActiveStep] = useState(0);
  const [expandedSection, setExpandedSection] = useState<string | false>('data-flow');

  const workflowSteps = [
    {
      label: 'Data Ingestion',
      icon: <DataObject />,
      description: 'Market data collection and normalization',
      details: {
        sources: ['Aster DEX WebSocket API', 'REST API for historical data'],
        frequency: 'Real-time (WebSocket) + 15s polling (REST)',
        dataTypes: ['Price ticks', 'Order book depth', 'Trade history', 'Volume metrics'],
        processing: 'Stream processing with buffering and deduplication',
      },
      technical: {
        protocol: 'WebSocket (WSS) with JSON-RPC 2.0',
        rateLimits: '100 requests/second per connection',
        compression: 'GZIP compression for historical data',
        caching: 'Redis cache with 5-minute TTL for frequently accessed symbols',
      },
    },
    {
      label: 'AI Analysis Layer',
      icon: <Psychology />,
      description: 'Multi-agent AI inference and strategy evaluation',
      details: {
        agents: [
          'Trend Momentum Agent (Gemini 2.0 Flash Exp)',
          'Strategy Optimization Agent (Gemini Exp-1206)',
          'Financial Sentiment Agent (Gemini 2.0 Flash Exp)',
          'Market Prediction Agent (Gemini Exp-1206)',
          'Volume Microstructure Agent (Codey 001)',
          'VPIN HFT Agent (Gemini 2.0 Flash Exp)',
        ],
        coordination: 'MCP (Multi-Agent Coordination Protocol)',
        inference: 'Parallel async inference via Vertex AI API',
        promptEngineering: 'Structured prompts with few-shot examples',
      },
      technical: {
        endpoint: 'Vertex AI Gemini API (us-central1)',
        modelTypes: ['text-bison@001', 'code-bison@001', 'chat-bison@001'],
        latency: '200-800ms per inference request',
        concurrency: 'Up to 6 parallel agent inferences',
        tokenLimit: '8192 tokens per request',
      },
    },
    {
      label: 'Signal Generation',
      icon: <ShowChart />,
      description: 'Trading signal synthesis from multiple agents',
      details: {
        aggregation: 'Weighted consensus from all agents',
        scoring: 'Confidence-weighted strategy selection',
        filtering: 'Minimum confidence threshold (0.1)',
        prioritization: 'Activity score and historical performance',
      },
      technical: {
        algorithm: 'Multi-signal fusion with confidence weighting',
        threshold: 'MIN_CONFIDENCE_THRESHOLD = 0.1',
        scoring: 'Exponential decay for historical performance',
        selection: 'Highest scored non-HOLD signal wins',
      },
    },
    {
      label: 'Risk Management',
      icon: <Security />,
      description: 'Pre-trade risk checks and position sizing',
      details: {
        checks: [
          'Portfolio drawdown limits',
          'Position size limits (Kelly Criterion)',
          'Circuit breakers',
          'Daily loss limits',
          'Leverage restrictions',
        ],
        sizing: 'Dynamic position sizing based on confidence and volatility',
        limits: 'Maximum 5% of portfolio per position',
      },
      technical: {
        kellyCriterion: 'f = (p*b - q) / b where p=win prob, b=odds, q=1-p',
        maxPosition: 'CAPITAL_ALLOCATION * base_position_fraction',
        drawdownLimit: 'Max 20% portfolio drawdown',
        circuitBreaker: 'Stop trading if 3 consecutive failures',
      },
    },
    {
      label: 'Order Execution',
      icon: <FlashOn />,
      description: 'Trade execution on Aster DEX',
      details: {
        exchange: 'Aster DEX perpetual futures',
        orderTypes: ['Market orders', 'Limit orders (future)'],
        symbols: '155+ USDT perpetual contracts',
        slippage: 'Dynamic slippage tolerance based on volatility',
      },
      technical: {
        api: 'Aster DEX REST API with HMAC-SHA256 authentication',
        endpoint: 'https://api.aster.network/v1/orders',
        rateLimit: '10 orders/second',
        timeout: '5 second request timeout',
        retry: 'Exponential backoff with 3 retries',
      },
    },
    {
      label: 'Monitoring & Feedback',
      icon: <NetworkCheck />,
      description: 'Real-time monitoring and performance tracking',
      details: {
        metrics: [
          'Agent activity scores',
          'Trade success rates',
          'Portfolio performance',
          'System health',
          'API latency',
        ],
        alerting: 'Real-time alerts for high-confidence signals',
        feedback: 'Continuous model performance evaluation',
      },
      technical: {
        metricsBackend: 'Prometheus + Grafana',
        updateFrequency: '5s for metrics, 15s for portfolio',
        alerting: 'Pub/Sub notifications for critical events',
        logging: 'Structured JSON logging with correlation IDs',
      },
    },
  ];

  const architectureLayers = [
    {
      name: 'Infrastructure Layer',
      description: 'Google Kubernetes Engine (GKE) cluster providing scalable container orchestration',
      components: [
        { name: 'GKE Cluster', spec: '3 node pool with auto-scaling (1-10 nodes)' },
        { name: 'Load Balancer', spec: 'Global HTTP(S) load balancer with CDN' },
        { name: 'Container Registry', spec: 'Google Artifact Registry for Docker images' },
      ],
      color: '#0EA5E9',
    },
    {
      name: 'Core Services Layer',
      description: 'Essential services for data processing and coordination',
      components: [
        { name: 'Cloud Trader API', spec: 'FastAPI service handling market data and trade execution' },
        { name: 'MCP Coordinator', spec: 'Multi-Agent Coordination Protocol orchestrator' },
        { name: 'Redis Cache', spec: 'In-memory cache for market data and agent state' },
      ],
      color: '#8B5CF6',
    },
    {
      name: 'AI Agents Layer',
      description: 'Six specialized AI trading agents with distinct roles',
      components: [
        { name: 'Analysis Agents', spec: 'Volume Microstructure, Trend Momentum, Financial Sentiment' },
        { name: 'Strategy Agents', spec: 'Strategy Optimization, Market Prediction' },
        { name: 'Execution Agent', spec: 'VPIN HFT for high-frequency trade execution' },
      ],
      color: '#10B981',
    },
    {
      name: 'External Services Layer',
      description: 'Third-party APIs and services',
      components: [
        { name: 'Aster DEX API', spec: 'WebSocket + REST API for market data and execution' },
        { name: 'Vertex AI', spec: 'Google Cloud AI platform for model inference' },
      ],
      color: '#F59E0B',
    },
  ];

  const handleStepClick = (step: number) => {
    setActiveStep(step);
  };

  const handleSectionChange = (section: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedSection(isExpanded ? section : false);
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: { xs: 3, md: 4 } }}>
        <Typography
          variant="h1"
          sx={{
            fontWeight: 900,
            fontSize: { xs: '2rem', md: '3rem' },
            color: '#FFFFFF',
            mb: { xs: 1, md: 1.5 },
            lineHeight: 1.1,
          }}
        >
          Application Workflow
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
          Technical deep-dive into how the AI trading system processes market data, generates signals, and executes trades
        </Typography>
      </Box>

      {/* Architecture Overview */}
      <Paper
        sx={{
          p: 4,
          mb: 4,
          background: 'linear-gradient(135deg, rgba(14, 165, 233, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%)',
          border: '1px solid rgba(14, 165, 233, 0.3)',
          borderRadius: 3,
        }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, color: '#FFFFFF' }}>
          System Architecture
        </Typography>
        <Grid container spacing={3}>
          {architectureLayers.map((layer, index) => (
            <Grid item xs={12} md={6} key={layer.name}>
              <Card
                sx={{
                  height: '100%',
                  background: `linear-gradient(135deg, ${layer.color}10, ${layer.color}05)`,
                  border: `2px solid ${layer.color}40`,
                  borderRadius: 2,
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    transform: 'translateY(-4px)',
                    borderColor: layer.color,
                    boxShadow: `0 8px 24px ${layer.color}30`,
                  },
                }}
              >
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                    <Box
                      sx={{
                        width: 48,
                        height: 48,
                        borderRadius: '50%',
                        bgcolor: `${layer.color}20`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        border: `2px solid ${layer.color}`,
                      }}
                    >
                      <Typography
                        variant="h6"
                        sx={{
                          color: layer.color,
                          fontWeight: 700,
                        }}
                      >
                        {index + 1}
                      </Typography>
                    </Box>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        color: layer.color,
                      }}
                    >
                      {layer.name}
                    </Typography>
                  </Box>
                  <Typography
                    variant="body2"
                    sx={{
                      color: 'rgba(255, 255, 255, 0.8)',
                      mb: 2,
                      lineHeight: 1.6,
                    }}
                  >
                    {layer.description}
                  </Typography>
                  <List dense>
                    {layer.components.map((component, idx) => (
                      <ListItem key={idx} sx={{ py: 0.5 }}>
                        <ListItemIcon sx={{ minWidth: 32 }}>
                          <ArrowForward sx={{ fontSize: 16, color: layer.color }} />
                        </ListItemIcon>
                        <ListItemText
                          primary={component.name}
                          secondary={component.spec}
                          primaryTypographyProps={{
                            sx: { fontSize: '0.875rem', fontWeight: 600, color: '#FFFFFF' },
                          }}
                          secondaryTypographyProps={{
                            sx: { fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.6)' },
                          }}
                        />
                      </ListItem>
                    ))}
                  </List>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Paper>

      {/* Workflow Stepper */}
      <Paper
        sx={{
          p: 4,
          mb: 4,
          background: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(24px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: 3,
        }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 4, color: '#FFFFFF' }}>
          Trading Workflow Pipeline
        </Typography>
        <Stepper activeStep={activeStep} orientation="vertical">
          {workflowSteps.map((step, index) => (
            <Step key={step.label}>
              <StepLabel
                onClick={() => handleStepClick(index)}
                sx={{
                  cursor: 'pointer',
                  '& .MuiStepLabel-iconContainer': {
                    cursor: 'pointer',
                  },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Box
                    sx={{
                      width: 40,
                      height: 40,
                      borderRadius: '50%',
                      bgcolor: activeStep === index ? 'primary.main' : 'rgba(255, 255, 255, 0.1)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: activeStep === index ? 'white' : 'text.secondary',
                      transition: 'all 0.3s ease',
                    }}
                  >
                    {step.icon}
                  </Box>
                  <Box>
                    <Typography
                      variant="h6"
                      sx={{
                        fontWeight: 700,
                        color: activeStep === index ? 'primary.main' : '#FFFFFF',
                      }}
                    >
                      {step.label}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: 'rgba(255, 255, 255, 0.7)',
                        fontSize: '0.875rem',
                      }}
                    >
                      {step.description}
                    </Typography>
                  </Box>
                </Box>
              </StepLabel>
              <StepContent>
                <Box sx={{ mt: 2, mb: 4 }}>
                  {/* Details Section */}
                  <Accordion
                    expanded={expandedSection === `details-${index}`}
                    onChange={handleSectionChange(`details-${index}`)}
                    sx={{
                      bgcolor: 'rgba(0, 0, 0, 0.3)',
                      mb: 2,
                      '&:before': { display: 'none' },
                    }}
                  >
                    <AccordionSummary expandIcon={<ExpandMore sx={{ color: '#FFFFFF' }} />}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 600, color: '#FFFFFF' }}>
                        📋 Operational Details
                      </Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Grid container spacing={2}>
                        {Object.entries(step.details).map(([key, value]) => (
                          <Grid item xs={12} md={6} key={key}>
                            <Typography
                              variant="overline"
                              sx={{
                                color: 'primary.main',
                                fontWeight: 700,
                                display: 'block',
                                mb: 1,
                              }}
                            >
                              {key.replace(/([A-Z])/g, ' $1').trim()}
                            </Typography>
                            {Array.isArray(value) ? (
                              <List dense>
                                {value.map((item, idx) => (
                                  <ListItem key={idx} sx={{ py: 0.5 }}>
                                    <ListItemIcon sx={{ minWidth: 24 }}>
                                      <ArrowForward sx={{ fontSize: 12 }} />
                                    </ListItemIcon>
                                    <ListItemText
                                      primary={item}
                                      primaryTypographyProps={{
                                        sx: { fontSize: '0.875rem', color: '#FFFFFF' },
                                      }}
                                    />
                                  </ListItem>
                                ))}
                              </List>
                            ) : (
                              <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.8)' }}>
                                {value}
                              </Typography>
                            )}
                          </Grid>
                        ))}
                      </Grid>
                    </AccordionDetails>
                  </Accordion>

                  {/* Technical Details */}
                  <Accordion
                    expanded={expandedSection === `technical-${index}`}
                    onChange={handleSectionChange(`technical-${index}`)}
                    sx={{
                      bgcolor: 'rgba(0, 0, 0, 0.3)',
                      '&:before': { display: 'none' },
                    }}
                  >
                    <AccordionSummary expandIcon={<ExpandMore sx={{ color: '#FFFFFF' }} />}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 600, color: '#FFFFFF' }}>
                        ⚙️ Technical Specifications
                      </Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Grid container spacing={2}>
                        {Object.entries(step.technical).map(([key, value]) => (
                          <Grid item xs={12} md={6} key={key}>
                            <Typography
                              variant="overline"
                              sx={{
                                color: '#06b6d4',
                                fontWeight: 700,
                                display: 'block',
                                mb: 1,
                              }}
                            >
                              {key.replace(/([A-Z])/g, ' $1').trim()}
                            </Typography>
                            <Paper
                              sx={{
                                p: 1.5,
                                bgcolor: 'rgba(6, 182, 212, 0.1)',
                                border: '1px solid rgba(6, 182, 212, 0.3)',
                                borderRadius: 1,
                              }}
                            >
                              <Typography
                                variant="body2"
                                sx={{
                                  color: '#FFFFFF',
                                  fontFamily: 'monospace',
                                  fontSize: '0.875rem',
                                }}
                              >
                                {value}
                              </Typography>
                            </Paper>
                          </Grid>
                        ))}
                      </Grid>
                    </AccordionDetails>
                  </Accordion>
                </Box>
              </StepContent>
            </Step>
          ))}
        </Stepper>
      </Paper>

      {/* Data Flow Diagram */}
      <Paper
        sx={{
          p: 4,
          mb: 4,
          background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(6, 182, 212, 0.1) 100%)',
          border: '1px solid rgba(16, 185, 129, 0.3)',
          borderRadius: 3,
        }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, color: '#FFFFFF' }}>
          Data Flow Architecture
        </Typography>
        <Box sx={{ position: 'relative', minHeight: '400px' }}>
          {/* Simplified visual data flow */}
          <Grid container spacing={3}>
            {workflowSteps.map((step, index) => (
              <Grid item xs={12} sm={6} md={4} key={step.label}>
                <Card
                  sx={{
                    height: '100%',
                    background: `linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(236, 72, 153, 0.1))`,
                    border: `2px solid rgba(139, 92, 246, 0.4)`,
                    borderRadius: 2,
                    p: 2,
                    position: 'relative',
                    transition: 'all 0.3s ease',
                    '&:hover': {
                      transform: 'scale(1.05)',
                      borderColor: 'rgba(139, 92, 246, 0.8)',
                    },
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
                    <Box
                      sx={{
                        width: 32,
                        height: 32,
                        borderRadius: '50%',
                        bgcolor: 'rgba(139, 92, 246, 0.3)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#8b5cf6',
                      }}
                    >
                      {step.icon}
                    </Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#FFFFFF' }}>
                      {step.label}
                    </Typography>
                  </Box>
                  <Typography
                    variant="caption"
                    sx={{ color: 'rgba(255, 255, 255, 0.7)', lineHeight: 1.5 }}
                  >
                    {step.description}
                  </Typography>
                  {index < workflowSteps.length - 1 && (
                    <Box
                      sx={{
                        position: 'absolute',
                        right: -16,
                        top: '50%',
                        transform: 'translateY(-50%)',
                        color: 'rgba(139, 92, 246, 0.6)',
                        zIndex: 1,
                        display: { xs: 'none', md: 'block' },
                      }}
                    >
                      <ArrowForward />
                    </Box>
                  )}
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      </Paper>

      {/* Performance Metrics */}
      <Paper
        sx={{
          p: 4,
          background: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(24px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: 3,
        }}
      >
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 3, color: '#FFFFFF' }}>
          System Performance Characteristics
        </Typography>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Alert severity="info" sx={{ bgcolor: 'rgba(6, 182, 212, 0.1)', border: '1px solid rgba(6, 182, 212, 0.3)' }}>
              <AlertTitle sx={{ color: '#06b6d4', fontWeight: 700 }}>
                ⚡ Latency Profile
              </AlertTitle>
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" sx={{ mb: 1, color: '#FFFFFF' }}>
                  <strong>Data Ingestion:</strong> &lt;50ms (WebSocket)
                </Typography>
                <Typography variant="body2" sx={{ mb: 1, color: '#FFFFFF' }}>
                  <strong>AI Inference:</strong> 200-800ms per agent
                </Typography>
                <Typography variant="body2" sx={{ mb: 1, color: '#FFFFFF' }}>
                  <strong>Signal Generation:</strong> &lt;10ms (in-memory)
                </Typography>
                <Typography variant="body2" sx={{ color: '#FFFFFF' }}>
                  <strong>Order Execution:</strong> 100-500ms (API round-trip)
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={75}
                  sx={{ mt: 2, height: 8, borderRadius: 4 }}
                />
                <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)', mt: 1, display: 'block' }}>
                  End-to-end latency: ~1-2 seconds per decision cycle
                </Typography>
              </Box>
            </Alert>
          </Grid>
          <Grid item xs={12} md={6}>
            <Alert severity="success" sx={{ bgcolor: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
              <AlertTitle sx={{ color: '#10b981', fontWeight: 700 }}>
                📊 Throughput
              </AlertTitle>
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" sx={{ mb: 1, color: '#FFFFFF' }}>
                  <strong>Market Data:</strong> 100+ symbols per second
                </Typography>
                <Typography variant="body2" sx={{ mb: 1, color: '#FFFFFF' }}>
                  <strong>AI Inferences:</strong> 6 parallel agents every 15s
                </Typography>
                <Typography variant="body2" sx={{ mb: 1, color: '#FFFFFF' }}>
                  <strong>Trades:</strong> Limited by risk management (max 5% per position)
                </Typography>
                <Typography variant="body2" sx={{ color: '#FFFFFF' }}>
                  <strong>API Rate Limit:</strong> 10 orders/second (Aster DEX)
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={60}
                  sx={{ mt: 2, height: 8, borderRadius: 4 }}
                />
                <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)', mt: 1, display: 'block' }}>
                  Decision interval: 15 seconds (configurable)
                </Typography>
              </Box>
            </Alert>
          </Grid>
        </Grid>
      </Paper>
    </Container>
  );
};

export default Workflow;

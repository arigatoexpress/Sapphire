import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  LinearProgress,
  Tooltip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Collapse,
  Alert,
} from '@mui/material';
import {
  Speed,
  Memory,
  AttachMoney,
  TrendingUp,
  Error,
  ExpandMore,
  ExpandLess,
  Refresh,
} from '@mui/icons-material';
import { getApiUrl } from '../utils/apiConfig';

// API base URL - resolved via centralized config
const API_BASE_URL = getApiUrl();

interface AgentMetrics {
  agent_id: string;
  latency: {
    last_inference_ms: number;
    avg_inference_ms: number;
    p95_inference_ms: number;
  };
  inference: {
    total_count: number;
    total_tokens_input: number;
    total_tokens_output: number;
    avg_cost_usd: number;
    model: string;
  };
  performance: {
    throughput: number;
    success_rate: number;
    avg_confidence: number;
    error_count: number;
  };
  timestamp: number;
}

interface AgentPerformanceMetricsProps {
  agentId?: string;
}

const AgentPerformanceMetrics: React.FC<AgentPerformanceMetricsProps> = ({ agentId }) => {
  const [metrics, setMetrics] = useState<Record<string, AgentMetrics>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedAgents, setExpandedAgents] = useState<Set<string>>(new Set());

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      setError(null);
      const url = agentId
        ? `${API_BASE_URL}/api/agents/metrics?agent_id=${agentId}`
        : `${API_BASE_URL}/api/agents/metrics`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch metrics: ${response.statusText}`);
      }

      const data = await response.json();

      if (agentId) {
        // Single agent response
        setMetrics({ [agentId]: data });
      } else {
        // Multiple agents response
        setMetrics(data.agents || {});
      }
    } catch (err) {
      console.error('Error fetching metrics:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch metrics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, [agentId]);

  const toggleAgent = (agentId: string) => {
    const newExpanded = new Set(expandedAgents);
    if (newExpanded.has(agentId)) {
      newExpanded.delete(agentId);
    } else {
      newExpanded.add(agentId);
    }
    setExpandedAgents(newExpanded);
  };

  const formatLatency = (ms: number) => {
    if (ms < 1) return `${(ms * 1000).toFixed(0)}μs`;
    if (ms < 1000) return `${ms.toFixed(2)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const formatCost = (usd: number) => {
    if (usd < 0.001) return `$${(usd * 1000).toFixed(3)}m`;
    if (usd < 1) return `$${(usd * 100).toFixed(2)}c`;
    return `$${usd.toFixed(2)}`;
  };

  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(2)}K`;
    return num.toFixed(0);
  };

  if (loading && Object.keys(metrics).length === 0) {
    return (
      <Box sx={{ p: 3 }}>
        <LinearProgress />
        <Typography variant="body2" sx={{ mt: 2, textAlign: 'center' }}>
          Loading performance metrics...
        </Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" action={
          <IconButton size="small" onClick={fetchMetrics}>
            <Refresh />
          </IconButton>
        }>
          {error}
        </Alert>
      </Box>
    );
  }

  const agents = Object.values(metrics);

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          Agent Performance Metrics
        </Typography>
        <IconButton onClick={fetchMetrics} disabled={loading}>
          <Refresh />
        </IconButton>
      </Box>

      <Grid container spacing={3}>
        {agents.map((agent) => (
          <Grid item xs={12} key={agent.agent_id}>
            <Card
              sx={{
                border: '1px solid',
                borderColor: 'divider',
                '&:hover': {
                  boxShadow: 4,
                },
              }}
            >
              <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {agent.agent_id.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </Typography>
                  <IconButton
                    size="small"
                    onClick={() => toggleAgent(agent.agent_id)}
                  >
                    {expandedAgents.has(agent.agent_id) ? <ExpandLess /> : <ExpandMore />}
                  </IconButton>
                </Box>

                {/* Summary Metrics */}
                <Grid container spacing={2} mb={2}>
                  <Grid item xs={6} sm={3}>
                    <Box textAlign="center">
                      <Speed sx={{ fontSize: 24, color: 'primary.main', mb: 0.5 }} />
                      <Typography variant="caption" color="text.secondary">
                        Avg Latency
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600 }}>
                        {formatLatency(agent.latency.avg_inference_ms)}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Box textAlign="center">
                      <TrendingUp sx={{ fontSize: 24, color: 'success.main', mb: 0.5 }} />
                      <Typography variant="caption" color="text.secondary">
                        Throughput
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600 }}>
                        {formatNumber(agent.performance.throughput)}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Box textAlign="center">
                      <Memory sx={{ fontSize: 24, color: 'info.main', mb: 0.5 }} />
                      <Typography variant="caption" color="text.secondary">
                        Tokens
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600 }}>
                        {formatNumber(agent.inference.total_tokens_input + agent.inference.total_tokens_output)}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Box textAlign="center">
                      <AttachMoney sx={{ fontSize: 24, color: 'warning.main', mb: 0.5 }} />
                      <Typography variant="caption" color="text.secondary">
                        Avg Cost
                      </Typography>
                      <Typography variant="h6" sx={{ fontWeight: 600 }}>
                        {formatCost(agent.inference.avg_cost_usd)}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>

                {/* Detailed Metrics */}
                <Collapse in={expandedAgents.has(agent.agent_id)}>
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell><strong>Metric</strong></TableCell>
                          <TableCell align="right"><strong>Value</strong></TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        <TableRow>
                          <TableCell>Model</TableCell>
                          <TableCell align="right">
                            <Chip label={agent.inference.model} size="small" />
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Last Inference Latency</TableCell>
                          <TableCell align="right">{formatLatency(agent.latency.last_inference_ms)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>P95 Inference Latency</TableCell>
                          <TableCell align="right">{formatLatency(agent.latency.p95_inference_ms)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Total Inferences</TableCell>
                          <TableCell align="right">{formatNumber(agent.inference.total_count)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Input Tokens</TableCell>
                          <TableCell align="right">{formatNumber(agent.inference.total_tokens_input)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Output Tokens</TableCell>
                          <TableCell align="right">{formatNumber(agent.inference.total_tokens_output)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Total Cost</TableCell>
                          <TableCell align="right">
                            {formatCost(agent.inference.avg_cost_usd * agent.inference.total_count)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Success Rate</TableCell>
                          <TableCell align="right">
                            <Chip
                              label={`${(agent.performance.success_rate * 100).toFixed(1)}%`}
                              size="small"
                              color={agent.performance.success_rate > 0.9 ? 'success' : 'default'}
                            />
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Avg Confidence</TableCell>
                          <TableCell align="right">
                            <Chip
                              label={`${(agent.performance.avg_confidence * 100).toFixed(1)}%`}
                              size="small"
                              color={agent.performance.avg_confidence > 0.7 ? 'success' : 'warning'}
                            />
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Error Count</TableCell>
                          <TableCell align="right">
                            {agent.performance.error_count > 0 ? (
                              <Chip
                                label={agent.performance.error_count}
                                size="small"
                                color="error"
                                icon={<Error />}
                              />
                            ) : (
                              <Chip label="0" size="small" color="success" />
                            )}
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Collapse>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {agents.length === 0 && !loading && (
        <Alert severity="info">
          No performance metrics available. Metrics will appear once agents start making decisions.
        </Alert>
      )}
    </Box>
  );
};

export default AgentPerformanceMetrics;

import React, { useState, useEffect } from 'react';
import { Box, Typography, Grid, Card, CardContent, LinearProgress, Chip, Tabs, Tab } from '@mui/material';
import { useTrading } from '../contexts/TradingContext';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Area, AreaChart } from 'recharts';

const SystemMetrics: React.FC = () => {
  const { agentActivities } = useTrading();
  const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d'>('24h');
  const [metricsTab, setMetricsTab] = useState(0);

  // Generate mock historical data
  const generateHistoricalData = () => {
    const data = [];
    const now = Date.now();
    const intervals = timeRange === '1h' ? 12 : timeRange === '24h' ? 24 : 168;
    const intervalMs = timeRange === '1h' ? 5 * 60 * 1000 : timeRange === '24h' ? 60 * 60 * 1000 : 60 * 60 * 1000;

    for (let i = intervals; i >= 0; i--) {
      const timestamp = now - (i * intervalMs);
      data.push({
        time: new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        cpu: 30 + Math.random() * 40,
        memory: 40 + Math.random() * 35,
        latency: 50 + Math.random() * 100,
        requests: 100 + Math.random() * 200,
        throughput: 50 + Math.random() * 100,
      });
    }
    return data;
  };

  const [historicalData, setHistoricalData] = useState(generateHistoricalData());

  useEffect(() => {
    setHistoricalData(generateHistoricalData());
    const interval = setInterval(() => {
      setHistoricalData(generateHistoricalData());
    }, 30000); // Update every 30 seconds
    return () => clearInterval(interval);
  }, [timeRange]);

  const currentMetrics = {
    cpu: 45.2,
    memory: 62.8,
    latency: 78,
    requests: 245,
    throughput: 85.3,
    errorRate: 0.12,
    uptime: 99.8,
  };

  const agentMetrics = agentActivities.map(agent => ({
    name: agent.agent_name,
    status: agent.status,
    activity: agent.activity_score,
    communications: agent.communication_count,
    trades: agent.trading_count || 0,
  }));

  return (
    <Box>
      {/* Time Range Selector */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'flex-end' }}>
        <Tabs value={timeRange} onChange={(_, value) => setTimeRange(value)}>
          <Tab label="1 Hour" value="1h" />
          <Tab label="24 Hours" value="24h" />
          <Tab label="7 Days" value="7d" />
        </Tabs>
      </Box>

      {/* Current Metrics Overview */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ bgcolor: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(14, 165, 233, 0.3)' }}>
            <CardContent>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1, fontSize: '0.95rem' }}>
                CPU Usage
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 800, color: 'primary.main', mb: 1, fontSize: '2rem' }}>
                {currentMetrics.cpu.toFixed(1)}%
              </Typography>
              <LinearProgress
                variant="determinate"
                value={currentMetrics.cpu}
                sx={{
                  height: 8,
                  borderRadius: 4,
                  bgcolor: 'rgba(14, 165, 233, 0.1)',
                  '& .MuiLinearProgress-bar': {
                    bgcolor: currentMetrics.cpu > 80 ? '#EF4444' : currentMetrics.cpu > 60 ? '#F59E0B' : '#0EA5E9',
                  },
                }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ bgcolor: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
            <CardContent>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1, fontSize: '0.95rem' }}>
                Memory Usage
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 800, color: 'secondary.main', mb: 1, fontSize: '2rem' }}>
                {currentMetrics.memory.toFixed(1)}%
              </Typography>
              <LinearProgress
                variant="determinate"
                value={currentMetrics.memory}
                sx={{
                  height: 8,
                  borderRadius: 4,
                  bgcolor: 'rgba(139, 92, 246, 0.1)',
                  '& .MuiLinearProgress-bar': {
                    bgcolor: currentMetrics.memory > 80 ? '#EF4444' : currentMetrics.memory > 60 ? '#F59E0B' : '#8B5CF6',
                  },
                }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ bgcolor: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(6, 182, 212, 0.3)' }}>
            <CardContent>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1, fontSize: '0.95rem' }}>
                Avg Latency
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 800, color: 'info.main', mb: 1, fontSize: '2rem' }}>
                {currentMetrics.latency}ms
              </Typography>
              <Chip
                label={currentMetrics.latency < 100 ? 'Excellent' : currentMetrics.latency < 200 ? 'Good' : 'Fair'}
                size="small"
                sx={{
                  bgcolor: currentMetrics.latency < 100 ? 'rgba(16, 185, 129, 0.2)' :
                           currentMetrics.latency < 200 ? 'rgba(245, 158, 11, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                  color: currentMetrics.latency < 100 ? '#10B981' :
                         currentMetrics.latency < 200 ? '#F59E0B' : '#EF4444',
                }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ bgcolor: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
            <CardContent>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1, fontSize: '0.95rem' }}>
                Requests/sec
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 800, color: 'success.main', mb: 1, fontSize: '2rem' }}>
                {currentMetrics.requests}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.85rem' }}>
                Throughput: {currentMetrics.throughput.toFixed(1)} MB/s
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Historical Charts */}
      <Tabs value={metricsTab} onChange={(_, value) => setMetricsTab(value)} sx={{ mb: 3 }}>
        <Tab label="Performance" />
        <Tab label="Resource Usage" />
        <Tab label="Agent Metrics" />
      </Tabs>

      {metricsTab === 0 && (
        <Card sx={{ mb: 3, bgcolor: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(148, 163, 184, 0.1)' }}>
          <CardContent>
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, fontSize: '1.25rem' }}>
              Performance Metrics ({timeRange})
            </Typography>
            <ResponsiveContainer width="100%" height={400}>
              <AreaChart data={historicalData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.1)" />
                <XAxis dataKey="time" stroke="#CBD5E1" />
                <YAxis stroke="#CBD5E1" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: 8,
                  }}
                />
                <Legend />
                <Area type="monotone" dataKey="latency" stroke="#06B6D4" fill="#06B6D4" fillOpacity={0.3} name="Latency (ms)" />
                <Area type="monotone" dataKey="requests" stroke="#10B981" fill="#10B981" fillOpacity={0.3} name="Requests/sec" />
                <Area type="monotone" dataKey="throughput" stroke="#8B5CF6" fill="#8B5CF6" fillOpacity={0.3} name="Throughput (MB/s)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {metricsTab === 1 && (
        <Card sx={{ mb: 3, bgcolor: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(148, 163, 184, 0.1)' }}>
          <CardContent>
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 3, fontSize: '1.25rem' }}>
              Resource Usage ({timeRange})
            </Typography>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={historicalData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.1)" />
                <XAxis dataKey="time" stroke="#CBD5E1" />
                <YAxis stroke="#CBD5E1" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: 8,
                  }}
                />
                <Legend />
                <Line type="monotone" dataKey="cpu" stroke="#0EA5E9" strokeWidth={2} name="CPU %" />
                <Line type="monotone" dataKey="memory" stroke="#8B5CF6" strokeWidth={2} name="Memory %" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {metricsTab === 2 && (
        <Grid container spacing={3}>
          {agentMetrics.map((agent, index) => (
            <Grid item xs={12} sm={6} md={4} key={index}>
              <Card sx={{ bgcolor: 'rgba(15, 23, 42, 0.8)', border: '1px solid rgba(148, 163, 184, 0.1)' }}>
                <CardContent>
                  <Typography variant="h6" sx={{ fontWeight: 700, mb: 2, fontSize: '1.1rem' }}>
                    {agent.name}
                  </Typography>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ color: 'text.secondary', mb: 0.5, fontSize: '0.9rem' }}>
                      Activity Score
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={agent.activity}
                      sx={{
                        height: 8,
                        borderRadius: 4,
                        bgcolor: 'rgba(14, 165, 233, 0.1)',
                        '& .MuiLinearProgress-bar': { bgcolor: '#0EA5E9' },
                      }}
                    />
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.85rem' }}>
                      {agent.activity.toFixed(0)}%
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.9rem' }}>
                      Communications:
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.9rem' }}>
                      {agent.communications}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.9rem' }}>
                      Trades:
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.9rem' }}>
                      {agent.trades}
                    </Typography>
                  </Box>
                  <Chip
                    label={agent.status}
                    size="small"
                    sx={{
                      mt: 2,
                      bgcolor: agent.status === 'active' || agent.status === 'trading' ? 'rgba(16, 185, 129, 0.2)' :
                               agent.status === 'analyzing' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(100, 116, 139, 0.2)',
                      color: agent.status === 'active' || agent.status === 'trading' ? '#10B981' :
                             agent.status === 'analyzing' ? '#F59E0B' : '#64748B',
                    }}
                  />
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
};

export default SystemMetrics;


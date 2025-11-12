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
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
} from '@mui/material';
import {
  Psychology,
  TrendingUp,
  Message,
  Settings,
  Info,
  Timeline,
  BarChart,
} from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

interface AgentCardProps {
  agent: {
    agent_id: string;
    activity_score: number;
    communication_count: number;
    trading_count: number;
    last_activity: string;
    participation_threshold: number;
  };
}

const AgentCard: React.FC<AgentCardProps> = ({ agent }) => {
  const [detailsOpen, setDetailsOpen] = useState(false);

  const getActivityColor = (score: number) => {
    if (score > 7) return '#00d4aa';
    if (score > 4) return '#ffaa00';
    return '#ff6b35';
  };

  const getActivityLevel = (score: number) => {
    if (score > 7) return 'High';
    if (score > 4) return 'Medium';
    return 'Low';
  };

  // Mock activity data for the chart
  const activityData = [
    { time: '1h', activity: Math.random() * 10 },
    { time: '2h', activity: Math.random() * 10 },
    { time: '3h', activity: Math.random() * 10 },
    { time: '4h', activity: Math.random() * 10 },
    { time: '5h', activity: Math.random() * 10 },
    { time: '6h', activity: agent.activity_score },
  ];

  const agentType = agent.agent_id.toLowerCase();
  const getAgentIcon = () => {
    if (agentType.includes('deepseek')) return '🤖';
    if (agentType.includes('qwen')) return '🧠';
    if (agentType.includes('fingpt')) return '📊';
    if (agentType.includes('lagllama')) return '📈';
    if (agentType.includes('freqtrade')) return '⚡';
    if (agentType.includes('hummingbot')) return '🤖';
    return '🎯';
  };

  return (
    <>
      <Card
        sx={{
          height: '100%',
          cursor: 'pointer',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            transform: 'translateY(-4px)',
            boxShadow: '0 12px 24px rgba(0, 212, 170, 0.15)',
            borderColor: 'primary.main',
          },
          border: '1px solid',
          borderColor: 'divider',
        }}
        onClick={() => setDetailsOpen(true)}
      >
        <CardContent sx={{ p: 3 }}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Box display="flex" alignItems="center" gap={2}>
              <Avatar
                sx={{
                  bgcolor: `${getActivityColor(agent.activity_score)}20`,
                  width: 48,
                  height: 48,
                  fontSize: '1.5rem',
                }}
              >
                {getAgentIcon()}
              </Avatar>
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 600, fontSize: '1.1rem' }}>
                  {agent.agent_id.replace('-', ' ').toUpperCase()}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {getActivityLevel(agent.activity_score)} Activity
                </Typography>
              </Box>
            </Box>
            <Tooltip title="View Details" arrow>
              <IconButton size="small">
                <Info sx={{ fontSize: 20 }} />
              </IconButton>
            </Tooltip>
          </Box>

          <Box sx={{ mb: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography variant="body2" color="text.secondary">
                Activity Score
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {agent.activity_score.toFixed(1)}
              </Typography>
            </Box>
            <LinearProgress
              variant="determinate"
              value={(agent.activity_score / 10) * 100}
              sx={{
                height: 8,
                borderRadius: 4,
                bgcolor: 'grey.200',
                '& .MuiLinearProgress-bar': {
                  bgcolor: getActivityColor(agent.activity_score),
                  borderRadius: 4,
                },
              }}
            />
          </Box>

          <Box display="flex" gap={1} flexWrap="wrap">
            <Chip
              label={`${agent.trading_count} Trades`}
              size="small"
              sx={{
                bgcolor: 'primary.main',
                color: 'primary.contrastText',
                fontSize: '0.75rem',
              }}
            />
            <Chip
              label={`${agent.communication_count} Messages`}
              size="small"
              sx={{
                bgcolor: 'secondary.main',
                color: 'secondary.contrastText',
                fontSize: '0.75rem',
              }}
            />
          </Box>

          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            Last active: {new Date(agent.last_activity).toLocaleTimeString()}
          </Typography>
        </CardContent>
      </Card>

      {/* Agent Details Dialog */}
      <Dialog
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        maxWidth="md"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: 3,
            bgcolor: 'background.paper',
          }
        }}
      >
        <DialogTitle sx={{ pb: 1 }}>
          <Box display="flex" alignItems="center" gap={2}>
            <Avatar sx={{ bgcolor: `${getActivityColor(agent.activity_score)}20`, width: 56, height: 56, fontSize: '2rem' }}>
              {getAgentIcon()}
            </Avatar>
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {agent.agent_id.replace('-', ' ').toUpperCase()}
              </Typography>
              <Typography variant="body1" color="text.secondary">
                {getActivityLevel(agent.activity_score)} Activity Agent
              </Typography>
            </Box>
          </Box>
        </DialogTitle>

        <DialogContent>
          <Grid container spacing={3} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <Card sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
                    Performance Metrics
                  </Typography>
                  <Box sx={{ mb: 2 }}>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Activity Score</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {agent.activity_score.toFixed(1)}/10
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={(agent.activity_score / 10) * 100}
                      sx={{
                        height: 8,
                        borderRadius: 4,
                        '& .MuiLinearProgress-bar': {
                          bgcolor: getActivityColor(agent.activity_score),
                        },
                      }}
                    />
                  </Box>

                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Box textAlign="center">
                        <Typography variant="h4" sx={{ color: 'primary.main', fontWeight: 700 }}>
                          {agent.trading_count}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Total Trades
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6}>
                      <Box textAlign="center">
                        <Typography variant="h4" sx={{ color: 'secondary.main', fontWeight: 700 }}>
                          {agent.communication_count}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Messages Sent
                        </Typography>
                      </Box>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
                    Activity Timeline (Last 6 Hours)
                  </Typography>
                  <Box sx={{ height: 200, mt: 2 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={activityData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis dataKey="time" stroke="#888" />
                        <YAxis stroke="#888" />
                        <RechartsTooltip
                          contentStyle={{
                            backgroundColor: '#1a1a1a',
                            border: '1px solid #333',
                            borderRadius: 8,
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="activity"
                          stroke={getActivityColor(agent.activity_score)}
                          fill={`${getActivityColor(agent.activity_score)}40`}
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </DialogContent>

        <DialogActions sx={{ p: 3, pt: 0 }}>
          <Button onClick={() => setDetailsOpen(false)} variant="outlined">
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

const AgentActivityGrid: React.FC = () => {
  const { agentActivities, loading } = useTrading();

  if (loading) {
    return (
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" gutterBottom sx={{ fontWeight: 600 }}>
          Agent Activity
        </Typography>
        <Grid container spacing={3}>
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Grid item xs={12} sm={6} md={4} key={i}>
              <Card sx={{ height: 200 }}>
                <CardContent sx={{ p: 3 }}>
                  <LinearProgress sx={{ mb: 2 }} />
                  <LinearProgress />
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
      <Box display="flex" alignItems="center" gap={2} mb={3}>
        <Psychology sx={{ fontSize: 28, color: 'primary.main' }} />
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          AI Agent Status
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {agentActivities.map((agent) => (
          <Grid item xs={12} sm={6} md={4} key={agent.agent_id}>
            <AgentCard agent={agent} />
          </Grid>
        ))}
      </Grid>

      {agentActivities.length === 0 && (
        <Card sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" color="text.secondary">
            No agent activity data available
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Agents will appear here once they start trading and communicating.
          </Typography>
        </Card>
      )}
    </Box>
  );
};

export default AgentActivityGrid;

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
  Info,
} from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';
import { useTheme } from '@mui/material/styles';
import { XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { AGENT_COLORS, STATUS_COLORS } from '../constants/colors';

interface AgentCardProps {
  agent: {
    agent_id: string;
    agent_type: 'trend-momentum-agent' | 'strategy-optimization-agent' | 'financial-sentiment-agent' | 'market-prediction-agent' | 'volume-microstructure-agent' | 'vpin-hft';
    agent_name: string;
    activity_score: number;
    communication_count: number;
    trading_count: number;
    last_activity: string;
    participation_threshold: number;
    specialization: string;
    color: string;
    status: 'active' | 'idle' | 'analyzing' | 'trading';
    gpu_utilization?: number;
    memory_usage?: number;
  };
}

const AgentCard: React.FC<AgentCardProps> = ({ agent }) => {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const theme = useTheme();

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return STATUS_COLORS.active;
      case 'trading': return STATUS_COLORS.trading;
      case 'analyzing': return STATUS_COLORS.analyzing;
      case 'idle': return STATUS_COLORS.idle;
      default: return STATUS_COLORS.active;
    }
  };

  const getAgentThemeColor = () => {
    const agentColor = AGENT_COLORS[agent.agent_type as keyof typeof AGENT_COLORS];
    return agentColor ? agentColor.primary : AGENT_COLORS.coordinator.primary;
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'active': return 'Active';
      case 'trading': return 'Trading';
      case 'analyzing': return 'Analyzing';
      case 'idle': return 'Idle';
      default: return 'Unknown';
    }
  };

  // Enhanced activity data for the chart
  const activityData = [
    { time: '1h', activity: Math.random() * 10 },
    { time: '2h', activity: Math.random() * 10 },
    { time: '3h', activity: Math.random() * 10 },
    { time: '4h', activity: Math.random() * 10 },
    { time: '5h', activity: Math.random() * 10 },
    { time: '6h', activity: agent.activity_score },
  ];

  const getAgentIcon = () => {
    switch (agent.agent_type) {
      case 'trend-momentum-agent': return '🎯'; // Target for momentum analysis
      case 'strategy-optimization-agent': return '🧠'; // Brain for strategy optimization
      case 'financial-sentiment-agent': return '💭'; // Thought bubble for sentiment analysis
      case 'market-prediction-agent': return '🔮'; // Crystal ball for prediction
      case 'volume-microstructure-agent': return '📊'; // Chart for microstructure
      case 'vpin-hft': return '⚡'; // Lightning for high-frequency trading
      default: return '🎯';
    }
  };

  const getAgentTypeLabel = (type: string) => {
    const agentColor = AGENT_COLORS[type as keyof typeof AGENT_COLORS];
    if (agentColor) {
      return agentColor.name;
    }
    // Fallback formatting
    return type.replace(/-/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
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
                  bgcolor: `${getAgentThemeColor()}20`,
                  border: `2px solid ${getAgentThemeColor()}`,
                  width: 48,
                  height: 48,
                  fontSize: '1.5rem',
                  boxShadow: `0 0 12px ${getAgentThemeColor()}40`,
                }}
              >
                {getAgentIcon()}
              </Avatar>
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 600, fontSize: '1.1rem' }}>
                  {agent.agent_name}
                </Typography>
                <Typography variant="body2" sx={{ color: getAgentThemeColor(), fontWeight: 500 }}>
                  {getStatusLabel(agent.status)} • {getAgentTypeLabel(agent.agent_type)}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.2 }}>
                  {agent.specialization}
                </Typography>
              </Box>
            </Box>
            <Box display="flex" flexDirection="column" alignItems="flex-end" gap={1}>
              <Tooltip title="View Details" arrow>
                <IconButton size="small">
                  <Info sx={{ fontSize: 20 }} />
                </IconButton>
              </Tooltip>
              <Chip
                label={getStatusLabel(agent.status)}
                size="small"
                sx={{
                  bgcolor: `${getStatusColor(agent.status)}20`,
                  color: getStatusColor(agent.status),
                  fontWeight: 600,
                  fontSize: '0.7rem',
                  height: 20,
                }}
              />
            </Box>
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
                  bgcolor: agent.color,
                  borderRadius: 4,
                },
              }}
            />
          </Box>

          <Box display="flex" gap={1} flexWrap="wrap" mb={1}>
            <Chip
              label={`${agent.trading_count} Trades`}
              size="small"
              sx={{
                bgcolor: getAgentThemeColor(),
                color: 'white',
                fontSize: '0.75rem',
                fontWeight: 600,
              }}
            />
            <Chip
              label={`${agent.communication_count} Messages`}
              size="small"
              sx={{
                bgcolor: 'secondary.main',
                color: 'secondary.contrastText',
                fontSize: '0.75rem',
                fontWeight: 600,
              }}
            />
            {agent.gpu_utilization && (
              <Chip
                label={`GPU: ${agent.gpu_utilization.toFixed(0)}%`}
                size="small"
                sx={{
                  bgcolor: 'warning.main',
                  color: 'warning.contrastText',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                }}
              />
            )}
            {agent.memory_usage && (
              <Chip
                label={`RAM: ${agent.memory_usage.toFixed(1)}GB`}
                size="small"
                sx={{
                  bgcolor: 'info.main',
                  color: 'info.contrastText',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                }}
              />
            )}
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
          <Box display="flex" alignItems="center" gap={3}>
            <Avatar
              sx={{
                bgcolor: `${getAgentThemeColor()}20`,
                border: `3px solid ${getAgentThemeColor()}`,
                width: 64,
                height: 64,
                fontSize: '2.5rem',
                boxShadow: `0 0 20px ${getAgentThemeColor()}60`,
              }}
            >
              {getAgentIcon()}
            </Avatar>
            <Box sx={{ flex: 1 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5, color: getAgentThemeColor() }}>
                {agent.agent_name}
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 600, color: 'text.primary', mb: 1 }}>
                {getAgentTypeLabel(agent.agent_type)}
              </Typography>
              <Box display="flex" alignItems="center" gap={2} mb={1}>
                <Chip
                  label={getStatusLabel(agent.status)}
                  sx={{
                    bgcolor: `${getStatusColor(agent.status)}20`,
                    color: getStatusColor(agent.status),
                    fontWeight: 600,
                    fontSize: '0.8rem',
                  }}
                />
                <Typography variant="body2" color="text.secondary">
                  {agent.specialization}
                </Typography>
              </Box>
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
                          bgcolor: agent.color,
                        },
                      }}
                    />
                  </Box>

                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Box textAlign="center">
                        <Typography variant="h4" sx={{ color: agent.color, fontWeight: 700 }}>
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
                    {agent.gpu_utilization && (
                      <Grid item xs={6}>
                        <Box textAlign="center">
                          <Typography variant="h4" sx={{ color: 'warning.main', fontWeight: 700 }}>
                            {agent.gpu_utilization.toFixed(0)}%
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            GPU Utilization
                          </Typography>
                        </Box>
                      </Grid>
                    )}
                    {agent.memory_usage && (
                      <Grid item xs={6}>
                        <Box textAlign="center">
                          <Typography variant="h4" sx={{ color: 'info.main', fontWeight: 700 }}>
                            {agent.memory_usage.toFixed(1)}GB
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Memory Usage
                          </Typography>
                        </Box>
                      </Grid>
                    )}
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
                          stroke={getAgentThemeColor()}
                          fill={`${getAgentThemeColor()}40`}
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

import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Chip,
  Fade,
  Collapse,
  IconButton,
  Alert,
  AlertTitle,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  LinearProgress,
} from '@mui/material';
import {
  Notifications,
  NotificationsActive,
  Close,
  Warning,
  CheckCircle,
  Info,
  Error as ErrorIcon,
  TrendingUp,
  TrendingDown,
  FlashOn,
  Psychology,
  Memory,
} from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';

interface BotAlert {
  id: string;
  type: 'success' | 'warning' | 'error' | 'info' | 'trade';
  severity: 'low' | 'medium' | 'high';
  title: string;
  message: string;
  timestamp: Date;
  agent?: string;
  symbol?: string;
  confidence?: number;
  metadata?: Record<string, any>;
}

const BotAlerts: React.FC = () => {
  const { agentActivities, recentSignals } = useTrading();
  const [alerts, setAlerts] = useState<BotAlert[]>([]);
  const [expanded, setExpanded] = useState(true);
  const [lastSignalCheck, setLastSignalCheck] = useState<Date>(new Date());

  // Generate alerts based on agent activities and signals
  useEffect(() => {
    const newAlerts: BotAlert[] = [];

    // Generate alerts from agent activities
    agentActivities.forEach((agent) => {
      // High activity score alert
      if (agent.activity_score >= 0.9 && agent.status === 'trading') {
        newAlerts.push({
          id: `agent-high-activity-${agent.agent_id}`,
          type: 'success',
          severity: 'medium',
          title: `${agent.agent_name} High Activity`,
          message: `Activity score: ${(agent.activity_score * 100).toFixed(0)}% - ${agent.status}`,
          timestamp: new Date(agent.last_activity),
          agent: agent.agent_name,
          metadata: {
            activity_score: agent.activity_score,
            communication_count: agent.communication_count,
          },
        });
      }

      // Active trading alert
      if (agent.status === 'trading' && agent.trading_count > 0) {
        newAlerts.push({
          id: `agent-trading-${agent.agent_id}-${Date.now()}`,
          type: 'trade',
          severity: 'high',
          title: `${agent.agent_name} Trading`,
          message: `Executing trades - ${agent.trading_count} total trades`,
          timestamp: new Date(),
          agent: agent.agent_name,
          confidence: agent.activity_score,
          metadata: {
            trading_count: agent.trading_count,
            specialization: agent.specialization,
          },
        });
      }

      // High communication alert
      if (agent.communication_count > 40) {
        newAlerts.push({
          id: `agent-communication-${agent.agent_id}`,
          type: 'info',
          severity: 'low',
          title: `${agent.agent_name} Active Communication`,
          message: `${agent.communication_count} messages in coordination protocol`,
          timestamp: new Date(agent.last_activity),
          agent: agent.agent_name,
        });
      }
    });

    // Generate alerts from recent signals
    recentSignals.forEach((signal) => {
      const signalTime = new Date(signal.timestamp);
      if (signalTime > lastSignalCheck) {
        newAlerts.push({
          id: `signal-${signal.symbol}-${signalTime.getTime()}`,
          type: 'trade',
          severity: signal.confidence > 0.7 ? 'high' : 'medium',
          title: `Trading Signal: ${signal.symbol}`,
          message: `${signal.side} signal with ${(signal.confidence * 100).toFixed(0)}% confidence - $${signal.notional.toFixed(2)}`,
          timestamp: signalTime,
          symbol: signal.symbol,
          confidence: signal.confidence,
          metadata: {
            side: signal.side,
            notional: signal.notional,
            price: signal.price,
            source: signal.source,
          },
        });
      }
    });

    if (newAlerts.length > 0) {
      setLastSignalCheck(new Date());
      setAlerts((prev) => {
        // Merge new alerts, remove duplicates, keep last 20
        const merged = [...newAlerts, ...prev];
        const unique = Array.from(
          new Map(merged.map((alert) => [alert.id, alert])).values()
        );
        return unique.slice(0, 20);
      });
    }
  }, [agentActivities, recentSignals, lastSignalCheck]);

  // Auto-expand on new high-severity alerts
  useEffect(() => {
    const highSeverity = alerts.filter(
      (a) => a.severity === 'high' && new Date().getTime() - a.timestamp.getTime() < 10000
    );
    if (highSeverity.length > 0) {
      setExpanded(true);
    }
  }, [alerts]);

  const getAlertIcon = (type: string) => {
    switch (type) {
      case 'success':
        return <CheckCircle sx={{ fontSize: 20 }} />;
      case 'warning':
        return <Warning sx={{ fontSize: 20 }} />;
      case 'error':
        return <ErrorIcon sx={{ fontSize: 20 }} />;
      case 'trade':
        return <FlashOn sx={{ fontSize: 20 }} />;
      default:
        return <Info sx={{ fontSize: 20 }} />;
    }
  };

  const getAlertColor = (type: string, severity: string) => {
    if (type === 'trade') return '#f59e0b';
    if (type === 'success') return '#10b981';
    if (type === 'warning') return '#f59e0b';
    if (type === 'error') return '#ef4444';
    return severity === 'high' ? '#06b6d4' : '#8b5cf6';
  };

  const activeAlerts = alerts.filter(
    (a) => new Date().getTime() - a.timestamp.getTime() < 300000 // Last 5 minutes
  );

  const unreadCount = activeAlerts.length;

  return (
    <Paper
      elevation={0}
      sx={{
        mt: 4,
        background: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(24px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: 3,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 2,
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(236, 72, 153, 0.1))',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box
            sx={{
              width: 40,
              height: 40,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 16px rgba(139, 92, 246, 0.3)',
            }}
          >
            {unreadCount > 0 ? (
              <NotificationsActive sx={{ color: 'white', fontSize: 20 }} />
            ) : (
              <Notifications sx={{ color: 'white', fontSize: 20 }} />
            )}
          </Box>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#FFFFFF' }}>
              Live Bot Alerts
            </Typography>
            <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
              Real-time notifications from AI trading agents
            </Typography>
          </Box>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {unreadCount > 0 && (
            <Chip
              label={unreadCount}
              size="small"
              sx={{
                bgcolor: '#ec4899',
                color: 'white',
                fontWeight: 700,
                animation: 'pulse 2s infinite',
                '@keyframes pulse': {
                  '0%, 100%': { transform: 'scale(1)' },
                  '50%': { transform: 'scale(1.1)' },
                },
              }}
            />
          )}
          <IconButton
            size="small"
            onClick={() => setExpanded(!expanded)}
            sx={{
              color: 'rgba(255, 255, 255, 0.7)',
              '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.1)' },
            }}
          >
            {expanded ? <Close /> : <Notifications />}
          </IconButton>
        </Box>
      </Box>

      {/* Alerts List */}
      <Collapse in={expanded}>
        <Box
          sx={{
            maxHeight: '500px',
            overflowY: 'auto',
            '&::-webkit-scrollbar': {
              width: '6px',
            },
            '&::-webkit-scrollbar-track': {
              background: 'rgba(139, 92, 246, 0.1)',
            },
            '&::-webkit-scrollbar-thumb': {
              background: 'rgba(139, 92, 246, 0.3)',
              borderRadius: '3px',
            },
          }}
        >
          {activeAlerts.length === 0 ? (
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <Psychology sx={{ fontSize: 48, color: 'rgba(255, 255, 255, 0.3)', mb: 2 }} />
              <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.6)' }}>
                No recent alerts. AI agents are monitoring the market...
              </Typography>
            </Box>
          ) : (
            <List sx={{ p: 0 }}>
              {activeAlerts.map((alert, index) => (
                <React.Fragment key={alert.id}>
                  <Fade in timeout={300}>
                    <ListItem
                      sx={{
                        p: 2,
                        background:
                          index % 2 === 0
                            ? 'rgba(255, 255, 255, 0.02)'
                            : 'transparent',
                        '&:hover': {
                          background: 'rgba(139, 92, 246, 0.1)',
                        },
                        transition: 'background 0.2s ease',
                      }}
                    >
                      <ListItemIcon
                        sx={{
                          minWidth: 40,
                          color: getAlertColor(alert.type, alert.severity),
                        }}
                      >
                        {getAlertIcon(alert.type)}
                      </ListItemIcon>
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                            <Typography
                              variant="subtitle2"
                              sx={{
                                fontWeight: 700,
                                color: '#FFFFFF',
                                fontSize: '0.95rem',
                              }}
                            >
                              {alert.title}
                            </Typography>
                            <Chip
                              label={alert.severity.toUpperCase()}
                              size="small"
                              sx={{
                                height: 18,
                                fontSize: '0.65rem',
                                fontWeight: 600,
                                bgcolor: `${getAlertColor(alert.type, alert.severity)}20`,
                                color: getAlertColor(alert.type, alert.severity),
                                border: `1px solid ${getAlertColor(alert.type, alert.severity)}40`,
                              }}
                            />
                          </Box>
                        }
                        secondary={
                          <Box>
                            <Typography
                              variant="body2"
                              sx={{
                                color: 'rgba(255, 255, 255, 0.8)',
                                mb: 1,
                                lineHeight: 1.5,
                              }}
                            >
                              {alert.message}
                            </Typography>
                            {alert.confidence && (
                              <Box sx={{ mb: 1 }}>
                                <Box
                                  sx={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    mb: 0.5,
                                  }}
                                >
                                  <Typography
                                    variant="caption"
                                    sx={{ color: 'rgba(255, 255, 255, 0.6)' }}
                                  >
                                    Confidence
                                  </Typography>
                                  <Typography
                                    variant="caption"
                                    sx={{
                                      color: getAlertColor(alert.type, alert.severity),
                                      fontWeight: 600,
                                    }}
                                  >
                                    {(alert.confidence * 100).toFixed(0)}%
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={alert.confidence * 100}
                                  sx={{
                                    height: 4,
                                    borderRadius: 2,
                                    bgcolor: 'rgba(255, 255, 255, 0.1)',
                                    '& .MuiLinearProgress-bar': {
                                      bgcolor: getAlertColor(alert.type, alert.severity),
                                      borderRadius: 2,
                                    },
                                  }}
                                />
                              </Box>
                            )}
                            <Box
                              sx={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 1,
                                mt: 1,
                              }}
                            >
                              <Typography
                                variant="caption"
                                sx={{
                                  color: 'rgba(255, 255, 255, 0.5)',
                                  fontSize: '0.75rem',
                                }}
                              >
                                {alert.timestamp.toLocaleTimeString([], {
                                  hour: '2-digit',
                                  minute: '2-digit',
                                  second: '2-digit',
                                })}
                              </Typography>
                              {alert.agent && (
                                <>
                                  <Typography
                                    variant="caption"
                                    sx={{
                                      color: 'rgba(255, 255, 255, 0.3)',
                                      fontSize: '0.75rem',
                                    }}
                                  >
                                    •
                                  </Typography>
                                  <Chip
                                    icon={<Memory sx={{ fontSize: 12 }} />}
                                    label={alert.agent}
                                    size="small"
                                    sx={{
                                      height: 18,
                                      fontSize: '0.65rem',
                                      bgcolor: 'rgba(139, 92, 246, 0.1)',
                                      color: '#8b5cf6',
                                      border: '1px solid rgba(139, 92, 246, 0.3)',
                                    }}
                                  />
                                </>
                              )}
                              {alert.symbol && (
                                <>
                                  <Typography
                                    variant="caption"
                                    sx={{
                                      color: 'rgba(255, 255, 255, 0.3)',
                                      fontSize: '0.75rem',
                                    }}
                                  >
                                    •
                                  </Typography>
                                  <Chip
                                    label={alert.symbol}
                                    size="small"
                                    sx={{
                                      height: 18,
                                      fontSize: '0.65rem',
                                      bgcolor: 'rgba(6, 182, 212, 0.1)',
                                      color: '#06b6d4',
                                      border: '1px solid rgba(6, 182, 212, 0.3)',
                                    }}
                                  />
                                </>
                              )}
                            </Box>
                          </Box>
                        }
                      />
                    </ListItem>
                  </Fade>
                  {index < activeAlerts.length - 1 && (
                    <Divider sx={{ borderColor: 'rgba(255, 255, 255, 0.05)' }} />
                  )}
                </React.Fragment>
              ))}
            </List>
          )}
        </Box>
      </Collapse>
    </Paper>
  );
};

export default BotAlerts;

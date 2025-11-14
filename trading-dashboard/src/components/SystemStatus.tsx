import React from 'react';
import { Box, Typography, Chip, Card, CardContent, Grid } from '@mui/material';
import { CheckCircle, Warning, Error as ErrorIcon, Info } from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';

const SystemStatus: React.FC = () => {
  const { portfolio, agentActivities } = useTrading();

  const getStatusMessage = () => {
    const activeAgents = agentActivities?.filter(a => a.status === 'active' || a.status === 'trading').length || 0;
    const totalAgents = agentActivities?.length || 6;
    
    if (activeAgents === totalAgents) {
      return {
        icon: <CheckCircle sx={{ color: '#10b981', fontSize: 20 }} />,
        text: "All systems operational! 🚀 All 6 AI agents are active and analyzing markets in real-time. The trading system is running smoothly and ready to execute trades.",
        color: '#10b981',
        bgColor: 'rgba(16, 185, 129, 0.1)',
        borderColor: 'rgba(16, 185, 129, 0.3)'
      };
    } else if (activeAgents >= totalAgents * 0.8) {
      return {
        icon: <Warning sx={{ color: '#f59e0b', fontSize: 20 }} />,
        text: `System mostly operational! ⚠️ ${activeAgents} out of ${totalAgents} agents are active. Most trading functions are working normally, but some agents may be initializing.`,
        color: '#f59e0b',
        bgColor: 'rgba(245, 158, 11, 0.1)',
        borderColor: 'rgba(245, 158, 11, 0.3)'
      };
    } else {
      return {
        icon: <ErrorIcon sx={{ color: '#ef4444', fontSize: 20 }} />,
        text: `System status: Limited operation. 🔴 Only ${activeAgents} out of ${totalAgents} agents are active. Some trading capabilities may be reduced. Please check agent status.`,
        color: '#ef4444',
        bgColor: 'rgba(239, 68, 68, 0.1)',
        borderColor: 'rgba(239, 68, 68, 0.3)'
      };
    }
  };

  const status = getStatusMessage();
  // Calculate bot trading capital from agent allocations
  const totalValue = portfolio?.agent_allocations ? Object.values(portfolio.agent_allocations).reduce((sum: number, val: any) => sum + (val || 0), 0) : 3000;
  const activeAgents = agentActivities?.filter(a => a.status === 'active' || a.status === 'trading').length || 0;

  return (
    <Card
      sx={{
        background: 'rgba(30, 41, 59, 0.6)',
        backdropFilter: 'blur(16px)',
        border: `1px solid ${status.borderColor}`,
        borderRadius: 3,
        mb: 3,
      }}
    >
      <CardContent sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          {status.icon}
          <Typography variant="h6" sx={{ fontWeight: 700, color: status.color }}>
            System Status
          </Typography>
        </Box>
        
        <Typography
          variant="body1"
          sx={{
            color: 'text.primary',
            lineHeight: 1.7,
            mb: 3,
            fontSize: '0.95rem',
          }}
        >
          {status.text}
        </Typography>

        <Grid container spacing={2}>
          <Grid item xs={6} sm={3}>
            <Box sx={{ textAlign: 'center', p: 2, borderRadius: 2, bgcolor: 'rgba(255, 255, 255, 0.05)' }}>
              <Typography variant="h4" sx={{ fontWeight: 900, color: 'primary.main', mb: 0.5 }}>
                {activeAgents}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                Active Agents
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={6} sm={3}>
            <Box sx={{ textAlign: 'center', p: 2, borderRadius: 2, bgcolor: 'rgba(255, 255, 255, 0.05)' }}>
              <Typography variant="h4" sx={{ fontWeight: 900, color: '#10b981', mb: 0.5 }}>
                ${totalValue.toLocaleString()}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                Bot Trading Capital
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={6} sm={3}>
            <Box sx={{ textAlign: 'center', p: 2, borderRadius: 2, bgcolor: 'rgba(255, 255, 255, 0.05)' }}>
              <Typography variant="h4" sx={{ fontWeight: 900, color: '#06b6d4', mb: 0.5 }}>
                Real-Time
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                Market Data
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={6} sm={3}>
            <Box sx={{ textAlign: 'center', p: 2, borderRadius: 2, bgcolor: 'rgba(255, 255, 255, 0.05)' }}>
              <Chip
                icon={status.icon}
                label="Operational"
                sx={{
                  bgcolor: status.bgColor,
                  color: status.color,
                  border: `1px solid ${status.borderColor}`,
                  fontWeight: 600,
                }}
              />
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

export default SystemStatus;


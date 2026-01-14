import React from 'react';
import { Box, Typography, Card, CardContent, Chip } from '@mui/material';
import { useTrading } from '../contexts/TradingContext';

const LiveMetricsPanel: React.FC = () => {
  const { portfolio, agentActivities, recentSignals } = useTrading();
  const activeAgents = agentActivities.filter(a => a.status === 'active' || a.status === 'trading').length;
  const totalTrades = agentActivities.reduce((sum, a) => sum + (a.trading_count || 0), 0);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Typography variant="h6" sx={{ fontWeight: 700, color: '#00ffff', mb: 1 }}>
        Live Metrics
      </Typography>

      <Card sx={{
        background: '#000000',
        border: '2px solid rgba(0, 255, 255, 0.3)',
        borderRadius: 2,
      }}>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="caption" sx={{ color: '#e2e8f0', display: 'block', mb: 1 }}>
            Total Capital
          </Typography>
          <Typography variant="h5" sx={{ fontWeight: 900, color: '#00ffff' }}>
            ${portfolio?.portfolio_value?.toLocaleString() || '3,000'}
          </Typography>
        </CardContent>
      </Card>

      <Card sx={{
        background: '#000000',
        border: '2px solid rgba(168, 85, 247, 0.3)',
        borderRadius: 2,
      }}>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="caption" sx={{ color: '#e2e8f0', display: 'block', mb: 1 }}>
            Active Agents
          </Typography>
          <Typography variant="h5" sx={{ fontWeight: 900, color: '#a855f7' }}>
            {activeAgents} / {agentActivities.length}
          </Typography>
        </CardContent>
      </Card>

      <Card sx={{
        background: '#000000',
        border: '2px solid rgba(0, 255, 255, 0.3)',
        borderRadius: 2,
      }}>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="caption" sx={{ color: '#e2e8f0', display: 'block', mb: 1 }}>
            Total Trades
          </Typography>
          <Typography variant="h5" sx={{ fontWeight: 900, color: '#00ffff' }}>
            {totalTrades}
          </Typography>
        </CardContent>
      </Card>

      <Card sx={{
        background: '#000000',
        border: '2px solid rgba(0, 255, 255, 0.3)',
        borderRadius: 2,
      }}>
        <CardContent sx={{ p: 2 }}>
          <Typography variant="caption" sx={{ color: '#e2e8f0', display: 'block', mb: 1 }}>
            Recent Signals
          </Typography>
          <Typography variant="h5" sx={{ fontWeight: 900, color: '#00ffff' }}>
            {recentSignals.length}
          </Typography>
        </CardContent>
      </Card>

      <Box sx={{ mt: 2 }}>
        <Typography variant="caption" sx={{ color: '#e2e8f0', display: 'block', mb: 1 }}>
          Agent Status
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {agentActivities.slice(0, 3).map((agent) => (
            <Box
              key={agent.agent_id}
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                p: 1,
                bgcolor: 'rgba(0, 255, 255, 0.05)',
                borderRadius: 1,
                border: '1px solid rgba(0, 255, 255, 0.2)',
              }}
            >
              <Typography variant="caption" sx={{ color: '#e2e8f0', fontSize: '0.75rem' }}>
                {agent.agent_name}
              </Typography>
              <Chip
                label={agent.status}
                size="small"
                sx={{
                  height: 18,
                  fontSize: '0.65rem',
                  bgcolor: agent.status === 'active' || agent.status === 'trading' ? 'rgba(0, 255, 0, 0.2)' : 'rgba(255, 255, 255, 0.1)',
                  color: agent.status === 'active' || agent.status === 'trading' ? '#00ff00' : '#e2e8f0',
                  border: `1px solid ${agent.status === 'active' || agent.status === 'trading' ? 'rgba(0, 255, 0, 0.4)' : 'rgba(255, 255, 255, 0.2)'}`,
                }}
              />
            </Box>
          ))}
        </Box>
      </Box>
    </Box>
  );
};

export default LiveMetricsPanel;

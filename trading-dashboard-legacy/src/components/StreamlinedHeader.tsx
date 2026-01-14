import React from 'react';
import { Box, Typography } from '@mui/material';
import { useTrading } from '../contexts/TradingContext';

const StreamlinedHeader: React.FC = () => {
  const { portfolio, agentActivities } = useTrading();
  const activeAgents = agentActivities.filter(a => a.status === 'active' || a.status === 'trading').length;

  return (
    <Box sx={{
      mb: 4,
      textAlign: 'center',
      background: 'transparent',
      border: '2px solid rgba(0, 255, 255, 0.3)',
      borderRadius: 4,
      p: 3,
      position: 'relative',
      overflow: 'hidden',
      boxShadow: '0 0 20px rgba(0, 255, 255, 0.1)',
    }}>
      <Box sx={{ position: 'relative', zIndex: 1 }}>
        <Typography
          variant="h2"
          sx={{
            mb: 1,
            fontWeight: 900,
            fontSize: { xs: '1.75rem', md: '2.5rem' },
            background: 'linear-gradient(135deg, #00ffff 0%, #a855f7 100%)',
            backgroundClip: 'text',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            textShadow: '0 0 20px rgba(0, 255, 255, 0.3)',
          }}
        >
          AI Trading System
        </Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 3, mt: 2, flexWrap: 'wrap' }}>
          <Typography variant="body2" sx={{ color: '#e2e8f0' }}>
            <strong style={{ color: '#00ffff' }}>${portfolio?.portfolio_value?.toLocaleString() || '3,000'}</strong> Trading Capital
          </Typography>
          <Typography variant="body2" sx={{ color: '#e2e8f0' }}>
            <strong style={{ color: '#00ffff' }}>{activeAgents}/{agentActivities.length}</strong> Active Agents
          </Typography>
          <Typography variant="body2" sx={{ color: '#e2e8f0' }}>
            <strong style={{ color: '#a855f7' }}>6</strong> Specialized AI Agents
          </Typography>
        </Box>
      </Box>
    </Box>
  );
};

export default StreamlinedHeader;

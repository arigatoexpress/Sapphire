import React from 'react';
import { Box, Alert, Button, Container, Typography } from '@mui/material';
import { useTrading } from '../contexts/TradingContext';
import EnhancedMetrics from '../components/EnhancedMetrics';
import AgentActivityGrid from '../components/AgentActivityGrid';
import PortfolioChart from '../components/PortfolioChart';

const Dashboard: React.FC = () => {
  const { error, refreshData } = useTrading();

  return (
    <Container maxWidth="xl" sx={{ py: 2 }}>
      {error && (
        <Alert
          severity="error"
          sx={{
            mb: 3,
            borderRadius: 2,
            '& .MuiAlert-message': { width: '100%' }
          }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={refreshData}
              sx={{ fontWeight: 600 }}
            >
              Retry
            </Button>
          }
        >
          <Box>
            <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5 }}>
              Connection Error
            </Typography>
            <Typography variant="body2">
              {error} - Click retry to refresh data from the trading system.
            </Typography>
          </Box>
        </Alert>
      )}

      {/* System Overview */}
      <Typography variant="h4" sx={{ mb: 1, fontWeight: 700 }}>
        Trading Operations Center
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
        Enterprise-grade autonomous trading system with real-time monitoring and AI-driven decision making.
      </Typography>

      {/* Key Performance Indicators */}
      <EnhancedMetrics />

      {/* Portfolio Performance */}
      <PortfolioChart />

      {/* AI Agent Activity */}
      <AgentActivityGrid />

      {/* System Status */}
      <Box
        sx={{
          mt: 4,
          p: 3,
          borderRadius: 2,
          bgcolor: 'background.paper',
          border: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
          System Status
        </Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 2 }}>
          <Box>
            <Typography variant="body2" color="text.secondary">Architecture</Typography>
            <Typography variant="body1" sx={{ fontWeight: 600 }}>Kubernetes + GCP</Typography>
          </Box>
          <Box>
            <Typography variant="body2" color="text.secondary">Uptime Target</Typography>
            <Typography variant="body1" sx={{ fontWeight: 600 }}>99.9%</Typography>
          </Box>
          <Box>
            <Typography variant="body2" color="text.secondary">AI Agents</Typography>
            <Typography variant="body1" sx={{ fontWeight: 600 }}>6 Active</Typography>
          </Box>
          <Box>
            <Typography variant="body2" color="text.secondary">Last Updated</Typography>
            <Typography variant="body1" sx={{ fontWeight: 600 }}>{new Date().toLocaleTimeString()}</Typography>
          </Box>
        </Box>
      </Box>
    </Container>
  );
};

export default Dashboard;

import React, { useState, useEffect } from 'react';
import { Container, Box, Typography, Grid, Card, CardContent, Chip, Tabs, Tab, Paper } from '@mui/material';
import { useTrading } from '../contexts/TradingContext';
import InfrastructureTopology from '../components/InfrastructureTopology';
import SystemMetrics from '../components/SystemMetrics';
import DataFlowDiagram from '../components/DataFlowDiagram';
import RegulatoryDisclaimer from '../components/RegulatoryDisclaimer';

const MissionControl: React.FC = () => {
  const [activeTab, setActiveTab] = useState(0);
  const { agentActivities, portfolio, loading } = useTrading();

  const tabs = [
    { label: 'Infrastructure Topology', value: 0 },
    { label: 'Data Flow', value: 1 },
    { label: 'System Metrics', value: 2 },
  ];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header - Bold and Clean */}
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
          Mission Control
        </Typography>
        <Typography 
          variant="h6" 
          sx={{ 
            color: '#E2E8F0',
            fontSize: { xs: '1rem', md: '1.125rem' },
            fontWeight: 500,
            maxWidth: '900px',
            lineHeight: 1.6,
          }}
        >
          Real-time infrastructure monitoring and system topology
        </Typography>
      </Box>

      {/* Quick Status Overview - Bold Cards */}
      <Grid container spacing={{ xs: 2, md: 3 }} sx={{ mb: { xs: 3, md: 4 } }}>
        <Grid item xs={6} sm={6} md={3}>
          <Card sx={{ 
            background: '#0A0A0F',
            border: '2px solid rgba(14, 165, 233, 0.4)',
            borderRadius: 2,
          }}>
            <CardContent sx={{ p: { xs: 2, md: 2.5 } }}>
              <Typography variant="body2" sx={{ color: '#CBD5E1', mb: 1.5, fontSize: { xs: '0.85rem', md: '0.95rem' }, fontWeight: 600 }}>
                Kubernetes
              </Typography>
              <Typography variant="h2" sx={{ fontWeight: 900, color: '#0EA5E9', fontSize: { xs: '2rem', md: '2.5rem' }, lineHeight: 1 }}>
                GKE
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={6} md={3}>
          <Card sx={{ 
            background: '#0A0A0F',
            border: '2px solid rgba(139, 92, 246, 0.4)',
            borderRadius: 2,
          }}>
            <CardContent sx={{ p: { xs: 2, md: 2.5 } }}>
              <Typography variant="body2" sx={{ color: '#CBD5E1', mb: 1.5, fontSize: { xs: '0.85rem', md: '0.95rem' }, fontWeight: 600 }}>
                Services
              </Typography>
              <Typography variant="h2" sx={{ fontWeight: 900, color: '#8B5CF6', fontSize: { xs: '2rem', md: '2.5rem' }, lineHeight: 1 }}>
                {agentActivities.length + 3}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={6} md={3}>
          <Card sx={{ 
            background: '#0A0A0F',
            border: '2px solid rgba(6, 182, 212, 0.4)',
            borderRadius: 2,
          }}>
            <CardContent sx={{ p: { xs: 2, md: 2.5 } }}>
              <Typography variant="body2" sx={{ color: '#CBD5E1', mb: 1.5, fontSize: { xs: '0.85rem', md: '0.95rem' }, fontWeight: 600 }}>
                AI Agents
              </Typography>
              <Typography variant="h2" sx={{ fontWeight: 900, color: '#06B6D4', fontSize: { xs: '2rem', md: '2.5rem' }, lineHeight: 1 }}>
                {agentActivities.filter(a => a.status !== 'idle').length}/{agentActivities.length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={6} sm={6} md={3}>
          <Card sx={{ 
            background: '#0A0A0F',
            border: '2px solid rgba(16, 185, 129, 0.4)',
            borderRadius: 2,
          }}>
            <CardContent sx={{ p: { xs: 2, md: 2.5 } }}>
              <Typography variant="body2" sx={{ color: '#CBD5E1', mb: 1.5, fontSize: { xs: '0.85rem', md: '0.95rem' }, fontWeight: 600 }}>
                Health
              </Typography>
              <Typography variant="h2" sx={{ fontWeight: 900, color: '#10B981', fontSize: { xs: '2rem', md: '2.5rem' }, lineHeight: 1 }}>
                98%
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs for different views */}
      <Tabs 
        value={activeTab} 
        onChange={(_, newValue) => setActiveTab(newValue)}
        sx={{ 
          mb: 4,
          borderBottom: 1,
          borderColor: 'divider',
          '& .MuiTab-root': {
            fontSize: '1.1rem',
            fontWeight: 600,
            minHeight: 56,
            textTransform: 'none',
          },
        }}
      >
        {tabs.map((tab) => (
          <Tab key={tab.value} label={tab.label} />
        ))}
      </Tabs>

      {/* Tab Content */}
      {activeTab === 0 && (
        <Box>
          <Typography 
            variant="h5" 
            sx={{ 
              fontWeight: 700, 
              mb: 3,
              fontSize: '1.5rem',
              color: 'text.primary',
            }}
          >
            Infrastructure Topology
          </Typography>
          <InfrastructureTopology />
        </Box>
      )}

      {activeTab === 1 && (
        <Box>
          <Typography 
            variant="h5" 
            sx={{ 
              fontWeight: 700, 
              mb: 3,
              fontSize: '1.5rem',
              color: 'text.primary',
            }}
          >
            Data Flow Architecture
          </Typography>
          <DataFlowDiagram />
        </Box>
      )}

      {activeTab === 2 && (
        <Box>
          <Typography 
            variant="h5" 
            sx={{ 
              fontWeight: 700, 
              mb: 3,
              fontSize: '1.5rem',
              color: 'text.primary',
            }}
          >
            System Performance Metrics
          </Typography>
          <SystemMetrics />
        </Box>
      )}

      {/* Regulatory Disclaimer */}
      <Box sx={{ mt: 6 }}>
        <RegulatoryDisclaimer />
      </Box>
    </Container>
  );
};

export default MissionControl;


import React from 'react';
import { Box, Card, Typography, Chip, LinearProgress } from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import GavelIcon from '@mui/icons-material/Gavel';

interface GrokArbitration {
  total_arbitrations: number;
  successful_overrides: number;
  average_confidence: number;
  conflicts_resolved: number;
  last_arbitration?: {
    timestamp: number;
    decision: string;
    confidence: number;
    agents_disagreed: string[];
  };
}

interface GrokArbitrationPanelProps {
  data: GrokArbitration;
}

export const GrokArbitrationPanel: React.FC<GrokArbitrationPanelProps> = ({ data }) => {
  const successRate = data.total_arbitrations > 0 
    ? (data.successful_overrides / data.total_arbitrations) * 100 
    : 0;

  return (
    <Card 
      sx={{ 
        p: 3,
        background: 'linear-gradient(135deg, rgba(255, 215, 0, 0.15) 0%, rgba(30, 34, 45, 0.98) 50%)',
        border: '2px solid rgba(255, 215, 0, 0.4)',
        borderRadius: 3,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Grok Badge */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <AutoAwesomeIcon sx={{ fontSize: 40, color: '#FFD700' }} />
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, color: '#FFD700' }}>
              Grok 4.1 Arbitrator
            </Typography>
            <Typography variant="caption" sx={{ color: '#9ca3af' }}>
              AI-Powered Conflict Resolution
            </Typography>
          </Box>
        </Box>
        
        <Chip 
          icon={<GavelIcon />}
          label={data.total_arbitrations > 0 ? "ACTIVE" : "STANDBY"}
          sx={{ 
            background: data.total_arbitrations > 0 ? 'rgba(255, 215, 0, 0.2)' : 'rgba(156, 163, 175, 0.2)',
            color: data.total_arbitrations > 0 ? '#FFD700' : '#9ca3af',
            fontWeight: 700,
            border: `1px solid ${data.total_arbitrations > 0 ? '#FFD700' : '#9ca3af'}`
          }}
        />
      </Box>

      {/* Stats Grid */}
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 2, mb: 3 }}>
        <Box sx={{ textAlign: 'center', p: 2, background: 'rgba(0, 0, 0, 0.3)', borderRadius: 2 }}>
          <Typography variant="h4" sx={{ fontWeight: 700, color: '#FFD700', fontFamily: 'monospace' }}>
            {data.total_arbitrations}
          </Typography>
          <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase' }}>
            Total Arbitrations
          </Typography>
        </Box>

        <Box sx={{ textAlign: 'center', p: 2, background: 'rgba(0, 0, 0, 0.3)', borderRadius: 2 }}>
          <Typography variant="h4" sx={{ fontWeight: 700, color: '#26a69a', fontFamily: 'monospace' }}>
            {data.successful_overrides}
          </Typography>
          <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase' }}>
            Overrides
          </Typography>
        </Box>

        <Box sx={{ textAlign: 'center', p: 2, background: 'rgba(0, 0, 0, 0.3)', borderRadius: 2 }}>
          <Typography variant="h4" sx={{ fontWeight: 700, color: '#2196F3', fontFamily: 'monospace' }}>
            {data.conflicts_resolved}
          </Typography>
          <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase' }}>
            Conflicts Resolved
          </Typography>
        </Box>

        <Box sx={{ textAlign: 'center', p: 2, background: 'rgba(0, 0, 0, 0.3)', borderRadius: 2 }}>
          <Typography variant="h4" sx={{ fontWeight: 700, color: '#9C27B0', fontFamily: 'monospace' }}>
            {(data.average_confidence * 100).toFixed(0)}%
          </Typography>
          <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase' }}>
            Avg Confidence
          </Typography>
        </Box>
      </Box>

      {/* Success Rate Progress */}
      <Box sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="body2" sx={{ color: '#d1d4dc', fontWeight: 600 }}>
            Override Success Rate
          </Typography>
          <Typography variant="body2" sx={{ color: '#FFD700', fontWeight: 700, fontFamily: 'monospace' }}>
            {successRate.toFixed(1)}%
          </Typography>
        </Box>
        <LinearProgress 
          variant="determinate" 
          value={successRate}
          sx={{
            height: 8,
            borderRadius: 4,
            background: 'rgba(255, 255, 255, 0.1)',
            '& .MuiLinearProgress-bar': {
              background: 'linear-gradient(90deg, #FFD700 0%, #FFA500 100%)',
              borderRadius: 4,
            }
          }}
        />
      </Box>

      {/* Last Arbitration */}
      {data.last_arbitration && (
        <Box sx={{ p: 2, background: 'rgba(0, 0, 0, 0.4)', borderRadius: 2, border: '1px solid rgba(255, 215, 0, 0.2)' }}>
          <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase', mb: 1, display: 'block' }}>
            Latest Arbitration
          </Typography>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="body1" sx={{ fontWeight: 700, color: '#FFD700' }}>
              {data.last_arbitration.decision}
            </Typography>
            <Chip 
              label={`${(data.last_arbitration.confidence * 100).toFixed(0)}% confidence`}
              size="small"
              sx={{ 
                background: 'rgba(255, 215, 0, 0.2)', 
                color: '#FFD700',
                fontFamily: 'monospace',
                fontWeight: 700
              }}
            />
          </Box>
          <Typography variant="caption" sx={{ color: '#6b7280' }}>
            Resolved disagreement between: {data.last_arbitration.agents_disagreed.join(', ')}
          </Typography>
          <Typography variant="caption" sx={{ color: '#9ca3af', display: 'block', mt: 0.5 }}>
            {new Date(data.last_arbitration.timestamp * 1000).toLocaleString()}
          </Typography>
        </Box>
      )}

      {/* Info Box */}
      <Box sx={{ mt: 3, p: 2, background: 'rgba(255, 215, 0, 0.05)', borderRadius: 2, border: '1px solid rgba(255, 215, 0, 0.2)' }}>
        <Typography variant="body2" sx={{ color: '#d1d4dc', lineHeight: 1.6 }}>
          <strong style={{ color: '#FFD700' }}>How it works:</strong> When AI agents disagree significantly (40%+ disagreement score), 
          Grok 4.1 analyzes all viewpoints and provides a definitive trading decision. This ensures the best collective intelligence 
          and prevents analysis paralysis.
        </Typography>
      </Box>
    </Card>
  );
};

export default GrokArbitrationPanel;


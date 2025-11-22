import React from 'react';
import { Box, Card, Typography, Chip } from '@mui/material';

export const SystemArchitecture: React.FC = () => {
  return (
    <Card sx={{ p: 4, background: 'rgba(30, 34, 45, 0.98)', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
      <Typography variant="h5" sx={{ fontWeight: 700, color: '#fff', mb: 4 }}>
        🏗️ System Architecture - Current Deployment
      </Typography>

      {/* Architecture Diagram */}
      <Box sx={{ fontFamily: 'monospace', fontSize: '13px', color: '#d1d4dc', mb: 4, p: 3, background: 'rgba(0, 0, 0, 0.3)', borderRadius: 2, overflow: 'auto' }}>
        <pre style={{ margin: 0 }}>{`
┌─────────────────────────────────────────────────────────────┐
│              Google Kubernetes Engine (GKE)                 │
│           Cluster: hft-trading-cluster                      │
│           Region: us-central1-a | 3 nodes                   │
└────────────────────────┬────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            │  Namespace: trading     │
            └────────────┬────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌────▼─────┐   ┌────▼────┐
    │ Trading │    │   Grok   │   │   MCP   │
    │ Engine  │───▶│   4.1    │◀──│  Coord  │
    │         │    │Arbitrator│   │         │
    └────┬────┘    └────┬─────┘   └────┬────┘
         │               │               │
         │         Resolves Conflicts    │
         │               │               │
    ┌────▼───────────────▼───────────────▼────┐
    │          6 AI Trading Agents             │
    ├──────────────────────────────────────────┤
    │ 📈 Trend       🧠 Strategy   💭 Sentiment│
    │ 🔮 Prediction  📊 Volume     ⚡ VPIN     │
    │                                          │
    │ Each: $100 capital | Independent trade  │
    └──────────┬───────────────────────────────┘
               │
    ┌──────────▼───────────────────────────────┐
    │          External Services                │
    ├──────────────────────────────────────────┤
    │ • Vertex AI (4 Gemini models)            │
    │ • Aster DEX (Futures trading)            │
    │ • Redis (Agent coordination)             │
    │ • PostgreSQL (Trade history)             │
    │ • BigQuery (Analytics)                   │
    │ • Telegram (Notifications)               │
    └──────────────────────────────────────────┘
`}</pre>
      </Box>

      {/* Key Features */}
      <Box>
        <Typography variant="h6" sx={{ fontWeight: 700, color: '#fff', mb: 2 }}>
          🎯 Key Features
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5 }}>
          <Chip label="✅ ServiceAccount Configured" sx={{ background: 'rgba(38, 166, 154, 0.2)', color: '#26a69a' }} />
          <Chip label="✅ Safe Nil Handling" sx={{ background: 'rgba(38, 166, 154, 0.2)', color: '#26a69a' }} />
          <Chip label="✅ $100 Per Bot" sx={{ background: 'rgba(33, 150, 243, 0.2)', color: '#2196F3' }} />
          <Chip label="✅ Grok 4.1 Arbitration" sx={{ background: 'rgba(255, 215, 0, 0.2)', color: '#FFD700' }} />
          <Chip label="✅ Real-Time WebSocket" sx={{ background: 'rgba(156, 39, 176, 0.2)', color: '#9C27B0' }} />
          <Chip label="✅ TradingView Charts" sx={{ background: 'rgba(255, 152, 0, 0.2)', color: '#FF9800' }} />
          <Chip label="✅ Smart Telegram" sx={{ background: 'rgba(76, 175, 80, 0.2)', color: '#4CAF50' }} />
          <Chip label="✅ Dual CI/CD" sx={{ background: 'rgba(244, 67, 54, 0.2)', color: '#F44336' }} />
        </Box>
      </Box>

      {/* Tech Stack */}
      <Box sx={{ mt: 4 }}>
        <Typography variant="h6" sx={{ fontWeight: 700, color: '#fff', mb: 2 }}>
          🛠️ Technology Stack
        </Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 2 }}>
          <Box sx={{ p: 2, background: 'rgba(0, 0, 0, 0.3)', borderRadius: 2 }}>
            <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase' }}>Backend</Typography>
            <Typography variant="body2" sx={{ color: '#fff', fontWeight: 600, mt: 0.5 }}>
              Python 3.11 + FastAPI
            </Typography>
          </Box>
          <Box sx={{ p: 2, background: 'rgba(0, 0, 0, 0.3)', borderRadius: 2 }}>
            <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase' }}>AI Models</Typography>
            <Typography variant="body2" sx={{ color: '#fff', fontWeight: 600, mt: 0.5 }}>
              Gemini 2.0 + Grok 4.1
            </Typography>
          </Box>
          <Box sx={{ p: 2, background: 'rgba(0, 0, 0, 0.3)', borderRadius: 2 }}>
            <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase' }}>Infrastructure</Typography>
            <Typography variant="body2" sx={{ color: '#fff', fontWeight: 600, mt: 0.5 }}>
              Kubernetes + Helm
            </Typography>
          </Box>
          <Box sx={{ p: 2, background: 'rgba(0, 0, 0, 0.3)', borderRadius: 2 }}>
            <Typography variant="caption" sx={{ color: '#9ca3af', textTransform: 'uppercase' }}>Frontend</Typography>
            <Typography variant="body2" sx={{ color: '#fff', fontWeight: 600, mt: 0.5 }}>
              React + TypeScript
            </Typography>
          </Box>
        </Box>
      </Box>
    </Card>
  );
};

export default SystemArchitecture;


import React, { useState, useEffect, useRef } from 'react';
import { Box, Typography, Grid, Container, Chip, Paper } from '@mui/material';
import { Zap, Activity, MessageSquare, Terminal } from 'lucide-react';
import AsterAgentGrid from '../components/AsterAgentGrid';
import HypeBrainStream from '../components/HypeBrainStream';
import TradingTerminal from '../components/TradingTerminal';
import LiveChatPanel from '../components/LiveChatPanel';
import { getApiUrl } from '../utils/apiConfig';

const MissionControl: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'agents' | 'terminal' | 'chat'>('agents');

  const handleUpdateTpSl = async (symbol: string, tp: number | null, sl: number | null) => {
    console.log(`Updating TP/SL for ${symbol}: ${tp}/${sl}`);
    try {
      const baseUrl = getApiUrl();

      await fetch(`${baseUrl}/positions/${symbol}/tpsl`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ tp, sl }),
      });
    } catch (e) {
      console.error('Failed to update TP/SL', e);
    }
  };

  const fetchMarketStats = async () => {
    try {
      const apiUrl = getApiUrl();
      const response = await fetch(`${apiUrl}/api/market-stats`);
      const data = await response.json();
      console.log('Market stats:', data);
    } catch (e) {
      console.error('Failed to fetch market stats', e);
    }
  };

  useEffect(() => {
    fetchMarketStats();
  }, []);

  return (
    <Box className="min-h-screen bg-slate-900 text-white p-6">
      <Container maxWidth="xl">
        <header className="flex justify-between items-center mb-8">
          <Box>
            <Typography variant="h4" className="font-bold bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">
              Mission Control
            </Typography>
            <Typography variant="subtitle2" className="text-slate-500 font-mono">
              System Ready // Status: ASTER_V1_ACTIVE
            </Typography>
          </Box>
          <Box className="flex space-x-2">
            {[
              { id: 'agents', label: 'Agents', icon: <Zap size={16} /> },
              { id: 'terminal', label: 'Terminal', icon: <Terminal size={16} /> },
              { id: 'chat', label: 'Social', icon: <MessageSquare size={16} /> },
            ].map((tab) => (
              <Chip
                key={tab.id}
                icon={tab.icon}
                label={tab.label}
                onClick={() => setActiveTab(tab.id as any)}
                className={`cursor-pointer transition-all ${activeTab === tab.id
                    ? 'bg-blue-600/30 text-blue-400 border border-blue-500/50'
                    : 'bg-slate-800 text-slate-500 border border-slate-700'
                  }`}
              />
            ))}
          </Box>
        </header>

        <Grid container spacing={3}>
          <Grid item xs={12} lg={8}>
            {activeTab === 'agents' && <AsterAgentGrid />}
            {activeTab === 'terminal' && <TradingTerminal onUpdateTpSl={handleUpdateTpSl} />}
            {activeTab === 'chat' && <LiveChatPanel />}
          </Grid>
          <Grid item xs={12} lg={4}>
            <Paper className="p-4 bg-slate-800/20 border border-slate-700 backdrop-blur-md rounded-xl">
              <Typography variant="h6" className="text-white font-bold mb-4 flex items-center gap-2">
                <Activity size={20} className="text-blue-400" /> Aster Brain Stream
              </Typography>
              <HypeBrainStream />
            </Paper>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
};

export default MissionControl;

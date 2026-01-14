import React from 'react';
import { Box, Paper, Typography, Grid, LinearProgress } from '@mui/material';
import { alpha } from '@mui/material/styles';

interface AgentStats {
    name: string;
    icon: string;
    winRate: number;
    ops: number; // Operations or Score
    status: 'active' | 'idle' | 'learning';
    color: string;
}

interface AsterAgentGridProps {
    agents: AgentStats[];
    onAgentClick: (agent: AgentStats) => void;
}

const AgentCard: React.FC<{ agent: AgentStats; onClick: () => void }> = ({ agent, onClick }) => (
    <Paper
        elevation={0}
        onClick={onClick}
        className={agent.status === 'active' ? 'agent-card-active' : ''}
        sx={{
            p: 2,
            bgcolor: '#0a0b10',
            border: `1px solid ${alpha(agent.color, 0.2)}`,
            borderRadius: 2,
            transition: 'all 0.2s',
            cursor: 'pointer', // Make it obvious
            '&:hover': {
                borderColor: agent.color,
                boxShadow: `0 0 15px ${alpha(agent.color, 0.15)}`,
                transform: 'translateY(-2px)',
            },
        }}
    >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Typography variant="h5">{agent.icon}</Typography>
                <Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#fff', fontSize: '0.9rem' }}>
                        {agent.name}
                    </Typography>
                    <Typography variant="caption" sx={{ color: alpha('#fff', 0.5) }}>
                        SYSTEM_ID: {agent.name.toUpperCase().substring(0, 3)}_01
                    </Typography>
                </Box>
            </Box>
            <Box
                sx={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    bgcolor: agent.status === 'active' ? '#00ff00' : '#ffa500',
                    boxShadow: `0 0 8px ${agent.status === 'active' ? '#00ff00' : '#ffa500'}`
                }}
            />
        </Box>

        <Box sx={{ mb: 1.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: '#aaa' }}>Win Rate</Typography>
                <Typography variant="caption" sx={{ color: agent.color, fontWeight: 700 }}>{agent.winRate}%</Typography>
            </Box>
            <LinearProgress
                variant="determinate"
                value={agent.winRate}
                sx={{
                    height: 4,
                    borderRadius: 2,
                    bgcolor: alpha('#fff', 0.05),
                    '& .MuiLinearProgress-bar': { bgcolor: agent.color }
                }}
            />
        </Box>

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="caption" sx={{ color: '#aaa' }}>OPS</Typography>
            <Typography variant="body2" sx={{ color: '#fff', fontFamily: 'Monospace' }}>{agent.ops}</Typography>
        </Box>
    </Paper>
);

const AsterAgentGrid: React.FC<AsterAgentGridProps> = ({ agents }) => {
    return (
        <Box>
            <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography variant="overline" sx={{ color: '#00d4aa', fontWeight: 700, letterSpacing: 1.2 }}>
                    ASTER SWARM // STATUS
                </Typography>
            </Box>
            <Grid container spacing={2}>
                {agents.map((agent, index) => (
                    <Grid item xs={12} md={6} lg={4} key={index}>
                        <AgentCard agent={agent} onClick={() => onAgentClick(agent)} />
                    </Grid>
                ))}
            </Grid>
        </Box>
    );
};

export default AsterAgentGrid;

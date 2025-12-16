import React from 'react';
import { Box, Grid, Paper, Typography, LinearProgress, Chip } from '@mui/material';
import { useTradingData, Agent } from '../../contexts/TradingContext';
import { TrendingUp, TrendingDown } from 'lucide-react';

const AgentCard: React.FC<{ agent: Agent; totalAllocation: number }> = ({ agent, totalAllocation }) => {
    // Format win rate as percentage (if stored as decimal, multiply by 100)
    const winRateValue = agent.win_rate > 1 ? agent.win_rate : agent.win_rate * 100;
    const pnlPercent = agent.pnl_percent > 1 ? agent.pnl_percent : agent.pnl_percent * 100;
    const allocationPercent = totalAllocation > 0 ? (agent.allocation / totalAllocation) * 100 : 0;
    const isProfitable = agent.pnl >= 0;

    return (
        <Paper
            sx={{
                p: 2.5,
                borderRadius: 2,
                background: 'linear-gradient(135deg, rgba(10,11,16,0.95), rgba(15,16,22,0.9))',
                border: `1px solid ${agent.status === 'active' ? 'rgba(0, 212, 170, 0.3)' : 'rgba(255,255,255,0.05)'}`,
                position: 'relative',
                overflow: 'hidden'
            }}
        >
            {/* Active Glow */}
            {agent.status === 'active' && (
                <Box sx={{
                    position: 'absolute', top: 0, left: 0, right: 0, height: 2,
                    background: 'linear-gradient(90deg, transparent, #00d4aa, transparent)',
                    opacity: 0.8
                }} />
            )}

            {/* Header */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
                    <Box sx={{
                        width: 42, height: 42,
                        borderRadius: 1.5,
                        bgcolor: 'rgba(255,255,255,0.05)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: '1.5rem'
                    }}>
                        {agent.emoji || '🤖'}
                    </Box>
                    <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#fff', lineHeight: 1.2 }}>
                            {agent.name}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#555', fontSize: '0.6rem' }}>
                            {agent.type || 'AI Agent'}
                        </Typography>
                    </Box>
                </Box>
                <Chip
                    label={agent.status === 'active' ? 'ACTIVE' : 'IDLE'}
                    size="small"
                    sx={{
                        height: 18,
                        fontSize: '0.55rem',
                        fontWeight: 700,
                        bgcolor: agent.status === 'active' ? 'rgba(0,212,170,0.15)' : 'rgba(255,255,255,0.05)',
                        color: agent.status === 'active' ? '#00d4aa' : '#555'
                    }}
                />
            </Box>

            {/* Performance Stats */}
            <Box sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 2,
                mb: 2,
                pt: 2,
                borderTop: '1px solid rgba(255,255,255,0.05)'
            }}>
                {/* Win Rate */}
                <Box>
                    <Typography variant="caption" sx={{ color: '#666', fontSize: '0.6rem', display: 'block', mb: 0.5 }}>
                        WIN RATE
                    </Typography>
                    <Typography sx={{
                        color: winRateValue >= 50 ? '#00d4aa' : '#ff6b6b',
                        fontWeight: 700,
                        fontFamily: 'JetBrains Mono',
                        fontSize: '1rem'
                    }}>
                        {winRateValue.toFixed(0)}%
                    </Typography>
                </Box>

                {/* P&L % */}
                <Box>
                    <Typography variant="caption" sx={{ color: '#666', fontSize: '0.6rem', display: 'block', mb: 0.5 }}>
                        RETURN
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        {isProfitable ? <TrendingUp size={12} color="#00d4aa" /> : <TrendingDown size={12} color="#ff6b6b" />}
                        <Typography sx={{
                            color: isProfitable ? '#00d4aa' : '#ff6b6b',
                            fontWeight: 700,
                            fontFamily: 'JetBrains Mono',
                            fontSize: '1rem'
                        }}>
                            {isProfitable ? '+' : ''}{pnlPercent.toFixed(1)}%
                        </Typography>
                    </Box>
                </Box>

                {/* Allocation % */}
                <Box>
                    <Typography variant="caption" sx={{ color: '#666', fontSize: '0.6rem', display: 'block', mb: 0.5 }}>
                        ALLOCATION
                    </Typography>
                    <Typography sx={{
                        color: '#fff',
                        fontWeight: 700,
                        fontFamily: 'JetBrains Mono',
                        fontSize: '1rem'
                    }}>
                        {allocationPercent.toFixed(0)}%
                    </Typography>
                </Box>
            </Box>

            {/* Trades Count */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="caption" sx={{ color: '#555', fontSize: '0.65rem' }}>
                    {agent.total_trades} trades executed
                </Typography>
                <Box sx={{
                    width: 60,
                    height: 4,
                    borderRadius: 2,
                    bgcolor: 'rgba(255,255,255,0.05)',
                    overflow: 'hidden'
                }}>
                    <Box sx={{
                        width: `${Math.min(winRateValue, 100)}%`,
                        height: '100%',
                        bgcolor: winRateValue >= 50 ? '#00d4aa' : '#ff6b6b',
                        borderRadius: 2
                    }} />
                </Box>
            </Box>
        </Paper>
    );
};

export const NewAsterAgentGrid: React.FC = () => {
    const { agents } = useTradingData();
    const asterAgents = agents.filter(a => !a.name.toLowerCase().includes('hype'));
    const totalAllocation = asterAgents.reduce((sum, a) => sum + (a.allocation || 0), 0);

    return (
        <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="overline" sx={{ color: '#00d4aa', fontWeight: 700, letterSpacing: 1.2 }}>
                    SWARM AGENTS
                </Typography>
                <Typography variant="caption" sx={{ color: '#555' }}>
                    {asterAgents.filter(a => a.status === 'active').length} active
                </Typography>
            </Box>
            <Grid container spacing={2}>
                {asterAgents.length === 0 ? (
                    <Grid item xs={12}>
                        <Paper sx={{ p: 3, textAlign: 'center', bgcolor: 'rgba(255,255,255,0.02)' }}>
                            <Typography variant="body2" sx={{ color: '#666' }}>Initializing agents...</Typography>
                        </Paper>
                    </Grid>
                ) : (
                    asterAgents.map(agent => (
                        <Grid item xs={12} md={6} key={agent.id}>
                            <AgentCard agent={agent} totalAllocation={totalAllocation} />
                        </Grid>
                    ))
                )}
            </Grid>
        </Box>
    );
};

export default NewAsterAgentGrid;

import React from 'react';
import { Box, Grid, Paper, Typography, Chip } from '@mui/material';
import { useTradingData } from '../contexts/TradingContext';

// Reusing Bento Card concept for consistency (Should be a shared component in real refactor)
const BentoCard: React.FC<{ children: React.ReactNode, title?: string, colSpan?: number, rowSpan?: number, height?: number | string }> = ({ children, title, colSpan = 1, rowSpan = 1, height }) => (
    <Grid item xs={12} md={colSpan * 4} lg={colSpan * 3}>
        <Paper
            elevation={0}
            sx={{
                height: height || '100%',
                minHeight: 200,
                p: 3,
                bgcolor: 'rgba(15, 16, 22, 0.6)',
                backdropFilter: 'blur(12px)',
                border: '1px solid rgba(255,255,255,0.05)',
                borderRadius: 4,
                display: 'flex',
                flexDirection: 'column',
                position: 'relative',
                overflow: 'hidden'
            }}
        >
            {title && (
                <Typography variant="overline" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: 1.2, mb: 2 }}>
                    {title}
                </Typography>
            )}
            <Box sx={{ flex: 1, position: 'relative' }}>
                {children}
            </Box>
        </Paper>
    </Grid>
);

export const AgentLab: React.FC = () => {
    const { agents } = useTradingData();

    return (
        <Box>
            <Box sx={{ mb: 6 }}>
                <Typography variant="h3" sx={{ fontWeight: 800, letterSpacing: -1, background: 'linear-gradient(to right, #fff, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                    Agent Laboratory
                </Typography>
                <Typography variant="body1" sx={{ color: '#64748b', maxWidth: 600, mt: 1 }}>
                    Technical diagnostics, memory states, and decision vectors for the Aster Swarm.
                </Typography>
            </Box>

            <Grid container spacing={3}>
                {agents.map((agent) => (
                    <BentoCard key={agent.id} title={agent.name.toUpperCase()} colSpan={1} height={250}>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <Chip
                                    label={agent.status}
                                    size="small"
                                    sx={{
                                        bgcolor: agent.status === 'active' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(255,255,255,0.05)',
                                        color: agent.status === 'active' ? '#10b981' : '#64748b',
                                        fontWeight: 700
                                    }}
                                />
                                <Typography variant="caption" sx={{ color: '#64748b', fontFamily: 'JetBrains Mono' }}>ID: {agent.id.slice(0, 8)}</Typography>
                            </Box>

                            <Box>
                                <Typography variant="caption" sx={{ color: '#64748b' }}>CONFIDENCE</Typography>
                                <Box sx={{ width: '100%', height: 6, bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 1, mt: 0.5, overflow: 'hidden' }}>
                                    <Box sx={{ width: '87%', height: '100%', bgcolor: '#3b82f6' }} />
                                </Box>
                            </Box>

                            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mt: 1 }}>
                                <Box>
                                    <Typography variant="caption" sx={{ color: '#64748b' }}>LAST CYCLE</Typography>
                                    <Typography variant="body2" sx={{ color: '#fff', fontFamily: 'JetBrains Mono' }}>12ms</Typography>
                                </Box>
                                <Box>
                                    <Typography variant="caption" sx={{ color: '#64748b' }}>MEMORY USAGE</Typography>
                                    <Typography variant="body2" sx={{ color: '#fff', fontFamily: 'JetBrains Mono' }}>24MB</Typography>
                                </Box>
                            </Box>
                        </Box>
                    </BentoCard>
                ))}
            </Grid>
        </Box>
    );
};

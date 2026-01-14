import React from 'react';
import { Box, Dialog, DialogContent, Typography, IconButton, Grid, Chip, Paper } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import TerminalIcon from '@mui/icons-material/Terminal';

interface AgentDetailModalProps {
    open: boolean;
    onClose: () => void;
    agent: any;
    logs: any[];
}

const AgentDetailModal: React.FC<AgentDetailModalProps> = ({ open, onClose, agent, logs }) => {
    if (!agent) return null;

    // Filter logs for this agent
    const agentLogs = logs.filter(
        l => (l.agentName && l.agentName.includes(agent.name)) ||
            (l.agentId && l.agentId === agent.id) ||
            (agent.name === 'Hype Bull Agent' && l.agent === 'Hype Bull') // Fallback for specific knowns
    ).slice(0, 50); // Limit to recent

    return (
        <Dialog
            open={open}
            onClose={onClose}
            maxWidth="md"
            fullWidth
            PaperProps={{
                sx: {
                    bgcolor: '#0a0b10',
                    border: '1px solid #333',
                    backgroundImage: 'none',
                    boxShadow: '0 0 40px rgba(0,0,0,0.8)'
                }
            }}
        >
            <Box sx={{ p: 2, borderBottom: '1px solid #222', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Typography variant="h5" sx={{ fontSize: '1.5rem' }}>{agent.icon}</Typography>
                    <Box>
                        <Typography variant="h6" sx={{ color: '#fff', fontWeight: 700 }}>
                            {agent.name.toUpperCase()}
                        </Typography>
                        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                            <Chip
                                label={agent.status.toUpperCase()}
                                size="small"
                                sx={{
                                    height: 20,
                                    fontSize: '0.7rem',
                                    bgcolor: agent.status === 'active' ? 'rgba(0, 255, 0, 0.1)' : 'rgba(255, 165, 0, 0.1)',
                                    color: agent.status === 'active' ? '#00ff00' : '#ffa500',
                                    border: `1px solid ${agent.status === 'active' ? '#00ff00' : '#ffa500'}`
                                }}
                            />
                            {agent.system && (
                                <Chip
                                    label={agent.system.toUpperCase()}
                                    size="small"
                                    sx={{
                                        height: 20,
                                        fontSize: '0.7rem',
                                        bgcolor: agent.system === 'hyperliquid' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(59, 130, 246, 0.1)',
                                        color: agent.system === 'hyperliquid' ? '#10b981' : '#3b82f6',
                                        border: `1px solid ${agent.system === 'hyperliquid' ? '#10b981' : '#3b82f6'}`
                                    }}
                                />
                            )}
                            <Typography variant="caption" sx={{ color: '#666', fontFamily: 'Monospace' }}>
                                ID: {agent.name.substring(0, 3).toUpperCase()}_001
                            </Typography>
                        </Box>
                    </Box>
                </Box>
                <IconButton onClick={onClose} sx={{ color: '#666' }}>
                    <CloseIcon />
                </IconButton>
            </Box>

            <DialogContent sx={{ p: 3 }}>
                <Grid container spacing={3}>
                    {/* Stats Column */}
                    <Grid item xs={12} md={4}>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <Paper sx={{ p: 2, bgcolor: '#111', border: '1px solid #222' }}>
                                <Typography variant="caption" sx={{ color: '#888' }}>WIN RATE</Typography>
                                <Typography variant="h4" sx={{ color: agent.color, fontWeight: 700 }}>{agent.winRate}%</Typography>
                            </Paper>
                            <Paper sx={{ p: 2, bgcolor: '#111', border: '1px solid #222' }}>
                                <Typography variant="caption" sx={{ color: '#888' }}>TOTAL OPS</Typography>
                                <Typography variant="h4" sx={{ color: '#fff', fontWeight: 700 }}>{agent.ops}</Typography>
                            </Paper>
                            <Paper sx={{ p: 2, bgcolor: '#111', border: '1px solid #222' }}>
                                <Typography variant="caption" sx={{ color: '#888' }}>LAST ACTIVE</Typography>
                                <Typography variant="body1" sx={{ color: '#fff' }}>Just now</Typography>
                            </Paper>
                        </Box>
                    </Grid>

                    {/* Neural Stream Column */}
                    <Grid item xs={12} md={8}>
                        <Box sx={{
                            height: 400,
                            bgcolor: '#000',
                            border: '1px solid #333',
                            borderRadius: 1,
                            fontFamily: 'JetBrains Mono',
                            fontSize: '0.8rem',
                            display: 'flex',
                            flexDirection: 'column'
                        }}>
                            <Box sx={{ p: 1, borderBottom: '1px solid #222', bgcolor: '#0a0b10', display: 'flex', alignItems: 'center', gap: 1 }}>
                                <TerminalIcon sx={{ fontSize: 16, color: '#666' }} />
                                <Typography variant="caption" sx={{ color: '#666' }}>NEURAL_LOG_STREAM // {agent.name.toUpperCase()}</Typography>
                            </Box>
                            <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
                                {agentLogs.length === 0 ? (
                                    <Typography variant="caption" sx={{ color: '#444' }}>No active observations...</Typography>
                                ) : (
                                    agentLogs.map((log, i) => (
                                        <Box key={i} sx={{ mb: 1.5, display: 'flex', gap: 1.5, opacity: i === 0 ? 1 : 0.7 }}>
                                            <Typography variant="caption" sx={{ color: '#444', minWidth: 60 }}>
                                                {new Date(log.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                            </Typography>
                                            <Box>
                                                <Typography variant="body2" sx={{ color: log.role === 'BUY' ? '#00ff00' : log.role === 'SELL' ? '#ff0000' : '#ccc' }}>
                                                    <span style={{ color: '#666', marginRight: 8 }}>[{log.role}]</span>
                                                    {log.content || log.message}
                                                </Typography>
                                            </Box>
                                        </Box>
                                    ))
                                )}
                            </Box>
                        </Box>
                    </Grid>
                </Grid>
            </DialogContent>
        </Dialog>
    );
};

export default AgentDetailModal;

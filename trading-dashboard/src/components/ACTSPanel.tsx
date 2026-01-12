import { useState, useEffect } from 'react';
import { Box, Typography, Chip, LinearProgress, Paper, Grid, Tooltip } from '@mui/material';
import { Psychology, Memory, Visibility, Gavel, Bolt, CloudQueue } from '@mui/icons-material';

// Types for ACTS data
interface ACTSAgent {
    id: string;
    role: string;
    capabilities: string[];
    message_count: number;
    last_message: string | null;
    last_confidence: number | null;
}

interface ACTSStatus {
    status: 'active' | 'inactive' | 'offline';
    mesh: {
        agents_registered: number;
        messages_logged: number;
    };
    memory: {
        total_episodes: number;
        total_trades: number;
        total_pnl: number;
    };
    timestamp: string;
}

interface TemporalInsights {
    best_hour: number | null;
    best_hour_pnl: number;
    worst_hour: number | null;
    worst_hour_pnl: number;
    best_day: string | null;
    best_day_pnl: number;
}

interface Episode {
    id: string;
    name: string;
    regime: string;
    duration_hours: number;
    pnl: number;
    win_rate: number;
    trade_count: number;
    lesson_tactical: string | null;
    lesson_strategic: string | null;
}

interface MemoryInsights {
    stats: {
        total_episodes: number;
        total_trades: number;
        total_pnl: number;
        regime_distribution: Record<string, number>;
    };
    temporal_insights: TemporalInsights;
    recent_episodes: Episode[];
}

// Role to icon mapping
const roleIcon = (role: string) => {
    switch (role.toLowerCase()) {
        case 'scout': return <Visibility fontSize="small" />;
        case 'sniper': return <Gavel fontSize="small" />;
        case 'oracle': return <Psychology fontSize="small" />;
        case 'executor': return <Bolt fontSize="small" />;
        default: return <CloudQueue fontSize="small" />;
    }
};

// Role to color mapping
const roleColor = (role: string): 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'info' => {
    switch (role.toLowerCase()) {
        case 'scout': return 'info';
        case 'sniper': return 'warning';
        case 'oracle': return 'secondary';
        case 'executor': return 'success';
        default: return 'primary';
    }
};

// Format confidence as percentage
const formatConfidence = (conf: number | null) => {
    if (conf === null) return '-';
    return `${(conf * 100).toFixed(0)}%`;
};

// Main ACTS Panel Component
export const ACTSPanel: React.FC = () => {
    const [status, setStatus] = useState<ACTSStatus | null>(null);
    const [agents, setAgents] = useState<ACTSAgent[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchACTSData = async () => {
            try {
                const baseUrl = import.meta.env.VITE_API_URL || '';

                const [statusRes, agentsRes] = await Promise.all([
                    fetch(`${baseUrl}/api/acts/status`),
                    fetch(`${baseUrl}/api/acts/agents`),
                ]);

                if (statusRes.ok) {
                    setStatus(await statusRes.json());
                }

                if (agentsRes.ok) {
                    const data = await agentsRes.json();
                    setAgents(data.agents || []);
                }

                setLoading(false);
            } catch (e) {
                setError('Failed to fetch ACTS data');
                setLoading(false);
            }
        };

        fetchACTSData();
        const interval = setInterval(fetchACTSData, 10000); // Refresh every 10s

        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <Paper sx={{ p: 2, background: 'rgba(0, 255, 159, 0.05)', borderRadius: 2 }}>
                <Typography variant="subtitle2" color="text.secondary">
                    Loading ACTS...
                </Typography>
                <LinearProgress color="secondary" sx={{ mt: 1 }} />
            </Paper>
        );
    }

    if (error) {
        return (
            <Paper sx={{ p: 2, background: 'rgba(255, 0, 0, 0.1)', borderRadius: 2 }}>
                <Typography variant="subtitle2" color="error">
                    {error}
                </Typography>
            </Paper>
        );
    }

    return (
        <Paper
            sx={{
                p: 2,
                background: 'linear-gradient(135deg, rgba(0, 255, 159, 0.08) 0%, rgba(0, 200, 255, 0.05) 100%)',
                borderRadius: 2,
                border: '1px solid rgba(0, 255, 159, 0.2)',
            }}
        >
            {/* Header */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <Psychology sx={{ color: '#00ff9f' }} />
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#00ff9f' }}>
                    Cognitive Swarm (ACTS)
                </Typography>
                <Chip
                    label={status?.status || 'unknown'}
                    size="small"
                    color={status?.status === 'active' ? 'success' : 'error'}
                    sx={{ ml: 'auto' }}
                />
            </Box>

            {/* Stats Row */}
            <Grid container spacing={2} sx={{ mb: 2 }}>
                <Grid item xs={4}>
                    <Box sx={{ textAlign: 'center' }}>
                        <Typography variant="h4" sx={{ color: '#00ff9f', fontWeight: 700 }}>
                            {status?.mesh.agents_registered || 0}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                            Agents Online
                        </Typography>
                    </Box>
                </Grid>
                <Grid item xs={4}>
                    <Box sx={{ textAlign: 'center' }}>
                        <Typography variant="h4" sx={{ color: '#00c8ff', fontWeight: 700 }}>
                            {status?.mesh.messages_logged || 0}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                            Messages
                        </Typography>
                    </Box>
                </Grid>
                <Grid item xs={4}>
                    <Box sx={{ textAlign: 'center' }}>
                        <Typography variant="h4" sx={{ color: '#ffcc00', fontWeight: 700 }}>
                            {status?.memory.total_episodes || 0}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                            Episodes
                        </Typography>
                    </Box>
                </Grid>
            </Grid>

            {/* Agent List */}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
                Active Agents
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {agents.map((agent) => (
                    <Tooltip
                        key={agent.id}
                        title={agent.last_message || 'No recent activity'}
                        arrow
                    >
                        <Chip
                            icon={roleIcon(agent.role)}
                            label={`${agent.id} (${formatConfidence(agent.last_confidence)})`}
                            size="small"
                            color={roleColor(agent.role)}
                            variant="outlined"
                            sx={{
                                borderRadius: 1,
                                '& .MuiChip-label': { fontSize: '0.75rem' },
                            }}
                        />
                    </Tooltip>
                ))}
                {agents.length === 0 && (
                    <Typography variant="body2" color="text.secondary">
                        No agents active
                    </Typography>
                )}
            </Box>
        </Paper>
    );
};

// Memory Insights Panel
export const MemoryInsightsPanel: React.FC = () => {
    const [memory, setMemory] = useState<MemoryInsights | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchMemory = async () => {
            try {
                const baseUrl = import.meta.env.VITE_API_URL || '';
                const res = await fetch(`${baseUrl}/api/acts/memory`);
                if (res.ok) {
                    setMemory(await res.json());
                }
                setLoading(false);
            } catch {
                setLoading(false);
            }
        };

        fetchMemory();
    }, []);

    if (loading || !memory) {
        return null;
    }

    const { temporal_insights: temporal, recent_episodes: episodes } = memory;

    return (
        <Paper
            sx={{
                p: 2,
                background: 'linear-gradient(135deg, rgba(255, 200, 0, 0.08) 0%, rgba(255, 100, 100, 0.05) 100%)',
                borderRadius: 2,
                border: '1px solid rgba(255, 200, 0, 0.2)',
            }}
        >
            {/* Header */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <Memory sx={{ color: '#ffcc00' }} />
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#ffcc00' }}>
                    Memory Insights
                </Typography>
            </Box>

            {/* Temporal Insights */}
            {temporal && (
                <Box sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
                        Best/Worst Times
                    </Typography>
                    <Grid container spacing={1}>
                        {temporal.best_hour !== null && (
                            <Grid item xs={6}>
                                <Chip
                                    label={`Best: ${temporal.best_hour}:00 UTC (+$${temporal.best_hour_pnl.toFixed(0)})`}
                                    size="small"
                                    color="success"
                                    variant="filled"
                                    sx={{ width: '100%' }}
                                />
                            </Grid>
                        )}
                        {temporal.worst_hour !== null && (
                            <Grid item xs={6}>
                                <Chip
                                    label={`Worst: ${temporal.worst_hour}:00 UTC ($${temporal.worst_hour_pnl.toFixed(0)})`}
                                    size="small"
                                    color="error"
                                    variant="filled"
                                    sx={{ width: '100%' }}
                                />
                            </Grid>
                        )}
                    </Grid>
                </Box>
            )}

            {/* Recent Episodes */}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
                Recent Episodes
            </Typography>
            <Box sx={{ maxHeight: 200, overflow: 'auto' }}>
                {episodes.slice(0, 3).map((ep) => (
                    <Box
                        key={ep.id}
                        sx={{
                            p: 1,
                            mb: 1,
                            borderRadius: 1,
                            background: 'rgba(255, 255, 255, 0.05)',
                        }}
                    >
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {ep.name}
                            </Typography>
                            <Chip
                                label={ep.regime}
                                size="small"
                                sx={{ fontSize: '0.65rem', height: 18 }}
                            />
                        </Box>
                        <Typography
                            variant="body2"
                            sx={{
                                color: ep.pnl >= 0 ? '#00ff9f' : '#ff4444',
                                fontWeight: 600,
                            }}
                        >
                            ${ep.pnl.toFixed(2)} ({(ep.win_rate * 100).toFixed(0)}% WR)
                        </Typography>
                        {ep.lesson_tactical && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                                📌 {ep.lesson_tactical}
                            </Typography>
                        )}
                    </Box>
                ))}
                {episodes.length === 0 && (
                    <Typography variant="body2" color="text.secondary">
                        No episodes yet
                    </Typography>
                )}
            </Box>
        </Paper>
    );
};

// Symbol Reasoning Panel (for detail views)
interface SymbolReasoningProps {
    symbol: string;
}

export const SymbolReasoningPanel: React.FC<SymbolReasoningProps> = ({ symbol }) => {
    const [reasoning, setReasoning] = useState<{
        reasoning: Array<{
            agent: string;
            role: string;
            reasoning: string;
            action: string;
            confidence: number;
        }>;
        memory_advice: string;
    } | null>(null);

    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchReasoning = async () => {
            try {
                const baseUrl = import.meta.env.VITE_API_URL || '';
                const res = await fetch(`${baseUrl}/api/acts/reasoning/${symbol}`);
                if (res.ok) {
                    setReasoning(await res.json());
                }
                setLoading(false);
            } catch {
                setLoading(false);
            }
        };

        fetchReasoning();
    }, [symbol]);

    if (loading) return <LinearProgress />;
    if (!reasoning) return null;

    return (
        <Paper sx={{ p: 2, borderRadius: 2, background: 'rgba(100, 100, 255, 0.05)' }}>
            <Typography variant="h6" sx={{ mb: 2, color: '#00c8ff' }}>
                🧠 AI Reasoning for {symbol}
            </Typography>

            {/* Agent Reasoning */}
            {reasoning.reasoning.map((r, i) => (
                <Box
                    key={i}
                    sx={{
                        p: 1.5,
                        mb: 1,
                        borderRadius: 1,
                        background: 'rgba(255, 255, 255, 0.03)',
                        borderLeft: `3px solid ${r.action === 'BUY' ? '#00ff9f' : r.action === 'SELL' ? '#ff4444' : '#888'}`,
                    }}
                >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                        {roleIcon(r.role)}
                        <Typography variant="subtitle2">
                            {r.agent}
                        </Typography>
                        <Chip
                            label={r.action}
                            size="small"
                            color={r.action === 'BUY' ? 'success' : r.action === 'SELL' ? 'error' : 'default'}
                            sx={{ ml: 'auto' }}
                        />
                        <Typography variant="caption" color="text.secondary">
                            {formatConfidence(r.confidence)}
                        </Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                        {r.reasoning.slice(0, 200)}...
                    </Typography>
                </Box>
            ))}

            {/* Memory Advice */}
            {reasoning.memory_advice && (
                <Box sx={{ mt: 2, p: 1.5, background: 'rgba(255, 200, 0, 0.1)', borderRadius: 1 }}>
                    <Typography variant="subtitle2" sx={{ color: '#ffcc00', mb: 0.5 }}>
                        📚 Memory Says:
                    </Typography>
                    <Typography variant="body2">
                        {reasoning.memory_advice}
                    </Typography>
                </Box>
            )}
        </Paper>
    );
};

export default ACTSPanel;

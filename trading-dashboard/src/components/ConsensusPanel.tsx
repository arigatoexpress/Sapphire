import React, { useEffect, useState } from 'react';
import { Box, Paper, Typography, LinearProgress, Chip } from '@mui/material';
import { Brain, Target, Users, Zap } from 'lucide-react';
import { getApiUrl } from '../utils/apiConfig';

interface ConsensusData {
    stats: {
        total_consensus_events: number;
        success_rate: number;
        avg_confidence: number;
        avg_agreement: number;
        active_agents: number;
        signal_distribution: {
            entry_long?: number;
            entry_short?: number;
        };
    };
}

const API_BASE = getApiUrl();

export const ConsensusPanel: React.FC = () => {
    const [data, setData] = useState<ConsensusData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchConsensus = async () => {
            try {
                const res = await fetch(`${API_BASE}/consensus/state`);
                if (res.ok) {
                    const json = await res.json();
                    setData(json);
                }
            } catch (e) {
                console.error('Failed to fetch consensus:', e);
            } finally {
                setLoading(false);
            }
        };

        fetchConsensus();
        const interval = setInterval(fetchConsensus, 10000); // Poll every 10s
        return () => clearInterval(interval);
    }, []);

    if (loading || !data || !data.stats) {
        return (
            <Paper sx={{
                p: 3,
                borderRadius: 2,
                background: 'linear-gradient(135deg, rgba(10,11,16,0.95), rgba(15,16,22,0.9))',
                border: '1px solid rgba(255,255,255,0.06)',
            }}>
                <Typography sx={{ color: '#666' }}>Loading consensus...</Typography>
            </Paper>
        );
    }

    const { stats } = data;
    const confPercent = (stats.avg_confidence || 0) * 100;
    const agreePercent = (stats.avg_agreement || 0) * 100;
    const longCount = stats.signal_distribution?.entry_long || 0;
    const shortCount = stats.signal_distribution?.entry_short || 0;
    const totalSignals = longCount + shortCount;
    const longPercent = totalSignals > 0 ? (longCount / totalSignals) * 100 : 50;

    return (
        <Paper sx={{
            p: 3,
            borderRadius: 2,
            background: 'linear-gradient(135deg, rgba(10,11,16,0.95), rgba(15,16,22,0.9))',
            border: '1px solid rgba(0,212,170,0.15)',
            position: 'relative',
            overflow: 'hidden'
        }}>
            {/* Glow effect */}
            <Box sx={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: 2,
                background: 'linear-gradient(90deg, transparent, #00d4aa, transparent)',
                opacity: 0.6
            }} />

            {/* Header */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
                <Box sx={{
                    p: 1,
                    borderRadius: 1.5,
                    background: 'rgba(0,212,170,0.1)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                }}>
                    <Brain size={20} color="#00d4aa" />
                </Box>
                <Box>
                    <Typography variant="overline" sx={{ color: '#00d4aa', fontWeight: 700, letterSpacing: 1.2 }}>
                        SWARM CONSENSUS ENGINE
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#666', display: 'block' }}>
                        {stats.total_consensus_events} votes • {stats.active_agents} agents
                    </Typography>
                </Box>
                <Chip
                    label={`${(stats.success_rate * 100).toFixed(0)}% SUCCESS`}
                    size="small"
                    sx={{
                        ml: 'auto',
                        bgcolor: 'rgba(0,212,170,0.15)',
                        color: '#00d4aa',
                        fontWeight: 700,
                        fontSize: '0.65rem'
                    }}
                />
            </Box>

            {/* Confidence Meter */}
            <Box sx={{ mb: 2.5 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="caption" sx={{ color: '#888' }}>
                        <Target size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                        Avg Confidence
                    </Typography>
                    <Typography variant="caption" sx={{
                        color: confPercent >= 80 ? '#00d4aa' : confPercent >= 70 ? '#ffc107' : '#ff6b6b',
                        fontWeight: 700,
                        fontFamily: 'JetBrains Mono, monospace'
                    }}>
                        {confPercent.toFixed(0)}%
                    </Typography>
                </Box>
                <LinearProgress
                    variant="determinate"
                    value={confPercent}
                    sx={{
                        height: 6,
                        borderRadius: 1,
                        bgcolor: 'rgba(255,255,255,0.05)',
                        '& .MuiLinearProgress-bar': {
                            bgcolor: confPercent >= 80 ? '#00d4aa' : confPercent >= 70 ? '#ffc107' : '#ff6b6b',
                            borderRadius: 1
                        }
                    }}
                />
                <Typography variant="caption" sx={{ color: '#555', fontSize: '0.6rem' }}>
                    Threshold: 80% for trade execution
                </Typography>
            </Box>

            {/* Agreement Meter */}
            <Box sx={{ mb: 2.5 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="caption" sx={{ color: '#888' }}>
                        <Users size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                        Agent Agreement
                    </Typography>
                    <Typography variant="caption" sx={{
                        color: agreePercent >= 90 ? '#00d4aa' : '#ffc107',
                        fontWeight: 700,
                        fontFamily: 'JetBrains Mono, monospace'
                    }}>
                        {agreePercent.toFixed(0)}%
                    </Typography>
                </Box>
                <LinearProgress
                    variant="determinate"
                    value={agreePercent}
                    sx={{
                        height: 6,
                        borderRadius: 1,
                        bgcolor: 'rgba(255,255,255,0.05)',
                        '& .MuiLinearProgress-bar': {
                            bgcolor: '#00d4aa',
                            borderRadius: 1
                        }
                    }}
                />
            </Box>

            {/* Signal Distribution */}
            <Box sx={{ mt: 3 }}>
                <Typography variant="caption" sx={{ color: '#888', mb: 1, display: 'block' }}>
                    <Zap size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                    Signal Distribution
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, height: 28 }}>
                    <Box sx={{
                        flex: longPercent,
                        background: 'linear-gradient(90deg, #00d4aa, #00b894)',
                        borderRadius: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        minWidth: 50,
                        transition: 'flex 0.5s ease'
                    }}>
                        <Typography sx={{ fontSize: '0.65rem', fontWeight: 700, color: '#000' }}>
                            LONG {longCount}
                        </Typography>
                    </Box>
                    <Box sx={{
                        flex: 100 - longPercent,
                        background: 'linear-gradient(90deg, #ff6b6b, #ee5a5a)',
                        borderRadius: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        minWidth: 50,
                        transition: 'flex 0.5s ease'
                    }}>
                        <Typography sx={{ fontSize: '0.65rem', fontWeight: 700, color: '#fff' }}>
                            SHORT {shortCount}
                        </Typography>
                    </Box>
                </Box>
            </Box>
        </Paper>
    );
};

export default ConsensusPanel;

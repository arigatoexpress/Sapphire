import React, { useEffect, useState, useRef } from 'react';
import { Box, Typography, Chip } from '@mui/material';
import { Brain, Zap, TrendingUp, TrendingDown, Users, Target } from 'lucide-react';

interface ConsensusStats {
    total_consensus_events: number;
    success_rate: number;
    avg_confidence: number;
    avg_agreement: number;
    signal_distribution: {
        entry_long?: number;
        entry_short?: number;
    };
    agent_performance: Record<string, {
        win_rate: number;
        total_trades: number;
        current_weight: number;
    }>;
    active_agents: number;
}

interface ActivityItem {
    id: string;
    timestamp: Date;
    type: 'consensus' | 'signal' | 'agent' | 'system';
    content: string;
    icon: React.ReactNode;
    color: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'https://cloud-trader-267358751314.northamerica-northeast1.run.app';

export const NewAsterBrainStream: React.FC = () => {
    const [activities, setActivities] = useState<ActivityItem[]>([]);
    const [stats, setStats] = useState<ConsensusStats | null>(null);
    const [lastEventCount, setLastEventCount] = useState(0);
    const bottomRef = useRef<HTMLDivElement>(null);

    // Generate activity items from consensus data
    const generateActivities = (newStats: ConsensusStats, prevEventCount: number): ActivityItem[] => {
        const items: ActivityItem[] = [];
        const now = new Date();

        // New consensus events detected
        const newEvents = newStats.total_consensus_events - prevEventCount;
        if (newEvents > 0 && prevEventCount > 0) {
            items.push({
                id: `consensus-${now.getTime()}`,
                timestamp: now,
                type: 'consensus',
                content: `${newEvents} new consensus vote${newEvents > 1 ? 's' : ''} completed • ${(newStats.avg_confidence * 100).toFixed(0)}% avg confidence`,
                icon: <Brain size={12} />,
                color: '#00d4aa'
            });
        }

        // Signal distribution insight
        const longPct = newStats.signal_distribution.entry_long || 0;
        const shortPct = newStats.signal_distribution.entry_short || 0;
        const total = longPct + shortPct;
        if (total > 0) {
            const bias = longPct > shortPct ? 'LONG' : 'SHORT';
            const biasPercent = Math.round((Math.max(longPct, shortPct) / total) * 100);
            if (Math.random() < 0.3) { // Show occasionally
                items.push({
                    id: `signal-${now.getTime()}`,
                    timestamp: new Date(now.getTime() - 1000),
                    type: 'signal',
                    content: `Market bias: ${bias} (${biasPercent}%) • ${total} signals analyzed`,
                    icon: bias === 'LONG' ? <TrendingUp size={12} /> : <TrendingDown size={12} />,
                    color: bias === 'LONG' ? '#00ff00' : '#ff6b6b'
                });
            }
        }

        // Agent activity
        const agents = Object.entries(newStats.agent_performance);
        if (agents.length > 0 && Math.random() < 0.2) {
            const [agentName, perf] = agents[Math.floor(Math.random() * agents.length)];
            const friendlyName = agentName.replace(/-/g, ' ').replace('agent', '').trim();
            items.push({
                id: `agent-${now.getTime()}`,
                timestamp: new Date(now.getTime() - 2000),
                type: 'agent',
                content: `${friendlyName} analyzing market • Weight: ${perf.current_weight.toFixed(1)}`,
                icon: <Users size={12} />,
                color: '#8a2be2'
            });
        }

        return items;
    };

    useEffect(() => {
        const fetchConsensus = async () => {
            try {
                const res = await fetch(`${API_BASE}/consensus/state`);
                if (res.ok) {
                    const data = await res.json();
                    const newStats = data.stats as ConsensusStats;

                    // Generate new activities based on changes
                    const newActivities = generateActivities(newStats, lastEventCount);

                    if (newActivities.length > 0) {
                        setActivities(prev => [...newActivities, ...prev].slice(0, 50));
                    }

                    setStats(newStats);
                    setLastEventCount(newStats.total_consensus_events);
                }
            } catch (e) {
                console.error('Failed to fetch consensus:', e);
            }
        };

        // Initial fetch
        fetchConsensus();

        // Add initial system messages
        const now = new Date();
        setActivities([
            {
                id: 'init-1',
                timestamp: now,
                type: 'system',
                content: 'Neural stream connected • Monitoring swarm activity',
                icon: <Zap size={12} />,
                color: '#00d4aa'
            },
            {
                id: 'init-2',
                timestamp: new Date(now.getTime() - 5000),
                type: 'system',
                content: 'Ultra-concentrated strategy active • 80% confidence threshold',
                icon: <Target size={12} />,
                color: '#ffc107'
            }
        ]);

        // Poll every 5 seconds
        const interval = setInterval(fetchConsensus, 5000);
        return () => clearInterval(interval);
    }, []);

    return (
        <Box sx={{
            height: '100%',
            minHeight: 400,
            display: 'flex',
            flexDirection: 'column',
            bgcolor: 'rgba(0,0,0,0.4)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 2,
            overflow: 'hidden'
        }}>
            {/* Header */}
            <Box sx={{
                p: 1.5,
                borderBottom: '1px solid rgba(255,255,255,0.08)',
                display: 'flex',
                justifyContent: 'space-between',
                bgcolor: 'rgba(255,255,255,0.02)'
            }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Brain size={16} color="#00d4aa" />
                    <Typography variant="overline" sx={{ fontWeight: 700, color: '#fff', letterSpacing: 1 }}>
                        NEURAL STREAM
                    </Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{
                        width: 6,
                        height: 6,
                        borderRadius: '50%',
                        bgcolor: '#00ff00',
                        animation: 'pulse 2s infinite'
                    }} />
                    <Typography variant="caption" sx={{ color: '#00ff00' }}>LIVE</Typography>
                    {stats && (
                        <Chip
                            label={`${stats.total_consensus_events} events`}
                            size="small"
                            sx={{
                                ml: 1,
                                height: 18,
                                bgcolor: 'rgba(0,212,170,0.1)',
                                color: '#00d4aa',
                                fontSize: '0.6rem'
                            }}
                        />
                    )}
                </Box>
            </Box>

            {/* Activity Stream */}
            <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
                {activities.length === 0 ? (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, opacity: 0.5 }}>
                        <Typography variant="caption" sx={{ color: '#00d4aa', fontFamily: 'JetBrains Mono' }}>
                            Connecting to neural network...
                        </Typography>
                    </Box>
                ) : (
                    activities.map((activity) => (
                        <Box
                            key={activity.id}
                            sx={{
                                fontFamily: 'JetBrains Mono',
                                fontSize: '0.75rem',
                                mb: 1.5,
                                display: 'flex',
                                gap: 1.5,
                                opacity: 0.9,
                                '&:hover': { opacity: 1 }
                            }}
                        >
                            <Typography variant="caption" sx={{ color: '#444', minWidth: 55, flexShrink: 0 }}>
                                {activity.timestamp.toLocaleTimeString([], {
                                    hour12: false,
                                    hour: '2-digit',
                                    minute: '2-digit',
                                    second: '2-digit'
                                })}
                            </Typography>
                            <Box sx={{ color: activity.color, display: 'flex', alignItems: 'center' }}>
                                {activity.icon}
                            </Box>
                            <Typography component="span" sx={{ color: '#ccc' }}>
                                {activity.content}
                            </Typography>
                        </Box>
                    ))
                )}
                <div ref={bottomRef} />
            </Box>

            {/* Footer Stats */}
            {stats && (
                <Box sx={{
                    p: 1.5,
                    borderTop: '1px solid rgba(255,255,255,0.05)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    bgcolor: 'rgba(0,0,0,0.3)'
                }}>
                    <Typography variant="caption" sx={{ color: '#666' }}>
                        {stats.active_agents} agents • {(stats.avg_agreement * 100).toFixed(0)}% agreement
                    </Typography>
                    <Typography variant="caption" sx={{ color: stats.success_rate >= 0.9 ? '#00d4aa' : '#ffc107' }}>
                        {(stats.success_rate * 100).toFixed(0)}% success rate
                    </Typography>
                </Box>
            )}
        </Box>
    );
};

export default NewAsterBrainStream;

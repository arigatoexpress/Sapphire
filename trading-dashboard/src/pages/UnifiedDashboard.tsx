import React from 'react';
import { Box, Grid, Paper, Typography, Chip } from '@mui/material';
import { TrendingUp, TrendingDown, Wallet, Activity, Users, Zap } from 'lucide-react';
import { useTradingData } from '../contexts/TradingContext';
import { NewAsterAgentGrid } from '../components/mission-control/NewAsterAgentGrid';
import UnifiedPositionsTable from '../components/UnifiedPositionsTable';
import { NewAsterBrainStream } from '../components/mission-control/NewAsterBrainStream';
import ConsensusPanel from '../components/ConsensusPanel';
import StrategyStatusCard from '../components/StrategyStatusCard';

// Stat Card Component
const StatCard: React.FC<{
    title: string;
    value: string;
    subtitle?: string;
    trend?: 'up' | 'down' | 'neutral';
    icon: React.ReactNode;
    highlight?: boolean;
}> = ({ title, value, subtitle, trend, icon, highlight }) => (
    <Paper
        sx={{
            p: 2.5,
            borderRadius: 2,
            background: highlight
                ? 'linear-gradient(135deg, rgba(0,212,170,0.1), rgba(10,11,16,0.95))'
                : 'linear-gradient(135deg, rgba(10,11,16,0.95), rgba(15,16,22,0.9))',
            border: highlight
                ? '1px solid rgba(0,212,170,0.2)'
                : '1px solid rgba(255,255,255,0.06)',
            height: '100%',
            position: 'relative',
            overflow: 'hidden'
        }}
    >
        {highlight && (
            <Box sx={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: 2,
                background: 'linear-gradient(90deg, #00d4aa, transparent)',
            }} />
        )}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
            <Typography variant="caption" sx={{ color: '#666', textTransform: 'uppercase', letterSpacing: 1, fontSize: '0.65rem' }}>
                {title}
            </Typography>
            <Box sx={{ color: highlight ? '#00d4aa' : '#444' }}>{icon}</Box>
        </Box>
        <Typography variant="h5" sx={{
            fontWeight: 700,
            color: trend === 'up' ? '#00d4aa' : trend === 'down' ? '#ff6b6b' : '#fff',
            fontFamily: 'JetBrains Mono, monospace',
            mb: 0.5
        }}>
            {value}
        </Typography>
        {subtitle && (
            <Typography variant="caption" sx={{ color: '#666', fontSize: '0.7rem' }}>
                {subtitle}
            </Typography>
        )}
    </Paper>
);

export const UnifiedDashboard: React.FC = () => {
    const {
        portfolio_value,
        total_pnl,
        total_pnl_percent,
        agents,
        open_positions,
        market_regime
    } = useTradingData();

    const activeAgents = agents.filter(a => a.status === 'active').length;
    const pnlTrend = total_pnl >= 0 ? 'up' : 'down';

    return (
        <Box sx={{ maxWidth: 1800, mx: 'auto' }}>
            {/* Clean Header */}
            <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box>
                    <Typography variant="h4" sx={{ fontWeight: 700, color: '#fff', mb: 0.5 }}>
                        Sapphire AI
                    </Typography>
                    <Typography variant="body2" sx={{ color: '#555' }}>
                        Ultra-Concentrated Trading • PvP Optimized
                    </Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    {market_regime && (
                        <Chip
                            label={market_regime.current_regime}
                            size="small"
                            sx={{
                                bgcolor: 'rgba(0,212,170,0.1)',
                                color: '#00d4aa',
                                fontSize: '0.7rem',
                                fontWeight: 600
                            }}
                        />
                    )}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            bgcolor: '#00ff00',
                            boxShadow: '0 0 8px #00ff00'
                        }} />
                        <Typography variant="caption" sx={{ color: '#00ff00', fontWeight: 600 }}>
                            LIVE
                        </Typography>
                    </Box>
                </Box>
            </Box>

            {/* Stats Row */}
            <Grid container spacing={2} sx={{ mb: 4 }}>
                <Grid item xs={6} md={2.4}>
                    <StatCard
                        title="Portfolio Value"
                        value={`$${portfolio_value.toLocaleString()}`}
                        icon={<Wallet size={18} />}
                        highlight
                    />
                </Grid>
                <Grid item xs={6} md={2.4}>
                    <StatCard
                        title="Total P&L"
                        value={`${total_pnl >= 0 ? '+' : ''}$${total_pnl.toFixed(2)}`}
                        subtitle={`${total_pnl_percent >= 0 ? '+' : ''}${total_pnl_percent.toFixed(2)}%`}
                        trend={pnlTrend}
                        icon={pnlTrend === 'up' ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
                    />
                </Grid>
                <Grid item xs={6} md={2.4}>
                    <StatCard
                        title="Active Agents"
                        value={`${activeAgents} / ${agents.length}`}
                        subtitle="Swarm consensus"
                        icon={<Users size={18} />}
                    />
                </Grid>
                <Grid item xs={6} md={2.4}>
                    <StatCard
                        title="Open Positions"
                        value={`${open_positions.length} / 4`}
                        subtitle="Ultra-focused"
                        icon={<Activity size={18} />}
                    />
                </Grid>
                <Grid item xs={12} md={2.4}>
                    <StatCard
                        title="Strategy"
                        value="High Conviction"
                        subtitle="80% min confidence"
                        icon={<Zap size={18} />}
                    />
                </Grid>
            </Grid>

            {/* Main Content - 3 Column Layout */}
            <Grid container spacing={3}>
                {/* Left Column: Consensus & Strategy */}
                <Grid item xs={12} lg={4}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        <ConsensusPanel />
                        <StrategyStatusCard positionCount={open_positions.length} />
                    </Box>
                </Grid>

                {/* Middle Column: Agents & Positions */}
                <Grid item xs={12} lg={4}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        <NewAsterAgentGrid />
                        <Paper
                            sx={{
                                p: 3,
                                borderRadius: 2,
                                background: 'linear-gradient(135deg, rgba(10,11,16,0.95), rgba(15,16,22,0.9))',
                                border: '1px solid rgba(255,255,255,0.06)',
                            }}
                        >
                            <Typography variant="overline" sx={{ color: '#00d4aa', fontWeight: 700, letterSpacing: 1.2, mb: 2, display: 'block' }}>
                                OPEN POSITIONS
                            </Typography>
                            <UnifiedPositionsTable
                                asterPositions={open_positions as any}
                                hypePositions={[]}
                                onUpdateTpSl={(sym, tp, sl) => console.log('TP/SL Update', sym, tp, sl)}
                            />
                        </Paper>
                    </Box>
                </Grid>

                {/* Right Column: Activity Feed */}
                <Grid item xs={12} lg={4}>
                    <Paper
                        sx={{
                            p: 3,
                            borderRadius: 2,
                            background: 'linear-gradient(135deg, rgba(10,11,16,0.95), rgba(15,16,22,0.9))',
                            border: '1px solid rgba(255,255,255,0.06)',
                            height: 'calc(100vh - 280px)',
                            minHeight: 500,
                            overflow: 'hidden',
                            display: 'flex',
                            flexDirection: 'column'
                        }}
                    >
                        <Typography variant="overline" sx={{ color: '#00d4aa', fontWeight: 700, letterSpacing: 1.2, mb: 2, display: 'block' }}>
                            BRAIN STREAM
                        </Typography>
                        <Box sx={{ flex: 1, overflow: 'auto' }}>
                            <NewAsterBrainStream />
                        </Box>
                    </Paper>
                </Grid>
            </Grid>
        </Box>
    );
};

export default UnifiedDashboard;

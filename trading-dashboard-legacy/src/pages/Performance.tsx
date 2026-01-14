import React from 'react';
import { Box, Grid, Typography, CircularProgress } from '@mui/material';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useTradingData } from '../contexts/TradingContext';
import SapphireDust from '../components/SapphireDust';

const GlassCard: React.FC<{ children: React.ReactNode, title?: string, colSpan?: number, height?: number | string, delay?: number }> = ({
    children, title, colSpan = 1, height, delay = 0
}) => (
    <Grid item xs={12} md={colSpan * 4} lg={colSpan * 3}>
        <div
            className="relative group overflow-hidden rounded-3xl transition-all duration-700 ease-out"
            style={{
                height: height || '100%',
                minHeight: 200,
                opacity: 0,
                animation: `fadeInUp 0.8s ease-out ${delay}s forwards`
            }}
        >
            {/* Glass Background */}
            <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl border border-white/5 rounded-3xl group-hover:border-blue-500/30 transition-colors duration-500"></div>

            {/* Animated Glow Border */}
            <div className="absolute -inset-[1px] bg-gradient-to-r from-blue-500/20 via-purple-500/20 to-cyan-500/20 rounded-3xl opacity-0 group-hover:opacity-100 blur-sm transition-opacity duration-500"></div>

            <div className="relative p-6 h-full flex flex-col z-10">
                {title && (
                    <div className="flex items-center justify-between mb-4">
                        <Typography variant="overline" className="text-slate-400 font-bold tracking-widest text-xs uppercase">
                            {title}
                        </Typography>
                        <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shadow-[0_0_8px_#3b82f6] animate-pulse"></div>
                    </div>
                )}
                <div className="flex-1 relative">
                    {children}
                </div>
            </div>
        </div>
    </Grid>
);

const KPICard: React.FC<{ label: string, value: string, subValue?: string, trend?: 'up' | 'down' | 'neutral', sparkline?: boolean }> = ({ label, value, subValue, trend }) => (
    <div className="flex flex-col h-full justify-between">
        <div>
            <Typography className="text-slate-400 text-sm font-medium mb-1">{label}</Typography>
            <Typography variant="h3" className="font-black text-white tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
                {value}
            </Typography>
        </div>
        {subValue && (
            <div className={`
                flex items-center gap-2 mt-2 px-3 py-1.5 rounded-lg w-fit text-sm font-bold
                ${trend === 'up' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                    trend === 'down' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                        'bg-blue-500/10 text-blue-400 border border-blue-500/20'}
            `}>
                <span>{trend === 'up' ? '▲' : trend === 'down' ? '▼' : '•'}</span>
                {subValue}
            </div>
        )}
    </div>
);

export const Performance: React.FC = () => {
    const [metrics, setMetrics] = React.useState<any>(null);
    const [loading, setLoading] = React.useState(true);
    const { apiBaseUrl } = useTradingData();

    React.useEffect(() => {
        const fetchMetrics = async () => {
            try {
                const response = await fetch(`${apiBaseUrl}/api/analytics/performance/stats`);
                const data = await response.json();
                if (data.status === 'success') {
                    setMetrics(data);
                }
            } catch (error) {
                console.error("Failed to fetch performance stats:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchMetrics();
        const interval = setInterval(fetchMetrics, 10000); // Faster polling for "Live" feel
        return () => clearInterval(interval);
    }, [apiBaseUrl]);

    // Calculate Aggregates
    const aggregated = React.useMemo(() => {
        if (!metrics || !metrics.metrics) return null;

        const agents = Object.values(metrics.metrics) as any[];
        const totalPnL = agents.reduce((sum, a) => sum + (a.total_pnl || 0), 0);
        const totalWins = agents.reduce((sum, a) => sum + (a.wins || 0), 0);
        const totalTrades = agents.reduce((sum, a) => sum + (a.total_trades || 0), 0);
        const winRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0;

        // Find best Sharpe
        const bestAgent = agents.reduce((prev, curr) =>
            (curr.sharpe_ratio || 0) > (prev.sharpe_ratio || 0) ? curr : prev
            , agents[0] || {});

        const chartData = (bestAgent.equity_curve || []).map((val: number, i: number) => ({
            name: i,
            value: val
        }));

        return {
            totalPnL,
            winRate,
            totalTrades,
            bestAgentName: bestAgent.agent_id,
            bestSharpe: bestAgent.sharpe_ratio || 0,
            chartData
        };
    }, [metrics]);

    const chartData = aggregated?.chartData || Array.from({ length: 30 }, (_, i) => ({
        name: i,
        value: Math.sin(i * 0.2) * 100 + i * 5,
    }));

    if (loading && !metrics) {
        return (
            <Box className="flex h-screen items-center justify-center bg-[#050508]">
                <CircularProgress sx={{ color: '#3b82f6' }} />
            </Box>
        );
    }

    return (
        <Box className="relative min-h-screen bg-[#050508] p-8 pb-32 overflow-hidden">
            <style>
                {`@keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }`}
            </style>

            {/* Ambient Background */}
            <div className="fixed inset-0 pointer-events-none">
                <SapphireDust />
                <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-blue-600/10 rounded-full blur-[120px] mix-blend-screen animate-pulse"></div>
                <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-purple-600/10 rounded-full blur-[120px] mix-blend-screen animate-pulse delay-1000"></div>
                <div className="absolute top-1/2 left-1/2 w-[800px] h-[800px] bg-cyan-600/5 rounded-full blur-[150px] mix-blend-screen -translate-x-1/2 -translate-y-1/2"></div>
            </div>

            <div className="relative z-10 max-w-7xl mx-auto">
                <Box className="mb-12">
                    <h1 className="text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-purple-400 to-white mb-4 tracking-tight drop-shadow-lg">
                        Performance Intelligence
                    </h1>
                    <Typography className="text-slate-400 text-lg max-w-2xl font-light">
                        Real-time visualization of algorithmic alpha generation. Tracking Win Rates, Sharpe Ratios, and PnL velocity across the neural swarm.
                    </Typography>
                </Box>

                <Grid container spacing={4}>
                    {/* Row 1: Key Metrics */}
                    <GlassCard title="NET ALPHA GENERATED" colSpan={1} height={240} delay={0.1}>
                        <KPICard
                            label="Total PnL"
                            value={aggregated ? `$${aggregated.totalPnL.toFixed(2)}` : "$0.00"}
                            subValue={aggregated ? `${aggregated.totalTrades} Trades Executed` : "Waiting for signals..."}
                            trend={aggregated?.totalPnL >= 0 ? "up" : "down"}
                        />
                    </GlassCard>
                    <GlassCard title="LEADING NEURAL AGENT" colSpan={1} height={240} delay={0.2}>
                        <KPICard
                            label={aggregated?.bestAgentName || "Analyzing..."}
                            value={aggregated ? `${aggregated.bestSharpe.toFixed(2)}` : "0.00"}
                            subValue="Sharpe Ratio (Risk Adj.)"
                            trend="up"
                        />
                    </GlassCard>
                    <GlassCard title="GLOBAL WIN EFFICIENCY" colSpan={1} height={240} delay={0.3}>
                        <KPICard
                            label="Win Rate"
                            value={aggregated ? `${aggregated.winRate.toFixed(1)}%` : "0.0%"}
                            subValue="Across all strategies"
                            trend={(aggregated?.winRate ?? 0) > 50 ? "up" : "neutral"}
                        />
                    </GlassCard>
                    <GlassCard title="RISK / REWARD GAUGE" colSpan={1} height={240} delay={0.4}>
                        <div className="flex flex-col h-full justify-between items-center relative overflow-hidden">
                            {/* Gauge Visualization */}
                            <div className="w-full h-24 relative mt-4">
                                <div className="absolute inset-x-0 bottom-0 h-2 bg-slate-800 rounded-full overflow-hidden">
                                    {/* Color Zones */}
                                    <div className="absolute left-0 w-1/3 h-full bg-rose-500/50"></div>
                                    <div className="absolute left-1/3 w-1/3 h-full bg-yellow-500/50"></div>
                                    <div className="absolute right-0 w-1/3 h-full bg-emerald-500/50"></div>
                                </div>
                                {/* Needle */}
                                <div
                                    className="absolute bottom-0 left-1/2 w-1 h-20 bg-white origin-bottom rounded-full transition-transform duration-1000 ease-out shadow-[0_0_10px_white]"
                                    style={{
                                        transform: `translateX(-50%) rotate(${Math.min(90, Math.max(-90, ((aggregated?.bestSharpe || 0) - 1.5) * 60))
                                            }deg)`
                                    }}
                                ></div>
                                <div className="absolute bottom-0 left-1/2 w-4 h-4 bg-white rounded-full -translate-x-1/2 translate-y-1/2 shadow-lg"></div>
                            </div>

                            <div className="text-center mt-2 z-10">
                                <div className="text-2xl font-black text-white">{aggregated ? aggregated.bestSharpe.toFixed(2) : "0.00"}</div>
                                <div className="text-xs text-slate-400 font-mono uppercase tracking-wider">Sharpe Ratio</div>
                            </div>
                            {/* Background Glow */}
                            <div className="absolute inset-0 bg-gradient-to-t from-blue-500/10 to-transparent pointer-events-none"></div>
                        </div>
                    </GlassCard>
                    <GlassCard title="MISSION TARGET" colSpan={1} height={240} delay={0.5}>
                        <div className="flex flex-col h-full justify-between">
                            <div>
                                <Typography className="text-slate-400 text-sm font-medium mb-1">$1,000 / Day Goal</Typography>
                                <Typography variant="h3" className="font-black text-white tracking-tight">
                                    {aggregated ? `${((aggregated.totalPnL / 1000) * 100).toFixed(1)}%` : "0%"}
                                </Typography>
                            </div>
                            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden mt-4">
                                <div
                                    className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-cyan-500 relative"
                                    style={{ width: `${Math.min(100, Math.max(0, (aggregated?.totalPnL || 0) / 10))}%` }}
                                >
                                    <div className="absolute inset-0 bg-white/30 animate-[shimmer_2s_infinite]"></div>
                                </div>
                            </div>
                        </div>
                    </GlassCard>


                    {/* Row 2: Main Chart */}
                    <GlassCard title="CUMULATIVE ALPHA CURVE" colSpan={4} height={500} delay={0.5}>
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={chartData} margin={{ top: 20, right: 0, left: -20, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="colorAlpha" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                                <XAxis dataKey="name" hide />
                                <YAxis
                                    tick={{ fill: '#64748b', fontSize: 12 }}
                                    tickLine={false}
                                    axisLine={false}
                                    tickFormatter={(val) => `$${val}`}
                                    domain={['auto', 'auto']}
                                />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#0f1016', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, boxShadow: '0 10px 30px -10px rgba(0,0,0,0.5)' }}
                                    itemStyle={{ color: '#fff', fontWeight: 'bold' }}
                                    formatter={(val: number) => [`$${val.toFixed(2)}`, 'Equity']}
                                    labelStyle={{ display: 'none' }}
                                />
                                <Area
                                    type="monotone"
                                    dataKey="value"
                                    stroke="#3b82f6"
                                    strokeWidth={4}
                                    fillOpacity={1}
                                    fill="url(#colorAlpha)"
                                    animationDuration={2000}
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </GlassCard>
                </Grid>
            </div>
        </Box>
    );
};

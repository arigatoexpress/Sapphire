import React, { useState, useEffect, memo } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Activity, Users, Zap, Target, Brain, Signal, ChevronRight, Trophy, Lock, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { useTradingData } from '../contexts/TradingContext';
import { LiveChatPanel } from '../components/LiveChatPanel';
import { AnimatedNumber } from '../components/ui/AnimatedNumber';
import { Sparkline } from '../components/ui/Sparkline';
import PlatformRouterStatus from '../components/PlatformRouterStatus';
import HFTStatusWidget from '../components/HFTStatusWidget';
import { getApiUrl } from '../utils/apiConfig';

// ============ STAT CARD ============
const StatCard = memo<{
    title: string;
    value: string | number;
    subtitle?: string;
    trend?: 'up' | 'down' | 'neutral';
    icon: React.ReactNode;
    highlight?: boolean;
    isNumeric?: boolean;
    prefix?: string;
    suffix?: string;
    delay?: number;
    sparklineData?: number[];
}>(({ title, value, subtitle, trend, icon, highlight, isNumeric, prefix = '', suffix = '', delay = 0, sparklineData }) => (
    <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: delay * 0.08, ease: [0.25, 0.46, 0.45, 0.94] }}
        className={`relative p-4 rounded-xl border backdrop-blur-xl overflow-hidden transition-all hover:scale-[1.02] hover:shadow-lg hover:shadow-cyan-500/5 ${highlight
            ? 'bg-gradient-to-br from-cyan-500/10 to-slate-900/90 border-cyan-500/30'
            : 'bg-slate-900/60 border-white/5 hover:border-white/10'
            }`}
    >
        {highlight && <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-cyan-400 via-cyan-500/50 to-transparent" />}
        <div className="flex justify-between items-start mb-2">
            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">{title}</span>
            <span className={highlight ? 'text-cyan-400' : 'text-slate-600'}>{icon}</span>
        </div>
        <div className="flex items-end justify-between gap-2">
            <div className={`text-2xl font-bold font-mono ${trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-white'}`}>
                {isNumeric && typeof value === 'number' ? (
                    <AnimatedNumber value={value} prefix={prefix} suffix={suffix} colorBySign={trend !== 'neutral'} />
                ) : (
                    value
                )}
            </div>
            {sparklineData && sparklineData.length >= 2 && (
                <div className="w-16 h-6 opacity-80">
                    <Sparkline data={sparklineData} color="auto" height={24} />
                </div>
            )}
        </div>
        {subtitle && <span className="text-[10px] text-slate-600">{subtitle}</span>}
    </motion.div>
));
StatCard.displayName = 'StatCard';

// ============ AGENT PERFORMANCE CARD ============
const AgentCard = memo<{
    name: string;
    emoji: string;
    winRate: number;
    trades: number;
    weight: number;
    isActive: boolean;
    system?: string;
    delay?: number;
}>(({ name, emoji, winRate, trades, weight, isActive, system = 'aster', delay = 0 }) => (
    <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.3, delay: delay * 0.1 }}
        className="relative p-3 rounded-lg bg-slate-800/50 border border-white/5 hover:border-cyan-500/30 hover:scale-[1.02] transition-all group cursor-pointer"
    >
        <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
                <span className="text-lg">{emoji}</span>
                <div className="flex flex-col">
                    <span className="text-sm font-medium text-white">{name}</span>
                    <span className={`text-[9px] uppercase tracking-tighter font-bold ${system === 'aster' ? 'text-emerald-400' :
                        system === 'symphony' ? 'text-purple-400' :
                            system === 'drift' ? 'text-blue-400' : 'text-cyan-400'
                        }`}>
                        {system}
                    </span>
                </div>
            </div>
            <div className={`w-2 h-2 rounded-full ${isActive ? 'bg-emerald-400 animate-pulse shadow-lg shadow-emerald-400/50' : 'bg-slate-600'}`} />
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
            <div>
                <div className="text-xs text-slate-500">Win Rate</div>
                <div className={`text-sm font-bold ${winRate >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {(winRate * 100).toFixed(0)}%
                </div>
            </div>
            <div>
                <div className="text-xs text-slate-500">Trades</div>
                <div className="text-sm font-bold text-white">{trades}</div>
            </div>
            <div>
                <div className="text-xs text-slate-500">Weight</div>
                <div className="text-sm font-bold text-cyan-400">{(weight * 100).toFixed(0)}%</div>
            </div>
        </div>
    </motion.div>
));
AgentCard.displayName = 'AgentCard';

// ============ SIGNAL ITEM ============
const SignalItem = memo<{
    symbol: string;
    signal: string;
    confidence: number;
    agreement: number;
    isStrong: boolean;
    timestamp: number;
}>(({ symbol, signal, confidence, agreement, isStrong }) => {
    const isLong = (signal || '').includes('long');

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.2 }}
            className={`relative p-2 rounded-lg border transition-all hover:scale-[1.01] ${isStrong
                ? 'bg-cyan-500/10 border-cyan-500/30 shadow-lg shadow-cyan-500/5'
                : 'bg-slate-800/30 border-white/5 hover:border-white/10'
                }`}
        >
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <div className={`p-1 rounded ${isLong ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                        {isLong ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                    </div>
                    <span className="text-sm font-mono text-white">{symbol.replace('USDT', '')}</span>
                    {isStrong && (
                        <span className="text-[9px] bg-cyan-500/20 text-cyan-400 px-1.5 py-0.5 rounded-full font-medium animate-pulse">
                            STRONG
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-3">
                    <div className="text-right">
                        <div className="text-[10px] text-slate-500">Confidence</div>
                        <div className={`text-xs font-bold ${(confidence ?? 0) > 0.7 ? 'text-emerald-400' : (confidence ?? 0) > 0.4 ? 'text-yellow-400' : 'text-slate-400'}`}>
                            {((confidence ?? 0) * 100).toFixed(0)}%
                        </div>
                    </div>
                    <div className="text-right">
                        <div className="text-[10px] text-slate-500">Agreement</div>
                        <div className="text-xs font-bold text-cyan-400">{((agreement ?? 0) * 100).toFixed(0)}%</div>
                    </div>
                </div>
            </div>
        </motion.div>
    );
});
SignalItem.displayName = 'SignalItem';

// ============ LEADERBOARD WIDGET ============
const LeaderboardWidget: React.FC = () => {
    const [leaders, setLeaders] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchLeaders = async () => {
            try {
                const res = await fetch('/api/leaderboard?limit=5');
                if (res.ok) {
                    const data = await res.json();
                    setLeaders(data.slice(0, 5));
                }
            } catch (e) {
                // Mock data for demo
                setLeaders([
                    { rank: 1, email: 'trader***@gmail.com', total_points: 2450, streak_days: 12 },
                    { rank: 2, email: 'crypto***@outlook.com', total_points: 2180, streak_days: 8 },
                    { rank: 3, email: 'anon***@proton.me', total_points: 1920, streak_days: 15 },
                    { rank: 4, email: 'whale***@gmail.com', total_points: 1650, streak_days: 5 },
                    { rank: 5, email: 'degen***@yahoo.com', total_points: 1420, streak_days: 3 },
                ]);
            } finally {
                setLoading(false);
            }
        };
        fetchLeaders();
    }, []);

    const getRankBadge = (rank: number) => {
        if (rank === 1) return '🥇';
        if (rank === 2) return '🥈';
        if (rank === 3) return '🥉';
        return `#${rank}`;
    };

    const encryptEmail = (email: string) => {
        if (!email) return '***@***';
        const [user, domain] = email.split('@');
        const encUser = user.slice(0, 3) + '***';
        const encDomain = domain ? domain.slice(0, 3) + '***' : '***';
        return `${encUser}@${encDomain}`;
    };

    return (
        <div className="bg-slate-900/60 backdrop-blur-xl rounded-xl border border-white/5 p-4">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Trophy className="w-4 h-4 text-yellow-400" />
                    <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">Leaderboard</span>
                </div>
                <Link to="/leaderboard" className="text-[10px] text-cyan-400 hover:text-cyan-300 flex items-center gap-1">
                    View All <ChevronRight size={12} />
                </Link>
            </div>
            <div className="space-y-2">
                {loading ? (
                    <div className="text-center text-slate-500 py-4">Loading...</div>
                ) : (
                    leaders.map((leader, idx) => (
                        <div key={idx} className={`flex items-center justify-between p-2 rounded-lg ${leader.rank <= 3 ? 'bg-yellow-500/5 border border-yellow-500/10' : 'bg-slate-800/30'
                            }`}>
                            <div className="flex items-center gap-2">
                                <span className="text-sm w-6">{getRankBadge(leader.rank)}</span>
                                <div className="flex items-center gap-1">
                                    <Lock size={10} className="text-slate-600" />
                                    <span className="text-xs text-slate-400 font-mono">{encryptEmail(leader.email)}</span>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <span className="text-xs font-bold text-yellow-400">{leader.total_points} pts</span>
                                {leader.streak_days >= 7 && <span className="text-[10px]">🔥{leader.streak_days}</span>}
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};

// ============ MAIN DASHBOARD ============
export const UnifiedDashboard: React.FC = () => {
    const {
        total_pnl_percent,
        portfolio_value,
        agents,
        open_positions,
        market_regime,
        recent_activity,
        portfolio_history
    } = useTradingData();

    const [consensusStats, setConsensusStats] = useState<any>(null);
    const API_URL = getApiUrl();

    // Fetch consensus stats directly for more data
    useEffect(() => {
        const fetchStats = async () => {
            try {
                const res = await fetch(`${API_URL}/api/consensus/state`);
                if (res.ok) {
                    const data = await res.json();
                    setConsensusStats(data.stats);
                }
            } catch (e) {
                console.error('Failed to fetch consensus stats', e);
            }
        };
        fetchStats();
        const interval = setInterval(fetchStats, 15000);
        return () => clearInterval(interval);
    }, [API_URL]);

    const activeAgents = agents.filter(a => a.status === 'active').length;
    const pnlTrend = total_pnl_percent >= 0 ? 'up' : 'down';
    const formattedPnL = `${total_pnl_percent >= 0 ? '+' : ''}${total_pnl_percent.toFixed(2)}%`;
    const avgWinRate = agents.length > 0
        ? agents.reduce((sum, a) => sum + (a.win_rate > 1 ? a.win_rate : a.win_rate * 100), 0) / agents.length
        : 50;

    const signalDistribution = consensusStats?.signal_distribution || { entry_long: 0, entry_short: 0 };
    const totalSignals = signalDistribution.entry_long + signalDistribution.entry_short;
    const longPercent = totalSignals > 0 ? (signalDistribution.entry_long / totalSignals) * 100 : 50;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-white">Mission Control</h1>
                    <p className="text-sm text-slate-500">Real-time AI Trading Intelligence</p>
                </div>
                <div className="flex items-center gap-3">
                    {market_regime && (
                        <span className="px-3 py-1 rounded-full text-xs font-medium bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                            {market_regime.current_regime}
                        </span>
                    )}
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-lg shadow-emerald-400/50" />
                        <span className="text-xs font-medium text-emerald-400">LIVE</span>
                    </div>
                </div>
            </div>

            {/* Stats Row */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                <StatCard
                    title="Portfolio Return"
                    value={formattedPnL}
                    subtitle="Total P&L"
                    trend={pnlTrend}
                    icon={pnlTrend === 'up' ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                    sparklineData={portfolio_history}
                    highlight
                    delay={0}
                />
                <StatCard
                    title="Portfolio Value"
                    value={`$${(portfolio_value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                    subtitle="Live Balance"
                    icon={<Activity size={16} />}
                />
                <StatCard
                    title="Avg Win Rate"
                    value={`${avgWinRate.toFixed(0)}%`}
                    subtitle="All agents"
                    trend={avgWinRate >= 50 ? 'up' : 'down'}
                    icon={<Target size={16} />}
                />
                <StatCard
                    title="Active Agents"
                    value={`${activeAgents}`}
                    subtitle={`${agents.length} in swarm`}
                    icon={<Users size={16} />}
                />
                <StatCard
                    title="Open Positions"
                    value={`${open_positions.length}`}
                    subtitle="Max 4 concentrated"
                    icon={<Zap size={16} />}
                />
                <StatCard
                    title="Consensus Events"
                    value={`${consensusStats?.total_consensus_events || 0}`}
                    subtitle={`${((consensusStats?.success_rate || 0) * 100).toFixed(0)}% success`}
                    icon={<Brain size={16} />}
                />
            </div>

            {/* Platform Router Status */}
            <PlatformRouterStatus />

            {/* HFT Engine Status - Phase 6 */}
            <HFTStatusWidget />

            {/* Market Bias Bar */}
            <div className="bg-slate-900/60 backdrop-blur-xl rounded-xl border border-white/5 p-4">
                <div className="flex items-center justify-between mb-2">
                    <span className="text-xs uppercase tracking-wider text-slate-400">Market Bias</span>
                    <span className="text-xs text-slate-500">{totalSignals} signals analyzed</span>
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-sm font-bold text-emerald-400">LONG {longPercent.toFixed(0)}%</span>
                    <div className="flex-1 h-2 rounded-full bg-slate-800 overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-500"
                            style={{ width: `${longPercent}%` }}
                        />
                    </div>
                    <span className="text-sm font-bold text-red-400">{(100 - longPercent).toFixed(0)}% SHORT</span>
                </div>
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {/* Agent Performance */}
                <div className="bg-slate-900/60 backdrop-blur-xl rounded-xl border border-white/5 p-4">
                    <div className="flex items-center gap-2 mb-3">
                        <Users className="w-4 h-4 text-cyan-400" />
                        <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">Agent Performance</span>
                    </div>
                    <div className="space-y-2">
                        {agents.map((agent) => (
                            <AgentCard
                                key={agent.id}
                                name={agent.name}
                                emoji={agent.emoji || '🤖'}
                                winRate={agent.win_rate}
                                trades={agent.total_trades}
                                weight={1.0}
                                isActive={agent.status === 'active'}
                                system={agent.system}
                            />
                        ))}
                    </div>
                </div>

                {/* Live Signals */}
                <div className="bg-slate-900/60 backdrop-blur-xl rounded-xl border border-white/5 p-4">
                    <div className="flex items-center gap-2 mb-3">
                        <Signal className="w-4 h-4 text-cyan-400" />
                        <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">Live Consensus Signals</span>
                    </div>
                    <div className="space-y-1.5 max-h-[350px] overflow-y-auto">
                        {(recent_activity || []).slice(0, 12).map((signal: any, idx: number) => (
                            <SignalItem
                                key={idx}
                                symbol={signal.symbol}
                                signal={signal.winning_signal}
                                confidence={signal.confidence}
                                agreement={signal.agreement}
                                isStrong={signal.is_strong}
                                timestamp={signal.timestamp_us}
                            />
                        ))}
                    </div>
                </div>

                {/* Leaderboard */}
                <LeaderboardWidget />
            </div>

            {/* Consensus Metrics */}
            {consensusStats && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-slate-900/40 rounded-lg p-3 border border-white/5">
                        <div className="text-[10px] text-slate-500 uppercase mb-1">Avg Confidence</div>
                        <div className="text-lg font-bold text-cyan-400">{((consensusStats.avg_confidence || 0) * 100).toFixed(1)}%</div>
                    </div>
                    <div className="bg-slate-900/40 rounded-lg p-3 border border-white/5">
                        <div className="text-[10px] text-slate-500 uppercase mb-1">Avg Agreement</div>
                        <div className="text-lg font-bold text-emerald-400">{((consensusStats.avg_agreement || 0) * 100).toFixed(1)}%</div>
                    </div>
                    <div className="bg-slate-900/40 rounded-lg p-3 border border-white/5">
                        <div className="text-[10px] text-slate-500 uppercase mb-1">Participation Rate</div>
                        <div className="text-lg font-bold text-yellow-400">{((consensusStats.avg_participation || 0) * 100).toFixed(1)}%</div>
                    </div>
                    <div className="bg-slate-900/40 rounded-lg p-3 border border-white/5">
                        <div className="text-[10px] text-slate-500 uppercase mb-1">Success Rate</div>
                        <div className="text-lg font-bold text-purple-400">{((consensusStats.success_rate || 0) * 100).toFixed(1)}%</div>
                    </div>
                </div>
            )}

            {/* Community Intelligence Chat */}
            <div className="h-[400px]">
                <LiveChatPanel />
            </div>
        </div>
    );
};

export default UnifiedDashboard;

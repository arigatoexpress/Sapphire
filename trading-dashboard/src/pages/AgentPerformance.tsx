import React, { useState, useEffect } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Activity, TrendingUp, TrendingDown, Brain, Target, Zap } from 'lucide-react';

// Inline UI Components
const Card: React.FC<{ children: React.ReactNode; className?: string; onClick?: () => void }> = ({ children, className = '', onClick }) => (
    <div className={`rounded-lg border ${className}`} onClick={onClick}>{children}</div>
);

const CardHeader: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <div className="p-6 pb-3">{children}</div>
);

const CardTitle: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
    <h3 className={`font-semibold ${className}`}>{children}</h3>
);

const CardContent: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
    <div className={`p-6 pt-3 ${className}`}>{children}</div>
);

const Badge: React.FC<{ children: React.ReactNode; className?: string; variant?: string }> = ({ children, className = '', variant = 'default' }) => {
    const baseClass = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold';
    const variantClass = variant === 'outline' ? 'border' : '';
    return <span className={`${baseClass} ${variantClass} ${className}`}>{children}</span>;
};
interface AgentMetrics {
    agent_id: string;
    name: string;
    specialization: string;
    total_trades: number;
    winning_trades: number;
    win_rate: number;
    recent_win_rate: number;
    health: 'LEARNING' | 'PERFORMING' | 'HEALTHY' | 'UNDERPERFORMING';
    preferred_indicators: string[];
    indicator_scores: Record<string, number>;
    confidence_threshold: number;
    // Advanced Ratios
    sharpe_ratio?: number;
    sortino_ratio?: number;
    calmar_ratio?: number;
    alpha?: number;
    beta?: number;
    profit_factor?: number;
    max_drawdown?: number;
    recovery_factor?: number;
    expectancy?: number;
    equity_curve?: number[];
}

interface ConsensusDecision {
    timestamp: number;
    symbol: string;
    opportunity_score: number;
    opportunity_reason: string;
    agent_votes: Array<{
        agent_id: string;
        agent_name: string;
        signal: string;
        confidence: number;
        reasoning: string;
    }>;
    consensus_signal: string;
    consensus_confidence: number;
    buy_score: number;
    sell_score: number;
    executed: boolean;
    position_status?: string;
    final_pnl?: number;
}
const MetricCard: React.FC<{ label: string; value: string | number; description: string; trend?: 'up' | 'down' | 'neutral' }> = ({ label, value, description, trend }) => (
    <div className="bg-white/5 border border-white/10 rounded-xl p-3 hover:bg-white/10 transition-colors group">
        <div className="flex justify-between items-start mb-1">
            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-widest leading-none">{label}</span>
            {trend === 'up' && <TrendingUp size={10} className="text-emerald-400" />}
            {trend === 'down' && <TrendingDown size={10} className="text-rose-400" />}
        </div>
        <div className="text-lg font-bold text-white font-mono leading-none mb-1">{typeof value === 'number' ? value.toFixed(2) : value}</div>
        <div className="text-[9px] text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity leading-tight">{description}</div>
    </div>
);
const AgentPerformance: React.FC = () => {
    const [agents, setAgents] = useState<AgentMetrics[]>([]);
    const [consensusHistory, setConsensusHistory] = useState<ConsensusDecision[]>([]);
    const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
    const [evolutionData, setEvolutionData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    // Fetch data on mount and every 5 seconds
    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 5000);
        return () => clearInterval(interval);
    }, []);

    // Fetch evolution data when agent is selected
    useEffect(() => {
        if (selectedAgent) {
            fetchEvolutionData(selectedAgent);
        }
    }, [selectedAgent]);

    const fetchData = async () => {
        try {
            const [agentsRes, consensusRes] = await Promise.all([
                fetch('/api/agents/autonomous-performance'),
                fetch('/api/agents/consensus-history?limit=20')
            ]);

            const agentsData = await agentsRes.json();
            const consensusData = await consensusRes.json();

            setAgents(agentsData.agents || []);
            setConsensusHistory(consensusData.decisions || []);
            setLoading(false);
        } catch (error) {
            console.error('Error fetching agent data:', error);
            setLoading(false);
        }
    };

    const fetchEvolutionData = async (agentId: string) => {
        try {
            const res = await fetch(`/api/agents/evolution/${agentId}`);
            const data = await res.json();
            setEvolutionData(data);
        } catch (error) {
            console.error('Error fetching evolution data:', error);
        }
    };

    const getHealthColor = (health: string) => {
        switch (health) {
            case 'HEALTHY': return 'bg-emerald-500';
            case 'PERFORMING': return 'bg-blue-500';
            case 'UNDERPERFORMING': return 'bg-rose-500';
            case 'LEARNING': return 'bg-slate-500';
            default: return 'bg-gray-500';
        }
    };

    const formatTimestamp = (timestamp: number) => {
        const date = new Date(timestamp * 1000);
        return date.toLocaleTimeString();
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-screen">
                <div className="text-xl">Loading agent performance data...</div>
            </div>
        );
    }

    return (
        <div className="p-6 space-y-6 bg-gray-950 min-h-screen">
            {/* Header */}
            <div className="mb-8 flex justify-between items-end">
                <div>
                    <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
                        <Brain className="text-blue-400" /> Quant Lab <span className="text-slate-500 text-lg font-normal">/ Agent Analytics</span>
                    </h1>
                    <p className="text-gray-400 font-mono text-sm tracking-tight">Advanced risk-adjusted performance & strategy evolution</p>
                </div>
                <div className="flex gap-4 mb-2">
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] text-slate-500 uppercase font-bold">System Status</span>
                        <span className="text-xs text-emerald-400 flex items-center gap-1 font-mono">
                            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            LIVE_UPLINK_ACTIVE
                        </span>
                    </div>
                </div>
            </div>

            {/* Section 1: Agent Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {agents.map((agent) => (
                    <Card
                        key={agent.agent_id}
                        className={`bg-[#0a0c12] border-white/5 cursor-pointer transition-all hover:border-blue-500/50 relative overflow-hidden group ${selectedAgent === agent.agent_id ? 'border-blue-500 bg-blue-500/5' : ''
                            }`}
                        onClick={() => setSelectedAgent(agent.agent_id)}
                    >
                        <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none group-hover:opacity-10 transition-opacity">
                            <Zap size={80} />
                        </div>

                        <CardHeader>
                            <div className="flex justify-between items-start">
                                <div>
                                    <div className="flex items-center gap-2">
                                        <CardTitle className="text-white text-lg font-bold">{agent.name}</CardTitle>
                                        <Badge className={`${getHealthColor(agent.health)} text-[9px] uppercase tracking-tighter text-white/90 px-1.5`}>
                                            {agent.health}
                                        </Badge>
                                    </div>
                                    <p className="text-[10px] font-mono text-blue-400 capitalize tracking-widest mt-0.5">{agent.specialization}</p>
                                </div>
                                <div className="text-right">
                                    <div className="text-[10px] text-slate-500 font-mono">WIN_RATE</div>
                                    <div className="text-xl font-bold text-white font-mono">{(agent.win_rate * 100).toFixed(0)}%</div>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {/* Scientific Metrics Grid */}
                            <div className="grid grid-cols-2 gap-2">
                                <MetricCard
                                    label="Sharpe"
                                    value={agent.sharpe_ratio || 0}
                                    description="Risk-adjusted return vs volatility"
                                    trend={(agent.sharpe_ratio || 0) > 1.5 ? 'up' : 'neutral'}
                                />
                                <MetricCard
                                    label="Profit Factor"
                                    value={agent.profit_factor || 0}
                                    description="Gross Profit / Gross Loss"
                                    trend={(agent.profit_factor || 0) > 1.2 ? 'up' : 'neutral'}
                                />
                                <MetricCard
                                    label="Recovery"
                                    value={agent.recovery_factor || 0}
                                    description="Speed of recovery from drawdown"
                                    trend={(agent.recovery_factor || 0) > 2 ? 'up' : 'neutral'}
                                />
                                <MetricCard
                                    label="Expectancy"
                                    value={agent.expectancy || 0}
                                    description="Avg profitability per trade"
                                    trend={(agent.expectancy || 0) > 0 ? 'up' : 'neutral'}
                                />
                            </div>

                            {/* Equity Sparkline Mini */}
                            {agent.equity_curve && agent.equity_curve.length > 0 && (
                                <div className="h-16 w-full opacity-50 group-hover:opacity-100 transition-opacity">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <LineChart data={agent.equity_curve.map((v, i) => ({ v, i }))}>
                                            <Line type="monotone" dataKey="v" stroke="#3B82F6" strokeWidth={2} dot={false} />
                                        </LineChart>
                                    </ResponsiveContainer>
                                </div>
                            )}

                            {/* Stats */}
                            <div className="flex justify-between items-center py-2 border-t border-white/5">
                                <div className="flex gap-4">
                                    <div className="text-[10px] font-mono">
                                        <span className="text-slate-500">TRADES:</span> <span className="text-white">{agent.total_trades}</span>
                                    </div>
                                    <div className="text-[10px] font-mono">
                                        <span className="text-slate-500">WINS:</span> <span className="text-emerald-400">{agent.winning_trades}</span>
                                    </div>
                                </div>
                                <div className="flex flex-wrap gap-1 justify-end">
                                    {agent.preferred_indicators.slice(0, 2).map((indicator) => (
                                        <span key={indicator} className="text-[9px] px-1 bg-white/5 border border-white/10 rounded text-slate-400 font-mono">
                                            {indicator}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>

            {/* Section 2: Consensus Timeline & Research Notes */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                    <Card className="bg-[#0a0c12] border-white/5 h-full">
                        <CardHeader>
                            <CardTitle className="text-white flex items-center gap-2">
                                <Target className="w-5 h-5 text-blue-400" />
                                Consensus Decision Log
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-white/10">
                                {consensusHistory.length === 0 ? (
                                    <p className="text-gray-500 text-center py-8">No decisions recorded in current epoch</p>
                                ) : (
                                    consensusHistory.map((decision, idx) => (
                                        <div
                                            key={idx}
                                            className="p-4 bg-white/[0.02] rounded-lg border border-white/5 hover:border-white/10 transition-colors"
                                        >
                                            <div className="flex justify-between items-start mb-2">
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-white font-bold font-mono tracking-tighter">{decision.symbol}</span>
                                                        <Badge className={`${decision.consensus_signal === 'BUY' ? 'bg-emerald-600' : 'bg-rose-600'} text-[10px]`}>
                                                            {decision.consensus_signal}
                                                        </Badge>
                                                        <span className="text-[10px] text-slate-500 font-mono">CONF: {((decision.consensus_confidence ?? 0) * 100).toFixed(0)}%</span>
                                                    </div>
                                                    <p className="text-[10px] text-slate-500 mt-1 uppercase tracking-widest">{formatTimestamp(decision.timestamp)}</p>
                                                </div>
                                                {decision.final_pnl !== undefined && (
                                                    <div className={`px-2 py-1 rounded text-xs font-bold font-mono ${decision.final_pnl > 0 ? 'text-emerald-400 bg-emerald-500/10' : 'text-rose-400 bg-rose-500/10'}`}>
                                                        {decision.final_pnl > 0 ? '+' : ''}{(decision.final_pnl * 100).toFixed(2)}%
                                                    </div>
                                                )}
                                            </div>

                                            <p className="text-xs text-slate-400 mb-3 bg-white/5 p-2 rounded italic border-l-2 border-blue-500/50">
                                                "{decision.opportunity_reason}"
                                            </p>

                                            <div className="flex gap-2 overflow-x-auto pb-2">
                                                {decision.agent_votes.map((vote) => (
                                                    <div key={vote.agent_id} className="bg-black/40 p-1.5 rounded border border-white/5 min-w-[120px]">
                                                        <div className="flex justify-between items-center mb-1">
                                                            <span className="text-[9px] text-slate-500 truncate mr-1">{vote.agent_name}</span>
                                                            <span className={`text-[9px] font-bold ${vote.signal === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>{vote.signal}</span>
                                                        </div>
                                                        <div className="w-full bg-white/5 h-1 rounded-full overflow-hidden">
                                                            <div className="bg-blue-500 h-full" style={{ width: `${(vote.confidence || 0) * 100}%` }} />
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </CardContent>
                    </Card>
                </div>

                <div className="lg:col-span-1">
                    <Card className="bg-[#0a0c12] border-white/5 h-full">
                        <CardHeader>
                            <CardTitle className="text-white flex items-center gap-2">
                                <Activity className="w-5 h-5 text-purple-400" />
                                Research Notes
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="p-4 bg-purple-500/5 border border-purple-500/20 rounded-xl">
                                <h4 className="text-purple-400 text-xs font-bold uppercase mb-2">Swarm Intelligence</h4>
                                <p className="text-xs text-slate-400 leading-relaxed">
                                    Decisions are reached through a weighted consensus of 6 autonomous agents. Each agent utilizes a unique combination of technical, sentiment, and volume microstructure models.
                                </p>
                            </div>

                            <div className="space-y-3">
                                <div className="flex items-start gap-3">
                                    <div className="w-6 h-6 rounded bg-blue-500/20 flex items-center justify-center text-blue-400 shrink-0 text-[10px] font-bold">01</div>
                                    <div>
                                        <div className="text-white text-xs font-bold">Feature Extraction</div>
                                        <p className="text-[10px] text-slate-500">UMEP pipeline processes 50+ dimensions per symbol including HFT order flow.</p>
                                    </div>
                                </div>
                                <div className="flex items-start gap-3">
                                    <div className="w-6 h-6 rounded bg-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0 text-[10px] font-bold">02</div>
                                    <div>
                                        <div className="text-white text-xs font-bold">Cross-Verification</div>
                                        <p className="text-[10px] text-slate-500">Agents must maintain {'>'} 45% win rate to influence the final consensus signal.</p>
                                    </div>
                                </div>
                                <div className="flex items-start gap-3">
                                    <div className="w-6 h-6 rounded bg-purple-500/20 flex items-center justify-center text-purple-400 shrink-0 text-[10px] font-bold">03</div>
                                    <div>
                                        <div className="text-white text-xs font-bold">Adaptive Execution</div>
                                        <p className="text-[10px] text-slate-500">Stops and targets are recalculated every minute based on realized volatility (ATR).</p>
                                    </div>
                                </div>
                            </div>

                            <div className="mt-6 pt-6 border-t border-white/5">
                                <div className="text-[10px] text-slate-500 font-mono mb-2 uppercase">Lab Metrics Guide</div>
                                <div className="space-y-2">
                                    <div className="flex justify-between items-center text-[10px]">
                                        <span className="text-slate-400">Sharpe Ratio</span>
                                        <span className="text-white font-bold">{'>'} 1.5 is Optimal</span>
                                    </div>
                                    <div className="flex justify-between items-center text-[10px]">
                                        <span className="text-slate-400">Profit Factor</span>
                                        <span className="text-white font-bold">{'>'} 1.2 is Profitable</span>
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>

            {/* Section 3: Agent Evolution Charts */}
            {selectedAgent && evolutionData && evolutionData.snapshots.length > 0 && (
                <Card className="bg-gray-900 border-gray-800">
                    <CardHeader>
                        <CardTitle className="text-white flex items-center gap-2">
                            <Zap className="w-5 h-5" />
                            Agent Evolution: {agents.find(a => a.agent_id === selectedAgent)?.name}
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {/* Win Rate Chart */}
                            <div>
                                <h3 className="text-white font-semibold mb-4">Win Rate Over Time</h3>
                                <ResponsiveContainer width="100%" height={250}>
                                    <LineChart data={evolutionData.snapshots}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                        <XAxis
                                            dataKey="timestamp"
                                            tickFormatter={(ts) => new Date(ts * 1000).toLocaleDateString()}
                                            stroke="#9CA3AF"
                                            tick={{ fill: '#9CA3AF' }}
                                        />
                                        <YAxis
                                            stroke="#9CA3AF"
                                            tick={{ fill: '#9CA3AF' }}
                                            domain={[0, 1]}
                                            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                                        />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                                            labelStyle={{ color: '#F3F4F6' }}
                                        />
                                        <Line type="monotone" dataKey="win_rate" stroke="#3B82F6" strokeWidth={2} dot={{ fill: '#3B82F6' }} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>

                            {/* Indicator Scores */}
                            <div>
                                <h3 className="text-white font-semibold mb-4">Latest Indicator Preferences</h3>
                                <ResponsiveContainer width="100%" height={250}>
                                    <BarChart
                                        data={Object.entries(evolutionData.snapshots[evolutionData.snapshots.length - 1].indicator_scores || {})
                                            .map(([name, score]) => ({ name, score }))
                                            .sort((a, b) => (b.score as number) - (a.score as number))
                                            .slice(0, 5)
                                        }
                                        layout="horizontal"
                                    >
                                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                        <XAxis type="number" stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} domain={[0, 1]} />
                                        <YAxis type="category" dataKey="name" stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                                            labelStyle={{ color: '#F3F4F6' }}
                                        />
                                        <Bar dataKey="score" fill="#10B981" />
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Section 4: Performance Comparison */}
            {agents.length > 1 && (
                <Card className="bg-gray-900 border-gray-800">
                    <CardHeader>
                        <CardTitle className="text-white">Performance Comparison</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={agents}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                                <XAxis dataKey="name" stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} />
                                <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF' }} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                                    labelStyle={{ color: '#F3F4F6' }}
                                />
                                <Legend wrapperStyle={{ color: '#9CA3AF' }} />
                                <Bar dataKey="win_rate" name="Overall Win Rate" fill="#3B82F6" />
                                <Bar dataKey="recent_win_rate" name="Recent Win Rate" fill="#10B981" />
                            </BarChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>
            )}
        </div>
    );
};

export default AgentPerformance;

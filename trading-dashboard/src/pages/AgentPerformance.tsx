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
            case 'HEALTHY': return 'bg-green-500';
            case 'PERFORMING': return 'bg-yellow-500';
            case 'UNDERPERFORMING': return 'bg-red-500';
            case 'LEARNING': return 'bg-blue-500';
            default: return 'bg-gray-500';
        }
    };

    const getHealthIcon = (health: string) => {
        switch (health) {
            case 'HEALTHY': return <TrendingUp className="w-4 h-4" />;
            case 'PERFORMING': return <Activity className="w-4 h-4" />;
            case 'UNDERPERFORMING': return <TrendingDown className="w-4 h-4" />;
            case 'LEARNING': return <Brain className="w-4 h-4" />;
            default: return <Activity className="w-4 h-4" />;
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
            <div className="mb-8">
                <h1 className="text-3xl font-bold text-white mb-2">Autonomous Agent Performance</h1>
                <p className="text-gray-400">Monitor agent decisions, win rates, and strategy evolution</p>
            </div>

            {/* Section 1: Agent Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {agents.map((agent) => (
                    <Card
                        key={agent.agent_id}
                        className={`bg-gray-900 border-gray-800 cursor-pointer transition-all hover:border-blue-500 ${selectedAgent === agent.agent_id ? 'border-blue-500' : ''
                            }`}
                        onClick={() => setSelectedAgent(agent.agent_id)}
                    >
                        <CardHeader>
                            <div className="flex justify-between items-start">
                                <div>
                                    <CardTitle className="text-white text-lg">{agent.name}</CardTitle>
                                    <p className="text-sm text-gray-400 capitalize">{agent.specialization}</p>
                                </div>
                                <Badge className={`${getHealthColor(agent.health)} text-white flex items-center gap-1`}>
                                    {getHealthIcon(agent.health)}
                                    {agent.health}
                                </Badge>
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            {/* Win Rate */}
                            <div>
                                <div className="flex justify-between text-sm mb-1">
                                    <span className="text-gray-400">Overall Win Rate</span>
                                    <span className="text-white font-semibold">{(agent.win_rate * 100).toFixed(1)}%</span>
                                </div>
                                <div className="w-full bg-gray-800 rounded-full h-2">
                                    <div
                                        className="bg-blue-500 h-2 rounded-full transition-all"
                                        style={{ width: `${agent.win_rate * 100}%` }}
                                    />
                                </div>
                            </div>

                            {/* Recent Win Rate */}
                            <div>
                                <div className="flex justify-between text-sm mb-1">
                                    <span className="text-gray-400">Recent (Last 10)</span>
                                    <span className="text-white font-semibold">{(agent.recent_win_rate * 100).toFixed(1)}%</span>
                                </div>
                                <div className="w-full bg-gray-800 rounded-full h-2">
                                    <div
                                        className="bg-green-500 h-2 rounded-full transition-all"
                                        style={{ width: `${agent.recent_win_rate * 100}%` }}
                                    />
                                </div>
                            </div>

                            {/* Stats */}
                            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-gray-800">
                                <div>
                                    <p className="text-xs text-gray-500">Total Trades</p>
                                    <p className="text-lg font-bold text-white">{agent.total_trades}</p>
                                </div>
                                <div>
                                    <p className="text-xs text-gray-500">Wins</p>
                                    <p className="text-lg font-bold text-green-400">{agent.winning_trades}</p>
                                </div>
                            </div>

                            {/* Top Indicators */}
                            <div>
                                <p className="text-xs text-gray-500 mb-1">Preferred Indicators</p>
                                <div className="flex flex-wrap gap-1">
                                    {agent.preferred_indicators.slice(0, 3).map((indicator) => (
                                        <Badge key={indicator} variant="outline" className="text-xs border-gray-700 text-gray-300">
                                            {indicator}
                                        </Badge>
                                    ))}
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>

            {/* Section 2: Consensus Timeline */}
            <Card className="bg-gray-900 border-gray-800">
                <CardHeader>
                    <CardTitle className="text-white flex items-center gap-2">
                        <Target className="w-5 h-5" />
                        Recent Consensus Decisions
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                        {consensusHistory.length === 0 ? (
                            <p className="text-gray-500 text-center py-8">No consensus decisions yet</p>
                        ) : (
                            consensusHistory.map((decision, idx) => (
                                <div
                                    key={idx}
                                    className="p-4 bg-gray-800 rounded-lg border border-gray-700"
                                >
                                    <div className="flex justify-between items-start mb-2">
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <span className="text-white font-semibold">{decision.symbol}</span>
                                                <Badge className={decision.consensus_signal === 'BUY' ? 'bg-green-600' : 'bg-red-600'}>
                                                    {decision.consensus_signal}
                                                </Badge>
                                                {decision.position_status && (
                                                    <Badge variant="outline" className="border-gray-600 text-gray-400">
                                                        {decision.position_status}
                                                    </Badge>
                                                )}
                                            </div>
                                            <p className="text-xs text-gray-500 mt-1">{formatTimestamp(decision.timestamp)}</p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-sm text-gray-400">Confidence</p>
                                            <p className="text-lg font-bold text-white">{(decision.consensus_confidence * 100).toFixed(0)}%</p>
                                        </div>
                                    </div>

                                    <p className="text-sm text-gray-400 mb-2">{decision.opportunity_reason}</p>

                                    {/* Agent Votes */}
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-3">
                                        {decision.agent_votes.map((vote) => (
                                            <div key={vote.agent_id} className="bg-gray-900 p-2 rounded border border-gray-700">
                                                <div className="flex justify-between items-center">
                                                    <span className="text-xs text-gray-500">{vote.agent_name}</span>
                                                    <Badge
                                                        variant={vote.signal === decision.consensus_signal ? 'default' : 'outline'}
                                                        className="text-xs"
                                                    >
                                                        {vote.signal}
                                                    </Badge>
                                                </div>
                                                <p className="text-xs text-gray-400 mt-1">
                                                    Conf: {(vote.confidence * 100).toFixed(0)}%
                                                </p>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Outcome */}
                                    {decision.final_pnl !== undefined && (
                                        <div className={`mt-2 p-2 rounded ${decision.final_pnl > 0 ? 'bg-green-900/20' : 'bg-red-900/20'}`}>
                                            <p className="text-sm font-semibold ${decision.final_pnl > 0 ? 'text-green-400' : 'text-red-400'}">
                                                Final PnL: {(decision.final_pnl * 100).toFixed(2)}%
                                            </p>
                                        </div>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                </CardContent>
            </Card>

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

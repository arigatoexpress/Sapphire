
import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Zap, Target, Award, Activity, Users } from 'lucide-react';
import { GlassCard } from '../GlassCard';
import { useTradingData } from '../../contexts/TradingContext';

interface NeuralState {
    stats: {
        avg_confidence: number;
        agreement_level: number;
        participation_rate: number;
        total_consensus_events: number;
    };
    weights: Record<string, number>;
}

export const NeuralConsensus: React.FC = () => {
    const { apiBaseUrl } = useTradingData();
    const [state, setState] = useState<NeuralState | null>(null);
    const [lastUpdate, setLastUpdate] = useState<number>(Date.now());

    useEffect(() => {
        const fetchState = async () => {
            try {
                const res = await fetch(`${apiBaseUrl}/consensus/state`);
                const data = await res.json();
                if (data.status === 'active') {
                    setState(data);
                    setLastUpdate(Date.now());
                }
            } catch (e) {
                console.error("Failed to fetch consensus state", e);
            }
        };

        const interval = setInterval(fetchState, 5000); // 5s poll
        fetchState();
        return () => clearInterval(interval);
    }, [apiBaseUrl]);

    if (!state || !state.stats) return (
        <GlassCard title="NEURAL CONSENSUS" height={300}>
            <div className="flex items-center justify-center h-full text-blue-400/50 animate-pulse">
                INITIALIZING NEURAL LINK...
            </div>
        </GlassCard>
    );

    const agents = Object.entries(state.weights || {}).sort(([, a], [, b]) => b - a).slice(0, 5); // Top 5
    const totalWeight = Object.values(state.weights || {}).reduce((a, b) => a + b, 0) || 1;

    return (
        <GlassCard title="SWARM INTELLIGENCE" height={340} className="relative overflow-hidden group">
            {/* Background Neural Effect */}
            <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-purple-500/5 z-0" />
            <div className="absolute top-0 right-0 p-4 opacity-20">
                <Brain className="w-24 h-24 text-blue-400 animate-pulse" />
            </div>

            <div className="relative z-10 flex flex-col h-full gap-4">

                {/* Top Metrics Row */}
                <div className="grid grid-cols-3 gap-2">
                    <div className="bg-black/20 rounded-lg p-3 border border-white/5 backdrop-blur-sm">
                        <div className="flex items-center gap-2 mb-1">
                            <Zap className="w-3 h-3 text-yellow-400" />
                            <span className="text-[10px] text-gray-400 uppercase tracking-wider">Confidence</span>
                        </div>
                        <div className="text-xl font-bold text-white font-mono">
                            {((state.stats?.avg_confidence ?? 0) * 100).toFixed(0)}%
                        </div>
                    </div>

                    <div className="bg-black/20 rounded-lg p-3 border border-white/5 backdrop-blur-sm">
                        <div className="flex items-center gap-2 mb-1">
                            <Users className="w-3 h-3 text-blue-400" />
                            <span className="text-[10px] text-gray-400 uppercase tracking-wider">Agreement</span>
                        </div>
                        <div className="text-xl font-bold text-white font-mono">
                            {((state.stats?.agreement_level ?? 0) * 100).toFixed(0)}%
                        </div>
                    </div>

                    <div className="bg-black/20 rounded-lg p-3 border border-white/5 backdrop-blur-sm">
                        <div className="flex items-center gap-2 mb-1">
                            <Activity className="w-3 h-3 text-green-400" />
                            <span className="text-[10px] text-gray-400 uppercase tracking-wider">Events</span>
                        </div>
                        <div className="text-xl font-bold text-white font-mono">
                            {state.stats.total_consensus_events}
                        </div>
                    </div>
                </div>

                {/* Neural Weights Display */}
                <div className="flex-1 overflow-y-auto pr-1">
                    <h4 className="text-[10px] text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Award className="w-3 h-3" /> Top Performing Synapses (Weights)
                    </h4>

                    <div className="space-y-2">
                        {agents.map(([agentId, weight], idx) => {
                            const percent = (weight / totalWeight) * 100;
                            const isTop = idx === 0;

                            return (
                                <motion.div
                                    key={agentId}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: idx * 0.1 }}
                                    className={`
                                        relative p-2 rounded border
                                        ${isTop
                                            ? 'bg-gradient-to-r from-yellow-500/10 to-transparent border-yellow-500/30'
                                            : 'bg-white/5 border-white/5'}
                                    `}
                                >
                                    <div className="flex justify-between items-center mb-1 text-xs">
                                        <span className={`font-medium ${isTop ? 'text-yellow-400' : 'text-gray-300'}`}>
                                            {agentId}
                                        </span>
                                        <span className="font-mono text-gray-400">{weight.toFixed(2)}x</span>
                                    </div>

                                    {/* Weight Bar */}
                                    <div className="w-full h-1 bg-black/40 rounded-full overflow-hidden">
                                        <motion.div
                                            className={`h-full ${isTop ? 'bg-yellow-400' : 'bg-blue-500'}`}
                                            initial={{ width: 0 }}
                                            animate={{ width: `${Math.min(percent * 3, 100)}%` }} // Scale up for visibility
                                        />
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>
            </div>
        </GlassCard>
    );
};

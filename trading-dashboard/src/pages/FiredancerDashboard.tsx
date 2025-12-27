import React, { useState, useEffect, useMemo } from 'react';
import FiredancerLayout from '../components/firedancer/FiredancerLayout';
import StreamWaterfall, { StreamItem } from '../components/firedancer/StreamWaterfall';
import MetricTurbine from '../components/firedancer/MetricTurbine';
import StatusStrip from '../components/firedancer/StatusStrip';
import { useTradingData } from '../contexts/TradingContext';

const FiredancerDashboard: React.FC = () => {
    const { logs, agents, open_positions, metrics, connected } = useTradingData();

    // Mock cycle state (still useful for UI flavor if backend doesn't provide current phase)
    const [phase, setPhase] = useState<'scan' | 'signal' | 'entry' | 'manage' | 'exit'>('scan');

    // Auto-cycle for demo flavor
    useEffect(() => {
        const phases: any[] = ['scan', 'signal', 'entry', 'manage', 'exit'];
        let i = 0;
        const interval = setInterval(() => {
            i = (i + 1) % phases.length;
            setPhase(phases[i]);
        }, 3000);
        return () => clearInterval(interval);
    }, []);

    // Transform logs to stream items
    const streamItems = useMemo<StreamItem[]>(() => {
        return logs.map(log => ({
            id: log.id,
            timestamp: log.timestamp,
            // Logic to determine type based on content/role
            type: log.type === 'trade' || log.content.toLowerCase().includes('filled') ? 'trade' :
                log.type === 'signal' || log.content.toLowerCase().includes('signal') ? 'signal' :
                    log.content.toLowerCase().includes('funding') ? 'funding' :
                        log.content.toLowerCase().includes('error') ? 'error' : 'info',
            message: log.content || log.message || '',
            symbol: log.agent?.toUpperCase() || 'SYS',
            agent: log.agent
        }));
    }, [logs]);

    const totalPortfolioPnl = useMemo(() => {
        return open_positions.reduce((acc, pos) => acc + (pos.pnl || 0), 0);
    }, [open_positions]);

    return (
        <FiredancerLayout>
            {/* LEFT COLUMN: System Metrics (Turbines) - 3 Cols */}
            <div className="col-span-3 flex flex-col gap-4 h-full">
                <div className="h-32">
                    <StatusStrip currentPhase={phase} />
                </div>

                <div className="grid grid-cols-2 gap-2 flex-1">
                    <MetricTurbine
                        label="TPS (Signals)"
                        value={logs.length.toString()}
                        unit="sig/s"
                        trend="up"
                        color="success"
                        progress={Math.min(85, logs.length)}
                    />
                    <MetricTurbine
                        label="Latency"
                        value={connected ? "<20" : "--"}
                        unit="ms"
                        color="blue"
                        progress={connected ? 15 : 0}
                    />
                    <MetricTurbine
                        label="Win Rate"
                        value={(metrics.win_rate * 100).toFixed(1)}
                        unit="%"
                        color="purple"
                        trend={metrics.win_rate > 0.5 ? "up" : "down"}
                    />
                    <MetricTurbine
                        label="Active Agents"
                        value={agents.filter(a => a.status === 'active').length.toString()}
                        color="warning"
                        subtext="Swarm Mode"
                    />
                </div>

                {/* Portfolio Map Placeholder */}
                <div className="h-48 bg-fd-card border border-fd-border p-2 rounded-sm overflow-hidden relative">
                    <span className="absolute top-2 left-2 text-[10px] font-mono text-gray-500">CAPITAL ALLOCATION</span>
                    <div className="mt-4 flex flex-wrap gap-1 h-full content-start">
                        {agents.length > 0 ? agents.map((agent, i) => (
                            <div
                                key={agent.id}
                                style={{ width: `${Math.max(20, agent.allocation / 10)}%`, height: '40%' }}
                                className={`
                                    border flex items-center justify-center text-[10px] font-mono
                                    ${i === 0 ? 'bg-fd-success/20 border-fd-success text-fd-success' :
                                        i === 1 ? 'bg-fd-blue/20 border-fd-blue text-fd-blue' :
                                            'bg-fd-purple/20 border-fd-purple text-fd-purple'}
                                `}
                            >
                                {agent.name.split(' ')[0]}
                            </div>
                        )) : (
                            <div className="w-full text-center text-fd-muted text-[10px] mt-8">NO AGENTS ACTIVE</div>
                        )}
                    </div>
                </div>
            </div>

            {/* MIDDLE COLUMN: The Waterfall (Main Stream) - 6 Cols */}
            <div className="col-span-6 h-full">
                <StreamWaterfall items={streamItems} />
            </div>

            {/* RIGHT COLUMN: Active Positions - 3 Cols */}
            <div className="col-span-3 flex flex-col gap-4 h-full">
                <div className="bg-fd-card border border-fd-border flex-1 p-2 rounded-sm relative overflow-hidden">
                    <div className="flex justify-between items-center mb-2 border-b border-fd-border pb-1">
                        <span className="text-[10px] font-mono uppercase text-gray-400">Active Positions</span>
                        <span className={`text-[10px] font-mono px-1 py-0.5 rounded ${totalPortfolioPnl >= 0 ? 'text-fd-success bg-fd-success/10' : 'text-fd-error bg-fd-error/10'}`}>
                            {totalPortfolioPnl >= 0 ? '+' : ''}${totalPortfolioPnl.toFixed(2)}
                        </span>
                    </div>

                    <div className="space-y-2 overflow-y-auto max-h-[400px]">
                        {open_positions.length > 0 ? open_positions.map((pos) => (
                            <div key={pos.symbol} className={`flex justify-between items-center text-xs font-mono p-1 bg-fd-bg/50 border-l-2 ${pos.pnl >= 0 ? 'border-fd-success' : 'border-fd-error'}`}>
                                <div className="flex flex-col">
                                    <span className="text-gray-300">{pos.symbol}</span>
                                    <span className="text-[9px] text-gray-500">{pos.side} {pos.leverage}x</span>
                                </div>
                                <span className={pos.pnl >= 0 ? 'text-fd-success' : 'text-fd-error'}>
                                    {pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(2)}%
                                </span>
                            </div>
                        )) : (
                            <div className="text-center py-8 text-fd-muted text-[10px] font-mono uppercase">No Open Positions</div>
                        )}
                    </div>
                </div>

                <div className="h-1/3 bg-fd-card border border-fd-border p-2 rounded-sm relative overflow-hidden">
                    <span className="text-[10px] font-mono uppercase text-gray-400 block mb-2">Memepool (Pending)</span>
                    <div className="space-y-1 opacity-50">
                        <div className="h-1 w-full bg-fd-border rounded animate-pulse"></div>
                        <div className="h-1 w-2/3 bg-fd-border rounded animate-pulse delay-75"></div>
                        <div className="h-1 w-4/5 bg-fd-border rounded animate-pulse delay-150"></div>
                    </div>
                </div>
            </div>
        </FiredancerLayout>
    );
};

export default FiredancerDashboard;

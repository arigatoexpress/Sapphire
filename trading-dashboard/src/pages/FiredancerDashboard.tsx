
import React from 'react';
import { MissionControlLayout } from '../components/mission-control/layout/MissionControlLayout';
import { GlassPanel } from '../components/mission-control/ui/GlassPanel';
import { Activity, Zap, Brain, TrendingUp, Terminal, ShieldAlert } from 'lucide-react';
import { useTradingData } from '../contexts/TradingContext';
import { ACTSPanel as ACTSPanelComponent, MemoryInsightsPanel as MemoryInsightsPanelComponent } from '../components/ACTSPanel';

import TradingViewChart from '../components/TradingViewChart';
import { useState, useEffect } from 'react';

// --- Utils ---
const generateMockData = (count: number = 100) => {
    const data = [];
    let time = Math.floor(Date.now() / 1000) - count * 60;
    let price = 45000;
    for (let i = 0; i < count; i++) {
        const open = price;
        const close = price + (Math.random() - 0.5) * 100;
        const high = Math.max(open, close) + Math.random() * 50;
        const low = Math.min(open, close) - Math.random() * 50;
        const volume = Math.random() * 100;
        data.push({ time, open, high, low, close, volume });
        time += 60;
        price = close;
    }
    return data;
};

// Placeholder Components (We will build these out next)
const TradeTape = ({ trades }: { trades: any[] }) => (
    <div className="h-full overflow-y-auto space-y-1 font-mono text-xs p-2 scrollbar-hide">
        {trades.length === 0 && <div className="text-slate-500 text-center mt-10">Waiting for trades...</div>}
        {trades.map((trade, i) => (
            <div key={i} className="flex justify-between items-center text-slate-400 border-b border-white/5 pb-1 hover:bg-white/5 px-2 rounded cursor-pointer transition-colors animate-fade-in">
                <span className="text-cyan-400">{new Date(trade.timestamp || Date.now()).toLocaleTimeString()}</span>
                <span className={trade.side === "BUY" ? "text-emerald-400" : "text-rose-400"}>
                    {trade.side}
                </span>
                <span className="text-white">{trade.symbol}</span>
                <span>{trade.quantity}</span>
                <span className="text-slate-500">{trade.platform}</span>
            </div>
        ))}
    </div>
);

const AICortex = ({ lastLog }: { lastLog: any }) => (
    <div className="h-full flex flex-col items-center justify-center relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-blue-500/10 via-transparent to-transparent animate-pulse-slow" />
        <div className="relative z-10 text-center space-y-4 w-full px-4">
            <div className="flex justify-center gap-8">
                <div className={`flex flex-col items-center gap-2 transition-all duration-300 ${lastLog?.source === 'flash' ? 'scale-110' : ''}`}>
                    <div className="w-16 h-16 rounded-full border-2 border-cyan-500 flex items-center justify-center shadow-[0_0_20px_rgba(34,211,238,0.3)] bg-cyan-500/10">
                        <Zap className="text-cyan-400 w-8 h-8" />
                    </div>
                    <span className="text-xs font-mono text-cyan-400">FLASH v3.0</span>
                </div>
                <div className={`flex flex-col items-center gap-2 transition-all duration-300 ${lastLog?.source === 'pro' ? 'scale-110' : ''}`}>
                    <div className="w-16 h-16 rounded-full border-2 border-purple-500 flex items-center justify-center shadow-[0_0_20px_rgba(168,85,247,0.3)] bg-purple-500/10">
                        <Brain className="text-purple-400 w-8 h-8" />
                    </div>
                    <span className="text-xs font-mono text-purple-400">PRO v3.0</span>
                </div>
            </div>

            {/* Live AI Log Stream */}
            <div className="p-3 bg-white/5 rounded border border-white/10 w-full backdrop-blur-md min-h-[80px] flex items-center justify-center">
                {lastLog ? (
                    <p className="text-xs text-slate-300 font-mono animate-fade-in text-left w-full">
                        <span className="text-cyan-500 mr-2">[{new Date(lastLog.timestamp).toLocaleTimeString()}]</span>
                        {lastLog.message}
                    </p>
                ) : (
                    <p className="text-xs text-slate-500 font-mono italic">"Monitoring market conditions..."</p>
                )}
            </div>
        </div>
    </div>
);

const FiredancerDashboard: React.FC = () => {
    // 1. Access Data from TradingContext (Centralized State)
    const {
        recent_trades,
        logs,
        open_positions,
        connected: isConnected,
        portfolio_value
    } = useTradingData();

    // 2. Map Context Data to Component Props
    const trades = recent_trades || [];
    const lastLog = logs && logs.length > 0 ? logs[0] : null;

    // Chart Data State
    const [chartData, setChartData] = useState<any[]>([]);

    useEffect(() => {
        setChartData(generateMockData(150));
        const interval = setInterval(() => {
            // Simulate live candle updates
            setChartData(prev => {
                const last = prev[prev.length - 1];
                const newTime = last.time + 60;
                const newPrice = last.close + (Math.random() - 0.5) * 50;
                const newCandle = {
                    time: newTime,
                    open: last.close,
                    high: Math.max(last.close, newPrice) + Math.random() * 20,
                    low: Math.min(last.close, newPrice) - Math.random() * 20,
                    close: newPrice,
                    volume: Math.random() * 50
                };
                return [...prev.slice(1), newCandle];
            });
        }, 3000);
        return () => clearInterval(interval);
    }, []);

    // CLI State
    const [cliInput, setCliInput] = useState("");
    const [cliOutput, setCliOutput] = useState<string[]>([]);

    const handleCliSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!cliInput.trim()) return;

        const cmd = cliInput.trim().toLowerCase();
        let response = "";

        if (cmd === 'help') response = "Available commands: status, clear, agents, scan";
        else if (cmd === 'status') response = `System: ${isConnected ? 'ONLINE' : 'OFFLINE'} | Portfolio: $${portfolio_value?.toFixed(2)}`;
        else if (cmd === 'clear') { setCliOutput([]); setCliInput(""); return; }
        else if (cmd === 'scan') response = "Initiating deep market scan... [MOCK]";
        else response = `Unknown command: ${cmd}`;

        setCliOutput(prev => [...prev, `> ${cliInput}`, response]);
        setCliInput("");
    };

    return (
        <MissionControlLayout>
            {/* Bento Grid Layout */}
            <div className="grid grid-cols-12 grid-rows-12 gap-4 h-full">

                {/* Left Col: Market Data (3 cols) */}
                <div className="col-span-3 row-span-12 flex flex-col gap-4">
                    <GlassPanel title="Live Feed" icon={<Activity size={16} />} className="flex-[2]">
                        <TradeTape trades={trades} />
                    </GlassPanel>
                    <GlassPanel title="Active Positions" icon={<TrendingUp size={16} />} className="flex-1 overflow-y-auto scrollbar-hide">
                        {open_positions && open_positions.length > 0 ? (
                            <div className="space-y-2 p-2">
                                {open_positions.map((pos, idx) => (
                                    <div key={idx} className="bg-white/5 p-2 rounded border border-white/5 flex justify-between items-center">
                                        <div>
                                            <div className="font-bold text-sm text-white">{pos.symbol}</div>
                                            <div className={`text-xs ${pos.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>{pos.side}</div>
                                        </div>
                                        <div className="text-right">
                                            <div className="text-sm font-mono text-cyan-300">{pos.size}</div>
                                            <div className={`text-xs font-mono ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                {pos.pnl >= 0 ? '+' : ''}{pos.pnl.toFixed(2)} ({pos.pnl_percent.toFixed(2)}%)
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="flex items-center justify-center h-full text-xs text-slate-500">
                                No Active Positions
                            </div>
                        )}
                    </GlassPanel>
                </div>

                {/* Center Col: AI & Vis (6 cols) */}
                <div className="col-span-6 row-span-12 flex flex-col gap-4">
                    {/* Top: AI Core */}
                    <GlassPanel title="Gemini Cortex" icon={<Brain size={16} />} className="flex-[2] relative overflow-hidden group">
                        <AICortex lastLog={lastLog} />
                    </GlassPanel>

                    {/* Bottom: Charts */}
                    <GlassPanel title="Market Depth [BTC/USDT]" icon={<Activity size={16} />} className="flex-[2] flex flex-col">
                        <div className="flex-1 w-full bg-black/20 rounded-lg overflow-hidden">
                            <TradingViewChart data={chartData} height={250} />
                        </div>
                    </GlassPanel>

                    {/* ACTS Cognitive Swarm */}
                    <GlassPanel title="Cognitive Swarm" icon={<Brain size={16} />} className="flex-[1]">
                        <ACTSPanelComponent />
                    </GlassPanel>
                </div>

                {/* Right Col: Operations (3 cols) */}
                <div className="col-span-3 row-span-12 flex flex-col gap-4">
                    <GlassPanel title="System Status" icon={<ShieldAlert size={16} />} className="h-48">
                        <div className="space-y-4 p-2">
                            <div className="flex justify-between text-xs font-mono">
                                <span className="text-slate-400">Connection</span>
                                <span className={isConnected ? "text-emerald-400" : "text-rose-400"}>
                                    {isConnected ? "STABLE" : "OFFLINE"}
                                </span>
                            </div>
                            <div className="flex justify-between text-xs font-mono">
                                <span className="text-slate-400">Latency</span>
                                <span className={isConnected ? "text-emerald-400" : "text-slate-500"}>
                                    {isConnected ? "12ms" : "--"}
                                </span>
                            </div>
                            <div className={`mt-4 p-2 border rounded text-center transition-colors ${isConnected ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-rose-500/10 border-rose-500/20'}`}>
                                <span className={`text-xs font-bold tracking-widest ${isConnected ? 'text-emerald-400' : 'text-rose-400'}`}>
                                    {isConnected ? "SYSTEM OPTIMAL" : "RECONNECTING..."}
                                </span>
                            </div>
                        </div>
                    </GlassPanel>

                    {/* Memory Insights */}
                    <GlassPanel title="Memory Insights" icon={<Brain size={16} />} className="h-48">
                        <MemoryInsightsPanelComponent />
                    </GlassPanel>

                    <GlassPanel title="Command Line" icon={<Terminal size={16} />} className="flex-1">
                        <div className="h-full flex flex-col font-mono text-xs">
                            <div className="flex-1 text-slate-400 space-y-1 overflow-hidden">
                                <div><span className="text-emerald-500">➜</span> System initialized...</div>
                                <div>
                                    <span className="text-emerald-500">➜</span> Connection:
                                    <span className={isConnected ? "text-emerald-400 ml-2 animate-pulse" : "text-rose-400 ml-2"}>
                                        {isConnected ? "ONLINE" : "RECONNECTING"}
                                    </span>
                                </div>
                                {isConnected ? (
                                    <>
                                        <div><span className="text-emerald-500">➜</span> Feed Latency: <span className="text-emerald-400">12ms</span></div>
                                        <div><span className="text-emerald-500">➜</span> Backend: <span className="text-emerald-400">sapphire-alpha</span></div>
                                    </>
                                ) : (
                                    <div><span className="text-rose-500">➜</span> Waiting for uplink...</div>
                                )}
                            </div>
                            <div className="mt-2 flex items-center gap-2 border-t border-white/10 pt-2">
                                <span className="text-cyan-500">admin@sapphire:~$</span>
                                <form onSubmit={handleCliSubmit} className="flex-1">
                                    <input
                                        type="text"
                                        value={cliInput}
                                        onChange={(e) => setCliInput(e.target.value)}
                                        className="bg-transparent border-none outline-none text-white w-full placeholder-slate-600 focus:ring-0"
                                        placeholder="Enter command..."
                                    />
                                </form>
                            </div>
                            <div className="max-h-20 overflow-y-auto scrollbar-hide text-xs text-slate-300 mt-2 space-y-1">
                                {cliOutput.slice().reverse().map((line, i) => (
                                    <div key={i}>{line}</div>
                                ))}
                            </div>
                        </div>
                    </GlassPanel>
                </div>

            </div>
        </MissionControlLayout>
    );
};

export default FiredancerDashboard;

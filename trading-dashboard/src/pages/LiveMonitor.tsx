import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Pause, Play, Trash2, Cpu, Activity } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useLogStream } from '../hooks/useLogStream';

export const LiveMonitor: React.FC = () => {
    const { user } = useAuth();
    const [token, setToken] = useState<string | null>(null);

    useEffect(() => {
        if (user) user.getIdToken().then(setToken);
    }, [user]);

    const { logs, connected, paused, setPaused, clearLogs } = useLogStream(token);

    const [filterLevel, setFilterLevel] = useState<string>('ALL');
    const [filterModule, setFilterModule] = useState<string>('ALL');
    const [autoScroll, setAutoScroll] = useState(true);
    const scrollRef = useRef<HTMLDivElement>(null);

    // Auto-scroll handler
    useEffect(() => {
        if (autoScroll && scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logs, autoScroll]);

    // Filter logic
    const filteredLogs = logs.filter(log => {
        if (filterLevel !== 'ALL' && log.level !== filterLevel) return false;
        if (filterModule !== 'ALL') {
            // Simple containment check for module filtering
            if (!log.module.toLowerCase().includes(filterModule.toLowerCase())) return false;
        }
        return true;
    });

    const getLevelColor = (level: string) => {
        switch (level) {
            case 'ERROR': return 'text-rose-500';
            case 'CRITICAL': return 'text-rose-600 font-bold bg-rose-950/30';
            case 'WARNING': return 'text-amber-400';
            case 'DEBUG': return 'text-slate-500';
            default: return 'text-emerald-400';
        }
    };

    return (
        <div className="flex flex-col h-[calc(100vh-100px)] gap-4">
            {/* Header / HUD */}
            <div className="flex justify-between items-center p-4 rounded-2xl bg-[#0a0b10] border border-white/10">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400">
                        <Terminal size={20} />
                    </div>
                    <div>
                        <h2 className="text-lg font-bold text-white font-mono">SYSTEM_LOGS_V2</h2>
                        <div className="flex items-center gap-2 text-xs font-mono">
                            <span className={connected ? "text-emerald-500" : "text-rose-500"}>
                                {connected ? "● UPLINK ESTABLISHED" : "○ UPLINK OFFLINE"}
                            </span>
                            <span className="text-slate-500">|</span>
                            <span className="text-slate-400">{filteredLogs.length} EVENTS BUFFERED</span>
                        </div>
                    </div>
                </div>

                {/* Controls */}
                <div className="flex items-center gap-3">
                    <div className="flex bg-[#13141b] rounded-lg p-1 border border-white/5">
                        <select
                            value={filterModule}
                            onChange={(e) => setFilterModule(e.target.value)}
                            className="bg-transparent text-xs font-mono text-slate-300 border-none outline-none px-2 py-1"
                        >
                            <option value="ALL">ALL MODULES</option>
                            <option value="aster">ASTER</option>
                            <option value="hyperliquid">HYPERLIQUID</option>
                            <option value="symphony">SYMPHONY</option>
                            <option value="drift">DRIFT</option>
                            <option value="scanner">SCANNER</option>
                            <option value="consensus">CONSENSUS</option>
                        </select>
                        <div className="w-px bg-white/10 mx-1" />
                        <select
                            value={filterLevel}
                            onChange={(e) => setFilterLevel(e.target.value)}
                            className="bg-transparent text-xs font-mono text-slate-300 border-none outline-none px-2 py-1"
                        >
                            <option value="ALL">ALL LEVELS</option>
                            <option value="INFO">INFO</option>
                            <option value="WARNING">WARNING</option>
                            <option value="ERROR">ERROR</option>
                            <option value="DEBUG">DEBUG</option>
                        </select>
                    </div>

                    <button
                        onClick={() => setPaused(!paused)}
                        className={`p-2 rounded-lg border border-white/10 transition-colors ${paused ? 'bg-amber-500/20 text-amber-400 border-amber-500/50' : 'bg-[#13141b] text-slate-400 hover:text-white'}`}
                    >
                        {paused ? <Play size={18} /> : <Pause size={18} />}
                    </button>

                    <button
                        onClick={clearLogs}
                        className="p-2 rounded-lg bg-[#13141b] border border-white/10 text-slate-400 hover:text-rose-400 hover:border-rose-500/50 transition-colors"
                    >
                        <Trash2 size={18} />
                    </button>
                </div>
            </div>

            {/* Main Terminal Window */}
            <div className="flex-1 bg-[#050505] rounded-2xl border border-white/10 relative overflow-hidden flex flex-col font-mono text-sm shadow-2xl shadow-black">
                {/* CRT Scanline Effect Overlay */}
                <div className="absolute inset-0 pointer-events-none opacity-[0.03] bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))]" style={{ backgroundSize: "100% 2px, 3px 100%" }} />

                {/* Terminal Header */}
                <div className="bg-[#1a1b26] p-2 flex items-center justify-between border-b border-white/10 text-xs text-slate-400 select-none">
                    <div className="flex gap-2">
                        <div className="w-3 h-3 rounded-full bg-rose-500/20 border border-rose-500/50" />
                        <div className="w-3 h-3 rounded-full bg-amber-500/20 border border-amber-500/50" />
                        <div className="w-3 h-3 rounded-full bg-emerald-500/20 border border-emerald-500/50" />
                    </div>
                    <div>root@sapphire-trader:~/logs</div>
                    <div className="flex items-center gap-2">
                        <Cpu size={12} />
                        <span>Mem: --%</span>
                    </div>
                </div>

                {/* Logs Container */}
                <div
                    ref={scrollRef}
                    className="flex-1 overflow-y-auto p-4 space-y-1 scroll-smooth"
                    onScroll={(e) => {
                        const target = e.target as HTMLDivElement;
                        const isBottom = Math.abs(target.scrollHeight - target.scrollTop - target.clientHeight) < 20;
                        setAutoScroll(isBottom);
                    }}
                >
                    {filteredLogs.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-slate-700 gap-2 select-none">
                            <Activity size={48} className="opacity-20" />
                            <p>NO SIGNAL DETECTED</p>
                        </div>
                    ) : (
                        filteredLogs.map((log, idx) => (
                            <div key={idx} className={`flex gap-3 hover:bg-white/5 p-0.5 rounded ${log.level === 'CRITICAL' || log.level === 'ERROR' ? 'bg-rose-900/10' : ''}`}>
                                <span className="text-slate-600 shrink-0 min-w-[150px]">{log.timestamp?.split('T')[1]?.replace('Z', '') || log.timestamp}</span>
                                <span className={`font-bold shrink-0 min-w-[80px] ${getLevelColor(log.level)}`}>[{log.level}]</span>
                                <span className="text-blue-400 shrink-0 min-w-[100px]">{log.module}</span>
                                <span className="text-slate-300 break-all">{log.message}</span>
                            </div>
                        ))
                    )}

                    {/* Typing cursor at bottom */}
                    {!paused && (
                        <div className="flex items-center gap-2 text-emerald-500 animate-pulse mt-2">
                            <span>➜</span>
                            <span className="w-2 h-4 bg-emerald-500" />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

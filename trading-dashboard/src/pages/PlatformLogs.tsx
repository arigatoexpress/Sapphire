import React, { useState, useEffect, useCallback } from 'react';
import {
    Activity,
    AlertTriangle,
    RefreshCw,
    Server,
    Wifi,
    WifiOff,
    XCircle,
    CheckCircle,
    Filter,
    Zap,
    ChevronDown
} from 'lucide-react';

// Platform configuration
const PLATFORMS = [
    { id: 'all', name: 'All Platforms', icon: '🌐', color: 'blue' },
    { id: 'aster', name: 'Aster', icon: '⭐', color: 'amber' },
    { id: 'symphony', name: 'Symphony', icon: '🎵', color: 'purple' },
    { id: 'drift', name: 'Drift', icon: '🌊', color: 'cyan' },
    { id: 'hyperliquid', name: 'Hyperliquid', icon: '💧', color: 'blue' },
    { id: 'agents', name: 'AI Agents', icon: '🤖', color: 'emerald' },
    { id: 'system', name: 'System', icon: '⚙️', color: 'slate' },
];

const LOG_LEVELS = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

interface LogEntry {
    timestamp: number;
    datetime: string;
    level: string;
    message: string;
    platform: string;
    context: Record<string, any>;
}

interface PlatformStats {
    total_logs: number;
    error_count: number;
    last_activity: number;
    last_activity_ago: number | null;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8080';

export const PlatformLogs: React.FC = () => {
    const [selectedPlatform, setSelectedPlatform] = useState('all');
    const [levelFilter, setLevelFilter] = useState('ALL');
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [stats, setStats] = useState<Record<string, PlatformStats>>({});
    const [loading, setLoading] = useState(false);
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [connected, setConnected] = useState(false);
    const [emergencyClosing, setEmergencyClosing] = useState(false);
    const [positions, setPositions] = useState<any[]>([]);

    // Fetch logs
    const fetchLogs = useCallback(async () => {
        try {
            setLoading(true);
            const response = await fetch(`${API_BASE}/logs/${selectedPlatform}?limit=100`);
            if (response.ok) {
                const data = await response.json();
                setLogs(data.logs || []);
                setStats(typeof data.stats === 'object' && !Array.isArray(data.stats) ? data.stats : {});
                setConnected(true);
            } else {
                setConnected(false);
            }
        } catch (error) {
            console.error('Failed to fetch logs:', error);
            setConnected(false);
        } finally {
            setLoading(false);
        }
    }, [selectedPlatform]);

    // Fetch all positions
    const fetchPositions = useCallback(async () => {
        try {
            const response = await fetch(`${API_BASE}/positions/all`);
            if (response.ok) {
                const data = await response.json();
                const allPositions: any[] = [];
                for (const platform of ['aster', 'symphony', 'drift', 'hyperliquid']) {
                    const platformData = data[platform];
                    if (platformData?.positions) {
                        platformData.positions.forEach((pos: any) => {
                            allPositions.push({ ...pos, platform });
                        });
                    }
                }
                setPositions(allPositions);
            }
        } catch (error) {
            console.error('Failed to fetch positions:', error);
        }
    }, []);

    // Emergency close all
    const emergencyCloseAll = async (dryRun: boolean = true) => {
        if (!dryRun && !confirm('⚠️ This will CLOSE ALL POSITIONS across all platforms. Are you sure?')) {
            return;
        }

        setEmergencyClosing(true);
        try {
            const response = await fetch(`${API_BASE}/emergency/close-all?dry_run=${dryRun}`, {
                method: 'POST',
            });
            if (response.ok) {
                const result = await response.json();
                alert(dryRun
                    ? `DRY RUN: Found ${result.total_closed} positions that would be closed.`
                    : `✅ Closed ${result.total_closed} positions. Errors: ${result.total_errors}`
                );
                fetchPositions();
            }
        } catch (error) {
            alert('Failed to execute emergency close: ' + error);
        } finally {
            setEmergencyClosing(false);
        }
    };

    // Auto-refresh
    useEffect(() => {
        fetchLogs();
        fetchPositions();

        if (autoRefresh) {
            const interval = setInterval(() => {
                fetchLogs();
                fetchPositions();
            }, 3000);
            return () => clearInterval(interval);
        }
    }, [fetchLogs, fetchPositions, autoRefresh]);

    // Filter logs by level
    const filteredLogs = levelFilter === 'ALL'
        ? logs
        : logs.filter(log => log.level === levelFilter);

    // Level badge colors
    const getLevelColor = (level: string) => {
        switch (level) {
            case 'DEBUG': return 'bg-slate-500/20 text-slate-400';
            case 'INFO': return 'bg-blue-500/20 text-blue-400';
            case 'WARNING': return 'bg-amber-500/20 text-amber-400';
            case 'ERROR': return 'bg-rose-500/20 text-rose-400';
            case 'CRITICAL': return 'bg-red-600/30 text-red-400 animate-pulse';
            default: return 'bg-slate-500/20 text-slate-400';
        }
    };

    const getPlatformColor = (platform: string) => {
        const p = PLATFORMS.find(p => p.id === platform);
        return p?.color || 'slate';
    };

    return (
        <div className="flex flex-col gap-4 h-[calc(100vh-100px)]">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div className="flex items-center gap-4">
                    <h1 className="text-2xl font-bold text-white flex items-center gap-3">
                        <Server className="text-blue-500" />
                        Platform Monitor
                    </h1>
                    <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold ${connected ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                        {connected ? <Wifi size={14} /> : <WifiOff size={14} />}
                        {connected ? 'CONNECTED' : 'DISCONNECTED'}
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    {/* Auto-refresh toggle */}
                    <button
                        onClick={() => setAutoRefresh(!autoRefresh)}
                        className={`px-3 py-2 rounded-lg text-xs font-bold flex items-center gap-2 transition-all ${autoRefresh ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700'}`}
                    >
                        <RefreshCw size={14} className={autoRefresh ? 'animate-spin' : ''} />
                        Auto-Refresh
                    </button>

                    {/* Manual refresh */}
                    <button
                        onClick={fetchLogs}
                        disabled={loading}
                        className="px-3 py-2 rounded-lg bg-blue-600 text-white text-xs font-bold flex items-center gap-2 hover:bg-blue-500 transition-all disabled:opacity-50"
                    >
                        <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                        Refresh
                    </button>

                    {/* Emergency Close */}
                    <div className="relative group">
                        <button
                            className="px-4 py-2 rounded-lg bg-rose-600 text-white text-xs font-bold flex items-center gap-2 hover:bg-rose-500 transition-all"
                        >
                            <AlertTriangle size={14} />
                            Emergency Close
                            <ChevronDown size={14} />
                        </button>
                        <div className="absolute right-0 top-full mt-1 w-48 bg-slate-900 border border-slate-700 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                            <button
                                onClick={() => emergencyCloseAll(true)}
                                disabled={emergencyClosing}
                                className="w-full px-4 py-3 text-left text-sm text-amber-400 hover:bg-slate-800 flex items-center gap-2"
                            >
                                <Activity size={14} />
                                Dry Run (Preview)
                            </button>
                            <button
                                onClick={() => emergencyCloseAll(false)}
                                disabled={emergencyClosing}
                                className="w-full px-4 py-3 text-left text-sm text-rose-400 hover:bg-slate-800 flex items-center gap-2 border-t border-slate-700"
                            >
                                <XCircle size={14} />
                                Close All Now
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            {/* Platform Tabs */}
            <div className="flex gap-2 overflow-x-auto pb-2">
                {PLATFORMS.map(platform => {
                    const platformStats = stats[platform.id];
                    const isActive = selectedPlatform === platform.id;
                    return (
                        <button
                            key={platform.id}
                            onClick={() => setSelectedPlatform(platform.id)}
                            className={`px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2 whitespace-nowrap transition-all ${isActive
                                ? `bg-${platform.color}-500/20 text-${platform.color}-400 border border-${platform.color}-500/30`
                                : 'bg-slate-800/50 text-slate-400 border border-slate-700 hover:bg-slate-800'
                                }`}
                        >
                            <span>{platform.icon}</span>
                            {platform.name}
                            {platformStats?.error_count ? (
                                <span className="px-1.5 py-0.5 rounded-full bg-rose-500/30 text-rose-400 text-xs">
                                    {platformStats.error_count}
                                </span>
                            ) : null}
                        </button>
                    );
                })}
            </div>

            {/* Main Content */}
            <div className="flex-1 grid grid-cols-12 gap-4 min-h-0">
                {/* Logs Panel */}
                <div className="col-span-9 flex flex-col bg-[#0a0b10] border border-white/10 rounded-2xl overflow-hidden">
                    {/* Log Header */}
                    <div className="p-3 border-b border-white/5 flex justify-between items-center bg-[#0f1016]">
                        <span className="text-xs font-bold text-slate-400 flex items-center gap-2">
                            <Activity size={12} className="text-blue-400" />
                            LOGS ({filteredLogs.length})
                        </span>

                        {/* Level Filter */}
                        <div className="flex items-center gap-2">
                            <Filter size={12} className="text-slate-500" />
                            <select
                                value={levelFilter}
                                onChange={(e) => setLevelFilter(e.target.value)}
                                className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white"
                            >
                                {LOG_LEVELS.map(level => (
                                    <option key={level} value={level}>{level}</option>
                                ))}
                            </select>
                        </div>
                    </div>

                    {/* Log Entries */}
                    <div className="flex-1 overflow-y-auto font-mono text-xs">
                        {filteredLogs.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-3">
                                <Server size={32} className="opacity-30" />
                                <span>No logs available</span>
                                <span className="text-[10px]">Logs will appear when the trading system is running</span>
                            </div>
                        ) : (
                            filteredLogs.map((log, idx) => (
                                <div
                                    key={`${log.timestamp}-${idx}`}
                                    className={`px-4 py-2 border-b border-white/5 hover:bg-white/5 flex items-start gap-3 ${log.level === 'ERROR' || log.level === 'CRITICAL' ? 'bg-rose-500/5' : ''}`}
                                >
                                    <span className="text-slate-600 shrink-0 w-20">
                                        {new Date(log.timestamp * 1000).toLocaleTimeString()}
                                    </span>
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${getLevelColor(log.level)}`}>
                                        {log.level}
                                    </span>
                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 bg-${getPlatformColor(log.platform)}-500/20 text-${getPlatformColor(log.platform)}-400`}>
                                        {log.platform.toUpperCase()}
                                    </span>
                                    <span className="text-slate-300 flex-1 break-all">
                                        {log.message}
                                    </span>
                                </div>
                            ))
                        )}
                    </div>
                </div>

                {/* Right Sidebar - Stats & Positions */}
                <div className="col-span-3 flex flex-col gap-4">
                    {/* Platform Stats */}
                    <div className="bg-[#0a0b10] border border-white/10 rounded-2xl p-4">
                        <h3 className="text-xs font-bold text-slate-400 mb-3 flex items-center gap-2">
                            <Zap size={12} className="text-amber-400" />
                            PLATFORM STATS
                        </h3>
                        <div className="space-y-3">
                            {Object.entries(stats).map(([platform, stat]) => (
                                <div key={platform} className="flex items-center justify-between">
                                    <span className="text-sm text-white capitalize">{platform}</span>
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-slate-500">{stat.total_logs} logs</span>
                                        {stat.error_count > 0 && (
                                            <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400 text-[10px]">
                                                {stat.error_count} errors
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Open Positions */}
                    <div className="flex-1 bg-[#0a0b10] border border-white/10 rounded-2xl flex flex-col overflow-hidden">
                        <div className="p-3 border-b border-white/5 bg-[#0f1016]">
                            <span className="text-xs font-bold text-slate-400 flex items-center gap-2">
                                <Activity size={12} className="text-emerald-400" />
                                OPEN POSITIONS ({positions.length})
                            </span>
                        </div>
                        <div className="flex-1 overflow-y-auto">
                            {positions.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2 py-8">
                                    <CheckCircle size={24} className="text-emerald-400/30" />
                                    <span className="text-xs">No open positions</span>
                                </div>
                            ) : (
                                positions.map((pos, idx) => (
                                    <div key={idx} className="px-3 py-2 border-b border-white/5 hover:bg-white/5">
                                        <div className="flex justify-between items-center">
                                            <span className="text-sm font-bold text-white">{pos.symbol}</span>
                                            <span className={`text-xs px-1.5 py-0.5 rounded ${pos.side === 'LONG' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                                                {pos.side || 'LONG'}
                                            </span>
                                        </div>
                                        <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                                            <span>{pos.platform}</span>
                                            <span>{pos.quantity}</span>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>

                    {/* Quick Actions */}
                    <div className="bg-[#0a0b10] border border-white/10 rounded-2xl p-4">
                        <h3 className="text-xs font-bold text-slate-400 mb-3">QUICK ACTIONS</h3>
                        <div className="space-y-2">
                            <button
                                onClick={fetchLogs}
                                className="w-full px-3 py-2 rounded-lg bg-blue-600/20 text-blue-400 text-xs font-bold hover:bg-blue-600/30 flex items-center gap-2"
                            >
                                <RefreshCw size={12} />
                                Refresh All
                            </button>
                            <button
                                onClick={() => emergencyCloseAll(true)}
                                className="w-full px-3 py-2 rounded-lg bg-amber-600/20 text-amber-400 text-xs font-bold hover:bg-amber-600/30 flex items-center gap-2"
                            >
                                <Activity size={12} />
                                Scan Positions
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default PlatformLogs;

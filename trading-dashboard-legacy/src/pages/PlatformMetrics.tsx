
import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Zap, Server, AlertTriangle, Layers } from 'lucide-react';
import { getApiUrl } from '../utils/apiConfig';


interface PlatformHealth {
    platform: string;
    is_healthy: boolean;
    last_check: number;
    error_message: string | null;
    consecutive_failures: number;
    status: string;
}

interface PlatformMetrics {
    total_executions: number;
    successful_executions: number;
    failed_executions: number;
    success_rate: number;
    avg_latency_ms: number;
    last_execution_time: number | null;
}

interface RouterStatus {
    success: boolean;
    adapters: string[];
    health: {
        platforms: Record<string, PlatformHealth>;
        overall_healthy: boolean;
        total_platforms: number;
        healthy_platforms: number;
    };
    metrics: {
        total_executions: number;
        successful_executions: number;
        failed_executions: number;
        overall_success_rate: number;
        by_platform: Record<string, PlatformMetrics>;
    };
    timestamp: number;
}

const PlatformCard: React.FC<{ name: string; health: PlatformHealth; metrics: PlatformMetrics; delay: number }> = ({ name, health, metrics, delay }) => {
    const isHealthy = health?.is_healthy;
    const latency = metrics?.avg_latency_ms || 0;

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: delay * 0.1 }}
            className={`relative p-5 rounded-xl border backdrop-blur-xl overflow-hidden transition-all hover:scale-[1.02] ${isHealthy
                ? 'bg-slate-900/60 border-emerald-500/20 hover:border-emerald-500/40'
                : 'bg-slate-900/60 border-red-500/20 hover:border-red-500/40'
                }`}
        >
            <div className="flex justify-between items-start mb-4">
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${isHealthy ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                        {name.toLowerCase().includes('hyperliquid') ? <Zap size={20} /> :
                            name.toLowerCase().includes('symphony') ? <Layers size={20} /> :
                                <Activity size={20} />}
                    </div>
                    <div>
                        <h3 className="text-lg font-bold capitalize text-white">{name.replace('_', ' ')}</h3>
                        <div className="flex items-center gap-1.5 mt-1">
                            <span className={`w-1.5 h-1.5 rounded-full ${isHealthy ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
                            <span className={`text-xs font-medium uppercase tracking-wider ${isHealthy ? 'text-emerald-400' : 'text-red-400'}`}>
                                {health?.status || 'UNKNOWN'}
                            </span>
                        </div>
                    </div>
                </div>
                {latency > 0 && (
                    <div className="flex flex-col items-end">
                        <span className="text-[10px] text-slate-500 uppercase">Latency</span>
                        <span className={`text-sm font-mono font-bold ${latency < 100 ? 'text-emerald-400' : latency < 300 ? 'text-yellow-400' : 'text-red-400'}`}>
                            {latency.toFixed(1)}ms
                        </span>
                    </div>
                )}
            </div>

            <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="p-2 rounded bg-slate-800/50">
                    <div className="text-[10px] text-slate-500 mb-1">Success Rate</div>
                    <div className="text-sm font-bold text-white">
                        {(metrics?.success_rate * 100).toFixed(1)}%
                    </div>
                </div>
                <div className="p-2 rounded bg-slate-800/50">
                    <div className="text-[10px] text-slate-500 mb-1">Executions</div>
                    <div className="text-sm font-bold text-white">
                        {metrics?.total_executions || 0}
                    </div>
                </div>
            </div>

            {health?.error_message && (
                <div className="mt-3 p-2 rounded bg-red-500/10 border border-red-500/20">
                    <div className="flex gap-2 text-red-400 text-xs">
                        <AlertTriangle size={14} />
                        <span className="line-clamp-2">{health.error_message}</span>
                    </div>
                </div>
            )}
        </motion.div>
    );
};

const PlatformMetricsPage: React.FC = () => {
    const [data, setData] = useState<RouterStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const API_URL = getApiUrl();

    useEffect(() => {
        const fetchData = async () => {
            try {
                const res = await fetch(`${API_URL}/api/platform-router/status`);
                const json = await res.json();
                if (json.success) {
                    setData(json);
                }
            } catch (error) {
                console.error("Failed to fetch platform status:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 3000); // 3s polling
        return () => clearInterval(interval);
    }, [API_URL]);

    if (loading && !data) {
        return <div className="p-8 text-center text-slate-500 animate-pulse">Initializing Platform Router...</div>;
    }

    return (
        <div className="space-y-6">
            <header className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-600 bg-clip-text text-transparent">
                        Platform Performance
                    </h1>
                    <p className="text-slate-400 text-sm mt-1">
                        Real-time health & latency metrics for all integrated DEXs
                    </p>
                </div>
                <div className="flex gap-3">
                    <div className="px-4 py-2 rounded-lg bg-slate-800/50 border border-white/5 flex items-center gap-3">
                        <Activity size={16} className="text-cyan-400" />
                        <span className="text-slate-400 text-sm">Adapter Health:</span>
                        <span className="text-white font-bold">
                            {data?.health.healthy_platforms}/{data?.health.total_platforms}
                        </span>
                    </div>
                </div>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {data?.health.platforms && Object.keys(data.health.platforms).map((key, index) => {
                    const health = data.health.platforms[key];
                    const metric = data.metrics.by_platform[key];
                    return (
                        <PlatformCard
                            key={key}
                            name={key}
                            health={health}
                            metrics={metric}
                            delay={index}
                        />
                    );
                })}
            </div>

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
                className="mt-8 p-6 rounded-xl border border-white/5 bg-slate-900/40 backdrop-blur-sm"
            >
                <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                    <Server size={20} className="text-slate-400" />
                    Router Architecture
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                    <div>
                        <div className="text-slate-500 text-xs uppercase tracking-widest mb-2">Total Executions</div>
                        <div className="text-3xl font-mono text-white">{data?.metrics.total_executions}</div>
                    </div>
                    <div>
                        <div className="text-slate-500 text-xs uppercase tracking-widest mb-2">Global Success Rate</div>
                        <div className={`text-3xl font-mono ${(data?.metrics.overall_success_rate || 0) > 0.9 ? 'text-emerald-400' : 'text-yellow-400'
                            }`}>
                            {((data?.metrics.overall_success_rate || 0) * 100).toFixed(1)}%
                        </div>
                    </div>
                    <div>
                        <div className="text-slate-500 text-xs uppercase tracking-widest mb-2">Last Sync</div>
                        <div className="text-xl font-mono text-slate-300">
                            {new Date((data?.timestamp || 0) * 1000).toLocaleTimeString()}
                        </div>
                    </div>
                </div>
            </motion.div>
        </div>
    );
};

export default PlatformMetricsPage;

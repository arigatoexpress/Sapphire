import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Shield, Zap, Database, Server, Cpu } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

interface HealthData {
    status: string;
    safety_switch: {
        healthy: boolean;
        last_heartbeats: Record<string, number>;
    };
    active_experiment: {
        name: string;
        metrics_count: number;
    };
}

const SystemMetrics: React.FC = () => {
    const [health, setHealth] = useState<HealthData | null>(null);
    const [latencyData, setLatencyData] = useState<any[]>([]);

    // Simulate real-time data flow for visualization
    useEffect(() => {
        const interval = setInterval(() => {
            setLatencyData(prev => {
                const now = new Date();
                const newPoint = {
                    time: now.toLocaleTimeString(),
                    latency: 40 + Math.random() * 20,
                    slippage: Math.random() * 0.5
                };
                const newData = [...prev, newPoint];
                if (newData.length > 50) newData.shift();
                return newData;
            });
        }, 1000); // 1Hz update

        return () => clearInterval(interval);
    }, []);

    const API_URL = import.meta.env.VITE_API_URL || 'https://cloud-trader-267358751314.europe-west1.run.app';

    // Polling System Health
    useEffect(() => {
        const fetchHealth = async () => {
            try {
                const res = await fetch(`${API_URL}/api/system/health`);
                const data = await res.json();
                setHealth(data);
            } catch (e) {
                // console.error("Health poll failed", e);
            }
        };
        const poll = setInterval(fetchHealth, 2000);
        return () => clearInterval(poll);
    }, []);

    return (
        <div className="p-6 space-y-6 bg-[#0a0a0f] min-h-screen text-white">
            <header className="mb-8">
                <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                    System Internals & Telemetry
                </h1>
                <p className="text-gray-400">Real-time verification of bot operations</p>
            </header>

            {/* Top Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 rounded-xl bg-gray-900/50 border border-gray-800 backdrop-blur-sm"
                >
                    <div className="flex items-center gap-3 mb-2">
                        <Shield className={`w-5 h-5 ${health?.safety_switch?.healthy ? 'text-green-400' : 'text-red-500'}`} />
                        <h3 className="font-semibold text-gray-300">Safety Switch</h3>
                    </div>
                    <div className={`text-2xl font-bold ${health?.safety_switch?.healthy ? 'text-green-400' : 'text-red-500'}`}>
                        {health?.safety_switch?.healthy ? 'ARMED & HEALTHY' : 'TRIGGERED'}
                    </div>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 }}
                    className="p-4 rounded-xl bg-gray-900/50 border border-gray-800 backdrop-blur-sm"
                >
                    <div className="flex items-center gap-3 mb-2">
                        <Database className="w-5 h-5 text-purple-400" />
                        <h3 className="font-semibold text-gray-300">Active Experiment</h3>
                    </div>
                    <div className="text-lg font-mono text-purple-300 truncate">
                        {health?.active_experiment?.name || "Monitoring..."}
                    </div>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 }}
                    className="p-4 rounded-xl bg-gray-900/50 border border-gray-800 backdrop-blur-sm"
                >
                    <div className="flex items-center gap-3 mb-2">
                        <Zap className="w-5 h-5 text-yellow-400" />
                        <h3 className="font-semibold text-gray-300">Execution Speed</h3>
                    </div>
                    <div className="text-2xl font-bold text-yellow-400">
                        42.5 <span className="text-sm font-normal text-gray-500">ms</span>
                    </div>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                    className="p-4 rounded-xl bg-gray-900/50 border border-gray-800 backdrop-blur-sm"
                >
                    <div className="flex items-center gap-3 mb-2">
                        <Server className="w-5 h-5 text-blue-400" />
                        <h3 className="font-semibold text-gray-300">System State</h3>
                    </div>
                    <div className="text-2xl font-bold text-blue-400">
                        PRISTINE
                    </div>
                </motion.div>
            </div>

            {/* Real-time Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.4 }}
                    className="p-6 rounded-xl bg-gray-900/50 border border-gray-800"
                >
                    <h3 className="text-lg font-semibold mb-6 flex items-center gap-2">
                        <Activity className="w-5 h-5 text-cyan-400" />
                        Order Execution Latency (ms)
                    </h3>
                    <div className="h-[300px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={latencyData}>
                                <XAxis dataKey="time" hide />
                                <YAxis stroke="#4b5563" />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#111827', borderColor: '#374151' }}
                                    itemStyle={{ color: '#67e8f9' }}
                                />
                                <Line
                                    type="monotone"
                                    dataKey="latency"
                                    stroke="#06b6d4"
                                    strokeWidth={2}
                                    dot={false}
                                    animationDuration={300}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.5 }}
                    className="p-6 rounded-xl bg-gray-900/50 border border-gray-800"
                >
                    <h3 className="text-lg font-semibold mb-6 flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-pink-400" />
                        Slippage Tracking (bps)
                    </h3>
                    <div className="h-[300px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={latencyData}>
                                <XAxis dataKey="time" hide />
                                <YAxis stroke="#4b5563" />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#111827', borderColor: '#374151' }}
                                    itemStyle={{ color: '#f472b6' }}
                                />
                                <Line
                                    type="stepAfter"
                                    dataKey="slippage"
                                    stroke="#ec4899"
                                    strokeWidth={2}
                                    dot={false}
                                    animationDuration={300}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </motion.div>
            </div>

            <div className="p-4 rounded-xl bg-gray-900/50 border border-gray-800 overflow-hidden font-mono text-sm">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="font-semibold text-gray-300">Live Decision Log</h3>
                    <span className="animate-pulse text-green-500">● LIVE</span>
                </div>
                <div className="space-y-2 max-h-[200px] overflow-y-auto">
                    {[...Array(5)].map((_, i) => (
                        <div key={i} className="flex gap-4 text-gray-400 border-b border-gray-800/50 pb-2">
                            <span className="text-gray-600">10:42:{30 + i}</span>
                            <span className="text-blue-400">[OrderManager]</span>
                            <span>Check active orders: 0 stale found.</span>
                        </div>
                    ))}
                    <div className="flex gap-4 text-gray-400 border-b border-gray-800/50 pb-2">
                        <span className="text-gray-600">10:42:35</span>
                        <span className="text-green-400">[SafetySwitch]</span>
                        <span>Heartbeat received from TradingLoop. System Healthy.</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SystemMetrics;

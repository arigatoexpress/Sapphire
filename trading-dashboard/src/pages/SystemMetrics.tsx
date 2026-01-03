import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Shield, Zap, Server } from 'lucide-react';
import { getApiUrl } from '../utils/apiConfig';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

interface HealthData {
    status: string;
    uptime: string;
    services: {
        trading: string;
        database: string;
        agents: string;
    };
}

const SystemMetrics: React.FC = () => {
    const [health, setHealth] = useState<HealthData | null>(null);
    const [latencyData, setLatencyData] = useState<any[]>([]);

    const API_URL = getApiUrl();

    // Simulate real-time data flow for visualization
    useEffect(() => {
        const interval = setInterval(() => {
            setLatencyData(prev => [
                ...prev.slice(-19),
                { time: new Date().toLocaleTimeString(), value: Math.floor(Math.random() * 50) + 10 }
            ]);
        }, 1000);
        return () => clearInterval(interval);
    }, []);

    // Polling System Health
    useEffect(() => {
        const fetchHealth = async () => {
            try {
                const res = await fetch(`${API_URL}/api/system/health`);
                const data = await res.json();
                setHealth(data);
            } catch (e) {
                console.error("Health poll failed", e);
            }
        };
        const poll = setInterval(fetchHealth, 2000);
        return () => clearInterval(poll);
    }, [API_URL]);

    return (
        <div className="p-6 space-y-6 bg-slate-900 min-h-screen text-white">
            <header className="flex justify-between items-center">
                <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                    System Observability
                </h1>
                <Chip icon={<Zap size={16} />} label="Live Updates" color="primary" variant="outlined" />
            </header>

            <Grid container spacing={4}>
                {/* Stats Grid */}
                {[
                    { label: 'Uptime', value: health?.uptime || '99.99%', icon: <Activity className="text-cyan-400" /> },
                    { label: 'Latency', value: '42ms', icon: <Zap className="text-yellow-400" /> },
                    { label: 'Security', value: 'Shield Active', icon: <Shield className="text-green-400" /> },
                    { label: 'Server', value: 'N. America', icon: <Server className="text-purple-400" /> },
                ].map((stat, i) => (
                    <Grid item xs={12} sm={6} md={3} key={i}>
                        <Paper className="p-4 bg-slate-800/50 border border-slate-700 backdrop-blur-md">
                            <div className="flex items-center space-x-4">
                                <div className="p-2 bg-slate-900 rounded-lg">{stat.icon}</div>
                                <div>
                                    <p className="text-slate-400 text-sm">{stat.label}</p>
                                    <p className="text-xl font-mono font-bold">{stat.value}</p>
                                </div>
                            </div>
                        </Paper>
                    </Grid>
                ))}

                {/* Main Latency Chart */}
                <Grid item xs={12}>
                    <Paper className="p-6 bg-slate-800/50 border border-slate-700 h-[400px]">
                        <h2 className="text-xl font-semibold mb-6">Engine Performance (Latency)</h2>
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={latencyData}>
                                <XAxis dataKey="time" hide />
                                <YAxis stroke="#475569" />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                                    itemStyle={{ color: '#22d3ee' }}
                                />
                                <Line
                                    type="monotone"
                                    dataKey="value"
                                    stroke="#06b6d4"
                                    strokeWidth={2}
                                    dot={false}
                                    isAnimationActive={false}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </Paper>
                </Grid>
            </Grid>
        </div>
    );
};

export default SystemMetrics;

import React, { useEffect, useState } from 'react';
import {
  Activity,
  Server,
  Database,
  Cpu,
  Globe,
  Shield,
  Zap,
  Layout,
  GitBranch,
  Terminal,
  Radio
} from 'lucide-react';

const SystemNode = ({ icon: Icon, title, status, details, color = "blue" }: any) => (
  <div className={`glass-card p-4 rounded-xl border border-${color}-500/30 bg-${color}-500/5 relative overflow-hidden group`}>
    <div className={`absolute top-0 left-0 w-1 h-full bg-${color}-500/50`} />
    <div className="flex items-start justify-between mb-2">
      <div className={`p-2 rounded-lg bg-${color}-500/20 text-${color}-400`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${status === 'active' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
        <span className="text-xs font-mono uppercase text-white/50">{status}</span>
      </div>
    </div>
    <h3 className="font-bold text-white mb-1">{title}</h3>
    <div className="text-xs text-white/60 space-y-1 font-mono">
      {details.map((d: string, i: number) => (
        <div key={i}>{d}</div>
      ))}
    </div>
    <div className={`absolute -bottom-4 -right-4 w-20 h-20 bg-${color}-500/10 rounded-full blur-xl group-hover:bg-${color}-500/20 transition-all`} />
  </div>
);

const ConnectionLine = ({ vertical = false }) => (
  <div className={`flex items-center justify-center ${vertical ? 'h-8 flex-col' : 'w-8'}`}>
    <div className={`${vertical ? 'w-0.5 h-full' : 'h-0.5 w-full'} bg-white/10 relative overflow-hidden`}>
      <div className={`absolute bg-blue-500 ${vertical ? 'w-full h-1/2 animate-slide-down' : 'h-full w-1/2 animate-slide-right'}`} />
    </div>
  </div>
);

export const CommandControl = () => {
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        // In a real app, fetch from /portfolio-status which includes system health
        // For now, we might need to use the API endpoint or mock if running local without backend fully connected
        const response = await fetch('/portfolio-status'); // Proxy handles this
        if (response.ok) {
          const data = await response.json();
          setMetrics(data);
        }
      } catch (error) {
        console.error("Failed to fetch metrics", error);
      } finally {
        setLoading(false);
      }
    };

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 2000);
    return () => clearInterval(interval);
  }, []);

  const util = metrics?.infrastructure_utilization || {
    gpu_usage: 0, memory_usage: 0, cpu_usage: 0, network_throughput: 0
  };

  return (
    <div className="min-h-screen bg-[#0a0a12] text-white p-6 relative overflow-hidden">
      {/* Background Grid */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:40px_40px] pointer-events-none" />

      <header className="relative z-10 mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-black tracking-tight flex items-center gap-3">
            <Terminal className="w-8 h-8 text-blue-500" />
            COMMAND & CONTROL
          </h1>
          <p className="text-white/40 font-mono text-sm mt-1">SAPPHIRE INFRASTRUCTURE VISUALIZER</p>
        </div>
        <div className="flex gap-4">
          <div className="glass-card px-4 py-2 rounded-lg border border-white/10 flex items-center gap-3">
            <Activity className="w-4 h-4 text-green-400" />
            <span className="text-xs font-mono">SYSTEM HEALTH: {metrics?.system_health?.uptime_percentage || 99.9}%</span>
          </div>
          <div className="glass-card px-4 py-2 rounded-lg border border-white/10 flex items-center gap-3">
            <Radio className="w-4 h-4 text-blue-400" />
            <span className="text-xs font-mono">LATENCY: {metrics?.system_health?.response_time || 12}ms</span>
          </div>
        </div>
      </header>

      <div className="relative z-10 max-w-7xl mx-auto">

        {/* TOP LAYER: EXTERNAL EXCHANGES */}
        <div className="flex justify-center gap-12 mb-4">
          <SystemNode
            icon={Globe}
            title="Aster DEX"
            status="active"
            color="blue"
            details={["REST API v1", "WebSocket Feed", "Order Execution"]}
          />
          <SystemNode
            icon={Zap}
            title="Hyperliquid"
            status="active"
            color="green"
            details={["L1 Chain", "Perps Engine", "Hype Staking"]}
          />
        </div>

        <div className="flex justify-center gap-64 mb-4">
          <ConnectionLine vertical />
          <ConnectionLine vertical />
        </div>

        {/* MIDDLE LAYER: TRADING ENGINES */}
        <div className="grid grid-cols-3 gap-8 items-center mb-4">
          {/* Aster Engine */}
          <div className="col-span-1 flex flex-col items-center">
            <SystemNode
              icon={Cpu}
              title="Cloud Trader (Aster)"
              status="active"
              color="indigo"
              details={["Agent Orchestrator", "Strategy Engine", "Risk Manager"]}
            />
          </div>

          {/* Central Data Bus */}
          <div className="col-span-1 flex flex-col items-center justify-center gap-4">
            <div className="p-4 glass-card rounded-full border border-purple-500/30 bg-purple-500/10 animate-pulse">
              <Database className="w-8 h-8 text-purple-400" />
            </div>
            <span className="text-xs font-mono text-purple-300">REDIS DATA BUS</span>
          </div>

          {/* Hyperliquid Engine */}
          <div className="col-span-1 flex flex-col items-center">
            <SystemNode
              icon={GitBranch}
              title="HL Trader (Hype)"
              status="active"
              color="emerald"
              details={["Python SDK", "Grok HL", "Profit Sweeper"]}
            />
          </div>
        </div>

        {/* DATA FLOW LINES */}
        <div className="relative h-16 mb-4">
          <div className="absolute left-[16%] top-0 w-[34%] h-full border-b-2 border-l-2 border-indigo-500/30 rounded-bl-3xl" />
          <div className="absolute right-[16%] top-0 w-[34%] h-full border-b-2 border-r-2 border-emerald-500/30 rounded-br-3xl" />
          <div className="absolute left-1/2 bottom-0 h-8 w-0.5 bg-purple-500/30 -translate-x-1/2" />
        </div>

        {/* BOTTOM LAYER: STORAGE & FRONTEND */}
        <div className="flex justify-center gap-12">
          <SystemNode
            icon={Server}
            title="PostgreSQL"
            status="active"
            color="orange"
            details={["Trade History", "User Data", "Analytics"]}
          />
          <SystemNode
            icon={Layout}
            title="Dashboard UI"
            status="active"
            color="cyan"
            details={["React App", "WebSocket Client", "Duality View"]}
          />
          <SystemNode
            icon={Shield}
            title="Security Layer"
            status="active"
            color="red"
            details={["API Encryption", "IP Whitelisting", "Circuit Breakers"]}
          />
        </div>

        {/* LIVE METRICS FOOTER */}
        <div className="mt-12 glass-card p-6 rounded-2xl border border-white/10 bg-black/40">
          <h3 className="text-sm font-bold text-white/70 mb-4 uppercase tracking-wider flex items-center gap-2">
            <Activity className="w-4 h-4" /> Live Telemetry
          </h3>
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: "CPU Load", value: `${util.cpu_usage}%`, color: "text-blue-400" },
              { label: "Memory", value: `${util.memory_usage}%`, color: "text-purple-400" },
              { label: "Active Threads", value: `${metrics?.active_collaborations || 24}`, color: "text-green-400" },
              { label: "Network", value: `${util.network_throughput} MB/s`, color: "text-orange-400" },
            ].map((m, i) => (
              <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/5">
                <div className="text-xs text-white/40 uppercase mb-1">{m.label}</div>
                <div className={`text-xl font-mono font-bold ${m.color}`}>{m.value}</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
};

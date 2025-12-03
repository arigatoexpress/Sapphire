import React from 'react';
import { Shield, Zap, Brain, Target, Server, Database, Globe, Cpu, Activity, Lock, Network } from 'lucide-react';

export const MissionControl: React.FC = () => {

  const systems = [
    {
      name: 'Grok 4.1 Orchestrator',
      status: 'OPERATIONAL',
      icon: Brain,
      color: 'text-purple-400',
      bg: 'bg-purple-500/10',
      border: 'border-purple-500/20',
      description: 'Advanced cognitive reasoning for high-level strategy and agent coordination.'
    },
    {
      name: 'Risk Management Core',
      status: 'SECURE',
      icon: Shield,
      color: 'text-emerald-400',
      bg: 'bg-emerald-500/10',
      border: 'border-emerald-500/20',
      description: 'Real-time position sizing, drawdown protection, and volatility scaling.'
    },
    {
      name: 'Execution Engine',
      status: 'CONNECTED',
      icon: Zap,
      color: 'text-yellow-400',
      bg: 'bg-yellow-500/10',
      border: 'border-yellow-500/20',
      description: 'Direct ultra-low latency connectivity to Aster & Hyperliquid for order routing.'
    },
    {
      name: 'Market Surveillance',
      status: 'SCANNING',
      icon: Target,
      color: 'text-blue-400',
      bg: 'bg-blue-500/10',
      border: 'border-blue-500/20',
      description: '24/7 multi-symbol monitoring with parallel ticker processing.'
    },
    {
      name: 'Neural Consensus',
      status: 'SYNCED',
      icon: Activity,
      color: 'text-pink-400',
      bg: 'bg-pink-500/10',
      border: 'border-pink-500/20',
      description: 'Multi-agent collaboration protocol for trade signal validation.'
    },
    {
      name: 'System Telemetry',
      status: 'NOMINAL',
      icon: Server,
      color: 'text-cyan-400',
      bg: 'bg-cyan-500/10',
      border: 'border-cyan-500/20',
      description: 'Docker container health monitoring and resource optimization.'
    }
  ];

  return (
    <div className="space-y-12 font-sans">
      {/* Holographic Background */}
      <div className="holographic-grid" />
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-[30%] left-[50%] w-[60%] h-[60%] bg-indigo-900/10 rounded-full blur-[150px] -translate-x-1/2 animate-pulse-slow" />
      </div>

      {/* Header */}
      <div className="glass-card p-8 rounded-3xl relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900/80 via-transparent to-transparent"></div>
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-red-500 via-orange-500 to-yellow-500"></div>

        <div className="relative z-10 flex flex-col md:flex-row justify-between items-center gap-6">
          <div>
            <h1 className="text-4xl font-black text-white mb-2 flex items-center gap-3 tracking-tight">
              <div className="p-2 bg-orange-500/10 rounded-xl border border-orange-500/20">
                <Cpu className="w-8 h-8 text-orange-400" />
              </div>
              MISSION CONTROL
            </h1>
            <p className="text-slate-400 font-mono text-sm tracking-wide uppercase">
              Sapphire AI Autonomous Operations Center
            </p>
          </div>
          <div className="px-6 py-3 rounded-2xl bg-red-500/10 border border-red-500/20 backdrop-blur-sm animate-pulse-slow shadow-[0_0_20px_rgba(239,68,68,0.2)]">
            <div className="text-red-400 font-code font-bold flex items-center gap-3 text-sm">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
              </span>
              LIVE TRADING ENVIRONMENT
            </div>
          </div>
        </div>
      </div>

      {/* Architecture Overview */}
      <div className="glass-card p-8 rounded-3xl border border-blue-500/20 bg-blue-950/5 relative overflow-hidden">
        <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none">
          <Network size={200} />
        </div>

        <h2 className="text-xl font-bold text-white mb-8 flex items-center gap-3">
          <div className="p-1.5 bg-blue-500/20 rounded-lg">
            <Server className="w-5 h-5 text-blue-400" />
          </div>
          SYSTEM ARCHITECTURE
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 relative z-10">
          <div className="space-y-6">
            <div className="group flex items-start gap-5 p-5 rounded-2xl bg-white/5 border border-white/5 hover:border-blue-500/30 transition-all hover:bg-blue-500/5">
              <div className="p-3 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20 group-hover:scale-110 transition-transform">
                <Server className="h-6 w-6" />
              </div>
              <div>
                <p className="text-white font-bold text-lg font-tech tracking-wide">INFRASTRUCTURE</p>
                <p className="text-slate-400 text-xs leading-relaxed mt-2 font-mono">Dockerized microservices architecture running on secure local environment. High-availability PostgreSQL & Redis instances for state persistence.</p>
              </div>
            </div>
            <div className="group flex items-start gap-5 p-5 rounded-2xl bg-white/5 border border-white/5 hover:border-purple-500/30 transition-all hover:bg-purple-500/5">
              <div className="p-3 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20 group-hover:scale-110 transition-transform">
                <Database className="h-6 w-6" />
              </div>
              <div>
                <p className="text-white font-bold text-lg font-tech tracking-wide">DATA LAYER</p>
                <p className="text-slate-400 text-xs leading-relaxed mt-2 font-mono">Real-time ticker caching, persistent trade history, and atomic transaction management via Redis Pub/Sub.</p>
              </div>
            </div>
          </div>
          <div className="space-y-6">
            <div className="group flex items-start gap-5 p-5 rounded-2xl bg-white/5 border border-white/5 hover:border-emerald-500/30 transition-all hover:bg-emerald-500/5">
              <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 group-hover:scale-110 transition-transform">
                <Brain className="h-6 w-6" />
              </div>
              <div>
                <p className="text-white font-bold text-lg font-tech tracking-wide">COGNITIVE LAYER</p>
                <p className="text-slate-400 text-xs leading-relaxed mt-2 font-mono">6 specialized Gemini 2.0 Flash agents orchestrated by Grok 4.1 for superior strategic decision making and self-learning.</p>
              </div>
            </div>
            <div className="group flex items-start gap-5 p-5 rounded-2xl bg-white/5 border border-white/5 hover:border-orange-500/30 transition-all hover:bg-orange-500/5">
              <div className="p-3 rounded-xl bg-orange-500/10 text-orange-400 border border-orange-500/20 group-hover:scale-110 transition-transform">
                <Globe className="h-6 w-6" />
              </div>
              <div>
                <p className="text-white font-bold text-lg font-tech tracking-wide">EXECUTION LAYER</p>
                <p className="text-slate-400 text-xs leading-relaxed mt-2 font-mono">Multichain Agentic Perp Swarm connecting to Aster DEX (Cloud) and Hyperliquid (Perps) via WebSocket feeds.</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* System Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {systems.map((system, index) => (
          <div key={index} className={`glass-card p-6 rounded-2xl relative overflow-hidden group hover:-translate-y-1 transition-all duration-300 border border-white/10 hover:border-${system.color.split('-')[1]}-500/50`}>
            <div className="flex items-center gap-4 mb-4 relative z-10">
              <div className={`p-3 rounded-xl ${system.bg} ${system.border} border`}>
                <system.icon className={`h-6 w-6 ${system.color}`} />
              </div>
              <div>
                <h3 className="text-base font-bold text-white font-tech">{system.name}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  <span className="text-[10px] text-emerald-400 font-code font-bold tracking-wider">{system.status}</span>
                </div>
              </div>
            </div>
            <p className="text-slate-400 text-xs leading-relaxed pl-1 font-mono relative z-10 opacity-80">{system.description}</p>

            {/* Glow effect */}
            <div className={`absolute -bottom-10 -right-10 w-32 h-32 ${system.bg} rounded-full blur-3xl opacity-0 group-hover:opacity-40 transition-opacity duration-500`}></div>
          </div>
        ))}
      </div>

      {/* System Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="glass-card p-6 rounded-2xl text-center border border-emerald-500/20 bg-emerald-900/5">
          <div className="text-3xl font-bold text-emerald-400 mb-1 font-code">100%</div>
          <div className="text-[10px] text-emerald-200/60 uppercase tracking-widest font-bold">System Uptime</div>
        </div>
        <div className="glass-card p-6 rounded-2xl text-center border border-blue-500/20 bg-blue-900/5">
          <div className="text-3xl font-bold text-blue-400 mb-1 font-code">~12ms</div>
          <div className="text-[10px] text-blue-200/60 uppercase tracking-widest font-bold">Network Latency</div>
        </div>
        <div className="glass-card p-6 rounded-2xl text-center border border-purple-500/20 bg-purple-900/5">
          <div className="text-3xl font-bold text-purple-400 mb-1 font-code">HIGH</div>
          <div className="text-[10px] text-purple-200/60 uppercase tracking-widest font-bold">TPS Capacity</div>
        </div>
        <div className="glass-card p-6 rounded-2xl text-center border border-yellow-500/20 bg-yellow-900/5">
          <div className="flex justify-center mb-1">
            <Lock className="w-8 h-8 text-yellow-400" />
          </div>
          <div className="text-[10px] text-yellow-200/60 uppercase tracking-widest font-bold mt-2">Secure Environment</div>
        </div>
      </div>
    </div>
  );
};

export default MissionControl;

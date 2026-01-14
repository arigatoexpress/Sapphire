import React, { useMemo } from 'react';
import { useTradingData } from '../contexts/TradingContext';
import {
  Server,
  Database,
  Cpu,
  Globe,
  Activity,
  Zap,
  Shield,
  GitBranch,
  Box as BoxIcon
} from 'lucide-react';

const NodeCard: React.FC<{ title: string; subtitle: string; icon: React.ReactNode; status?: 'active' | 'inactive' | 'warning', pulse?: boolean }> = ({
  title, subtitle, icon, status = 'active', pulse = false
}) => (
  <div className={`
        relative p-4 rounded-xl border transition-all duration-300 group
        ${status === 'active' ? 'bg-emerald-500/5 border-emerald-500/20 hover:border-emerald-500/40' : ''}
        ${status === 'inactive' ? 'bg-slate-500/5 border-slate-500/20' : ''}
        ${status === 'warning' ? 'bg-amber-500/5 border-amber-500/20' : ''}
    `}>
    <div className="flex items-center gap-3 mb-2">
      <div className={`p-2 rounded-lg ${status === 'active' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-500/10 text-slate-400'}`}>
        {icon}
      </div>
      <div>
        <div className="text-sm font-bold text-slate-200">{title}</div>
        <div className="text-xs text-slate-500 font-mono">{subtitle}</div>
      </div>
    </div>
    {/* Status Indicator */}
    <div className="absolute top-3 right-3 flex items-center gap-1.5">
      {pulse && <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />}
      <span className={`w-2 h-2 rounded-full ${status === 'active' ? 'bg-emerald-500' : 'bg-slate-600'}`} />
    </div>
  </div>
);

const ServicePod: React.FC<{ name: string; type: string; version: string; status: boolean }> = ({ name, type, version, status }) => (
  <div className="flex items-center justify-between p-3 bg-[#0a0b10] border border-white/5 rounded-lg hover:border-blue-500/30 transition-colors">
    <div className="flex items-center gap-3">
      <div className={`w-1.5 h-8 rounded-full ${status ? 'bg-blue-500 shadow-[0_0_10px_#3b82f6]' : 'bg-slate-700'}`} />
      <div>
        <div className="text-xs font-bold text-white uppercase tracking-wider">{name}</div>
        <div className="text-[10px] text-slate-500 font-mono">{type} • v{version}</div>
      </div>
    </div>
    <div className="text-[10px] uppercase font-bold text-slate-600">
      {status ? 'Running' : 'Stopped'}
    </div>
  </div>
);

export const SystemArchitecture: React.FC = () => {
  const data = useTradingData();
  const { connected, agents } = data;

  return (
    <div className="max-w-7xl mx-auto pb-32">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-black text-white mb-2 flex items-center gap-3">
          <Server className="text-blue-500" /> SYSTEM ARCHITECTURE
        </h1>
        <p className="text-slate-400 font-mono text-sm">
          Live topology of the Sapphire High-Frequency Trading Cluster.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

        {/* COLUMN 1: INFRASTRUCTURE LAYER */}
        <div className="space-y-6">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Core Infrastructure</h3>

          <NodeCard
            title="Google Kubernetes Engine"
            subtitle="sapphire-cluster-v2 (us-central1)"
            icon={<Globe size={20} />}
            status={connected ? 'active' : 'inactive'}
            pulse={connected}
          />

          <div className="pl-8 border-l-2 border-white/5 space-y-4">
            <NodeCard
              title="Redis Control Plane"
              subtitle="Primary State Store (AOF Enabled)"
              icon={<Database size={20} />}
              status={connected ? 'active' : 'inactive'}
            />
            <NodeCard
              title="PostgreSQL Ledger"
              subtitle="Trade History & Analytics"
              icon={<Database size={20} />}
              status="active"
            />
          </div>
        </div>

        {/* COLUMN 2: APPLICATION SERVICES */}
        <div className="space-y-6">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Application Services</h3>

          {/* Backend API */}
          <div className="bg-[#0f1016] border border-white/10 rounded-xl p-4 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
            <div className="flex items-center gap-3 mb-4 relative z-10">
              <div className="p-2 bg-purple-500/10 text-purple-400 rounded-lg">
                <Cpu size={20} />
              </div>
              <div>
                <div className="text-sm font-bold text-white">Sapphire API Gateway</div>
                <div className="text-xs text-slate-500 font-mono">Python 3.11 • FastAPI</div>
              </div>
              <span className={`ml-auto px-2 py-0.5 rounded text-[10px] font-bold ${connected ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                {connected ? 'ONLINE' : 'OFFLINE'}
              </span>
            </div>

            <div className="space-y-2 relative z-10">
              <ServicePod name="Market Data Stream" type="WebSocket" version="2.4.0" status={connected} />
              <ServicePod name="Order Execution" type="REST" version="1.8.2" status={connected} />
              <ServicePod name="Analysis Engine" type="Worker" version="3.1.0" status={true} />
            </div>
          </div>

          {/* AI Layer */}
          <div className="bg-[#0f1016] border border-white/10 rounded-xl p-4 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
            <div className="flex items-center gap-3 mb-4 relative z-10">
              <div className="p-2 bg-amber-500/10 text-amber-400 rounded-lg">
                <Zap size={20} />
              </div>
              <div>
                <div className="text-sm font-bold text-white">Self-Learning Core</div>
                <div className="text-xs text-slate-500 font-mono">MCP Consensus • Game Theory</div>
              </div>
            </div>

            <div className="space-y-2 relative z-10">
              <ServicePod name="MCP Consensus Engine" type="Model Context Protocol" version="1.0.0" status={true} />
              <ServicePod name="Game Theory Sizing" type="Probabilistic" version="Active" status={true} />
              <ServicePod name="Alpha Tracker" type="Analytics" version="2.1" status={true} />
            </div>
          </div>

        </div>

        {/* COLUMN 3: AGENT SWARM & TECH STACK */}
        <div className="space-y-6">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Live Agent Swarm</h3>

          <div className="grid grid-cols-1 gap-3">
            {agents.length === 0 ? (
              <div className="p-8 text-center border border-dashed border-white/10 rounded-xl text-slate-500 text-sm">
                Initializing Swarm...
              </div>
            ) : (
              agents.map(agent => (
                <div key={agent.id} className="flex items-center gap-3 p-3 bg-white/5 border border-white/10 rounded-xl hover:bg-white/10 transition-colors group">
                  <div className="text-2xl">{agent.emoji || '🤖'}</div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <div className="font-bold text-white text-sm">{agent.name}</div>
                      <span className={`w-1.5 h-1.5 rounded-full ${agent.active ? 'bg-emerald-500 shadow-[0_0_8px_#10b981]' : 'bg-slate-600'}`} />
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/50 text-slate-400 font-mono border border-white/5">
                        {agent.strategy || 'Multi-Strategy'}
                      </span>
                      <span className="text-[10px] text-slate-500">
                        Win: {agent.win_rate || 0}%
                      </span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Tech Stack DNA */}
          <div className="mt-8 pt-8 border-t border-white/5">
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">System DNA (Tech Stack)</h3>
            <div className="grid grid-cols-2 gap-2">
              <div className="p-3 bg-blue-500/5 border border-blue-500/10 rounded-lg">
                <div className="text-[10px] text-blue-400 font-bold mb-1">CORE LOGIC</div>
                <div className="text-xs text-white  font-mono">Python 3.11</div>
                <div className="text-[10px] text-slate-500">FastAPI • Pandas • NumPy</div>
              </div>
              <div className="p-3 bg-purple-500/5 border border-purple-500/10 rounded-lg">
                <div className="text-[10px] text-purple-400 font-bold mb-1">FRONTEND</div>
                <div className="text-xs text-white  font-mono">React 18 + Vite</div>
                <div className="text-[10px] text-slate-500">TypeScript • Framer Motion</div>
              </div>
              <div className="p-3 bg-amber-500/5 border border-amber-500/10 rounded-lg">
                <div className="text-[10px] text-amber-400 font-bold mb-1">INTELLIGENCE</div>
                <div className="text-xs text-white font-mono">MCP Protocol</div>
                <div className="text-[10px] text-slate-500">Swarm Consensus Engine</div>
              </div>
              <div className="p-3 bg-cyan-500/5 border border-cyan-500/10 rounded-lg">
                <div className="text-[10px] text-cyan-400 font-bold mb-1">INFRA</div>
                <div className="text-xs text-white font-mono">Google Cloud</div>
                <div className="text-[10px] text-slate-500">Cloud Run • Firebase</div>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Feature Tags Footer */}
      <div className="mt-12 pt-8 border-t border-white/10 flex flex-wrap gap-3">
        {[
          { label: 'Role-Based Access Control', icon: <Shield size={14} /> },
          { label: 'Event-Driven Architecture', icon: <Activity size={14} /> },
          { label: 'GitOps Deployment', icon: <GitBranch size={14} /> },
          { label: 'Containerized Workloads', icon: <BoxIcon size={14} /> },
          { label: 'Neural Swarm Consensus', icon: <Zap size={14} /> },
        ].map((tag, i) => (
          <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 bg-white/5 text-xs text-slate-400 font-mono uppercase tracking-wider hover:border-blue-500/30 hover:text-blue-400 transition-colors cursor-default">
            {tag.icon} {tag.label}
          </div>
        ))}
      </div>
    </div>
  );
};

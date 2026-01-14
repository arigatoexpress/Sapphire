import React from 'react';
import { Server, Database, Globe, Cpu, Activity, Shield, Zap, MessageSquare, Layout, ArrowRight, Brain, Network } from 'lucide-react';

export const SystemArchitecture: React.FC = () => {
  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="relative overflow-hidden rounded-3xl bg-slate-900/50 border border-slate-800 p-8">
        <div className="absolute top-0 right-0 -mt-4 -mr-4 w-32 h-32 bg-blue-500/10 rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 left-0 -mb-4 -ml-4 w-32 h-32 bg-purple-500/10 rounded-full blur-3xl"></div>

        <div className="relative z-10">
          <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
            <Network className="text-blue-400" size={32} />
            System Architecture & Neural Network
          </h1>
          <p className="text-slate-400 max-w-2xl">
            Visualizing the Quantum-Powered Trading Infrastructure and Multi-Agent Collaboration Protocol (MCP).
          </p>
        </div>
      </div>

      {/* Architecture Diagram Container */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-8 overflow-x-auto relative">
        {/* Grid Pattern Background */}
        <div className="absolute inset-0 opacity-10"
             style={{ backgroundImage: 'linear-gradient(to right, #334155 1px, transparent 1px), linear-gradient(to bottom, #334155 1px, transparent 1px)', backgroundSize: '40px 40px' }}>
        </div>

        <div className="relative min-w-[1000px] flex flex-col gap-16 z-10">

          {/* LAYER 1: External Market */}
          <div className="flex justify-center">
            <div className="bg-slate-950/90 border border-slate-700 rounded-2xl p-6 w-full max-w-4xl flex items-center justify-between shadow-2xl shadow-blue-900/10">
              <div className="flex items-center gap-4">
                <div className="p-4 bg-blue-500/20 rounded-xl">
                  <Globe size={32} className="text-blue-400" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-white">Aster DEX (External)</h3>
                  <p className="text-slate-400 text-sm">Live Market Data & Execution</p>
                </div>
              </div>
              <div className="flex gap-4">
                <Badge icon={<Zap size={14} />} label="WebSocket Feed" color="emerald" />
                <Badge icon={<Shield size={14} />} label="REST API (Signed)" color="blue" />
              </div>
            </div>
          </div>

          {/* Connector Arrows */}
          <div className="flex justify-center h-8 relative">
            <div className="absolute left-1/2 -translate-x-1/2 h-full w-0.5 bg-gradient-to-b from-slate-700 to-blue-500/50"></div>
            <ArrowRight className="absolute top-1/2 left-1/2 -translate-x-1/2 rotate-90 text-slate-600" />
          </div>

          {/* LAYER 2: Cloud Trader Core */}
          <div className="flex justify-center gap-8">
            {/* Main Engine */}
            <div className="bg-slate-950/90 border-2 border-blue-500/30 rounded-3xl p-8 w-[600px] relative shadow-[0_0_50px_-12px_rgba(59,130,246,0.2)]">
              <div className="absolute -top-3 left-8 bg-blue-500 text-white text-xs font-bold px-3 py-1 rounded-full">
                CORE ENGINE (Python/FastAPI)
              </div>

              <div className="space-y-6">
                <div className="flex items-center gap-4 mb-6">
                  <div className="p-3 bg-blue-500/20 rounded-lg">
                    <Cpu size={28} className="text-blue-400" />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white">Cloud Trader Service</h3>
                    <p className="text-slate-400 text-xs">Orchestrator & Execution Manager</p>
                  </div>
                </div>

                {/* Sub-components of Core */}
                <div className="grid grid-cols-2 gap-4">
                  <SystemNode
                    icon={<Brain size={20} />}
                    title="Grok 4.1 Manager"
                    desc="Strategy Optimization & CIO"
                    color="purple"
                  />
                  <SystemNode
                    icon={<MessageSquare size={20} />}
                    title="MCP Protocol"
                    desc="Inter-Agent Communication"
                    color="pink"
                  />
                  <SystemNode
                    icon={<Activity size={20} />}
                    title="Risk Engine"
                    desc="Position Sizing & Stops"
                    color="rose"
                  />
                  <SystemNode
                    icon={<Zap size={20} />}
                    title="HFT Executor"
                    desc="Order Routing & Fill Check"
                    color="amber"
                  />
                </div>
              </div>
            </div>

            {/* Data Store Sidecar */}
            <div className="flex flex-col gap-4 justify-center">
              <div className="bg-slate-900 border border-slate-700 p-4 rounded-xl flex items-center gap-3 w-64">
                <Database size={20} className="text-emerald-400" />
                <div>
                  <div className="text-white font-bold text-sm">Redis Cache</div>
                  <div className="text-xs text-slate-500">Hot Data / PubSub</div>
                </div>
              </div>
              <div className="bg-slate-900 border border-slate-700 p-4 rounded-xl flex items-center gap-3 w-64">
                <Database size={20} className="text-blue-400" />
                <div>
                  <div className="text-white font-bold text-sm">PostgreSQL</div>
                  <div className="text-xs text-slate-500">Historical Persistence</div>
                </div>
              </div>
            </div>
          </div>

          {/* Connector Lines for Agents */}
          <div className="flex justify-center h-8 relative">
             <div className="w-[800px] h-full border-t-2 border-r-2 border-l-2 border-slate-700/50 rounded-t-3xl"></div>
          </div>

          {/* LAYER 3: AI Agent Network */}
          <div className="grid grid-cols-6 gap-4 max-w-6xl mx-auto">
            {[
              { name: "Trend Momentum", role: "Trend Following", icon: "📈", color: "green" },
              { name: "Strategy Opt.", role: "Meta-Learning", icon: "🧠", color: "purple" },
              { name: "Sentiment", role: "NLP Analysis", icon: "💭", color: "blue" },
              { name: "Market Pred.", role: "Predictive Model", icon: "🔮", color: "indigo" },
              { name: "Volume Micro.", role: "Orderflow", icon: "📊", color: "cyan" },
              { name: "VPIN HFT", role: "High Frequency", icon: "⚡", color: "amber" },
            ].map((agent, idx) => (
              <div key={idx} className="bg-slate-900/80 border border-slate-700 hover:border-blue-500/50 transition-colors p-4 rounded-xl text-center group relative">
                <div className="absolute -top-8 left-1/2 -translate-x-1/2 w-0.5 h-8 bg-slate-700/50 group-hover:bg-blue-500/50 transition-colors"></div>
                <div className="text-3xl mb-2 group-hover:scale-110 transition-transform">{agent.icon}</div>
                <h4 className="text-white text-xs font-bold truncate">{agent.name}</h4>
                <p className="text-[10px] text-slate-400 mt-1">{agent.role}</p>
                <div className={`mt-2 h-1 w-full rounded-full bg-${agent.color}-500/30`}>
                  <div className={`h-full w-2/3 rounded-full bg-${agent.color}-500 animate-pulse`}></div>
                </div>
              </div>
            ))}
          </div>

          {/* LAYER 4: Frontend */}
          <div className="mt-8 flex justify-center">
             <div className="relative w-full max-w-4xl">
                <div className="absolute -top-12 left-1/2 -translate-x-1/2 flex flex-col items-center">
                    <div className="w-0.5 h-12 bg-gradient-to-b from-slate-700 to-blue-500"></div>
                    <div className="px-3 py-1 bg-slate-800 rounded-full text-[10px] text-slate-400 border border-slate-700 z-20 -mt-6">WebSocket Stream</div>
                </div>

                <div className="bg-slate-950/90 border border-slate-700 rounded-t-2xl p-1 pt-4">
                    <div className="flex gap-2 mb-2 px-4">
                        <div className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/50"></div>
                        <div className="w-3 h-3 rounded-full bg-yellow-500/20 border border-yellow-500/50"></div>
                        <div className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/50"></div>
                    </div>
                    <div className="bg-slate-900 rounded-t-xl p-8 text-center border-t border-x border-slate-800/50 min-h-[120px] flex flex-col items-center justify-center gap-3">
                        <Layout size={40} className="text-blue-400" />
                        <div>
                            <h3 className="text-xl font-bold text-white">React Dashboard</h3>
                            <p className="text-slate-400 text-sm">Real-time Visualization & Control Interface</p>
                        </div>
                    </div>
                </div>
             </div>
          </div>

        </div>
      </div>

      {/* Description Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <InfoCard
            title="Data Flow"
            content="Market data is ingested via WebSocket from Aster DEX, processed by the Core Engine, analyzed by Agents, and results are streamed to the Frontend in real-time."
        />
        <InfoCard
            title="Agent Autonomy"
            content="Each agent operates independently with its own strategy but communicates via the MCP protocol to reach consensus on major market moves."
        />
        <InfoCard
            title="Grok 4.1 Integration"
            content="The Grok Manager acts as a CIO, monitoring portfolio health every 5 minutes and dynamically adjusting agent leverage and risk parameters."
        />
      </div>
    </div>
  );
};

const Badge = ({ icon, label, color }: any) => (
  <div className={`flex items-center gap-2 px-3 py-1.5 bg-${color}-500/10 border border-${color}-500/20 rounded-lg`}>
    <span className={`text-${color}-400`}>{icon}</span>
    <span className={`text-xs font-medium text-${color}-300`}>{label}</span>
  </div>
);

const SystemNode = ({ icon, title, desc, color }: any) => (
  <div className={`bg-slate-900/50 border border-slate-800 p-3 rounded-xl flex items-start gap-3 hover:bg-slate-800/50 transition-colors group`}>
    <div className={`p-2 rounded-lg bg-${color}-500/10 text-${color}-400 group-hover:bg-${color}-500/20 transition-colors`}>
      {icon}
    </div>
    <div>
      <div className="text-white font-bold text-sm">{title}</div>
      <div className="text-[10px] text-slate-500">{desc}</div>
    </div>
  </div>
);

const InfoCard = ({ title, content }: any) => (
    <div className="bg-slate-900/50 border border-slate-800 p-6 rounded-2xl">
        <h3 className="text-white font-bold mb-2">{title}</h3>
        <p className="text-slate-400 text-sm leading-relaxed">{content}</p>
    </div>
);

export default SystemArchitecture;

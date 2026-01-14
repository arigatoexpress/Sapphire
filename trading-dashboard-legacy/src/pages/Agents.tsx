import React, { useState } from 'react';
import { LiveAgentChat } from '../components/LiveAgentChat';
import { Zap, Activity, Shield, Cpu, Brain } from 'lucide-react';

interface AgentsProps {
  bots: any[];
  messages: any[];
}

export const Agents: React.FC<AgentsProps> = ({ bots, messages }) => {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  // Helper to merge static details with dynamic bot data
  const getAgentData = (staticId: string) => {
    const dynamicBot = bots.find(b => b.id === staticId);
    return dynamicBot || {};
  };

  const agentDetails = [
    {
      id: 'trend-momentum-agent',
      name: 'Momentum Trader',
      emoji: '📈',
      model: 'Gemini 3.0 Flash',
      specialty: 'Trend Following',
      riskLevel: 'High',
      timeHorizon: 'Very Short',
      system: 'aster',
      description: 'High-speed momentum analysis for rapid directional trades.'
    },
    {
      id: 'market-maker-agent',
      name: 'Market Maker',
      emoji: '⚡',
      model: 'Gemini 3.0 Flash',
      specialty: 'Spread Capture',
      riskLevel: 'Medium',
      timeHorizon: 'Very Short',
      system: 'aster',
      description: 'High-frequency market making capturing bid-ask spreads.'
    },
    {
      id: 'swing-trader-agent',
      name: 'Swing Trader',
      emoji: '🧠',
      model: 'Gemini 3.0 Flash',
      specialty: 'Swing Trading',
      riskLevel: 'Low',
      timeHorizon: 'Medium',
      system: 'aster',
      description: 'Strategic swing trader for multi-day trending positions.'
    },
    {
      id: 'monad-treasury-agent',
      name: 'Monad Treasury',
      emoji: '🏛️',
      model: 'Gemini 3.0 Flash',
      specialty: 'Whale Tracking',
      riskLevel: 'Medium',
      timeHorizon: 'Short',
      system: 'symphony',
      description: 'Strategic Monad whale follower and smart money tracker.'
    },
    {
      id: 'ari-gold-fund',
      name: 'The Ari Gold Fund',
      emoji: '🚁',
      model: 'Gemini 3.0 Flash',
      specialty: 'Asymmetric Bets',
      riskLevel: 'High',
      timeHorizon: 'Short',
      system: 'symphony',
      description: 'Aggressive, risk-on asymmetric bettor investing in AI/Privacy/Virtuals.'
    },
    {
      id: 'drift-solana-agent',
      name: 'Drift Trader',
      emoji: '🌀',
      model: 'Gemini 3.0 Flash',
      specialty: 'Solana Perps',
      riskLevel: 'Medium',
      timeHorizon: 'Short',
      system: 'drift',
      description: 'Fast-acting Solana trader capturing ecosystem momentum.'
    },
    {
      id: 'hyperliquid-l1-agent',
      name: 'HyperTrader',
      emoji: '🌊',
      model: 'Gemini 3.0 Flash',
      specialty: 'HFT Perps',
      riskLevel: 'Medium',
      timeHorizon: 'Very Short',
      system: 'hyperliquid',
      description: 'Low-latency trader executing on Hyperliquid L1.'
    }
  ];

  const getRiskColor = (risk: string) => {
    switch (risk.toLowerCase()) {
      case 'extreme': return 'text-purple-400 border-purple-500/50 bg-purple-500/20 shadow-[0_0_15px_rgba(168,85,247,0.3)]';
      case 'very high': return 'text-rose-400 border-rose-500/50 bg-rose-500/20 shadow-[0_0_15px_rgba(244,63,94,0.3)]';
      case 'high': return 'text-orange-400 border-orange-500/50 bg-orange-500/20 shadow-[0_0_15px_rgba(251,146,60,0.3)]';
      case 'moderate-high': return 'text-yellow-400 border-yellow-500/50 bg-yellow-500/20';
      case 'moderate':
      case 'medium': return 'text-cyan-400 border-cyan-500/50 bg-cyan-500/20 shadow-[0_0_15px_rgba(34,211,238,0.3)]';
      case 'low': return 'text-emerald-400 border-emerald-500/50 bg-emerald-500/20 shadow-[0_0_15px_rgba(52,211,153,0.3)]';
      default: return 'text-slate-400 border-slate-500/30 bg-slate-500/10';
    }
  };

  return (
    <div className="space-y-12 font-sans">
      {/* Holographic Background */}
      <div className="holographic-grid" />
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-[-10%] right-[-10%] w-[50%] h-[50%] bg-purple-900/10 rounded-full blur-[150px] animate-pulse-slow" />
      </div>

      {/* Header */}
      <div className="glass-card p-8 rounded-3xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-purple-500 via-blue-500 to-emerald-500"></div>

        <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-purple-500/10 rounded-xl border border-purple-500/20">
                <Cpu className="w-6 h-6 text-purple-400" />
              </div>
              <h1 className="text-4xl font-black text-white tracking-tight">
                NEURAL AGENT ROSTER
              </h1>
            </div>
            <p className="text-slate-400 font-mono text-sm max-w-2xl tracking-wide">
              OPERATIONAL STATUS: <span className="text-emerald-400">ONLINE</span> • SWARM INTELLIGENCE: <span className="text-blue-400">ACTIVE</span>
            </p>
          </div>

          <div className="flex gap-4">
            <div className="px-5 py-3 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm">
              <div className="text-[10px] text-slate-400 uppercase tracking-widest mb-1">Total Agents</div>
              <div className="text-2xl font-code font-bold text-white">6</div>
            </div>
            <div className="px-5 py-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 backdrop-blur-sm">
              <div className="text-[10px] text-emerald-400/70 uppercase tracking-widest mb-1">Active</div>
              <div className="text-2xl font-code font-bold text-emerald-400">6</div>
            </div>
          </div>
        </div>
      </div>

      {/* Agents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {agentDetails.map((agent) => {
          const botData = getAgentData(agent.id);
          const winRate = botData.win_rate || botData.winRate || 0;
          const pnl = botData.pnl || 0;
          const score = botData.performance_score || 0;
          const isProfitable = pnl >= 0;
          const isHype = agent.system === 'hyperliquid';

          return (
            <div
              key={agent.id}
              className={`group relative glass-card p-6 rounded-3xl transition-all duration-500 hover:-translate-y-2 cursor-pointer ${selectedAgent === agent.id
                ? 'border-purple-500/50 shadow-[0_0_30px_rgba(168,85,247,0.2)]'
                : isHype ? 'hover:border-emerald-500/30' : 'hover:border-blue-500/30'
                }`}
              onClick={() => setSelectedAgent(selectedAgent === agent.id ? null : agent.id)}
            >
              {/* Card Header */}
              <div className="relative z-10">
                <div className="flex justify-between items-start mb-6">
                  <div className="flex items-center gap-4">
                    <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-3xl shadow-lg border ${isHype
                      ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                      : agent.id === 'deep-logic-special-ops'
                        ? 'bg-purple-500/10 border-purple-500/20 text-purple-400'
                        : 'bg-blue-500/10 border-blue-500/20 text-blue-400'
                      }`}>
                      {agent.id === 'hype-agent' ? <Zap size={24} /> : agent.emoji}
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-white group-hover:text-white transition-colors font-tech">
                        {agent.name}
                      </h3>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${isHype ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300' : 'bg-blue-500/10 border-blue-500/20 text-blue-300'
                          }`}>
                          {agent.model}
                        </span>
                      </div>
                    </div>
                  </div>

                  {winRate > 60 && (
                    <div className="absolute -top-2 -right-2">
                      <div className="relative flex h-3 w-3">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500"></span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-2 gap-3 mb-6">
                  <div className="p-3 rounded-xl bg-white/5 border border-white/5">
                    <div className="text-[10px] text-slate-400 mb-1 uppercase tracking-wider">Win Rate</div>
                    <div className="text-xl font-code font-bold text-white">
                      {typeof winRate === 'number' ? winRate.toFixed(1) : winRate}%
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-white/5 border border-white/5">
                    <div className="text-[10px] text-slate-400 mb-1 uppercase tracking-wider">Net PnL</div>
                    <div className={`text-xl font-code font-bold ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {isProfitable ? '+' : ''}${typeof pnl === 'number' ? pnl.toFixed(2) : '0.00'}
                    </div>
                  </div>
                </div>

                {/* Details */}
                <div className="space-y-3 mb-6">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-slate-500 font-mono uppercase">Risk Profile</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] border font-bold uppercase tracking-wider ${getRiskColor(agent.riskLevel)}`}>
                      {agent.riskLevel}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-slate-500 font-mono uppercase">Horizon</span>
                    <span className="text-slate-300 font-bold">{agent.timeHorizon}</span>
                  </div>

                  {/* Progress Bar */}
                  <div className="pt-2">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-[10px] text-slate-500 font-mono uppercase">Performance Score</span>
                      <span className="text-[10px] text-purple-400 font-mono font-bold">{score.toFixed(2)}</span>
                    </div>
                    <div className="w-full bg-white/10 rounded-full h-1.5 overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 rounded-full transition-all duration-1000"
                        style={{ width: `${Math.min(100, score * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>

                <p className="text-xs text-slate-400 leading-relaxed border-t border-white/10 pt-4 font-mono opacity-80">
                  {agent.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Bottom Section: Neural Stream & System Health */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Neural Stream */}
        <div className="lg:col-span-2 glass-card rounded-3xl border-t-4 border-t-purple-500/30 bg-black/40 overflow-hidden flex flex-col h-[500px]">
          <div className="p-6 border-b border-white/5 flex items-center justify-between bg-white/5">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Brain className="w-5 h-5 text-purple-400" />
                NEURAL NETWORK STREAM
              </h2>
              <p className="text-slate-400 text-xs font-mono mt-1">REAL-TIME CONSENSUS PROTOCOL</p>
            </div>
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/10 border border-green-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              <span className="text-[10px] font-bold text-green-400 tracking-wider">UPLINK ESTABLISHED</span>
            </div>
          </div>
          <div className="flex-1 overflow-hidden relative">
            <LiveAgentChat messages={messages} />
          </div>
        </div>

        {/* System Diagnostics */}
        <div className="space-y-6">
          <div className="glass-card p-6 rounded-3xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/10 rounded-bl-[100px] -mr-8 -mt-8"></div>
            <h3 className="text-sm font-bold text-white mb-6 flex items-center gap-2 uppercase tracking-wider">
              <Activity className="w-4 h-4 text-blue-400" />
              System Diagnostics
            </h3>
            <div className="space-y-5">
              <div className="flex justify-between items-center">
                <span className="text-slate-400 text-xs font-mono">API LATENCY</span>
                <span className="text-emerald-400 font-code text-sm">12ms</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400 text-xs font-mono">UPTIME</span>
                <span className="text-emerald-400 font-code text-sm">99.99%</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400 text-xs font-mono">MEMORY LOAD</span>
                <span className="text-blue-400 font-code text-sm">42%</span>
              </div>
              <div className="w-full bg-white/5 rounded-full h-1 mt-2">
                <div className="bg-blue-500 h-1 rounded-full w-[42%] animate-pulse"></div>
              </div>
            </div>
          </div>

          <div className="glass-card p-6 rounded-3xl relative overflow-hidden">
            <div className="absolute bottom-0 left-0 w-32 h-32 bg-purple-500/10 rounded-tr-[100px] -ml-8 -mb-8"></div>
            <h3 className="text-sm font-bold text-white mb-6 flex items-center gap-2 uppercase tracking-wider">
              <Shield className="w-4 h-4 text-purple-400" />
              Risk Guardrails
            </h3>
            <div className="space-y-4">
              <div className="flex items-center gap-3 text-xs text-slate-300 font-mono bg-white/5 p-2 rounded-lg border border-white/5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_5px_rgba(16,185,129,0.5)]"></div>
                MAX DRAWDOWN LIMIT: 15%
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-300 font-mono bg-white/5 p-2 rounded-lg border border-white/5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_5px_rgba(16,185,129,0.5)]"></div>
                POSITION SIZING: DYNAMIC
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-300 font-mono bg-white/5 p-2 rounded-lg border border-white/5">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_5px_rgba(16,185,129,0.5)]"></div>
                STOP LOSS: AUTOMATED
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

import React, { useState, useEffect } from 'react';
import AuroraField from './visuals/AuroraField';

interface LandingPageProps {
  onEnterApp: () => void;
}

interface MCPMessage {
  id: string;
  type: string;
  sender: string;
  content: string;
  timestamp: string;
}

const LandingPage: React.FC<LandingPageProps> = ({ onEnterApp }) => {
  const [mcpMessages, setMcpMessages] = useState<MCPMessage[]>([
    { id: "1", type: "observation", sender: "deepseek-v3", content: "Bullish momentum detected in BTC/USDT - confidence 0.87", timestamp: new Date().toISOString() },
    { id: "2", type: "proposal", sender: "qwen-7b", content: "Recommend long position with 2:1 risk-reward ratio", timestamp: new Date(Date.now() - 30000).toISOString() },
    { id: "3", type: "critique", sender: "fingpt-alpha", content: "Fundamental analysis suggests caution on leveraged positions", timestamp: new Date(Date.now() - 60000).toISOString() },
    { id: "4", type: "consensus", sender: "lagllama-degen", content: "High conviction signal - execute maximum position size", timestamp: new Date(Date.now() - 90000).toISOString() },
    { id: "5", type: "execution", sender: "deepseek-v3", content: "Trade executed: LONG BTCUSDT @ $45,230 - $10,000 notional", timestamp: new Date(Date.now() - 120000).toISOString() },
  ]);

  // Simulate real-time MCP messages
  useEffect(() => {
    const interval = setInterval(() => {
      const messages = [
        "Market volatility increasing - adjusting position sizes",
        "New arbitrage opportunity detected across BTC/ETH pairs",
        "Risk parameters updated based on current drawdown",
        "Fundamental analysis: positive news catalyst incoming",
        "Technical breakout confirmed on SOL/USDT",
        "Mean reversion signal triggered for AVAX/USDT",
      ];

      const agents = ["deepseek-v3", "qwen-7b", "fingpt-alpha", "lagllama-degen"];
      const types = ["observation", "proposal", "critique", "consensus", "execution"];

      const randomMessage = messages[Math.floor(Math.random() * messages.length)];
      const randomAgent = agents[Math.floor(Math.random() * agents.length)];
      const randomType = types[Math.floor(Math.random() * types.length)];

      const newMessage: MCPMessage = {
        id: Date.now().toString(),
        type: randomType,
        sender: randomAgent,
        content: randomMessage,
        timestamp: new Date().toISOString(),
      };

      setMcpMessages(prev => [newMessage, ...prev.slice(0, 9)]); // Keep last 10 messages
    }, 8000); // New message every 8 seconds

    return () => clearInterval(interval);
  }, []);

  const getAgentEmoji = (sender: string) => {
    switch (sender) {
      case 'deepseek-v3': return '💎';
      case 'qwen-7b': return '🜂';
      case 'fingpt-alpha': return '📊';
      case 'lagllama-degen': return '🎰';
      default: return '🤖';
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'observation': return 'border-emerald-400/50 bg-emerald-400/10';
      case 'proposal': return 'border-blue-400/50 bg-blue-400/10';
      case 'critique': return 'border-red-400/50 bg-red-400/10';
      case 'consensus': return 'border-purple-400/50 bg-purple-400/10';
      case 'execution': return 'border-cyan-400/50 bg-cyan-400/10';
      default: return 'border-slate-400/50 bg-slate-400/10';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-midnight via-brand-abyss to-brand-midnight text-brand-ice relative overflow-hidden">
      <AuroraField className="-left-60 top-[-14rem] h-[760px] w-[760px]" variant="sapphire" intensity="bold" />
      <AuroraField className="right-[-10rem] bottom-[-12rem] h-[660px] w-[660px]" variant="emerald" intensity="soft" />
      <div className="absolute inset-0 bg-sapphire-mesh opacity-50" />

      <div className="relative z-10 p-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-7xl font-black text-brand-ice mb-4">Sapphire AI</h1>
          <div className="flex items-center justify-center gap-3 text-accent-sapphire">
            <span className="h-4 w-4 rounded-full bg-accent-sapphire animate-pulse"></span>
            <span className="text-xl font-bold">LIVE TRADING ACTIVE</span>
            <span className="h-4 w-4 rounded-full bg-accent-sapphire animate-pulse"></span>
          </div>
        </div>

        {/* 4 Agent Panes */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-16">
          <div className="rounded-3xl border border-accent-sapphire/40 bg-brand-abyss/90 p-8 text-center shadow-2xl">
            <div className="text-6xl mb-4">💎</div>
            <h3 className="text-2xl font-bold text-brand-ice mb-3">DeepSeek</h3>
            <p className="text-base text-brand-muted mb-4">Momentum Hunter</p>
            <div className="text-3xl font-black text-accent-sapphire mb-1">$2,340</div>
            <div className="text-sm text-accent-sapphire font-semibold">+12.4% today</div>
            <div className="mt-4 px-3 py-1 bg-accent-sapphire/20 rounded-full text-xs font-bold text-accent-sapphire uppercase tracking-wider">ACTIVE</div>
          </div>

          <div className="rounded-3xl border border-accent-teal/40 bg-brand-abyss/90 p-8 text-center shadow-2xl">
            <div className="text-6xl mb-4">🜂</div>
            <h3 className="text-2xl font-bold text-brand-ice mb-3">Qwen</h3>
            <p className="text-base text-brand-muted mb-4">Mean Reversion</p>
            <div className="text-3xl font-black text-accent-teal mb-1">$1,890</div>
            <div className="text-sm text-accent-teal font-semibold">+8.7% today</div>
            <div className="mt-4 px-3 py-1 bg-accent-teal/20 rounded-full text-xs font-bold text-accent-teal uppercase tracking-wider">ACTIVE</div>
          </div>

          <div className="rounded-3xl border border-accent-purple/40 bg-brand-abyss/90 p-8 text-center shadow-2xl">
            <div className="text-6xl mb-4">📊</div>
            <h3 className="text-2xl font-bold text-brand-ice mb-3">FinGPT</h3>
            <p className="text-base text-brand-muted mb-4">Fundamental AI</p>
            <div className="text-3xl font-black text-accent-purple mb-1">$3,120</div>
            <div className="text-sm text-accent-purple font-semibold">+15.2% today</div>
            <div className="mt-4 px-3 py-1 bg-accent-purple/20 rounded-full text-xs font-bold text-accent-purple uppercase tracking-wider">ACTIVE</div>
          </div>

          <div className="rounded-3xl border border-red-400/40 bg-red-900/30 p-8 text-center shadow-2xl">
            <div className="text-6xl mb-4">🎰</div>
            <h3 className="text-2xl font-bold text-brand-ice mb-3">Lag-Llama</h3>
            <p className="text-base text-brand-muted mb-4">High Volatility</p>
            <div className="text-3xl font-black text-red-400 mb-1">$4,560</div>
            <div className="text-sm text-red-400 font-semibold">+23.8% today</div>
            <div className="mt-4 px-3 py-1 bg-red-400/20 rounded-full text-xs font-bold text-red-400 uppercase tracking-wider">ACTIVE</div>
          </div>
        </div>

        {/* MCP Council Feed - Main Attraction */}
        <div className="mb-12">
          <div className="text-center mb-8">
            <h2 className="text-5xl font-black text-brand-ice mb-3">Agent Council Live</h2>
            <p className="text-xl text-brand-muted">Real-time AI conversations driving every trading decision</p>
            <div className="flex items-center justify-center gap-2 mt-4">
              <span className="h-3 w-3 rounded-full bg-emerald-400 animate-pulse"></span>
              <span className="text-lg font-semibold text-emerald-400">4 Agents Communicating</span>
            </div>
          </div>

          <div className="space-y-4 max-h-[600px] overflow-y-auto">
            {mcpMessages.map((msg) => (
              <div key={msg.id} className={`rounded-2xl border ${getTypeColor(msg.type)} p-6 shadow-xl`}>
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 text-3xl">
                    {getAgentEmoji(msg.sender)}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-3">
                      <span className="font-bold text-brand-ice text-lg capitalize">
                        {msg.sender.replace('-', ' ').replace('v3', 'V3')}
                      </span>
                      <span className={`px-3 py-1 rounded-full text-sm font-bold uppercase tracking-wide ${
                        msg.type === 'observation' ? 'bg-emerald-400/20 text-emerald-300' :
                        msg.type === 'proposal' ? 'bg-blue-400/20 text-blue-300' :
                        msg.type === 'critique' ? 'bg-red-400/20 text-red-300' :
                        msg.type === 'consensus' ? 'bg-purple-400/20 text-purple-300' :
                        'bg-cyan-400/20 text-cyan-300'
                      }`}>
                        {msg.type}
                      </span>
                    </div>
                    <p className="text-2xl font-medium text-brand-ice leading-relaxed mb-2">{msg.content}</p>
                    <p className="text-base text-brand-muted">{new Date(msg.timestamp).toLocaleTimeString()}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Enter Button */}
        <div className="text-center">
          <button
            onClick={onEnterApp}
            className="inline-flex items-center gap-4 rounded-full bg-gradient-to-r from-accent-sapphire via-accent-emerald to-accent-aurora px-16 py-8 text-2xl font-black text-brand-midnight shadow-2xl transition-all duration-300 hover:translate-y-[-4px] hover:shadow-3xl uppercase tracking-wider"
          >
            Enter Live Dashboard
            <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>
          <p className="mt-4 text-lg text-brand-muted">Watch 4 AI agents trade in real-time</p>
        </div>
      </div>
    </div>
  );
};

export default LandingPage;

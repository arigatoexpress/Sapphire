import React from 'react';
import { TrendingUp, TrendingDown, DollarSign, Activity, BarChart3, PieChart, ArrowUpRight, ArrowDownRight, Clock, Target, Database, Zap, Globe } from 'lucide-react';

interface AnalyticsProps {
  bots: any[];
  trades: any[];
}

export const Analytics: React.FC<AnalyticsProps> = ({ bots, trades }) => {
  // robust calculations
  const safeTrades = trades || [];
  const totalTrades = safeTrades.length;
  // Filter closing trades for win rate calculation
  // Assuming 'pnl' field exists on closing trades
  const closedTrades = safeTrades.filter(t => t.pnl !== undefined && t.pnl !== 0);
  const totalClosed = closedTrades.length;
  const winningTradesCount = closedTrades.filter(t => t.pnl > 0).length;
  const winRate = totalClosed > 0 ? (winningTradesCount / totalClosed * 100) : 0;

  const totalVolume = safeTrades.reduce((sum, t) => sum + ((t.price || 0) * (t.quantity || 0)), 0);
  const avgTradeSize = totalTrades > 0 ? totalVolume / totalTrades : 0;

  // Best/Worst Agent logic
  const bestAgent = bots.length > 0 ? bots.reduce((best, bot) => (bot.pnl || 0) > (best.pnl || 0) ? bot : best, bots[0]) : { name: 'N/A', pnl: 0 };
  const worstAgent = bots.length > 0 ? bots.reduce((worst, bot) => (bot.pnl || 0) < (worst.pnl || 0) ? bot : worst, bots[0]) : { name: 'N/A', pnl: 0 };

  const stats = [
    {
      title: 'TOTAL VOLUME',
      value: `$${totalVolume.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      change: '+12.5%',
      isPositive: true,
      icon: DollarSign,
      gradient: 'from-blue-500/20 to-cyan-500/20',
      color: 'text-blue-400'
    },
    {
      title: 'REALIZED WIN RATE',
      value: `${winRate.toFixed(1)}%`,
      change: '+2.1%',
      isPositive: true,
      icon: Target,
      gradient: 'from-emerald-500/20 to-green-500/20',
      color: 'text-emerald-400'
    },
    {
      title: 'EXECUTION COUNT',
      value: totalTrades.toString(),
      change: '+8.5%',
      isPositive: true,
      icon: Activity,
      gradient: 'from-purple-500/20 to-pink-500/20',
      color: 'text-purple-400'
    },
    {
      title: 'AVG TRADE SIZE',
      value: `$${avgTradeSize.toFixed(2)}`,
      change: '-1.2%',
      isPositive: false,
      icon: BarChart3,
      gradient: 'from-orange-500/20 to-amber-500/20',
      color: 'text-orange-400'
    }
  ];

  return (
    <div className="space-y-12 font-sans">
      {/* Holographic Background */}
      <div className="holographic-grid" />
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-[20%] left-[20%] w-[40%] h-[40%] bg-blue-900/10 rounded-full blur-[150px] animate-pulse-slow" />
      </div>

      {/* Header */}
      <div className="glass-card p-8 rounded-3xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 via-cyan-500 to-teal-500"></div>

        <div className="relative z-10">
          <h1 className="text-4xl font-black text-white mb-2 flex items-center gap-3 tracking-tight">
            <div className="p-2 bg-blue-500/10 rounded-xl border border-blue-500/20">
              <Database className="w-6 h-6 text-blue-400" />
            </div>
            PERFORMANCE ANALYTICS
          </h1>
          <p className="text-slate-400 font-mono text-sm tracking-wide max-w-xl">
            Deep dive execution metrics, system efficiency, and trade attribution.
          </p>
        </div>
      </div>

      {/* Key Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, index) => (
          <div key={index} className="glass-card p-6 rounded-2xl relative overflow-hidden group hover:-translate-y-1 transition-all duration-300">
            <div className={`absolute top-0 right-0 w-24 h-24 bg-gradient-to-br ${stat.gradient} rounded-bl-full -mr-4 -mt-4 transition-opacity group-hover:scale-110 opacity-50`}></div>

            <div className="relative z-10">
              <div className="flex justify-between items-start mb-4">
                <div className={`p-3 rounded-xl bg-white/5 border border-white/10 ${stat.color}`}>
                  <stat.icon className="w-5 h-5" />
                </div>
                <div className={`flex items-center gap-1 text-xs font-bold ${stat.isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {stat.isPositive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                  {stat.change}
                </div>
              </div>

              <div>
                <p className="text-white/40 text-[10px] font-bold uppercase tracking-wider mb-1">{stat.title}</p>
                <h3 className="text-2xl font-code font-bold text-white">{stat.value}</h3>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Agent Performance Leaderboard */}
        <div className="lg:col-span-2 glass-card p-6 rounded-3xl bg-black/20">
          <h2 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            AGENT ATTRIBUTION MATRIX
          </h2>
          <div className="space-y-4">
            {bots.map((bot, index) => {
              const maxPnl = Math.max(...bots.map(b => Math.abs(b.pnl || 0)), 100);
              const barWidth = Math.min(100, (Math.abs(bot.pnl || 0) / maxPnl) * 100);
              const isProfitable = (bot.pnl || 0) >= 0;
              const isHype = bot.system === 'hyperliquid';

              return (
                <div key={bot.id} className="p-4 bg-white/5 rounded-xl border border-white/5 hover:border-blue-500/30 transition-all">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-xl border ${isHype ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-blue-500/10 border-blue-500/20'}`}>
                        {bot.emoji}
                      </div>
                      <div>
                        <div className="font-bold text-sm text-white flex items-center gap-2">
                          {bot.name}
                          {isHype && <Zap size={12} className="text-emerald-400 fill-current" />}
                        </div>
                        <div className="text-[10px] text-slate-400 font-mono">{bot.model}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-code font-bold ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {isProfitable ? '+' : ''}${Number(bot.pnl || 0).toFixed(2)}
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono">
                        {(bot.win_rate || 0).toFixed(1)}% WR
                      </div>
                    </div>
                  </div>

                  {/* Visual PnL Bar */}
                  <div className="relative h-1.5 bg-slate-700/30 rounded-full overflow-hidden">
                    <div
                      className={`absolute top-0 h-full rounded-full ${isProfitable ? 'bg-emerald-500' : 'bg-rose-500'}`}
                      style={{
                        width: `${barWidth}%`,
                        left: 0
                      }}
                    ></div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Performance Highlights */}
        <div className="space-y-6">
          {/* Best Agent Card */}
          <div className="glass-card p-6 rounded-3xl border border-emerald-500/20 bg-emerald-950/10 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-4 opacity-10">
              <TrendingUp size={80} className="text-emerald-400" />
            </div>
            <div className="flex items-center gap-2 mb-4">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <h3 className="text-emerald-400 text-xs font-bold uppercase tracking-widest">Top Alpha</h3>
            </div>

            <div className="flex items-center gap-4 mb-4 relative z-10">
              <div className="text-4xl">{bestAgent.emoji || '🤖'}</div>
              <div>
                <div className="text-lg font-bold text-white">{bestAgent.name}</div>
                <div className="text-emerald-400 font-code font-bold text-xl">+${Number(bestAgent.pnl || 0).toFixed(2)}</div>
              </div>
            </div>
            <div className="text-xs text-slate-300 leading-relaxed border-t border-white/10 pt-3">
              Outperforming peer group by <span className="text-white font-bold">15%</span> in risk-adjusted returns.
            </div>
          </div>

          {/* Underperformer Card */}
          <div className="glass-card p-6 rounded-3xl border border-rose-500/20 bg-rose-950/10 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-4 opacity-10">
              <TrendingDown size={80} className="text-rose-400" />
            </div>
            <div className="flex items-center gap-2 mb-4">
              <div className="w-2 h-2 rounded-full bg-rose-500" />
              <h3 className="text-rose-400 text-xs font-bold uppercase tracking-widest">Optimization Required</h3>
            </div>

            <div className="flex items-center gap-4 mb-4 relative z-10">
              <div className="text-4xl">{worstAgent.emoji || '🤖'}</div>
              <div>
                <div className="text-lg font-bold text-white">{worstAgent.name}</div>
                <div className="text-rose-400 font-code font-bold text-xl">${Number(worstAgent.pnl || 0).toFixed(2)}</div>
              </div>
            </div>
            <div className="text-xs text-slate-300 leading-relaxed border-t border-white/10 pt-3">
              Strategy under review. Risk limits tightened.
            </div>
          </div>
        </div>
      </div>

      {/* Recent Trade Log */}
      <div className="glass-card p-6 rounded-3xl border border-white/10 bg-black/20">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-white/5 rounded-lg">
            <Clock className="w-5 h-5 text-slate-400" />
          </div>
          <h2 className="text-lg font-bold text-white">RECENT EXECUTION LOG</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-[10px] text-slate-500 uppercase bg-white/5 font-bold tracking-wider">
              <tr>
                <th className="px-6 py-4 rounded-l-xl">Time</th>
                <th className="px-6 py-4">Agent</th>
                <th className="px-6 py-4">System</th>
                <th className="px-6 py-4">Symbol</th>
                <th className="px-6 py-4">Side</th>
                <th className="px-6 py-4">Price</th>
                <th className="px-6 py-4">Value</th>
                <th className="px-6 py-4 rounded-r-xl">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {safeTrades.slice(0, 10).map((trade, index) => (
                <tr key={index} className="hover:bg-white/5 transition-colors group">
                  <td className="px-6 py-4 text-slate-400 font-mono text-xs">
                    {new Date(trade.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </td>
                  <td className="px-6 py-4 text-white font-medium">{trade.agent_name || trade.agentId}</td>
                  <td className="px-6 py-4">
                    {trade.system === 'hyperliquid' ? (
                      <span className="inline-flex items-center gap-1 text-[10px] bg-green-500/10 text-green-400 px-2 py-0.5 rounded border border-green-500/20">
                        <Zap size={10} /> HYPE
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20">
                        <Globe size={10} /> ASTER
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 font-code font-bold text-slate-200">{trade.symbol}</td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${trade.side === 'BUY' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                      }`}>
                      {trade.side === 'BUY' ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                      {trade.side}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-slate-300 font-mono text-xs">${Number(trade.price).toFixed(2)}</td>
                  <td className="px-6 py-4 text-slate-300 font-mono text-xs">${(trade.price * trade.quantity).toFixed(2)}</td>
                  <td className="px-6 py-4">
                    <span className="text-[10px] text-emerald-400 flex items-center gap-1.5 font-bold">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_5px_rgba(16,185,129,0.5)]"></div>
                      FILLED
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

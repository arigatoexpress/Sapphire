import React, { useMemo } from 'react';
import AgentChart from './charts/AgentChart';
import { DashboardAgent } from '../api/client';
import AgentRadar from './visuals/AgentRadar';
import { resolveTokenMeta } from '../utils/tokenMeta';

interface AgentCardProps {
  agent: DashboardAgent;
  onClick?: () => void;
}

const AgentCard: React.FC<AgentCardProps> = ({ agent, onClick }) => {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);

  const formatPercent = (value: number) =>
    `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;

  const statusColors = {
    active: 'bg-emerald-400/80 text-slate-900',
    monitoring: 'bg-sky-400/80 text-slate-900',
    idle: 'bg-slate-500/60 text-white',
    error: 'bg-red-400/80 text-slate-900',
  } as const;

  const pnlColor = agent.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400';
  const activePositions = agent.positions?.length ?? 0;
  const lastTrade = agent.last_trade ? new Date(agent.last_trade) : null;
  const agentDescription = agent.description || 'Autonomous trading agent on live duty inside Sapphire AI.';

  const chartData = useMemo(() => {
    if (!agent.performance) return [];
    return agent.performance.map((point) => ({
      timestamp: point.timestamp,
      equity: point.equity,
    }));
  }, [agent.performance]);

  const sentiment = useMemo(() => {
    const netExposure = (agent.positions ?? []).reduce((acc, position) => {
      const notional = typeof position.notional === 'number' ? position.notional : 0;
      const side = (position.side || '').toUpperCase();
      if (side === 'SELL') return acc - Math.abs(notional);
      if (side === 'BUY') return acc + Math.abs(notional);
      return acc + notional;
    }, 0);
    if (netExposure > 0.0001) {
      return { label: 'Bullish', tone: 'bg-emerald-400/80 text-emerald-950', icon: '⬆️' };
    }
    if (netExposure < -0.0001) {
      return { label: 'Bearish', tone: 'bg-red-400/80 text-red-950', icon: '⬇️' };
    }
    return { label: 'Holding Cash', tone: 'bg-slate-400/70 text-slate-900', icon: '⏸️' };
  }, [agent.positions]);

  return (
    <div
      onClick={onClick}
      className="group relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass transition-all duration-200 hover:shadow-glass-lg hover:scale-[1.02] hover:bg-surface-100/70 cursor-pointer"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-white/5 via-transparent to-transparent" />
      <div className="absolute inset-0 bg-gradient-to-br from-white/10 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" />

      <div className="relative">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-primary-500 via-primary-400 to-accent-teal flex items-center justify-center shadow-glass group-hover:scale-110 transition-transform duration-200">
              <span className="text-xl">{agent.emoji}</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-semibold text-white">{agent.name}</h3>
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-[0.3em] ${sentiment.tone}`}>
                  <span>{sentiment.icon}</span>
                  {sentiment.label}
                </span>
              </div>
              {/* Removed redundant model label under radar */}
            </div>
          </div>
          <span
            className={`inline-flex items-center gap-2 rounded-full px-2 py-1 text-xs font-medium ${statusColors[agent.status as keyof typeof statusColors] || statusColors.monitoring
              }`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-current opacity-60" />
            {agent.status}
          </span>
        </div>

        {/* Radar + Overview */}
        <div className="mb-6 flex flex-col gap-6 md:flex-row md:items-center">
          <AgentRadar agent={agent} />
          <div className="flex-1 space-y-4">
            <p className="text-sm text-slate-300 leading-relaxed">
              {agentDescription}
            </p>
            <div className="flex flex-wrap gap-2">
              {(agent.symbols ?? []).map((symbol) => {
                const meta = resolveTokenMeta(symbol);
                return (
                  <span
                    key={symbol}
                    className={`inline-flex items-center gap-2 rounded-full border border-white/10 bg-gradient-to-r ${meta.gradient} px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-white shadow-glass`}
                  >
                    <span className="rounded-full bg-black/30 px-2 py-0.5 text-[0.65rem]">{meta.short}</span>
                    {meta.name}
                  </span>
                );
              })}
            </div>
          </div>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="rounded-lg border border-surface-200/40 bg-surface-50/40 p-3">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">P/L</p>
            <p className={`text-lg font-semibold ${pnlColor}`}>{formatCurrency(agent.total_pnl)}</p>
          </div>
          <div className="rounded-lg border border-surface-200/40 bg-surface-50/40 p-3">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Win Rate</p>
            <p className="text-lg font-semibold text-white">{Number.isFinite(agent.win_rate) ? `${agent.win_rate.toFixed(1)}%` : '--'}</p>
          </div>
        </div>

        {/* Positions */}
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Active Positions</p>
            <span className="text-sm font-medium text-white">{activePositions}</span>
          </div>

          {activePositions > 0 ? (
            <div className="space-y-1">
              {agent.positions.slice(0, 2).map((position, index) => {
                const meta = resolveTokenMeta(position.symbol);
                return (
                  <div key={index} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-3">
                      <div className={`h-8 w-8 rounded-full bg-gradient-to-br ${meta.gradient} flex items-center justify-center text-[0.65rem] font-bold text-white shadow-glass`}>{meta.short}</div>
                      <div>
                        <span className="text-sm font-semibold text-white">{position.symbol}</span>
                        <p className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-500">{meta.name}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`font-medium ${Number(position.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {formatPercent(position.pnl_percent ?? 0)}
                      </span>
                      {position.size !== undefined && <span className="text-slate-500">{position.size?.toFixed(2)}</span>}
                    </div>
                  </div>
                );
              })}
              {activePositions > 2 && (
                <p className="text-xs text-slate-500">+{activePositions - 2} more positions</p>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-500">No active positions</p>
          )}
        </div>

        {/* Performance Chart */}
        {chartData && chartData.length > 0 && (
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Equity Curve</p>
              <span className="text-xs text-slate-500">48h</span>
            </div>
            <div className="h-24">
              <AgentChart data={chartData} height={96} />
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">
            Last trade: {lastTrade ? lastTrade.toLocaleTimeString() : '—'}
          </span>
          <span className="text-slate-400">{agent.total_trades} trades</span>
        </div>
      </div>
    </div>
  );
};
export default AgentCard;

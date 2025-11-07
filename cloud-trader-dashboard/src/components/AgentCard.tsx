import React, { useMemo } from 'react';
import AgentChart from './charts/AgentChart';
import { DashboardAgent } from '../api/client';
import AgentRadar from './visuals/AgentRadar';
import { resolveTokenMeta } from '../utils/tokenMeta';

interface AgentCardProps {
  agent: DashboardAgent;
  onClick?: () => void;
  onViewHistory?: (agent: DashboardAgent) => void;
}

const modelPalette: Record<string, { label: string; subtitle: string; accent: string; icon: string; multiAgent?: boolean }> = {
  'fingpt-alpha': {
    label: 'FinGPT Alpha',
    subtitle: 'Open-source thesis engine \u2022 privacy-first \u2022 Parallel queries enabled',
    accent: 'from-brand-accent-blue/30 via-brand-accent-purple/20 to-brand-accent-green/30',
    icon: '🧠',
    multiAgent: true,
  },
  'lagllama-visionary': {
    label: 'Lag-LLaMA Visionary',
    subtitle: 'Probabilistic forecasts with anomaly guardrails \u2022 Parallel queries enabled',
    accent: 'from-brand-accent-purple/30 via-brand-accent-teal/20 to-brand-accent-blue/30',
    icon: '🦙',
    multiAgent: true,
  },
};

const statusTone: Record<string, string> = {
  active: 'bg-brand-accent-green/80 text-brand-midnight',
  monitoring: 'bg-brand-accent-teal/80 text-brand-midnight',
  idle: 'bg-brand-border/70 text-brand-ice',
  error: 'bg-red-400/80 text-brand-midnight',
};

const AgentCard: React.FC<AgentCardProps> = ({ agent, onClick, onViewHistory }) => {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);

  const formatPercent = (value: number) =>
    `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;

  const pnlColor = agent.total_pnl >= 0 ? 'text-brand-accent-green' : 'text-red-400';
  const activePositions = agent.positions?.length ?? 0;
  const lastTrade = agent.last_trade ? new Date(agent.last_trade) : null;
  const agentDescription =
    agent.description || 'Autonomous trading agent on live Sapphire mainnet, pairing quantitative edges with open-source AI.';

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
      return { label: 'Bullish bias', tone: 'bg-brand-accent-green/20 text-brand-accent-green', icon: '▲' };
    }
    if (netExposure < -0.0001) {
      return { label: 'Bearish bias', tone: 'bg-red-500/20 text-red-400', icon: '▼' };
    }
    return { label: 'Neutral stance', tone: 'bg-brand-border/40 text-brand-ice/70', icon: '◈' };
  }, [agent.positions]);

  const palette = modelPalette[agent.model ?? ''] ?? {
    label: agent.model ?? 'Autonomous Agent',
    subtitle: 'Hybrid quant + AI decision stack',
    accent: 'from-brand-accent-blue/30 via-brand-accent-teal/20 to-brand-accent-purple/30',
    icon: '✦',
  };

  return (
    <div
      onClick={onClick}
      className="sapphire-panel group relative overflow-hidden border border-brand-border/50 bg-brand-abyss/70 p-6 transition-all duration-200 hover:-translate-y-1 hover:border-brand-accent-blue/60 hover:shadow-sapphire-xl cursor-pointer"
    >
      <div className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${palette.accent} opacity-20 transition-opacity duration-200 group-hover:opacity-40`} />
      <div className="pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-200" style={{ backgroundImage: 'radial-gradient(circle at top, rgba(56, 189, 248, 0.25), transparent 55%)' }} />

      <div className="relative space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-accent-blue/20 text-2xl shadow-sapphire">
              <span aria-hidden>{palette.icon}</span>
            </div>
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-xl font-semibold text-brand-ice drop-shadow-sm">{agent.name}</h3>
                <span className={`sapphire-chip ${sentiment.tone}`}>
                  <span className="text-sm" aria-hidden>
                    {sentiment.icon}
                  </span>
                  {sentiment.label}
                </span>
              </div>
              <div className="rounded-full border border-brand-border/60 bg-brand-abyss/70 px-3 py-1 text-xs text-brand-ice/80">
                {palette.subtitle}
              </div>
            </div>
          </div>

          <span
            className={`inline-flex min-w-[8rem] items-center justify-center gap-2 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] ${
              statusTone[agent.status as keyof typeof statusTone] ?? statusTone.monitoring
            }`}
          >
            <span className="h-2 w-2 rounded-full bg-current shadow-inner" />
            {agent.status}
          </span>
        </div>

        {/* Model badge */}
        <div className="rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-4 shadow-sapphire-sm">
          <div className="flex flex-wrap items-center gap-4 text-sm text-brand-ice/80">
            <div className="flex items-center gap-2">
              <span className="text-2xl" aria-hidden>
                {palette.icon}
              </span>
              <div>
                <p className="text-brand-ice font-semibold tracking-[0.3em] uppercase">{palette.label}</p>
                <p className="text-xs text-brand-ice/60">Open-source, privacy-preserving AI inference routed via Sapphire</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-brand-ice/60">
              {palette.multiAgent && (
                <>
                  <span className="inline-flex items-center gap-1 rounded-full bg-brand-accent-green/20 px-2 py-1 text-brand-accent-green">
                    <span>⚡</span>
                    <span>Parallel Multi-Agent</span>
                  </span>
                  <span className="text-brand-border">•</span>
                </>
              )}
              <span>Community-safe reasoning logs</span>
              <span className="text-brand-border">•</span>
              <span>Edge-weighted with real-market data</span>
              {palette.multiAgent && (
                <>
                  <span className="text-brand-border">•</span>
                  <span>Risk threshold enforced</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Radar + Overview */}
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
          <div className="flex-1 min-w-[220px]">
            <AgentRadar agent={agent} />
          </div>
          <div className="flex flex-1 flex-col gap-4">
            <p className="text-sm text-brand-ice/70 leading-relaxed">
              {agentDescription}
            </p>
            <div className="flex flex-wrap gap-2">
              {(agent.symbols ?? []).map((symbol) => {
                const meta = resolveTokenMeta(symbol);
                return (
                  <span
                    key={symbol}
                    className={`inline-flex items-center gap-2 rounded-full border border-brand-border/60 bg-gradient-to-r ${meta.gradient} px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-brand-ice shadow-sapphire-sm`}
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-4 shadow-sapphire-sm">
            <p className="text-xs uppercase tracking-[0.32em] text-brand-ice/50">Cumulative P/L</p>
            <p className={`mt-1 text-2xl font-semibold ${pnlColor}`}>{formatCurrency(agent.total_pnl)}</p>
          </div>
          <div className="rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-4 shadow-sapphire-sm">
            <p className="text-xs uppercase tracking-[0.32em] text-brand-ice/50">Win Rate</p>
            <p className="mt-1 text-2xl font-semibold text-brand-ice">{Number.isFinite(agent.win_rate) ? `${agent.win_rate.toFixed(1)}%` : '--'}</p>
          </div>
        </div>

        {/* View History Button */}
        {onViewHistory && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onViewHistory(agent);
            }}
            className="w-full px-4 py-2 text-sm font-medium text-brand-ice bg-brand-accent-blue/20 hover:bg-brand-accent-blue/30 rounded-lg transition-colors border border-brand-accent-blue/30"
          >
            View Historical Performance →
          </button>
        )}

        {/* Positions */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs uppercase tracking-[0.3em] text-brand-ice/50">
            <span>Active Positions</span>
            <span className="text-brand-ice">{activePositions}</span>
          </div>

          {activePositions > 0 ? (
            <div className="space-y-2">
              {agent.positions.slice(0, 2).map((position, index) => {
                const meta = resolveTokenMeta(position.symbol);
                return (
                  <div key={index} className="flex items-center justify-between rounded-xl border border-brand-border/50 bg-brand-abyss/60 p-3 text-xs text-brand-ice">
                    <div className="flex items-center gap-3">
                      <div className={`flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br ${meta.gradient} text-[0.65rem] font-bold text-brand-ice shadow-sapphire-sm`}>
                        {meta.short}
                      </div>
                      <div>
                        <span className="text-sm font-semibold text-brand-ice">{position.symbol}</span>
                        <p className="text-[0.65rem] uppercase tracking-[0.2em] text-brand-ice/50">{meta.name}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      <span className={`font-medium ${Number(position.pnl) >= 0 ? 'text-brand-accent-green' : 'text-red-400'}`}>
                        {formatPercent(position.pnl_percent ?? 0)}
                      </span>
                      {position.size !== undefined && <span className="text-brand-ice/60">{position.size?.toFixed(2)}</span>}
                    </div>
                  </div>
                );
              })}
              {activePositions > 2 && <p className="text-xs text-brand-ice/60">+{activePositions - 2} additional exposures</p>}
            </div>
          ) : (
            <p className="text-xs text-brand-ice/60">No active positions \u2013 monitoring order book for optimal entries.</p>
          )}
        </div>

        {/* Performance Chart */}
        {chartData && chartData.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs uppercase tracking-[0.3em] text-brand-ice/50">
              <span>Equity Curve</span>
              <span className="text-brand-ice/60">48h</span>
            </div>
            <div className="h-28 rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-2 shadow-sapphire-sm">
              <AgentChart data={chartData} height={112} />
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-brand-ice/60">
          <span>Last trade: {lastTrade ? lastTrade.toLocaleTimeString() : '—'}</span>
          <span>{agent.total_trades} trades executed</span>
        </div>
      </div>
    </div>
  );
};

export default AgentCard;

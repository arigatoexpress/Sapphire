import React, { useState } from 'react';
import { resolveTokenMeta } from '../utils/tokenMeta';

interface PositionRow {
  symbol: string;
  side: string;
  size: number;
  entry_price: number;
  current_price: number;
  pnl: number;
  pnl_percent: number;
  leverage: number;
  model_used: string;
  timestamp: string;
}

interface LivePositionsProps {
  positions: any[];
}

const LivePositions: React.FC<LivePositionsProps> = ({ positions }) => {
  const [sortBy, setSortBy] = useState<'pnl' | 'symbol' | 'size'>('pnl');
  const [filterModel, setFilterModel] = useState<string>('all');
  const normalizedPositions: PositionRow[] = positions.map((pos) => {
    const notional = typeof pos.notional === 'number' ? pos.notional : 0;
    const size = typeof pos.size === 'number' ? pos.size : Math.abs(notional);
    const side = pos.side
      ? String(pos.side).toUpperCase()
      : notional >= 0
        ? 'LONG'
        : 'SHORT';

    return {
      symbol: pos.symbol ?? 'Unknown',
      side,
      size,
      entry_price: typeof pos.entry_price === 'number' ? pos.entry_price : 0,
      current_price: typeof pos.current_price === 'number' ? pos.current_price : 0,
      pnl: typeof pos.pnl === 'number' ? pos.pnl : 0,
      pnl_percent: typeof pos.pnl_percent === 'number' ? pos.pnl_percent : 0,
      leverage: typeof pos.leverage === 'number' ? pos.leverage : 1,
      model_used: pos.model_used ?? 'N/A',
      timestamp: pos.timestamp ?? new Date().toISOString(),
    };
  });

  const getPositionColor = (side: string) => {
    return side.toLowerCase() === 'long' ? 'text-green-600' : 'text-red-600';
  };

  const getPnLColor = (pnl: number) => {
    return pnl >= 0 ? 'text-green-600' : 'text-red-600';
  };

  // Filter and sort positions
  const filteredPositions = normalizedPositions.filter(pos =>
    filterModel === 'all' || pos.model_used === filterModel
  );

  const sortedPositions = [...filteredPositions].sort((a, b) => {
    switch (sortBy) {
      case 'pnl':
        return b.pnl - a.pnl;
      case 'symbol':
        return a.symbol.localeCompare(b.symbol);
      case 'size':
        return b.size - a.size;
      default:
        return 0;
    }
  });

  const totalPnL = normalizedPositions.reduce((sum, pos) => sum + pos.pnl, 0);
  const totalExposure = normalizedPositions.reduce((sum, pos) => sum + (pos.size * pos.entry_price), 0);

  const uniqueModels = Array.from(new Set(normalizedPositions.map(p => p.model_used)));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-surface-200/40 bg-surface-100/80 p-5 shadow-glass">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Positions</p>
          <p className="mt-2 text-3xl font-semibold text-white">{normalizedPositions.length}</p>
          <p className="mt-1 text-xs text-slate-500">Active exposures across all models</p>
        </div>
        <div className="rounded-2xl border border-surface-200/40 bg-surface-100/80 p-5 shadow-glass">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Total P&L</p>
          <p className={`mt-2 text-3xl font-semibold ${getPnLColor(totalPnL)}`}>${totalPnL.toFixed(2)}</p>
          <p className="mt-1 text-xs text-slate-500">Session-to-date realised + unrealised</p>
        </div>
        <div className="rounded-2xl border border-surface-200/40 bg-surface-100/80 p-5 shadow-glass">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Gross Exposure</p>
          <p className="mt-2 text-3xl font-semibold text-white">${totalExposure.toFixed(2)}</p>
          <p className="mt-1 text-xs text-slate-500">Calculated at entry notional</p>
        </div>
      </div>

      <div className="rounded-2xl border border-surface-200/40 bg-surface-100/80 p-5 shadow-glass">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Sort Order</p>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'pnl' | 'symbol' | 'size')}
                className="mt-2 rounded-xl border border-surface-200/40 bg-surface-50/40 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500/60"
              >
                <option value="pnl">P&L</option>
                <option value="symbol">Symbol</option>
                <option value="size">Size</option>
              </select>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Model Filter</p>
              <select
                value={filterModel}
                onChange={(e) => setFilterModel(e.target.value)}
                className="mt-2 rounded-xl border border-surface-200/40 bg-surface-50/40 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500/60"
              >
                <option value="all">All Models</option>
                {uniqueModels.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <p className="text-sm text-slate-400">
            Showing <span className="font-semibold text-slate-200">{sortedPositions.length}</span> of {normalizedPositions.length}
          </p>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/80 shadow-glass">
        <div className="border-b border-surface-200/40 px-6 py-4">
          <h2 className="text-xl font-semibold text-white">Live Positions</h2>
        </div>

        {sortedPositions.length === 0 ? (
          <div className="py-16 text-center text-slate-500">
            <p className="text-sm">No active positions · awaiting signal fulfilment</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-surface-200/40 text-sm">
              <thead className="bg-surface-50/40 text-xs uppercase tracking-[0.2em] text-slate-400">
                <tr>
                  <th className="px-6 py-3 text-left">Symbol & Model</th>
                  <th className="px-6 py-3 text-left">Side</th>
                  <th className="px-6 py-3 text-left">Size</th>
                  <th className="px-6 py-3 text-left">Entry</th>
                  <th className="px-6 py-3 text-left">Last</th>
                  <th className="px-6 py-3 text-left">P&L</th>
                  <th className="px-6 py-3 text-left">Lev</th>
                  <th className="px-6 py-3 text-left">Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-200/30 text-slate-200">
                {sortedPositions.map((position, index) => {
                  const meta = resolveTokenMeta(position.symbol);
                  return (
                    <tr key={index} className="hover:bg-surface-50/30">
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-3">
                          <div className={`h-9 w-9 rounded-full bg-gradient-to-br ${meta.gradient} flex items-center justify-center text-xs font-bold text-white shadow-glass`}>{meta.short}</div>
                          <div>
                            <p className="text-sm font-medium text-white">{position.symbol}</p>
                            <p className="text-xs text-slate-500">{meta.name} · {position.model_used}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-3">
                        <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${getPositionColor(position.side)} bg-white/10`}>
                          {position.side.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-slate-200">{position.size.toFixed(4)}</td>
                      <td className="px-6 py-3 text-slate-200">${position.entry_price.toFixed(2)}</td>
                      <td className="px-6 py-3 text-slate-200">${position.current_price.toFixed(2)}</td>
                      <td className="px-6 py-3">
                        <div className={`font-semibold ${getPnLColor(position.pnl)}`}>${position.pnl.toFixed(2)}</div>
                        <div className={`text-xs ${getPnLColor(position.pnl_percent)}`}>
                          ({position.pnl_percent >= 0 ? '+' : ''}{position.pnl_percent.toFixed(2)}%)
                        </div>
                      </td>
                      <td className="px-6 py-3 text-slate-200">{position.leverage}x</td>
                      <td className="px-6 py-3 text-slate-500">
                        {new Date(position.timestamp).toLocaleTimeString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default LivePositions;

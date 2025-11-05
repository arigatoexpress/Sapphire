import React, { useMemo } from 'react';
import { DashboardPortfolio } from '../api/client';
import { resolveTokenMeta } from '../utils/tokenMeta';

interface PortfolioCardProps {
  portfolio?: DashboardPortfolio;
}

const PortfolioCard: React.FC<PortfolioCardProps> = ({ portfolio }) => {
  const positions = useMemo(() => {
    if (!portfolio?.positions) return [];
    return Object.values(portfolio.positions).map((position) => ({
      symbol: position.symbol ?? 'Unknown',
      notional: position.notional ?? 0,
    }));
  }, [portfolio]);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatMaskedCurrency = (_value: number) => '%s';

  if (!portfolio) {
    return (
      <div className="rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass">
        <div className="animate-pulse space-y-4">
          <div className="h-5 w-32 rounded bg-slate-600/30" />
          <div className="grid grid-cols-3 gap-4">
            <div className="h-16 rounded-xl bg-slate-600/10" />
            <div className="h-16 rounded-xl bg-slate-600/10" />
            <div className="h-16 rounded-xl bg-slate-600/10" />
          </div>
        </div>
      </div>
    );
  }

  const balance = portfolio.balance ?? 0;
  const exposure = portfolio.total_exposure ?? 0;
  const available = Math.max(balance - exposure, 0);

  return (
    <div className="relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass">
      <div className="absolute inset-0 bg-gradient-to-br from-primary-500/5 via-transparent to-transparent" />
      <div className="relative flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Portfolio Overview</p>
          <h3 className="mt-2 text-2xl font-semibold text-white">{formatMaskedCurrency(balance)}</h3>
          <p className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">
            Source · {portfolio.source ?? 'local cache'}
          </p>
        </div>
        {portfolio.alerts && portfolio.alerts.length > 0 && (
          <span className="rounded-full bg-accent-amber/20 px-4 py-1 text-xs font-medium text-accent-amber shadow-glass">
            {portfolio.alerts[0]}
          </span>
        )}
      </div>

      <div className="relative mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-surface-200/40 bg-surface-50/40 p-4">
          <p className="text-[0.65rem] uppercase tracking-[0.3em] text-slate-500">Balance</p>
          <p className="mt-2 text-xl font-semibold text-white">{formatMaskedCurrency(balance)}</p>
        </div>
        <div className="rounded-xl border border-surface-200/40 bg-surface-50/40 p-4">
          <p className="text-[0.65rem] uppercase tracking-[0.3em] text-slate-500">Exposure</p>
          <p className="mt-2 text-xl font-semibold text-white">{formatCurrency(exposure)}</p>
        </div>
        <div className="rounded-xl border border-surface-200/40 bg-surface-50/40 p-4">
          <p className="text-[0.65rem] uppercase tracking-[0.3em] text-slate-500">Available</p>
          <p className="mt-2 text-xl font-semibold text-white">{formatCurrency(available)}</p>
        </div>
      </div>

      <div className="relative mt-6">
        <h4 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">Open Exposure</h4>
        {positions.length > 0 ? (
          <div className="mt-3 space-y-2">
            {positions.map((position) => {
              const meta = resolveTokenMeta(position.symbol);
              return (
                <div
                  key={position.symbol}
                  className="flex items-center justify-between rounded-xl border border-surface-200/40 bg-surface-50/30 px-4 py-3 text-sm text-slate-200"
                >
                  <div className="flex items-center gap-3">
                    <div className={`h-9 w-9 rounded-full bg-gradient-to-br ${meta.gradient} flex items-center justify-center text-xs font-bold text-white shadow-glass`}>{meta.short}</div>
                    <div>
                      <p className="font-medium text-white">{position.symbol}</p>
                      <p className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-500">{meta.name}</p>
                    </div>
                  </div>
                  <p className="text-base font-semibold text-white">{formatCurrency(Math.abs(position.notional || 0))}</p>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-dashed border-surface-200/40 bg-surface-50/20 px-6 py-10 text-center text-slate-500">
            <p className="text-sm">No active positions · risk budget fully available</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default PortfolioCard;

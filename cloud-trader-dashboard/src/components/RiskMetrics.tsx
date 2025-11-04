import React, { useMemo } from 'react';
import { DashboardPortfolio } from '../api/client';

interface RiskMetricsProps {
  portfolio?: DashboardPortfolio;
}

const RiskMetrics: React.FC<RiskMetricsProps> = ({ portfolio }) => {
  const derived = useMemo(() => {
    if (!portfolio) {
      return {
        balance: 0,
        exposure: 0,
        positions: [] as Array<{ symbol: string; notional: number }>,
      };
    }

    const balance = portfolio.balance ?? 0;
    const exposure = portfolio.total_exposure ?? 0;
    const positions = portfolio.positions
      ? Object.values(portfolio.positions).map((position) => ({
        symbol: position.symbol ?? 'Unknown',
        notional: position.notional ?? 0,
      }))
      : [];

    return { balance, exposure, positions };
  }, [portfolio]);


  const calculateRiskMetrics = () => {
    const { balance, exposure, positions } = derived;
    if (balance === 0 && exposure === 0) return null;

    const availableBalance = Math.max(balance - exposure, 0);

    // Calculate leverage ratio
    const leverageRatio = balance > 0 ? (exposure / balance) * 100 : 0;

    // Calculate position concentration (largest position as % of total exposure)
    const positionSizes = positions.map(p => Math.abs(p.notional));
    const maxPositionSize = Math.max(...positionSizes, 0);
    const concentrationRisk = exposure > 0 ? (maxPositionSize / exposure) * 100 : 0;

    // Risk levels
    const getRiskLevel = (value: number, thresholds: { low: number; medium: number; high: number }) => {
      if (value <= thresholds.low) return { level: 'low', color: 'text-green-600', bg: 'bg-green-50' };
      if (value <= thresholds.medium) return { level: 'medium', color: 'text-yellow-600', bg: 'bg-yellow-50' };
      return { level: 'high', color: 'text-red-600', bg: 'bg-red-50' };
    };

    return {
      totalBalance: balance,
      marginUsed: exposure,
      availableBalance,
      leverageRatio,
      concentrationRisk,
      leverageRisk: getRiskLevel(leverageRatio, { low: 25, medium: 50, high: 75 }),
      concentrationRiskLevel: getRiskLevel(concentrationRisk, { low: 30, medium: 50, high: 70 }),
    };
  };

  const riskMetrics = calculateRiskMetrics();

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number) => {
    return `${value.toFixed(1)}%`;
  };

  if (!portfolio) {
    return (
      <div className="rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-56 rounded bg-slate-600/30" />
          <div className="grid grid-cols-2 gap-3">
            <div className="h-20 rounded-xl bg-slate-600/10" />
            <div className="h-20 rounded-xl bg-slate-600/10" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 text-slate-200 shadow-glass">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Risk Envelope</p>
            <h3 className="mt-2 text-2xl font-semibold text-white">Exposure Diagnostics</h3>
          </div>
          <div className="rounded-full border border-surface-200/60 bg-surface-50/60 px-3 py-1 text-xs text-slate-400">
            Margin budget {formatPercent(riskMetrics?.leverageRatio ?? 0)}
          </div>
        </div>

        {riskMetrics && (
          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-surface-200/40 bg-surface-50/40 p-4">
            <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-300">Leverage Ratio</p>
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${riskMetrics.leverageRisk.bg} ${riskMetrics.leverageRisk.color}`}>
                  {riskMetrics.leverageRisk.level.toUpperCase()}
                </span>
              </div>
              <p className="mt-3 text-2xl font-semibold text-white">{formatPercent(riskMetrics.leverageRatio)}</p>
              <p className="mt-1 text-xs text-slate-500">Total exposure vs equity</p>
            </div>

            <div className="rounded-xl border border-surface-200/40 bg-surface-50/40 p-4">
            <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-300">Concentration Risk</p>
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${riskMetrics.concentrationRiskLevel.bg} ${riskMetrics.concentrationRiskLevel.color}`}>
                  {riskMetrics.concentrationRiskLevel.level.toUpperCase()}
                </span>
              </div>
              <p className="mt-3 text-2xl font-semibold text-white">{formatPercent(riskMetrics.concentrationRisk)}</p>
              <p className="mt-1 text-xs text-slate-500">Largest position share of gross exposure</p>
            </div>

            <div className="md:col-span-2">
              <div className="rounded-xl border border-surface-200/40 bg-surface-50/30 p-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Margin Utilisation</span>
                  <span className="font-medium text-white">
                  {formatCurrency(riskMetrics.marginUsed)} / {formatCurrency(riskMetrics.totalBalance)}
                </span>
              </div>
                <div className="mt-3 h-2 rounded-full bg-slate-700/60">
                <div
                    className="h-full rounded-full bg-gradient-to-r from-primary-500 via-accent-teal to-accent-emerald"
                  style={{ width: `${Math.min((riskMetrics.marginUsed / riskMetrics.totalBalance) * 100, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

    </div>
  );
};

export default RiskMetrics;


import React from 'react';
import { Activity, DollarSign, TrendingUp, Users, Zap } from 'lucide-react';

interface SystemMetrics {
  pnl: number;
  volume: number;
  fees: number;
  win_rate: number;
  active_agents: number;
  swept_profits: number;
}

interface SystemComparisonBoardProps {
  asterMetrics: SystemMetrics;
  hyperliquidMetrics: SystemMetrics;
}

const MetricRow = ({ label, asterValue, hlValue, format = 'currency', inverse = false }: any) => {
  const formatValue = (val: number) => {
    if (format === 'currency') return `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (format === 'percent') return `${val.toFixed(1)}%`;
    return val.toLocaleString();
  };

  // Determine winner
  let asterWin = asterValue > hlValue;
  if (inverse) asterWin = asterValue < hlValue; // Lower fees is better
  if (asterValue === hlValue) asterWin = false; // Tie

  const hlWin = !asterWin && asterValue !== hlValue;

  return (
    <div className="grid grid-cols-3 items-center py-3 border-b border-slate-700/30 last:border-0">
      <div className={`text-right font-mono font-bold ${asterWin ? 'text-blue-400' : 'text-slate-400'}`}>
        {formatValue(asterValue)}
      </div>
      <div className="text-center text-xs text-slate-500 uppercase font-semibold tracking-wider">
        {label}
      </div>
      <div className={`text-left font-mono font-bold ${hlWin ? 'text-emerald-400' : 'text-slate-400'}`}>
        {formatValue(hlValue)}
      </div>
    </div>
  );
};

export const SystemComparisonBoard: React.FC<SystemComparisonBoardProps> = ({ asterMetrics, hyperliquidMetrics }) => {
  return (
    <div className="relative bg-slate-900/80 backdrop-blur-xl rounded-3xl border border-slate-700/50 p-6 overflow-hidden">
      {/* Background Glows */}
      <div className="absolute top-0 left-0 w-1/2 h-full bg-blue-500/5 blur-3xl -z-10"></div>
      <div className="absolute top-0 right-0 w-1/2 h-full bg-emerald-500/5 blur-3xl -z-10"></div>

      {/* Header */}
      <div className="flex justify-between items-center mb-8 relative">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/20 flex items-center justify-center border border-blue-500/30">
            <GlobeIcon className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Aster Bull Agents</h3>
            <p className="text-xs text-blue-400 font-mono">CLOUD TRADER</p>
          </div>
        </div>

        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
          <div className="w-12 h-12 rounded-full bg-slate-800 border border-slate-600 flex items-center justify-center shadow-xl z-10">
            <span className="text-slate-400 font-black italic text-sm">VS</span>
          </div>
        </div>

        <div className="flex items-center gap-3 text-right">
          <div>
            <h3 className="text-lg font-bold text-white">Hype Bull Agents</h3>
            <p className="text-xs text-emerald-400 font-mono">HYPERLIQUID</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center border border-emerald-500/30">
            <Zap className="w-6 h-6 text-emerald-400" />
          </div>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="space-y-1">
        <MetricRow 
          label="Net Profit (PnL)" 
          asterValue={asterMetrics.pnl} 
          hlValue={hyperliquidMetrics.pnl} 
        />
        <MetricRow 
          label="Trading Volume" 
          asterValue={asterMetrics.volume} 
          hlValue={hyperliquidMetrics.volume} 
        />
        <MetricRow 
          label="Win Rate" 
          asterValue={asterMetrics.win_rate} 
          hlValue={hyperliquidMetrics.win_rate} 
          format="percent"
        />
        <MetricRow 
          label="Fees Paid" 
          asterValue={asterMetrics.fees} 
          hlValue={hyperliquidMetrics.fees} 
          inverse={true}
        />
        <MetricRow 
          label="Active Agents" 
          asterValue={asterMetrics.active_agents} 
          hlValue={hyperliquidMetrics.active_agents} 
          format="number"
        />
        <MetricRow 
          label="Swept Profits" 
          asterValue={asterMetrics.swept_profits} 
          hlValue={hyperliquidMetrics.swept_profits} 
        />
      </div>

      {/* Footer Status */}
      <div className="mt-6 pt-4 border-t border-slate-700/50 flex justify-between text-xs font-mono text-slate-500">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></div>
          ONLINE
        </div>
        <div className="flex items-center gap-2">
          ONLINE
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
        </div>
      </div>
    </div>
  );
};

// Helper Icon
const GlobeIcon = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <circle cx="12" cy="12" r="10" />
    <line x1="2" x2="22" y1="12" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
);


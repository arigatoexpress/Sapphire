import React from 'react';
import { ArrowUpRight, ArrowDownRight, Clock, Filter, Search } from 'lucide-react';
import { format } from 'date-fns';

interface Trade {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  type: 'MARKET' | 'LIMIT';
  price: number;
  quantity: number;
  total: number;
  timestamp: string;
  status: 'FILLED' | 'PENDING' | 'FAILED';
  agentId: string;
}

interface Props {
  trades: Trade[];
}

export const TradeActivityFeed: React.FC<Props> = ({ trades }) => {
  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-2xl backdrop-blur-sm flex flex-col h-[500px]">
      <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
        <h3 className="font-semibold text-white">Trade Activity</h3>
        <div className="flex gap-2">
          <button className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 transition-colors">
            <Search size={16} />
          </button>
          <button className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 transition-colors">
            <Filter size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-left border-collapse">
          <thead className="bg-slate-900/50 sticky top-0 z-10 text-xs font-medium text-slate-400 uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3 text-right">Price</th>
              <th className="px-4 py-3 text-right">Total</th>
              <th className="px-4 py-3 text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50 text-sm">
            {(!trades || trades.length === 0) ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  No trades recorded yet today
                </td>
              </tr>
            ) : (
              trades.map((trade) => (
                <tr key={trade.id} className="hover:bg-slate-800/30 transition-colors group">
                  <td className="px-4 py-3 text-slate-400 whitespace-nowrap font-mono text-xs">
                    {format(new Date(trade.timestamp), 'HH:mm:ss')}
                  </td>
                  <td className="px-4 py-3 font-medium text-white">
                    {trade.symbol}
                    <div className="text-[10px] text-slate-500 font-normal hidden group-hover:block">
                      Via {trade.agentId}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${
                      trade.side === 'BUY'
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-rose-500/10 text-rose-400'
                    }`}>
                      {trade.side === 'BUY' ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                      {trade.side}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-slate-300 font-mono">
                    ${(trade.price ?? 0).toFixed((trade.price ?? 0) < 1 ? 4 : 2)}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-300 font-mono">
                    ${(trade.total ?? 0).toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <StatusBadge status={trade.status} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const StatusBadge = ({ status }: { status: string }) => {
  const styles = {
    FILLED: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    PENDING: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    FAILED: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  }[status] || 'bg-slate-500/10 text-slate-400';

  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-medium border ${styles}`}>
      {status}
    </span>
  );
};

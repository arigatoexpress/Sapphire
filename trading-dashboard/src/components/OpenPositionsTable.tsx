import React from 'react';
import { ArrowUpRight, ArrowDownRight, Target, Octagon } from 'lucide-react';

interface Position {
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  pnl: number;
  agent: string;
  tp?: number;
  sl?: number;
}

interface Props {
  positions: Position[];
}

export const OpenPositionsTable: React.FC<Props> = ({ positions }) => {
  if (!positions || positions.length === 0) return null;

  return (
    <div className="bg-slate-900/50 border border-slate-800 rounded-2xl backdrop-blur-sm flex flex-col overflow-hidden">
      <div className="p-4 border-b border-slate-800 bg-slate-900/80">
        <h3 className="font-semibold text-white flex items-center gap-2">
          <span className="text-emerald-400">●</span> Live Positions
        </h3>
      </div>
      
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-900/50 text-xs font-medium text-slate-400 uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3 text-right">Entry</th>
              <th className="px-4 py-3 text-right">TP / SL</th>
              <th className="px-4 py-3 text-right">PnL</th>
              <th className="px-4 py-3 text-right">Agent</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {positions.map((pos, idx) => (
              <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-4 py-3 font-medium text-white">{pos.symbol}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${
                    pos.side === 'BUY' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                  }`}>
                    {pos.side === 'BUY' ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                    {pos.side}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-slate-300 font-mono">
                  ${pos.entry_price.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right font-mono">
                  <div className="flex flex-col items-end gap-1">
                    {pos.tp && (
                      <span className="text-emerald-400 text-xs flex items-center gap-1">
                        <Target size={10} /> {pos.tp.toLocaleString()}
                      </span>
                    )}
                    {pos.sl && (
                      <span className="text-rose-400 text-xs flex items-center gap-1">
                        <Octagon size={10} /> {pos.sl.toLocaleString()}
                      </span>
                    )}
                  </div>
                </td>
                <td className={`px-4 py-3 text-right font-bold ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {pos.pnl >= 0 ? '+' : ''}{pos.pnl.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-right text-slate-400 text-xs">
                  {pos.agent}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};


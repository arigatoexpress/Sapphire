import React, { useMemo } from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Wallet, 
  Target, 
  PieChart, 
  BarChart3,
  Globe,
  Zap,
  Activity
} from 'lucide-react';

interface PortfolioProps {
  totalValue: number;
  totalPnl: number;
  pnlPercent: number;
  trades: any[];
  openPositions: any[];
}

export const Portfolio: React.FC<PortfolioProps> = ({ totalValue, totalPnl, pnlPercent, trades, openPositions }) => {
  
  // Calculate real asset allocation
  const positionGroups: { [key: string]: number } = {};
  let totalPositionValue = 0;

  openPositions.forEach(pos => {
    const val = pos.quantity * (pos.current_price || pos.entry_price);
    positionGroups[pos.symbol] = (positionGroups[pos.symbol] || 0) + val;
    totalPositionValue += val;
  });

  const cashValue = Math.max(0, totalValue - totalPositionValue);
  
  const allocations = Object.entries(positionGroups).map(([symbol, value]) => ({
    symbol,
    value,
    percentage: (value / totalValue) * 100,
    type: 'Crypto'
  }));

  if (cashValue > 1) {
      allocations.push({
          symbol: 'USDT (Cash)',
          value: cashValue,
          percentage: (cashValue / totalValue) * 100,
          type: 'Stablecoin'
      });
  }

  allocations.sort((a, b) => b.value - a.value);

  // Separate Positions for Duality View
  const asterPositions = useMemo(() => openPositions.filter(p => !p.system || p.system === 'aster'), [openPositions]);
  const hypePositions = useMemo(() => openPositions.filter(p => p.system === 'hyperliquid'), [openPositions]);

  const stats = [
    {
      title: 'NET LIQUIDITY',
      value: `$${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      change: `${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%`,
      icon: Wallet,
      gradient: 'from-blue-500/20 to-purple-500/20',
      color: 'text-blue-400',
      isPositive: pnlPercent >= 0
    },
    {
      title: '24H PNL',
      value: `${totalPnl >= 0 ? '+' : ''}$${Math.abs(totalPnl).toFixed(2)}`,
      change: 'Realized + Unrealized',
      icon: TrendingUp,
      gradient: totalPnl >= 0 ? 'from-emerald-500/20 to-green-500/20' : 'from-rose-500/20 to-red-500/20',
      color: totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400',
      isPositive: totalPnl >= 0
    },
    {
      title: 'EXPOSURE',
      value: `${((totalPositionValue / totalValue) * 100).toFixed(1)}%`,
      change: 'Capital Deployed',
      icon: Activity,
      gradient: 'from-orange-500/20 to-amber-500/20',
      color: 'text-orange-400',
      isPositive: true
    },
    {
      title: 'ACTIVE BETS',
      value: openPositions.length.toString(),
      change: `${asterPositions.length} Aster / ${hypePositions.length} Hype`,
      icon: Target,
      gradient: 'from-cyan-500/20 to-blue-500/20',
      color: 'text-cyan-400',
      isPositive: true
    }
  ];

  return (
    <div className="space-y-8 font-sans">
      {/* Background Effects */}
      <div className="holographic-grid" />
      <div className="fixed inset-0 pointer-events-none">
         <div className="absolute top-[10%] right-[10%] w-[30%] h-[30%] bg-purple-900/10 rounded-full blur-[120px] animate-pulse-slow" />
      </div>

      {/* Header */}
      <div className="glass-card p-8 rounded-3xl relative overflow-hidden">
         <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500"></div>
         
         <div className="relative z-10 flex flex-col md:flex-row justify-between items-center gap-6">
           <div>
             <h1 className="text-3xl font-black text-white mb-2 flex items-center gap-3 tracking-tight">
               <div className="p-2 bg-white/5 rounded-xl">
                 <PieChart className="w-6 h-6 text-purple-400" />
               </div>
               PORTFOLIO ALLOCATION
             </h1>
             <p className="text-white/40 font-mono text-xs uppercase tracking-widest ml-1">
               System-Wide Asset Distribution
             </p>
           </div>
           
           <div className="flex gap-3">
              <div className="px-4 py-2 bg-white/5 border border-white/10 rounded-xl backdrop-blur-sm text-right">
                 <div className="text-[10px] text-white/40 uppercase font-bold tracking-wider">Risk Model</div>
                 <div className="text-emerald-400 font-code font-bold text-sm">DYNAMIC</div>
              </div>
           </div>
         </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat, index) => (
          <div key={index} className="glass-card p-6 rounded-2xl relative overflow-hidden group hover:-translate-y-1 transition-all duration-300">
             <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${stat.gradient} rounded-bl-[100px] -mr-8 -mt-8 transition-all group-hover:scale-110 opacity-50`}></div>
            
            <div className="relative z-10">
              <div className="flex justify-between items-start mb-4">
                <div className={`p-3 rounded-xl bg-white/5 border border-white/10 ${stat.color}`}>
                  <stat.icon className="w-5 h-5" />
                </div>
                {index === 1 && (
                   <div className={`flex items-center gap-1 text-xs font-bold ${stat.isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                     {stat.isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                   </div>
                )}
              </div>
              
              <div>
                <p className="text-white/40 text-[10px] font-bold uppercase tracking-wider mb-1">{stat.title}</p>
                <h3 className="text-2xl font-code font-bold text-white">{stat.value}</h3>
                <p className="text-xs text-white/30 mt-1 font-mono">{stat.change}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Split Position View */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* ASTER POSITIONS */}
        <div className="glass-card rounded-3xl border border-blue-500/20 bg-blue-950/5 overflow-hidden">
          <div className="p-6 border-b border-white/5 flex justify-between items-center bg-blue-500/5">
            <div className="flex items-center gap-3">
              <Globe className="w-5 h-5 text-blue-400" />
              <h2 className="font-bold text-lg">ASTER POSITIONS</h2>
            </div>
            <span className="text-xs font-code text-blue-300 bg-blue-500/10 px-2 py-1 rounded border border-blue-500/20">{asterPositions.length} ACTIVE</span>
          </div>
          <div className="p-6 space-y-3">
            {asterPositions.length === 0 && (
              <div className="text-center py-12 text-white/20 font-mono text-sm">NO ACTIVE POSITIONS</div>
            )}
            {asterPositions.map((pos: any, i: number) => (
              <div key={i} className="group flex items-center justify-between p-4 bg-white/5 border border-white/5 rounded-xl hover:border-blue-500/30 transition-all">
                <div className="flex items-center gap-4">
                  <div className={`w-1 h-8 rounded-full ${pos.side === 'BUY' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  <div>
                    <div className="font-code font-bold text-white">{pos.symbol}</div>
                    <div className={`text-[10px] font-bold uppercase ${pos.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pos.side} • {pos.quantity} Units
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-white/40 mb-1">ENTRY PRICE</div>
                  <div className="font-mono text-sm text-slate-300">${Number(pos.entry_price).toFixed(4)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* HYPE POSITIONS */}
        <div className="glass-card rounded-3xl border border-green-500/20 bg-green-950/5 overflow-hidden">
          <div className="p-6 border-b border-white/5 flex justify-between items-center bg-green-500/5">
            <div className="flex items-center gap-3">
              <Zap className="w-5 h-5 text-emerald-400" />
              <h2 className="font-bold text-lg">HYPE POSITIONS</h2>
            </div>
            <span className="text-xs font-code text-emerald-300 bg-emerald-500/10 px-2 py-1 rounded border border-emerald-500/20">{hypePositions.length} ACTIVE</span>
          </div>
          <div className="p-6 space-y-3">
            {hypePositions.length === 0 && (
              <div className="text-center py-12 text-white/20 font-mono text-sm">NO ACTIVE POSITIONS</div>
            )}
            {hypePositions.map((pos: any, i: number) => (
              <div key={i} className="group flex items-center justify-between p-4 bg-white/5 border border-white/5 rounded-xl hover:border-emerald-500/30 transition-all">
                <div className="flex items-center gap-4">
                  <div className={`w-1 h-8 rounded-full ${pos.side === 'BUY' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  <div>
                    <div className="font-code font-bold text-white">{pos.symbol}</div>
                    <div className={`text-[10px] font-bold uppercase ${pos.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {pos.side} • {pos.quantity} Units
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-white/40 mb-1">ENTRY PRICE</div>
                  <div className="font-mono text-sm text-slate-300">${Number(pos.entry_price).toFixed(4)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* Asset Allocation Bar */}
      <div className="glass-card p-8 rounded-3xl">
        <h2 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-white/60" />
          ALLOCATION BREAKDOWN
        </h2>
        
        <div className="flex h-4 w-full rounded-full overflow-hidden mb-6 bg-white/5">
          {allocations.map((asset, i) => (
            <div 
              key={asset.symbol}
              className={`h-full hover:opacity-80 transition-opacity`}
              style={{ 
                width: `${asset.percentage}%`,
                backgroundColor: `hsl(${210 + (i * 40)}, 70%, 60%)`
              }}
              title={`${asset.symbol}: ${asset.percentage.toFixed(1)}%`}
            />
          ))}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {allocations.map((asset, i) => (
            <div key={asset.symbol} className="flex items-center gap-3 p-3 rounded-lg bg-white/5 border border-white/5">
               <div 
                 className="w-2 h-2 rounded-full" 
                 style={{ backgroundColor: `hsl(${210 + (i * 40)}, 70%, 60%)` }}
               />
               <div>
                 <div className="text-xs font-bold text-white">{asset.symbol}</div>
                 <div className="text-[10px] font-mono text-white/50">{asset.percentage.toFixed(1)}%</div>
               </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Portfolio;

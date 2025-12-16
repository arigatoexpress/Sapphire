import React, { useMemo } from 'react';
import {
    Briefcase,
    TrendingUp,
    TrendingDown,
    PieChart,
    ArrowUpRight,
    ArrowDownRight,
    DollarSign,
    Activity,
    Wallet
} from 'lucide-react';
import { useTradingData } from '../contexts/TradingContext';
import { PieChart as RechartsPie, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

const PortfolioStat: React.FC<{ label: string; value: string; trend?: string; trendColor?: string; icon?: React.ReactNode }> = ({ label, value, trend, trendColor, icon }) => (
    <div className="relative overflow-hidden p-6 rounded-2xl bg-[#0a0b10] border border-white/5 hover:border-blue-500/20 transition-all duration-300 group">
        <div className="flex items-start justify-between mb-4">
            <div className="p-3 rounded-xl bg-white/5 text-slate-400 group-hover:bg-blue-500/10 group-hover:text-blue-400 transition-colors">
                {icon || <Activity size={20} />}
            </div>
            {trend && (
                <div className={`flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-full ${trend.startsWith('+') ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                    {trend.startsWith('+') ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                    {trend}
                </div>
            )}
        </div>
        <div>
            <div className="text-slate-500 text-xs font-bold uppercase tracking-widest mb-1">{label}</div>
            <div className="text-3xl font-black text-white tracking-tight">{value}</div>
        </div>

        {/* Ambient Glow */}
        <div className="absolute -bottom-12 -right-12 w-32 h-32 bg-blue-500/5 rounded-full blur-3xl group-hover:bg-blue-500/10 transition-colors pointer-events-none" />
    </div>
);

export const PortfolioPro: React.FC = () => {
    const { portfolio_value, total_pnl, total_pnl_percent, open_positions, cash_balance } = useTradingData();

    // Calculate Asset Allocation for Chart
    const allocationData = useMemo(() => {
        // Assume cash is one slice
        const cryptoExposure = open_positions.reduce((acc, pos) => acc + (pos.size * pos.mark_price), 0);
        return [
            { name: 'Cash / Stablecoins', value: cash_balance },
            { name: 'Active Positions', value: cryptoExposure }
        ];
    }, [cash_balance, open_positions]);

    return (
        <div className="max-w-7xl mx-auto pb-32">

            {/* Header */}
            <div className="mb-8 flex items-end justify-between">
                <div>
                    <h1 className="text-3xl font-black text-white mb-2 flex items-center gap-3">
                        <Briefcase className="text-emerald-400" /> INSTITUTIONAL PORTFOLIO
                    </h1>
                    <p className="text-slate-400 font-mono text-sm max-w-2xl">
                        Real-time asset Breakdown, PnL analysis, and exposure tracking.
                    </p>
                </div>
                <div className="text-right hidden sm:block">
                    <div className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1">Total Equity</div>
                    <div className="text-4xl font-black text-white">${portfolio_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                <PortfolioStat
                    label="Total Equity"
                    value={`$${portfolio_value.toLocaleString()}`}
                    trend={total_pnl >= 0 ? `+${total_pnl_percent.toFixed(2)}%` : `${total_pnl_percent.toFixed(2)}%`}
                    trendColor={total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}
                    icon={<Wallet size={20} />}
                />
                <PortfolioStat
                    label="Unrealized PnL"
                    value={`${total_pnl >= 0 ? '+' : ''}$${total_pnl.toFixed(2)}`}
                    icon={<TrendingUp size={20} />}
                />
                <PortfolioStat
                    label="Available Cash"
                    value={`$${cash_balance.toLocaleString()}`}
                    icon={<DollarSign size={20} />}
                />
                <PortfolioStat
                    label="Active Positions"
                    value={open_positions.length.toString()}
                    icon={<PieChart size={20} />}
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

                {/* Main Content: Holdings Table */}
                <div className="lg:col-span-2 space-y-6">
                    <div className="flex items-center justify-between">
                        <h3 className="text-lg font-bold text-white flex items-center gap-2">
                            <Activity size={18} className="text-blue-500" /> Live Holdings
                        </h3>
                    </div>

                    <div className="bg-[#0a0b10] border border-white/10 rounded-2xl overflow-hidden">
                        {open_positions.length === 0 ? (
                            <div className="p-12 text-center text-slate-500 flex flex-col items-center gap-4">
                                <div className="w-16 h-16 rounded-full bg-slate-800/50 flex items-center justify-center">
                                    <Briefcase size={32} className="opacity-20" />
                                </div>
                                <p>No active positions. Scanning market...</p>
                            </div>
                        ) : (
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="bg-white/5 text-xs text-slate-400 font-bold uppercase tracking-wider">
                                        <th className="p-4 rounded-tl-xl">Asset</th>
                                        <th className="p-4 text-right">Size</th>
                                        <th className="p-4 text-right">Entry</th>
                                        <th className="p-4 text-right">Mark</th>
                                        <th className="p-4 text-right rounded-tr-xl">PnL</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/5">
                                    {open_positions.map((pos, i) => {
                                        const isProfit = pos.pnl >= 0;
                                        return (
                                            <tr key={i} className="hover:bg-white/5 transition-colors group">
                                                <td className="p-4">
                                                    <div className="flex items-center gap-3">
                                                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center font-bold text-xs ${pos.side === 'BUY' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                                                            {pos.symbol.substring(0, 3)}
                                                        </div>
                                                        <div>
                                                            <div className="font-bold text-white text-sm">{pos.symbol}</div>
                                                            <div className="text-[10px] font-mono text-slate-500">{pos.leverage}x {pos.side}</div>
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className="p-4 text-right font-mono text-sm text-slate-300">
                                                    {pos.size.toFixed(4)}
                                                </td>
                                                <td className="p-4 text-right font-mono text-sm text-slate-400">
                                                    ${pos.entry_price.toFixed(2)}
                                                </td>
                                                <td className="p-4 text-right font-mono text-sm text-white font-bold">
                                                    ${pos.mark_price.toFixed(2)}
                                                </td>
                                                <td className="p-4 text-right">
                                                    <div className={`font-mono font-bold text-sm ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                        {isProfit ? '+' : ''}{pos.pnl.toFixed(2)}
                                                    </div>
                                                    <div className={`text-[10px] font-mono ${isProfit ? 'text-emerald-500/70' : 'text-rose-500/70'}`}>
                                                        {pos.pnl_percent.toFixed(2)}%
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>

                {/* Sidebar: Allocation Chart */}
                <div className="space-y-6">
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <PieChart size={18} className="text-purple-500" /> Allocation By Class
                    </h3>
                    <div className="p-6 bg-[#0a0b10] border border-white/10 rounded-2xl relative overflow-hidden flex flex-col items-center justify-center min-h-[300px]">
                        <ResponsiveContainer width="100%" height={200}>
                            <RechartsPie
                                data={allocationData}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={80}
                                paddingAngle={5}
                                dataKey="value"
                            >
                                {allocationData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} stroke="rgba(0,0,0,0)" />
                                ))}
                            </RechartsPie>
                        </ResponsiveContainer>

                        {/* Legend */}
                        <div className="w-full mt-6 space-y-3">
                            {allocationData.map((entry, index) => (
                                <div key={index} className="flex items-center justify-between text-sm">
                                    <div className="flex items-center gap-2">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[index] }} />
                                        <span className="text-slate-300">{entry.name}</span>
                                    </div>
                                    <span className="font-mono font-bold text-white">
                                        {portfolio_value > 0 ? ((entry.value / portfolio_value) * 100).toFixed(1) : 0}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

            </div>
        </div>
    );
};

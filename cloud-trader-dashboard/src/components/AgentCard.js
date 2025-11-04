import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo } from 'react';
import AgentChart from './charts/AgentChart';
import AgentRadar from './visuals/AgentRadar';
import { resolveTokenMeta } from '../utils/tokenMeta';
const AgentCard = ({ agent, onClick }) => {
    const formatCurrency = (value) => new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(value);
    const formatPercent = (value) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
    const statusColors = {
        active: 'bg-emerald-400/80 text-slate-900',
        monitoring: 'bg-sky-400/80 text-slate-900',
        idle: 'bg-slate-500/60 text-white',
        error: 'bg-red-400/80 text-slate-900',
    };
    const pnlColor = agent.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400';
    const activePositions = agent.positions?.length ?? 0;
    const lastTrade = agent.last_trade ? new Date(agent.last_trade) : null;
    const agentDescription = agent.description || 'Autonomous trading agent on live duty inside Sapphire AI.';
    const chartData = useMemo(() => {
        if (!agent.performance)
            return [];
        return agent.performance.map((point) => ({
            timestamp: point.timestamp,
            equity: point.equity,
        }));
    }, [agent.performance]);
    const sentiment = useMemo(() => {
        const netExposure = (agent.positions ?? []).reduce((acc, position) => {
            const notional = typeof position.notional === 'number' ? position.notional : 0;
            const side = (position.side || '').toUpperCase();
            if (side === 'SELL')
                return acc - Math.abs(notional);
            if (side === 'BUY')
                return acc + Math.abs(notional);
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
    return (_jsxs("div", { onClick: onClick, className: "group relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass transition-all duration-200 hover:shadow-glass-lg hover:scale-[1.02] hover:bg-surface-100/70 cursor-pointer", children: [_jsx("div", { className: "absolute inset-0 bg-gradient-to-br from-white/5 via-transparent to-transparent" }), _jsx("div", { className: "absolute inset-0 bg-gradient-to-br from-white/10 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" }), _jsxs("div", { className: "relative", children: [_jsxs("div", { className: "flex items-start justify-between mb-4", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("div", { className: "h-12 w-12 rounded-xl bg-gradient-to-br from-primary-500 via-primary-400 to-accent-teal flex items-center justify-center shadow-glass group-hover:scale-110 transition-transform duration-200", children: _jsx("span", { className: "text-xl", children: agent.emoji }) }), _jsx("div", { children: _jsxs("div", { className: "flex items-center gap-2", children: [_jsx("h3", { className: "text-lg font-semibold text-white", children: agent.name }), _jsxs("span", { className: `inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-[0.3em] ${sentiment.tone}`, children: [_jsx("span", { children: sentiment.icon }), sentiment.label] })] }) })] }), _jsxs("span", { className: `inline-flex items-center gap-2 rounded-full px-2 py-1 text-xs font-medium ${statusColors[agent.status] || statusColors.monitoring}`, children: [_jsx("span", { className: "h-1.5 w-1.5 rounded-full bg-current opacity-60" }), agent.status] })] }), _jsxs("div", { className: "mb-6 flex flex-col gap-6 md:flex-row md:items-center", children: [_jsx(AgentRadar, { agent: agent }), _jsxs("div", { className: "flex-1 space-y-4", children: [_jsx("p", { className: "text-sm text-slate-300 leading-relaxed", children: agentDescription }), _jsx("div", { className: "flex flex-wrap gap-2", children: (agent.symbols ?? []).map((symbol) => {
                                            const meta = resolveTokenMeta(symbol);
                                            return (_jsxs("span", { className: `inline-flex items-center gap-2 rounded-full border border-white/10 bg-gradient-to-r ${meta.gradient} px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-white shadow-glass`, children: [_jsx("span", { className: "rounded-full bg-black/30 px-2 py-0.5 text-[0.65rem]", children: meta.short }), meta.name] }, symbol));
                                        }) })] })] }), _jsxs("div", { className: "grid grid-cols-2 gap-4 mb-4", children: [_jsxs("div", { className: "rounded-lg border border-surface-200/40 bg-surface-50/40 p-3", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-500", children: "P/L" }), _jsx("p", { className: `text-lg font-semibold ${pnlColor}`, children: formatCurrency(agent.total_pnl) })] }), _jsxs("div", { className: "rounded-lg border border-surface-200/40 bg-surface-50/40 p-3", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-500", children: "Win Rate" }), _jsx("p", { className: "text-lg font-semibold text-white", children: Number.isFinite(agent.win_rate) ? `${agent.win_rate.toFixed(1)}%` : '--' })] })] }), _jsxs("div", { className: "mb-4", children: [_jsxs("div", { className: "flex items-center justify-between mb-2", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Active Positions" }), _jsx("span", { className: "text-sm font-medium text-white", children: activePositions })] }), activePositions > 0 ? (_jsxs("div", { className: "space-y-1", children: [agent.positions.slice(0, 2).map((position, index) => {
                                        const meta = resolveTokenMeta(position.symbol);
                                        return (_jsxs("div", { className: "flex items-center justify-between text-xs", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("div", { className: `h-8 w-8 rounded-full bg-gradient-to-br ${meta.gradient} flex items-center justify-center text-[0.65rem] font-bold text-white shadow-glass`, children: meta.short }), _jsxs("div", { children: [_jsx("span", { className: "text-sm font-semibold text-white", children: position.symbol }), _jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.2em] text-slate-500", children: meta.name })] })] }), _jsxs("div", { className: "flex items-center gap-2", children: [_jsx("span", { className: `font-medium ${Number(position.pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'}`, children: formatPercent(position.pnl_percent ?? 0) }), position.size !== undefined && _jsx("span", { className: "text-slate-500", children: position.size?.toFixed(2) })] })] }, index));
                                    }), activePositions > 2 && (_jsxs("p", { className: "text-xs text-slate-500", children: ["+", activePositions - 2, " more positions"] }))] })) : (_jsx("p", { className: "text-xs text-slate-500", children: "No active positions" }))] }), chartData && chartData.length > 0 && (_jsxs("div", { className: "mb-4", children: [_jsxs("div", { className: "flex items-center justify-between mb-2", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Equity Curve" }), _jsx("span", { className: "text-xs text-slate-500", children: "48h" })] }), _jsx("div", { className: "h-24", children: _jsx(AgentChart, { data: chartData, height: 96 }) })] })), _jsxs("div", { className: "flex items-center justify-between text-xs", children: [_jsxs("span", { className: "text-slate-500", children: ["Last trade: ", lastTrade ? lastTrade.toLocaleTimeString() : '—'] }), _jsxs("span", { className: "text-slate-400", children: [agent.total_trades, " trades"] })] })] })] }));
};
export default AgentCard;

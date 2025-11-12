import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { resolveTokenMeta } from '../utils/tokenMeta';
const LivePositions = ({ positions }) => {
    const [sortBy, setSortBy] = useState('pnl');
    const [filterModel, setFilterModel] = useState('all');
    const normalizedPositions = positions.map((pos) => {
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
    const getPositionColor = (side) => {
        return side.toLowerCase() === 'long' ? 'text-green-600' : 'text-red-600';
    };
    const getPnLColor = (pnl) => {
        return pnl >= 0 ? 'text-green-600' : 'text-red-600';
    };
    // Filter and sort positions
    const filteredPositions = normalizedPositions.filter(pos => filterModel === 'all' || pos.model_used === filterModel);
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
    return (_jsxs("div", { className: "space-y-6", children: [_jsxs("div", { className: "grid grid-cols-1 gap-4 md:grid-cols-3", children: [_jsxs("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/80 p-5 shadow-glass", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Positions" }), _jsx("p", { className: "mt-2 text-3xl font-semibold text-white", children: normalizedPositions.length }), _jsx("p", { className: "mt-1 text-xs text-slate-500", children: "Active exposures across all models" })] }), _jsxs("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/80 p-5 shadow-glass", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Total P&L" }), _jsxs("p", { className: `mt-2 text-3xl font-semibold ${getPnLColor(totalPnL)}`, children: ["$", totalPnL.toFixed(2)] }), _jsx("p", { className: "mt-1 text-xs text-slate-500", children: "Session-to-date realised + unrealised" })] }), _jsxs("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/80 p-5 shadow-glass", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Gross Exposure" }), _jsxs("p", { className: "mt-2 text-3xl font-semibold text-white", children: ["$", totalExposure.toFixed(2)] }), _jsx("p", { className: "mt-1 text-xs text-slate-500", children: "Calculated at entry notional" })] })] }), _jsx("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/80 p-5 shadow-glass", children: _jsxs("div", { className: "flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between", children: [_jsxs("div", { className: "flex flex-col gap-4 sm:flex-row sm:items-center", children: [_jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Sort Order" }), _jsxs("select", { value: sortBy, onChange: (e) => setSortBy(e.target.value), className: "mt-2 rounded-xl border border-surface-200/40 bg-surface-50/40 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500/60", children: [_jsx("option", { value: "pnl", children: "P&L" }), _jsx("option", { value: "symbol", children: "Symbol" }), _jsx("option", { value: "size", children: "Size" })] })] }), _jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Model Filter" }), _jsxs("select", { value: filterModel, onChange: (e) => setFilterModel(e.target.value), className: "mt-2 rounded-xl border border-surface-200/40 bg-surface-50/40 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500/60", children: [_jsx("option", { value: "all", children: "All Models" }), uniqueModels.map((model) => (_jsx("option", { value: model, children: model }, model)))] })] })] }), _jsxs("p", { className: "text-sm text-slate-400", children: ["Showing ", _jsx("span", { className: "font-semibold text-slate-200", children: sortedPositions.length }), " of ", normalizedPositions.length] })] }) }), _jsxs("div", { className: "overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/80 shadow-glass", children: [_jsx("div", { className: "border-b border-surface-200/40 px-6 py-4", children: _jsx("h2", { className: "text-xl font-semibold text-white", children: "Live Positions" }) }), sortedPositions.length === 0 ? (_jsx("div", { className: "py-16 text-center text-slate-500", children: _jsx("p", { className: "text-sm", children: "No active positions \u00B7 awaiting signal fulfilment" }) })) : (_jsx("div", { className: "overflow-x-auto", children: _jsxs("table", { className: "min-w-full divide-y divide-surface-200/40 text-sm", children: [_jsx("thead", { className: "bg-surface-50/40 text-xs uppercase tracking-[0.2em] text-slate-400", children: _jsxs("tr", { children: [_jsx("th", { className: "px-6 py-3 text-left", children: "Symbol & Model" }), _jsx("th", { className: "px-6 py-3 text-left", children: "Side" }), _jsx("th", { className: "px-6 py-3 text-left", children: "Size" }), _jsx("th", { className: "px-6 py-3 text-left", children: "Entry" }), _jsx("th", { className: "px-6 py-3 text-left", children: "Last" }), _jsx("th", { className: "px-6 py-3 text-left", children: "P&L" }), _jsx("th", { className: "px-6 py-3 text-left", children: "Lev" }), _jsx("th", { className: "px-6 py-3 text-left", children: "Updated" })] }) }), _jsx("tbody", { className: "divide-y divide-surface-200/30 text-slate-200", children: sortedPositions.map((position, index) => {
                                        const meta = resolveTokenMeta(position.symbol);
                                        return (_jsxs("tr", { className: "hover:bg-surface-50/30", children: [_jsx("td", { className: "px-6 py-3", children: _jsxs("div", { className: "flex items-center gap-3", children: [_jsx("div", { className: `h-9 w-9 rounded-full bg-gradient-to-br ${meta.gradient} flex items-center justify-center text-xs font-bold text-white shadow-glass`, children: meta.short }), _jsxs("div", { children: [_jsx("p", { className: "text-sm font-medium text-white", children: position.symbol }), _jsxs("p", { className: "text-xs text-slate-500", children: [meta.name, " \u00B7 ", position.model_used] })] })] }) }), _jsx("td", { className: "px-6 py-3", children: _jsx("span", { className: `inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${getPositionColor(position.side)} bg-white/10`, children: position.side.toUpperCase() }) }), _jsx("td", { className: "px-6 py-3 text-slate-200", children: position.size.toFixed(4) }), _jsxs("td", { className: "px-6 py-3 text-slate-200", children: ["$", position.entry_price.toFixed(2)] }), _jsxs("td", { className: "px-6 py-3 text-slate-200", children: ["$", position.current_price.toFixed(2)] }), _jsxs("td", { className: "px-6 py-3", children: [_jsxs("div", { className: `font-semibold ${getPnLColor(position.pnl)}`, children: ["$", position.pnl.toFixed(2)] }), _jsxs("div", { className: `text-xs ${getPnLColor(position.pnl_percent)}`, children: ["(", position.pnl_percent >= 0 ? '+' : '', position.pnl_percent.toFixed(2), "%)"] })] }), _jsxs("td", { className: "px-6 py-3 text-slate-200", children: [position.leverage, "x"] }), _jsx("td", { className: "px-6 py-3 text-slate-500", children: new Date(position.timestamp).toLocaleTimeString() })] }, index));
                                    }) })] }) }))] })] }));
};
export default LivePositions;

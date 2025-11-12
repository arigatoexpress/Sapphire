import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo } from 'react';
import { resolveTokenMeta } from '../utils/tokenMeta';
const PortfolioCard = ({ portfolio }) => {
    const positions = useMemo(() => {
        if (!portfolio?.positions)
            return [];
        return Object.values(portfolio.positions).map((position) => ({
            symbol: position.symbol ?? 'Unknown',
            notional: position.notional ?? 0,
        }));
    }, [portfolio]);
    const formatCurrency = (value) => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 2,
        }).format(value);
    };
    const formatMaskedCurrency = (value) => {
        void value;
        return '%s';
    };
    if (!portfolio) {
        return (_jsx("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass", children: _jsxs("div", { className: "animate-pulse space-y-4", children: [_jsx("div", { className: "h-5 w-32 rounded bg-slate-600/30" }), _jsxs("div", { className: "grid grid-cols-3 gap-4", children: [_jsx("div", { className: "h-16 rounded-xl bg-slate-600/10" }), _jsx("div", { className: "h-16 rounded-xl bg-slate-600/10" }), _jsx("div", { className: "h-16 rounded-xl bg-slate-600/10" })] })] }) }));
    }
    const balance = portfolio.balance ?? 0;
    const exposure = portfolio.total_exposure ?? 0;
    const available = Math.max(balance - exposure, 0);
    return (_jsxs("div", { className: "relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass", children: [_jsx("div", { className: "absolute inset-0 bg-gradient-to-br from-primary-500/5 via-transparent to-transparent" }), _jsxs("div", { className: "relative flex items-center justify-between", children: [_jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Portfolio Overview" }), _jsx("h3", { className: "mt-2 text-2xl font-semibold text-white", children: formatMaskedCurrency(balance) }), _jsxs("p", { className: "mt-1 text-xs uppercase tracking-[0.2em] text-slate-500", children: ["Source \u00B7 ", portfolio.source ?? 'local cache'] })] }), portfolio.alerts && portfolio.alerts.length > 0 && (_jsx("span", { className: "rounded-full bg-accent-amber/20 px-4 py-1 text-xs font-medium text-accent-amber shadow-glass", children: portfolio.alerts[0] }))] }), _jsxs("div", { className: "relative mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3", children: [_jsxs("div", { className: "rounded-xl border border-surface-200/40 bg-surface-50/40 p-4", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.3em] text-slate-500", children: "Balance" }), _jsx("p", { className: "mt-2 text-xl font-semibold text-white", children: formatMaskedCurrency(balance) })] }), _jsxs("div", { className: "rounded-xl border border-surface-200/40 bg-surface-50/40 p-4", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.3em] text-slate-500", children: "Exposure" }), _jsx("p", { className: "mt-2 text-xl font-semibold text-white", children: formatCurrency(exposure) })] }), _jsxs("div", { className: "rounded-xl border border-surface-200/40 bg-surface-50/40 p-4", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.3em] text-slate-500", children: "Available" }), _jsx("p", { className: "mt-2 text-xl font-semibold text-white", children: formatCurrency(available) })] })] }), _jsxs("div", { className: "relative mt-6", children: [_jsx("h4", { className: "text-sm font-semibold uppercase tracking-[0.2em] text-slate-400", children: "Open Exposure" }), positions.length > 0 ? (_jsx("div", { className: "mt-3 space-y-2", children: positions.map((position) => {
                            const meta = resolveTokenMeta(position.symbol);
                            return (_jsxs("div", { className: "flex items-center justify-between rounded-xl border border-surface-200/40 bg-surface-50/30 px-4 py-3 text-sm text-slate-200", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("div", { className: `h-9 w-9 rounded-full bg-gradient-to-br ${meta.gradient} flex items-center justify-center text-xs font-bold text-white shadow-glass`, children: meta.short }), _jsxs("div", { children: [_jsx("p", { className: "font-medium text-white", children: position.symbol }), _jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.2em] text-slate-500", children: meta.name })] })] }), _jsx("p", { className: "text-base font-semibold text-white", children: formatCurrency(Math.abs(position.notional || 0)) })] }, position.symbol));
                        }) })) : (_jsx("div", { className: "mt-4 rounded-xl border border-dashed border-surface-200/40 bg-surface-50/20 px-6 py-10 text-center text-slate-500", children: _jsx("p", { className: "text-sm", children: "No active positions \u00B7 risk budget fully available" }) }))] })] }));
};
export default PortfolioCard;

import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useMemo } from 'react';
import { emergencyStop } from '../api/client';
const RiskMetrics = ({ portfolio }) => {
    const [emergencyLoading, setEmergencyLoading] = useState(false);
    const derived = useMemo(() => {
        if (!portfolio) {
            return {
                balance: 0,
                exposure: 0,
                positions: [],
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
    const handleEmergencyStop = async () => {
        if (!confirm('Are you sure you want to trigger an emergency stop? This will cancel all open orders and close positions.')) {
            return;
        }
        try {
            setEmergencyLoading(true);
            await emergencyStop();
            alert('Emergency stop triggered successfully');
        }
        catch (err) {
            alert(`Emergency stop failed: ${err.message}`);
        }
        finally {
            setEmergencyLoading(false);
        }
    };
    const calculateRiskMetrics = () => {
        const { balance, exposure, positions } = derived;
        if (balance === 0 && exposure === 0)
            return null;
        const availableBalance = Math.max(balance - exposure, 0);
        // Calculate leverage ratio
        const leverageRatio = balance > 0 ? (exposure / balance) * 100 : 0;
        // Calculate position concentration (largest position as % of total exposure)
        const positionSizes = positions.map(p => Math.abs(p.notional));
        const maxPositionSize = Math.max(...positionSizes, 0);
        const concentrationRisk = exposure > 0 ? (maxPositionSize / exposure) * 100 : 0;
        // Risk levels
        const getRiskLevel = (value, thresholds) => {
            if (value <= thresholds.low)
                return { level: 'low', color: 'text-green-600', bg: 'bg-green-50' };
            if (value <= thresholds.medium)
                return { level: 'medium', color: 'text-yellow-600', bg: 'bg-yellow-50' };
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
    const formatCurrency = (value) => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 2,
        }).format(value);
    };
    const formatPercent = (value) => {
        return `${value.toFixed(1)}%`;
    };
    if (!portfolio) {
        return (_jsx("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass", children: _jsxs("div", { className: "animate-pulse space-y-3", children: [_jsx("div", { className: "h-6 w-56 rounded bg-slate-600/30" }), _jsxs("div", { className: "grid grid-cols-2 gap-3", children: [_jsx("div", { className: "h-20 rounded-xl bg-slate-600/10" }), _jsx("div", { className: "h-20 rounded-xl bg-slate-600/10" })] })] }) }));
    }
    return (_jsxs("div", { className: "space-y-6", children: [_jsxs("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 text-slate-200 shadow-glass", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Risk Envelope" }), _jsx("h3", { className: "mt-2 text-2xl font-semibold text-white", children: "Exposure Diagnostics" })] }), _jsxs("div", { className: "rounded-full border border-surface-200/60 bg-surface-50/60 px-3 py-1 text-xs text-slate-400", children: ["Margin budget ", formatPercent(riskMetrics?.leverageRatio ?? 0)] })] }), riskMetrics && (_jsxs("div", { className: "mt-6 grid grid-cols-1 gap-4 md:grid-cols-2", children: [_jsxs("div", { className: "rounded-xl border border-surface-200/40 bg-surface-50/40 p-4", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("p", { className: "text-sm font-medium text-slate-300", children: "Leverage Ratio" }), _jsx("span", { className: `rounded-full px-2 py-1 text-xs font-semibold ${riskMetrics.leverageRisk.bg} ${riskMetrics.leverageRisk.color}`, children: riskMetrics.leverageRisk.level.toUpperCase() })] }), _jsx("p", { className: "mt-3 text-2xl font-semibold text-white", children: formatPercent(riskMetrics.leverageRatio) }), _jsx("p", { className: "mt-1 text-xs text-slate-500", children: "Total exposure vs equity" })] }), _jsxs("div", { className: "rounded-xl border border-surface-200/40 bg-surface-50/40 p-4", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("p", { className: "text-sm font-medium text-slate-300", children: "Concentration Risk" }), _jsx("span", { className: `rounded-full px-2 py-1 text-xs font-semibold ${riskMetrics.concentrationRiskLevel.bg} ${riskMetrics.concentrationRiskLevel.color}`, children: riskMetrics.concentrationRiskLevel.level.toUpperCase() })] }), _jsx("p", { className: "mt-3 text-2xl font-semibold text-white", children: formatPercent(riskMetrics.concentrationRisk) }), _jsx("p", { className: "mt-1 text-xs text-slate-500", children: "Largest position share of gross exposure" })] }), _jsx("div", { className: "md:col-span-2", children: _jsxs("div", { className: "rounded-xl border border-surface-200/40 bg-surface-50/30 p-4", children: [_jsxs("div", { className: "flex items-center justify-between text-sm", children: [_jsx("span", { className: "text-slate-400", children: "Margin Utilisation" }), _jsxs("span", { className: "font-medium text-white", children: [formatCurrency(riskMetrics.marginUsed), " / ", formatCurrency(riskMetrics.totalBalance)] })] }), _jsx("div", { className: "mt-3 h-2 rounded-full bg-slate-700/60", children: _jsx("div", { className: "h-full rounded-full bg-gradient-to-r from-primary-500 via-accent-teal to-accent-emerald", style: { width: `${Math.min((riskMetrics.marginUsed / riskMetrics.totalBalance) * 100, 100)}%` } }) })] }) })] }))] }), _jsxs("div", { className: "rounded-2xl border border-red-500/20 bg-red-500/10 p-6 text-red-100 shadow-glass", children: [_jsx("h3", { className: "text-lg font-semibold text-red-100", children: "Emergency Controls" }), _jsx("p", { className: "mt-1 text-sm text-red-200/80", children: "Use only to halt trading and flatten exposure. Accessibility restricted to operators with elevated permissions." }), _jsx("button", { onClick: handleEmergencyStop, disabled: emergencyLoading, className: "mt-4 flex w-full items-center justify-center gap-2 rounded-full bg-red-500/80 px-5 py-3 text-sm font-semibold text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:bg-red-500/40", children: emergencyLoading ? (_jsxs(_Fragment, { children: [_jsxs("svg", { className: "h-4 w-4 animate-spin", viewBox: "0 0 24 24", fill: "none", children: [_jsx("circle", { className: "opacity-25", cx: "12", cy: "12", r: "10", stroke: "currentColor", strokeWidth: "4" }), _jsx("path", { className: "opacity-75", fill: "currentColor", d: "M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" })] }), "Triggering Emergency Stop\u2026"] })) : (_jsxs(_Fragment, { children: [_jsx("span", { children: "\uD83D\uDED1" }), "Emergency Stop"] })) }), _jsx("p", { className: "mt-3 text-xs text-red-200/70", children: "Action will cancel open orders and send liquidation-intent to orchestrator routing layer." })] })] }));
};
export default RiskMetrics;

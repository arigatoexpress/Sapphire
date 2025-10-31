import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { fetchPortfolio, emergencyStop } from '../api/client';
const RiskMetrics = () => {
    const [portfolio, setPortfolio] = useState(null);
    const [loading, setLoading] = useState(true);
    const [emergencyLoading, setEmergencyLoading] = useState(false);
    const loadPortfolio = async () => {
        try {
            setLoading(true);
            const data = await fetchPortfolio();
            setPortfolio(data);
        }
        catch (err) {
            console.error('Failed to load portfolio for risk metrics:', err);
        }
        finally {
            setLoading(false);
        }
    };
    useEffect(() => {
        loadPortfolio();
        // Refresh risk metrics every 30 seconds
        const interval = setInterval(loadPortfolio, 30000);
        return () => clearInterval(interval);
    }, []);
    const handleEmergencyStop = async () => {
        if (!confirm('Are you sure you want to trigger an emergency stop? This will cancel all open orders and close positions.')) {
            return;
        }
        try {
            setEmergencyLoading(true);
            await emergencyStop();
            alert('Emergency stop triggered successfully');
            loadPortfolio(); // Refresh data
        }
        catch (err) {
            alert(`Emergency stop failed: ${err.message}`);
        }
        finally {
            setEmergencyLoading(false);
        }
    };
    const calculateRiskMetrics = () => {
        if (!portfolio)
            return null;
        const totalBalance = parseFloat(portfolio.totalWalletBalance);
        const marginUsed = parseFloat(portfolio.totalPositionInitialMargin);
        const availableBalance = totalBalance - marginUsed;
        // Calculate leverage ratio
        const leverageRatio = marginUsed > 0 ? (marginUsed / availableBalance) * 100 : 0;
        // Calculate position concentration (largest position as % of total exposure)
        const positionSizes = portfolio.positions.map(p => Math.abs(parseFloat(p.positionAmt)));
        const maxPositionSize = Math.max(...positionSizes, 0);
        const concentrationRisk = marginUsed > 0 ? (maxPositionSize / marginUsed) * 100 : 0;
        // Risk levels
        const getRiskLevel = (value, thresholds) => {
            if (value <= thresholds.low)
                return { level: 'low', color: 'text-green-600', bg: 'bg-green-50' };
            if (value <= thresholds.medium)
                return { level: 'medium', color: 'text-yellow-600', bg: 'bg-yellow-50' };
            return { level: 'high', color: 'text-red-600', bg: 'bg-red-50' };
        };
        return {
            totalBalance,
            marginUsed,
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
            currency: 'USDT',
            minimumFractionDigits: 2,
        }).format(value);
    };
    const formatPercent = (value) => {
        return `${value.toFixed(1)}%`;
    };
    if (loading) {
        return (_jsx("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: _jsxs("div", { className: "animate-pulse", children: [_jsx("div", { className: "h-6 bg-slate-200 rounded w-1/2 mb-4" }), _jsxs("div", { className: "space-y-3", children: [_jsx("div", { className: "h-4 bg-slate-200 rounded w-full" }), _jsx("div", { className: "h-4 bg-slate-200 rounded w-3/4" }), _jsx("div", { className: "h-4 bg-slate-200 rounded w-1/2" })] })] }) }));
    }
    return (_jsxs("div", { className: "space-y-6", children: [_jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: [_jsx("h3", { className: "text-lg font-semibold text-slate-900 mb-4", children: "Risk Metrics" }), riskMetrics && (_jsxs("div", { className: "space-y-4", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { className: "flex items-center space-x-2", children: [_jsx("span", { className: "text-sm font-medium text-slate-700", children: "Leverage Ratio" }), _jsx("span", { className: `px-2 py-1 text-xs font-medium rounded-full ${riskMetrics.leverageRisk.bg} ${riskMetrics.leverageRisk.color}`, children: riskMetrics.leverageRisk.level.toUpperCase() })] }), _jsx("span", { className: "text-sm font-semibold text-slate-900", children: formatPercent(riskMetrics.leverageRatio) })] }), _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { className: "flex items-center space-x-2", children: [_jsx("span", { className: "text-sm font-medium text-slate-700", children: "Concentration Risk" }), _jsx("span", { className: `px-2 py-1 text-xs font-medium rounded-full ${riskMetrics.concentrationRiskLevel.bg} ${riskMetrics.concentrationRiskLevel.color}`, children: riskMetrics.concentrationRiskLevel.level.toUpperCase() })] }), _jsx("span", { className: "text-sm font-semibold text-slate-900", children: formatPercent(riskMetrics.concentrationRisk) })] }), _jsxs("div", { className: "pt-2 border-t border-slate-200", children: [_jsxs("div", { className: "flex justify-between text-sm mb-2", children: [_jsx("span", { className: "text-slate-600", children: "Margin Used" }), _jsxs("span", { className: "font-medium text-slate-900", children: [formatCurrency(riskMetrics.marginUsed), " / ", formatCurrency(riskMetrics.totalBalance)] })] }), _jsx("div", { className: "w-full bg-slate-200 rounded-full h-2", children: _jsx("div", { className: "bg-blue-600 h-2 rounded-full transition-all duration-300", style: { width: `${Math.min((riskMetrics.marginUsed / riskMetrics.totalBalance) * 100, 100)}%` } }) })] })] }))] }), _jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-red-200 p-6", children: [_jsx("h3", { className: "text-lg font-semibold text-slate-900 mb-4", children: "Emergency Controls" }), _jsx("p", { className: "text-sm text-slate-600 mb-4", children: "Use these controls only in emergency situations to protect your capital." }), _jsx("button", { onClick: handleEmergencyStop, disabled: emergencyLoading, className: "w-full flex items-center justify-center px-4 py-3 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-medium rounded-lg transition-colors disabled:cursor-not-allowed", children: emergencyLoading ? (_jsxs(_Fragment, { children: [_jsxs("svg", { className: "animate-spin -ml-1 mr-2 h-4 w-4 text-white", fill: "none", viewBox: "0 0 24 24", children: [_jsx("circle", { className: "opacity-25", cx: "12", cy: "12", r: "10", stroke: "currentColor", strokeWidth: "4" }), _jsx("path", { className: "opacity-75", fill: "currentColor", d: "M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" })] }), "Triggering Emergency Stop..."] })) : (_jsxs(_Fragment, { children: [_jsx("svg", { className: "w-4 h-4 mr-2", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" }) }), "Emergency Stop"] })) }), _jsx("p", { className: "text-xs text-slate-500 mt-3", children: "This will cancel all open orders and close positions at market price." })] })] }));
};
export default RiskMetrics;

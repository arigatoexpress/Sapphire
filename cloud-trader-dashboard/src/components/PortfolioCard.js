import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { fetchPortfolio } from '../api/client';
const PortfolioCard = ({ portfolio: initialPortfolio }) => {
    const [portfolio, setPortfolio] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const loadPortfolio = async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await fetchPortfolio();
            setPortfolio(data);
        }
        catch (err) {
            setError(err.message);
        }
        finally {
            setLoading(false);
        }
    };
    useEffect(() => {
        loadPortfolio();
        // Refresh portfolio data every 30 seconds
        const interval = setInterval(loadPortfolio, 30000);
        return () => clearInterval(interval);
    }, []);
    const formatCurrency = (value) => {
        const num = parseFloat(value);
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USDT',
            minimumFractionDigits: 2,
        }).format(num);
    };
    const formatNumber = (value) => {
        const num = parseFloat(value);
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 6,
        }).format(num);
    };
    if (loading && !portfolio) {
        return (_jsx("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: _jsxs("div", { className: "animate-pulse", children: [_jsx("div", { className: "h-6 bg-slate-200 rounded w-1/3 mb-4" }), _jsxs("div", { className: "space-y-3", children: [_jsx("div", { className: "h-4 bg-slate-200 rounded w-full" }), _jsx("div", { className: "h-4 bg-slate-200 rounded w-3/4" }), _jsx("div", { className: "h-4 bg-slate-200 rounded w-1/2" })] })] }) }));
    }
    if (error) {
        return (_jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: [_jsxs("div", { className: "flex items-center justify-between mb-4", children: [_jsx("h3", { className: "text-lg font-semibold text-slate-900", children: "Portfolio" }), _jsx("button", { onClick: loadPortfolio, className: "text-slate-500 hover:text-slate-700", children: _jsx("svg", { className: "w-4 h-4", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" }) }) })] }), _jsxs("p", { className: "text-red-600 text-sm", children: ["Failed to load portfolio: ", error] })] }));
    }
    return (_jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: [_jsxs("div", { className: "flex items-center justify-between mb-6", children: [_jsx("h3", { className: "text-lg font-semibold text-slate-900", children: "Portfolio Overview" }), _jsx("button", { onClick: loadPortfolio, disabled: loading, className: "text-slate-500 hover:text-slate-700 disabled:opacity-50", children: _jsx("svg", { className: `w-4 h-4 ${loading ? 'animate-spin' : ''}`, fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" }) }) })] }), _jsxs("div", { className: "grid grid-cols-2 gap-4 mb-6", children: [_jsxs("div", { className: "bg-slate-50 rounded-lg p-4", children: [_jsx("p", { className: "text-sm text-slate-600 mb-1", children: "Total Balance" }), _jsx("p", { className: "text-2xl font-bold text-slate-900", children: portfolio ? formatCurrency(portfolio.totalWalletBalance) : '$0.00' })] }), _jsxs("div", { className: "bg-slate-50 rounded-lg p-4", children: [_jsx("p", { className: "text-sm text-slate-600 mb-1", children: "Margin Used" }), _jsx("p", { className: "text-2xl font-bold text-slate-900", children: portfolio ? formatCurrency(portfolio.totalPositionInitialMargin) : '$0.00' })] })] }), _jsxs("div", { className: "space-y-3", children: [_jsx("h4", { className: "text-md font-medium text-slate-900", children: "Positions" }), portfolio && portfolio.positions.length > 0 ? (_jsx("div", { className: "space-y-2", children: portfolio.positions.map((position, index) => (_jsxs("div", { className: "flex items-center justify-between p-3 bg-slate-50 rounded-lg", children: [_jsxs("div", { className: "flex items-center space-x-3", children: [_jsx("div", { className: `w-3 h-3 rounded-full ${position.positionSide === 'LONG' ? 'bg-green-500' :
                                                position.positionSide === 'SHORT' ? 'bg-red-500' : 'bg-blue-500'}` }), _jsxs("div", { children: [_jsx("p", { className: "font-medium text-slate-900", children: position.symbol.replace('USDT', '/USDT') }), _jsxs("p", { className: "text-sm text-slate-600", children: ["Leverage: ", position.leverage, "x"] })] })] }), _jsxs("div", { className: "text-right", children: [_jsx("p", { className: "font-medium text-slate-900", children: formatNumber(position.positionAmt) }), _jsxs("p", { className: `text-sm ${parseFloat(position.unrealizedProfit) >= 0 ? 'text-green-600' : 'text-red-600'}`, children: ["P&L: ", formatCurrency(position.unrealizedProfit)] })] })] }, index))) })) : (_jsxs("div", { className: "text-center py-8 text-slate-500", children: [_jsx("svg", { className: "w-12 h-12 mx-auto mb-3 text-slate-400", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 1, d: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" }) }), _jsx("p", { children: "No open positions" })] }))] })] }));
};
export default PortfolioCard;

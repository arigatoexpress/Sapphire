import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
const LivePositions = ({ positions }) => {
    const [sortBy, setSortBy] = useState('pnl');
    const [filterModel, setFilterModel] = useState('all');
    const getModelIcon = (modelName) => {
        const icons = {
            'DeepSeek-Coder-V2': '🧠',
            'Qwen2.5-Coder': '🧮',
            'FinGPT': '💰',
            'Phi-3': '🔬'
        };
        return icons[modelName] || '🤖';
    };
    const getPositionColor = (side) => {
        return side.toLowerCase() === 'long' ? 'text-green-600' : 'text-red-600';
    };
    const getPnLColor = (pnl) => {
        return pnl >= 0 ? 'text-green-600' : 'text-red-600';
    };
    const getPnLBgColor = (pnl) => {
        return pnl >= 0 ? 'bg-green-50' : 'bg-red-50';
    };
    // Filter and sort positions
    const filteredPositions = positions.filter(pos => filterModel === 'all' || pos.model_used === filterModel);
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
    const totalPnL = positions.reduce((sum, pos) => sum + pos.pnl, 0);
    const totalExposure = positions.reduce((sum, pos) => sum + (pos.size * pos.entry_price), 0);
    const uniqueModels = Array.from(new Set(positions.map(p => p.model_used)));
    return (_jsxs("div", { className: "space-y-6", children: [_jsxs("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-4", children: [_jsx("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-4", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { children: [_jsx("p", { className: "text-sm text-slate-600", children: "Total Positions" }), _jsx("p", { className: "text-2xl font-bold text-slate-900", children: positions.length })] }), _jsx("span", { className: "text-2xl", children: "\uD83D\uDCCA" })] }) }), _jsx("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-4", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { children: [_jsx("p", { className: "text-sm text-slate-600", children: "Total P&L" }), _jsxs("p", { className: `text-2xl font-bold ${getPnLColor(totalPnL)}`, children: ["$", totalPnL.toFixed(2)] })] }), _jsx("span", { className: `text-2xl ${totalPnL >= 0 ? 'filter hue-rotate-120' : ''}`, children: "\uD83D\uDCB0" })] }) }), _jsx("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-4", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { children: [_jsx("p", { className: "text-sm text-slate-600", children: "Total Exposure" }), _jsxs("p", { className: "text-2xl font-bold text-slate-900", children: ["$", totalExposure.toFixed(2)] })] }), _jsx("span", { className: "text-2xl", children: "\uD83D\uDCC8" })] }) })] }), _jsx("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-4", children: _jsxs("div", { className: "flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between", children: [_jsxs("div", { className: "flex items-center space-x-4", children: [_jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-slate-700 mb-1", children: "Sort by:" }), _jsxs("select", { value: sortBy, onChange: (e) => setSortBy(e.target.value), className: "px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500", children: [_jsx("option", { value: "pnl", children: "P&L" }), _jsx("option", { value: "symbol", children: "Symbol" }), _jsx("option", { value: "size", children: "Size" })] })] }), _jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-slate-700 mb-1", children: "Filter Model:" }), _jsxs("select", { value: filterModel, onChange: (e) => setFilterModel(e.target.value), className: "px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500", children: [_jsx("option", { value: "all", children: "All Models" }), uniqueModels.map(model => (_jsx("option", { value: model, children: model }, model)))] })] })] }), _jsxs("div", { className: "text-sm text-slate-600", children: ["Showing ", sortedPositions.length, " of ", positions.length, " positions"] })] }) }), _jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden", children: [_jsx("div", { className: "px-6 py-4 border-b border-slate-200", children: _jsx("h2", { className: "text-xl font-semibold text-slate-900", children: "Live Positions" }) }), sortedPositions.length === 0 ? (_jsxs("div", { className: "text-center py-12 text-slate-500", children: [_jsx("span", { className: "text-4xl mb-2 block", children: "\uD83D\uDCCA" }), _jsx("p", { children: "No active positions" }), _jsx("p", { className: "text-sm", children: "Positions will appear here when trades are executed" })] })) : (_jsx("div", { className: "overflow-x-auto", children: _jsxs("table", { className: "min-w-full divide-y divide-slate-200", children: [_jsx("thead", { className: "bg-slate-50", children: _jsxs("tr", { children: [_jsx("th", { className: "px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider", children: "Symbol & Model" }), _jsx("th", { className: "px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider", children: "Side" }), _jsx("th", { className: "px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider", children: "Size" }), _jsx("th", { className: "px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider", children: "Entry Price" }), _jsx("th", { className: "px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider", children: "Current Price" }), _jsx("th", { className: "px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider", children: "P&L" }), _jsx("th", { className: "px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider", children: "Leverage" }), _jsx("th", { className: "px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider", children: "Last Update" })] }) }), _jsx("tbody", { className: "bg-white divide-y divide-slate-200", children: sortedPositions.map((position, index) => (_jsxs("tr", { className: `${getPnLBgColor(position.pnl)} hover:bg-slate-50`, children: [_jsx("td", { className: "px-6 py-4 whitespace-nowrap", children: _jsxs("div", { className: "flex items-center", children: [_jsx("span", { className: "text-lg mr-2", children: getModelIcon(position.model_used) }), _jsxs("div", { children: [_jsx("div", { className: "text-sm font-medium text-slate-900", children: position.symbol }), _jsx("div", { className: "text-xs text-slate-500", children: position.model_used })] })] }) }), _jsx("td", { className: "px-6 py-4 whitespace-nowrap", children: _jsx("span", { className: `inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getPositionColor(position.side)} bg-current bg-opacity-10`, children: position.side.toUpperCase() }) }), _jsx("td", { className: "px-6 py-4 whitespace-nowrap text-sm text-slate-900", children: position.size.toFixed(4) }), _jsxs("td", { className: "px-6 py-4 whitespace-nowrap text-sm text-slate-900", children: ["$", position.entry_price.toFixed(2)] }), _jsxs("td", { className: "px-6 py-4 whitespace-nowrap text-sm text-slate-900", children: ["$", position.current_price.toFixed(2)] }), _jsxs("td", { className: "px-6 py-4 whitespace-nowrap", children: [_jsxs("div", { className: `text-sm font-medium ${getPnLColor(position.pnl)}`, children: ["$", position.pnl.toFixed(2)] }), _jsxs("div", { className: `text-xs ${getPnLColor(position.pnl_percent)}`, children: ["(", position.pnl_percent >= 0 ? '+' : '', position.pnl_percent.toFixed(2), "%)"] })] }), _jsxs("td", { className: "px-6 py-4 whitespace-nowrap text-sm text-slate-900", children: [position.leverage, "x"] }), _jsx("td", { className: "px-6 py-4 whitespace-nowrap text-sm text-slate-500", children: new Date(position.timestamp).toLocaleTimeString() })] }, index))) })] }) }))] })] }));
};
export default LivePositions;

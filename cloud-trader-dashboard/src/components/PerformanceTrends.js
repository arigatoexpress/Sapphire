import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
const PerformanceTrends = ({ trades }) => {
    const [selectedModels, setSelectedModels] = useState(['all']);
    const [timeRange, setTimeRange] = useState('24h');
    // Get unique models
    const models = Array.from(new Set(trades.map(t => t.model_used)));
    // Filter trades by time range
    const now = new Date();
    const timeRanges = {
        '1h': 60 * 60 * 1000,
        '24h': 24 * 60 * 60 * 1000,
        '7d': 7 * 24 * 60 * 60 * 1000
    };
    const filteredTrades = trades.filter(trade => {
        const tradeTime = new Date(trade.timestamp);
        return (now.getTime() - tradeTime.getTime()) <= timeRanges[timeRange];
    });
    // Calculate cumulative P&L for each model
    const calculateModelPnL = (model) => {
        const modelTrades = filteredTrades.filter(t => t.model_used === model && t.pnl !== undefined);
        let cumulative = 0;
        return modelTrades.map(trade => {
            cumulative += trade.pnl;
            return {
                time: new Date(trade.timestamp),
                pnl: cumulative,
                trade: trade
            };
        });
    };
    const getModelColor = (modelName) => {
        const colors = {
            'DeepSeek-Coder-V2': '#10B981', // green
            'Qwen2.5-Coder': '#3B82F6', // blue
            'FinGPT': '#F59E0B', // yellow
            'Phi-3': '#EF4444', // red
        };
        return colors[modelName] || '#6B7280';
    };
    const toggleModel = (model) => {
        if (model === 'all') {
            setSelectedModels(['all']);
        }
        else {
            if (selectedModels.includes('all')) {
                setSelectedModels([model]);
            }
            else if (selectedModels.includes(model)) {
                const newSelected = selectedModels.filter(m => m !== model);
                setSelectedModels(newSelected.length === 0 ? ['all'] : newSelected);
            }
            else {
                setSelectedModels([...selectedModels.filter(m => m !== 'all'), model]);
            }
        }
    };
    const maxPnL = Math.max(...filteredTrades.map(t => Math.abs(t.pnl || 0)), 100);
    const chartHeight = 200;
    const chartWidth = 600;
    return (_jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: [_jsxs("div", { className: "flex items-center justify-between mb-6", children: [_jsx("h2", { className: "text-xl font-semibold text-slate-900", children: "Performance Trends" }), _jsx("div", { className: "flex items-center space-x-4", children: _jsxs("div", { className: "flex items-center space-x-2", children: [_jsx("label", { className: "text-sm text-slate-600", children: "Time:" }), _jsxs("select", { value: timeRange, onChange: (e) => setTimeRange(e.target.value), className: "px-2 py-1 border border-slate-300 rounded text-sm", children: [_jsx("option", { value: "1h", children: "1 Hour" }), _jsx("option", { value: "24h", children: "24 Hours" }), _jsx("option", { value: "7d", children: "7 Days" })] })] }) })] }), _jsxs("div", { className: "flex flex-wrap gap-2 mb-4", children: [_jsx("button", { onClick: () => toggleModel('all'), className: `px-3 py-1 rounded-full text-sm font-medium transition-colors ${selectedModels.includes('all')
                            ? 'bg-slate-900 text-white'
                            : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`, children: "All Models" }), models.map(model => (_jsx("button", { onClick: () => toggleModel(model), className: `px-3 py-1 rounded-full text-sm font-medium transition-colors ${selectedModels.includes(model) || selectedModels.includes('all')
                            ? 'text-white'
                            : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`, style: {
                            backgroundColor: selectedModels.includes(model) || selectedModels.includes('all')
                                ? getModelColor(model)
                                : undefined
                        }, children: model }, model)))] }), _jsxs("div", { className: "relative bg-slate-50 rounded-lg p-4", children: [_jsxs("svg", { width: chartWidth, height: chartHeight, className: "overflow-visible", children: [_jsx("defs", { children: _jsx("pattern", { id: "grid", width: "50", height: "20", patternUnits: "userSpaceOnUse", children: _jsx("path", { d: "M 50 0 L 0 0 0 20", fill: "none", stroke: "#E2E8F0", strokeWidth: "1" }) }) }), _jsx("rect", { width: "100%", height: "100%", fill: "url(#grid)" }), _jsx("line", { x1: "0", y1: chartHeight / 2, x2: chartWidth, y2: chartHeight / 2, stroke: "#94A3B8", strokeWidth: "1", strokeDasharray: "2,2" }), _jsx("text", { x: "-10", y: chartHeight / 2 - 5, textAnchor: "end", className: "text-xs fill-slate-500", children: "$0" }), _jsxs("text", { x: "-10", y: "15", textAnchor: "end", className: "text-xs fill-green-600", children: ["+$", maxPnL.toFixed(0)] }), _jsxs("text", { x: "-10", y: chartHeight - 5, textAnchor: "end", className: "text-xs fill-red-600", children: ["-$", maxPnL.toFixed(0)] }), models.map(model => {
                                if (!selectedModels.includes('all') && !selectedModels.includes(model))
                                    return null;
                                const pnlData = calculateModelPnL(model);
                                if (pnlData.length === 0)
                                    return null;
                                const points = pnlData.map((point, index) => {
                                    const x = (index / Math.max(pnlData.length - 1, 1)) * chartWidth;
                                    const y = chartHeight / 2 - (point.pnl / maxPnL) * (chartHeight / 2);
                                    return `${x},${y}`;
                                }).join(' ');
                                return (_jsxs("g", { children: [_jsx("polyline", { points: points, fill: "none", stroke: getModelColor(model), strokeWidth: "2", strokeLinejoin: "round", strokeLinecap: "round" }), pnlData.map((point, index) => {
                                            const x = (index / Math.max(pnlData.length - 1, 1)) * chartWidth;
                                            const y = chartHeight / 2 - (point.pnl / maxPnL) * (chartHeight / 2);
                                            return (_jsx("circle", { cx: x, cy: y, r: "3", fill: getModelColor(model), className: "hover:r-4 transition-all cursor-pointer" }, index));
                                        })] }, model));
                            })] }), filteredTrades.length === 0 && (_jsx("div", { className: "absolute inset-0 flex items-center justify-center", children: _jsxs("div", { className: "text-center text-slate-500", children: [_jsx("span", { className: "text-4xl mb-2 block", children: "\uD83D\uDCC8" }), _jsx("p", { children: "No trading data available for the selected time range" })] }) }))] }), _jsx("div", { className: "grid grid-cols-1 md:grid-cols-4 gap-4 mt-6", children: models.map(model => {
                    const modelTrades = filteredTrades.filter(t => t.model_used === model);
                    const totalPnL = modelTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
                    const winRate = modelTrades.length > 0
                        ? modelTrades.filter(t => (t.pnl || 0) > 0).length / modelTrades.length
                        : 0;
                    return (_jsxs("div", { className: "bg-slate-50 rounded-lg p-3", children: [_jsxs("div", { className: "flex items-center space-x-2 mb-2", children: [_jsx("div", { className: "w-3 h-3 rounded-full", style: { backgroundColor: getModelColor(model) } }), _jsx("span", { className: "text-sm font-medium text-slate-700 truncate", children: model })] }), _jsxs("div", { className: "space-y-1", children: [_jsxs("div", { className: "text-xs text-slate-500", children: ["Trades: ", modelTrades.length] }), _jsxs("div", { className: `text-sm font-medium ${totalPnL >= 0 ? 'text-green-600' : 'text-red-600'}`, children: ["P&L: $", totalPnL.toFixed(2)] }), _jsxs("div", { className: "text-xs text-slate-500", children: ["Win Rate: ", (winRate * 100).toFixed(1), "%"] })] })] }, model));
                }) })] }));
};
export default PerformanceTrends;

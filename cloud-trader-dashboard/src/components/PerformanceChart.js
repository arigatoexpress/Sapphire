import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
const PerformanceChart = ({ data: initialData, detailed = false }) => {
    const [performanceData, setPerformanceData] = useState([]);
    const [loading, setLoading] = useState(true);
    // Mock performance data - in real implementation, this would come from your backend
    useEffect(() => {
        const generateMockData = () => {
            const data = [];
            const now = Date.now();
            let balance = 1000;
            for (let i = 23; i >= 0; i--) {
                const timestamp = now - (i * 60 * 60 * 1000); // Hourly data for last 24 hours
                const pnlChange = (Math.random() - 0.5) * 20; // Random P&L change
                balance += pnlChange;
                data.push({
                    timestamp,
                    balance: Math.max(950, balance), // Ensure balance doesn't go too low
                    pnl: pnlChange,
                });
            }
            setPerformanceData(data);
            setLoading(false);
        };
        generateMockData();
    }, []);
    const formatCurrency = (value) => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USDT',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(value);
    };
    const formatTime = (timestamp) => {
        return new Date(timestamp).toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
        });
    };
    if (loading) {
        return (_jsx("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: _jsxs("div", { className: "animate-pulse", children: [_jsx("div", { className: "h-6 bg-slate-200 rounded w-1/3 mb-4" }), _jsx("div", { className: "h-64 bg-slate-200 rounded" })] }) }));
    }
    const maxBalance = Math.max(...performanceData.map(d => d.balance));
    const minBalance = Math.min(...performanceData.map(d => d.balance));
    const range = maxBalance - minBalance;
    const chartHeight = 200;
    // Calculate points for the chart line
    const points = performanceData.map((data, index) => {
        const x = (index / (performanceData.length - 1)) * 100;
        const y = chartHeight - ((data.balance - minBalance) / range) * chartHeight;
        return `${x},${y}`;
    }).join(' ');
    const currentBalance = performanceData[performanceData.length - 1]?.balance || 0;
    const previousBalance = performanceData[performanceData.length - 2]?.balance || currentBalance;
    const changePercent = ((currentBalance - previousBalance) / previousBalance) * 100;
    return (_jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: [_jsxs("div", { className: "flex items-center justify-between mb-6", children: [_jsxs("div", { children: [_jsx("h3", { className: "text-lg font-semibold text-slate-900", children: "Performance" }), _jsx("p", { className: "text-sm text-slate-600", children: "24-hour balance chart" })] }), _jsxs("div", { className: "text-right", children: [_jsx("p", { className: "text-2xl font-bold text-slate-900", children: formatCurrency(currentBalance) }), _jsxs("p", { className: `text-sm font-medium ${changePercent >= 0 ? 'text-green-600' : 'text-red-600'}`, children: [changePercent >= 0 ? '+' : '', changePercent.toFixed(2), "%"] })] })] }), _jsxs("div", { className: "relative mb-4", children: [_jsxs("svg", { width: "100%", height: chartHeight + 20, className: "overflow-visible", children: [_jsx("defs", { children: _jsx("pattern", { id: "grid", width: "20", height: "20", patternUnits: "userSpaceOnUse", children: _jsx("path", { d: "M 20 0 L 0 0 0 20", fill: "none", stroke: "#f1f5f9", strokeWidth: "1" }) }) }), _jsx("rect", { width: "100%", height: chartHeight, fill: "url(#grid)" }), _jsx("polyline", { fill: "none", stroke: "#3b82f6", strokeWidth: "2", points: points }), performanceData.map((data, index) => {
                                const x = (index / (performanceData.length - 1)) * 100;
                                const y = chartHeight - ((data.balance - minBalance) / range) * chartHeight;
                                return (_jsx("circle", { cx: `${x}%`, cy: y, r: "3", fill: "#3b82f6", className: "hover:r-4 transition-all cursor-pointer" }, index));
                            })] }), _jsxs("div", { className: "absolute left-0 top-0 h-full flex flex-col justify-between text-xs text-slate-500 -ml-12", children: [_jsx("span", { children: formatCurrency(maxBalance) }), _jsx("span", { children: formatCurrency((maxBalance + minBalance) / 2) }), _jsx("span", { children: formatCurrency(minBalance) })] })] }), _jsxs("div", { className: "flex justify-between text-xs text-slate-500", children: [_jsx("span", { children: formatTime(performanceData[0]?.timestamp || 0) }), _jsx("span", { children: formatTime(performanceData[Math.floor(performanceData.length / 2)]?.timestamp || 0) }), _jsx("span", { children: formatTime(performanceData[performanceData.length - 1]?.timestamp || 0) })] }), _jsxs("div", { className: "grid grid-cols-3 gap-4 mt-6 pt-4 border-t border-slate-200", children: [_jsxs("div", { className: "text-center", children: [_jsx("p", { className: "text-sm text-slate-600", children: "24h High" }), _jsx("p", { className: "text-lg font-semibold text-slate-900", children: formatCurrency(maxBalance) })] }), _jsxs("div", { className: "text-center", children: [_jsx("p", { className: "text-sm text-slate-600", children: "24h Low" }), _jsx("p", { className: "text-lg font-semibold text-slate-900", children: formatCurrency(minBalance) })] }), _jsxs("div", { className: "text-center", children: [_jsx("p", { className: "text-sm text-slate-600", children: "Change" }), _jsxs("p", { className: `text-lg font-semibold ${changePercent >= 0 ? 'text-green-600' : 'text-red-600'}`, children: [changePercent >= 0 ? '+' : '', changePercent.toFixed(2), "%"] })] })] })] }));
};
export default PerformanceChart;

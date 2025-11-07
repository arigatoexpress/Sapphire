import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
import { useState, useEffect, useMemo } from 'react';
import { fetchAgentPerformance, fetchTradeHistory } from '../api/client';
const HistoricalPerformance = ({ agent, onClose }) => {
    const [performanceData, setPerformanceData] = useState([]);
    const [tradeHistory, setTradeHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [timeRange, setTimeRange] = useState('7d');
    const [activeTab, setActiveTab] = useState('performance');
    useEffect(() => {
        const loadData = async () => {
            setLoading(true);
            try {
                const endDate = new Date().toISOString();
                let startDate;
                if (timeRange === '24h') {
                    startDate = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
                }
                else if (timeRange === '7d') {
                    startDate = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
                }
                else if (timeRange === '30d') {
                    startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
                }
                const [perfResult, tradesResult] = await Promise.all([
                    fetchAgentPerformance(agent.id, startDate, endDate, 1000),
                    fetchTradeHistory(agent.id, undefined, startDate, endDate, 500),
                ]);
                setPerformanceData(perfResult.performance || []);
                setTradeHistory(tradesResult.trades || []);
            }
            catch (err) {
                console.error('Failed to load historical data:', err);
            }
            finally {
                setLoading(false);
            }
        };
        loadData();
    }, [agent.id, timeRange]);
    const chartData = useMemo(() => {
        if (!performanceData.length)
            return [];
        return performanceData.map(p => ({
            timestamp: new Date(p.timestamp).getTime(),
            equity: p.equity,
            pnl: p.total_pnl,
            winRate: p.win_rate || 0,
        })).sort((a, b) => a.timestamp - b.timestamp);
    }, [performanceData]);
    const maxEquity = Math.max(...chartData.map(d => d.equity), 1);
    const minEquity = Math.min(...chartData.map(d => d.equity), 0);
    const range = maxEquity - minEquity || 1;
    return (_jsx("div", { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm", children: _jsxs("div", { className: "relative w-full max-w-6xl max-h-[90vh] bg-brand-abyss border border-brand-border rounded-2xl shadow-2xl overflow-hidden", children: [_jsxs("div", { className: "flex items-center justify-between p-6 border-b border-brand-border", children: [_jsxs("div", { children: [_jsxs("h2", { className: "text-2xl font-bold text-brand-ice", children: [agent.name, " - Historical Performance"] }), _jsx("p", { className: "text-sm text-brand-muted mt-1", children: agent.model })] }), _jsx("button", { onClick: onClose, className: "px-4 py-2 text-sm font-medium text-brand-ice hover:text-red-400 transition-colors", children: "\u2715 Close" })] }), _jsxs("div", { className: "flex items-center justify-between p-4 border-b border-brand-border bg-brand-abyss/50", children: [_jsx("div", { className: "flex gap-2", children: ['24h', '7d', '30d', 'all'].map(range => (_jsx("button", { onClick: () => setTimeRange(range), className: `px-4 py-2 text-sm font-medium rounded-lg transition-colors ${timeRange === range
                                    ? 'bg-brand-accent-blue text-white'
                                    : 'bg-brand-border/30 text-brand-ice hover:bg-brand-border/50'}`, children: range === 'all' ? 'All Time' : range }, range))) }), _jsxs("div", { className: "flex gap-2", children: [_jsx("button", { onClick: () => setActiveTab('performance'), className: `px-4 py-2 text-sm font-medium rounded-lg transition-colors ${activeTab === 'performance'
                                        ? 'bg-brand-accent-blue text-white'
                                        : 'bg-brand-border/30 text-brand-ice hover:bg-brand-border/50'}`, children: "Performance" }), _jsxs("button", { onClick: () => setActiveTab('trades'), className: `px-4 py-2 text-sm font-medium rounded-lg transition-colors ${activeTab === 'trades'
                                        ? 'bg-brand-accent-blue text-white'
                                        : 'bg-brand-border/30 text-brand-ice hover:bg-brand-border/50'}`, children: ["Trades (", tradeHistory.length, ")"] })] })] }), _jsx("div", { className: "p-6 overflow-y-auto max-h-[calc(90vh-200px)]", children: loading ? (_jsx("div", { className: "flex items-center justify-center h-64", children: _jsx("div", { className: "animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-brand-accent-blue" }) })) : activeTab === 'performance' ? (_jsxs("div", { className: "space-y-6", children: [_jsxs("div", { className: "bg-brand-abyss/70 rounded-xl p-6 border border-brand-border", children: [_jsx("h3", { className: "text-lg font-semibold text-brand-ice mb-4", children: "Equity Curve" }), _jsx("div", { className: "h-64 relative", children: chartData.length > 0 ? (_jsx("svg", { className: "w-full h-full", viewBox: `0 0 ${chartData.length * 2} 200`, preserveAspectRatio: "none", children: _jsx("polyline", { fill: "none", stroke: "rgb(56, 189, 248)", strokeWidth: "2", points: chartData.map((d, i) => `${i * 2},${200 - ((d.equity - minEquity) / range) * 200}`).join(' ') }) })) : (_jsx("div", { className: "flex items-center justify-center h-full text-brand-muted", children: "No performance data available" })) })] }), _jsxs("div", { className: "grid grid-cols-2 md:grid-cols-4 gap-4", children: [_jsxs("div", { className: "bg-brand-abyss/70 rounded-xl p-4 border border-brand-border", children: [_jsx("div", { className: "text-sm text-brand-muted", children: "Total P&L" }), _jsxs("div", { className: `text-2xl font-bold mt-1 ${performanceData[performanceData.length - 1]?.total_pnl >= 0
                                                    ? 'text-green-400'
                                                    : 'text-red-400'}`, children: ["$", performanceData[performanceData.length - 1]?.total_pnl.toFixed(2) || '0.00'] })] }), _jsxs("div", { className: "bg-brand-abyss/70 rounded-xl p-4 border border-brand-border", children: [_jsx("div", { className: "text-sm text-brand-muted", children: "Total Trades" }), _jsx("div", { className: "text-2xl font-bold mt-1 text-brand-ice", children: performanceData[performanceData.length - 1]?.total_trades || 0 })] }), _jsxs("div", { className: "bg-brand-abyss/70 rounded-xl p-4 border border-brand-border", children: [_jsx("div", { className: "text-sm text-brand-muted", children: "Win Rate" }), _jsxs("div", { className: "text-2xl font-bold mt-1 text-brand-ice", children: [performanceData[performanceData.length - 1]?.win_rate?.toFixed(1) || '0.0', "%"] })] }), _jsxs("div", { className: "bg-brand-abyss/70 rounded-xl p-4 border border-brand-border", children: [_jsx("div", { className: "text-sm text-brand-muted", children: "Current Equity" }), _jsxs("div", { className: "text-2xl font-bold mt-1 text-brand-ice", children: ["$", performanceData[performanceData.length - 1]?.equity.toFixed(2) || '0.00'] })] })] })] })) : (_jsx("div", { className: "space-y-2", children: tradeHistory.length > 0 ? (tradeHistory.map((trade, idx) => (_jsx("div", { className: "bg-brand-abyss/70 rounded-lg p-4 border border-brand-border hover:border-brand-accent-blue/50 transition-colors", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { className: "flex items-center gap-4", children: [_jsx("span", { className: `px-3 py-1 rounded-full text-xs font-semibold ${trade.side === 'BUY'
                                                    ? 'bg-green-500/20 text-green-400'
                                                    : 'bg-red-500/20 text-red-400'}`, children: trade.side }), _jsx("span", { className: "text-brand-ice font-medium", children: trade.symbol }), _jsx("span", { className: "text-brand-muted text-sm", children: new Date(trade.timestamp).toLocaleString() })] }), _jsxs("div", { className: "flex items-center gap-6 text-sm", children: [_jsxs("div", { children: [_jsx("span", { className: "text-brand-muted", children: "Price: " }), _jsxs("span", { className: "text-brand-ice", children: ["$", trade.price.toFixed(4)] })] }), _jsxs("div", { children: [_jsx("span", { className: "text-brand-muted", children: "Qty: " }), _jsx("span", { className: "text-brand-ice", children: trade.quantity.toFixed(6) })] }), _jsxs("div", { children: [_jsx("span", { className: "text-brand-muted", children: "Notional: " }), _jsxs("span", { className: "text-brand-ice", children: ["$", trade.notional.toFixed(2)] })] })] })] }) }, idx)))) : (_jsx("div", { className: "text-center py-12 text-brand-muted", children: "No trades found for this period" })) })) })] }) }));
};
export default HistoricalPerformance;

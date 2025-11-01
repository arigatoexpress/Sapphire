import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo, Suspense, lazy } from 'react';
// Lazy load the chart components to reduce bundle size
const AreaChart = lazy(() => import('recharts').then(module => ({ default: module.AreaChart })));
const Area = lazy(() => import('recharts').then(module => ({ default: module.Area })));
const XAxis = lazy(() => import('recharts').then(module => ({ default: module.XAxis })));
const YAxis = lazy(() => import('recharts').then(module => ({ default: module.YAxis })));
const CartesianGrid = lazy(() => import('recharts').then(module => ({ default: module.CartesianGrid })));
const Tooltip = lazy(() => import('recharts').then(module => ({ default: module.Tooltip })));
const ResponsiveContainer = lazy(() => import('recharts').then(module => ({ default: module.ResponsiveContainer })));
const toUnix = (input) => {
    const date = typeof input === 'number' ? new Date(input) : new Date(input);
    return Math.floor(date.getTime() / 1000);
};
const PortfolioPerformance = ({ balanceSeries, priceSeries }) => {
    const chartData = useMemo(() => {
        // Combine balance and price data by timestamp
        const dataMap = new Map();
        // Add balance data
        balanceSeries.forEach((point) => {
            if (typeof point.balance === 'number') {
                const time = toUnix(point.timestamp);
                dataMap.set(time, { ...dataMap.get(time), time, balance: point.balance });
            }
        });
        // Add price data
        priceSeries.forEach((point) => {
            if (typeof point.price === 'number') {
                const time = toUnix(point.timestamp);
                dataMap.set(time, { ...dataMap.get(time), time, price: point.price });
            }
        });
        // Convert to array and sort by time
        return Array.from(dataMap.values()).sort((a, b) => a.time - b.time);
    }, [balanceSeries, priceSeries]);
    const formatTime = (time) => {
        return new Date(time * 1000).toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
        });
    };
    if (chartData.length === 0) {
        return (_jsx("div", { className: "h-64 w-full flex items-center justify-center text-slate-400", children: _jsx("p", { children: "No performance data available" }) }));
    }
    return (_jsx(Suspense, { fallback: _jsx("div", { className: "h-64 w-full flex items-center justify-center text-slate-400", children: _jsx("div", { className: "animate-pulse", children: "Loading chart..." }) }), children: _jsx(ResponsiveContainer, { width: "100%", height: 256, children: _jsxs(AreaChart, { data: chartData, children: [_jsx(CartesianGrid, { strokeDasharray: "3 3", stroke: "rgba(148, 163, 184, 0.1)" }), _jsx(XAxis, { dataKey: "time", tickFormatter: formatTime, stroke: "#cbd5f5", fontSize: 12 }), _jsx(YAxis, { stroke: "#cbd5f5", fontSize: 12, tickFormatter: (value) => `$${value.toFixed(0)}` }), _jsx(Tooltip, { labelFormatter: (time) => new Date(time * 1000).toLocaleString(), formatter: (value, name) => [
                            `$${Number(value).toFixed(2)}`,
                            String(name) === 'balance' ? 'Portfolio Balance' : 'Price'
                        ], contentStyle: {
                            backgroundColor: 'rgba(15, 23, 42, 0.95)',
                            border: '1px solid rgba(148, 163, 184, 0.2)',
                            borderRadius: '8px',
                            color: '#cbd5f5',
                        } }), _jsx(Area, { type: "monotone", dataKey: "balance", stroke: "#4c63ff", fill: "rgba(76, 99, 255, 0.25)", strokeWidth: 2 }), _jsx(Area, { type: "monotone", dataKey: "price", stroke: "#22d3ee", fill: "rgba(34, 211, 238, 0.1)", strokeWidth: 1 })] }) }) }));
};
export default PortfolioPerformance;

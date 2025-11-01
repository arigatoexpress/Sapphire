import React, { useMemo, Suspense, lazy } from 'react';

// Lazy load the chart components to reduce bundle size
const AreaChart = lazy(() => import('recharts').then(module => ({ default: module.AreaChart })));
const Area = lazy(() => import('recharts').then(module => ({ default: module.Area })));
const XAxis = lazy(() => import('recharts').then(module => ({ default: module.XAxis })));
const YAxis = lazy(() => import('recharts').then(module => ({ default: module.YAxis })));
const CartesianGrid = lazy(() => import('recharts').then(module => ({ default: module.CartesianGrid })));
const Tooltip = lazy(() => import('recharts').then(module => ({ default: module.Tooltip })));
const ResponsiveContainer = lazy(() => import('recharts').then(module => ({ default: module.ResponsiveContainer })));

interface PerformanceDatum {
    timestamp: string | number;
    balance?: number;
    price?: number;
}

interface PortfolioPerformanceProps {
    balanceSeries: PerformanceDatum[];
    priceSeries: PerformanceDatum[];
}

const toUnix = (input: string | number) => {
    const date = typeof input === 'number' ? new Date(input) : new Date(input);
    return Math.floor(date.getTime() / 1000);
};

const PortfolioPerformance: React.FC<PortfolioPerformanceProps> = ({ balanceSeries, priceSeries }) => {
    const chartData = useMemo(() => {
        // Combine balance and price data by timestamp
        const dataMap = new Map<number, { time: number; balance?: number; price?: number }>();

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

    const formatTime = (time: number) => {
        return new Date(time * 1000).toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    if (chartData.length === 0) {
        return (
            <div className="h-64 w-full flex items-center justify-center text-slate-400">
                <p>No performance data available</p>
            </div>
        );
    }

    return (
        <Suspense fallback={
            <div className="h-64 w-full flex items-center justify-center text-slate-400">
                <div className="animate-pulse">Loading chart...</div>
            </div>
        }>
            <ResponsiveContainer width="100%" height={256}>
                <AreaChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.1)" />
                    <XAxis
                        dataKey="time"
                        tickFormatter={formatTime}
                        stroke="#cbd5f5"
                        fontSize={12}
                    />
                    <YAxis
                        stroke="#cbd5f5"
                        fontSize={12}
                        tickFormatter={(value) => `$${value.toFixed(0)}`}
                    />
                    <Tooltip
                        labelFormatter={(time) => new Date(time * 1000).toLocaleString()}
                        formatter={(value: any, name: any) => [
                            `$${Number(value).toFixed(2)}`,
                            String(name) === 'balance' ? 'Portfolio Balance' : 'Price'
                        ]}
                        contentStyle={{
                            backgroundColor: 'rgba(15, 23, 42, 0.95)',
                            border: '1px solid rgba(148, 163, 184, 0.2)',
                            borderRadius: '8px',
                            color: '#cbd5f5',
                        }}
                    />
                    <Area
                        type="monotone"
                        dataKey="balance"
                        stroke="#4c63ff"
                        fill="rgba(76, 99, 255, 0.25)"
                        strokeWidth={2}
                    />
                    <Area
                        type="monotone"
                        dataKey="price"
                        stroke="#22d3ee"
                        fill="rgba(34, 211, 238, 0.1)"
                        strokeWidth={1}
                    />
                </AreaChart>
            </ResponsiveContainer>
        </Suspense>
    );
};

export default PortfolioPerformance;


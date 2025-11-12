import React from 'react';
interface PerformanceData {
    timestamp: number;
    balance: number;
    pnl: number;
}
interface PerformanceChartProps {
    data?: PerformanceData[];
    detailed?: boolean;
}
declare const PerformanceChart: React.FC<PerformanceChartProps>;
export default PerformanceChart;

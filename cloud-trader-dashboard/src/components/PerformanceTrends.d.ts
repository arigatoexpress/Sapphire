import React from 'react';
interface TradeRecord {
    id: string;
    symbol: string;
    side: string;
    quantity: number;
    price: number;
    timestamp: string;
    model_used: string;
    confidence: number;
    status: string;
    pnl?: number;
}
interface PerformanceTrendsProps {
    trades: TradeRecord[];
}
declare const PerformanceTrends: React.FC<PerformanceTrendsProps>;
export default PerformanceTrends;

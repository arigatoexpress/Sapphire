import React from 'react';
interface Position {
    symbol: string;
    side: string;
    size: number;
    entry_price: number;
    current_price: number;
    pnl: number;
    pnl_percent: number;
    leverage: number;
    model_used: string;
    timestamp: string;
}
interface LivePositionsProps {
    positions: Position[];
}
declare const LivePositions: React.FC<LivePositionsProps>;
export default LivePositions;

import React from 'react';
interface ModelMetrics {
    model_name: string;
    total_decisions: number;
    successful_trades: number;
    avg_confidence: number;
    avg_response_time: number;
    win_rate: number;
    total_pnl: number;
    last_decision: string | null;
}
interface ModelPerformanceProps {
    models: ModelMetrics[];
}
declare const ModelPerformance: React.FC<ModelPerformanceProps>;
export default ModelPerformance;

import React from 'react';
interface ReasoningEntry {
    model_name: string;
    decision: string;
    reasoning: string;
    confidence: number;
    context: any;
    timestamp: string;
    symbol: string;
}
interface ModelReasoningProps {
    reasoning: ReasoningEntry[];
}
declare const ModelReasoning: React.FC<ModelReasoningProps>;
export default ModelReasoning;

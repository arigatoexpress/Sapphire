import React from 'react';
interface CrowdSentimentWidgetProps {
    totalVotes: number;
    bullishVotes: number;
    bearishVotes: number;
    hasVoted: boolean;
    onVote: (vote: 'bullish' | 'bearish') => void;
    onAuthenticate: () => void;
    isAuthenticated: boolean;
    onReset?: () => void;
    loading?: boolean;
}
declare const CrowdSentimentWidget: React.FC<CrowdSentimentWidgetProps>;
export default CrowdSentimentWidget;

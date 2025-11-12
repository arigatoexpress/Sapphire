import type { User } from 'firebase/auth';
interface CrowdSentimentState {
    totalVotes: number;
    bullishVotes: number;
    bearishVotes: number;
    hasVoted: boolean;
    dateKey: string;
}
export declare const useCrowdSentiment: (user: User | null) => [CrowdSentimentState, (vote: "bullish" | "bearish") => Promise<void>, () => void, boolean];
export default useCrowdSentiment;

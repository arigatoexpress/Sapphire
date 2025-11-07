export interface LeaderboardEntry {
    id: string;
    username: string;
    displayName?: string;
    publicId?: string;
    score: number;
    points?: number;
    lastActive?: string;
    checkIns?: number;
    votes?: number;
    comments?: number;
}
export interface CommunityComment {
    id: string;
    publicId?: string;
    message: string;
    username?: string;
    displayName?: string;
    createdAt: string;
    avatarUrl?: string;
    mentionedTickers: string[];
}
export declare const recordCheckIn: (user: {
    uid?: string;
    email?: string | null;
}) => Promise<void>;
export declare const addCommunityComment: (user: {
    uid?: string;
    email?: string | null;
    displayName?: string | null;
    photoURL?: string | null;
}, message: string) => Promise<void>;
export interface SentimentSnapshot {
    symbol: string;
    bullish: number;
    bearish: number;
    neutral: number;
    total?: number;
    hasVoted?: boolean;
    dateKey?: string;
}
export declare const castVote: (user: {
    uid?: string;
}, sentiment: "bullish" | "bearish" | "neutral") => Promise<void>;
export declare const subscribeSentiment: (user: {
    uid?: string;
} | null, callback: (snapshot: SentimentSnapshot) => void) => () => void;
export declare const isRealtimeCommunityEnabled: () => boolean;
export declare const subscribeCommunityComments: (callback: (comments: CommunityComment[]) => void) => () => void;
export declare const subscribeLeaderboard: (callback: (leaderboard: LeaderboardEntry[]) => void, limit?: number) => () => void;

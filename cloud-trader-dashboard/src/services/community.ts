// Community service stubs
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

export const recordCheckIn = async (user: { uid?: string; email?: string | null }): Promise<void> => {
  // Stub implementation
};

export const addCommunityComment = async (user: { uid?: string; email?: string | null; displayName?: string | null; photoURL?: string | null }, message: string): Promise<void> => {
  // Stub implementation
};

export interface SentimentSnapshot {
  symbol: string;
  bullish: number;
  bearish: number;
  neutral: number;
  total?: number;
  hasVoted?: boolean;
  dateKey?: string;
}

export const castVote = async (user: { uid?: string }, sentiment: 'bullish' | 'bearish' | 'neutral'): Promise<void> => {
  // Stub implementation
};

export const subscribeSentiment = (user: { uid?: string } | null, callback: (snapshot: SentimentSnapshot) => void) => {
  // Stub implementation
  return () => {}; // Return unsubscribe function
};

export const isRealtimeCommunityEnabled = (): boolean => {
  return false;
};

export const subscribeCommunityComments = (callback: (comments: CommunityComment[]) => void) => {
  // Stub implementation
  return () => {}; // Return unsubscribe function
};

export const subscribeLeaderboard = (callback: (leaderboard: LeaderboardEntry[]) => void, limit?: number) => {
  // Stub implementation
  return () => {}; // Return unsubscribe function
};


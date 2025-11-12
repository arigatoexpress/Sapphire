import { type LeaderboardEntry } from '../services/community';
declare const useCommunityLeaderboard: (limit?: number) => [LeaderboardEntry[], boolean];
export default useCommunityLeaderboard;

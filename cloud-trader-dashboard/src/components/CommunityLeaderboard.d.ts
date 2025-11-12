import React from 'react';
import type { LeaderboardEntry } from '../services/community';
interface CommunityLeaderboardProps {
    entries: LeaderboardEntry[];
    loading?: boolean;
}
declare const CommunityLeaderboard: React.FC<CommunityLeaderboardProps>;
export default CommunityLeaderboard;

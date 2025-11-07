import { useEffect, useState } from 'react';
import {
  subscribeLeaderboard,
  type LeaderboardEntry,
  isRealtimeCommunityEnabled,
} from '../services/community';

const FALLBACK_DATA: LeaderboardEntry[] = [];

const useCommunityLeaderboard = (limit = 10): [LeaderboardEntry[], boolean] => {
  const [entries, setEntries] = useState<LeaderboardEntry[]>(FALLBACK_DATA);
  const [loading, setLoading] = useState<boolean>(isRealtimeCommunityEnabled());

  useEffect(() => {
    if (!isRealtimeCommunityEnabled()) {
      return;
    }

    setLoading(true);
    const unsubscribe = subscribeLeaderboard((leaderboard: LeaderboardEntry[]) => {
      setEntries(leaderboard);
      setLoading(false);
    }, limit);

    return () => unsubscribe();
  }, [limit]);

  return [entries, loading];
};

export default useCommunityLeaderboard;


import { useEffect, useState } from 'react';
import { subscribeLeaderboard, isRealtimeCommunityEnabled, } from '../services/community';
const FALLBACK_DATA = [];
const useCommunityLeaderboard = (limit = 10) => {
    const [entries, setEntries] = useState(FALLBACK_DATA);
    const [loading, setLoading] = useState(isRealtimeCommunityEnabled());
    useEffect(() => {
        if (!isRealtimeCommunityEnabled()) {
            return;
        }
        setLoading(true);
        const unsubscribe = subscribeLeaderboard((leaderboard) => {
            setEntries(leaderboard);
            setLoading(false);
        }, limit);
        return () => unsubscribe();
    }, [limit]);
    return [entries, loading];
};
export default useCommunityLeaderboard;

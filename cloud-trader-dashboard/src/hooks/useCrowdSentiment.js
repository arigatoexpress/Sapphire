import { useEffect, useMemo, useState } from 'react';
import { castVote, subscribeSentiment, isRealtimeCommunityEnabled, } from '../services/community';
const FALLBACK_KEY = 'sapphire-crowd-sentiment-fallback';
const todayKey = () => new Date().toISOString().slice(0, 10);
const readFallbackState = () => {
    try {
        const raw = localStorage.getItem(FALLBACK_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed.dateKey === todayKey()) {
                return parsed;
            }
        }
    }
    catch (error) {
        console.warn('Crowd sentiment fallback read failed', error);
    }
    return { totalVotes: 0, bullishVotes: 0, bearishVotes: 0, hasVoted: false, dateKey: todayKey() };
};
export const useCrowdSentiment = (user) => {
    const [state, setState] = useState(() => readFallbackState());
    const [loading, setLoading] = useState(isRealtimeCommunityEnabled());
    useEffect(() => {
        if (!isRealtimeCommunityEnabled()) {
            return;
        }
        setLoading(true);
        const unsubscribe = subscribeSentiment(user, (snapshot) => {
            setState({
                totalVotes: snapshot.total ?? 0,
                bullishVotes: snapshot.bullish,
                bearishVotes: snapshot.bearish,
                hasVoted: snapshot.hasVoted ?? false,
                dateKey: snapshot.dateKey ?? todayKey(),
            });
            setLoading(false);
        });
        return () => unsubscribe();
    }, [user]);
    useEffect(() => {
        if (!isRealtimeCommunityEnabled()) {
            try {
                localStorage.setItem(FALLBACK_KEY, JSON.stringify(state));
            }
            catch (error) {
                console.warn('Crowd sentiment fallback write failed', error);
            }
        }
    }, [state]);
    const fallbackVote = useMemo(() => {
        if (isRealtimeCommunityEnabled()) {
            return null;
        }
        return (vote) => {
            setState((prev) => {
                if (prev.hasVoted) {
                    return prev;
                }
                const next = {
                    totalVotes: prev.totalVotes + 1,
                    bullishVotes: vote === 'bullish' ? prev.bullishVotes + 1 : prev.bullishVotes,
                    bearishVotes: vote === 'bearish' ? prev.bearishVotes + 1 : prev.bearishVotes,
                    hasVoted: true,
                    dateKey: todayKey(),
                };
                return next;
            });
        };
    }, []);
    const registerVote = async (direction) => {
        if (!user) {
            throw new Error('Authentication required to vote');
        }
        if (isRealtimeCommunityEnabled()) {
            await castVote(user, direction);
        }
        else if (fallbackVote) {
            fallbackVote(direction);
        }
    };
    const reset = () => {
        if (!isRealtimeCommunityEnabled()) {
            const next = { totalVotes: 0, bullishVotes: 0, bearishVotes: 0, hasVoted: false, dateKey: todayKey() };
            setState(next);
            try {
                localStorage.setItem(FALLBACK_KEY, JSON.stringify(next));
            }
            catch (error) {
                console.warn('Crowd sentiment fallback reset failed', error);
            }
        }
    };
    return [state, registerVote, reset, loading];
};
export default useCrowdSentiment;

import { useEffect, useMemo, useState } from 'react';
import type { User } from 'firebase/auth';
import {
  castVote,
  subscribeSentiment,
  type SentimentSnapshot,
  isRealtimeCommunityEnabled,
} from '../services/community';

interface CrowdSentimentState {
  totalVotes: number;
  bullishVotes: number;
  bearishVotes: number;
  hasVoted: boolean;
  dateKey: string;
}

const FALLBACK_KEY = 'sapphire-crowd-sentiment-fallback';

const todayKey = (): string => new Date().toISOString().slice(0, 10);

const readFallbackState = (): CrowdSentimentState => {
    try {
    const raw = localStorage.getItem(FALLBACK_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as CrowdSentimentState;
      if (parsed.dateKey === todayKey()) {
        return parsed;
      }
      }
  } catch (error) {
    console.warn('Crowd sentiment fallback read failed', error);
  }
  return { totalVotes: 0, bullishVotes: 0, bearishVotes: 0, hasVoted: false, dateKey: todayKey() };
};

export const useCrowdSentiment = (
  user: User | null,
): [CrowdSentimentState, (vote: 'bullish' | 'bearish') => Promise<void>, () => void, boolean] => {
  const [state, setState] = useState<CrowdSentimentState>(() => readFallbackState());
  const [loading, setLoading] = useState<boolean>(isRealtimeCommunityEnabled());

  useEffect(() => {
    if (!isRealtimeCommunityEnabled()) {
      return;
    }

    setLoading(true);
    const unsubscribe = subscribeSentiment(user, (snapshot: SentimentSnapshot) => {
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
      } catch (error) {
        console.warn('Crowd sentiment fallback write failed', error);
      }
    }
  }, [state]);

  const fallbackVote = useMemo(() => {
    if (isRealtimeCommunityEnabled()) {
      return null;
    }
    return (vote: 'bullish' | 'bearish') => {
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
        } satisfies CrowdSentimentState;
        return next;
      });
    };
  }, []);

  const registerVote = async (direction: 'bullish' | 'bearish') => {
    if (!user) {
      throw new Error('Authentication required to vote');
    }

    if (isRealtimeCommunityEnabled()) {
      await castVote(user, direction);
    } else if (fallbackVote) {
      fallbackVote(direction);
    }
  };

  const reset = () => {
    if (!isRealtimeCommunityEnabled()) {
      const next = { totalVotes: 0, bullishVotes: 0, bearishVotes: 0, hasVoted: false, dateKey: todayKey() };
      setState(next);
      try {
        localStorage.setItem(FALLBACK_KEY, JSON.stringify(next));
      } catch (error) {
        console.warn('Crowd sentiment fallback reset failed', error);
      }
    }
  };

  return [state, registerVote, reset, loading];
};

export default useCrowdSentiment;

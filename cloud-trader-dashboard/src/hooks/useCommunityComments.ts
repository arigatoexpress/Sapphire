import { useEffect, useState } from 'react';
import { type User } from 'firebase/auth';
import {
  addCommunityComment,
  subscribeCommunityComments,
  type CommunityComment,
  isRealtimeCommunityEnabled,
} from '../services/community';

const FALLBACK_STORAGE_KEY = 'sapphire-community-comments-fallback';

const readFallbackComments = (): CommunityComment[] => {
  try {
    const raw = localStorage.getItem(FALLBACK_STORAGE_KEY);
    if (raw) {
      return JSON.parse(raw) as CommunityComment[];
    }
  } catch (error) {
    console.warn('Community comments fallback read failed', error);
  }
  return [];
};

const useCommunityComments = (
  user: User | null,
): [CommunityComment[], (message: string) => Promise<void>, boolean] => {
  const [comments, setComments] = useState<CommunityComment[]>(() => readFallbackComments());
  const [loading, setLoading] = useState<boolean>(isRealtimeCommunityEnabled());

  useEffect(() => {
    if (!isRealtimeCommunityEnabled()) {
      return;
    }

    setLoading(true);
    const unsubscribe = subscribeCommunityComments((next: CommunityComment[]) => {
      setComments(next);
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (!isRealtimeCommunityEnabled()) {
    try {
        localStorage.setItem(FALLBACK_STORAGE_KEY, JSON.stringify(comments.slice(0, 50)));
      } catch (error) {
        console.warn('Community comments fallback write failed', error);
      }
    }
  }, [comments]);

  const submitComment = async (message: string) => {
    if (!user) {
      throw new Error('Authentication required to leave a comment');
    }

    if (isRealtimeCommunityEnabled()) {
      await addCommunityComment(user, message);
    } else {
      const fallbackComment: CommunityComment = {
        id: typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
          : `${Date.now()}-${Math.random()}`,
        publicId: 'local-preview',
        displayName: user.displayName || user.email || 'Anonymous',
      message,
        createdAt: new Date().toISOString(),
        avatarUrl: user.photoURL || undefined,
        mentionedTickers: [],
    };
      setComments((prev) => [fallbackComment, ...prev].slice(0, 50));
    }
  };

  return [comments, submitComment, loading];
};

export type { CommunityComment };
export default useCommunityComments;


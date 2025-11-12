import { useEffect, useState } from 'react';
import { addCommunityComment, subscribeCommunityComments, isRealtimeCommunityEnabled, } from '../services/community';
const FALLBACK_STORAGE_KEY = 'sapphire-community-comments-fallback';
const readFallbackComments = () => {
    try {
        const raw = localStorage.getItem(FALLBACK_STORAGE_KEY);
        if (raw) {
            return JSON.parse(raw);
        }
    }
    catch (error) {
        console.warn('Community comments fallback read failed', error);
    }
    return [];
};
const useCommunityComments = (user) => {
    const [comments, setComments] = useState(() => readFallbackComments());
    const [loading, setLoading] = useState(isRealtimeCommunityEnabled());
    useEffect(() => {
        if (!isRealtimeCommunityEnabled()) {
            return;
        }
        setLoading(true);
        const unsubscribe = subscribeCommunityComments((next) => {
            setComments(next);
            setLoading(false);
        });
        return () => unsubscribe();
    }, []);
    useEffect(() => {
        if (!isRealtimeCommunityEnabled()) {
            try {
                localStorage.setItem(FALLBACK_STORAGE_KEY, JSON.stringify(comments.slice(0, 50)));
            }
            catch (error) {
                console.warn('Community comments fallback write failed', error);
            }
        }
    }, [comments]);
    const submitComment = async (message) => {
        if (!user) {
            throw new Error('Authentication required to leave a comment');
        }
        if (isRealtimeCommunityEnabled()) {
            await addCommunityComment(user, message);
        }
        else {
            const fallbackComment = {
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
export default useCommunityComments;

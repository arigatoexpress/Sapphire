import React from 'react';
import type { User } from 'firebase/auth';
import type { CommunityComment } from '../hooks/useCommunityComments';
type SocialProvider = 'google' | 'facebook' | 'apple';
interface CommunityFeedbackProps {
    comments: CommunityComment[];
    onSubmit: (message: string) => Promise<void>;
    user: User | null;
    loading: boolean;
    onSignOut: () => Promise<void>;
    authEnabled: boolean;
    authError?: string | null;
    onSocialSignIn: (provider: SocialProvider) => Promise<void>;
    onEmailSignIn: (email: string, password: string) => Promise<void>;
    onEmailSignUp: (email: string, password: string, displayName?: string) => Promise<void>;
    commentSubmitting?: boolean;
}
declare const CommunityFeedback: React.FC<CommunityFeedbackProps>;
export default CommunityFeedback;

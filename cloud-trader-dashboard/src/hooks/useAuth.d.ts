import { type User } from 'firebase/auth';
type SocialProvider = 'google' | 'facebook' | 'apple';
interface UseAuthResult {
    user: User | null;
    loading: boolean;
    signInWithSocial: (provider: SocialProvider) => Promise<void>;
    signUpWithEmail: (email: string, password: string, displayName?: string) => Promise<void>;
    signInWithEmail: (email: string, password: string) => Promise<void>;
    signOut: () => Promise<void>;
    enabled: boolean;
    error: string | null;
}
declare const useAuth: () => UseAuthResult;
export default useAuth;

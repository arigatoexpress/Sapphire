import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  onAuthStateChanged,
  signInWithPopup,
  signOut,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  updateProfile,
  type User,
} from 'firebase/auth';
import {
  auth,
  googleProvider,
  facebookProvider,
  appleProvider,
  firebaseEnabled,
  firebaseInitError,
} from '../firebase';

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

const useAuth = (): UseAuthResult => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!firebaseEnabled || !auth) {
      setLoading(false);
      return;
    }

    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const providerMap = useMemo(() => ({
    google: googleProvider,
    facebook: facebookProvider,
    apple: appleProvider,
  } satisfies Record<SocialProvider, typeof googleProvider>), []);

  const handleSocialSignIn = useCallback(async (provider: SocialProvider) => {
    if (!firebaseEnabled || !auth) return;
    const authProvider = providerMap[provider];
    if (!authProvider) {
      setError(`${provider} auth not configured`);
      return;
    }
    setError(null);
    await signInWithPopup(auth, authProvider);
  }, [providerMap]);

  const handleEmailSignUp = useCallback(async (email: string, password: string, displayName?: string) => {
    if (!firebaseEnabled || !auth) return;
    setError(null);
    const credential = await createUserWithEmailAndPassword(auth, email, password);
    if (displayName) {
      await updateProfile(credential.user, { displayName });
    }
  }, []);

  const handleEmailSignIn = useCallback(async (email: string, password: string) => {
    if (!firebaseEnabled || !auth) return;
    setError(null);
    await signInWithEmailAndPassword(auth, email, password);
  }, []);

  const handleSignOut = useCallback(async () => {
    if (!firebaseEnabled || !auth) {
      return;
    }
    await signOut(auth);
  }, []);

  return {
    user,
    loading,
    signInWithSocial: handleSocialSignIn,
    signUpWithEmail: handleEmailSignUp,
    signInWithEmail: handleEmailSignIn,
    signOut: handleSignOut,
    enabled: firebaseEnabled,
    error: error ?? firebaseInitError,
  };
};

export default useAuth;

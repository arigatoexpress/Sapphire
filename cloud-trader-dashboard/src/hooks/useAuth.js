import { useCallback, useEffect, useMemo, useState } from 'react';
import { onAuthStateChanged, signInWithPopup, signOut, createUserWithEmailAndPassword, signInWithEmailAndPassword, updateProfile, } from 'firebase/auth';
import { auth, googleProvider, facebookProvider, appleProvider, firebaseEnabled, firebaseInitError, } from '../firebase';
const useAuth = () => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
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
    }), []);
    const handleSocialSignIn = useCallback(async (provider) => {
        if (!firebaseEnabled || !auth)
            return;
        const authProvider = providerMap[provider];
        if (!authProvider) {
            setError(`${provider} auth not configured`);
            return;
        }
        setError(null);
        await signInWithPopup(auth, authProvider);
    }, [providerMap]);
    const handleEmailSignUp = useCallback(async (email, password, displayName) => {
        if (!firebaseEnabled || !auth)
            return;
        setError(null);
        const credential = await createUserWithEmailAndPassword(auth, email, password);
        if (displayName) {
            await updateProfile(credential.user, { displayName });
        }
    }, []);
    const handleEmailSignIn = useCallback(async (email, password) => {
        if (!firebaseEnabled || !auth)
            return;
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

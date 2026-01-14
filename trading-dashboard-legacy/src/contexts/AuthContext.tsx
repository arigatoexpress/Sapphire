import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import {
    User,
    signInWithEmailAndPassword,
    createUserWithEmailAndPassword,
    signOut,
    onAuthStateChanged,
    sendPasswordResetEmail,
    signInAnonymously
} from 'firebase/auth';
import { doc, setDoc, getDoc } from 'firebase/firestore';
import { auth, db } from '../firebase';

interface AuthContextType {
    user: User | null;
    loading: boolean;
    signIn: (email: string, password: string) => Promise<void>;
    signUp: (email: string, password: string) => Promise<void>;
    logout: () => Promise<void>;
    resetPassword: (email: string) => Promise<void>;
    enterAsGuest: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === null) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
    // DEV MODE: Mock User for seamless access
    const [user, setUser] = useState<User | null>({
        uid: 'dev-bypass',
        email: 'developer@sapphire.ai',
        emailVerified: true,
        isAnonymous: false,
        metadata: {},
        providerData: [],
        refreshToken: '',
        tenantId: null,
        delete: async () => { },
        getIdToken: async () => 'mock-dev-token',
        getIdTokenResult: async () => ({} as any),
        reload: async () => { },
        toJSON: () => ({}),
        displayName: 'Dev User',
        phoneNumber: null,
        photoURL: null,
    } as unknown as User);

    // DEV MODE: Loading is always false
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        // DEV MODE: Skip Firebase Auth subscription
        console.warn("Auth Bypass Active: Skipping Firebase Auth");
        return;

        /*
        // Original Auth Logic Preserved below for easy restoration
        // If auth is a mock object (no onAuthStateChanged), skip subscription
        if (typeof onAuthStateChanged !== 'function' || !auth.app) {
            console.warn("Skipping onAuthStateChanged (Demo Mode)");
            setLoading(false);
            return;
        }

        const unsubscribe = onAuthStateChanged(auth, async (user) => {
            setUser(user);

            // Create user profile in Firestore if it doesn't exist (non-blocking)
            if (user && db.type === 'firestore') { // Only try if db is real
                try {
                    const userRef = doc(db, 'users', user.uid);
                    const userSnap = await getDoc(userRef);

                    if (!userSnap.exists()) {
                        await setDoc(userRef, {
                            uid: user.uid,
                            email: user.email,
                            created_at: new Date().toISOString(),
                            total_points: 0,
                            streak_days: 0,
                            last_checkin: null
                        });
                    }
                } catch (error) {
                    console.error('Firestore error (non-blocking):', error);
                    // Don't block auth flow if Firestore fails
                }
            }

            setLoading(false);
        });

        return unsubscribe;
        */
    }, []);

    const signIn = async (email: string, password: string) => {
        await signInWithEmailAndPassword(auth, email, password);
    };

    const signUp = async (email: string, password: string) => {
        await createUserWithEmailAndPassword(auth, email, password);
    };

    const logout = async () => {
        await signOut(auth);
    };

    const resetPassword = async (email: string) => {
        await sendPasswordResetEmail(auth, email);
    };

    const enterAsGuest = async () => {
        await signInAnonymously(auth);
    };

    const value = {
        user,
        loading,
        signIn,
        signUp,
        logout,
        resetPassword,
        enterAsGuest
    };

    console.log('[AuthProvider] Rendering. loading:', loading, 'hasValue:', !!value);
    return (
        <AuthContext.Provider value={value}>
            {!loading && (
                <>
                    {console.log('[AuthProvider] Rendering Children')}
                    {children}
                </>
            )}
        </AuthContext.Provider>
    );
};

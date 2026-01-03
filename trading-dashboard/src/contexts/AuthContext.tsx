import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import {
    User,
    signInWithEmailAndPassword,
    createUserWithEmailAndPassword,
    signOut,
    onAuthStateChanged,
    sendPasswordResetEmail
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
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
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

    const value = {
        user,
        loading,
        signIn,
        signUp,
        logout,
        resetPassword
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

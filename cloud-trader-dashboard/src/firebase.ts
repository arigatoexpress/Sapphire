import { initializeApp, type FirebaseApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  FacebookAuthProvider,
  OAuthProvider,
  EmailAuthProvider,
  type Auth,
} from 'firebase/auth';
import { getFirestore, type Firestore } from 'firebase/firestore';

type FirebaseConfig = {
  apiKey?: string;
  authDomain?: string;
  projectId?: string;
  storageBucket?: string;
  messagingSenderId?: string;
  appId?: string;
};

const firebaseConfig: FirebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const isConfigValid = Object.values(firebaseConfig).every((value) => typeof value === 'string' && value.trim().length > 0);

let app: FirebaseApp | null = null;
let auth: Auth | null = null;
let googleProvider: GoogleAuthProvider | null = null;
let facebookProvider: FacebookAuthProvider | null = null;
let appleProvider: OAuthProvider | null = null;
let emailProvider: EmailAuthProvider | null = null;
let firebaseError: string | null = null;
let firestore: Firestore | null = null;

if (isConfigValid) {
  try {
    app = initializeApp(firebaseConfig as Required<FirebaseConfig>);
    auth = getAuth(app);
    auth.useDeviceLanguage();

    googleProvider = new GoogleAuthProvider();
    facebookProvider = new FacebookAuthProvider();
    facebookProvider.addScope('public_profile');
    facebookProvider.addScope('email');

    appleProvider = new OAuthProvider('apple.com');
    appleProvider.addScope('email');
    appleProvider.addScope('name');

    emailProvider = new EmailAuthProvider();

    firestore = getFirestore(app);
  } catch (error) {
    firebaseError = 'Failed to initialise Firebase';
    if (import.meta.env.DEV) {
      console.warn('[firebase]', firebaseError, error);
    }
  }
} else {
  firebaseError = 'Firebase configuration missing';
  if (import.meta.env.DEV) {
    console.warn('[firebase]', firebaseError, firebaseConfig);
  }
}

const authReady = Boolean(app && auth && googleProvider);

export const firebaseEnabled = authReady;
export const firestoreEnabled = Boolean(firestore);
export const firebaseInitError = firebaseError;

export { auth, googleProvider, facebookProvider, appleProvider, emailProvider, firestore };

export default app;


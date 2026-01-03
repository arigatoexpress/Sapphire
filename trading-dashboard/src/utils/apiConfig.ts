/**
 * Centralized API URL resolution for the Sapphire AI Trading system.
 * Eliminates hardcoded legacy URLs and ensures consistency across components.
 */

// Production Cloud Run URL (europe-west1 deployment)
const CLOUD_RUN_URL = 'https://sapphire-cloud-trader-267358751314.europe-west1.run.app';

export const getApiUrl = (): string => {
    // 1. Priority: Vite Environment Variable (Local Dev / Explicit Override)
    const envUrl = import.meta.env.VITE_API_URL;
    if (envUrl && !envUrl.includes('localhost') && !envUrl.includes('127.0.0.1')) {
        return envUrl.replace(/\/$/, ''); // Remove trailing slash
    }

    // 2. Production: Detect deployment environment
    if (typeof window !== 'undefined') {
        const hostname = window.location.hostname;

        // Cloud Run direct access - use current origin
        if (hostname.includes('run.app')) {
            return window.location.origin;
        }

        // Firebase Hosting or custom domain - use Cloud Run backend
        if (hostname.includes('web.app') || hostname.includes('sapphiretrade') || hostname.includes('xyz') || hostname.includes('firebaseapp.com')) {
            return CLOUD_RUN_URL;
        }
    }

    // 3. Absolute Fallback: Production Cloud Run Service
    return CLOUD_RUN_URL;
};

export const getWebSocketUrl = (path: string = '/ws/dashboard'): string => {
    const apiBase = getApiUrl();
    const protocol = apiBase.startsWith('https') ? 'wss' : 'ws';
    const host = apiBase.replace(/^https?:\/\//, '');
    return `${protocol}://${host}${path}`;
};

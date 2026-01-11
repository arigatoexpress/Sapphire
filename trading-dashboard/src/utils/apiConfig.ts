/**
 * Centralized API URL resolution for the Sapphire AI Trading system.
 * Supports both monolith (legacy) and microservices API Gateway.
 */

// Production URLs
const CLOUD_RUN_URL_LEGACY = 'https://sapphire-alpha-s77j6bxyra-uc.a.run.app';
const API_GATEWAY_URL = 'https://sapphire-api-gateway-s77j6bxyra-uc.a.run.app';

// Toggle: Microservices API Gateway is now deployed and active
const USE_MICROSERVICES = true;


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

        // Production environments (Firebase Hosting / Custom Domain)
        if (hostname.includes('web.app') || hostname.includes('sapphiretrade') || hostname.includes('xyz') || hostname.includes('firebaseapp.com')) {
            return USE_MICROSERVICES ? API_GATEWAY_URL : CLOUD_RUN_URL_LEGACY;
        }
    }

    // 3. Fallback: Use configured backend
    return USE_MICROSERVICES ? API_GATEWAY_URL : CLOUD_RUN_URL_LEGACY;
};


export const getWebSocketUrl = (path: string = '/ws/dashboard'): string => {
    const apiBase = getApiUrl();
    const protocol = apiBase.startsWith('https') ? 'wss' : 'ws';
    const host = apiBase.replace(/^https?:\/\//, '');
    return `${protocol}://${host}${path}`;
};

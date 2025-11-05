const DEFAULT_API_URL = 'https://api.sapphiretrade.xyz';
const DEFAULT_DASHBOARD_URL = 'https://api.sapphiretrade.xyz';
// Get API URL with fallback to current origin for development
const getApiUrl = () => {
    const envUrl = import.meta.env.VITE_API_URL;
    if (envUrl)
        return envUrl;
    if (typeof window !== 'undefined') {
        const origin = window.location.origin;
        const hostname = window.location.hostname;
        if (hostname === '127.0.0.1' || hostname === 'localhost') {
            return DEFAULT_API_URL;
        }
        // Use the direct service URL for production
        if (hostname === 'sapphiretrade.xyz' || hostname === 'www.sapphiretrade.xyz') {
            return 'https://api.sapphiretrade.xyz';
        }
        return origin;
    }
    // Fallback for SSR/development
    return DEFAULT_API_URL;
};
const API_URL = getApiUrl();
const DASHBOARD_URL = (() => {
    if (import.meta.env.VITE_DASHBOARD_URL)
        return import.meta.env.VITE_DASHBOARD_URL;
    if (typeof window !== 'undefined') {
        const hostname = window.location.hostname;
        if (hostname === '127.0.0.1' || hostname === 'localhost') {
            return DEFAULT_DASHBOARD_URL;
        }
        // Use the direct service URL for production dashboard endpoint
        if (hostname === 'sapphiretrade.xyz' || hostname === 'www.sapphiretrade.xyz') {
            return 'https://api.sapphiretrade.xyz';
        }
    }
    return DEFAULT_DASHBOARD_URL;
})();
// Rate limiting for API calls
const rateLimiter = {
    calls: new Map(),
    limits: {
        dashboard: { max: 30, window: 60000 }, // 30 calls per minute
        default: { max: 10, window: 60000 }, // 10 calls per minute
    },
    canMakeCall(endpoint) {
        const now = Date.now();
        const key = endpoint.split('/').pop() || 'default';
        const limit = this.limits[key] || this.limits.default;
        const calls = this.calls.get(key) || [];
        const recentCalls = calls.filter(call => now - call < limit.window);
        if (recentCalls.length >= limit.max) {
            return false;
        }
        recentCalls.push(now);
        this.calls.set(key, recentCalls);
        return true;
    }
};
const fetchWithTimeout = async (url, options = {}, timeout = 15_000) => {
    // Rate limiting check
    if (!rateLimiter.canMakeCall(url)) {
        throw new Error('Rate limit exceeded. Please wait before making another request.');
    }
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest', // CSRF protection
                ...options.headers,
            },
        });
        clearTimeout(id);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
        }
        return await response.json();
    }
    catch (error) {
        clearTimeout(id);
        if (error.name === 'AbortError') {
            throw new Error('Connection timeout or error');
        }
        throw new Error(`Connection Error: ${error.message}`);
    }
};
export const fetchHealth = async () => {
    return (await fetchWithTimeout(`${API_URL}/healthz`));
};
export const fetchDashboard = async () => {
    return (await fetchWithTimeout(`${DASHBOARD_URL}/dashboard`));
};
export const startTrader = async () => {
    return (await fetchWithTimeout(`${API_URL}/start`, { method: 'POST' }));
};
export const stopTrader = async () => {
    return (await fetchWithTimeout(`${API_URL}/stop`, { method: 'POST' }));
};

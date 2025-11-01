// Get API URL with fallback to current origin for development
const getApiUrl = () => {
    const envUrl = import.meta.env.VITE_API_URL;
    if (envUrl)
        return envUrl;
    // In production, use the same origin as the frontend
    if (typeof window !== 'undefined') {
        return window.location.origin;
    }
    // Fallback for SSR/development
    return 'http://localhost:8000';
};
const API_URL = getApiUrl();
const DASHBOARD_URL = import.meta.env.VITE_DASHBOARD_URL || API_URL;
const fetchWithTimeout = async (url, options = {}, timeout = 10_000) => {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        });
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return (await response.json());
    }
    finally {
        clearTimeout(id);
    }
};
export const fetchHealth = async () => {
    return (await fetchWithTimeout(`${API_URL}/healthz`));
};
export const postStart = async () => {
    return (await fetchWithTimeout(`${API_URL}/start`, { method: 'POST' }));
};
export const postStop = async () => {
    return (await fetchWithTimeout(`${API_URL}/stop`, { method: 'POST' }));
};
export const emergencyStop = async () => {
    const ORCHESTRATOR_URL = 'https://wallet-orchestrator-880429861698.us-central1.run.app';
    return (await fetchWithTimeout(`${ORCHESTRATOR_URL}/emergency_stop`, { method: 'POST' }));
};
export const fetchDashboard = async () => {
    return (await fetchWithTimeout(`${DASHBOARD_URL}/dashboard`));
};

const API_URL = import.meta.env.VITE_API_URL || 'https://cloud-trader-880429861698.us-central1.run.app';
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
    try {
        // Try the root endpoint first, fallback to healthz
        return (await fetchWithTimeout(`${API_URL}/`));
    }
    catch {
        // Fallback to healthz if root doesn't work
        return (await fetchWithTimeout(`${API_URL}/healthz`));
    }
};
export const fetchPortfolio = async () => {
    const ORCHESTRATOR_URL = 'https://wallet-orchestrator-880429861698.us-central1.run.app';
    return (await fetchWithTimeout(`${ORCHESTRATOR_URL}/portfolio`));
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

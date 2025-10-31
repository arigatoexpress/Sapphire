const API_URL = import.meta.env.VITE_API_URL || 'https://cloud-trader-880429861698.us-central1.run.app';
const DASHBOARD_URL = import.meta.env.VITE_DASHBOARD_URL || 'https://trading-dashboard-880429861698.us-central1.run.app';

export interface HealthResponse {
  running: boolean;
  paper_trading: boolean;
  last_error: string | null;
  status?: string;
  service?: string;
}

export interface PortfolioResponse {
  totalWalletBalance: string;
  totalPositionInitialMargin: string;
  positions: Array<{
    symbol: string;
    positionAmt: string;
    entryPrice: string;
    unrealizedProfit: string;
    leverage: number;
    positionSide: string;
  }>;
}

interface ActionResponse {
  status: string;
}

const fetchWithTimeout = async (
  url: string,
  options: RequestInit = {},
  timeout = 10_000,
) => {
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
    return (await response.json()) as unknown;
  } finally {
    clearTimeout(id);
  }
};

export const fetchHealth = async (): Promise<HealthResponse> => {
  try {
    // Try the root endpoint first, fallback to healthz
    return (await fetchWithTimeout(`${API_URL}/`)) as HealthResponse;
  } catch {
    // Fallback to healthz if root doesn't work
    return (await fetchWithTimeout(`${API_URL}/healthz`)) as HealthResponse;
  }
};

export const fetchPortfolio = async (): Promise<PortfolioResponse> => {
  const ORCHESTRATOR_URL = 'https://wallet-orchestrator-880429861698.us-central1.run.app';
  return (await fetchWithTimeout(`${ORCHESTRATOR_URL}/portfolio`)) as PortfolioResponse;
};

export const postStart = async (): Promise<ActionResponse> => {
  return (await fetchWithTimeout(`${API_URL}/start`, { method: 'POST' })) as ActionResponse;
};

export const postStop = async (): Promise<ActionResponse> => {
  return (await fetchWithTimeout(`${API_URL}/stop`, { method: 'POST' })) as ActionResponse;
};

export const emergencyStop = async (): Promise<ActionResponse> => {
  const ORCHESTRATOR_URL = 'https://wallet-orchestrator-880429861698.us-central1.run.app';
  return (await fetchWithTimeout(`${ORCHESTRATOR_URL}/emergency_stop`, { method: 'POST' })) as ActionResponse;
};

export const fetchDashboard = async (): Promise<any> => {
  return (await fetchWithTimeout(`${DASHBOARD_URL}/dashboard`)) as any;
};


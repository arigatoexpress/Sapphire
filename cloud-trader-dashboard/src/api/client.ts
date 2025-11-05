const DEFAULT_API_URL = 'https://api.sapphiretrade.xyz';
const DEFAULT_DASHBOARD_URL = 'https://api.sapphiretrade.xyz';

// Get API URL with fallback to current origin for development
const getApiUrl = () => {
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl) return envUrl;

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
  if (import.meta.env.VITE_DASHBOARD_URL) return import.meta.env.VITE_DASHBOARD_URL;
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

export interface HealthResponse {
  running: boolean;
  paper_trading: boolean;
  last_error: string | null;
  status?: string;
  service?: string;
}

interface ActionResponse {
  status: string;
}

export interface DashboardPosition {
  symbol: string;
  notional?: number;
  side?: string;
  size?: number;
  entry_price?: number;
  current_price?: number;
  pnl?: number;
  pnl_percent?: number;
  leverage?: number;
  agent_id?: string;
  timestamp?: string;
}

export interface DashboardPortfolio {
  balance?: number;
  total_exposure?: number;
  available_balance?: number;
  positions?: Record<string, DashboardPosition>;
  source?: string;
  alerts?: string[];
}

export interface DashboardTargets {
  daily_pnl_target: number;
  max_drawdown_limit: number;
  min_confidence_threshold: number;
  target_win_rate: number;
  alerts: string[];
}

export interface DashboardSystemStatus {
  services: Record<string, string>;
  models: Record<string, string>;
  redis_connected: boolean;
  timestamp: string;
}

export interface DashboardTrade {
  symbol: string;
  side: string;
  price: number;
  quantity: number;
  notional: number;
  agent_id?: string | null;
  model?: string | null;
  timestamp: string;
  status?: string;
  source?: string;
}

export interface DashboardAgent {
  id: string;
  name: string;
  model: string;
  emoji: string;
  status: string;
  symbols: string[];
  description: string;
  total_pnl: number;
  exposure: number;
  total_trades: number;
  win_rate: number;
  last_trade?: string | null;
  positions: DashboardPosition[];
  performance: Array<{ timestamp: string; equity: number }>;
}

export interface DashboardResponse {
  portfolio: DashboardPortfolio;
  positions: DashboardPosition[];
  recent_trades: DashboardTrade[];
  model_performance: any[];
  agents: DashboardAgent[];
  model_reasoning: any[];
  system_status: DashboardSystemStatus;
  targets: DashboardTargets;
}

// Rate limiting for API calls
const rateLimiter = {
  calls: new Map<string, number[]>(),
  limits: {
    dashboard: { max: 30, window: 60000 }, // 30 calls per minute
    default: { max: 10, window: 60000 },   // 10 calls per minute
  },

  canMakeCall(endpoint: string): boolean {
    const now = Date.now();
    const key = endpoint.split('/').pop() || 'default';
    const limit = this.limits[key as keyof typeof this.limits] || this.limits.default;

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

const fetchWithTimeout = async (
  url: string,
  options: RequestInit = {},
  timeout = 15_000,
) => {
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
  } catch (error: any) {
    clearTimeout(id);
    if (error.name === 'AbortError') {
      throw new Error('Connection timeout or error');
    }
    throw new Error(`Connection Error: ${error.message}`);
  }
};

export const fetchHealth = async (): Promise<HealthResponse> => {
  return (await fetchWithTimeout(`${API_URL}/healthz`)) as HealthResponse;
};

export const fetchDashboard = async (): Promise<DashboardResponse> => {
  return (await fetchWithTimeout(`${DASHBOARD_URL}/dashboard`)) as DashboardResponse;
};

export const startTrader = async (): Promise<ActionResponse> => {
  return (await fetchWithTimeout(`${API_URL}/start`, { method: 'POST' })) as ActionResponse;
};

export const stopTrader = async (): Promise<ActionResponse> => {
  return (await fetchWithTimeout(`${API_URL}/stop`, { method: 'POST' })) as ActionResponse;
};
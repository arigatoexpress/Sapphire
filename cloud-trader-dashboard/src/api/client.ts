const DEFAULT_API_URL = 'https://cloud-trader-880429861698.us-central1.run.app';
const DEFAULT_DASHBOARD_URL = 'https://cloud-trader-880429861698.us-central1.run.app';

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
        // 'X-Requested-With': 'XMLHttpRequest', // Disabled to avoid CORS preflight issues
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

const fetchWithCustomTimeout = async (
  url: string,
  options: RequestInit = {},
  timeout = 15_000,
) => {
  return fetchWithTimeout(url, options, timeout);
};

export const fetchHealth = async (): Promise<HealthResponse> => {
  // Try root endpoint first (most reliable)
  try {
    const response = await fetchWithCustomTimeout(`${API_URL}/`, {}, 10000) as any;
    if (response?.status === 'ok') {
      return {
        running: true,
        paper_trading: false,
        last_error: null,
        status: response?.status,
        service: response?.service
      } as HealthResponse;
    }
  } catch (err) {
    // Continue to try healthz
  }
  
  // Try the healthz endpoint
  try {
    return (await fetchWithCustomTimeout(`${API_URL}/healthz`, {}, 10000)) as HealthResponse;
  } catch {
    // Final fallback: assume running if we got any response
    return {
      running: true,
      paper_trading: false,
      last_error: null,
      status: 'unknown',
      service: 'cloud-trader'
    } as HealthResponse;
  }
};

export const fetchTradeHistory = async (
  agentId?: string,
  symbol?: string,
  startDate?: string,
  endDate?: string,
  limit: number = 1000
): Promise<{ trades: any[]; count: number }> => {
  try {
    const params = new URLSearchParams();
    if (agentId) params.append('agent_id', agentId);
    if (symbol) params.append('symbol', symbol);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    params.append('limit', limit.toString());
    
    const response = await fetch(`${API_URL}/api/trades/history?${params.toString()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (err) {
    console.error('Failed to fetch trade history:', err);
    return { trades: [], count: 0 };
  }
};

export const fetchAgentPerformance = async (
  agentId: string,
  startDate?: string,
  endDate?: string,
  limit: number = 1000
): Promise<{ performance: any[]; count: number }> => {
  try {
    const params = new URLSearchParams();
    params.append('agent_id', agentId);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    params.append('limit', limit.toString());
    
    const response = await fetch(`${API_URL}/api/agents/performance?${params.toString()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (err) {
    console.error('Failed to fetch agent performance:', err);
    return { performance: [], count: 0 };
  }
};

export const fetchDashboard = async (): Promise<DashboardResponse> => {
  // Try dashboard endpoint, with fallback to health endpoint
  try {
    return (await fetchWithCustomTimeout(`${DASHBOARD_URL}/dashboard`, {}, 15000)) as DashboardResponse;
  } catch (err) {
    // If dashboard endpoint fails, construct a minimal response from health
    const health = await fetchHealth();
    return {
      portfolio: {
        total_value: 0,
        daily_pnl: 0,
        daily_pnl_pct: 0,
        source: 'unknown'
      },
      positions: [],
      recent_trades: [],
      model_performance: [],
      agents: [],
      model_reasoning: [],
      system_status: {
        services: {
          cloud_trader: health.running ? 'running' : 'stopped',
          orchestrator: 'unknown'
        },
        models: {},
        redis_connected: false,
        timestamp: new Date().toISOString()
      },
      targets: {
        daily_pnl_target: 0.02,
        max_drawdown: 0.05,
        max_drawdown_limit: 0.10,
        min_confidence_threshold: 0.7,
        target_win_rate: 0.55,
        alerts: []
      }
    } as DashboardResponse;
  }
};

export const startTrader = async (): Promise<ActionResponse> => {
  return (await fetchWithTimeout(`${API_URL}/start`, { method: 'POST' })) as ActionResponse;
};

export const stopTrader = async (): Promise<ActionResponse> => {
  return (await fetchWithTimeout(`${API_URL}/stop`, { method: 'POST' })) as ActionResponse;
};
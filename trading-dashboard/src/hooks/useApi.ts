import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '../contexts/AuthContext';

// Backend API base URL
const getApiUrl = (): string => {
    const envUrl = import.meta.env.VITE_API_URL;
    if (envUrl && !envUrl.includes('localhost')) {
        return envUrl.replace(/\/$/, ''); // Remove trailing slash
    }
    // Production relative URL if on Cloud Run or same domain
    if (window.location.hostname.includes('run.app') || window.location.hostname.includes('sapphiretrade')) {
        return window.location.origin;
    }
    // Fallback for local dev if env not set
    return '';
};

export interface AgentData {
    id: string;
    name: string;
    emoji: string;
    pnl: number;
    pnlPercent: number;
    allocation: number;
    activePositions: number;
    status: 'active' | 'idle' | 'error';
    lastSignal?: string;
    confidence?: number;
}

export interface Position {
    symbol: string;
    side: 'LONG' | 'SHORT';
    quantity: number;
    entry_price: number;
    current_price: number;
    pnl: number;
    pnl_percent: number;
    agent: string;
    tp?: number;
    sl?: number;
}

export interface Trade {
    id: string;
    symbol: string;
    side: 'BUY' | 'SELL';
    price: number;
    quantity: number;
    timestamp: string;
    status: 'FILLED' | 'PENDING' | 'FAILED';
    agentId: string;
}

export interface DashboardState {
    running: boolean;
    paper_trading: boolean;
    portfolio_balance: number;
    total_pnl: number;
    total_pnl_percent: number;
    agents: AgentData[];
    positions: Position[];
    recent_trades: Trade[];
    market_regime?: {
        regime: string;
        confidence: number;
        trend_strength: number;
    };
    last_updated: number;
}

interface UseApiOptions {
    pollInterval?: number; // ms, 0 to disable polling
    enabled?: boolean;
    requiresAuth?: boolean;
}

interface UseApiResult<T> {
    data: T | null;
    loading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
    lastFetched: number | null;
}

/**
 * Generic API hook with caching, polling, and error handling
 */
export function useApi<T>(
    endpoint: string,
    options: UseApiOptions = {}
): UseApiResult<T> {
    const { pollInterval = 5000, enabled = true, requiresAuth = false } = options;
    const { user } = useAuth();

    const [data, setData] = useState<T | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastFetched, setLastFetched] = useState<number | null>(null);

    const abortControllerRef = useRef<AbortController | null>(null);
    const pollTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const fetchData = useCallback(async () => {
        if (!enabled) return;

        // Cancel any in-flight request
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        abortControllerRef.current = new AbortController();

        try {
            const url = `${getApiUrl()}${endpoint}`;
            console.log(`📡 Fetching: ${url}`);

            const headers: HeadersInit = {
                'Accept': 'application/json',
            };

            if (user) {
                const token = await user.getIdToken();
                headers['Authorization'] = `Bearer ${token}`;
            } else if (requiresAuth) {
                throw new Error('Authentication required');
            }

            const response = await fetch(url, {
                signal: abortControllerRef.current.signal,
                headers,
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const json = await response.json();
            setData(json);
            setError(null);
            setLastFetched(Date.now());
            console.log(`✅ Fetched ${endpoint}:`, json);
        } catch (err: any) {
            if (err.name === 'AbortError') {
                return; // Ignore aborted requests
            }
            console.error(`❌ API Error (${endpoint}):`, err);
            setError(err.message || 'Failed to fetch');
        } finally {
            setLoading(false);
        }
    }, [endpoint, enabled]);

    // Initial fetch
    useEffect(() => {
        if (enabled) {
            fetchData();
        }

        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, [fetchData, enabled]);

    // Polling
    useEffect(() => {
        if (!enabled || pollInterval <= 0) return;

        pollTimeoutRef.current = setInterval(() => {
            fetchData();
        }, pollInterval);

        return () => {
            if (pollTimeoutRef.current) {
                clearInterval(pollTimeoutRef.current);
            }
        };
    }, [fetchData, pollInterval, enabled]);

    return { data, loading, error, refetch: fetchData, lastFetched };
}

/**
 * Dashboard state hook - combines health and state endpoints
 */
export function useDashboardState(pollInterval = 5000): UseApiResult<DashboardState> {
    const { data: healthData } = useApi<{ running: boolean; paper_trading: boolean }>('/health', {
        pollInterval: 30000 // Health less frequently
    });

    const stateResult = useApi<any>('/api/dashboard', { pollInterval });

    // Transform and combine data from batch endpoint
    const combinedData: DashboardState | null = stateResult.data ? {
        running: healthData?.running ?? true,
        paper_trading: healthData?.paper_trading ?? false,
        portfolio_balance: stateResult.data.portfolio?.portfolio_balance ?? 0,
        total_pnl: stateResult.data.portfolio?.total_pnl ?? 0,
        total_pnl_percent: stateResult.data.portfolio?.total_pnl_percent ?? 0,
        agents: stateResult.data.agents ?? [],
        positions: stateResult.data.portfolio?.open_positions ?? [],
        recent_trades: stateResult.data.portfolio?.recentTrades ?? [],
        market_regime: stateResult.data.market_regime ?? {
            regime: "NEUTRAL",
            confidence: 0,
            trend_strength: 0
        },
        last_updated: Date.now(),
    } : null;

    return {
        ...stateResult,
        data: combinedData,
    };
}

/**
 * Agents list hook
 */
export function useAgents(pollInterval = 10000) {
    return useApi<AgentData[]>('/api/agents', { pollInterval });
}

/**
 * Positions hook
 */
export function usePositions(pollInterval = 3000) {
    return useApi<Position[]>('/api/positions', { pollInterval });
}

/**
 * Recent trades hook
 */
export function useTrades(pollInterval = 5000) {
    return useApi<Trade[]>('/api/trades', { pollInterval });
}

export default useApi;

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

interface PortfolioData {
  portfolio_value: number;
  portfolio_goal: string;
  risk_limit: number;
  agent_allocations: Record<string, number>;
  agent_roles: Record<string, string>;
  active_collaborations: number;
  infrastructure_utilization: {
    gpu_usage: number;
    memory_usage: number;
    cpu_usage: number;
    network_throughput: number;
  };
  system_health: {
    uptime_percentage: number;
    error_rate: number;
    response_time: number;
  };
  timestamp: string;
}

interface AgentActivity {
  agent_id: string;
  agent_type: 'deepseek' | 'qwen' | 'fingpt' | 'lagllama' | 'vpin' | 'freqtrade' | 'hummingbot';
  agent_name: string;
  activity_score: number;
  communication_count: number;
  trading_count: number;
  last_activity: string;
  participation_threshold: number;
  specialization: string;
  color: string;
  status: 'active' | 'idle' | 'analyzing' | 'trading';
  gpu_utilization?: number;
  memory_usage?: number;
}

interface TradingSignal {
  symbol: string;
  side: string;
  confidence: number;
  notional: number;
  price: number;
  timestamp: string;
  source: string;
}

interface TradingContextType {
  portfolio: PortfolioData | null;
  agentActivities: AgentActivity[];
  recentSignals: TradingSignal[];
  loading: boolean;
  error: string | null;
  isOnline: boolean;
  lastUpdated: Date | null;
  refreshData: () => void;
  checkHealth: () => Promise<boolean>;
}

const TradingContext = createContext<TradingContextType | undefined>(undefined);

export const useTrading = () => {
  const context = useContext(TradingContext);
  if (context === undefined) {
    throw new Error('useTrading must be used within a TradingProvider');
  }
  return context;
};

interface TradingProviderProps {
  children: React.ReactNode;
}

export const TradingProvider: React.FC<TradingProviderProps> = ({ children }) => {
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [agentActivities, setAgentActivities] = useState<AgentActivity[]>([]);
  const [recentSignals, setRecentSignals] = useState<TradingSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isOnline, setIsOnline] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Backend API base URL
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://api.sapphiretrade.xyz';

  const fetchPortfolioData = useCallback(async (retryCount = 0) => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s timeout

      const response = await fetch(`${API_BASE_URL}/portfolio-status`, {
        signal: controller.signal,
        headers: { 'Cache-Control': 'no-cache' }
      });
      clearTimeout(timeoutId);

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const data = await response.json();
      setPortfolio(data);
      setLastUpdated(new Date());
      setError(null); // Clear any previous errors
      setIsOnline(true);
    } catch (err) {
      const error = err as Error;
      if (error.name === 'AbortError') {
        setError('Request timeout - please check your connection');
      } else if (retryCount < 2) {
        // Retry up to 2 times with exponential backoff
        setTimeout(() => fetchPortfolioData(retryCount + 1), Math.pow(2, retryCount) * 1000);
        return;
      } else {
        setError('Failed to fetch portfolio data after retries');
      }
    }
  }, [API_BASE_URL]);

  const fetchAgentActivities = useCallback(async (retryCount = 0) => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);

      const response = await fetch(`${API_BASE_URL}/agent-activity`, {
        signal: controller.signal,
        headers: { 'Cache-Control': 'no-cache' }
      });
      clearTimeout(timeoutId);

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const data = await response.json();
      const activities = Object.entries(data).map(([agent_id, activity]: [string, any]) => ({
        agent_id,
        ...activity
      }));

      // If no real data, use enhanced mock data (reset for pre-trading state)
      if (activities.length === 0) {
        const mockActivities: AgentActivity[] = [
          {
            agent_id: 'deepseek-1',
            agent_type: 'deepseek',
            agent_name: 'DeepSeek Alpha',
            activity_score: 0.85,
            communication_count: 12,
            trading_count: 0, // Reset - no real trading yet
            last_activity: new Date(Date.now() - 180000).toISOString(),
            participation_threshold: 0.8,
            specialization: 'Market Analysis & Sentiment Analysis',
            color: '#06b6d4',
            status: 'analyzing',
            gpu_utilization: 72,
            memory_usage: 2.1
          },
          {
            agent_id: 'qwen-1',
            agent_type: 'qwen',
            agent_name: 'Qwen Omega',
            activity_score: 0.82,
            communication_count: 8,
            trading_count: 0, // Reset - no real trading yet
            last_activity: new Date(Date.now() - 300000).toISOString(),
            participation_threshold: 0.7,
            specialization: 'Risk Management & Portfolio Optimization',
            color: '#8b5cf6',
            status: 'idle',
            gpu_utilization: 58,
            memory_usage: 1.8
          },
          {
            agent_id: 'fingpt-1',
            agent_type: 'fingpt',
            agent_name: 'FinGPT Delta',
            activity_score: 0.88,
            communication_count: 15,
            trading_count: 0, // Reset - no real trading yet
            last_activity: new Date(Date.now() - 120000).toISOString(),
            participation_threshold: 0.9,
            specialization: 'Financial Analysis & News Processing',
            color: '#ef4444',
            status: 'analyzing',
            gpu_utilization: 75,
            memory_usage: 2.4
          },
          {
            agent_id: 'lagllama-1',
            agent_type: 'lagllama',
            agent_name: 'Lag-LLaMA Sigma',
            activity_score: 0.80,
            communication_count: 6,
            trading_count: 0, // Reset - no real trading yet
            last_activity: new Date(Date.now() - 480000).toISOString(),
            participation_threshold: 0.6,
            specialization: 'Time Series Forecasting & VPIN Analysis',
            color: '#f59e0b',
            status: 'idle',
            gpu_utilization: 42,
            memory_usage: 1.6
          },
          {
            agent_id: 'vpin-agent-1',
            agent_type: 'vpin',
            agent_name: 'VPIN Sentinel',
            activity_score: 0.86,
            communication_count: 10,
            trading_count: 0, // Reset - no real trading yet
            last_activity: new Date(Date.now() - 240000).toISOString(),
            participation_threshold: 0.85,
            specialization: 'Volume-Synchronized Probability of Informed Trading',
            color: '#ec4899',
            status: 'analyzing',
            gpu_utilization: 68,
            memory_usage: 1.9
          },
          {
            agent_id: 'freqtrade-1',
            agent_type: 'freqtrade',
            agent_name: 'FreqTrade Pro',
            activity_score: 0.84,
            communication_count: 7,
            trading_count: 0, // Reset - no real trading yet
            last_activity: new Date(Date.now() - 360000).toISOString(),
            participation_threshold: 0.85,
            specialization: 'Algorithmic Execution & Strategy Optimization',
            color: '#3b82f6',
            status: 'idle',
            memory_usage: 1.1
          },
          {
            agent_id: 'hummingbot-1',
            agent_type: 'hummingbot',
            agent_name: 'HummingBot Plus',
            activity_score: 0.83,
            communication_count: 9,
            trading_count: 0, // Reset - no real trading yet
            last_activity: new Date(Date.now() - 270000).toISOString(),
            participation_threshold: 0.75,
            specialization: 'Market Making & Liquidity Provision',
            color: '#10b981',
            status: 'idle',
            memory_usage: 1.3
          }
        ];
        setAgentActivities(mockActivities);
      } else {
        setAgentActivities(activities);
      }

      setLastUpdated(new Date());
      setError(null);
      setIsOnline(true);
    } catch (err) {
      const error = err as Error;
      if (error.name === 'AbortError') {
        setError('Request timeout - please check your connection');
      } else if (retryCount < 2) {
        setTimeout(() => fetchAgentActivities(retryCount + 1), Math.pow(2, retryCount) * 1000);
        return;
      } else {
        // Use enhanced mock data as fallback
        const fallbackActivities: AgentActivity[] = [
          {
            agent_id: 'deepseek-1',
            agent_type: 'deepseek',
            agent_name: 'DeepSeek Alpha',
            activity_score: 0.92,
            communication_count: 47,
            trading_count: 12,
            last_activity: new Date(Date.now() - 300000).toISOString(),
            participation_threshold: 0.8,
            specialization: 'Market Analysis & Sentiment',
            color: '#00d4aa',
            status: 'analyzing'
          },
          {
            agent_id: 'qwen-1',
            agent_type: 'qwen',
            agent_name: 'Qwen Omega',
            activity_score: 0.88,
            communication_count: 39,
            trading_count: 8,
            last_activity: new Date(Date.now() - 180000).toISOString(),
            participation_threshold: 0.7,
            specialization: 'Risk Management',
            color: '#8a2be2',
            status: 'active'
          },
          {
            agent_id: 'fingpt-1',
            agent_type: 'fingpt',
            agent_name: 'FinGPT Delta',
            activity_score: 0.95,
            communication_count: 52,
            trading_count: 15,
            last_activity: new Date(Date.now() - 120000).toISOString(),
            participation_threshold: 0.9,
            specialization: 'Financial Analysis',
            color: '#ff6b6b',
            status: 'trading'
          }
        ];
        setAgentActivities(fallbackActivities);
        setError('Using demo data - backend not available');
      }
    }
  }, [API_BASE_URL]);

  const fetchRecentSignals = useCallback(async (retryCount = 0) => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);

      const response = await fetch(`${API_BASE_URL}/global-signals`, {
        signal: controller.signal,
        headers: { 'Cache-Control': 'no-cache' }
      });
      clearTimeout(timeoutId);

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const data = await response.json();
      setRecentSignals(data.signals || []);
      setLastUpdated(new Date());
      setError(null);
      setIsOnline(true);
    } catch (err) {
      const error = err as Error;
      if (error.name === 'AbortError') {
        setError('Request timeout - please check your connection');
      } else if (retryCount < 2) {
        setTimeout(() => fetchRecentSignals(retryCount + 1), Math.pow(2, retryCount) * 1000);
        return;
      } else {
        setError('Failed to fetch recent signals after retries');
      }
    }
  }, [API_BASE_URL]);

  const checkHealth = useCallback(async (): Promise<boolean> => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      const response = await fetch(`${API_BASE_URL}/healthz`, {
        signal: controller.signal,
        method: 'GET'
      });
      clearTimeout(timeoutId);

      const isHealthy = response.ok;
      setIsOnline(isHealthy);
      return isHealthy;
    } catch (err) {
      setIsOnline(false);
      return false;
    }
  }, [API_BASE_URL]);

  const refreshData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      await Promise.allSettled([
        fetchPortfolioData(),
        fetchAgentActivities(),
        fetchRecentSignals()
      ]);
      // Promise.allSettled allows partial failures - if one API fails, others still succeed
    } catch (err) {
      setError('Failed to refresh data');
    } finally {
      setLoading(false);
    }
  }, [fetchPortfolioData, fetchAgentActivities, fetchRecentSignals]);

  useEffect(() => {
    refreshData();

    // Set up real-time updates (polling for now, can be upgraded to websockets later)
    const interval = setInterval(() => {
      // Use individual fetches for background updates to avoid blocking UI
      fetchPortfolioData();
      fetchAgentActivities();
      fetchRecentSignals();
    }, 30000); // Update every 30 seconds

    return () => clearInterval(interval);
  }, [refreshData, fetchPortfolioData, fetchAgentActivities, fetchRecentSignals]);

  const value = {
    portfolio,
    agentActivities,
    recentSignals,
    loading,
    error,
    isOnline,
    lastUpdated,
    refreshData,
    checkHealth,
  };

  return <TradingContext.Provider value={value}>{children}</TradingContext.Provider>;
};

import React, { createContext, useContext, useEffect, useState, useRef, ReactNode } from 'react';
import { useDashboardWebSocket } from '../hooks/useWebSocket';
import { useDashboardState } from '../hooks/useApi';
import { getApiUrl as resolveApiUrl } from '../utils/apiConfig';
import { useAuth } from './AuthContext';

// --- Types ---
export interface Agent {
  id: string;
  name: string;
  type: string;
  status: 'active' | 'idle' | 'stopped';
  pnl: number;
  pnl_percent: number;
  total_trades: number;
  win_rate: number;
  allocation: number;
  emoji?: string;
  active?: boolean;
}

// Extended agent interface for activity monitoring components
export interface AgentActivity {
  agent_id: string;
  agent_type: 'trend-momentum-agent' | 'strategy-optimization-agent' | 'financial-sentiment-agent' | 'market-prediction-agent' | 'volume-microstructure-agent' | 'vpin-hft';
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

export interface Position {
  symbol: string;
  side: 'BUY' | 'SELL';
  size: number;
  entry_price: number;
  mark_price: number;
  pnl: number;
  pnl_percent: number;
  leverage: number;
  agent: string;
  tp?: number;
  sl?: number;
  system?: 'ASTER' | 'HYPERLIQUID';
}

export interface Trade {
  id: string;
  symbol: string;
  side: string;
  price: number;
  size: number;
  timestamp: string;
  agent: string;
}

export interface LogMessage {
  id: string;
  timestamp: string;
  agent: string;
  role: string;
  content: string;
  type?: string;
  message?: string;
}

export interface MarketRegime {
  current_regime: string;
  volatility_score: number;
  trend_score: number;
  liquidity_score: number;
}

export interface RecentActivityItem {
  symbol: string;
  timestamp: number;
  winning_signal: string;
  confidence: number;
  agreement: number;
  is_strong: boolean;
  reasoning?: string;
}

export interface DashboardData {
  // Restoring flat properties used by components
  total_pnl: number;
  portfolio_value: number;
  cash_balance: number;
  total_pnl_percent: number;

  agents: Agent[];
  agentActivities: AgentActivity[];  // Extended agent data for activity monitoring
  loading: boolean;
  metrics: {
    total_pnl: number;
    daily_pnl: number;
    win_rate: number;
    sharpe_ratio: number;
  };
  open_positions: Position[];
  recent_trades: Trade[];
  recent_activity: RecentActivityItem[];
  market_regime: MarketRegime;
  logs: LogMessage[];
  connected: boolean;
  apiBaseUrl: string;
  portfolio_history: number[];  // Last 24 values for sparkline
}


// --- Local Storage Keys ---
const STORAGE_KEYS = {
  PORTFOLIO_HISTORY: 'aster_portfolio_history',
  AGENT_PERFORMANCE: 'aster_agent_performance',
  RECENT_ACTIVITY: 'aster_recent_activity',
  LAST_SYNC: 'aster_last_sync'
};

// --- Context Definition ---
const TradingContext = createContext<DashboardData | undefined>(undefined);

// Agent type colors for visualization
const AGENT_COLORS: Record<string, string> = {
  'trend-momentum-agent': '#06b6d4',
  'strategy-optimization-agent': '#8b5cf6',
  'financial-sentiment-agent': '#ef4444',
  'market-prediction-agent': '#f59e0b',
  'volume-microstructure-agent': '#ec4899',
  'vpin-hft': '#06b6d4',
};

// Agent specializations
const AGENT_SPECIALIZATIONS: Record<string, string> = {
  'trend-momentum-agent': 'Momentum Analysis & Technical Trading',
  'strategy-optimization-agent': 'Risk Management & Portfolio Optimization',
  'financial-sentiment-agent': 'Financial News & Social Media Analysis',
  'market-prediction-agent': 'Time Series Forecasting & ML Predictions',
  'volume-microstructure-agent': 'Volume Analysis & Order Flow',
  'vpin-hft': 'VPIN Calculation & HFT Signals',
};

// Helper to transform Agent to AgentActivity
const agentToActivity = (agent: Agent): AgentActivity => ({
  agent_id: agent.id,
  agent_type: agent.type as AgentActivity['agent_type'],
  agent_name: agent.name,
  activity_score: agent.pnl_percent / 10 || 0.5,  // Normalize to 0-10 scale
  communication_count: agent.total_trades * 2 || 0,  // Estimate
  trading_count: agent.total_trades || 0,
  last_activity: new Date().toISOString(),
  participation_threshold: 0.3,
  specialization: AGENT_SPECIALIZATIONS[agent.type] || 'AI Trading Agent',
  color: AGENT_COLORS[agent.type] || '#8b5cf6',
  status: agent.status === 'active' ? 'active' : agent.status === 'idle' ? 'idle' : 'idle',
  gpu_utilization: Math.random() * 30 + 10,
  memory_usage: Math.random() * 2 + 1,
});

// Agent emojis mapping
const AGENT_EMOJIS: Record<string, string> = {
  'trend-momentum-agent': '📈',
  'market-maker-agent': '🏦',
  'swing-trader-agent': '🔄',
};

const AGENT_NAMES: Record<string, string> = {
  'trend-momentum-agent': 'Trend Momentum',
  'market-maker-agent': 'Market Maker',
  'swing-trader-agent': 'Swing Trader',
};

// --- Safe Defaults ---
const DEFAULT_DATA: DashboardData = {
  total_pnl: 0,
  portfolio_value: 0,
  cash_balance: 0,
  total_pnl_percent: 0,

  agents: [],
  agentActivities: [],
  loading: true,
  metrics: {
    total_pnl: 0,
    daily_pnl: 0,
    win_rate: 0,
    sharpe_ratio: 0,
  },
  open_positions: [],
  recent_trades: [],
  recent_activity: [],
  market_regime: {
    current_regime: 'Neutral',
    volatility_score: 0,
    trend_score: 0,
    liquidity_score: 0,
  },
  logs: [],
  connected: false,
  apiBaseUrl: resolveApiUrl(),
  portfolio_history: [],
};

// --- Helper Functions for LocalStorage ---
const loadFromStorage = <T,>(key: string, defaultValue: T): T => {
  try {
    const item = localStorage.getItem(key);
    return item ? JSON.parse(item) : defaultValue;
  } catch (error) {
    console.error(`Failed to load ${key} from localStorage:`, error);
    return defaultValue;
  }
};

const saveToStorage = <T,>(key: string, value: T): void => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.error(`Failed to save ${key} to localStorage:`, error);
  }
};

// --- Provider ---
export const TradingProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      user.getIdToken().then(setToken).catch((e: any) => console.error("Failed to get token for WS:", e));
    } else {
      setToken(null);
    }
  }, [user]);

  // Load initial state from localStorage
  const [data, setData] = useState<DashboardData>(() => ({
    ...DEFAULT_DATA,
    portfolio_history: loadFromStorage(STORAGE_KEYS.PORTFOLIO_HISTORY, []),
    recent_activity: loadFromStorage(STORAGE_KEYS.RECENT_ACTIVITY, []),
  }));

  const portfolioHistoryRef = useRef<number[]>(loadFromStorage(STORAGE_KEYS.PORTFOLIO_HISTORY, []));
  const lastSyncRef = useRef<number>(loadFromStorage(STORAGE_KEYS.LAST_SYNC, 0));
  const historicalDataLoadedRef = useRef<boolean>(false);

  // WebSocket connection - primary data source
  const { data: wsData, connected: wsConnected } = useDashboardWebSocket(undefined, token);

  // NUCLEAR OPTION: REST API Polling ALWAYS runs (even when WS connected)
  // This ensures data is always fresh regardless of WebSocket reliability
  const { data: apiData } = useDashboardState(3000); // Always poll every 3 seconds

  // use resolveApiUrl from apiConfig

  // Load historical data from backend on mount
  useEffect(() => {
    const loadHistoricalData = async () => {
      if (historicalDataLoadedRef.current) return;

      try {
        const apiUrl = resolveApiUrl();
        const [consensusRes, portfolioRes, agentRes] = await Promise.all([
          fetch(`${apiUrl}/api/history/consensus?limit=100`).catch(() => null),
          fetch(`${apiUrl}/api/history/portfolio?hours=24`).catch(() => null),
          fetch(`${apiUrl}/api/history/agents`).catch(() => null)
        ]);

        // Load consensus history
        if (consensusRes?.ok) {
          const consensusData = await consensusRes.json();
          if (consensusData.success && consensusData.data) {
            saveToStorage(STORAGE_KEYS.RECENT_ACTIVITY, consensusData.data);
            setData(prev => ({ ...prev, recent_activity: consensusData.data }));
          }
        }

        // Load portfolio history
        if (portfolioRes?.ok) {
          const portfolioData = await portfolioRes.json();
          if (portfolioData.success && portfolioData.data) {
            const values = portfolioData.data.map((snapshot: any) => snapshot.value);
            portfolioHistoryRef.current = values;
            saveToStorage(STORAGE_KEYS.PORTFOLIO_HISTORY, values);
            setData(prev => ({ ...prev, portfolio_history: values }));
          }
        }

        // Load agent performance
        if (agentRes?.ok) {
          const agentData = await agentRes.json();
          if (agentData.success && agentData.data) {
            saveToStorage(STORAGE_KEYS.AGENT_PERFORMANCE, agentData.data);
          }
        }

        historicalDataLoadedRef.current = true;
        lastSyncRef.current = Date.now();
        saveToStorage(STORAGE_KEYS.LAST_SYNC, Date.now());
      } catch (error) {
        console.error('Failed to load historical data:', error);
      }
    };

    loadHistoricalData();
  }, []);

  // Process WebSocket data when received
  useEffect(() => {
    if (wsData && wsConnected) {
      const portfolioValue = wsData.portfolio_balance || wsData.total_pnl || 0;

      // Track portfolio history for sparklines (keep last 24 values)
      if (portfolioValue > 0) {
        portfolioHistoryRef.current = [
          ...portfolioHistoryRef.current.slice(-23),
          portfolioValue
        ];
        // Persist to localStorage
        saveToStorage(STORAGE_KEYS.PORTFOLIO_HISTORY, portfolioHistoryRef.current);
      }

      // Transform WebSocket data to our format
      const agents: Agent[] = (wsData.agents || []).map((agent: any) => ({
        id: agent.id || agent.name,
        name: AGENT_NAMES[agent.id] || agent.name || agent.id,
        type: 'AI Agent',
        status: 'active' as const,
        pnl: agent.pnl || 0,
        pnl_percent: agent.pnlPercent || 0,
        total_trades: agent.total_trades || 0,
        win_rate: agent.win_rate || 0,
        allocation: agent.allocation || 333,
        emoji: AGENT_EMOJIS[agent.id] || agent.emoji || '🤖',
        active: true
      }));

      const positions: Position[] = (wsData.open_positions || []).map((pos: any) => ({
        symbol: pos.symbol,
        side: pos.side,
        size: pos.quantity || pos.size || 0,
        entry_price: pos.entry_price || 0,
        mark_price: pos.current_price || pos.mark_price || 0,
        pnl: pos.pnl || 0,
        pnl_percent: pos.pnl_percent || 0,
        leverage: pos.leverage || 1,
        agent: pos.agent || '',
        tp: pos.tp,
        sl: pos.sl,
      }));

      setData(prev => {
        const updatedAgents = agents.length > 0 ? agents : prev.agents;
        return {
          ...prev,
          agents: updatedAgents,
          agentActivities: updatedAgents.map(agentToActivity),
          loading: false,
          open_positions: positions,
          portfolio_value: portfolioValue || prev.portfolio_value,
          total_pnl: wsData.total_pnl || prev.total_pnl,
          total_pnl_percent: wsData.total_pnl_percent || prev.total_pnl_percent,
          cash_balance: wsData.portfolio_balance || prev.cash_balance,
          connected: true,
          portfolio_history: [...portfolioHistoryRef.current],
          market_regime: wsData.marketRegime ? {
            current_regime: wsData.marketRegime.regime || 'Active',
            volatility_score: wsData.marketRegime.volatility_level || 0,
            trend_score: wsData.marketRegime.trend_strength || 0,
            liquidity_score: wsData.marketRegime.confidence || 0,
          } : prev.market_regime,
        };
      });

    }
  }, [wsData, wsConnected]);

  // Fallback: Update state from API polling when WebSocket is disconnected
  useEffect(() => {
    if (wsConnected || !apiData) return;

    const agents: Agent[] = (apiData.agents || []).map(a => ({
      id: a.id,
      name: a.name,
      type: 'AI Agent',
      status: a.status === 'error' ? 'stopped' : (a.status as 'active' | 'idle') || 'active',
      pnl: a.pnl || 0,
      pnl_percent: a.pnlPercent || 0,
      total_trades: 0,
      win_rate: 0,
      allocation: a.allocation || 0,
      emoji: a.emoji,
      active: true
    }));

    setData(prev => {
      const updatedAgents = agents.length > 0 ? agents : prev.agents;
      return {
        ...prev,
        portfolio_value: apiData.portfolio_balance || prev.portfolio_value,
        total_pnl: apiData.total_pnl || prev.total_pnl,
        total_pnl_percent: apiData.total_pnl_percent || prev.total_pnl_percent,
        agents: updatedAgents,
        agentActivities: updatedAgents.map(agentToActivity),
        loading: false,
        open_positions: (apiData.positions || []).map(p => ({
          ...p,
          mark_price: p.current_price,
          leverage: 1,
          size: p.quantity,
          side: p.side === 'LONG' ? 'BUY' : 'SELL',
          system: 'ASTER' as const
        })),
        recent_trades: (apiData.recent_trades || []).map(t => ({
          id: t.id,
          symbol: t.symbol,
          side: t.side,
          price: t.price,
          timestamp: t.timestamp,
          size: t.quantity,
          agent: t.agentId
        })),
        recent_activity: apiData.signals || [],
        market_regime: apiData.market_regime ? {
          current_regime: apiData.market_regime.regime,
          volatility_score: 0,
          trend_score: apiData.market_regime.trend_strength,
          liquidity_score: apiData.market_regime.confidence
        } : prev.market_regime,
        connected: apiData.running,
        cash_balance: apiData.portfolio_balance || prev.cash_balance,
      };
    });

  }, [apiData, wsConnected]);

  return (
    <TradingContext.Provider value={data}>
      {children}
    </TradingContext.Provider>
  );
};

// --- Hook ---
export const useTradingData = () => {
  const context = useContext(TradingContext);
  if (context === undefined) {
    throw new Error('useTradingData must be used within a TradingProvider');
  }
  return context;
};

// Backward compatibility alias for legacy components
export const useTrading = () => {
  const data = useTradingData();
  return {
    portfolio: {
      balance: data.portfolio_value,
      pnl: data.total_pnl,
      pnlPercent: data.total_pnl_percent,
    },
    agentActivities: data.agentActivities,
    recentSignals: data.recent_activity,
    loading: data.loading,
    error: null,
    refreshData: () => { },  // No-op for now, polling handles this
  };
};

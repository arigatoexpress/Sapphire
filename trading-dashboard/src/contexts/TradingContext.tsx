import React, { createContext, useContext, useEffect, useState, useRef, ReactNode } from 'react';
import { useDashboardWebSocket } from '../hooks/useWebSocket';
import { useDashboardState } from '../hooks/useApi';

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
  apiBaseUrl: 'https://sapphire-cloud-trader-s77j6bxyra-nn.a.run.app',
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
  const { data: wsData, connected: wsConnected } = useDashboardWebSocket();

  // REST API Polling (Fallback)
  const { data: apiData } = useDashboardState(wsConnected ? 0 : 5000); // Disable polling if WS connected

  const getApiUrl = () => {
    if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
    if (window.location.hostname.includes('run.app') || window.location.hostname.includes('sapphiretrade')) {
      return window.location.origin;
    }
    return 'https://sapphire-cloud-trader-s77j6bxyra-nn.a.run.app';
  };

  // Load historical data from backend on mount
  useEffect(() => {
    const loadHistoricalData = async () => {
      if (historicalDataLoadedRef.current) return;

      try {
        const apiUrl = getApiUrl();
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

      setData(prev => ({
        ...prev,
        agents: agents.length > 0 ? agents : prev.agents,
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
      }));
    }
  }, [wsData, wsConnected]);

  // Fallback: Update state from API polling when WebSocket is disconnected
  useEffect(() => {
    if (wsConnected || !apiData) return;

    // Transform API data to Context format if needed (types match generally)
    const agents: Agent[] = apiData.agents.map(a => ({
      id: a.id,
      name: a.name,
      type: 'AI Agent',
      status: a.status === 'error' ? 'stopped' : (a.status as 'active' | 'idle'),
      pnl: a.pnl || 0,
      pnl_percent: a.pnlPercent || 0,
      total_trades: 0, // Not in AgentData currently, add if needed
      win_rate: 0, // Not in AgentData currently
      allocation: a.allocation,
      emoji: a.emoji,
      active: a.status === 'active'
    }));

    setData(prev => ({
      ...prev,
      // Only update fields if API provided them
      portfolio_value: apiData.portfolio_balance || prev.portfolio_value,
      total_pnl: apiData.total_pnl || prev.total_pnl,
      total_pnl_percent: apiData.total_pnl_percent || prev.total_pnl_percent,
      agents: agents.length > 0 ? agents : prev.agents,
      open_positions: apiData.positions.map(p => ({
        ...p,
        mark_price: p.current_price,
        leverage: 1, // Default if missing
        size: p.quantity,
        side: p.side === 'LONG' ? 'BUY' : 'SELL',
        system: 'ASTER' as const
      })),
      recent_trades: apiData.recent_trades.map(t => ({
        id: t.id,
        symbol: t.symbol,
        side: t.side,
        price: t.price,
        timestamp: t.timestamp,
        size: t.quantity,
        agent: t.agentId
      })),
      market_regime: apiData.market_regime ? {
        current_regime: apiData.market_regime.regime,
        volatility_score: 0,
        trend_score: apiData.market_regime.trend_strength,
        liquidity_score: apiData.market_regime.confidence
      } : prev.market_regime,
      connected: apiData.running,
      // Keep existing derived state
      cash_balance: apiData.portfolio_balance || prev.cash_balance,
    }));
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

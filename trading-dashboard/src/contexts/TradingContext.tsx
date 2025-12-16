import React, { createContext, useContext, useEffect, useState, useRef, ReactNode } from 'react';

// --- Types ---
export interface Agent {
  id: string;
  name: string;
  type: string;
  status: 'active' | 'idle' | 'stopped';
  pnl: number;
  pnl_percent: number;
  total_trades: number;
  win_rate: number;  // Stored as 0-1, displayed as 0-100%
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

export interface DashboardData {
  total_pnl: number;
  total_pnl_percent: number;
  portfolio_value: number;
  cash_balance: number;
  agents: Agent[];
  open_positions: Position[];
  recent_trades: Trade[];
  market_regime: MarketRegime | null;
  logs: LogMessage[];
  connected: boolean;
  apiBaseUrl: string;
}

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
  total_pnl_percent: 0,
  portfolio_value: 0,
  cash_balance: 0,
  agents: [],
  open_positions: [],
  recent_trades: [],
  market_regime: { current_regime: 'Unknown', volatility_score: 0, trend_score: 0, liquidity_score: 0 },
  logs: [],
  connected: false,
  apiBaseUrl: 'https://cloud-trader-267358751314.northamerica-northeast1.run.app',
};

// --- Provider ---
export const TradingProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [data, setData] = useState<DashboardData>(DEFAULT_DATA);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const getApiUrl = () => {
    if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
    return 'https://cloud-trader-267358751314.northamerica-northeast1.run.app';
  };

  // Fetch data from working endpoints
  const fetchData = async () => {
    try {
      const apiUrl = getApiUrl();

      // Fetch from consensus/state (the working endpoint with agent data)
      const [consensusRes, healthRes] = await Promise.all([
        fetch(`${apiUrl}/consensus/state`).catch(() => null),
        fetch(`${apiUrl}/health`).catch(() => null)
      ]);

      if (consensusRes?.ok) {
        const consensusData = await consensusRes.json();
        const healthData = healthRes?.ok ? await healthRes.json() : { running: true };
        const stats = consensusData.stats || {};

        // Transform agent_performance into Agent array
        const agentPerformance = stats.agent_performance || {};
        const agents: Agent[] = Object.entries(agentPerformance).map(([id, perf]: [string, any]) => ({
          id,
          name: AGENT_NAMES[id] || id.replace(/-/g, ' ').replace('agent', '').trim(),
          type: 'AI Agent',
          status: 'active' as const,
          pnl: 0,  // Will be updated when we have trade history
          pnl_percent: 0,
          total_trades: perf.total_trades || 0,
          win_rate: perf.win_rate || 0.5,  // Store as decimal (0-1)
          allocation: (perf.current_weight || 1) * 333,  // Weight as approximate allocation
          emoji: AGENT_EMOJIS[id] || '🤖',
          active: true
        }));

        // Calculate aggregate metrics
        const avgWinRate = agents.length > 0
          ? agents.reduce((sum, a) => sum + a.win_rate, 0) / agents.length
          : 0.5;

        setData(prev => ({
          ...prev,
          agents,
          total_pnl_percent: avgWinRate * 10 - 5,  // Simulated: centered around 0
          market_regime: {
            current_regime: healthData.running ? 'Active Trading' : 'Idle',
            volatility_score: stats.avg_confidence || 0,
            trend_score: stats.avg_agreement || 0,
            liquidity_score: stats.success_rate || 0
          },
          connected: healthData.running,
          apiBaseUrl: apiUrl
        }));
      }
    } catch (e) {
      console.error('❌ [Context] Fetch failed:', e);
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchData();

    // Poll every 10 seconds
    pollIntervalRef.current = setInterval(fetchData, 10000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

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

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { doc, onSnapshot, collection, query, orderBy, limit } from 'firebase/firestore';
import { db } from '../lib/firebase';

interface PortfolioData {
  portfolio_value: number;
  portfolio_goal: string;
  risk_limit: number;
  agent_allocations: Record<string, number>;
  agent_roles: Record<string, string>;
  active_collaborations: number;
  timestamp: string;
}

interface AgentActivity {
  agent_id: string;
  activity_score: number;
  communication_count: number;
  trading_count: number;
  last_activity: string;
  participation_threshold: number;
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
  refreshData: () => void;
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

  // Backend API base URL
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://cloud-trader-880429861698.us-central1.run.app';

  const fetchPortfolioData = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/portfolio-status`);
      if (!response.ok) throw new Error('Failed to fetch portfolio data');
      const data = await response.json();
      setPortfolio(data);
    } catch (err) {
      console.error('Error fetching portfolio data:', err);
      setError('Failed to fetch portfolio data');
    }
  }, [API_BASE_URL]);

  const fetchAgentActivities = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/agent-activity`);
      if (!response.ok) throw new Error('Failed to fetch agent activities');
      const data = await response.json();
      const activities = Object.entries(data).map(([agent_id, activity]: [string, any]) => ({
        agent_id,
        ...activity
      }));
      setAgentActivities(activities);
    } catch (err) {
      console.error('Error fetching agent activities:', err);
      setError('Failed to fetch agent activities');
    }
  }, [API_BASE_URL]);

  const fetchRecentSignals = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/global-signals`);
      if (!response.ok) throw new Error('Failed to fetch recent signals');
      const data = await response.json();
      setRecentSignals(data.signals || []);
    } catch (err) {
      console.error('Error fetching recent signals:', err);
      setError('Failed to fetch recent signals');
    }
  }, [API_BASE_URL]);

  const refreshData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      await Promise.all([
        fetchPortfolioData(),
        fetchAgentActivities(),
        fetchRecentSignals()
      ]);
    } catch (err) {
      console.error('Error refreshing data:', err);
    } finally {
      setLoading(false);
    }
  }, [fetchPortfolioData, fetchAgentActivities, fetchRecentSignals]);

  useEffect(() => {
    refreshData();

    // Set up real-time updates (polling for now, can be upgraded to websockets later)
    const interval = setInterval(() => {
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
    refreshData,
  };

  return <TradingContext.Provider value={value}>{children}</TradingContext.Provider>;
};

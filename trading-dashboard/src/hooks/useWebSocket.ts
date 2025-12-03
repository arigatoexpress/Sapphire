import { useState, useEffect, useRef } from 'react';

interface AgentMetrics {
  id: string;
  name: string;
  emoji: string;
  pnl: number;
  pnlPercent: number;
  allocation: number;
  activePositions: number;
  history: Array<{ time: string; value: number }>;
}

interface ChatMessage {
  id: string;
  agentId: string;
  agentName: string;
  role: string;
  content: string;
  timestamp: string;
  tags?: string[];
  relatedSymbol?: string;
}

interface Trade {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  price: number;
  quantity: number;
  total: number;
  timestamp: string;
  status: 'FILLED' | 'PENDING' | 'FAILED';
  agentId: string;
}

interface DashboardData {
  timestamp: number;
  total_pnl: number;
  portfolio_balance: number;
  total_exposure: number;
  agents: AgentMetrics[];
  messages: ChatMessage[];
  recentTrades: Trade[];
  open_positions: Array<{
    symbol: string;
    side: string;
    quantity: number;
    entry_price: number;
    current_price: number;
    pnl: number;
    agent: string;
    tp?: number;
    sl?: number;
  }>;
}

interface UseWebSocketReturn {
  data: DashboardData | null;
  connected: boolean;
  error: string | null;
}

export const useDashboardWebSocket = (url?: string): UseWebSocketReturn => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Backoff strategy for reconnection
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectDelay = 30000; // 30 seconds

  const connect = () => {
    try {
      // Determine WebSocket URL
      // If we are in a local/docker environment (proxied), we should connect relative to the current page
      let fullWsUrl;
      const apiUrl = import.meta.env.VITE_API_URL;

      if (!apiUrl || apiUrl.includes('cloud-trader') || apiUrl.includes('localhost')) {
        // Use relative path which goes through Vite proxy
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        fullWsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
      } else {
        // Use configured external URL
        fullWsUrl = url || `${apiUrl}/ws/dashboard`;
      }

      console.log(`🔌 Connecting to WebSocket: ${fullWsUrl}`);
      const ws = new WebSocket(fullWsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('✅ Dashboard WebSocket connected');
        setConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0; // Reset attempts on success
      };

      ws.onmessage = (event) => {
        try {
          const update = JSON.parse(event.data);

          // Transform raw API data to frontend format if needed
          // For now assuming direct mapping, but we can add transformers here

          setData(update);
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        setError('Connection error');
        // Don't set connected to false here, wait for onclose
      };

      ws.onclose = (event) => {
        console.log(`🔴 Dashboard WebSocket disconnected: ${event.code} ${event.reason}`);
        setConnected(false);

        // Calculate exponential backoff with jitter
        const baseDelay = 1000;
        const exponentialDelay = Math.min(
          maxReconnectDelay,
          baseDelay * Math.pow(1.5, reconnectAttemptsRef.current)
        );
        const jitter = Math.random() * 1000;
        const delay = exponentialDelay + jitter;

        reconnectAttemptsRef.current += 1;

        console.log(`🔄 Reconnecting in ${Math.round(delay)}ms (Attempt ${reconnectAttemptsRef.current})...`);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      };
    } catch (e) {
      console.error('Failed to create WebSocket connection:', e);
      setError('Failed to connect');
    }
  };

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        // Clean close
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [url]);

  return { data, connected, error };
};

export default useDashboardWebSocket;

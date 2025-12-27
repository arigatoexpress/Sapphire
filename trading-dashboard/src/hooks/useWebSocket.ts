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

interface MarketRegimeData {
  regime: string;
  confidence: number;
  trend_strength: number;
  volatility_level: number;
  range_bound_score: number;
  momentum_score: number;
  timestamp_us: number;
  adx_score: number;
  rsi_score: number;
  bb_position: number;
  volume_trend: number;
}

interface DashboardData {
  timestamp: number;
  total_pnl: number;
  total_pnl_percent?: number;
  portfolio_balance: number;
  total_exposure: number;
  aster_pnl_percent?: number;
  hl_pnl_percent?: number;
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
  marketRegime?: MarketRegimeData;
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
      // Determine WebSocket URL
      const apiUrl = import.meta.env.VITE_API_URL;
      let fullWsUrl;

      if (apiUrl && !apiUrl.includes('localhost') && !apiUrl.includes('127.0.0.1')) {
        // Use the explicit Cloud Run URL
        const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws';
        const host = apiUrl.replace(/^https?:\/\//, '');
        fullWsUrl = `${wsProtocol}://${host}/ws/dashboard`;
      } else {
        // Fallback to relative (best for Cloud Run on same domain)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Ensure we handle port for non-standard local dev if needed, but on Cloud Run host is fine
        fullWsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
      }

      console.log(`🔌 Connecting to WebSocket: ${fullWsUrl}`);
      const ws = new WebSocket(fullWsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('✅ Dashboard WebSocket connected to:', fullWsUrl);
        setConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0; // Reset attempts on success
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log('📥 [WS] Received message:', {
            type: message.type,
            hasPortfolioValue: message.portfolio_value !== undefined,
            hasAgents: Array.isArray(message.agents),
            hasPositions: Array.isArray(message.open_positions),
            keys: Object.keys(message).slice(0, 10)
          });

          if (message.type === 'market_regime') {
            console.log('📊 [WS] Market regime update:', message.data);
            setData(prev => prev ? { ...prev, marketRegime: message.data } : null);
          } else if (message.type === 'agent_log') {
            // Handle Agent Log (Brain Stream)
            console.log('🧠 [WS] Brain Stream:', message.data);
            setData(prev => {
              if (!prev) return null;
              const newMsg = message.data;
              // Avoid duplicates if needed, or just append
              return {
                ...prev,
                messages: [newMsg, ...(prev.messages || [])].slice(0, 100) // Keep last 100
              };
            });
          } else if (message.type === 'trade_update') {
            console.log('📈 [WS] Trade update received:', message.data);
          } else if (message.portfolio_value !== undefined) {
            // Full snapshot with portfolio_value
            console.log('🎯 [WS] Setting dashboard data (portfolio_value present)');
            setData(message);
          } else if (message.status && message.timestamp) {
            // Fallback: Accept any message with status and timestamp as valid snapshot
            console.log('🔄 [WS] Setting dashboard data (fallback: status+timestamp)');
            setData({ ...message, portfolio_value: message.portfolio_balance || 100000 });
          } else if (message.error) {
            console.error('❌ [WS] Server error:', message.error);
          } else {
            // Log unknown message types for debugging
            console.log('❓ [WS] Unknown message format:', JSON.stringify(message).slice(0, 200));
          }
        } catch (e) {
          console.error('❌ [WS] Failed to parse WebSocket message:', e, 'Raw:', event.data.slice(0, 200));
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

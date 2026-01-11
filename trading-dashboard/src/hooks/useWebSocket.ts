
import { useState, useEffect, useRef } from 'react';
import { getWebSocketUrl } from '../utils/apiConfig';

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
  portfolio_value: number;
  total_exposure: number;
  aster_pnl_percent?: number;
  hl_pnl_percent?: number;
  systems?: any;
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

export const useDashboardWebSocket = (url?: string, token?: string | null): UseWebSocketReturn => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // NUCLEAR: Aggressive reconnection for maximum reliability
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectDelay = 10000; // 10 seconds max (was 30s)
  const baseReconnectDelay = 500; // Start at 500ms (was 1000ms)

  const connect = () => {
    if (!token) {
      // console.debug('⏳ [WS] Waiting for auth token...');
      return;
    }

    try {
      // Determine WebSocket URL using centralized config
      const baseUrl = getWebSocketUrl();
      const fullWsUrl = `${baseUrl}?token=${token}`;

      console.log(`🔌 Connecting to WebSocket: ${baseUrl} (Auth Token Attached)`);
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
          } else if (message.type === 'ai_log' || message.type === 'log') {
            // Handle Agent Log (Brain Stream)
            console.log('🧠 [WS] Brain Stream:', message.data);
            setData(prev => {
              if (!prev) return null;
              // Normalize new message format
              const newMsg: ChatMessage = {
                id: message.id || Date.now().toString(),
                agentId: message.data?.agent || 'system',
                agentName: message.data?.agent || 'System',
                role: message.data?.role || 'system',
                content: message.data?.message || JSON.stringify(message.data),
                timestamp: message.data?.timestamp || new Date().toISOString(),
              };

              return {
                ...prev,
                messages: [newMsg, ...(prev.messages || [])].slice(0, 100) // Keep last 100
              };
            });
          } else if (message.type === 'trade_update' || message.type === 'trade_executed') {
            console.log('📈 [WS] Trade update received:', message.data);
            setData(prev => {
              if (!prev) return null;
              // Parse new trade data (TradeResult from backend)
              const tradeData = message.data || message;
              const newTrade: Trade = {
                // Backend uses trade_id, fallback to id or timestamp
                id: tradeData.trade_id || tradeData.id || String(Date.now()),
                symbol: tradeData.symbol,
                side: tradeData.side,
                // Backend uses avg_price or price
                price: Number(tradeData.avg_price || tradeData.price || 0),
                // Backend uses filled_quantity or quantity
                quantity: Number(tradeData.filled_quantity || tradeData.quantity || tradeData.lines || 0),
                total: Number(tradeData.avg_price || tradeData.price || 0) * Number(tradeData.filled_quantity || tradeData.quantity || 0),
                timestamp: tradeData.timestamp || tradeData.execution_time || new Date().toISOString(),
                status: tradeData.success === false ? 'FAILED' : 'FILLED',
                // Backend uses platform field as the executor
                agentId: tradeData.platform || tradeData.agent || 'unknown'
              };

              return {
                ...prev,
                recentTrades: [newTrade, ...(prev.recentTrades || [])].slice(0, 50)
              };
            });
          } else if (message.type === 'init') {
            console.log('🚀 [WS] Init Snapshot received:', message);
            // Transform Init Data to DashboardData
            const snapshot: DashboardData = {
              timestamp: Date.now(),
              total_pnl: 0,
              portfolio_balance: message.total_balance || 0,
              portfolio_value: message.total_balance || 0,
              total_exposure: 0,
              agents: [],
              messages: [],
              // Accurately map TradeResult objects from init snapshot
              recentTrades: (message.recent_trades || []).map((t: any) => ({
                id: t.trade_id || t.id || String(Date.now()),
                symbol: t.symbol,
                side: t.side,
                price: Number(t.avg_price || t.price || 0),
                quantity: Number(t.filled_quantity || t.quantity || 0),
                total: Number(t.avg_price || t.price || 0) * Number(t.filled_quantity || t.quantity || 0),
                timestamp: t.timestamp || t.received_at || new Date().toISOString(),
                status: t.success === false ? 'FAILED' : 'FILLED',
                agentId: t.platform || t.agent || 'unknown'
              })),
              marketRegime: undefined,
              open_positions: (message.positions || []).map((p: any) => ({
                symbol: p.symbol,
                side: p.side || (Number(p.amount) > 0 ? 'BUY' : 'SELL'),
                quantity: Math.abs(Number(p.amount || p.size || 0)),
                entry_price: Number(p.entry_price || 0),
                current_price: Number(p.mark_price || p.current_price || 0),
                pnl: Number(p.unrealized_pnl || p.pnl || 0),
                agent: p.platform || 'unknown'
              }))
            };
            setData(snapshot);
          } else if (message.type === 'ping') {
            // Heartbeat - silent connection check
            // console.debug('💓 [WS] Heartbeat received');
          } else if (message.portfolio_value !== undefined || message.portfolio_balance !== undefined) {
            // Full Dashboard Snapshot
            // console.log('🎯 [WS] Full Snapshot received:', message.portfolio_value);

            // Safe Parsing with defaults (NO FAKE 100k)
            const safeSnapshot: DashboardData = {
              timestamp: message.timestamp || Date.now() / 1000,
              portfolio_value: typeof message.portfolio_value === 'number' ? message.portfolio_value : (message.portfolio_balance || 0),
              portfolio_balance: typeof message.portfolio_balance === 'number' ? message.portfolio_balance : 0,
              total_pnl: message.total_pnl || 0,
              total_pnl_percent: message.total_pnl_percent || 0,
              total_exposure: message.total_exposure || 0,

              // Arrays
              agents: Array.isArray(message.agents) ? message.agents : [],
              recentTrades: Array.isArray(message.recentTrades) ? message.recentTrades : [],
              messages: Array.isArray(message.messages) ? message.messages : [],
              open_positions: Array.isArray(message.open_positions) ? message.open_positions : [],

              // Optional
              aster_pnl_percent: message.aster_pnl_percent,
              hl_pnl_percent: message.hl_pnl_percent,
              systems: message.systems
            };

            setData(safeSnapshot);
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
        const exponentialDelay = Math.min(
          maxReconnectDelay,
          baseReconnectDelay * Math.pow(1.5, reconnectAttemptsRef.current)
        );
        const jitter = Math.random() * 500;
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
  }, [url, token]);

  return { data, connected, error };
};

export default useDashboardWebSocket;

<template>
  <div class="trader-terminals-view">
    <div class="terminals-header">
      <h1 class="title">
        <span class="icon">⚡</span>
        SAPPHIRE TRADER TERMINALS
        <span class="status-indicator" :class="connectionStatus">{{ connectionStatus }}</span>
      </h1>
      <div class="global-controls">
        <button @click="pauseAllLogs" class="control-btn">
          <span v-if="logsPaused">▶️ Resume</span>
          <span v-else>⏸️ Pause</span>
        </button>
        <button @click="clearAllLogs" class="control-btn danger">🗑️ Clear All</button>
      </div>
    </div>

    <div class="terminals-grid">
      <!-- Aster Terminal -->
      <TraderTerminal
        :trader="traders.aster"
        @send-command="sendCommand"
      />

      <!-- Lighter Terminal -->
      <TraderTerminal
        :trader="traders.lighter"
        @send-command="sendCommand"
      />

      <!-- Aster Terminal -->
      <TraderTerminal
        :trader="traders.aster"
        @send-command="sendCommand"
      />

      <!-- Aster Terminal -->
      <TraderTerminal
        :trader="traders.aster"
        @send-command="sendCommand"
      />

      <!-- Lighter Terminal -->
      <TraderTerminal
        :trader="traders.lighter"
        @send-command="sendCommand"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import TraderTerminal from '../components/TraderTerminal.vue'

interface Trader {
  id: string
  name: string
  status: 'online' | 'offline' | 'trading' | 'error'
  logs: LogEntry[]
  stats: {
    trades: number
    pnl: number
    winRate: number
    volume: number
  }
}

interface LogEntry {
  timestamp: Date
  level: 'info' | 'warn' | 'error' | 'success' | 'trade'
  message: string
}

const connectionStatus = ref<'connected' | 'disconnected' | 'connecting'>('connecting')
const logsPaused = ref(false)

const traders = reactive({
  aster: {
    id: 'aster',
    name: 'Aster (Solana Perps)',
    status: 'offline',
    logs: [] as LogEntry[],
    stats: { trades: 0, pnl: 0, winRate: 0, volume: 0 }
  },
  lighter: {
    id: 'lighter',
    name: 'Lighter',
    status: 'offline',
    logs: [] as LogEntry[],
    stats: { trades: 0, pnl: 0, winRate: 0, volume: 0 }
  },
  aster: {
    id: 'aster',
    name: 'Aster',
    status: 'offline',
    logs: [] as LogEntry[],
    stats: { trades: 0, pnl: 0, winRate: 0, volume: 0 }
  },
  aster: {
    id: 'aster',
    name: 'Aster (Monad)',
    status: 'offline',
    logs: [] as LogEntry[],
    stats: { trades: 0, pnl: 0, winRate: 0, volume: 0 }
  },
  lighter: {
    id: 'lighter',
    name: 'Lighter',
    status: 'offline',
    logs: [] as LogEntry[],
    stats: { trades: 0, pnl: 0, winRate: 0, volume: 0 }
  }
} as Record<string, Trader>)

let ws: WebSocket | null = null
let reconnectTimer: number | null = null

const connectWebSocket = () => {
  connectionStatus.value = 'connecting'

  // Connect to backend WebSocket for live logs
  const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8080/ws/logs'

  try {
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      connectionStatus.value = 'connected'
      console.log('WebSocket connected')
    }

    ws.onmessage = (event) => {
      if (logsPaused.value) return

      try {
        const data = JSON.parse(event.data)
        handleLogMessage(data)
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      connectionStatus.value = 'disconnected'
    }

    ws.onclose = () => {
      connectionStatus.value = 'disconnected'
      console.log('WebSocket disconnected, reconnecting in 5s...')
      reconnectTimer = window.setTimeout(connectWebSocket, 5000)
    }
  } catch (e) {
    console.error('Failed to connect WebSocket:', e)
    connectionStatus.value = 'disconnected'
    reconnectTimer = window.setTimeout(connectWebSocket, 5000)
  }
}

const handleLogMessage = (data: any) => {
  const traderId = data.trader || data.service
  const trader = traders[traderId]

  if (!trader) return

  const logEntry: LogEntry = {
    timestamp: new Date(data.timestamp || Date.now()),
    level: data.level || 'info',
    message: data.message || data.text
  }

  trader.logs.push(logEntry)

  // Keep only last 500 logs per trader
  if (trader.logs.length > 500) {
    trader.logs.shift()
  }

  // Update stats if included
  if (data.stats) {
    trader.stats = { ...trader.stats, ...data.stats }
  }

  // Update status based on log content
  if (data.message?.includes('ERROR') || data.level === 'error') {
    trader.status = 'error'
  } else if (data.message?.includes('SWAP') || data.message?.includes('BUY') || data.message?.includes('SELL')) {
    trader.status = 'trading'
    setTimeout(() => {
      if (trader.status === 'trading') trader.status = 'online'
    }, 3000)
  }
}

const sendCommand = (traderId: string, command: string) => {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('WebSocket not connected')
    return
  }

  ws.send(JSON.stringify({
    type: 'command',
    trader: traderId,
    command: command
  }))

  // Add command to logs
  const trader = traders[traderId]
  if (trader) {
    trader.logs.push({
      timestamp: new Date(),
      level: 'info',
      message: `> ${command}`
    })
  }
}

const pauseAllLogs = () => {
  logsPaused.value = !logsPaused.value
}

const clearAllLogs = () => {
  Object.values(traders).forEach(trader => {
    trader.logs = []
  })
}

// Simulate logs for demo (remove when WebSocket is connected)
const simulateLogs = () => {
  const messages = [
    { trader: 'aster', level: 'info', message: '📊 Analyzing SOL-PERP trends...' },
    { trader: 'aster', level: 'success', message: '✅ VPIN signal detected: SOL-PERP (conf: 0.85)' },
    { trader: 'lighter', level: 'info', message: '🔍 Scanning BTC-USDC market...' },
    { trader: 'lighter', level: 'warn', message: '⚠️ High volatility detected on BTC-USDC' },
    { trader: 'lighter', level: 'trade', message: '🧠 [Momentum] BTC-USDC: LONG (conf: 0.72)' },
    { trader: 'aster', level: 'info', message: '⚡ Shield strategy active, monitoring BTC-PERP...' },
    { trader: 'aster', level: 'info', message: '🎵 Monitoring MON-USDC liquidity...' },
    { trader: 'lighter', level: 'info', message: '💡 Lighter orderbook analysis running...' },
  ]

  setInterval(() => {
    if (logsPaused.value) return
    const msg = messages[Math.floor(Math.random() * messages.length)]
    handleLogMessage({
      ...msg,
      timestamp: new Date().toISOString()
    })
  }, 2000)
}

onMounted(() => {
  connectWebSocket()
  simulateLogs() // Remove this when real WebSocket is connected
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
  }
})
</script>

<style scoped>
.trader-terminals-view {
  min-height: 100vh;
  background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%);
  padding: 2rem;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.terminals-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(0, 247, 255, 0.2);
  border-radius: 12px;
  backdrop-filter: blur(10px);
}

.title {
  font-size: 1.5rem;
  font-weight: 700;
  color: #00f7ff;
  text-transform: uppercase;
  letter-spacing: 2px;
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 0;
}

.icon {
  font-size: 2rem;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(1.1); }
}

.status-indicator {
  font-size: 0.75rem;
  padding: 0.4rem 0.8rem;
  border-radius: 20px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 1px;
}

.status-indicator.connected {
  background: rgba(0, 255, 136, 0.2);
  color: #00ff88;
  border: 1px solid #00ff88;
  box-shadow: 0 0 15px rgba(0, 255, 136, 0.3);
}

.status-indicator.disconnected {
  background: rgba(255, 68, 68, 0.2);
  color: #ff4444;
  border: 1px solid #ff4444;
}

.status-indicator.connecting {
  background: rgba(255, 187, 0, 0.2);
  color: #ffbb00;
  border: 1px solid #ffbb00;
  animation: blink 1s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.global-controls {
  display: flex;
  gap: 1rem;
}

.control-btn {
  padding: 0.75rem 1.5rem;
  background: rgba(0, 247, 255, 0.1);
  border: 1px solid rgba(0, 247, 255, 0.3);
  border-radius: 8px;
  color: #00f7ff;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  text-transform: uppercase;
  font-size: 0.85rem;
  letter-spacing: 1px;
}

.control-btn:hover {
  background: rgba(0, 247, 255, 0.2);
  border-color: #00f7ff;
  box-shadow: 0 0 20px rgba(0, 247, 255, 0.4);
  transform: translateY(-2px);
}

.control-btn.danger {
  background: rgba(255, 68, 68, 0.1);
  border-color: rgba(255, 68, 68, 0.3);
  color: #ff4444;
}

.control-btn.danger:hover {
  background: rgba(255, 68, 68, 0.2);
  border-color: #ff4444;
  box-shadow: 0 0 20px rgba(255, 68, 68, 0.4);
}

.terminals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
  gap: 1.5rem;
}

@media (max-width: 1400px) {
  .terminals-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 900px) {
  .terminals-grid {
    grid-template-columns: 1fr;
  }
}
</style>

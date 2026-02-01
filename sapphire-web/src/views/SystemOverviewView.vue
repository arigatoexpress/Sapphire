<template>
  <div class="system-overview">
    <div class="overview-header">
      <h1 class="main-title">
        <span class="pulse-icon">💎</span>
        SAPPHIRE TRADING SYSTEM
        <span class="pulse-icon">💎</span>
      </h1>
      <div class="system-time">{{ currentTime }}</div>
    </div>

    <div class="system-grid">
      <!-- Core System Status -->
      <div class="panel core-status">
        <h2 class="panel-title">🔷 CORE SYSTEM</h2>
        <div class="status-grid">
          <StatusNode
            v-for="component in coreComponents"
            :key="component.id"
            :component="component"
          />
        </div>
      </div>

      <!-- Trading Platforms -->
      <div class="panel platforms-status">
        <h2 class="panel-title">⚡ TRADING PLATFORMS</h2>
        <div class="platforms-visualization">
          <PlatformNode
            v-for="platform in platforms"
            :key="platform.id"
            :platform="platform"
          />
        </div>
      </div>

      <!-- Data Feeds -->
      <div class="panel data-feeds">
        <h2 class="panel-title">📡 DATA FEEDS</h2>
        <div class="feeds-list">
          <DataFeed
            v-for="feed in dataFeeds"
            :key="feed.id"
            :feed="feed"
          />
        </div>
      </div>

      <!-- Live Metrics -->
      <div class="panel live-metrics">
        <h2 class="panel-title">📊 LIVE METRICS</h2>
        <div class="metrics-grid">
          <div class="metric">
            <div class="metric-label">Total Trades</div>
            <div class="metric-value animated-number">{{ metrics.totalTrades }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Active Positions</div>
            <div class="metric-value animated-number">{{ metrics.activePositions }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Total P&L</div>
            <div class="metric-value" :class="metrics.totalPnl >= 0 ? 'positive' : 'negative'">
              {{ metrics.totalPnl >= 0 ? '+' : '' }}${{ metrics.totalPnl.toFixed(2) }}
            </div>
          </div>
          <div class="metric">
            <div class="metric-label">Win Rate</div>
            <div class="metric-value">{{ (metrics.winRate * 100).toFixed(1) }}%</div>
          </div>
        </div>
      </div>

      <!-- System Flow Visualization -->
      <div class="panel system-flow">
        <h2 class="panel-title">🔄 SYSTEM FLOW</h2>
        <svg class="flow-diagram" viewBox="0 0 800 400">
          <!-- Data Sources -->
          <g class="data-sources">
            <circle cx="100" cy="100" r="30" class="node pulse" />
            <text x="100" y="105" text-anchor="middle" class="node-label">Price Feed</text>
          </g>

          <!-- AI Engine -->
          <g class="ai-engine">
            <rect x="320" y="70" width="160" height="60" rx="10" class="node glow" />
            <text x="400" y="105" text-anchor="middle" class="node-label">AI ENGINE</text>
          </g>

          <!-- Trading Platforms -->
          <g class="trading-platforms">
            <circle cx="700" cy="60" r="25" class="node pulse-fast" />
            <text x="700" y="100" text-anchor="middle" class="node-label">Drift</text>

            <circle cx="700" cy="140" r="25" class="node pulse-fast" />
            <text x="700" y="180" text-anchor="middle" class="node-label">Hyperliquid</text>

            <circle cx="700" cy="220" r="25" class="node pulse-fast" />
            <text x="700" y="260" text-anchor="middle" class="node-label">Aster</text>

            <circle cx="700" cy="300" r="25" class="node pulse-fast" />
            <text x="700" y="340" text-anchor="middle" class="node-label">Symphony</text>
          </g>

          <!-- Animated Connections -->
          <path d="M 130 100 Q 225 100 320 100" class="connection" />
          <path d="M 480 100 L 675 60" class="connection" />
          <path d="M 480 100 L 675 140" class="connection" />
          <path d="M 480 100 L 675 220" class="connection" />
          <path d="M 480 100 L 675 300" class="connection" />

          <!-- Data Flow Particles -->
          <circle r="4" class="particle">
            <animateMotion dur="3s" repeatCount="indefinite" path="M 130 100 Q 225 100 320 100" />
          </circle>
          <circle r="4" class="particle">
            <animateMotion dur="2s" repeatCount="indefinite" path="M 480 100 L 675 60" />
          </circle>
          <circle r="4" class="particle">
            <animateMotion dur="2.5s" repeatCount="indefinite" path="M 480 100 L 675 140" />
          </circle>
          <circle r="4" class="particle">
            <animateMotion dur="2.2s" repeatCount="indefinite" path="M 480 100 L 675 220" />
          </circle>
          <circle r="4" class="particle">
            <animateMotion dur="2.8s" repeatCount="indefinite" path="M 480 100 L 675 300" />
          </circle>
        </svg>
      </div>

      <!-- Recent Activity -->
      <div class="panel recent-activity">
        <h2 class="panel-title">⚡ RECENT ACTIVITY</h2>
        <div class="activity-stream">
          <div
            v-for="(activity, index) in recentActivity"
            :key="index"
            class="activity-item"
            :class="`activity-${activity.type}`"
          >
            <span class="activity-time">{{ formatTime(activity.timestamp) }}</span>
            <span class="activity-icon">{{ getActivityIcon(activity.type) }}</span>
            <span class="activity-message">{{ activity.message }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import StatusNode from '../components/StatusNode.vue'
import PlatformNode from '../components/PlatformNode.vue'
import DataFeed from '../components/DataFeed.vue'

const currentTime = ref('')

const coreComponents = reactive([
  { id: 'orchestrator', name: 'Trading Orchestrator', status: 'online' as const, health: 100 },
  { id: 'router', name: 'Platform Router', status: 'online' as const, health: 100 },
  { id: 'agents', name: 'AI Agents', status: 'online' as const, health: 95 },
  { id: 'monitoring', name: 'Monitoring', status: 'online' as const, health: 100 },
  { id: 'positions', name: 'Position Tracker', status: 'online' as const, health: 100 },
  { id: 'mev', name: 'MEV Protection', status: 'online' as const, health: 98 },
])

const platforms = reactive([
  { id: 'drift', name: 'Drift', status: 'offline' as const, trades: 0, volume: 0 },
  { id: 'hyperliquid', name: 'Hyperliquid', status: 'offline' as const, trades: 0, volume: 0 },
  { id: 'aster', name: 'Aster', status: 'offline' as const, trades: 0, volume: 0 },
  { id: 'symphony', name: 'Symphony', status: 'offline' as const, trades: 0, volume: 0 },
  { id: 'lighter', name: 'Lighter', status: 'offline' as const, trades: 0, volume: 0 },
])

const dataFeeds = reactive([
  { id: 'solana-rpc', name: 'Solana RPC', status: 'active' as const, latency: 120, rate: 450 },
  { id: 'jupiter-api', name: 'Jupiter API', status: 'active' as const, latency: 85, rate: 320 },
  { id: 'gemini-ai', name: 'Gemini AI', status: 'degraded' as const, latency: 650, rate: 15 },
  { id: 'telegram', name: 'Telegram Bot', status: 'active' as const, latency: 200, rate: 5 },
  { id: 'firestore', name: 'Firestore', status: 'active' as const, latency: 150, rate: 80 },
])

const metrics = reactive({
  totalTrades: 47,
  activePositions: 3,
  totalPnl: 234.56,
  winRate: 0.64,
})

const recentActivity = reactive([
  { timestamp: new Date(), type: 'info', message: 'System initialized: 5 platforms ready' },
  { timestamp: new Date(Date.now() - 15000), type: 'signal', message: 'AI Signal: BUY confidence 0.78' },
  { timestamp: new Date(Date.now() - 32000), type: 'info', message: 'Hyperliquid connection established' },
  { timestamp: new Date(Date.now() - 58000), type: 'success', message: 'Configuration loaded successfully' },
  { timestamp: new Date(Date.now() - 92000), type: 'info', message: 'Monitoring services started' },
])

const updateTime = () => {
  const now = new Date()
  currentTime.value = now.toLocaleTimeString('en-US', { hour12: false }) + '.' + String(now.getMilliseconds()).padStart(3, '0')
}

const formatTime = (date: Date) => {
  const now = new Date()
  const diff = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return date.toLocaleTimeString('en-US', { hour12: false })
}

const getActivityIcon = (type: string) => {
  const icons: Record<string, string> = {
    trade: '💰',
    signal: '🧠',
    info: 'ℹ️',
    success: '✅',
    warn: '⚠️',
    error: '❌',
  }
  return icons[type] || 'ℹ️'
}

// Simulate live updates
const simulateUpdates = () => {
  setInterval(() => {
    // Random metric updates
    if (Math.random() > 0.7) {
      metrics.totalTrades += 1
      metrics.totalPnl += (Math.random() - 0.4) * 50
      metrics.winRate = metrics.winRate * 0.95 + (Math.random() > 0.4 ? 0.05 : 0)

      // Add activity
      const platformNames = ['Drift', 'Hyperliquid', 'Aster', 'Symphony', 'Lighter']
      const randomPlatform = platformNames[Math.floor(Math.random() * platformNames.length)]
      const activities = [
        { type: 'signal', message: `AI Signal: ${Math.random() > 0.5 ? 'BUY' : 'SELL'} confidence ${(0.5 + Math.random() * 0.5).toFixed(2)}` },
        { type: 'info', message: `${randomPlatform}: Monitoring market conditions` },
        { type: 'success', message: `${randomPlatform}: Connection healthy` },
      ]
      const newActivity = activities[Math.floor(Math.random() * activities.length)]
      recentActivity.unshift({ ...newActivity, timestamp: new Date() })
      if (recentActivity.length > 10) recentActivity.pop()
    }
  }, 5000)
}

onMounted(() => {
  updateTime()
  setInterval(updateTime, 100)
  simulateUpdates()
})
</script>

<style scoped>
.system-overview {
  min-height: 100vh;
  background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 50%, #0a0e27 100%);
  padding: 2rem;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  position: relative;
  overflow: hidden;
}

/* Animated background grid */
.system-overview::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image:
    linear-gradient(rgba(0, 247, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 247, 255, 0.03) 1px, transparent 1px);
  background-size: 50px 50px;
  pointer-events: none;
  animation: grid-move 20s linear infinite;
}

@keyframes grid-move {
  0% { transform: translate(0, 0); }
  100% { transform: translate(50px, 50px); }
}

.overview-header {
  text-align: center;
  margin-bottom: 3rem;
  position: relative;
  z-index: 1;
}

.main-title {
  font-size: 2.5rem;
  font-weight: 900;
  background: linear-gradient(90deg, #00f7ff 0%, #00ff88 50%, #00f7ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  text-transform: uppercase;
  letter-spacing: 4px;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2rem;
}

.pulse-icon {
  font-size: 3rem;
  animation: pulse-glow 2s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% {
    filter: drop-shadow(0 0 10px rgba(0, 247, 255, 0.8));
    transform: scale(1);
  }
  50% {
    filter: drop-shadow(0 0 30px rgba(0, 255, 136, 0.8));
    transform: scale(1.2);
  }
}

.system-time {
  font-size: 1.2rem;
  color: #00f7ff;
  margin-top: 1rem;
  font-weight: 700;
  letter-spacing: 2px;
}

.system-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 1.5rem;
  position: relative;
  z-index: 1;
}

.panel {
  background: rgba(10, 14, 39, 0.8);
  border: 2px solid rgba(0, 247, 255, 0.3);
  border-radius: 16px;
  padding: 1.5rem;
  backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  transition: all 0.3s ease;
}

.panel:hover {
  border-color: rgba(0, 247, 255, 0.6);
  box-shadow: 0 8px 32px rgba(0, 247, 255, 0.2);
  transform: translateY(-4px);
}

.panel-title {
  font-size: 1rem;
  color: #00f7ff;
  text-transform: uppercase;
  letter-spacing: 2px;
  margin: 0 0 1.5rem 0;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.core-status {
  grid-column: span 6;
}

.platforms-status {
  grid-column: span 6;
}

.data-feeds {
  grid-column: span 4;
}

.live-metrics {
  grid-column: span 8;
}

.system-flow {
  grid-column: span 12;
}

.recent-activity {
  grid-column: span 12;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

.platforms-visualization {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

.feeds-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
}

.metric {
  text-align: center;
  padding: 1.5rem;
  background: rgba(0, 247, 255, 0.05);
  border: 1px solid rgba(0, 247, 255, 0.2);
  border-radius: 12px;
  transition: all 0.3s ease;
}

.metric:hover {
  background: rgba(0, 247, 255, 0.1);
  border-color: rgba(0, 247, 255, 0.5);
  transform: scale(1.05);
}

.metric-label {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.6);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 0.5rem;
}

.metric-value {
  font-size: 2rem;
  font-weight: 900;
  color: #fff;
}

.metric-value.positive {
  color: #00ff88;
}

.metric-value.negative {
  color: #ff4444;
}

.metric-value.animated-number {
  animation: number-pop 0.5s ease-out;
}

@keyframes number-pop {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

.flow-diagram {
  width: 100%;
  height: 400px;
}

.node {
  fill: rgba(0, 247, 255, 0.2);
  stroke: #00f7ff;
  stroke-width: 2;
}

.node.pulse {
  animation: node-pulse 2s ease-in-out infinite;
}

.node.pulse-fast {
  animation: node-pulse 1s ease-in-out infinite;
}

.node.glow {
  filter: drop-shadow(0 0 10px rgba(0, 247, 255, 0.8));
}

@keyframes node-pulse {
  0%, 100% {
    fill: rgba(0, 247, 255, 0.2);
    stroke-width: 2;
  }
  50% {
    fill: rgba(0, 247, 255, 0.4);
    stroke-width: 3;
  }
}

.node-label {
  fill: #00f7ff;
  font-size: 12px;
  font-weight: 700;
}

.connection {
  stroke: rgba(0, 247, 255, 0.4);
  stroke-width: 2;
  fill: none;
  stroke-dasharray: 5, 5;
  animation: dash-move 20s linear infinite;
}

@keyframes dash-move {
  to {
    stroke-dashoffset: -1000;
  }
}

.particle {
  fill: #00ff88;
  filter: drop-shadow(0 0 5px #00ff88);
}

.activity-stream {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 400px;
  overflow-y: auto;
}

.activity-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: rgba(0, 247, 255, 0.05);
  border-left: 3px solid rgba(0, 247, 255, 0.3);
  border-radius: 8px;
  transition: all 0.2s ease;
  animation: slide-in 0.3s ease-out;
}

@keyframes slide-in {
  from {
    opacity: 0;
    transform: translateX(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.activity-item:hover {
  background: rgba(0, 247, 255, 0.1);
  border-left-color: #00f7ff;
  transform: translateX(5px);
}

.activity-time {
  font-size: 0.75rem;
  color: rgba(0, 247, 255, 0.6);
  min-width: 80px;
}

.activity-icon {
  font-size: 1.2rem;
}

.activity-message {
  color: rgba(255, 255, 255, 0.9);
  flex: 1;
}

.activity-trade {
  border-left-color: rgba(0, 255, 136, 0.6);
}

.activity-signal {
  border-left-color: rgba(138, 43, 226, 0.6);
}

.activity-warn {
  border-left-color: rgba(255, 187, 0, 0.6);
}

.activity-error {
  border-left-color: rgba(255, 68, 68, 0.6);
}

@media (max-width: 1400px) {
  .status-grid,
  .platforms-visualization {
    grid-template-columns: repeat(2, 1fr);
  }

  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 900px) {
  .system-grid .panel {
    grid-column: span 12 !important;
  }

  .status-grid,
  .platforms-visualization,
  .metrics-grid {
    grid-template-columns: 1fr;
  }
}
</style>

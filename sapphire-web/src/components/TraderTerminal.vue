<template>
  <div class="trader-terminal" :class="[`status-${trader.status}`]">
    <!-- Terminal Header -->
    <div class="terminal-header">
      <div class="header-left">
        <div class="terminal-icon">
          <span v-if="trader.status === 'online'">🟢</span>
          <span v-else-if="trader.status === 'trading'">⚡</span>
          <span v-else-if="trader.status === 'error'">🔴</span>
          <span v-else>⚪</span>
        </div>
        <div class="terminal-title">
          <h3>{{ trader.name }}</h3>
          <span class="terminal-id">{{ trader.id }}</span>
        </div>
      </div>
      <div class="header-stats">
        <div class="stat">
          <span class="stat-label">Trades</span>
          <span class="stat-value">{{ trader.stats.trades }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">P&L</span>
          <span class="stat-value" :class="trader.stats.pnl >= 0 ? 'positive' : 'negative'">
            {{ trader.stats.pnl >= 0 ? '+' : '' }}${{ trader.stats.pnl.toFixed(2) }}
          </span>
        </div>
        <div class="stat">
          <span class="stat-label">Win%</span>
          <span class="stat-value">{{ (trader.stats.winRate * 100).toFixed(1) }}%</span>
        </div>
      </div>
    </div>

    <!-- Terminal Screen -->
    <div class="terminal-screen" ref="terminalScreen">
      <div class="scan-line"></div>
      <div class="terminal-content">
        <div
          v-for="(log, index) in trader.logs"
          :key="index"
          class="log-entry"
          :class="`log-${log.level}`"
        >
          <span class="log-timestamp">{{ formatTimestamp(log.timestamp) }}</span>
          <span class="log-message" v-html="formatLogMessage(log.message)"></span>
        </div>
        <div v-if="trader.logs.length === 0" class="log-entry log-info">
          <span class="log-message">Waiting for logs...</span>
        </div>
      </div>
    </div>

    <!-- Terminal Input -->
    <div class="terminal-input">
      <span class="input-prompt">{{ trader.id }}@sapphire:~$</span>
      <input
        v-model="commandInput"
        @keyup.enter="sendCommand"
        type="text"
        placeholder="Enter command..."
        class="command-input"
      />
      <button @click="sendCommand" class="send-btn">→</button>
    </div>

    <!-- Quick Actions -->
    <div class="quick-actions">
      <button @click="sendQuickCommand('status')" class="quick-btn">📊 Status</button>
      <button @click="sendQuickCommand('positions')" class="quick-btn">📈 Positions</button>
      <button @click="sendQuickCommand('health')" class="quick-btn">💚 Health</button>
      <button @click="clearTerminal" class="quick-btn danger">🗑️ Clear</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

interface Trader {
  id: string
  name: string
  status: 'online' | 'offline' | 'trading' | 'error'
  logs: Array<{
    timestamp: Date
    level: 'info' | 'warn' | 'error' | 'success' | 'trade'
    message: string
  }>
  stats: {
    trades: number
    pnl: number
    winRate: number
    volume: number
  }
}

const props = defineProps<{
  trader: Trader
}>()

const emit = defineEmits<{
  (e: 'send-command', traderId: string, command: string): void
}>()

const commandInput = ref('')
const terminalScreen = ref<HTMLElement | null>(null)

const formatTimestamp = (date: Date) => {
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  const ms = String(date.getMilliseconds()).padStart(3, '0')
  return `${hours}:${minutes}:${seconds}.${ms}`
}

const formatLogMessage = (message: string) => {
  // Highlight numbers in cyan
  message = message.replace(/(\d+\.?\d*)/g, '<span class="highlight-number">$1</span>')

  // Highlight symbols/tickers
  message = message.replace(/([A-Z]{2,}-[A-Z]{2,})/g, '<span class="highlight-symbol">$1</span>')

  // Highlight actions (BUY, SELL, HOLD)
  message = message.replace(/(BUY|SELL|HOLD)/g, '<span class="highlight-action">$1</span>')

  // Highlight emojis larger
  message = message.replace(/([\u{1F300}-\u{1F9FF}])/gu, '<span class="emoji">$1</span>')

  return message
}

const sendCommand = () => {
  if (!commandInput.value.trim()) return

  emit('send-command', props.trader.id, commandInput.value.trim())
  commandInput.value = ''
}

const sendQuickCommand = (command: string) => {
  emit('send-command', props.trader.id, command)
}

const clearTerminal = () => {
  props.trader.logs.length = 0
}

// Auto-scroll to bottom when new logs arrive
watch(() => props.trader.logs.length, async () => {
  await nextTick()
  if (terminalScreen.value) {
    terminalScreen.value.scrollTop = terminalScreen.value.scrollHeight
  }
})
</script>

<style scoped>
.trader-terminal {
  background: rgba(10, 14, 39, 0.9);
  border: 2px solid rgba(0, 247, 255, 0.3);
  border-radius: 16px;
  overflow: hidden;
  backdrop-filter: blur(20px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  transition: all 0.3s ease;
}

.trader-terminal:hover {
  border-color: rgba(0, 247, 255, 0.6);
  box-shadow: 0 8px 32px rgba(0, 247, 255, 0.2);
  transform: translateY(-4px);
}

.trader-terminal.status-trading {
  border-color: rgba(0, 255, 136, 0.6);
  box-shadow: 0 0 40px rgba(0, 255, 136, 0.3);
  animation: trading-pulse 1.5s ease-in-out infinite;
}

@keyframes trading-pulse {
  0%, 100% { box-shadow: 0 0 20px rgba(0, 255, 136, 0.3); }
  50% { box-shadow: 0 0 60px rgba(0, 255, 136, 0.6); }
}

.trader-terminal.status-error {
  border-color: rgba(255, 68, 68, 0.6);
}

.trader-terminal.status-offline {
  opacity: 0.6;
  border-color: rgba(100, 100, 100, 0.3);
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: linear-gradient(90deg, rgba(0, 247, 255, 0.1) 0%, rgba(0, 247, 255, 0.05) 100%);
  border-bottom: 1px solid rgba(0, 247, 255, 0.2);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.terminal-icon {
  font-size: 1.5rem;
  animation: pulse 2s ease-in-out infinite;
}

.terminal-title h3 {
  margin: 0;
  font-size: 1rem;
  color: #00f7ff;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.terminal-id {
  font-size: 0.75rem;
  color: rgba(0, 247, 255, 0.6);
  text-transform: lowercase;
}

.header-stats {
  display: flex;
  gap: 1.5rem;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.stat-label {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.stat-value {
  font-size: 0.95rem;
  color: #fff;
  font-weight: 700;
}

.stat-value.positive {
  color: #00ff88;
}

.stat-value.negative {
  color: #ff4444;
}

.terminal-screen {
  position: relative;
  height: 400px;
  overflow-y: auto;
  background: #0a0e27;
  padding: 1rem;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.85rem;
  line-height: 1.6;
}

/* Scrollbar styling */
.terminal-screen::-webkit-scrollbar {
  width: 8px;
}

.terminal-screen::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.3);
}

.terminal-screen::-webkit-scrollbar-thumb {
  background: rgba(0, 247, 255, 0.3);
  border-radius: 4px;
}

.terminal-screen::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 247, 255, 0.5);
}

.scan-line {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent 0%, rgba(0, 247, 255, 0.8) 50%, transparent 100%);
  animation: scan 3s linear infinite;
  pointer-events: none;
  z-index: 10;
}

@keyframes scan {
  0% { transform: translateY(0); opacity: 0.8; }
  100% { transform: translateY(400px); opacity: 0; }
}

.terminal-content {
  position: relative;
  z-index: 1;
}

.log-entry {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.25rem;
  padding: 0.25rem 0.5rem;
  border-left: 2px solid transparent;
  transition: all 0.2s ease;
}

.log-entry:hover {
  background: rgba(0, 247, 255, 0.05);
  border-left-color: rgba(0, 247, 255, 0.5);
}

.log-timestamp {
  color: rgba(0, 247, 255, 0.6);
  font-size: 0.75rem;
  flex-shrink: 0;
  min-width: 90px;
}

.log-message {
  color: rgba(255, 255, 255, 0.9);
  flex: 1;
}

.log-info { border-left-color: rgba(0, 247, 255, 0.3); }
.log-warn { border-left-color: rgba(255, 187, 0, 0.6); }
.log-warn .log-message { color: #ffbb00; }
.log-error { border-left-color: rgba(255, 68, 68, 0.6); }
.log-error .log-message { color: #ff4444; }
.log-success { border-left-color: rgba(0, 255, 136, 0.6); }
.log-success .log-message { color: #00ff88; }
.log-trade {
  border-left-color: rgba(138, 43, 226, 0.6);
  background: rgba(138, 43, 226, 0.1);
}
.log-trade .log-message {
  color: #bb86fc;
  font-weight: 600;
}

.log-message :deep(.highlight-number) {
  color: #00f7ff;
  font-weight: 600;
}

.log-message :deep(.highlight-symbol) {
  color: #ffbb00;
  font-weight: 700;
}

.log-message :deep(.highlight-action) {
  color: #00ff88;
  font-weight: 700;
  padding: 0.1rem 0.3rem;
  background: rgba(0, 255, 136, 0.15);
  border-radius: 3px;
}

.log-message :deep(.emoji) {
  font-size: 1.1rem;
}

.terminal-input {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  background: rgba(0, 0, 0, 0.3);
  border-top: 1px solid rgba(0, 247, 255, 0.2);
}

.input-prompt {
  color: #00ff88;
  font-weight: 700;
  font-size: 0.9rem;
  flex-shrink: 0;
}

.command-input {
  flex: 1;
  background: rgba(0, 247, 255, 0.05);
  border: 1px solid rgba(0, 247, 255, 0.2);
  border-radius: 6px;
  padding: 0.6rem 1rem;
  color: #fff;
  font-family: inherit;
  font-size: 0.9rem;
  outline: none;
  transition: all 0.3s ease;
}

.command-input:focus {
  background: rgba(0, 247, 255, 0.1);
  border-color: #00f7ff;
  box-shadow: 0 0 10px rgba(0, 247, 255, 0.3);
}

.command-input::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

.send-btn {
  padding: 0.6rem 1.2rem;
  background: linear-gradient(135deg, #00f7ff 0%, #00c9d1 100%);
  border: none;
  border-radius: 6px;
  color: #0a0e27;
  font-weight: 700;
  font-size: 1.2rem;
  cursor: pointer;
  transition: all 0.3s ease;
}

.send-btn:hover {
  transform: translateX(3px);
  box-shadow: 0 0 20px rgba(0, 247, 255, 0.5);
}

.quick-actions {
  display: flex;
  gap: 0.5rem;
  padding: 1rem 1.5rem;
  background: rgba(0, 0, 0, 0.2);
  border-top: 1px solid rgba(0, 247, 255, 0.1);
  flex-wrap: wrap;
}

.quick-btn {
  padding: 0.5rem 1rem;
  background: rgba(0, 247, 255, 0.1);
  border: 1px solid rgba(0, 247, 255, 0.2);
  border-radius: 6px;
  color: #00f7ff;
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.quick-btn:hover {
  background: rgba(0, 247, 255, 0.2);
  border-color: #00f7ff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 247, 255, 0.3);
}

.quick-btn.danger {
  background: rgba(255, 68, 68, 0.1);
  border-color: rgba(255, 68, 68, 0.2);
  color: #ff4444;
}

.quick-btn.danger:hover {
  background: rgba(255, 68, 68, 0.2);
  border-color: #ff4444;
  box-shadow: 0 4px 12px rgba(255, 68, 68, 0.3);
}
</style>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMarketStore } from '../stores/market'
import TradingChart from '../components/TradingChart.vue'

const store = useMarketStore()

onMounted(() => {
    store.startPolling()
})

// TODO: Fetch agents from store too
const agents = ref([
  { name: 'Quant Alpha', status: 'active', pnl: '+12.4%', signal: 'BUY BTC' },
  { name: 'Sentiment Sage', status: 'active', pnl: '+5.2%', signal: 'HOLD' },
  { name: 'Drift Trader', status: 'active', pnl: '+8.9%', signal: 'LONG JUP' },
  { name: 'Symphony MIT', status: 'active', pnl: '+15.1%', signal: 'SWAP MON' },
])
</script>

<template>
  <div class="dashboard">
    <div class="grid header-stats">
      <div class="stat-card glass">
        <span class="label font-mono">TOTAL PNL</span>
        <div class="value neon-text font-mono" :class="store.totalPnl >= 0 ? 'text-success' : 'text-error'">
            {{ store.totalPnl >= 0 ? '+' : '' }}{{ store.totalPnl.toFixed(2) }}
        </div>
        <div class="sub text-success">Verified</div>
      </div>
      <div class="stat-card glass">
        <span class="label font-mono">ACTIVE POSITIONS</span>
        <div class="value font-mono">{{ store.activePositions }}</div>
        <div class="sub">Exposure: Auto</div>
      </div>
      <div class="stat-card glass">
        <span class="label font-mono">WIN RATE</span>
        <div class="value font-mono">{{ store.winRate }}%</div>
        <div class="sub">Real-time</div>
      </div>
      <div class="stat-card glass">
        <span class="label font-mono">SWARM STATUS</span>
        <div class="value font-mono" :class="store.systemStatus === 'ONLINE' ? 'text-brand' : 'text-error'">
            {{ store.systemStatus }}
        </div>
        <div class="sub">{{ store.activeAgents }} Agents Active</div>
      </div>
    </div>

    <div class="visuals-grid">
      <!-- Chart Placeholder -->
      <div class="chart-container glass">
        <div class="panel-header">
          <h3 class="font-mono">PERFORMANCE</h3>
        </div>
        <div class="chart-content">
          <TradingChart />
        </div>
      </div>

      <!-- Agent List -->
      <div class="agents-container glass">
        <div class="panel-header">
          <h3 class="font-mono">ACTIVE AGENTS</h3>
        </div>
        <div class="agent-list">
          <div v-for="agent in agents" :key="agent.name" class="agent-row">
            <div class="agent-info">
              <div class="agent-name">{{ agent.name }}</div>
              <div class="agent-signal font-mono">{{ agent.signal }}</div>
            </div>
            <div class="agent-status">
              <span class="pnl text-success font-mono">{{ agent.pnl }}</span>
              <div class="dot active"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.grid {
  display: grid;
  gap: 1.5rem;
}

.header-stats {
  grid-template-columns: repeat(4, 1fr);
}

.stat-card {
  padding: 1.5rem;
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  letter-spacing: 0.05em;
}

.value {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
}

.sub {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.text-success { color: var(--color-success); }
.text-brand { color: var(--color-brand); }

.visuals-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 1.5rem;
  height: 500px;
}

.chart-container, .agents-container {
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
}

.panel-header {
  padding: 1rem 1.5rem;
  border-bottom: var(--glass-border);
}

.panel-header h3 {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin: 0;
}

.chart-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}

.agent-list {
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.agent-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.02);
  transition: background 0.2s;
}

.agent-row:hover {
  background: rgba(255, 255, 255, 0.05);
}

.agent-name {
  font-weight: 500;
  font-size: 0.9rem;
}

.agent-signal {
  font-size: 0.75rem;
  color: var(--color-brand);
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary);
}

.dot.active {
  background: var(--color-success);
  box-shadow: 0 0 5px var(--color-success);
}

.agent-status {
  display: flex;
  align-items: center;
  gap: 1rem;
}
</style>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { TrendingUp, TrendingDown, Activity, Bot, Zap, Database, Server } from 'lucide-vue-next'
import { fetchHealth, fetchPerformanceStats, fetchPlatformStatus, fetchMITStatus } from '../api/client'

// System State
const systemHealth = ref<any>(null)
const performanceStats = ref<any>(null)
const platformStatus = ref<any>(null)
const mitStatus = ref<any>(null)
const isLoading = ref(true)

// Computed metrics
const totalPnl = computed(() => {
    const pnl = performanceStats.value?.metrics?.system?.total_pnl || 0
    return pnl.toFixed(2)
})

const winRate = computed(() => {
    const stats = performanceStats.value?.metrics?.system
    if (!stats || stats.total_trades === 0) return 0
    return Math.round((stats.wins / stats.total_trades) * 100)
})

const activeAgents = computed(() => {
    return systemHealth.value?.orchestrator?.components ? 
        Object.values(systemHealth.value.orchestrator.components).filter(v => v).length : 0
})

const platforms = computed(() => {
    const health = systemHealth.value?.orchestrator?.config || {}
    return [
        { name: 'Hyperliquid', key: 'hyperliquid', enabled: true, type: 'DeFi Perps' },
        { name: 'Drift', key: 'drift', enabled: health.enable_drift, type: 'Solana Perps' },
        { name: 'Aster', key: 'aster', enabled: health.enable_aster, type: 'CEX' },
        { name: 'Symphony', key: 'symphony', enabled: health.enable_symphony, type: 'Monad Treasury' },
    ]
})

const mitProgress = computed(() => {
    if (!mitStatus.value) return { progress: 0, remaining: 5 }
    return {
        progress: mitStatus.value.activation_progress || 0,
        remaining: mitStatus.value.trades_until_activation || 5
    }
})

// Fetch all data
const fetchAllData = async () => {
    isLoading.value = true
    try {
        const [health, stats, platforms, mit] = await Promise.all([
            fetchHealth(),
            fetchPerformanceStats(),
            fetchPlatformStatus(),
            fetchMITStatus()
        ])
        systemHealth.value = health
        performanceStats.value = stats
        platformStatus.value = platforms
        mitStatus.value = mit
    } catch (error) {
        console.error('Failed to fetch dashboard data:', error)
    }
    isLoading.value = false
}

onMounted(() => {
    fetchAllData()
    setInterval(fetchAllData, 15000)
})
</script>

<template>
    <div class="dashboard">
        <!-- Header Stats -->
        <div class="stats-grid">
            <div class="stat-card glass-elevated">
                <div class="stat-icon" :class="parseFloat(totalPnl) >= 0 ? 'positive' : 'negative'">
                    <TrendingUp v-if="parseFloat(totalPnl) >= 0" :size="20" />
                    <TrendingDown v-else :size="20" />
                </div>
                <div class="stat-content">
                    <span class="stat-label font-mono">TOTAL PNL</span>
                    <span class="stat-value font-mono" :class="parseFloat(totalPnl) >= 0 ? 'text-success' : 'text-error'">
                        {{ parseFloat(totalPnl) >= 0 ? '+' : '' }}{{ totalPnl }}%
                    </span>
                </div>
            </div>

            <div class="stat-card glass-elevated">
                <div class="stat-icon brand">
                    <Activity :size="20" />
                </div>
                <div class="stat-content">
                    <span class="stat-label font-mono">WIN RATE</span>
                    <span class="stat-value font-mono">{{ winRate }}%</span>
                </div>
            </div>

            <div class="stat-card glass-elevated">
                <div class="stat-icon brand">
                    <Bot :size="20" />
                </div>
                <div class="stat-content">
                    <span class="stat-label font-mono">AI AGENTS</span>
                    <span class="stat-value font-mono">4 <span class="stat-sub">Active</span></span>
                </div>
            </div>

            <div class="stat-card glass-elevated">
                <div class="stat-icon brand">
                    <Server :size="20" />
                </div>
                <div class="stat-content">
                    <span class="stat-label font-mono">PLATFORMS</span>
                    <span class="stat-value font-mono">{{ platforms.filter(p => p.enabled).length }} <span class="stat-sub">Connected</span></span>
                </div>
            </div>
        </div>

        <!-- Main Grid -->
        <div class="main-grid">
            <!-- Platform Status -->
            <div class="panel glass">
                <div class="panel-header">
                    <h3 class="font-mono">PLATFORM STATUS</h3>
                    <span class="badge font-mono">DUAL ROUTER V2</span>
                </div>
                <div class="platform-list">
                    <div v-for="platform in platforms" :key="platform.key" class="platform-row">
                        <div class="platform-info">
                            <span class="platform-dot" :class="platform.key"></span>
                            <div class="platform-details">
                                <span class="platform-name font-mono">{{ platform.name }}</span>
                                <span class="platform-type">{{ platform.type }}</span>
                            </div>
                        </div>
                        <div class="platform-status">
                            <span class="status-badge" :class="platform.enabled ? 'active' : 'inactive'">
                                {{ platform.enabled ? 'ACTIVE' : 'DISABLED' }}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- AI Agent Swarm -->
            <div class="panel glass">
                <div class="panel-header">
                    <h3 class="font-mono">AI AGENT SWARM</h3>
                    <span class="badge font-mono">CONSENSUS ENGINE</span>
                </div>
                <div class="agent-grid">
                    <div class="agent-card">
                        <div class="agent-weight font-mono">35%</div>
                        <div class="agent-name font-mono">Quant Alpha</div>
                        <div class="agent-type">Technical Analysis</div>
                        <div class="agent-status active"></div>
                    </div>
                    <div class="agent-card">
                        <div class="agent-weight font-mono">25%</div>
                        <div class="agent-name font-mono">Risk Guard</div>
                        <div class="agent-type">Risk Management</div>
                        <div class="agent-status active"></div>
                    </div>
                    <div class="agent-card">
                        <div class="agent-weight font-mono">20%</div>
                        <div class="agent-name font-mono">Sentiment</div>
                        <div class="agent-type">Social Analysis</div>
                        <div class="agent-status active"></div>
                    </div>
                    <div class="agent-card">
                        <div class="agent-weight font-mono">20%</div>
                        <div class="agent-name font-mono">Degen Hunter</div>
                        <div class="agent-type">Momentum</div>
                        <div class="agent-status active"></div>
                    </div>
                </div>
            </div>

            <!-- Symphony Treasury -->
            <div class="panel glass symphony-panel">
                <div class="panel-header">
                    <h3 class="font-mono">SYMPHONY TREASURY</h3>
                    <span class="badge symphony font-mono">MONAD</span>
                </div>
                <div class="symphony-agents">
                    <div class="symphony-agent">
                        <div class="symphony-icon">💰</div>
                        <div class="symphony-info">
                            <span class="symphony-ticker font-mono">$MILF</span>
                            <span class="symphony-name">Treasury Agent</span>
                        </div>
                        <span class="symphony-status active font-mono">ACTIVE</span>
                    </div>
                    <div class="symphony-agent">
                        <div class="symphony-icon">🔥</div>
                        <div class="symphony-info">
                            <span class="symphony-ticker font-mono">$AGDG</span>
                            <span class="symphony-name">Degen Agent</span>
                        </div>
                        <span class="symphony-status active font-mono">ACTIVE</span>
                    </div>
                    <div class="symphony-agent">
                        <div class="symphony-icon">🏦</div>
                        <div class="symphony-info">
                            <span class="symphony-ticker font-mono">$MIT</span>
                            <span class="symphony-name">Implementation Treasury</span>
                        </div>
                        <span class="symphony-status pending font-mono">{{ mitProgress.remaining }}/5 TRADES</span>
                    </div>
                </div>
                <div class="mit-progress">
                    <span class="progress-label font-mono">MIT ACTIVATION</span>
                    <div class="progress-bar">
                        <div class="progress-fill" :style="{ width: (mitProgress.progress / 5 * 100) + '%' }"></div>
                    </div>
                </div>
            </div>

            <!-- Memory System -->
            <div class="panel glass">
                <div class="panel-header">
                    <h3 class="font-mono">MEMORY SYSTEM</h3>
                    <span class="badge font-mono">RAG ENGINE</span>
                </div>
                <div class="memory-stats">
                    <div class="memory-stat">
                        <Database :size="18" class="text-brand" />
                        <div class="memory-info">
                            <span class="memory-label">Vector Index</span>
                            <span class="memory-value font-mono">FAISS Active</span>
                        </div>
                    </div>
                    <div class="memory-stat">
                        <Zap :size="18" class="text-success" />
                        <div class="memory-info">
                            <span class="memory-label">Persistence</span>
                            <span class="memory-value font-mono">Firestore</span>
                        </div>
                    </div>
                    <div class="memory-stat">
                        <Server :size="18" class="text-purple" />
                        <div class="memory-info">
                            <span class="memory-label">WAL Status</span>
                            <span class="memory-value font-mono">Protected</span>
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

/* Stats Grid */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
}

.stat-card {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.25rem;
    border-radius: var(--radius-md);
}

.stat-icon {
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-sm);
}

.stat-icon.positive {
    background: var(--color-success-dim);
    color: var(--color-success);
}

.stat-icon.negative {
    background: var(--color-error-dim);
    color: var(--color-error);
}

.stat-icon.brand {
    background: var(--color-brand-dim);
    color: var(--color-brand);
}

.stat-content {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.stat-label {
    font-size: 0.625rem;
    color: var(--text-tertiary);
    letter-spacing: 0.08em;
}

.stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-primary);
}

.stat-sub {
    font-size: 0.75rem;
    color: var(--text-tertiary);
    font-weight: 400;
}

/* Main Grid */
.main-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
}

.panel {
    border-radius: var(--radius-md);
    padding: 1.25rem;
}

.panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
}

.panel-header h3 {
    font-size: 0.6875rem;
    color: var(--text-secondary);
    letter-spacing: 0.08em;
    margin: 0;
}

.badge {
    font-size: 0.5625rem;
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-xs);
    background: var(--color-brand-dim);
    color: var(--color-brand);
    letter-spacing: 0.05em;
}

.badge.symphony {
    background: var(--color-purple-dim);
    color: var(--color-purple);
}

/* Platform List */
.platform-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.platform-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.625rem;
    background: rgba(255, 255, 255, 0.02);
    border-radius: var(--radius-sm);
}

.platform-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.platform-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.platform-dot.hyperliquid { background: var(--platform-hyperliquid); box-shadow: 0 0 8px var(--platform-hyperliquid); }
.platform-dot.drift { background: var(--platform-drift); box-shadow: 0 0 8px var(--platform-drift); }
.platform-dot.aster { background: var(--platform-aster); box-shadow: 0 0 8px var(--platform-aster); }
.platform-dot.symphony { background: var(--platform-symphony); box-shadow: 0 0 8px var(--platform-symphony); }

.platform-details {
    display: flex;
    flex-direction: column;
}

.platform-name {
    font-size: 0.8125rem;
    font-weight: 600;
}

.platform-type {
    font-size: 0.6875rem;
    color: var(--text-tertiary);
}

.status-badge {
    font-family: var(--font-mono);
    font-size: 0.5625rem;
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-xs);
    font-weight: 600;
}

.status-badge.active {
    background: var(--color-success-dim);
    color: var(--color-success);
}

.status-badge.inactive {
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-tertiary);
}

/* Agent Grid */
.agent-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.75rem;
}

.agent-card {
    padding: 1rem;
    background: rgba(255, 255, 255, 0.02);
    border-radius: var(--radius-sm);
    position: relative;
}

.agent-weight {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--color-brand);
    margin-bottom: 0.5rem;
}

.agent-name {
    font-size: 0.75rem;
    font-weight: 600;
    margin-bottom: 0.125rem;
}

.agent-type {
    font-size: 0.625rem;
    color: var(--text-tertiary);
}

.agent-status {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    width: 6px;
    height: 6px;
    border-radius: 50%;
}

.agent-status.active {
    background: var(--color-success);
    box-shadow: 0 0 8px var(--color-success);
}

/* Symphony Panel */
.symphony-agents {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1rem;
}

.symphony-agent {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.625rem;
    background: rgba(255, 255, 255, 0.02);
    border-radius: var(--radius-sm);
}

.symphony-icon {
    font-size: 1.25rem;
}

.symphony-info {
    flex: 1;
    display: flex;
    flex-direction: column;
}

.symphony-ticker {
    font-size: 0.75rem;
    font-weight: 700;
}

.symphony-name {
    font-size: 0.625rem;
    color: var(--text-tertiary);
}

.symphony-status {
    font-size: 0.5625rem;
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-xs);
    font-weight: 600;
}

.symphony-status.active {
    background: var(--color-success-dim);
    color: var(--color-success);
}

.symphony-status.pending {
    background: var(--color-warning-dim);
    color: var(--color-warning);
}

.mit-progress {
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-subtle);
}

.progress-label {
    font-size: 0.5625rem;
    color: var(--text-tertiary);
    letter-spacing: 0.08em;
    display: block;
    margin-bottom: 0.5rem;
}

.progress-bar {
    height: 6px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 3px;
    overflow: hidden;
}

.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--color-purple) 0%, var(--color-brand) 100%);
    border-radius: 3px;
    transition: width 0.5s ease;
}

/* Memory Stats */
.memory-stats {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.memory-stat {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.625rem;
    background: rgba(255, 255, 255, 0.02);
    border-radius: var(--radius-sm);
}

.memory-info {
    display: flex;
    flex-direction: column;
}

.memory-label {
    font-size: 0.625rem;
    color: var(--text-tertiary);
}

.memory-value {
    font-size: 0.75rem;
    font-weight: 600;
}
</style>

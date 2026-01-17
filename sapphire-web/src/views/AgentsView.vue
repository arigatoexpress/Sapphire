<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Bot, Brain, Shield, TrendingUp, Flame, Zap, RefreshCw } from 'lucide-vue-next'
import { fetchAgents, fetchHealth } from '../api/client'

interface Agent {
    id: string
    name: string
    type: string
    weight: number
    role: string
    platform: 'all' | 'hyperliquid' | 'drift' | 'aster' | 'symphony'
    status: 'active' | 'inactive' | 'pending'
    confidence: number
    lastSignal: string
    icon: any
}

const agents = ref<Agent[]>([
    {
        id: 'quant-alpha',
        name: 'Quant Alpha',
        type: 'Technical Analysis',
        weight: 35,
        role: 'Primary technical signals using multi-timeframe analysis',
        platform: 'all',
        status: 'active',
        confidence: 0.87,
        lastSignal: 'LONG BTC',
        icon: Brain
    },
    {
        id: 'risk-guard',
        name: 'Risk Guard',
        type: 'Risk Management',
        weight: 25,
        role: 'Portfolio protection and position sizing',
        platform: 'all',
        status: 'active',
        confidence: 0.92,
        lastSignal: 'REDUCE SIZE',
        icon: Shield
    },
    {
        id: 'sentiment-sage',
        name: 'Sentiment Sage',
        type: 'Social Analysis',
        weight: 20,
        role: 'Market sentiment from social and news data',
        platform: 'all',
        status: 'active',
        confidence: 0.71,
        lastSignal: 'NEUTRAL',
        icon: TrendingUp
    },
    {
        id: 'degen-hunter',
        name: 'Degen Hunter',
        type: 'Momentum Trading',
        weight: 20,
        role: 'High-conviction momentum plays and breakouts',
        platform: 'all',
        status: 'active',
        confidence: 0.68,
        lastSignal: 'LONG SOL',
        icon: Flame
    }
])

const symphonyAgents = ref([
    { ticker: '$MILF', name: 'Treasury Agent', status: 'active', trades: 127 },
    { ticker: '$AGDG', name: 'Degen Agent', status: 'active', trades: 89 },
    { ticker: '$MIT', name: 'Implementation Treasury', status: 'pending', trades: 0 }
])

const consensusThreshold = ref(0.65)
const swarmCohesion = ref(94)
const isRefreshing = ref(false)

const refreshData = async () => {
    isRefreshing.value = true
    // Simulate refresh
    await new Promise(resolve => setTimeout(resolve, 1000))
    isRefreshing.value = false
}

onMounted(() => {
    refreshData()
})

const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'high'
    if (confidence >= 0.6) return 'medium'
    return 'low'
}
</script>

<template>
    <div class="view-container">
        <div class="header">
            <div class="header-left">
                <h2 class="font-mono text-gradient">AI AGENT SWARM</h2>
                <p class="subtitle">Weighted Consensus Trading Engine</p>
            </div>
            <div class="header-right">
                <button class="btn-refresh" @click="refreshData" :class="{ spinning: isRefreshing }">
                    <RefreshCw :size="16" />
                </button>
                <div class="cohesion-badge font-mono">
                    <Zap :size="14" class="text-success" />
                    COHESION: {{ swarmCohesion }}%
                </div>
            </div>
        </div>

        <!-- Consensus Diagram -->
        <div class="consensus-panel glass">
            <div class="consensus-header">
                <h3 class="font-mono">WEIGHTED CONSENSUS ENGINE</h3>
                <span class="threshold font-mono">Threshold: {{ consensusThreshold * 100 }}%</span>
            </div>
            <div class="consensus-visual">
                <div class="agents-circle">
                    <div v-for="agent in agents" :key="agent.id"
                         class="agent-node"
                         :class="agent.id"
                         :style="{ '--weight': agent.weight }">
                        <div class="node-weight font-mono">{{ agent.weight }}%</div>
                        <div class="node-name font-mono">{{ agent.name.split(' ')[0] }}</div>
                    </div>
                    <div class="consensus-center">
                        <Zap :size="24" class="text-brand" />
                        <span class="font-mono">CONSENSUS</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Agent Cards -->
        <div class="agents-grid">
            <div v-for="agent in agents" :key="agent.id" class="agent-card glass">
                <div class="card-header">
                    <div class="agent-icon" :class="agent.id">
                        <component :is="agent.icon" :size="20" />
                    </div>
                    <div class="agent-identity">
                        <span class="agent-name font-mono">{{ agent.name }}</span>
                        <span class="agent-type">{{ agent.type }}</span>
                    </div>
                    <div class="weight-badge font-mono">{{ agent.weight }}%</div>
                </div>

                <p class="agent-role">{{ agent.role }}</p>

                <div class="agent-metrics">
                    <div class="metric">
                        <span class="metric-label">Confidence</span>
                        <div class="confidence-bar">
                            <div class="confidence-fill" 
                                 :class="getConfidenceColor(agent.confidence)"
                                 :style="{ width: (agent.confidence * 100) + '%' }"></div>
                        </div>
                        <span class="metric-value font-mono">{{ Math.round(agent.confidence * 100) }}%</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Last Signal</span>
                        <span class="signal-badge font-mono" :class="agent.lastSignal.includes('LONG') ? 'long' : 'neutral'">
                            {{ agent.lastSignal }}
                        </span>
                    </div>
                </div>

                <div class="card-footer">
                    <div class="status-indicator" :class="agent.status">
                        <span class="dot"></span>
                        <span class="font-mono">{{ agent.status.toUpperCase() }}</span>
                    </div>
                    <span class="platform-tag font-mono">{{ agent.platform.toUpperCase() }}</span>
                </div>
            </div>
        </div>

        <!-- Symphony Agents -->
        <div class="symphony-section">
            <h3 class="section-title font-mono">SYMPHONY TREASURY AGENTS</h3>
            <div class="symphony-grid">
                <div v-for="agent in symphonyAgents" :key="agent.ticker" class="symphony-card glass">
                    <div class="symphony-ticker font-mono">{{ agent.ticker }}</div>
                    <div class="symphony-name">{{ agent.name }}</div>
                    <div class="symphony-stats">
                        <span class="status-pill font-mono" :class="agent.status">{{ agent.status.toUpperCase() }}</span>
                        <span class="trade-count font-mono">{{ agent.trades }} trades</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.view-container {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.header-left h2 {
    font-size: 1.25rem;
    margin: 0 0 0.25rem 0;
}

.subtitle {
    font-size: 0.8125rem;
    color: var(--text-tertiary);
    margin: 0;
}

.header-right {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.btn-refresh {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
}

.btn-refresh:hover {
    border-color: var(--color-brand);
    color: var(--color-brand);
}

.btn-refresh.spinning svg {
    animation: spin 1s linear infinite;
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.cohesion-badge {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: var(--color-success-dim);
    border: 1px solid rgba(0, 255, 136, 0.2);
    border-radius: 20px;
    color: var(--color-success);
    font-size: 0.75rem;
}

/* Consensus Panel */
.consensus-panel {
    padding: 1.5rem;
    border-radius: var(--radius-md);
}

.consensus-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
}

.consensus-header h3 {
    font-size: 0.75rem;
    color: var(--text-secondary);
    letter-spacing: 0.08em;
    margin: 0;
}

.threshold {
    font-size: 0.6875rem;
    color: var(--color-brand);
}

.consensus-visual {
    display: flex;
    justify-content: center;
    padding: 2rem 0;
}

.agents-circle {
    position: relative;
    width: 300px;
    height: 200px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.agent-node {
    position: absolute;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
}

.agent-node.quant-alpha { left: 10%; top: 20%; }
.agent-node.risk-guard { right: 10%; top: 20%; }
.agent-node.sentiment-sage { left: 10%; bottom: 20%; }
.agent-node.degen-hunter { right: 10%; bottom: 20%; }

.node-weight {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--color-brand);
}

.node-name {
    font-size: 0.625rem;
    color: var(--text-tertiary);
}

.consensus-center {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    padding: 1.5rem;
    background: var(--color-brand-dim);
    border-radius: 50%;
    border: 2px solid rgba(0, 212, 255, 0.3);
}

.consensus-center span {
    font-size: 0.5625rem;
    letter-spacing: 0.1em;
}

/* Agent Cards */
.agents-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
}

.agent-card {
    padding: 1.25rem;
    border-radius: var(--radius-md);
}

.card-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
}

.agent-icon {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-sm);
}

.agent-icon.quant-alpha { background: var(--color-brand-dim); color: var(--color-brand); }
.agent-icon.risk-guard { background: var(--color-success-dim); color: var(--color-success); }
.agent-icon.sentiment-sage { background: var(--color-warning-dim); color: var(--color-warning); }
.agent-icon.degen-hunter { background: var(--color-error-dim); color: var(--color-error); }

.agent-identity {
    flex: 1;
    display: flex;
    flex-direction: column;
}

.agent-name {
    font-weight: 700;
    font-size: 0.875rem;
}

.agent-type {
    font-size: 0.6875rem;
    color: var(--text-tertiary);
}

.weight-badge {
    font-size: 1rem;
    font-weight: 700;
    color: var(--color-brand);
}

.agent-role {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin: 0 0 1rem 0;
    line-height: 1.4;
}

.agent-metrics {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1rem;
}

.metric {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.metric-label {
    font-size: 0.6875rem;
    color: var(--text-tertiary);
    width: 70px;
}

.confidence-bar {
    flex: 1;
    height: 4px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 2px;
    overflow: hidden;
}

.confidence-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s;
}

.confidence-fill.high { background: var(--color-success); }
.confidence-fill.medium { background: var(--color-warning); }
.confidence-fill.low { background: var(--color-error); }

.metric-value {
    font-size: 0.6875rem;
    color: var(--text-primary);
    width: 35px;
    text-align: right;
}

.signal-badge {
    font-size: 0.625rem;
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-xs);
}

.signal-badge.long {
    background: var(--color-success-dim);
    color: var(--color-success);
}

.signal-badge.neutral {
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-tertiary);
}

.card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-subtle);
}

.status-indicator {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.625rem;
}

.status-indicator .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
}

.status-indicator.active { color: var(--color-success); }
.status-indicator.active .dot { background: var(--color-success); box-shadow: 0 0 8px var(--color-success); }

.platform-tag {
    font-size: 0.5625rem;
    color: var(--text-tertiary);
}

/* Symphony Section */
.symphony-section {
    margin-top: 1rem;
}

.section-title {
    font-size: 0.75rem;
    color: var(--text-secondary);
    letter-spacing: 0.08em;
    margin: 0 0 1rem 0;
}

.symphony-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
}

.symphony-card {
    padding: 1.25rem;
    border-radius: var(--radius-md);
    text-align: center;
}

.symphony-ticker {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--color-purple);
    margin-bottom: 0.25rem;
}

.symphony-name {
    font-size: 0.75rem;
    color: var(--text-tertiary);
    margin-bottom: 1rem;
}

.symphony-stats {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.status-pill {
    font-size: 0.5625rem;
    padding: 0.25rem 0.5rem;
    border-radius: var(--radius-xs);
}

.status-pill.active {
    background: var(--color-success-dim);
    color: var(--color-success);
}

.status-pill.pending {
    background: var(--color-warning-dim);
    color: var(--color-warning);
}

.trade-count {
    font-size: 0.625rem;
    color: var(--text-tertiary);
}
</style>

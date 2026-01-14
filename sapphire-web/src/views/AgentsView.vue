<script setup lang="ts">
import { ref } from 'vue'
import { Bot } from 'lucide-vue-next'

const agents = ref([
    { id: 'quant-alpha', name: 'Quant Alpha', type: 'Technical', status: 'active', confidence: 0.85, system: 'aster' },
    { id: 'sentiment-sage', name: 'Sentiment Sage', type: 'Psycho-history', status: 'active', confidence: 0.72, system: 'aster' },
    { id: 'drift-trader', name: 'Drift Trader', type: 'DEX Specialist', status: 'active', confidence: 0.91, system: 'drift' },
    { id: 'monad-treasury', name: 'MIT Agent', type: 'Treasury Mgmt', status: 'active', confidence: 0.94, system: 'symphony' },
    { id: 'hyper-trader', name: 'HyperTrader', type: 'HFT', status: 'active', confidence: 0.65, system: 'hyperliquid' },
])
</script>

<template>
    <div class="view-container">
        <div class="header">
            <h2 class="font-mono text-gradient">AI SWARM ROSTER</h2>
            <div class="status-badge font-mono">
                <span class="dot active"></span>
                SWARM COHESION: 94%
            </div>
        </div>

        <div class="grid agents-grid">
            <div v-for="agent in agents" :key="agent.id" class="agent-card glass">
                <div class="card-header">
                    <div class="icon-wrapper">
                        <Bot :size="24" class="text-brand" />
                    </div>
                    <div class="agent-identity">
                        <span class="name font-mono">{{ agent.name }}</span>
                        <span class="type">{{ agent.type }}</span>
                    </div>
                    <div :class="['system-badge', agent.system]">{{ agent.system.toUpperCase() }}</div>
                </div>

                <div class="metrics">
                    <div class="metric">
                        <span class="label">STATUS</span>
                        <span class="value text-success">ACTIVE</span>
                    </div>
                    <div class="metric">
                        <span class="label">CONFIDENCE</span>
                        <div class="bar-container">
                            <div class="bar" :style="{ width: (agent.confidence * 100) + '%' }"></div>
                        </div>
                    </div>
                </div>

                <div class="actions">
                    <button class="btn-inspect font-mono">INSPECT MEMORY</button>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.view-container {
    display: flex;
    flex-direction: column;
    gap: 2rem;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.status-badge {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: rgba(0, 240, 255, 0.1);
    border: 1px solid rgba(0, 240, 255, 0.2);
    border-radius: 20px;
    color: var(--color-brand);
    font-size: 0.8rem;
}

.dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-brand);
    box-shadow: 0 0 8px var(--color-brand);
}

.agents-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.5rem;
}

.agent-card {
    padding: 1.5rem;
    border-radius: var(--radius-md);
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    transition: transform 0.2s, background 0.2s;
}

.agent-card:hover {
    transform: translateY(-2px);
    background: rgba(255, 255, 255, 0.05);
}

.card-header {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.icon-wrapper {
    padding: 0.75rem;
    background: rgba(255,255,255,0.03);
    border-radius: 8px;
}

.agent-identity {
    flex: 1;
    display: flex;
    flex-direction: column;
}

.name {
    font-weight: 700;
    color: var(--text-primary);
}

.type {
    font-size: 0.75rem;
    color: var(--text-tertiary);
}

.system-badge {
    font-size: 0.65rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-weight: 700;
    letter-spacing: 0.05em;
}

.system-badge.aster { background: rgba(0, 240, 255, 0.1); color: var(--color-brand); }
.system-badge.drift { background: rgba(255, 215, 0, 0.1); color: var(--color-warning); }
.system-badge.symphony { background: rgba(176, 38, 255, 0.1); color: var(--color-purple); }
.system-badge.hyperliquid { background: rgba(57, 255, 20, 0.1); color: var(--color-success); }

.metrics {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.metric {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.8rem;
}

.label { color: var(--text-secondary); }

.bar-container {
    width: 100px;
    height: 4px;
    background: rgba(255,255,255,0.1);
    border-radius: 2px;
    overflow: hidden;
}

.bar {
    height: 100%;
    background: var(--color-success);
}

.btn-inspect {
    width: 100%;
    padding: 0.75rem;
    background: transparent;
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 0.75rem;
    transition: all 0.2s;
}

.btn-inspect:hover {
    border-color: var(--text-primary);
    color: var(--text-primary);
}
</style>

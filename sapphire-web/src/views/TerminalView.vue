<script setup lang="ts">
import { ref } from 'vue'

const logs = ref([
    { timestamp: '10:42:01', level: 'INFO', source: 'ORCHESTRATOR', message: 'System startup initialized' },
    { timestamp: '10:42:02', level: 'INFO', source: 'SWARM', message: 'Loaded 10 agents from config' },
    { timestamp: '10:42:05', level: 'WARN', source: 'ROUTER', message: 'Hyperliquid connection latency > 200ms' },
    { timestamp: '10:42:15', level: 'INFO', source: 'AGENT:QUANT', message: 'Analyzing BTC-USDC (Confidence: 0.85)' },
    { timestamp: '10:42:18', level: 'SUCCESS', source: 'EXECUTION', message: 'Order Filled: BUY 0.5 BTC @ 98,450' },
])

const glossary: Record<string, string> = {
    INFO: 'text-secondary',
    WARN: 'text-warning',
    ERROR: 'text-error',
    SUCCESS: 'text-success'
}
</script>

<template>
    <div class="terminal-container glass">
        <div class="panel-header">
            <h3 class="font-mono">SYSTEM LOGS</h3>
            <div class="controls">
                <button class="btn-clear font-mono">CLEAR</button>
            </div>
        </div>
        <div class="logs-content font-mono">
            <div v-for="(log, i) in logs" :key="i" class="log-line">
                <span class="timestamp">{{ log.timestamp }}</span>
                <span :class="['level', glossary[log.level] || 'text-secondary']">{{ log.level }}</span>
                <span class="source">[{{ log.source }}]</span>
                <span class="message">{{ log.message }}</span>
            </div>
            <div class="cursor-line">
                <span class="prompt">></span>
                <span class="cursor">_</span>
            </div>
        </div>
    </div>
</template>

<style scoped>
.terminal-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    border-radius: var(--radius-md);
    overflow: hidden;
}

.panel-header {
    padding: 1rem;
    border-bottom: var(--glass-border);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.logs-content {
    flex: 1;
    padding: 1rem;
    overflow-y: auto;
    font-size: 0.85rem;
    background: rgba(0,0,0,0.3);
}

.log-line {
    display: flex;
    gap: 1rem;
    margin-bottom: 0.5rem;
}

.timestamp { color: var(--text-tertiary); }
.source { color: var(--color-brand); }
.message { color: var(--text-primary); }

.text-warning { color: var(--color-warning); }
.text-error { color: var(--color-error); }
.text-success { color: var(--color-success); }
.text-secondary { color: var(--text-secondary); }

.cursor {
    animation: blink 1s step-end infinite;
}

@keyframes blink {
    50% { opacity: 0; }
}
</style>

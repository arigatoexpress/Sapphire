<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchSystemLogs, fetchPlatformLogs } from '@/api/client'

interface LogEntry {
    timestamp: string
    level: string
    source: string
    message: string
}

const logs = ref<LogEntry[]>([])
const isLoading = ref(true)
const autoRefresh = ref(true)
const selectedPlatform = ref('all')
let refreshInterval: ReturnType<typeof setInterval> | null = null

const platforms = ['all', 'aster', 'hyperliquid', 'drift', 'symphony', 'jupiter', 'lighter']

const glossary: Record<string, string> = {
    INFO: 'text-secondary',
    WARN: 'text-warning',
    ERROR: 'text-error',
    SUCCESS: 'text-success',
    DEBUG: 'text-debug'
}

const formatTimestamp = (ts: string | number): string => {
    if (!ts) return new Date().toLocaleTimeString('en-US', { hour12: false })
    const date = typeof ts === 'number' ? new Date(ts) : new Date(ts)
    return date.toLocaleTimeString('en-US', { hour12: false })
}

const parseLogLevel = (message: string): string => {
    if (message.includes('ERROR') || message.includes('Failed')) return 'ERROR'
    if (message.includes('WARN') || message.includes('Warning')) return 'WARN'
    if (message.includes('SUCCESS') || message.includes('FILLED')) return 'SUCCESS'
    return 'INFO'
}

const parseLogSource = (message: string): string => {
    const sourceMatch = message.match(/\[([A-Z_]+)\]/)
    if (sourceMatch) return sourceMatch[1]
    if (message.toLowerCase().includes('aster')) return 'ASTER'
    if (message.toLowerCase().includes('hyperliquid')) return 'HYPERLIQUID'
    if (message.toLowerCase().includes('drift')) return 'DRIFT'
    if (message.toLowerCase().includes('symphony')) return 'SYMPHONY'
    if (message.toLowerCase().includes('jupiter')) return 'JUPITER'
    if (message.toLowerCase().includes('router')) return 'ROUTER'
    if (message.toLowerCase().includes('agent')) return 'AGENT'
    return 'SYSTEM'
}

const fetchLogs = async () => {
    try {
        let data: any[]
        if (selectedPlatform.value === 'all') {
            data = await fetchSystemLogs()
        } else {
            data = await fetchPlatformLogs(selectedPlatform.value, 100)
        }

        if (Array.isArray(data) && data.length > 0) {
            logs.value = data.map((log: any) => ({
                timestamp: formatTimestamp(log.timestamp || log.time || log.created),
                level: log.level || parseLogLevel(log.message || log.msg || ''),
                source: log.source || parseLogSource(log.message || log.msg || ''),
                message: log.message || log.msg || JSON.stringify(log)
            })).slice(-100)
        } else if (logs.value.length === 0) {
            logs.value = [{
                timestamp: formatTimestamp(Date.now()),
                level: 'INFO',
                source: 'SYSTEM',
                message: 'Waiting for system logs...'
            }]
        }
    } catch (error) {
        if (logs.value.length === 0) {
            logs.value = [{
                timestamp: formatTimestamp(Date.now()),
                level: 'WARN',
                source: 'FRONTEND',
                message: 'Connecting to log stream...'
            }]
        }
    } finally {
        isLoading.value = false
    }
}

const clearLogs = () => {
    logs.value = [{
        timestamp: formatTimestamp(Date.now()),
        level: 'INFO',
        source: 'SYSTEM',
        message: 'Logs cleared by user'
    }]
}

const toggleAutoRefresh = () => {
    autoRefresh.value = !autoRefresh.value
    if (autoRefresh.value) {
        startAutoRefresh()
    } else {
        stopAutoRefresh()
    }
}

const startAutoRefresh = () => {
    if (refreshInterval) clearInterval(refreshInterval)
    refreshInterval = setInterval(fetchLogs, 3000)
}

const stopAutoRefresh = () => {
    if (refreshInterval) {
        clearInterval(refreshInterval)
        refreshInterval = null
    }
}

const changePlatform = (platform: string) => {
    selectedPlatform.value = platform
    logs.value = []
    isLoading.value = true
    fetchLogs()
}

onMounted(() => {
    fetchLogs()
    if (autoRefresh.value) startAutoRefresh()
})

onUnmounted(() => {
    stopAutoRefresh()
})
</script>

<template>
    <div class="terminal-container glass">
        <div class="panel-header">
            <div class="header-left">
                <h3 class="font-mono">SYSTEM LOGS</h3>
                <div class="platform-tabs">
                    <button
                        v-for="p in platforms"
                        :key="p"
                        :class="['tab-btn', { active: selectedPlatform === p }]"
                        @click="changePlatform(p)"
                    >
                        {{ p.toUpperCase() }}
                    </button>
                </div>
            </div>
            <div class="controls">
                <button
                    :class="['btn-refresh', { active: autoRefresh }]"
                    @click="toggleAutoRefresh"
                >
                    {{ autoRefresh ? 'LIVE' : 'PAUSED' }}
                </button>
                <button class="btn-clear font-mono" @click="clearLogs">CLEAR</button>
            </div>
        </div>
        <div class="logs-content font-mono">
            <div v-if="isLoading" class="loading">Loading logs...</div>
            <template v-else>
                <div v-for="(log, i) in logs" :key="i" class="log-line">
                    <span class="timestamp">{{ log.timestamp }}</span>
                    <span :class="['level', glossary[log.level] || 'text-secondary']">{{ log.level }}</span>
                    <span class="source">[{{ log.source }}]</span>
                    <span class="message">{{ log.message }}</span>
                </div>
            </template>
            <div class="cursor-line">
                <span class="prompt">></span>
                <span class="cursor">_</span>
            </div>
        </div>
        <div class="panel-footer">
            <span class="log-count font-mono">{{ logs.length }} entries</span>
            <span :class="['status', { live: autoRefresh }]">{{ autoRefresh ? 'LIVE' : 'PAUSED' }}</span>
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
    flex-wrap: wrap;
    gap: 0.5rem;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
}

.platform-tabs {
    display: flex;
    gap: 0.25rem;
}

.tab-btn {
    padding: 0.25rem 0.5rem;
    font-size: 0.7rem;
    font-family: var(--font-mono);
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 4px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
}

.tab-btn:hover {
    background: rgba(255,255,255,0.1);
}

.tab-btn.active {
    background: var(--color-brand);
    color: white;
    border-color: var(--color-brand);
}

.controls {
    display: flex;
    gap: 0.5rem;
}

.btn-refresh {
    padding: 0.25rem 0.75rem;
    font-size: 0.75rem;
    font-family: var(--font-mono);
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 4px;
    color: var(--text-secondary);
    cursor: pointer;
}

.btn-refresh.active {
    background: var(--color-success);
    color: white;
    border-color: var(--color-success);
}

.btn-clear {
    padding: 0.25rem 0.75rem;
    font-size: 0.75rem;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 4px;
    color: var(--text-secondary);
    cursor: pointer;
}

.btn-clear:hover {
    background: var(--color-error);
    color: white;
}

.logs-content {
    flex: 1;
    padding: 1rem;
    overflow-y: auto;
    font-size: 0.85rem;
    background: rgba(0,0,0,0.3);
}

.loading {
    color: var(--text-tertiary);
    text-align: center;
    padding: 2rem;
}

.log-line {
    display: flex;
    gap: 1rem;
    margin-bottom: 0.5rem;
    line-height: 1.4;
}

.timestamp {
    color: var(--text-tertiary);
    min-width: 70px;
}

.level {
    min-width: 60px;
    font-weight: 600;
}

.source {
    color: var(--color-brand);
    min-width: 100px;
}

.message {
    color: var(--text-primary);
    flex: 1;
    word-break: break-word;
}

.text-warning { color: var(--color-warning); }
.text-error { color: var(--color-error); }
.text-success { color: var(--color-success); }
.text-secondary { color: var(--text-secondary); }
.text-debug { color: var(--text-tertiary); }

.cursor-line {
    margin-top: 0.5rem;
}

.cursor {
    animation: blink 1s step-end infinite;
}

@keyframes blink {
    50% { opacity: 0; }
}

.panel-footer {
    padding: 0.5rem 1rem;
    border-top: var(--glass-border);
    display: flex;
    justify-content: space-between;
    font-size: 0.75rem;
    color: var(--text-tertiary);
}

.status {
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    background: rgba(255,255,255,0.05);
}

.status.live {
    background: var(--color-success);
    color: white;
}

.log-count {
    font-family: var(--font-mono);
}
</style>

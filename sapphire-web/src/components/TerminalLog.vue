<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { SystemLogEntry } from '../api/client'

const props = withDefaults(
    defineProps<{
        logs?: SystemLogEntry[]
        maxVisible?: number
        collapsed?: boolean
    }>(),
    {
        logs: () => [],
        maxVisible: 30,
        collapsed: false,
    },
)

const emit = defineEmits<{
    (e: 'toggle'): void
}>()

const scrollContainer = ref<HTMLElement | null>(null)

const visibleLogs = computed(() => {
    const sorted = [...props.logs]
        .sort((a, b) => Number(a.timestamp || 0) - Number(b.timestamp || 0))
        .slice(-props.maxVisible)
    return sorted
})

const formatTime = (epoch: number) => {
    if (!epoch || !Number.isFinite(epoch)) return '00:00:00'
    const ms = epoch < 1e12 ? epoch * 1000 : epoch
    const d = new Date(ms)
    return d.toISOString().slice(11, 19)
}

const levelClass = (level: string) => {
    const l = String(level || '').toLowerCase()
    if (l === 'error' || l === 'critical') return 'log-error'
    if (l === 'warning' || l === 'warn') return 'log-warn'
    return 'log-info'
}

const levelTag = (level: string) => {
    const l = String(level || '').toLowerCase()
    if (l === 'error' || l === 'critical') return 'ERR'
    if (l === 'warning' || l === 'warn') return 'WRN'
    return 'INF'
}

const scrollToBottom = async () => {
    await nextTick()
    if (scrollContainer.value) {
        scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    }
}

watch(() => props.logs.length, scrollToBottom)

onMounted(scrollToBottom)
</script>

<template>
    <div class="terminal" :class="{ collapsed: props.collapsed }">
        <header class="terminal-header" @click="emit('toggle')">
            <span class="terminal-title">
                <span class="terminal-prompt">&gt;</span>
                SYSTEM LOG
            </span>
            <span class="terminal-meta">
                {{ visibleLogs.length }} entries
                <span class="toggle-hint">{{ props.collapsed ? '[EXPAND]' : '[COLLAPSE]' }}</span>
            </span>
        </header>
        <div v-if="!props.collapsed" ref="scrollContainer" class="terminal-body">
            <div
                v-for="(entry, idx) in visibleLogs"
                :key="`${entry.timestamp}-${idx}`"
                class="log-line"
                :class="levelClass(entry.level)"
            >
                <span class="log-time">[{{ formatTime(entry.timestamp) }}]</span>
                <span class="log-level">[{{ levelTag(entry.level) }}]</span>
                <span class="log-msg">{{ entry.message }}</span>
            </div>
            <div v-if="!visibleLogs.length" class="log-line log-info">
                <span class="log-time">[--:--:--]</span>
                <span class="log-level">[SYS]</span>
                <span class="log-msg">Awaiting telemetry stream...</span>
            </div>
            <div class="cursor-line">
                <span class="cursor-prompt">&gt;</span>
                <span class="cursor-block"></span>
            </div>
        </div>
    </div>
</template>

<style scoped>
.terminal {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    background: rgba(5, 10, 5, 0.85);
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.terminal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0.7rem;
    border-bottom: 1px solid var(--border-subtle);
    background: rgba(10, 20, 10, 0.5);
    cursor: pointer;
    user-select: none;
}

.terminal-header:hover {
    background: rgba(15, 30, 15, 0.5);
}

.terminal-title {
    font-size: 0.76rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-primary);
}

.terminal-prompt {
    color: var(--color-terminal);
    margin-right: 0.3rem;
    text-shadow: 0 0 8px rgba(32, 194, 14, 0.5);
}

.terminal-meta {
    font-size: 0.68rem;
    color: var(--text-tertiary);
    letter-spacing: 0.04em;
}

.toggle-hint {
    margin-left: 0.5rem;
    color: var(--text-secondary);
}

.terminal-body {
    max-height: 200px;
    overflow-y: auto;
    padding: 0.5rem 0.7rem;
    font-size: 0.78rem;
    line-height: 1.6;
}

.log-line {
    display: flex;
    gap: 0.4rem;
    white-space: nowrap;
    overflow: hidden;
}

.log-time {
    color: var(--text-tertiary);
    flex-shrink: 0;
}

.log-level {
    flex-shrink: 0;
    font-weight: 500;
}

.log-msg {
    overflow: hidden;
    text-overflow: ellipsis;
}

.log-info .log-level { color: var(--color-terminal); }
.log-info .log-msg { color: var(--text-secondary); }

.log-warn .log-level { color: var(--color-warning); }
.log-warn .log-msg { color: rgba(255, 176, 0, 0.7); }

.log-error .log-level { color: var(--color-error); }
.log-error .log-msg { color: rgba(255, 68, 68, 0.8); }

.cursor-line {
    display: flex;
    align-items: center;
    gap: 0.2rem;
    margin-top: 0.15rem;
}

.cursor-prompt {
    color: var(--color-terminal);
    text-shadow: 0 0 6px rgba(32, 194, 14, 0.5);
}

.cursor-block {
    width: 7px;
    height: 13px;
    background: var(--color-terminal);
    animation: terminalBlink 1s step-end infinite;
    box-shadow: 0 0 4px rgba(32, 194, 14, 0.5);
}

.collapsed .terminal-body {
    display: none;
}
</style>

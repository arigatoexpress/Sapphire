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

const levelTagColor: Record<string, string> = {
    'log-info': 'text-terminal',
    'log-warn': 'text-warning',
    'log-error': 'text-error',
}

const levelMsgColor: Record<string, string> = {
    'log-info': 'text-text-secondary',
    'log-warn': 'text-[rgba(255,176,0,0.7)]',
    'log-error': 'text-[rgba(255,68,68,0.8)]',
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
    <div class="flex flex-col overflow-hidden rounded-md border border-border-subtle bg-[rgba(5,10,5,0.85)]">
        <!-- Header -->
        <header
            class="flex cursor-pointer select-none items-center justify-between border-b border-border-subtle bg-[rgba(10,20,10,0.5)] px-3 py-1.5 transition-colors hover:bg-[rgba(15,30,15,0.5)]"
            @click="emit('toggle')"
        >
            <span class="font-mono text-xs uppercase tracking-widest text-text-primary">
                <span class="mr-1 text-terminal glow" aria-hidden="true">&gt;</span>
                SYSTEM LOG
            </span>
            <span class="font-mono text-[0.68rem] tracking-wide text-text-tertiary">
                {{ visibleLogs.length }} entries
                <span class="ml-2 text-text-secondary">{{ props.collapsed ? '[EXPAND]' : '[COLLAPSE]' }}</span>
            </span>
        </header>

        <!-- Body -->
        <div
            v-if="!props.collapsed"
            ref="scrollContainer"
            class="max-h-[200px] overflow-y-auto px-3 py-2 font-mono text-[0.78rem] leading-relaxed"
        >
            <div
                v-for="(entry, idx) in visibleLogs"
                :key="`${entry.timestamp}-${idx}`"
                class="flex gap-1.5 overflow-hidden whitespace-nowrap"
            >
                <span class="shrink-0 text-text-tertiary">[{{ formatTime(entry.timestamp) }}]</span>
                <span :class="['shrink-0 font-medium', levelTagColor[levelClass(entry.level)]]">
                    [{{ levelTag(entry.level) }}]
                </span>
                <span :class="['truncate', levelMsgColor[levelClass(entry.level)]]">
                    {{ entry.message }}
                </span>
            </div>

            <div v-if="!visibleLogs.length" class="flex gap-1.5 overflow-hidden whitespace-nowrap">
                <span class="shrink-0 text-text-tertiary">[--:--:--]</span>
                <span class="shrink-0 font-medium text-terminal">[SYS]</span>
                <span class="truncate text-text-secondary">Awaiting telemetry stream...</span>
            </div>

            <!-- Blinking cursor -->
            <div class="mt-0.5 flex items-center gap-0.5">
                <span class="text-terminal glow" aria-hidden="true">&gt;</span>
                <span class="terminal-cursor" />
            </div>
        </div>
    </div>
</template>

<style scoped>
.terminal-cursor {
    width: 7px;
    height: 13px;
    background: var(--color-terminal);
    animation: terminalBlink 1s step-end infinite;
    box-shadow: 0 0 4px rgba(32, 194, 14, 0.5);
}
</style>

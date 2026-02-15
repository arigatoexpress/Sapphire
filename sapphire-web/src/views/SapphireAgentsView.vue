<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
    connectionHealth,
    fetchControlStatus,
    fetchPerformanceStats,
    fetchSystemLogs,
    type ControlStatusResponse,
    type PerformanceStatsResponse,
    type SystemLogEntry,
} from '../api/client'

const loading = ref(true)
const control = ref<ControlStatusResponse | null>(null)
const performance = ref<PerformanceStatsResponse | null>(null)
const recentOps = ref<SystemLogEntry[]>([])
const nowEpoch = ref(Date.now())
const lastSyncEpoch = ref(0)
const fetchError = ref('')

let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const dataAge = computed(() => {
    if (!lastSyncEpoch.value) return null
    return Math.floor((Date.now() - lastSyncEpoch.value) / 1000)
})
const isStale = computed(() => (dataAge.value ?? 999) > 30)

/* ── Agent definitions ── */
interface AgentDef {
    id: string
    name: string
    emoji: string
    theme: string
    role: string
    colorClass: string
    dotClass: string
    glowClass: string
    tools: string[]
}

const AGENTS: AgentDef[] = [
    {
        id: 'OBSIDIAN',
        name: 'Obsidian',
        emoji: '🖤',
        theme: 'Infrastructure & DevOps',
        role: 'Deployments, CI/CD, cloud operations, emergency response',
        colorClass: 'agent-obsidian',
        dotClass: 'agent-dot-obsidian',
        glowClass: 'agent-obsidian-glow',
        tools: ['read', 'write', 'edit', 'exec', 'browser', 'web_search', 'sessions', 'memory', 'cron', 'gateway'],
    },
    {
        id: 'EMERALD',
        name: 'Emerald',
        emoji: '💚',
        theme: 'Code Quality & Architecture',
        role: 'Code reviews, refactoring, testing, improvements',
        colorClass: 'agent-emerald',
        dotClass: 'agent-dot-emerald',
        glowClass: 'agent-emerald-glow',
        tools: ['read', 'write', 'edit', 'exec', 'web_search', 'sessions', 'memory'],
    },
    {
        id: 'SAPPHIRE',
        name: 'Sapphire',
        emoji: '💎',
        theme: 'Security & Risk',
        role: 'Trading oversight, security audits, risk monitoring',
        colorClass: 'agent-sapphire',
        dotClass: 'agent-dot-sapphire',
        glowClass: 'agent-sapphire-glow',
        tools: ['read', 'exec', 'web_search', 'sessions', 'memory'],
    },
]

/* ── Derived metrics ── */
const dispatchCount = computed(() =>
    Number(control.value?.autonomy_dispatch_count ?? performance.value?.metrics?.system?.autonomy_dispatch_count ?? 0),
)

const rotationCycle = computed(() => dispatchCount.value % 3)

const nextAgentId = computed(() => {
    const mapping = ['OBSIDIAN', 'EMERALD', 'SAPPHIRE']
    return mapping[rotationCycle.value] || 'OBSIDIAN'
})

const autonomyEnabled = computed(() => Boolean(control.value?.full_autonomy_enabled))
const killSwitchActive = computed(() => Boolean(control.value?.kill_switch_active))
const pendingDecisions = computed(() => Number(control.value?.pending_autonomy_decisions ?? 0))
const failurePressure = computed(() => Number(control.value?.failure_pressure ?? 0))

const uptimeLabel = computed(() => {
    const seconds = Number(performance.value?.metrics?.system?.uptime_seconds ?? 0)
    if (seconds < 60) return `${Math.round(seconds)}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
})

/* ── Agent dispatch logs (filtered from system logs) ── */
const agentOps = computed(() => {
    return recentOps.value
        .filter((op) => {
            const msg = op.message.toLowerCase()
            return msg.includes('obsidian') || msg.includes('emerald') || msg.includes('sapphire') ||
                msg.includes('autonomy') || msg.includes('dispatch') || msg.includes('agent')
        })
        .slice(0, 12)
        .map((op) => {
            const ts = new Date(op.timestamp * 1000)
            const time = `${String(ts.getHours()).padStart(2, '0')}:${String(ts.getMinutes()).padStart(2, '0')}:${String(ts.getSeconds()).padStart(2, '0')}`
            const levelTag = op.level === 'error' ? 'ERR' : op.level === 'warning' ? 'WRN' : 'INF'
            const agent = detectAgent(op.message)
            return { time, level: op.level, tag: levelTag, message: op.message, agent, id: `${op.timestamp}-${op.message.slice(0, 20)}` }
        })
})

function detectAgent(msg: string): string | null {
    const lower = msg.toLowerCase()
    if (lower.includes('obsidian')) return 'OBSIDIAN'
    if (lower.includes('emerald')) return 'EMERALD'
    if (lower.includes('sapphire')) return 'SAPPHIRE'
    return null
}

function agentDotClass(agentId: string | null): string {
    if (agentId === 'OBSIDIAN') return 'agent-dot-obsidian'
    if (agentId === 'EMERALD') return 'agent-dot-emerald'
    if (agentId === 'SAPPHIRE') return 'agent-dot-sapphire'
    return ''
}

/* ── Data fetch ── */
const loadData = async () => {
    fetchError.value = ''
    try {
        const settled = await Promise.allSettled([
            fetchControlStatus(),
            fetchPerformanceStats(),
            fetchSystemLogs(60),
        ])
        const pick = <T>(i: number): T | null => {
            const r = settled[i]
            return r?.status === 'fulfilled' ? (r.value as T | null) || null : null
        }
        const cp = pick<ControlStatusResponse>(0)
        if (cp?.ok) control.value = cp
        const perf = pick<PerformanceStatsResponse>(1)
        if (perf?.ok) performance.value = perf
        const logs = pick<SystemLogEntry[]>(2)
        if (Array.isArray(logs)) recentOps.value = logs

        lastSyncEpoch.value = Date.now()
    } catch (error) {
        fetchError.value = connectionHealth.lastErrorMessage || 'Connection failed'
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    loadData()
    refreshTimer = setInterval(loadData, 15000)
    clockTimer = setInterval(() => { nowEpoch.value = Date.now() }, 1000)
})

onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
    if (clockTimer) clearInterval(clockTimer)
})
</script>

<template>
    <div class="grid gap-4 fade-in" aria-label="Agent operations dashboard">

        <!-- Status Bar -->
        <StatusBar
            :loading="loading"
            :has-data="!!lastSyncEpoch"
            :fetch-error="fetchError || null"
            :is-stale="isStale"
            :data-age="dataAge"
            loading-message="Connecting to agent mesh..."
            @retry="loadData"
        />

        <!-- Skeleton -->
        <template v-if="loading && !lastSyncEpoch">
            <KpiStrip :columns="6" class="max-lg:!grid-cols-3 max-md:!grid-cols-2">
                <KpiCard v-for="i in 6" :key="i" label="" value="" :loading="true" />
            </KpiStrip>
            <section class="grid grid-cols-3 gap-3 max-lg:grid-cols-1">
                <article v-for="i in 3" :key="i" class="grid gap-2 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm">
                    <div class="mx-auto h-5 w-1/2 animate-pulse rounded-xs bg-terminal-ghost" />
                    <div class="mx-auto h-3 w-2/5 animate-pulse rounded-xs bg-terminal-ghost/50" />
                    <div class="mx-auto h-3 w-2/5 animate-pulse rounded-xs bg-terminal-ghost/50" />
                </article>
            </section>
        </template>

        <template v-else>
        <!-- KPI Strip -->
        <KpiStrip :columns="6" class="max-lg:!grid-cols-3 max-md:!grid-cols-2" aria-label="Agent system indicators">
            <KpiCard
                label="Autonomy"
                :value="autonomyEnabled ? 'ACTIVE' : 'OFF'"
                :tone="autonomyEnabled ? 'success' : undefined"
                :glow="autonomyEnabled"
            />
            <KpiCard
                label="Dispatches"
                :value="String(dispatchCount)"
                tone="success"
                :glow="true"
            />
            <KpiCard
                label="Rotation"
                :value="`${AGENTS[rotationCycle]?.emoji ?? ''} ${AGENTS[rotationCycle]?.name?.toUpperCase() ?? ''}`"
                :class="[
                    rotationCycle === 0 ? 'text-obsidian' : rotationCycle === 1 ? 'text-emerald' : 'text-sapphire-blue'
                ]"
                :glow="true"
            />
            <KpiCard
                label="Kill Switch"
                :value="killSwitchActive ? 'ACTIVE' : 'OFF'"
                :tone="killSwitchActive ? 'error' : 'success'"
                :glow="!killSwitchActive"
            />
            <KpiCard
                label="Pending"
                :value="String(pendingDecisions)"
                :tone="pendingDecisions > 0 ? 'warning' : undefined"
            />
            <KpiCard
                label="Uptime"
                :value="uptimeLabel"
            />
        </KpiStrip>

        <!-- Rotation Visualizer -->
        <section class="rounded-md border border-border-subtle bg-card p-5 backdrop-blur-sm" aria-label="Agent rotation cycle">
            <SectionHeader title="Dispatch Rotation">
                <template #actions>
                    <SyncBadge :text="`CYCLE ${rotationCycle}/2`" variant="success" :pulse="true" />
                </template>
            </SectionHeader>

            <div class="relative mt-3 grid grid-cols-3 gap-4 py-4 max-md:grid-cols-1">
                <div
                    v-for="(agent, idx) in AGENTS"
                    :key="agent.id"
                    class="relative z-10 flex flex-col items-center gap-1.5 rounded-md border px-2 py-4 transition-all duration-300"
                    :class="[
                        rotationCycle === idx
                            ? 'border-border-accent bg-[rgba(20,35,20,0.5)] shadow-[var(--glow-md)]'
                            : 'border-border-subtle bg-[rgba(10,18,10,0.4)]'
                    ]"
                >
                    <span class="text-3xl" :class="{ [agent.glowClass]: rotationCycle === idx }">{{ agent.emoji }}</span>
                    <span
                        class="font-mono text-xs font-bold tracking-widest"
                        :class="[
                            agent.id === 'OBSIDIAN' ? 'text-obsidian' : agent.id === 'EMERALD' ? 'text-emerald' : 'text-sapphire-blue'
                        ]"
                    >{{ agent.name.toUpperCase() }}</span>
                    <span class="font-mono text-[0.6rem] tracking-widest text-text-tertiary">
                        {{ idx === 0 ? 'MAINTAIN' : idx === 1 ? 'IMPROVE' : 'REVIEW' }}
                    </span>
                    <div
                        class="relative mt-1 h-2.5 w-2.5 rounded-full border"
                        :class="[
                            rotationCycle === idx
                                ? 'border-terminal bg-terminal shadow-[0_0_8px_rgba(32,194,14,0.6)]'
                                : 'border-border-subtle'
                        ]"
                    >
                        <span v-if="rotationCycle === idx" class="indicator-pulse" />
                    </div>
                </div>

                <!-- SVG connector lines (keep minimal CSS for these) -->
                <div class="pointer-events-none absolute inset-x-0 top-1/2 z-0 -translate-y-1/2 max-md:hidden">
                    <svg viewBox="0 0 300 20" class="h-5 w-full">
                        <line x1="50" y1="10" x2="150" y2="10" class="connector-line" :class="{ 'connector-active': rotationCycle >= 1 }" />
                        <line x1="150" y1="10" x2="250" y2="10" class="connector-line" :class="{ 'connector-active': rotationCycle >= 2 }" />
                    </svg>
                </div>
            </div>
        </section>

        <!-- Agent Cards -->
        <section class="grid grid-cols-3 gap-3 max-lg:grid-cols-1" aria-label="Agent profiles">
            <article
                v-for="(agent, idx) in AGENTS"
                :key="agent.id"
                class="grid gap-1.5 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm transition-all duration-300 glass-lift"
                :class="[
                    rotationCycle === idx
                        ? 'border-l-[3px] border-l-terminal shadow-[inset_3px_0_8px_-3px_rgba(32,194,14,0.15)]'
                        : 'border-l-[3px] border-l-border-subtle'
                ]"
            >
                <header class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <AgentDot :agent="agent.id.toLowerCase() as 'obsidian' | 'emerald' | 'sapphire'" size="md" />
                        <h4
                            class="m-0 font-mono text-sm font-bold tracking-widest"
                            :class="[
                                agent.id === 'OBSIDIAN' ? 'text-obsidian [text-shadow:0_0_8px_rgba(160,160,160,0.4)]'
                                    : agent.id === 'EMERALD' ? 'text-emerald [text-shadow:0_0_8px_rgba(52,211,153,0.4)]'
                                    : 'text-sapphire-blue [text-shadow:0_0_8px_rgba(96,165,250,0.4)]'
                            ]"
                        >{{ agent.emoji }} {{ agent.name.toUpperCase() }}</h4>
                    </div>
                    <SyncBadge v-if="rotationCycle === idx" text="NEXT" variant="success" :pulse="true" />
                </header>
                <p class="m-0 text-xs font-medium text-text-secondary">{{ agent.theme }}</p>
                <p class="m-0 text-[0.72rem] leading-relaxed text-text-tertiary">{{ agent.role }}</p>
                <div class="mt-0.5 flex flex-wrap gap-1">
                    <span
                        v-for="tool in agent.tools"
                        :key="tool"
                        class="rounded-xs border border-terminal/10 bg-terminal/[0.06] px-1.5 py-0.5 font-mono text-[0.58rem] tracking-wide text-text-tertiary"
                    >{{ tool }}</span>
                </div>
                <div class="mt-0.5 font-mono text-[0.68rem] text-text-secondary">
                    Dispatches: ~{{ Math.floor(dispatchCount / 3) + (idx < (dispatchCount % 3) ? 1 : 0) }}
                </div>
            </article>
        </section>

        <!-- Failure Pressure + Pending Approvals -->
        <section class="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
            <!-- Failure Pressure Gauge -->
            <article class="grid gap-2 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm glass-lift">
                <SectionHeader title="Failure Pressure">
                    <template #actions>
                        <span
                            class="font-mono text-lg font-bold"
                            :class="[
                                failurePressure > 7 ? 'text-error animate-pulse' : failurePressure > 3 ? 'text-warning' : 'text-terminal glow'
                            ]"
                        >{{ failurePressure }}</span>
                    </template>
                </SectionHeader>
                <GaugeBar :value="failurePressure" :max="10" />
                <small class="font-mono text-[0.62rem] text-text-tertiary">Threshold: 10 &middot; Max before emergency routing</small>
            </article>

            <!-- Pending Approvals -->
            <article class="grid gap-2 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm glass-lift">
                <SectionHeader title="Pending Approvals">
                    <template #actions>
                        <span
                            class="font-mono text-lg font-bold"
                            :class="[pendingDecisions > 0 ? 'text-warning' : 'text-terminal glow']"
                        >{{ pendingDecisions }}</span>
                    </template>
                </SectionHeader>
                <div class="grid gap-1.5">
                    <template v-if="control?.pending_sessions?.length">
                        <div
                            v-for="session in control.pending_sessions.slice(0, 3)"
                            :key="session.session_key"
                            class="flex items-center justify-between rounded-xs border border-border-subtle px-2 py-1.5 text-[0.72rem]"
                        >
                            <span class="font-mono">{{ session.trigger }}</span>
                            <span class="font-mono text-[0.65rem] text-text-tertiary">{{ new Date(session.created_at * 1000).toISOString().slice(11, 19) }}</span>
                        </div>
                    </template>
                    <p v-else class="m-0 py-2 text-[0.72rem] italic text-text-tertiary">No pending approvals</p>
                </div>
            </article>
        </section>

        <!-- Agent Operations Feed -->
        <OpsFeed
            :ops="agentOps.map(op => ({
                time: op.time,
                level: op.level as 'info' | 'warning' | 'error',
                tag: op.tag,
                message: op.message,
                agent: op.agent?.toLowerCase()
            }))"
            title="Agent Activity Feed"
            max-height="280px"
            :show-agent="true"
        />
        </template>
    </div>
</template>

<script lang="ts">
import { StatusBar, KpiCard, KpiStrip, SectionHeader, SyncBadge, OpsFeed, GaugeBar, AgentDot } from '../components/shared/index'
import type { OpEntry } from '../components/shared/index'

export default {
    components: { StatusBar, KpiCard, KpiStrip, SectionHeader, SyncBadge, OpsFeed, GaugeBar, AgentDot },
}
</script>

<style scoped>
/* ── Indicator pulse animation (rotation visualizer dots) ── */
.indicator-pulse {
    position: absolute;
    inset: -4px;
    border-radius: 50%;
    border: 1px solid rgba(32, 194, 14, 0.4);
    animation: indicatorPing 1.5s ease-out infinite;
}

@keyframes indicatorPing {
    0% { transform: scale(0.8); opacity: 1; }
    100% { transform: scale(2); opacity: 0; }
}

/* ── SVG connector lines (rotation visualizer) ── */
.connector-line {
    stroke: rgba(32, 194, 14, 0.12);
    stroke-width: 1;
    stroke-dasharray: 4 4;
}

.connector-line.connector-active {
    stroke: rgba(32, 194, 14, 0.35);
    stroke-width: 1.5;
}

/* ── Agent glow classes (used dynamically via agent.glowClass) ── */
.agent-obsidian-glow { text-shadow: 0 0 8px rgba(160, 160, 160, 0.4); }
.agent-emerald-glow { text-shadow: 0 0 8px rgba(52, 211, 153, 0.4); }
.agent-sapphire-glow { text-shadow: 0 0 8px rgba(96, 165, 250, 0.4); }
</style>

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
    <div class="agents-view fade-in" aria-label="Agent operations dashboard">
        <div v-if="loading && !lastSyncEpoch" class="status-bar loading-bar" role="status" aria-live="polite">
            <span class="pulse-dot" aria-hidden="true"></span> Connecting to agent mesh...
        </div>
        <div v-else-if="fetchError" class="status-bar error-bar" role="alert" tabindex="0" @click="loadData" @keydown.enter="loadData">
            {{ fetchError }} — tap to retry
        </div>
        <div v-else-if="isStale" class="status-bar stale-bar" role="status">
            Data {{ dataAge }}s old — awaiting refresh
        </div>

        <!-- Skeleton -->
        <template v-if="loading && !lastSyncEpoch">
            <section class="kpi-strip">
                <article v-for="i in 6" :key="i" class="kpi card glass-lift">
                    <div class="skel-line skel-sm"></div>
                    <div class="skel-line skel-lg"></div>
                </article>
            </section>
            <section class="agent-cards">
                <article v-for="i in 3" :key="i" class="agent-card card">
                    <div class="skel-line skel-lg"></div>
                    <div class="skel-line skel-sm"></div>
                    <div class="skel-line skel-sm"></div>
                </article>
            </section>
        </template>

        <template v-else>
        <!-- KPI Strip -->
        <section class="kpi-strip" aria-label="Agent system indicators">
            <article class="kpi card glass-lift">
                <span class="font-mono">Autonomy</span>
                <strong :class="autonomyEnabled ? 'glow' : 'dim'">{{ autonomyEnabled ? 'ACTIVE' : 'OFF' }}</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Dispatches</span>
                <strong class="glow">{{ dispatchCount }}</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Rotation</span>
                <strong :class="[AGENTS[rotationCycle]?.colorClass || '', AGENTS[rotationCycle]?.glowClass || '']">
                    {{ AGENTS[rotationCycle]?.emoji }} {{ AGENTS[rotationCycle]?.name?.toUpperCase() }}
                </strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Kill Switch</span>
                <strong :class="killSwitchActive ? 'kill-active' : 'glow'">{{ killSwitchActive ? 'ACTIVE' : 'OFF' }}</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Pending</span>
                <strong :class="pendingDecisions > 0 ? 'warn' : ''">{{ pendingDecisions }}</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Uptime</span>
                <strong>{{ uptimeLabel }}</strong>
            </article>
        </section>

        <!-- Rotation Visualizer -->
        <section class="rotation-section card-elevated" aria-label="Agent rotation cycle">
            <header class="section-header">
                <h3 class="font-mono glow-strong">Dispatch Rotation</h3>
                <span class="sync-badge pulse-badge">CYCLE {{ rotationCycle }}/2</span>
            </header>
            <div class="rotation-ring">
                <div
                    v-for="(agent, idx) in AGENTS"
                    :key="agent.id"
                    class="rotation-node"
                    :class="{ 'rotation-active': rotationCycle === idx }"
                >
                    <span class="rotation-emoji" :class="{ [agent.glowClass]: rotationCycle === idx }">{{ agent.emoji }}</span>
                    <span class="rotation-name font-mono" :class="agent.colorClass">{{ agent.name.toUpperCase() }}</span>
                    <span class="rotation-cycle font-mono">{{ idx === 0 ? 'MAINTAIN' : idx === 1 ? 'IMPROVE' : 'REVIEW' }}</span>
                    <div class="rotation-indicator" :class="{ active: rotationCycle === idx }">
                        <span v-if="rotationCycle === idx" class="indicator-pulse"></span>
                    </div>
                </div>
                <div class="rotation-connectors">
                    <svg viewBox="0 0 300 20" class="connector-svg">
                        <line x1="50" y1="10" x2="150" y2="10" class="connector-line" :class="{ 'connector-active': rotationCycle >= 1 }" />
                        <line x1="150" y1="10" x2="250" y2="10" class="connector-line" :class="{ 'connector-active': rotationCycle >= 2 }" />
                    </svg>
                </div>
            </div>
        </section>

        <!-- Agent Cards -->
        <section class="agent-cards" aria-label="Agent profiles">
            <article
                v-for="(agent, idx) in AGENTS"
                :key="agent.id"
                class="agent-card card glass-lift"
                :class="{ 'agent-card-active': rotationCycle === idx }"
            >
                <header class="agent-header">
                    <div class="agent-identity">
                        <span class="agent-dot" :class="agent.dotClass"></span>
                        <h4 :class="[agent.colorClass, agent.glowClass]">{{ agent.emoji }} {{ agent.name.toUpperCase() }}</h4>
                    </div>
                    <span v-if="rotationCycle === idx" class="next-badge">NEXT</span>
                </header>
                <p class="agent-theme">{{ agent.theme }}</p>
                <p class="agent-role">{{ agent.role }}</p>
                <div class="agent-tools">
                    <span v-for="tool in agent.tools" :key="tool" class="tool-chip">{{ tool }}</span>
                </div>
                <div class="agent-stats">
                    <span class="font-mono">Dispatches: ~{{ Math.floor(dispatchCount / 3) + (idx < (dispatchCount % 3) ? 1 : 0) }}</span>
                </div>
            </article>
        </section>

        <!-- Failure Pressure Gauge -->
        <section class="gauges-row">
            <article class="gauge-card card glass-lift">
                <header class="section-header">
                    <h3 class="font-mono">Failure Pressure</h3>
                    <span class="gauge-value" :class="failurePressure > 7 ? 'kill-active' : failurePressure > 3 ? 'warn' : 'glow'">
                        {{ failurePressure }}
                    </span>
                </header>
                <div class="gauge-bar">
                    <div
                        class="gauge-fill"
                        :class="failurePressure > 7 ? 'fill-error' : failurePressure > 3 ? 'fill-warn' : 'fill-ok'"
                        :style="{ width: `${Math.min(100, (failurePressure / 10) * 100)}%` }"
                    ></div>
                </div>
                <small class="font-mono">Threshold: 10 · Max before emergency routing</small>
            </article>
            <article class="gauge-card card glass-lift">
                <header class="section-header">
                    <h3 class="font-mono">Pending Approvals</h3>
                    <span class="gauge-value" :class="pendingDecisions > 0 ? 'warn' : 'glow'">{{ pendingDecisions }}</span>
                </header>
                <div class="approval-queue">
                    <template v-if="control?.pending_sessions?.length">
                        <div v-for="session in control.pending_sessions.slice(0, 3)" :key="session.session_key" class="approval-item">
                            <span class="font-mono">{{ session.trigger }}</span>
                            <span class="approval-time">{{ new Date(session.created_at * 1000).toISOString().slice(11, 19) }}</span>
                        </div>
                    </template>
                    <p v-else class="queue-empty">No pending approvals</p>
                </div>
            </article>
        </section>

        <!-- Agent Operations Feed -->
        <section class="ops-feed card">
            <header class="section-header">
                <h3 class="font-mono">Agent Activity Feed</h3>
                <span class="sync-badge">{{ agentOps.length }} events</span>
            </header>
            <div class="ops-grid">
                <article v-for="op in agentOps" :key="op.id" class="ops-row" :class="`ops-${op.level}`">
                    <span v-if="op.agent" class="agent-dot agent-dot-sm" :class="agentDotClass(op.agent)"></span>
                    <span v-else class="agent-dot agent-dot-sm"></span>
                    <span class="ops-time">{{ op.time }}</span>
                    <span class="ops-tag" :class="`tag-${op.level}`">{{ op.tag }}</span>
                    <span class="ops-msg">{{ op.message }}</span>
                </article>
                <article v-if="!agentOps.length" class="ops-row ops-empty">
                    <span class="ops-msg">Awaiting agent dispatch events...</span>
                </article>
            </div>
        </section>
        </template>
    </div>
</template>

<style scoped>
.agents-view {
    display: grid;
    gap: 1rem;
}

/* ── KPI Strip ── */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0.6rem;
}

.kpi {
    display: grid;
    gap: 0.2rem;
    text-align: center;
    padding: 0.65rem 0.5rem;
}

.kpi span { font-size: 0.62rem; color: var(--text-tertiary); }
.kpi strong { font-size: 1.05rem; color: var(--text-primary); }
.kpi strong.dim { color: var(--text-tertiary); }
.kpi strong.warn { color: var(--color-warning); text-shadow: 0 0 6px rgba(255, 176, 0, 0.4); }
.kpi strong.kill-active { color: var(--color-error); text-shadow: 0 0 8px rgba(255, 68, 68, 0.5); animation: killPulse 1s ease-in-out infinite; }

@keyframes killPulse {
    0%, 100% { opacity: 0.7; }
    50% { opacity: 1; }
}

/* ── Rotation Section ── */
.rotation-section {
    padding: 1.2rem;
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.8rem;
}

.section-header h3 { margin: 0; }

.sync-badge {
    font-size: 0.62rem;
    color: var(--text-tertiary);
    letter-spacing: 0.04em;
    border: 1px solid var(--border-subtle);
    border-radius: 999px;
    padding: 0.15rem 0.5rem;
    font-family: var(--font-mono);
    text-transform: uppercase;
}

.pulse-badge {
    color: var(--color-terminal);
    border-color: rgba(32, 194, 14, 0.4);
    animation: badgePulse 2s ease-in-out infinite;
}

@keyframes badgePulse {
    0%, 100% { opacity: 0.7; }
    50% { opacity: 1; }
}

.rotation-ring {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    position: relative;
    padding: 1rem 0;
}

.rotation-node {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    padding: 1rem 0.5rem;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background: rgba(10, 18, 10, 0.4);
    transition: all 0.3s ease;
    position: relative;
}

.rotation-node.rotation-active {
    border-color: var(--border-accent);
    background: rgba(20, 35, 20, 0.5);
    box-shadow: var(--glow-md);
}

.rotation-emoji { font-size: 1.8rem; }
.rotation-name { font-size: 0.78rem; font-weight: 700; letter-spacing: 0.06em; }
.rotation-cycle { font-size: 0.6rem; color: var(--text-tertiary); letter-spacing: 0.06em; }

.rotation-indicator {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 1px solid var(--border-subtle);
    margin-top: 0.3rem;
    position: relative;
}

.rotation-indicator.active {
    border-color: var(--color-terminal);
    background: var(--color-terminal);
    box-shadow: 0 0 8px rgba(32, 194, 14, 0.6);
}

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

.rotation-connectors {
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    transform: translateY(-50%);
    pointer-events: none;
    z-index: 0;
}

.connector-svg {
    width: 100%;
    height: 20px;
}

.connector-line {
    stroke: rgba(32, 194, 14, 0.12);
    stroke-width: 1;
    stroke-dasharray: 4 4;
}

.connector-line.connector-active {
    stroke: rgba(32, 194, 14, 0.35);
    stroke-width: 1.5;
}

/* ── Agent Cards ── */
.agent-cards {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.8rem;
}

.agent-card {
    display: grid;
    gap: 0.4rem;
    border-left: 3px solid var(--border-subtle);
    transition: border-color 0.3s, box-shadow 0.3s;
}

.agent-card-active {
    border-left-color: var(--color-terminal);
    box-shadow: inset 3px 0 8px -3px rgba(32, 194, 14, 0.15);
}

.agent-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.agent-identity {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.agent-identity h4 {
    margin: 0;
    font-size: 0.88rem;
    font-weight: 700;
    letter-spacing: 0.06em;
}

.next-badge {
    font-size: 0.58rem;
    font-family: var(--font-mono);
    letter-spacing: 0.08em;
    color: var(--color-terminal);
    border: 1px solid rgba(32, 194, 14, 0.4);
    border-radius: 999px;
    padding: 0.12rem 0.45rem;
    animation: badgePulse 2s ease-in-out infinite;
}

.agent-theme {
    margin: 0;
    font-size: 0.78rem;
    color: var(--text-secondary);
    font-weight: 500;
}

.agent-role {
    margin: 0;
    font-size: 0.72rem;
    color: var(--text-tertiary);
    line-height: 1.5;
}

.agent-tools {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-top: 0.2rem;
}

.tool-chip {
    font-size: 0.58rem;
    font-family: var(--font-mono);
    letter-spacing: 0.04em;
    color: var(--text-tertiary);
    background: rgba(32, 194, 14, 0.06);
    border: 1px solid rgba(32, 194, 14, 0.1);
    border-radius: var(--radius-xs);
    padding: 0.1rem 0.35rem;
}

.agent-stats {
    margin-top: 0.2rem;
    font-size: 0.68rem;
    color: var(--text-secondary);
}

/* ── Gauges Row ── */
.gauges-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.8rem;
}

.gauge-card { display: grid; gap: 0.4rem; }

.gauge-value {
    font-size: 1.1rem;
    font-weight: 700;
    font-family: var(--font-mono);
}

.gauge-bar {
    height: 6px;
    background: rgba(32, 194, 14, 0.08);
    border-radius: 3px;
    overflow: hidden;
}

.gauge-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
}

.fill-ok { background: var(--color-terminal); box-shadow: 0 0 6px rgba(32, 194, 14, 0.4); }
.fill-warn { background: var(--color-warning); box-shadow: 0 0 6px rgba(255, 176, 0, 0.4); }
.fill-error { background: var(--color-error); box-shadow: 0 0 6px rgba(255, 68, 68, 0.4); }

.gauge-card small { color: var(--text-tertiary); font-size: 0.62rem; }

.approval-queue {
    display: grid;
    gap: 0.3rem;
}

.approval-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.3rem 0.4rem;
    border-radius: var(--radius-xs);
    border: 1px solid var(--border-subtle);
    font-size: 0.72rem;
}

.approval-time {
    color: var(--text-tertiary);
    font-size: 0.65rem;
    font-family: var(--font-mono);
}

.queue-empty {
    margin: 0;
    color: var(--text-tertiary);
    font-size: 0.72rem;
    font-style: italic;
    padding: 0.5rem 0;
}

/* ── Ops Feed ── */
.ops-feed { display: grid; gap: 0.4rem; }

.ops-grid {
    display: grid;
    gap: 0.2rem;
    max-height: 280px;
    overflow-y: auto;
}

.ops-row {
    display: grid;
    grid-template-columns: 12px 56px 30px 1fr;
    gap: 0.4rem;
    align-items: center;
    padding: 0.3rem 0.4rem;
    border-radius: var(--radius-xs);
    font-size: 0.72rem;
    font-family: var(--font-mono);
    border-left: 2px solid transparent;
}

.ops-row.ops-info { border-left-color: rgba(32, 194, 14, 0.3); }
.ops-row.ops-warning { border-left-color: rgba(255, 176, 0, 0.4); }
.ops-row.ops-error { border-left-color: rgba(255, 68, 68, 0.4); background: rgba(255, 68, 68, 0.04); }

.agent-dot-sm {
    width: 6px;
    height: 6px;
}

.ops-time { color: var(--text-tertiary); font-size: 0.65rem; }
.ops-tag { font-size: 0.58rem; font-weight: 700; letter-spacing: 0.06em; }
.tag-info { color: var(--color-terminal); }
.tag-warning { color: var(--color-warning); }
.tag-error { color: var(--color-error); }
.ops-msg { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ops-empty { grid-template-columns: 1fr; }
.ops-empty .ops-msg { color: var(--text-tertiary); font-style: italic; }

/* ── Status Bars ── */
.status-bar {
    padding: 0.45rem 0.8rem;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    border-radius: var(--radius-sm);
    text-align: center;
}

.loading-bar { background: rgba(32, 194, 14, 0.08); color: var(--color-terminal); border: 1px solid rgba(32, 194, 14, 0.15); }
.error-bar { background: rgba(255, 68, 68, 0.08); color: var(--color-error); border: 1px solid rgba(255, 68, 68, 0.2); cursor: pointer; }
.stale-bar { background: rgba(255, 200, 50, 0.06); color: var(--color-warning); border: 1px solid rgba(255, 200, 50, 0.15); }

.pulse-dot {
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--color-terminal);
    margin-right: 0.4rem;
    animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 1; }
}

/* ── Skeleton ── */
.skel-line { border-radius: var(--radius-xs); animation: skelPulse 1.6s ease-in-out infinite; }
.skel-lg { width: 50%; height: 1.15rem; margin: 0 auto; background: rgba(32, 194, 14, 0.08); }
.skel-sm { width: 40%; height: 0.6rem; margin: 0 auto 0.3rem; background: rgba(32, 194, 14, 0.05); }

@keyframes skelPulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 0.85; }
}

/* ── Responsive ── */
@media (max-width: 1100px) {
    .kpi-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .agent-cards { grid-template-columns: 1fr; }
    .gauges-row { grid-template-columns: 1fr; }
}

@media (max-width: 760px) {
    .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .rotation-ring { grid-template-columns: 1fr; }
}
</style>

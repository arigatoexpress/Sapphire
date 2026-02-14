<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, nextTick } from 'vue'
import {
    connectionHealth,
    fetchControlStatus,
    fetchForumScoutStatus,
    fetchForumTopics,
    fetchPlatformStatus,
    fetchPerformanceStats,
    fetchSystemLogs,
    type ControlStatusResponse,
    type ForumScoutStatusResponse,
    type ForumTopic,
    type PlatformStatusResponse,
    type PerformanceStatsResponse,
    type SystemLogEntry,
} from '../api/client'

const loading = ref(true)
const topics = ref<ForumTopic[]>([])
const boardMeta = ref<{
    total: number
    lane_counts: Record<string, number>
    state_counts: Record<string, number>
    control: { pending_autonomy_decisions: number; owner_directive: string; failure_pressure: number }
} | null>(null)
const control = ref<ControlStatusResponse | null>(null)
const scout = ref<ForumScoutStatusResponse | null>(null)
const platform = ref<PlatformStatusResponse | null>(null)
const performance = ref<PerformanceStatsResponse | null>(null)
const recentOps = ref<SystemLogEntry[]>([])
const nowEpoch = ref(Date.now())
const lastSyncEpoch = ref(0)
const hoveredNode = ref<string | null>(null)
const fetchError = ref('')

const dataAge = computed(() => {
    if (!lastSyncEpoch.value) return null
    return Math.floor((Date.now() - lastSyncEpoch.value) / 1000)
})
const isStale = computed(() => (dataAge.value ?? 999) > 30)

let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null
let particleTimer: ReturnType<typeof setInterval> | null = null

/* ── Particles for animated data flow ── */
interface FlowParticle {
    id: number
    fromX: number; fromY: number
    toX: number; toY: number
    progress: number
    speed: number
    opacity: number
    linkKey: string
}

const particles = ref<FlowParticle[]>([])
let particleIdCounter = 0

const spawnParticle = (fromX: number, fromY: number, toX: number, toY: number, linkKey: string) => {
    particles.value.push({
        id: particleIdCounter++,
        fromX, fromY, toX, toY,
        progress: 0,
        speed: 0.008 + Math.random() * 0.012,
        opacity: 0.6 + Math.random() * 0.4,
        linkKey,
    })
}

const tickParticles = () => {
    particles.value = particles.value
        .map((p) => ({ ...p, progress: p.progress + p.speed, opacity: p.progress > 0.8 ? p.opacity * 0.92 : p.opacity }))
        .filter((p) => p.progress < 1)
}

const particleX = (p: FlowParticle) => p.fromX + (p.toX - p.fromX) * p.progress
const particleY = (p: FlowParticle) => p.fromY + (p.toY - p.fromY) * p.progress

/* ── Derived metrics ── */
const totalTopics = computed(() => Number(boardMeta.value?.total || topics.value.length || 0))
const pendingDecisions = computed(() =>
    Number(control.value?.pending_autonomy_decisions ?? boardMeta.value?.control?.pending_autonomy_decisions ?? 0),
)
const failurePressure = computed(() =>
    Number(control.value?.failure_pressure ?? boardMeta.value?.control?.failure_pressure ?? 0),
)
const syncAge = computed(() => {
    if (!lastSyncEpoch.value) return '--'
    return `${Math.max(0, Math.round((nowEpoch.value - lastSyncEpoch.value) / 1000))}s`
})

const totalTrades = computed(() => Number(performance.value?.metrics?.system?.total_trades || 0))
const winRatePercent = computed(() => {
    const raw = Number(performance.value?.metrics?.system?.win_rate || 0)
    return Math.max(0, Math.min(100, raw <= 1 ? raw * 100 : raw))
})
const formatUptime = (seconds: number) => {
    const rounded = Math.max(0, Math.round(Number(seconds || 0)))
    if (rounded < 60) return `${rounded}s`
    if (rounded < 3600) return `${Math.floor(rounded / 60)}m`
    return `${Math.floor(rounded / 3600)}h ${Math.floor((rounded % 3600) / 60)}m`
}
const uptimeLabel = computed(() =>
    formatUptime(Number(performance.value?.metrics?.system?.uptime_seconds || 0)),
)
const realizedPnl = computed(() => Number(performance.value?.metrics?.system?.realized_pnl || 0))

const forumHealthScore = computed(() => {
    const openCount = Number(boardMeta.value?.state_counts?.open || 0)
    const blockedCount = Number(boardMeta.value?.state_counts?.blocked || 0)
    const resolvedCount = Number(boardMeta.value?.state_counts?.resolved || 0)
    const raw = 65 + resolvedCount * 3 - blockedCount * 5 - pendingDecisions.value * 4 - failurePressure.value * 2 + openCount
    return Math.max(5, Math.min(99, Math.round(raw)))
})

const architectureHealthScore = computed(() => {
    const killPenalty = control.value?.kill_switch_active ? 35 : 0
    const failurePenalty = failurePressure.value * 7
    const pendingPenalty = pendingDecisions.value * 4
    const venueBonus = Object.values(platform.value?.platforms || {}).filter((item) => item.status === 'healthy').length * 6
    const autonomyBonus = control.value?.full_autonomy_enabled ? 8 : -5
    const raw = 74 + venueBonus + autonomyBonus - killPenalty - failurePenalty - pendingPenalty
    return Math.max(8, Math.min(99, Math.round(raw)))
})

const scoutReady = computed(() => Boolean(scout.value?.registration?.registered))
const scoutBridgeReady = computed(() => {
    const bridge = scout.value?.external_bridge
    if (!bridge) return false
    return Boolean(bridge.external_ready ?? (bridge.register_url_configured && bridge.post_url_configured && bridge.api_token_configured)) || Boolean(bridge.fallback_ready)
})

/* ── Platform venue status ── */
const VENUES = ['aster', 'lighter'] as const
type VenueId = typeof VENUES[number]

const venueDisplayNames: Record<VenueId, string> = {
    aster: 'ASTER',
    lighter: 'LIGHTER',
}

const venueStatus = computed(() => {
    const plats = platform.value?.platforms || {}
    return VENUES.map((id) => {
        const p = plats[id]
        return {
            id,
            name: venueDisplayNames[id],
            status: p?.status || 'offline',
            health: p?.health || 'unknown',
            mode: p?.mode || '—',
            routing: p?.routing || '—',
            allocation: Number(p?.allocation || 0),
            paused: Boolean(p?.paused),
            price: Number(p?.price || 0),
        }
    })
})

/* ── Architecture Nodes ── */
const architectureNodes = computed(() => {
    const alphaHealthy = !control.value?.kill_switch_active
    const venuesHealthyCount = Object.values(platform.value?.platforms || {}).filter((item) => item.status === 'healthy').length
    const venuesHealthy = venuesHealthyCount >= 2
    const vtReady = Boolean(control.value?.vt_security_enabled && control.value?.vt_api_key_configured)
    const dexLive = Boolean(control.value?.dex_live_dispatch_enabled && !control.value?.kill_switch_active)
    const scoutOk = Boolean(scoutReady.value && scoutBridgeReady.value)
    const autonomyOn = Boolean(control.value?.full_autonomy_enabled)
    const pending = pendingDecisions.value

    return [
        { id: 'owner', title: 'OWNER', status: 'healthy', detail: 'Telegram control', tier: 'command' as const },
        { id: 'sapphire', title: 'SAPPHIRE', status: vtReady ? 'healthy' : 'degraded', detail: vtReady ? `VT ${control.value?.vt_enforcement_mode || 'guard'}` : 'guard degraded', tier: 'core' as const },
        { id: 'obsidian', title: 'OBSIDIAN', status: alphaHealthy && venuesHealthy ? 'healthy' : 'degraded', detail: venuesHealthy ? 'runtime stable' : `${venuesHealthyCount}/2 venues`, tier: 'core' as const },
        { id: 'emerald', title: 'EMERALD', status: autonomyOn && pending === 0 ? 'healthy' : 'degraded', detail: pending > 0 ? `${pending} queued` : autonomyOn ? 'loop active' : 'disabled', tier: 'core' as const },
        { id: 'alpha', title: 'ORCHESTRATOR', status: alphaHealthy ? 'healthy' : 'degraded', detail: alphaHealthy ? 'routing online' : 'kill-switch', tier: 'orchestrator' as const },
        { id: 'execution', title: 'EXECUTION', status: dexLive && venuesHealthy ? 'healthy' : 'degraded', detail: dexLive ? 'live dispatch' : 'staged mode', tier: 'execution' as const },
        { id: 'security', title: 'GUARD', status: vtReady ? 'healthy' : 'degraded', detail: vtReady ? 'scanning active' : 'incomplete', tier: 'execution' as const },
        { id: 'scout', title: 'SCOUT', status: scoutOk ? 'healthy' : 'degraded', detail: scoutOk ? 'bridge active' : 'pending', tier: 'execution' as const },
    ]
})

/* ── Mesh Layout — expanded with venue nodes ── */
const meshLayout: Record<string, { x: number; y: number }> = {
    /* Command tier */
    owner: { x: 50, y: 6 },
    /* Core tier */
    sapphire: { x: 20, y: 20 },
    obsidian: { x: 50, y: 20 },
    emerald: { x: 80, y: 20 },
    /* Orchestrator */
    alpha: { x: 50, y: 38 },
    /* Execution tier */
    security: { x: 18, y: 52 },
    execution: { x: 50, y: 52 },
    scout: { x: 82, y: 52 },
    /* Venue tier */
    aster: { x: 35, y: 72 },
    lighter: { x: 65, y: 72 },
}

const meshNodes = computed(() =>
    architectureNodes.value
        .filter((n) => Boolean(meshLayout[n.id]))
        .map((n) => {
            const layout = meshLayout[n.id]!
            return { ...n, x: layout.x, y: layout.y }
        }),
)

const venueNodes = computed(() =>
    venueStatus.value.map((v) => {
        const layout = meshLayout[v.id]
        return layout ? { ...v, x: layout.x, y: layout.y } : null
    }).filter(Boolean) as Array<{ id: VenueId; name: string; status: string; health: string; mode: string; routing: string; allocation: number; paused: boolean; price: number; x: number; y: number }>
)

/* ── Links between nodes ── */
const coreLinks = [
    { from: 'owner', to: 'sapphire', type: 'command' },
    { from: 'owner', to: 'obsidian', type: 'command' },
    { from: 'owner', to: 'emerald', type: 'command' },
    { from: 'sapphire', to: 'alpha', type: 'data' },
    { from: 'obsidian', to: 'alpha', type: 'data' },
    { from: 'emerald', to: 'alpha', type: 'data' },
    { from: 'alpha', to: 'execution', type: 'signal' },
    { from: 'alpha', to: 'security', type: 'signal' },
    { from: 'alpha', to: 'scout', type: 'signal' },
]

const venueLinks = computed(() =>
    VENUES.map((v) => ({ from: 'execution', to: v, type: 'dispatch' as const }))
)

const allLinks = computed(() => [...coreLinks, ...venueLinks.value])

const meshNodeMap = computed(() => {
    const map: Record<string, { x: number; y: number; status: string }> = {}
    for (const n of meshNodes.value) {
        map[n.id] = { x: n.x, y: n.y, status: n.status }
    }
    for (const v of venueNodes.value) {
        map[v.id] = { x: v.x, y: v.y, status: v.status }
    }
    return map
})

/* ── Curved path for links ── */
const linkPath = (from: { x: number; y: number }, to: { x: number; y: number }) => {
    const dx = to.x - from.x
    const dy = to.y - from.y
    const cx = from.x + dx * 0.5
    const cy = from.y + dy * 0.3
    return `M ${from.x} ${from.y} Q ${cx} ${cy} ${to.x} ${to.y}`
}

/* ── Recent operations feed ── */
const recentOpsFeed = computed(() =>
    recentOps.value
        .slice(0, 8)
        .map((op) => {
            const ts = new Date(op.timestamp * 1000)
            const time = `${String(ts.getHours()).padStart(2, '0')}:${String(ts.getMinutes()).padStart(2, '0')}:${String(ts.getSeconds()).padStart(2, '0')}`
            const levelTag = op.level === 'error' ? 'ERR' : op.level === 'warning' ? 'WRN' : 'INF'
            return { time, level: op.level, tag: levelTag, message: op.message, id: `${op.timestamp}-${op.message.slice(0, 20)}` }
        })
)

/* ── Data fetch ── */
const loadBoard = async () => {
    fetchError.value = ''
    try {
        const settled = await Promise.allSettled([
            fetchForumTopics({ limit: 120 }),
            fetchControlStatus(),
            fetchForumScoutStatus(),
            fetchPlatformStatus(),
            fetchPerformanceStats(),
            fetchSystemLogs(20),
        ])
        const pick = <T>(i: number): T | null => {
            const r = settled[i]
            return r?.status === 'fulfilled' ? (r.value as T | null) || null : null
        }

        const board = pick<any>(0)
        if (board?.ok) {
            topics.value = Array.isArray(board.topics) ? board.topics : []
            boardMeta.value = {
                total: Number(board.total || topics.value.length),
                lane_counts: board.lane_counts || {},
                state_counts: board.state_counts || {},
                control: board.control || { pending_autonomy_decisions: 0, owner_directive: '', failure_pressure: 0 },
            }
        }
        const cp = pick<ControlStatusResponse>(1)
        if (cp?.ok) control.value = cp
        const sp = pick<ForumScoutStatusResponse>(2)
        if (sp?.ok) scout.value = sp
        const pp = pick<PlatformStatusResponse>(3)
        if (pp?.ok) platform.value = pp
        const perf = pick<PerformanceStatsResponse>(4)
        if (perf?.ok) performance.value = perf
        const logs = pick<SystemLogEntry[]>(5)
        if (Array.isArray(logs)) recentOps.value = logs

        lastSyncEpoch.value = Date.now()

        /* Spawn particles along active links after data load */
        await nextTick()
        spawnDataParticles()
    } catch (error) {
        fetchError.value = connectionHealth.lastErrorMessage || 'Connection failed'
        console.error('Board sync failed:', error)
    } finally {
        loading.value = false
    }
}

const spawnDataParticles = () => {
    for (const link of allLinks.value) {
        const fromNode = meshNodeMap.value[link.from]
        const toNode = meshNodeMap.value[link.to]
        if (!fromNode || !toNode) continue
        /* Only spawn for healthy/active links */
        if (toNode.status === 'offline') continue
        if (Math.random() > 0.5) {
            spawnParticle(fromNode.x, fromNode.y, toNode.x, toNode.y, `${link.from}-${link.to}`)
        }
    }
}

onMounted(() => {
    loadBoard()
    refreshTimer = setInterval(loadBoard, 15000)
    clockTimer = setInterval(() => { nowEpoch.value = Date.now() }, 1000)
    particleTimer = setInterval(() => {
        tickParticles()
        if (Math.random() > 0.6) spawnDataParticles()
    }, 60)
})
onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
    if (clockTimer) clearInterval(clockTimer)
    if (particleTimer) clearInterval(particleTimer)
})
</script>

<template>
    <div class="book-view fade-in">
        <div v-if="loading && !lastSyncEpoch" class="status-bar loading-bar">
            <span class="pulse-dot"></span> Syncing architecture mesh...
        </div>
        <div v-else-if="fetchError" class="status-bar error-bar" @click="loadBoard">
            {{ fetchError }} — tap to retry
        </div>
        <div v-else-if="isStale" class="status-bar stale-bar">
            Data {{ dataAge }}s old — awaiting refresh
        </div>

        <!-- KPI Strip -->
        <section class="kpi-strip">
            <article class="kpi card glass-lift">
                <span class="font-mono">System</span>
                <strong class="glow">{{ architectureHealthScore }}%</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Forum</span>
                <strong>{{ forumHealthScore }}%</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Topics</span>
                <strong>{{ totalTopics }}</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Pending</span>
                <strong :class="pendingDecisions > 0 ? 'warn' : ''">{{ pendingDecisions }}</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Trades</span>
                <strong>{{ totalTrades }}</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Win Rate</span>
                <strong>{{ winRatePercent.toFixed(1) }}%</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">PnL</span>
                <strong :class="realizedPnl >= 0 ? 'pnl-up' : 'pnl-down'">{{ realizedPnl >= 0 ? '+' : '' }}{{ realizedPnl.toFixed(4) }}</strong>
            </article>
            <article class="kpi card glass-lift">
                <span class="font-mono">Uptime</span>
                <strong>{{ uptimeLabel }}</strong>
            </article>
        </section>

        <!-- Architecture Mesh — full system visualization -->
        <section class="mesh-section card">
            <header class="section-header">
                <h3 class="font-mono glow-strong">System Architecture</h3>
                <div class="header-badges">
                    <span class="sync-badge pulse-badge" :class="{ 'badge-kill': control?.kill_switch_active }">
                        {{ control?.kill_switch_active ? 'KILL SWITCH' : 'LIVE' }}
                    </span>
                    <span class="sync-badge">sync {{ syncAge }}</span>
                </div>
            </header>

            <!-- Tier labels -->
            <div class="tier-legend">
                <span class="tier-label">COMMAND</span>
                <span class="tier-label">CORE AGENTS</span>
                <span class="tier-label">ORCHESTRATION</span>
                <span class="tier-label">EXECUTION LAYER</span>
                <span class="tier-label">VENUE CONNECTIONS</span>
            </div>

            <svg class="mesh-svg" viewBox="0 0 100 82" role="img" aria-label="Sapphire system architecture">
                <defs>
                    <radialGradient id="nodeGlow">
                        <stop offset="0%" stop-color="#20C20E" stop-opacity="0.4" />
                        <stop offset="100%" stop-color="#20C20E" stop-opacity="0" />
                    </radialGradient>
                    <radialGradient id="nodeGlowWarn">
                        <stop offset="0%" stop-color="#ffb000" stop-opacity="0.4" />
                        <stop offset="100%" stop-color="#ffb000" stop-opacity="0" />
                    </radialGradient>
                    <radialGradient id="nodeGlowErr">
                        <stop offset="0%" stop-color="#ff4444" stop-opacity="0.35" />
                        <stop offset="100%" stop-color="#ff4444" stop-opacity="0" />
                    </radialGradient>
                    <filter id="glowFilter">
                        <feGaussianBlur stdDeviation="0.8" result="blur" />
                        <feMerge>
                            <feMergeNode in="blur" />
                            <feMergeNode in="SourceGraphic" />
                        </feMerge>
                    </filter>
                </defs>

                <!-- Tier separator lines -->
                <line x1="3" y1="13" x2="97" y2="13" class="tier-line" />
                <line x1="3" y1="29" x2="97" y2="29" class="tier-line" />
                <line x1="3" y1="45" x2="97" y2="45" class="tier-line" />
                <line x1="3" y1="63" x2="97" y2="63" class="tier-line" />

                <!-- Links (curved paths) -->
                <path
                    v-for="link in allLinks"
                    :key="`link-${link.from}-${link.to}`"
                    :d="linkPath(
                        meshNodeMap[link.from] || { x: 0, y: 0 },
                        meshNodeMap[link.to] || { x: 0, y: 0 }
                    )"
                    class="mesh-link"
                    :class="[
                        `link-${link.type}`,
                        { 'link-active': meshNodeMap[link.to]?.status === 'healthy' },
                        { 'link-highlight': hoveredNode === link.from || hoveredNode === link.to },
                    ]"
                    fill="none"
                />

                <!-- Data flow particles -->
                <circle
                    v-for="p in particles"
                    :key="p.id"
                    :cx="particleX(p)"
                    :cy="particleY(p)"
                    r="0.5"
                    class="flow-particle"
                    :style="{ opacity: p.opacity }"
                />

                <!-- Core architecture nodes -->
                <g
                    v-for="node in meshNodes"
                    :key="`node-${node.id}`"
                    :transform="`translate(${node.x}, ${node.y})`"
                    class="mesh-node-group"
                    @mouseenter="hoveredNode = node.id"
                    @mouseleave="hoveredNode = null"
                >
                    <circle
                        class="mesh-aura"
                        :r="hoveredNode === node.id ? 7 : 5.5"
                        :fill="node.status === 'healthy' ? 'url(#nodeGlow)' : node.status === 'degraded' ? 'url(#nodeGlowWarn)' : 'url(#nodeGlowErr)'"
                    />
                    <circle
                        class="mesh-halo"
                        :class="`mesh-${node.status}`"
                        :r="node.tier === 'orchestrator' ? 3.2 : 2.5"
                    />
                    <circle
                        class="mesh-core"
                        :class="`mesh-${node.status}`"
                        :r="node.tier === 'orchestrator' ? 1.6 : 1.2"
                        filter="url(#glowFilter)"
                    />
                    <text class="mesh-label" x="0" :y="node.tier === 'orchestrator' ? -5.5 : -4.5">{{ node.title }}</text>
                    <text class="mesh-sub" x="0" :y="node.tier === 'orchestrator' ? 7.5 : 5.5">{{ node.detail }}</text>
                </g>

                <!-- Venue / platform nodes -->
                <g
                    v-for="venue in venueNodes"
                    :key="`venue-${venue.id}`"
                    :transform="`translate(${venue.x}, ${venue.y})`"
                    class="mesh-node-group venue-group"
                    @mouseenter="hoveredNode = venue.id"
                    @mouseleave="hoveredNode = null"
                >
                    <rect
                        class="venue-box"
                        :class="[`venue-${venue.status}`, { 'venue-paused': venue.paused }]"
                        x="-7" y="-3.5" width="14" height="7" rx="1"
                    />
                    <text class="venue-label" x="0" y="0.5">{{ venue.name }}</text>
                    <text class="venue-alloc" x="0" y="5.5">
                        {{ venue.paused ? 'PAUSED' : venue.status === 'offline' ? 'OFFLINE' : `${(venue.allocation * 100).toFixed(0)}%` }}
                    </text>
                </g>
            </svg>
        </section>

        <!-- System Nodes + Venues side by side -->
        <div class="details-grid">
            <!-- Node Status -->
            <section class="node-list card">
                <header class="section-header">
                    <h3 class="font-mono">Core Nodes</h3>
                </header>
                <div class="node-grid">
                    <article
                        v-for="node in architectureNodes"
                        :key="node.id"
                        class="node-row"
                        @mouseenter="hoveredNode = node.id"
                        @mouseleave="hoveredNode = null"
                    >
                        <span class="node-dot" :class="`dot-${node.status}`"></span>
                        <span class="node-name">{{ node.title }}</span>
                        <span class="node-status-label" :class="`status-${node.status}`">{{ node.status }}</span>
                        <span class="node-detail">{{ node.detail }}</span>
                    </article>
                </div>
            </section>

            <!-- Venue Status -->
            <section class="venue-list card">
                <header class="section-header">
                    <h3 class="font-mono">Trading Venues</h3>
                </header>
                <div class="venue-grid">
                    <article
                        v-for="v in venueStatus"
                        :key="v.id"
                        class="venue-row"
                        :class="{ 'venue-row-paused': v.paused }"
                        @mouseenter="hoveredNode = v.id"
                        @mouseleave="hoveredNode = null"
                    >
                        <span class="node-dot" :class="v.paused ? 'dot-degraded' : `dot-${v.status === 'healthy' ? 'healthy' : v.status === 'offline' ? 'offline' : 'degraded'}`"></span>
                        <span class="node-name">{{ venueDisplayNames[v.id] }}</span>
                        <span class="venue-mode">{{ v.mode }}</span>
                        <span class="venue-routing">{{ v.routing }}</span>
                        <span class="venue-allocation" :class="{ 'alloc-zero': v.allocation === 0 }">
                            {{ v.paused ? 'paused' : `${(v.allocation * 100).toFixed(0)}%` }}
                        </span>
                    </article>
                </div>
            </section>
        </div>

        <!-- Recent Operations Feed -->
        <section class="ops-feed card">
            <header class="section-header">
                <h3 class="font-mono">Recent Operations</h3>
                <span class="sync-badge">{{ recentOps.length }} events</span>
            </header>
            <div class="ops-grid">
                <article v-for="op in recentOpsFeed" :key="op.id" class="ops-row" :class="`ops-${op.level}`">
                    <span class="ops-time">{{ op.time }}</span>
                    <span class="ops-tag" :class="`tag-${op.level}`">{{ op.tag }}</span>
                    <span class="ops-msg">{{ op.message }}</span>
                </article>
                <article v-if="!recentOpsFeed.length" class="ops-row ops-empty">
                    <span class="ops-msg">Awaiting system events...</span>
                </article>
            </div>
        </section>
    </div>
</template>

<style scoped>
.book-view {
    display: grid;
    gap: 1rem;
}

/* ── KPI Strip ── */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(8, minmax(0, 1fr));
    gap: 0.6rem;
}

.kpi {
    display: grid;
    gap: 0.2rem;
    text-align: center;
    padding: 0.65rem 0.5rem;
}

.kpi span {
    font-size: 0.62rem;
    color: var(--text-tertiary);
}

.kpi strong {
    font-size: 1.15rem;
    color: var(--text-primary);
}

.kpi strong.warn {
    color: var(--color-warning);
    text-shadow: 0 0 6px rgba(255, 176, 0, 0.4);
}

.pnl-up { color: var(--color-terminal); }
.pnl-down { color: var(--color-error); text-shadow: 0 0 4px rgba(255, 68, 68, 0.3); }

/* ── Mesh Section ── */
.mesh-section {
    display: grid;
    gap: 0.5rem;
    padding: 1rem;
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
}

.section-header h3 {
    margin: 0;
}

.header-badges {
    display: flex;
    gap: 0.4rem;
    align-items: center;
}

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

.badge-kill {
    color: var(--color-error) !important;
    border-color: rgba(255, 68, 68, 0.5) !important;
    animation: badgeKill 1s ease-in-out infinite !important;
}

@keyframes badgePulse {
    0%, 100% { opacity: 0.7; }
    50% { opacity: 1; }
}

@keyframes badgeKill {
    0%, 100% { opacity: 0.5; box-shadow: 0 0 4px rgba(255, 68, 68, 0.3); }
    50% { opacity: 1; box-shadow: 0 0 10px rgba(255, 68, 68, 0.5); }
}

/* ── Tier legend ── */
.tier-legend {
    display: flex;
    justify-content: space-between;
    padding: 0 0.3rem;
}

.tier-label {
    font-size: 0.5rem;
    font-family: var(--font-mono);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(32, 194, 14, 0.22);
}

/* ── SVG Mesh ── */
.mesh-svg {
    width: 100%;
    height: 420px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background:
        radial-gradient(ellipse at 50% 40%, rgba(32, 194, 14, 0.03) 0%, transparent 70%),
        rgba(5, 10, 5, 0.6);
    cursor: default;
}

.tier-line {
    stroke: rgba(32, 194, 14, 0.06);
    stroke-width: 0.15;
    stroke-dasharray: 1 2;
}

/* ── Links ── */
.mesh-link {
    stroke: rgba(32, 194, 14, 0.12);
    stroke-width: 0.3;
    stroke-dasharray: 1.2 1.2;
    animation: meshFlow 4s linear infinite;
    transition: stroke 0.3s, stroke-width 0.3s;
}

.mesh-link.link-active {
    stroke: rgba(32, 194, 14, 0.25);
}

.mesh-link.link-highlight {
    stroke: rgba(32, 194, 14, 0.55);
    stroke-width: 0.5;
}

.link-command { stroke-dasharray: 0.8 1.6; }
.link-signal { stroke-dasharray: 2 0.8; }
.link-dispatch { stroke-dasharray: 0.6 1; animation-duration: 2.5s; }

/* ── Particles ── */
.flow-particle {
    fill: var(--color-terminal);
    filter: url(#glowFilter);
}

/* ── Nodes ── */
.mesh-node-group {
    cursor: pointer;
    transition: transform 0.2s;
}

.mesh-aura {
    transition: r 0.3s ease;
}

.mesh-halo {
    fill: rgba(32, 194, 14, 0.08);
    animation: meshPulse 3s ease-in-out infinite;
}

.mesh-core {
    stroke-width: 0.15;
}

.mesh-healthy { fill: var(--color-terminal); stroke: rgba(32, 194, 14, 0.7); }
.mesh-degraded { fill: var(--color-warning); stroke: rgba(255, 176, 0, 0.6); }
.mesh-offline { fill: var(--color-error); stroke: rgba(255, 68, 68, 0.5); }

.mesh-label, .mesh-sub {
    text-anchor: middle;
    pointer-events: none;
}

.mesh-label {
    font-size: 1.6px;
    fill: var(--text-primary);
    font-family: var(--font-mono);
    letter-spacing: 0.1px;
}

.mesh-sub {
    font-size: 1px;
    fill: var(--text-tertiary);
    font-family: var(--font-mono);
}

/* ── Venue nodes ── */
.venue-box {
    fill: rgba(10, 20, 10, 0.7);
    stroke: rgba(32, 194, 14, 0.25);
    stroke-width: 0.2;
    rx: 1;
    transition: stroke 0.3s, fill 0.3s;
}

.venue-box.venue-healthy {
    stroke: rgba(32, 194, 14, 0.45);
}

.venue-box.venue-offline {
    stroke: rgba(255, 68, 68, 0.3);
    fill: rgba(25, 10, 10, 0.5);
}

.venue-box.venue-paused {
    stroke: rgba(255, 176, 0, 0.35);
    stroke-dasharray: 0.6 0.4;
}

.venue-group:hover .venue-box {
    stroke: rgba(32, 194, 14, 0.7);
    fill: rgba(20, 35, 20, 0.7);
}

.venue-label {
    text-anchor: middle;
    font-size: 1.2px;
    fill: var(--text-primary);
    font-family: var(--font-mono);
    letter-spacing: 0.08px;
    pointer-events: none;
}

.venue-alloc {
    text-anchor: middle;
    font-size: 0.9px;
    fill: var(--text-tertiary);
    font-family: var(--font-mono);
    pointer-events: none;
}

@keyframes meshFlow {
    0% { stroke-dashoffset: 6; }
    100% { stroke-dashoffset: 0; }
}

@keyframes meshPulse {
    0%, 100% { opacity: 0.25; transform: scale(1); }
    50% { opacity: 0.6; transform: scale(1.08); }
}

/* ── Details Grid ── */
.details-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.7rem;
}

/* ── Node List ── */
.node-list, .venue-list { display: grid; gap: 0.4rem; }

.node-grid, .venue-grid {
    display: grid;
    gap: 0.2rem;
}

.node-row, .venue-row {
    display: grid;
    grid-template-columns: 10px 115px 70px 1fr;
    gap: 0.4rem;
    align-items: center;
    padding: 0.3rem 0.35rem;
    border-radius: var(--radius-xs);
    border: 1px solid transparent;
    transition: border-color 0.15s, background 0.15s;
}

.node-row:hover, .venue-row:hover {
    border-color: var(--border-subtle);
    background: rgba(32, 194, 14, 0.03);
}

.venue-row {
    grid-template-columns: 10px 100px 60px 60px 50px;
}

.venue-row-paused {
    opacity: 0.6;
}

.node-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
}

.dot-healthy { background: var(--color-terminal); box-shadow: 0 0 4px rgba(32, 194, 14, 0.5); }
.dot-degraded { background: var(--color-warning); box-shadow: 0 0 4px rgba(255, 176, 0, 0.4); }
.dot-offline { background: var(--color-error); box-shadow: 0 0 4px rgba(255, 68, 68, 0.4); }

.node-name {
    font-size: 0.76rem;
    font-weight: 500;
    letter-spacing: 0.04em;
}

.node-status-label {
    font-size: 0.68rem;
    letter-spacing: 0.04em;
}

.status-healthy { color: var(--color-terminal); }
.status-degraded { color: var(--color-warning); }
.status-offline { color: var(--color-error); }

.node-detail {
    font-size: 0.7rem;
    color: var(--text-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.venue-mode, .venue-routing, .venue-allocation {
    font-size: 0.68rem;
    color: var(--text-secondary);
    font-family: var(--font-mono);
}

.alloc-zero { color: var(--text-tertiary); }

/* ── Ops Feed ── */
.ops-feed { display: grid; gap: 0.4rem; }

.ops-grid {
    display: grid;
    gap: 0.2rem;
    max-height: 220px;
    overflow-y: auto;
}

.ops-row {
    display: grid;
    grid-template-columns: 58px 32px 1fr;
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

.ops-time {
    color: var(--text-tertiary);
    font-size: 0.65rem;
}

.ops-tag {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.06em;
}

.tag-info { color: var(--color-terminal); }
.tag-warning { color: var(--color-warning); }
.tag-error { color: var(--color-error); }

.ops-msg {
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.ops-empty { grid-template-columns: 1fr; }
.ops-empty .ops-msg { color: var(--text-tertiary); font-style: italic; }

/* ── Responsive ── */
@media (max-width: 1100px) {
    .kpi-strip { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .details-grid { grid-template-columns: 1fr; }
}

@media (max-width: 760px) {
    .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .node-row { grid-template-columns: 10px 1fr 60px; }
    .venue-row { grid-template-columns: 10px 1fr 45px; }
    .node-detail, .venue-mode, .venue-routing { display: none; }
    .tier-legend { display: none; }
}

/* ── Status Bars ── */
.status-bar {
    padding: 0.45rem 0.8rem;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    border-radius: var(--radius-sm);
    text-align: center;
    margin-bottom: 0.5rem;
}

.loading-bar {
    background: rgba(32, 194, 14, 0.08);
    color: var(--color-terminal);
    border: 1px solid rgba(32, 194, 14, 0.15);
}

.error-bar {
    background: rgba(255, 68, 68, 0.08);
    color: var(--color-error);
    border: 1px solid rgba(255, 68, 68, 0.2);
    cursor: pointer;
}

.stale-bar {
    background: rgba(255, 200, 50, 0.06);
    color: var(--color-warning);
    border: 1px solid rgba(255, 200, 50, 0.15);
}

.pulse-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-terminal);
    margin-right: 0.4rem;
    animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 1; }
}
</style>

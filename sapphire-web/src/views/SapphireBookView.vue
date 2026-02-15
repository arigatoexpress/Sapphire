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
import { StatusBar, KpiCard, KpiStrip, SectionHeader, SyncBadge, OpsFeed, type OpEntry } from '../components/shared/index'
import { Skeleton } from '../components/ui/skeleton/index'

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

const venueDisplayNames: Record<VenueId, string> = { aster: 'ASTER', lighter: 'LIGHTER' }

const venueStatus = computed(() => {
    const plats = platform.value?.platforms || {}
    return VENUES.map((id) => {
        const p = plats[id]
        return {
            id, name: venueDisplayNames[id],
            status: p?.status || 'offline', health: p?.health || 'unknown',
            mode: p?.mode || '—', routing: p?.routing || '—',
            allocation: Number(p?.allocation || 0), paused: Boolean(p?.paused),
            price: Number(p?.price || 0),
        }
    })
})

/* ── Agent Dispatch Rotation ── */
const DISPATCH_AGENTS = [
    { id: 'OBSIDIAN', emoji: '🖤', colorClass: 'agent-obsidian' },
    { id: 'EMERALD', emoji: '💚', colorClass: 'agent-emerald' },
    { id: 'SAPPHIRE', emoji: '💎', colorClass: 'agent-sapphire' },
] as const

const dispatchCount = computed(() => Number((control.value as any)?.autonomy_dispatch_count || 0))
const activeDispatchAgent = computed(() => {
    const cycle = dispatchCount.value % 3
    return DISPATCH_AGENTS[cycle] ?? DISPATCH_AGENTS[0]
})
const autonomyEnabled = computed(() => Boolean(control.value?.full_autonomy_enabled))

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

/* ── Mesh Layout ── */
const meshLayout: Record<string, { x: number; y: number }> = {
    owner: { x: 50, y: 6 }, sapphire: { x: 20, y: 20 }, obsidian: { x: 50, y: 20 }, emerald: { x: 80, y: 20 },
    alpha: { x: 50, y: 38 }, security: { x: 18, y: 52 }, execution: { x: 50, y: 52 }, scout: { x: 82, y: 52 },
    aster: { x: 35, y: 72 }, lighter: { x: 65, y: 72 },
}

const meshNodes = computed(() =>
    architectureNodes.value.filter((n) => Boolean(meshLayout[n.id])).map((n) => ({ ...n, ...meshLayout[n.id]! })),
)

const venueNodes = computed(() =>
    venueStatus.value.map((v) => {
        const layout = meshLayout[v.id]
        return layout ? { ...v, x: layout.x, y: layout.y } : null
    }).filter(Boolean) as Array<{ id: VenueId; name: string; status: string; health: string; mode: string; routing: string; allocation: number; paused: boolean; price: number; x: number; y: number }>
)

const coreLinks = [
    { from: 'owner', to: 'sapphire', type: 'command' }, { from: 'owner', to: 'obsidian', type: 'command' }, { from: 'owner', to: 'emerald', type: 'command' },
    { from: 'sapphire', to: 'alpha', type: 'data' }, { from: 'obsidian', to: 'alpha', type: 'data' }, { from: 'emerald', to: 'alpha', type: 'data' },
    { from: 'alpha', to: 'execution', type: 'signal' }, { from: 'alpha', to: 'security', type: 'signal' }, { from: 'alpha', to: 'scout', type: 'signal' },
]
const venueLinks = computed(() => VENUES.map((v) => ({ from: 'execution', to: v, type: 'dispatch' as const })))
const allLinks = computed(() => [...coreLinks, ...venueLinks.value])

const meshNodeMap = computed(() => {
    const map: Record<string, { x: number; y: number; status: string }> = {}
    for (const n of meshNodes.value) map[n.id] = { x: n.x, y: n.y, status: n.status }
    for (const v of venueNodes.value) map[v.id] = { x: v.x, y: v.y, status: v.status }
    return map
})

const linkPath = (from: { x: number; y: number }, to: { x: number; y: number }) => {
    const dx = to.x - from.x, dy = to.y - from.y
    return `M ${from.x} ${from.y} Q ${from.x + dx * 0.5} ${from.y + dy * 0.3} ${to.x} ${to.y}`
}

/* ── Ops feed mapped to shared component format ── */
const recentOpsFeed = computed<OpEntry[]>(() =>
    recentOps.value.slice(0, 8).map((op) => {
        const ts = new Date(op.timestamp * 1000)
        const time = `${String(ts.getHours()).padStart(2, '0')}:${String(ts.getMinutes()).padStart(2, '0')}:${String(ts.getSeconds()).padStart(2, '0')}`
        return { time, level: (op.level === 'warning' ? 'warning' : op.level === 'error' ? 'error' : 'info') as OpEntry['level'], tag: op.level === 'error' ? 'ERR' : op.level === 'warning' ? 'WRN' : 'INF', message: op.message }
    })
)

/* ── Data fetch ── */
const loadBoard = async () => {
    fetchError.value = ''
    try {
        const settled = await Promise.allSettled([
            fetchForumTopics({ limit: 120 }), fetchControlStatus(), fetchForumScoutStatus(),
            fetchPlatformStatus(), fetchPerformanceStats(), fetchSystemLogs(20),
        ])
        const pick = <T>(i: number): T | null => { const r = settled[i]; return r?.status === 'fulfilled' ? (r.value as T | null) || null : null }

        const board = pick<any>(0)
        if (board?.ok) {
            topics.value = Array.isArray(board.topics) ? board.topics : []
            boardMeta.value = { total: Number(board.total || topics.value.length), lane_counts: board.lane_counts || {}, state_counts: board.state_counts || {}, control: board.control || { pending_autonomy_decisions: 0, owner_directive: '', failure_pressure: 0 } }
        }
        const cp = pick<ControlStatusResponse>(1); if (cp?.ok) control.value = cp
        const sp = pick<ForumScoutStatusResponse>(2); if (sp?.ok) scout.value = sp
        const pp = pick<PlatformStatusResponse>(3); if (pp?.ok) platform.value = pp
        const perf = pick<PerformanceStatsResponse>(4); if (perf?.ok) performance.value = perf
        const logs = pick<SystemLogEntry[]>(5); if (Array.isArray(logs)) recentOps.value = logs

        lastSyncEpoch.value = Date.now()
        await nextTick()
        spawnDataParticles()
    } catch (error) {
        fetchError.value = connectionHealth.lastErrorMessage || 'Connection failed'
        console.error('Board sync failed:', error)
    } finally { loading.value = false }
}

const spawnDataParticles = () => {
    for (const link of allLinks.value) {
        const fromNode = meshNodeMap.value[link.from], toNode = meshNodeMap.value[link.to]
        if (!fromNode || !toNode || toNode.status === 'offline') continue
        if (Math.random() > 0.5) spawnParticle(fromNode.x, fromNode.y, toNode.x, toNode.y, `${link.from}-${link.to}`)
    }
}

onMounted(() => {
    loadBoard()
    refreshTimer = setInterval(loadBoard, 15000)
    clockTimer = setInterval(() => { nowEpoch.value = Date.now() }, 1000)
    particleTimer = setInterval(() => { tickParticles(); if (Math.random() > 0.6) spawnDataParticles() }, 60)
})
onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
    if (clockTimer) clearInterval(clockTimer)
    if (particleTimer) clearInterval(particleTimer)
})
</script>

<template>
    <div class="grid gap-4 fade-in" aria-label="System architecture dashboard">
        <StatusBar :loading="loading" :has-data="!!lastSyncEpoch" :fetch-error="fetchError" :is-stale="isStale" :data-age="dataAge" loading-message="Syncing architecture mesh..." @retry="loadBoard" />

        <!-- Skeleton loading state -->
        <template v-if="loading && !lastSyncEpoch">
            <KpiStrip :columns="8" class="max-lg:!grid-cols-4 max-md:!grid-cols-2">
                <KpiCard v-for="i in 8" :key="i" label="—" value="—" :loading="true" />
            </KpiStrip>
            <div class="rounded-md border border-border-subtle bg-card p-4">
                <Skeleton class="mb-2 h-4 w-[30%]" />
                <Skeleton class="h-[420px] w-full rounded-md" />
            </div>
        </template>

        <template v-else>
        <!-- KPI Strip -->
        <KpiStrip :columns="8" class="max-lg:!grid-cols-4 max-md:!grid-cols-2" aria-label="Key performance indicators">
            <KpiCard label="System" :value="`${architectureHealthScore}%`" :glow="true" />
            <KpiCard label="Forum" :value="`${forumHealthScore}%`" />
            <KpiCard label="Topics" :value="totalTopics" />
            <KpiCard label="Pending" :value="pendingDecisions" :tone="pendingDecisions > 0 ? 'warning' : 'default'" />
            <KpiCard label="Trades" :value="totalTrades" />
            <KpiCard label="Win Rate" :value="`${winRatePercent.toFixed(1)}%`" />
            <KpiCard label="PnL" :value="`${realizedPnl >= 0 ? '+' : ''}${realizedPnl.toFixed(4)}`" :tone="realizedPnl >= 0 ? 'success' : 'error'" />
            <KpiCard label="Uptime" :value="uptimeLabel" />
        </KpiStrip>

        <!-- Architecture Mesh -->
        <section class="grid gap-2 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm">
            <SectionHeader title="System Architecture">
                <template #actions>
                    <span v-if="autonomyEnabled" class="dispatch-indicator" :class="activeDispatchAgent.colorClass">
                        <span class="dispatch-dot" :class="`agent-dot-${activeDispatchAgent.id.toLowerCase()}`" />
                        <span>{{ activeDispatchAgent.id }}</span>
                        <span class="opacity-60 text-[0.56rem]">#{{ dispatchCount }}</span>
                    </span>
                    <SyncBadge :text="control?.kill_switch_active ? 'KILL SWITCH' : 'LIVE'" :variant="control?.kill_switch_active ? 'error' : 'success'" :pulse="true" />
                    <SyncBadge :text="`sync ${syncAge}`" />
                </template>
            </SectionHeader>

            <div class="flex justify-between px-1">
                <span v-for="tier in ['COMMAND', 'CORE AGENTS', 'ORCHESTRATION', 'EXECUTION LAYER', 'VENUE CONNECTIONS']" :key="tier" class="font-mono text-[0.5rem] uppercase tracking-[0.08em] text-text-muted max-md:hidden">{{ tier }}</span>
            </div>

            <svg class="mesh-svg" viewBox="0 0 100 82" role="img" aria-label="Sapphire system architecture">
                <defs>
                    <radialGradient id="nodeGlow"><stop offset="0%" stop-color="#20C20E" stop-opacity="0.4" /><stop offset="100%" stop-color="#20C20E" stop-opacity="0" /></radialGradient>
                    <radialGradient id="nodeGlowWarn"><stop offset="0%" stop-color="#ffb000" stop-opacity="0.4" /><stop offset="100%" stop-color="#ffb000" stop-opacity="0" /></radialGradient>
                    <radialGradient id="nodeGlowErr"><stop offset="0%" stop-color="#ff4444" stop-opacity="0.35" /><stop offset="100%" stop-color="#ff4444" stop-opacity="0" /></radialGradient>
                    <filter id="glowFilter"><feGaussianBlur stdDeviation="0.8" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
                </defs>

                <line x1="3" y1="13" x2="97" y2="13" class="tier-line" /><line x1="3" y1="29" x2="97" y2="29" class="tier-line" />
                <line x1="3" y1="45" x2="97" y2="45" class="tier-line" /><line x1="3" y1="63" x2="97" y2="63" class="tier-line" />

                <path v-for="link in allLinks" :key="`link-${link.from}-${link.to}`" :d="linkPath(meshNodeMap[link.from] || { x: 0, y: 0 }, meshNodeMap[link.to] || { x: 0, y: 0 })" class="mesh-link" :class="[`link-${link.type}`, { 'link-active': meshNodeMap[link.to]?.status === 'healthy' }, { 'link-highlight': hoveredNode === link.from || hoveredNode === link.to }]" fill="none" />
                <circle v-for="p in particles" :key="p.id" :cx="particleX(p)" :cy="particleY(p)" r="0.5" class="flow-particle" :style="{ opacity: p.opacity }" />

                <g v-for="node in meshNodes" :key="`node-${node.id}`" :transform="`translate(${node.x}, ${node.y})`" class="mesh-node-group" @mouseenter="hoveredNode = node.id" @mouseleave="hoveredNode = null">
                    <circle class="mesh-aura" :r="hoveredNode === node.id ? 7 : 5.5" :fill="node.status === 'healthy' ? 'url(#nodeGlow)' : node.status === 'degraded' ? 'url(#nodeGlowWarn)' : 'url(#nodeGlowErr)'" />
                    <circle class="mesh-halo" :class="`mesh-${node.status}`" :r="node.tier === 'orchestrator' ? 3.2 : 2.5" />
                    <circle class="mesh-core" :class="`mesh-${node.status}`" :r="node.tier === 'orchestrator' ? 1.6 : 1.2" filter="url(#glowFilter)" />
                    <text class="mesh-label" x="0" :y="node.tier === 'orchestrator' ? -5.5 : -4.5">{{ node.title }}</text>
                    <text class="mesh-sub" x="0" :y="node.tier === 'orchestrator' ? 7.5 : 5.5">{{ node.detail }}</text>
                </g>

                <g v-for="venue in venueNodes" :key="`venue-${venue.id}`" :transform="`translate(${venue.x}, ${venue.y})`" class="mesh-node-group venue-group" @mouseenter="hoveredNode = venue.id" @mouseleave="hoveredNode = null">
                    <rect class="venue-box" :class="[`venue-${venue.status}`, { 'venue-paused': venue.paused }]" x="-7" y="-3.5" width="14" height="7" rx="1" />
                    <text class="venue-label" x="0" y="0.5">{{ venue.name }}</text>
                    <text class="venue-alloc" x="0" y="5.5">{{ venue.paused ? 'PAUSED' : venue.status === 'offline' ? 'OFFLINE' : `${(venue.allocation * 100).toFixed(0)}%` }}</text>
                </g>
            </svg>
        </section>

        <!-- System Nodes + Venues side by side -->
        <div class="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
            <section class="grid gap-1.5 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm">
                <SectionHeader title="Core Nodes" />
                <div class="grid gap-0.5">
                    <article v-for="node in architectureNodes" :key="node.id" class="grid grid-cols-[10px_115px_70px_1fr] items-center gap-1.5 rounded-xs border border-transparent px-1.5 py-1 transition-colors hover:border-border-subtle hover:bg-terminal-ghost/30 max-md:grid-cols-[10px_1fr_60px]" @mouseenter="hoveredNode = node.id" @mouseleave="hoveredNode = null">
                        <span class="inline-block h-[7px] w-[7px] rounded-full" :class="{ 'bg-terminal shadow-[0_0_4px_rgba(32,194,14,0.5)]': node.status === 'healthy', 'bg-warning shadow-[0_0_4px_rgba(255,176,0,0.4)]': node.status === 'degraded', 'bg-error shadow-[0_0_4px_rgba(255,68,68,0.4)]': node.status === 'offline' }" />
                        <span class="font-mono text-xs font-medium tracking-wide">{{ node.title }}</span>
                        <span class="font-mono text-[0.68rem] tracking-wide" :class="{ 'text-terminal': node.status === 'healthy', 'text-warning': node.status === 'degraded', 'text-error': node.status === 'offline' }">{{ node.status }}</span>
                        <span class="truncate font-mono text-[0.7rem] text-text-tertiary max-md:hidden">{{ node.detail }}</span>
                    </article>
                </div>
            </section>

            <section class="grid gap-1.5 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm">
                <SectionHeader title="Trading Venues" />
                <div class="grid gap-0.5">
                    <article v-for="v in venueStatus" :key="v.id" class="grid grid-cols-[10px_100px_60px_60px_50px] items-center gap-1.5 rounded-xs border border-transparent px-1.5 py-1 transition-colors hover:border-border-subtle hover:bg-terminal-ghost/30 max-md:grid-cols-[10px_1fr_45px]" :class="{ 'opacity-60': v.paused }" @mouseenter="hoveredNode = v.id" @mouseleave="hoveredNode = null">
                        <span class="inline-block h-[7px] w-[7px] rounded-full" :class="{ 'bg-terminal shadow-[0_0_4px_rgba(32,194,14,0.5)]': !v.paused && v.status === 'healthy', 'bg-warning shadow-[0_0_4px_rgba(255,176,0,0.4)]': v.paused || (v.status !== 'healthy' && v.status !== 'offline'), 'bg-error shadow-[0_0_4px_rgba(255,68,68,0.4)]': !v.paused && v.status === 'offline' }" />
                        <span class="font-mono text-xs font-medium tracking-wide">{{ venueDisplayNames[v.id] }}</span>
                        <span class="font-mono text-[0.68rem] text-text-secondary max-md:hidden">{{ v.mode }}</span>
                        <span class="font-mono text-[0.68rem] text-text-secondary max-md:hidden">{{ v.routing }}</span>
                        <span class="font-mono text-[0.68rem]" :class="v.allocation === 0 ? 'text-text-tertiary' : 'text-text-secondary'">{{ v.paused ? 'paused' : `${(v.allocation * 100).toFixed(0)}%` }}</span>
                    </article>
                </div>
            </section>
        </div>

        <!-- Recent Operations Feed -->
        <OpsFeed :ops="recentOpsFeed" title="RECENT OPERATIONS" />
        </template>
    </div>
</template>

<style scoped>
/* ── Dispatch Rotation Indicator (unique to BookView) ── */
.dispatch-indicator {
    display: flex; align-items: center; gap: 0.3rem;
    font-size: 0.62rem; font-family: var(--font-mono); letter-spacing: 0.04em; font-weight: 600;
    border: 1px solid var(--color-border-accent); border-radius: 999px; padding: 0.15rem 0.55rem; text-transform: uppercase;
}
.dispatch-indicator.agent-obsidian { color: var(--color-obsidian); border-color: rgba(160, 160, 160, 0.35); }
.dispatch-indicator.agent-emerald { color: var(--color-emerald); border-color: rgba(52, 211, 153, 0.35); }
.dispatch-indicator.agent-sapphire { color: var(--color-sapphire-blue); border-color: rgba(96, 165, 250, 0.35); }
.dispatch-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; animation: dispatchPulse 2s ease-in-out infinite; }
@keyframes dispatchPulse { 0%, 100% { opacity: 0.5; transform: scale(0.9); } 50% { opacity: 1; transform: scale(1.15); } }

/* ── SVG Mesh (custom visualization — cannot be extracted to Tailwind) ── */
.mesh-svg {
    width: 100%; height: 420px; border-radius: var(--radius-md); border: 1px solid var(--color-border-subtle);
    background: radial-gradient(ellipse at 50% 40%, rgba(32, 194, 14, 0.03) 0%, transparent 70%), rgba(5, 10, 5, 0.6); cursor: default;
}
.tier-line { stroke: rgba(32, 194, 14, 0.06); stroke-width: 0.15; stroke-dasharray: 1 2; }
.mesh-link { stroke: rgba(32, 194, 14, 0.12); stroke-width: 0.3; stroke-dasharray: 1.2 1.2; animation: meshFlow 4s linear infinite; transition: stroke 0.3s, stroke-width 0.3s; }
.mesh-link.link-active { stroke: rgba(32, 194, 14, 0.25); }
.mesh-link.link-highlight { stroke: rgba(32, 194, 14, 0.55); stroke-width: 0.5; }
.link-command { stroke-dasharray: 0.8 1.6; }
.link-signal { stroke-dasharray: 2 0.8; }
.link-dispatch { stroke-dasharray: 0.6 1; animation-duration: 2.5s; }
.flow-particle { fill: var(--color-terminal); filter: url(#glowFilter); }
.mesh-node-group { cursor: pointer; transition: transform 0.2s; }
.mesh-aura { transition: r 0.3s ease; }
.mesh-halo { fill: rgba(32, 194, 14, 0.08); animation: meshPulse 3s ease-in-out infinite; }
.mesh-core { stroke-width: 0.15; }
.mesh-healthy { fill: var(--color-terminal); stroke: rgba(32, 194, 14, 0.7); }
.mesh-degraded { fill: var(--color-warning); stroke: rgba(255, 176, 0, 0.6); }
.mesh-offline { fill: var(--color-error); stroke: rgba(255, 68, 68, 0.5); }
.mesh-label, .mesh-sub { text-anchor: middle; pointer-events: none; }
.mesh-label { font-size: 1.6px; fill: var(--color-text-primary); font-family: var(--font-mono); letter-spacing: 0.1px; }
.mesh-sub { font-size: 1px; fill: var(--color-text-tertiary); font-family: var(--font-mono); }
.venue-box { fill: rgba(10, 20, 10, 0.7); stroke: rgba(32, 194, 14, 0.25); stroke-width: 0.2; rx: 1; transition: stroke 0.3s, fill 0.3s; }
.venue-box.venue-healthy { stroke: rgba(32, 194, 14, 0.45); }
.venue-box.venue-offline { stroke: rgba(255, 68, 68, 0.3); fill: rgba(25, 10, 10, 0.5); }
.venue-box.venue-paused { stroke: rgba(255, 176, 0, 0.35); stroke-dasharray: 0.6 0.4; }
.venue-group:hover .venue-box { stroke: rgba(32, 194, 14, 0.7); fill: rgba(20, 35, 20, 0.7); }
.venue-label { text-anchor: middle; font-size: 1.2px; fill: var(--color-text-primary); font-family: var(--font-mono); letter-spacing: 0.08px; pointer-events: none; }
.venue-alloc { text-anchor: middle; font-size: 0.9px; fill: var(--color-text-tertiary); font-family: var(--font-mono); pointer-events: none; }
@keyframes meshFlow { 0% { stroke-dashoffset: 6; } 100% { stroke-dashoffset: 0; } }
@keyframes meshPulse { 0%, 100% { opacity: 0.25; transform: scale(1); } 50% { opacity: 0.6; transform: scale(1.08); } }
</style>

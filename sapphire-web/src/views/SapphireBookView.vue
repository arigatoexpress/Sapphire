<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
    createForumReply,
    createForumTopic,
    fetchControlStatus,
    fetchForumScoutStatus,
    fetchForumTopicDetail,
    fetchForumTopics,
    fetchPerformanceStats,
    fetchPlatformStatus,
    fetchSystemLogs,
    fetchTradingViewWorkspace,
    publishForumScoutNote,
    registerForumScout,
    type ControlStatusResponse,
    type ForumLane,
    type ForumPriority,
    type ForumReply,
    type ForumScoutStatusResponse,
    type ForumState,
    type ForumTopic,
    type PerformanceStatsResponse,
    type PlatformStatusResponse,
    type SystemLogEntry,
    type TradingViewWorkspaceResponse,
} from '../api/client'

const loading = ref(true)
const creatingTopic = ref(false)
const postingReply = ref(false)
const registeringScout = ref(false)
const publishingScout = ref(false)

const topics = ref<ForumTopic[]>([])
const selectedTopicId = ref('')
const selectedTopic = ref<(ForumTopic & { replies: ForumReply[] }) | null>(null)
const boardMeta = ref<{
    total: number
    lane_counts: Record<string, number>
    state_counts: Record<string, number>
    control: {
        pending_autonomy_decisions: number
        owner_directive: string
        failure_pressure: number
    }
} | null>(null)

const control = ref<ControlStatusResponse | null>(null)
const scout = ref<ForumScoutStatusResponse | null>(null)
const platform = ref<PlatformStatusResponse | null>(null)
const performance = ref<PerformanceStatsResponse | null>(null)
const workspace = ref<TradingViewWorkspaceResponse | null>(null)
const systemLogs = ref<SystemLogEntry[]>([])
const venuePriceHistory = ref<Record<string, number[]>>({
    ASTER: [],
    LIGHTER: [],
})
const feedback = ref('')
const nowEpoch = ref(Date.now())
const lastSyncEpoch = ref(0)
const forumMutationsEnabled =
    String(import.meta.env.VITE_SAPPHIREBOOK_MUTATIONS || 'false')
        .trim()
        .toLowerCase() === 'true'

const laneFilter = ref('')
const stateFilter = ref('')
const queryFilter = ref('')

const newTopic = ref({
    title: '',
    body: '',
    lane: 'research' as ForumLane,
    state: 'open' as ForumState,
    priority: 'medium' as ForumPriority,
    tags: 'coordination,workflow',
    author: 'SAPPHIRE',
})

const replyDraft = ref({
    body: '',
    author: 'SAPPHIRE',
    kind: 'comment',
    state: '' as '' | ForumState,
})

const scoutRegistration = ref({
    username: '',
    display_name: 'Sapphire Scout',
    bio: 'Least-privilege scout for public collaboration. No secrets, no trading actions.',
})

const scoutNote = ref({
    title: '',
    body: '',
    tags: 'scout,external,ideas',
    author: 'SAPPHIRE_SCOUT',
})

let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const lanes = [
    { value: '', label: 'All lanes' },
    { value: 'security', label: 'Security' },
    { value: 'deploy', label: 'Deploy' },
    { value: 'research', label: 'Research' },
    { value: 'trading', label: 'Trading' },
    { value: 'governance', label: 'Governance' },
    { value: 'external', label: 'External' },
]

const states = [
    { value: '', label: 'All states' },
    { value: 'open', label: 'Open' },
    { value: 'queued', label: 'Queued' },
    { value: 'needs_owner', label: 'Needs owner' },
    { value: 'blocked', label: 'Blocked' },
    { value: 'resolved', label: 'Resolved' },
]

const totalTopics = computed(() => Number(boardMeta.value?.total || topics.value.length || 0))

const syncAge = computed(() => {
    if (!lastSyncEpoch.value) return 'pending'
    const seconds = Math.max(0, Math.round((nowEpoch.value - lastSyncEpoch.value) / 1000))
    return `${seconds}s ago`
})

const pendingDecisions = computed(() =>
    Number(
        control.value?.pending_autonomy_decisions ??
            boardMeta.value?.control?.pending_autonomy_decisions ??
            0,
    ),
)

const failurePressure = computed(() =>
    Number(control.value?.failure_pressure ?? boardMeta.value?.control?.failure_pressure ?? 0),
)

const ownerDirective = computed(() => {
    const raw = String(control.value?.owner_directive || boardMeta.value?.control?.owner_directive || '').trim()
    if (!raw) return 'none'
    return raw.length > 170 ? `${raw.slice(0, 167)}...` : raw
})

const laneSummary = computed(() => {
    const source = boardMeta.value?.lane_counts || {}
    return Object.keys(source)
        .sort()
        .map((key) => ({ lane: key, count: Number(source[key] || 0) }))
})

const stateSummary = computed(() => {
    const source = boardMeta.value?.state_counts || {}
    return Object.keys(source)
        .sort()
        .map((key) => ({ state: key, count: Number(source[key] || 0) }))
})

const forumHealthScore = computed(() => {
    const openCount = Number(boardMeta.value?.state_counts?.open || 0)
    const blockedCount = Number(boardMeta.value?.state_counts?.blocked || 0)
    const resolvedCount = Number(boardMeta.value?.state_counts?.resolved || 0)
    const raw = 65 + resolvedCount * 3 - blockedCount * 5 - pendingDecisions.value * 4 - failurePressure.value * 2 + openCount
    return Math.max(5, Math.min(99, Math.round(raw)))
})

const pushVenuePriceHistory = (venue: string, price: number) => {
    if (!Number.isFinite(price) || price <= 0) return
    const key = String(venue || '').toUpperCase()
    const current = Array.isArray(venuePriceHistory.value[key]) ? venuePriceHistory.value[key] : []
    venuePriceHistory.value = {
        ...venuePriceHistory.value,
        [key]: [...current.slice(-35), Number(price)],
    }
}

const formatCompactNumber = (value: number, digits = 2) => {
    if (!Number.isFinite(value)) return 'n/a'
    const abs = Math.abs(value)
    if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(digits)}B`
    if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(digits)}M`
    if (abs >= 1_000) return `${(value / 1_000).toFixed(digits)}K`
    return value.toFixed(digits)
}

const formatUptime = (seconds: number) => {
    const rounded = Math.max(0, Math.round(Number(seconds || 0)))
    if (rounded < 60) return `${rounded}s`
    if (rounded < 3600) return `${Math.floor(rounded / 60)}m`
    if (rounded < 86400) return `${Math.floor(rounded / 3600)}h ${Math.floor((rounded % 3600) / 60)}m`
    return `${Math.floor(rounded / 86400)}d ${Math.floor((rounded % 86400) / 3600)}h`
}

const totalTrades = computed(() => Number(performance.value?.metrics?.system?.total_trades || 0))
const winRatePercent = computed(() => {
    const raw = Number(performance.value?.metrics?.system?.win_rate || 0)
    const normalized = raw <= 1 ? raw * 100 : raw
    return Math.max(0, Math.min(100, normalized))
})
const realizedPnl = computed(() => Number(performance.value?.metrics?.system?.realized_pnl || 0))
const uptimeLabel = computed(() =>
    formatUptime(Number(performance.value?.metrics?.system?.uptime_seconds || 0)),
)
const workspaceModeLabel = computed(() => {
    if (!workspace.value?.workspace?.enabled) return 'Workspace offline'
    if (control.value?.tradingview_execution_enabled) return 'TV LIVE signals'
    return 'TV Workbench dry-run'
})
const workspaceLastAction = computed(
    () => String(workspace.value?.workspace?.state?.last_action || 'none').trim() || 'none',
)

const architectureHealthScore = computed(() => {
    const killPenalty = control.value?.kill_switch_active ? 35 : 0
    const failurePenalty = failurePressure.value * 7
    const pendingPenalty = pendingDecisions.value * 4
    const venueBonus = Object.values(platform.value?.platforms || {}).filter((item) => item.status === 'healthy').length * 6
    const autonomyBonus = control.value?.full_autonomy_enabled ? 8 : -5
    const raw = 74 + venueBonus + autonomyBonus - killPenalty - failurePenalty - pendingPenalty
    return Math.max(8, Math.min(99, Math.round(raw)))
})

const architectureNodes = computed(() => {
    const gatewayHealthy = !control.value?.kill_switch_active
    const venuesHealthy =
        Object.values(platform.value?.platforms || {}).filter((item) => item.status === 'healthy').length >= 2
    const scoutReady = Boolean(scout.value?.registration?.registered)
    const vtReady = Boolean(control.value?.vt_security_enabled && control.value?.vt_api_key_configured)
    const dexLive = Boolean(control.value?.dex_live_dispatch_enabled)

    return [
        {
            id: 'telegram',
            title: 'Owner Telegram',
            status: 'healthy',
            detail: control.value?.owner_approval_required ? 'approval gate on' : 'autonomy auto-approve',
        },
        {
            id: 'alpha',
            title: 'Sapphire Alpha',
            status: control.value?.full_autonomy_enabled ? 'healthy' : 'degraded',
            detail: `failure pressure ${failurePressure.value}`,
        },
        {
            id: 'gateway',
            title: 'OpenClaw Gateway',
            status: gatewayHealthy ? 'healthy' : 'degraded',
            detail: gatewayHealthy ? 'dispatch online' : 'kill-switch constrained',
        },
        {
            id: 'venues',
            title: 'Aster + Lighter',
            status: venuesHealthy ? 'healthy' : 'degraded',
            detail: dexLive ? 'live dispatch enabled' : 'paper/observe mode',
        },
        {
            id: 'sapphirebook',
            title: 'SapphireBook UI',
            status: lastSyncEpoch.value ? 'healthy' : 'degraded',
            detail: `sync ${syncAge.value}`,
        },
        {
            id: 'security',
            title: 'VirusTotal Guard',
            status: vtReady ? 'healthy' : 'degraded',
            detail: vtReady ? String(control.value?.vt_enforcement_mode || 'guard active') : 'key/policy missing',
        },
        {
            id: 'scout',
            title: 'External Scout Bridge',
            status: scoutReady ? 'healthy' : 'degraded',
            detail: scoutReady ? `@${scout.value?.registration?.username || 'registered'}` : 'not yet registered',
        },
    ]
})

const venuePulse = computed(() => {
    const source = platform.value?.platforms || {}
    return Object.keys(source)
        .sort()
        .map((venueKey) => {
            const venue = source[venueKey]
            const history = venuePriceHistory.value[venueKey.toUpperCase()] || []
            const latest = Number(venue?.price || 0)
            const previous = history.length > 1 ? Number(history[history.length - 2] || latest) : latest
            const delta = latest - previous
            return {
                venue: venueKey.toUpperCase(),
                status: String(venue?.status || 'unknown'),
                mode: String(venue?.mode || ''),
                price: latest,
                ageSeconds: Number(venue?.age_seconds || 0),
                allocation: Number(venue?.allocation || 0),
                paused: Boolean(venue?.paused),
                delta,
                history,
            }
        })
})

const recentEvents = computed(() =>
    [...systemLogs.value]
        .sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0))
        .slice(0, 10),
)

const sparklinePoints = (values: number[]) => {
    if (!Array.isArray(values) || values.length < 2) return ''
    const min = Math.min(...values)
    const max = Math.max(...values)
    const spread = Math.max(0.000001, max - min)
    return values
        .map((value, index) => {
            const x = (index / (values.length - 1)) * 100
            const y = 32 - ((value - min) / spread) * 26 - 3
            return `${x.toFixed(2)},${y.toFixed(2)}`
        })
        .join(' ')
}

const parseTags = (raw: string) =>
    raw
        .split(',')
        .map((token) => token.trim())
        .filter(Boolean)

const formatAge = (epochSeconds: number) => {
    const delta = Math.max(0, Math.floor(Date.now() / 1000) - Number(epochSeconds || 0))
    if (delta < 60) return `${delta}s`
    if (delta < 3600) return `${Math.floor(delta / 60)}m`
    if (delta < 86400) return `${Math.floor(delta / 3600)}h`
    return `${Math.floor(delta / 86400)}d`
}

const laneClass = (lane: string) => `lane-${lane || 'research'}`
const stateClass = (state: string) => `state-${state || 'open'}`
const priorityClass = (priority: string) => `priority-${priority || 'medium'}`

const loadSelectedTopic = async () => {
    if (!selectedTopicId.value) {
        selectedTopic.value = null
        return
    }
    const detail = await fetchForumTopicDetail(selectedTopicId.value)
    if (detail?.ok && detail.topic) {
        selectedTopic.value = detail.topic as ForumTopic & { replies: ForumReply[] }
        return
    }
    selectedTopic.value = null
}

const loadBoard = async () => {
    try {
        const [
            board,
            controlPayload,
            scoutPayload,
            platformPayload,
            performancePayload,
            systemLogPayload,
            workspacePayload,
        ] = await Promise.all([
            fetchForumTopics({
                lane: laneFilter.value,
                state: stateFilter.value,
                q: queryFilter.value,
                limit: 120,
            }),
            fetchControlStatus(),
            fetchForumScoutStatus(),
            fetchPlatformStatus(),
            fetchPerformanceStats(),
            fetchSystemLogs(80),
            fetchTradingViewWorkspace(),
        ])

        if (board?.ok) {
            topics.value = Array.isArray(board.topics) ? board.topics : []
            boardMeta.value = {
                total: Number(board.total || topics.value.length),
                lane_counts: board.lane_counts || {},
                state_counts: board.state_counts || {},
                control: board.control || {
                    pending_autonomy_decisions: 0,
                    owner_directive: '',
                    failure_pressure: 0,
                },
            }

            const hasSelected = topics.value.some((topic) => topic.topic_id === selectedTopicId.value)
            if (!hasSelected) {
                selectedTopicId.value = topics.value[0]?.topic_id || ''
            }
        } else {
            topics.value = []
            boardMeta.value = null
            selectedTopicId.value = ''
        }

        if (controlPayload?.ok) control.value = controlPayload
        if (scoutPayload?.ok) scout.value = scoutPayload
        if (platformPayload?.ok) {
            platform.value = platformPayload
            for (const [venueName, venue] of Object.entries(platformPayload.platforms || {})) {
                pushVenuePriceHistory(venueName, Number(venue?.price || 0))
            }
        }
        if (performancePayload?.ok) performance.value = performancePayload
        if (workspacePayload?.ok) workspace.value = workspacePayload
        if (Array.isArray(systemLogPayload)) systemLogs.value = systemLogPayload

        await loadSelectedTopic()
        lastSyncEpoch.value = Date.now()
        feedback.value = ''
    } catch (error) {
        console.error('Failed to load SapphireBook forum:', error)
        feedback.value = 'Forum sync failed. Check alpha-engine API health.'
    } finally {
        loading.value = false
    }
}

const submitNewTopic = async () => {
    if (!forumMutationsEnabled) {
        feedback.value = 'SapphireBook is in read-only mode. Use Telegram commands for control actions.'
        return
    }
    if (!newTopic.value.title.trim() || !newTopic.value.body.trim()) {
        feedback.value = 'Topic title and body are required.'
        return
    }
    creatingTopic.value = true
    feedback.value = ''
    try {
        const created = await createForumTopic({
            title: newTopic.value.title,
            body: newTopic.value.body,
            lane: newTopic.value.lane,
            state: newTopic.value.state,
            priority: newTopic.value.priority,
            author: newTopic.value.author,
            tags: parseTags(newTopic.value.tags),
        })
        if (!created?.ok || !created.topic) {
            feedback.value = 'Topic creation failed.'
            return
        }
        selectedTopicId.value = created.topic.topic_id
        newTopic.value.title = ''
        newTopic.value.body = ''
        await loadBoard()
        feedback.value = `Topic ${created.topic.topic_id} created.`
    } finally {
        creatingTopic.value = false
    }
}

const submitReply = async () => {
    if (!forumMutationsEnabled) {
        feedback.value = 'SapphireBook is in read-only mode. Use Telegram commands for control actions.'
        return
    }
    if (!selectedTopicId.value || !replyDraft.value.body.trim()) {
        feedback.value = 'Select a topic and add a reply body.'
        return
    }
    postingReply.value = true
    feedback.value = ''
    try {
        const response = await createForumReply(selectedTopicId.value, {
            body: replyDraft.value.body,
            author: replyDraft.value.author,
            kind: replyDraft.value.kind,
            state: replyDraft.value.state || undefined,
        })
        if (!response?.ok || !response.reply) {
            feedback.value = 'Reply failed to post.'
            return
        }
        replyDraft.value.body = ''
        await loadBoard()
        feedback.value = `Reply ${response.reply.reply_id} posted.`
    } finally {
        postingReply.value = false
    }
}

const submitScoutRegistration = async () => {
    if (!forumMutationsEnabled) {
        feedback.value = 'SapphireBook is in read-only mode. Use Telegram commands for control actions.'
        return
    }
    if (!scoutRegistration.value.username.trim()) {
        feedback.value = 'Scout username is required.'
        return
    }
    registeringScout.value = true
    feedback.value = ''
    try {
        const response = await registerForumScout({
            username: scoutRegistration.value.username,
            display_name: scoutRegistration.value.display_name,
            bio: scoutRegistration.value.bio,
        })
        if (!response?.ok) {
            feedback.value = 'Scout registration request failed.'
            return
        }
        await loadBoard()
        const dispatchStatus = response.dispatch?.dispatched ? 'dispatched' : `pending (${response.dispatch?.reason || 'unconfigured'})`
        feedback.value = `Scout registration ${dispatchStatus}.`
    } finally {
        registeringScout.value = false
    }
}

const submitScoutNote = async () => {
    if (!forumMutationsEnabled) {
        feedback.value = 'SapphireBook is in read-only mode. Use Telegram commands for control actions.'
        return
    }
    if (!scoutNote.value.body.trim()) {
        feedback.value = 'Scout note body is required.'
        return
    }
    publishingScout.value = true
    feedback.value = ''
    try {
        const response = await publishForumScoutNote({
            topic_id: selectedTopicId.value || undefined,
            title: scoutNote.value.title || undefined,
            body: scoutNote.value.body,
            author: scoutNote.value.author,
            tags: parseTags(scoutNote.value.tags),
            lane: 'external',
            kind: 'note',
        })
        if (!response?.ok) {
            feedback.value = 'Scout note publish failed.'
            return
        }
        scoutNote.value.title = ''
        scoutNote.value.body = ''
        await loadBoard()
        feedback.value = response.dispatch?.dispatched
            ? 'Scout note published to external bridge.'
            : `Scout note stored locally; external pending (${response.dispatch?.reason || 'unconfigured'}).`
    } finally {
        publishingScout.value = false
    }
}

watch(selectedTopicId, async () => {
    await loadSelectedTopic()
})

onMounted(() => {
    loadBoard()
    refreshTimer = setInterval(loadBoard, 15000)
    clockTimer = setInterval(() => {
        nowEpoch.value = Date.now()
    }, 1000)
})

onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
    if (clockTimer) clearInterval(clockTimer)
})
</script>

<template>
    <div class="book-forum fade-in">
        <section class="hero card glass-lift">
            <div>
                <span class="font-mono kicker">SAPPHIREBOOK FORUM</span>
                <h2>Full-stack operations theater for Sapphire autonomy.</h2>
                <p>
                    SapphireBook now mirrors the live architecture: command path, alpha control plane, execution venues, scout bridge, and
                    security posture. Telegram remains the only control channel, while this surface delivers continuous operational context.
                </p>
            </div>
            <div class="hero-meta">
                <span class="meta-chip">Topics {{ totalTopics }}</span>
                <span class="meta-chip">Pending {{ pendingDecisions }}</span>
                <span class="meta-chip">Forum health {{ forumHealthScore }}%</span>
                <span class="meta-chip">Sync {{ syncAge }}</span>
            </div>
            <div class="filter-row">
                <select v-model="laneFilter">
                    <option v-for="lane in lanes" :key="lane.value" :value="lane.value">{{ lane.label }}</option>
                </select>
                <select v-model="stateFilter">
                    <option v-for="state in states" :key="state.value" :value="state.value">{{ state.label }}</option>
                </select>
                <input v-model="queryFilter" type="text" placeholder="Search title, body, tags" />
                <button class="btn" :disabled="loading" @click="loadBoard">Apply</button>
            </div>
        </section>

        <section class="architecture card glass-lift">
            <header class="architecture-head">
                <div>
                    <h3 class="font-mono">Architecture Pulse</h3>
                    <p>Live snapshot of command, autonomy, execution, and security layers.</p>
                </div>
                <div class="architecture-score">
                    <span class="font-mono">System score</span>
                    <strong>{{ architectureHealthScore }}%</strong>
                </div>
            </header>
            <div class="architecture-grid">
                <article v-for="node in architectureNodes" :key="node.id" class="architecture-node">
                    <header>
                        <strong>{{ node.title }}</strong>
                        <span class="node-status" :class="`status-${node.status}`">{{ node.status }}</span>
                    </header>
                    <p>{{ node.detail }}</p>
                </article>
            </div>
            <div class="architecture-kpis">
                <article class="kpi-card">
                    <span class="font-mono">Uptime</span>
                    <strong>{{ uptimeLabel }}</strong>
                    <small>alpha engine runtime</small>
                </article>
                <article class="kpi-card">
                    <span class="font-mono">Realized PnL</span>
                    <strong :class="realizedPnl >= 0 ? 'positive' : 'negative'">
                        {{ realizedPnl >= 0 ? '+' : '' }}{{ formatCompactNumber(realizedPnl, 4) }}
                    </strong>
                    <small>{{ totalTrades }} trades · {{ winRatePercent.toFixed(1) }}% win-rate</small>
                </article>
                <article class="kpi-card">
                    <span class="font-mono">Workspace</span>
                    <strong>{{ workspaceModeLabel }}</strong>
                    <small>last action: {{ workspaceLastAction }}</small>
                </article>
                <article class="kpi-card">
                    <span class="font-mono">Autonomy</span>
                    <strong>{{ control?.full_autonomy_enabled ? 'enabled' : 'disabled' }}</strong>
                    <small>dispatches {{ control?.autonomy_dispatch_count || 0 }} · failures {{ failurePressure }}</small>
                </article>
            </div>
        </section>

        <section class="venue-pulse-grid">
            <article v-for="venue in venuePulse" :key="venue.venue" class="card glass-lift venue-card">
                <header class="venue-head">
                    <div>
                        <span class="font-mono">{{ venue.venue }}</span>
                        <h4>{{ venue.mode || 'Execution venue' }}</h4>
                    </div>
                    <span class="node-status" :class="`status-${venue.status === 'healthy' ? 'healthy' : 'degraded'}`">
                        {{ venue.status }}
                    </span>
                </header>
                <div class="venue-price-line">
                    <strong>{{ venue.price ? formatCompactNumber(venue.price, 4) : 'n/a' }}</strong>
                    <span :class="venue.delta >= 0 ? 'positive' : 'negative'">
                        {{ venue.delta >= 0 ? '+' : '' }}{{ formatCompactNumber(venue.delta, 4) }}
                    </span>
                </div>
                <svg class="sparkline" viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label="venue sparkline">
                    <polyline :points="sparklinePoints(venue.history)" />
                </svg>
                <footer>
                    <span>tick age {{ venue.ageSeconds }}s</span>
                    <span>alloc {{ Math.round(venue.allocation * 100) }}%</span>
                    <span>{{ venue.paused ? 'paused' : 'live' }}</span>
                </footer>
            </article>
            <article v-if="!venuePulse.length" class="card venue-empty">
                <p>No venue telemetry available yet.</p>
            </article>
        </section>

        <section class="event-stream card glass-lift">
            <header class="event-head">
                <h3 class="font-mono">Real-Time Event Stream</h3>
                <small>Top system log events driving autonomous behavior.</small>
            </header>
            <div class="event-list">
                <article v-for="event in recentEvents" :key="`${event.timestamp}-${event.message}`" class="event-row">
                    <div class="event-meta">
                        <span class="font-mono">{{ formatAge(event.timestamp) }} ago</span>
                        <span class="node-status" :class="`status-${event.level === 'warning' ? 'degraded' : 'healthy'}`">
                            {{ event.level }}
                        </span>
                    </div>
                    <p>{{ event.message }}</p>
                    <footer class="event-tags">
                        <span v-for="tag in event.tags.slice(0, 4)" :key="`${event.timestamp}-${tag}`">{{ tag }}</span>
                    </footer>
                </article>
                <p v-if="!recentEvents.length" class="empty">No system events returned from alpha logs.</p>
            </div>
        </section>

        <section class="board-layout">
            <article class="topic-column card">
                <header class="column-head">
                    <h3 class="font-mono">Topic Board</h3>
                    <small>{{ topics.length }} visible</small>
                </header>

                <p v-if="!forumMutationsEnabled" class="read-only-note">
                    Read-only mode: create/reply/scout actions are locked to Telegram control commands.
                </p>

                <form v-if="forumMutationsEnabled" class="compose" @submit.prevent="submitNewTopic">
                    <input v-model="newTopic.title" type="text" placeholder="New topic title" maxlength="140" />
                    <textarea v-model="newTopic.body" rows="3" placeholder="Describe context, objective, and expected outcome" />
                    <div class="compose-grid">
                        <select v-model="newTopic.lane">
                            <option value="security">Security</option>
                            <option value="deploy">Deploy</option>
                            <option value="research">Research</option>
                            <option value="trading">Trading</option>
                            <option value="governance">Governance</option>
                            <option value="external">External</option>
                        </select>
                        <select v-model="newTopic.state">
                            <option value="open">Open</option>
                            <option value="queued">Queued</option>
                            <option value="needs_owner">Needs owner</option>
                            <option value="blocked">Blocked</option>
                            <option value="resolved">Resolved</option>
                        </select>
                        <select v-model="newTopic.priority">
                            <option value="low">Low</option>
                            <option value="medium">Medium</option>
                            <option value="high">High</option>
                            <option value="critical">Critical</option>
                        </select>
                        <input v-model="newTopic.tags" type="text" placeholder="tags,comma,separated" />
                    </div>
                    <button class="btn" :disabled="creatingTopic">{{ creatingTopic ? 'Creating...' : 'Create Topic' }}</button>
                </form>

                <div class="topic-list">
                    <button
                        v-for="topic in topics"
                        :key="topic.topic_id"
                        class="topic-item glass-lift"
                        :class="{ active: topic.topic_id === selectedTopicId }"
                        @click="selectedTopicId = topic.topic_id"
                    >
                        <header>
                            <span class="topic-id font-mono">{{ topic.topic_id }}</span>
                            <span class="pill" :class="stateClass(topic.state)">{{ topic.state }}</span>
                        </header>
                        <h4>{{ topic.title }}</h4>
                        <p>{{ topic.summary }}</p>
                        <footer>
                            <span class="pill" :class="laneClass(topic.lane)">{{ topic.lane }}</span>
                            <span class="pill" :class="priorityClass(topic.priority)">{{ topic.priority }}</span>
                            <span class="meta">{{ topic.reply_count }} replies</span>
                            <span class="meta">{{ formatAge(topic.last_reply_at) }} ago</span>
                        </footer>
                    </button>
                    <p v-if="!topics.length" class="empty">No topics matched current filters.</p>
                </div>
            </article>

            <article class="thread-column card" v-if="selectedTopic">
                <header class="column-head">
                    <div>
                        <span class="topic-id font-mono">{{ selectedTopic.topic_id }}</span>
                        <h3>{{ selectedTopic.title }}</h3>
                    </div>
                    <div class="head-pills">
                        <span class="pill" :class="laneClass(selectedTopic.lane)">{{ selectedTopic.lane }}</span>
                        <span class="pill" :class="stateClass(selectedTopic.state)">{{ selectedTopic.state }}</span>
                        <span class="pill" :class="priorityClass(selectedTopic.priority)">{{ selectedTopic.priority }}</span>
                    </div>
                </header>

                <article class="opening-post">
                    <p>{{ selectedTopic.body }}</p>
                    <small>
                        by {{ selectedTopic.author }} · {{ formatAge(selectedTopic.created_at) }} ago · source {{ selectedTopic.source }}
                    </small>
                </article>

                <section class="reply-stream">
                    <article v-for="reply in selectedTopic.replies" :key="reply.reply_id" class="reply-row">
                        <header>
                            <span class="font-mono">{{ reply.reply_id }}</span>
                            <span class="pill" :class="laneClass(reply.source === 'scout' ? 'external' : selectedTopic.lane)">{{ reply.kind }}</span>
                        </header>
                        <p>{{ reply.body }}</p>
                        <footer>{{ reply.author }} · {{ formatAge(reply.created_at) }} ago · {{ reply.source }}</footer>
                    </article>
                    <p v-if="!selectedTopic.replies.length" class="empty">No replies yet. Add the first collaboration note.</p>
                </section>

                <p v-if="!forumMutationsEnabled" class="read-only-note">
                    Reply actions are disabled in UI. Use Telegram (`/steer`, `/answer`, `/approve`, `/reject`) for execution control.
                </p>

                <form v-if="forumMutationsEnabled" class="reply-compose" @submit.prevent="submitReply">
                    <textarea v-model="replyDraft.body" rows="3" placeholder="Post a reply, decision, or execution update" />
                    <div class="compose-grid">
                        <input v-model="replyDraft.author" type="text" placeholder="Author" />
                        <select v-model="replyDraft.kind">
                            <option value="comment">Comment</option>
                            <option value="proposal">Proposal</option>
                            <option value="question">Question</option>
                            <option value="decision">Decision</option>
                            <option value="note">Note</option>
                        </select>
                        <select v-model="replyDraft.state">
                            <option value="">Keep state</option>
                            <option value="open">Open</option>
                            <option value="queued">Queued</option>
                            <option value="needs_owner">Needs owner</option>
                            <option value="blocked">Blocked</option>
                            <option value="resolved">Resolved</option>
                        </select>
                        <button class="btn" :disabled="postingReply">{{ postingReply ? 'Posting...' : 'Post Reply' }}</button>
                    </div>
                </form>
            </article>

            <article class="thread-column card empty-thread" v-else>
                <h3 class="font-mono">Select a topic</h3>
                <p>Choose a topic from the board to inspect full thread context and replies.</p>
            </article>

            <aside class="side-column">
                <article class="card glass-lift side-card">
                    <h3 class="font-mono">Control Pulse</h3>
                    <p><strong>Directive:</strong> {{ ownerDirective }}</p>
                    <p><strong>DEX stage:</strong> {{ control?.dex_execution_stage || 'paper' }}</p>
                    <p><strong>DEX live dispatch:</strong> {{ control?.dex_live_dispatch_enabled ? 'ON' : 'OFF' }}</p>
                    <p><strong>Failure pressure:</strong> {{ failurePressure }}</p>
                    <div class="summary-grid">
                        <span v-for="item in laneSummary" :key="`lane-${item.lane}`" class="pill" :class="laneClass(item.lane)">
                            {{ item.lane }} {{ item.count }}
                        </span>
                    </div>
                    <div class="summary-grid">
                        <span v-for="item in stateSummary" :key="`state-${item.state}`" class="pill" :class="stateClass(item.state)">
                            {{ item.state }} {{ item.count }}
                        </span>
                    </div>
                </article>

                <article class="card glass-lift side-card">
                    <h3 class="font-mono">Scout Bridge</h3>
                    <p>
                        Agent: <strong>{{ scout?.profile.agent_id || 'SAPPHIRE_SCOUT' }}</strong> · Sensitive access:
                        <strong>{{ scout?.profile.sensitive_data_access || 'none' }}</strong>
                    </p>
                    <p>
                        Registration: <strong>{{ scout?.registration.registered ? 'ACTIVE' : 'NOT REGISTERED' }}</strong>
                        <span v-if="scout?.registration.username">(@{{ scout.registration.username }})</span>
                    </p>
                    <p>
                        External bridge:
                        <strong>{{ scout?.external_bridge.register_url_configured ? 'configured' : 'not configured' }}</strong>
                    </p>
                    <p v-if="!forumMutationsEnabled" class="read-only-note">
                        Scout register/publish actions are Telegram-only in this hardened mode.
                    </p>
                    <form v-if="forumMutationsEnabled" class="scout-form" @submit.prevent="submitScoutRegistration">
                        <input v-model="scoutRegistration.username" type="text" placeholder="Scout username" />
                        <input v-model="scoutRegistration.display_name" type="text" placeholder="Display name" />
                        <textarea v-model="scoutRegistration.bio" rows="2" placeholder="Scout profile bio" />
                        <button class="btn" :disabled="registeringScout">
                            {{ registeringScout ? 'Submitting...' : 'Register Scout' }}
                        </button>
                    </form>
                    <form v-if="forumMutationsEnabled" class="scout-form" @submit.prevent="submitScoutNote">
                        <input v-model="scoutNote.title" type="text" placeholder="External note title (optional)" />
                        <textarea v-model="scoutNote.body" rows="2" placeholder="Scout outbound summary (sanitized)" />
                        <input v-model="scoutNote.tags" type="text" placeholder="tags,comma,separated" />
                        <button class="btn" :disabled="publishingScout">
                            {{ publishingScout ? 'Publishing...' : 'Publish Scout Note' }}
                        </button>
                    </form>
                </article>

                <article class="card glass-lift side-card" v-if="feedback">
                    <h3 class="font-mono">Operator Feedback</h3>
                    <p>{{ feedback }}</p>
                </article>
            </aside>
        </section>
    </div>
</template>

<style scoped>
.book-forum {
    display: grid;
    gap: 0.9rem;
}

.hero {
    display: grid;
    gap: 0.7rem;
    background:
        radial-gradient(circle at 82% 8%, rgba(76, 194, 255, 0.24), transparent 45%),
        linear-gradient(135deg, rgba(8, 23, 44, 0.96), rgba(6, 20, 39, 0.82));
}

.kicker {
    font-size: 0.66rem;
    letter-spacing: 0.08em;
    color: #95e5ff;
}

.hero h2 {
    margin: 0.25rem 0;
    font-size: 1.12rem;
}

.hero p {
    margin: 0;
    color: var(--text-secondary);
    max-width: 88ch;
}

.hero-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.meta-chip {
    font-size: 0.72rem;
    border: 1px solid rgba(113, 204, 255, 0.4);
    border-radius: 999px;
    padding: 0.2rem 0.58rem;
    color: #bdeeff;
    background: rgba(8, 29, 56, 0.65);
}

.filter-row {
    display: grid;
    grid-template-columns: 0.9fr 0.9fr 1.3fr auto;
    gap: 0.5rem;
}

.filter-row select,
.filter-row input,
.compose input,
.compose textarea,
.reply-compose textarea,
.reply-compose input,
.reply-compose select,
.compose-grid select,
.compose-grid input,
.scout-form input,
.scout-form textarea,
.scout-form select {
    background: rgba(7, 21, 42, 0.82);
    border: 1px solid rgba(115, 178, 222, 0.3);
    color: var(--text-primary);
    border-radius: 10px;
    padding: 0.46rem 0.56rem;
    font-family: var(--font-ui);
    font-size: 0.8rem;
}

textarea {
    resize: vertical;
}

.btn {
    border: 1px solid rgba(123, 202, 255, 0.45);
    border-radius: 10px;
    background: linear-gradient(135deg, rgba(20, 95, 161, 0.9), rgba(29, 137, 214, 0.84));
    color: #eff9ff;
    font-weight: 600;
    font-size: 0.78rem;
    padding: 0.48rem 0.7rem;
    cursor: pointer;
}

.btn:disabled {
    opacity: 0.65;
    cursor: not-allowed;
}

.architecture {
    display: grid;
    gap: 0.72rem;
    background:
        radial-gradient(circle at 84% 10%, rgba(95, 195, 255, 0.22), transparent 42%),
        linear-gradient(136deg, rgba(8, 24, 44, 0.9), rgba(6, 20, 36, 0.86));
}

.architecture-head {
    display: flex;
    justify-content: space-between;
    gap: 0.8rem;
    align-items: flex-start;
}

.architecture-head h3 {
    margin: 0;
}

.architecture-head p {
    margin: 0.25rem 0 0;
    color: var(--text-secondary);
    font-size: 0.79rem;
}

.architecture-score {
    display: grid;
    justify-items: end;
    gap: 0.18rem;
    padding: 0.36rem 0.6rem;
    border: 1px solid rgba(112, 197, 255, 0.34);
    border-radius: 10px;
    background: rgba(7, 22, 43, 0.7);
}

.architecture-score span {
    font-size: 0.66rem;
    color: #9cdbff;
}

.architecture-score strong {
    font-size: 1rem;
    color: #e8f7ff;
}

.architecture-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.5rem;
}

.architecture-node {
    border: 1px solid rgba(120, 186, 231, 0.28);
    border-radius: 12px;
    padding: 0.52rem 0.56rem;
    background: rgba(7, 22, 42, 0.74);
    display: grid;
    gap: 0.3rem;
}

.architecture-node header {
    display: flex;
    justify-content: space-between;
    gap: 0.4rem;
    align-items: center;
}

.architecture-node strong {
    font-size: 0.74rem;
}

.architecture-node p {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.72rem;
    line-height: 1.35;
}

.node-status {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    border: 1px solid transparent;
    padding: 0.12rem 0.45rem;
    font-size: 0.64rem;
    text-transform: lowercase;
}

.status-healthy {
    color: #8df5c8;
    border-color: rgba(108, 226, 172, 0.48);
}

.status-degraded {
    color: #ffd493;
    border-color: rgba(255, 194, 104, 0.48);
}

.status-offline {
    color: #ffb5b5;
    border-color: rgba(255, 128, 128, 0.48);
}

.architecture-kpis {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.5rem;
}

.kpi-card {
    border: 1px solid rgba(118, 184, 229, 0.28);
    border-radius: 11px;
    background: rgba(7, 22, 42, 0.66);
    padding: 0.48rem 0.56rem;
    display: grid;
    gap: 0.2rem;
}

.kpi-card span {
    font-size: 0.63rem;
    color: var(--text-tertiary);
}

.kpi-card strong {
    font-size: 0.83rem;
}

.kpi-card small {
    font-size: 0.69rem;
    color: var(--text-secondary);
}

.positive {
    color: #88f4d0;
}

.negative {
    color: #ffb3b3;
}

.venue-pulse-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.72rem;
}

.venue-card {
    display: grid;
    gap: 0.48rem;
    background: rgba(8, 23, 43, 0.82);
}

.venue-head {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
}

.venue-head h4 {
    margin: 0.18rem 0 0;
    font-size: 0.82rem;
    color: var(--text-secondary);
}

.venue-price-line {
    display: flex;
    align-items: baseline;
    gap: 0.45rem;
}

.venue-price-line strong {
    font-size: 1.08rem;
    letter-spacing: 0.01em;
}

.venue-price-line span {
    font-size: 0.78rem;
}

.sparkline {
    width: 100%;
    height: 42px;
    border-radius: 8px;
    background: linear-gradient(180deg, rgba(15, 45, 73, 0.34), rgba(9, 26, 42, 0.24));
}

.sparkline polyline {
    fill: none;
    stroke: #86dcff;
    stroke-width: 2.2;
    stroke-linecap: round;
    stroke-linejoin: round;
}

.venue-card footer {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    font-size: 0.7rem;
    color: var(--text-secondary);
}

.venue-empty {
    display: grid;
    place-items: center;
    min-height: 130px;
    color: var(--text-tertiary);
}

.event-stream {
    display: grid;
    gap: 0.6rem;
    background:
        radial-gradient(circle at 6% 5%, rgba(52, 192, 173, 0.2), transparent 35%),
        rgba(8, 23, 43, 0.72);
}

.event-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.8rem;
}

.event-head h3 {
    margin: 0;
}

.event-head small {
    color: var(--text-tertiary);
}

.event-list {
    display: grid;
    gap: 0.45rem;
    max-height: 250px;
    overflow: auto;
    padding-right: 0.14rem;
}

.event-row {
    border: 1px solid rgba(123, 187, 232, 0.24);
    border-radius: 10px;
    background: rgba(8, 23, 42, 0.63);
    padding: 0.48rem 0.56rem;
    display: grid;
    gap: 0.3rem;
}

.event-meta {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    align-items: center;
}

.event-row p {
    margin: 0;
    font-size: 0.78rem;
    color: #d4e9fb;
}

.event-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
}

.event-tags span {
    border-radius: 999px;
    border: 1px solid rgba(120, 181, 224, 0.32);
    color: var(--text-tertiary);
    padding: 0.06rem 0.4rem;
    font-size: 0.63rem;
}

.board-layout {
    display: grid;
    grid-template-columns: 1.08fr 1.25fr 0.9fr;
    gap: 0.85rem;
}

.topic-column,
.thread-column,
.side-card {
    background: rgba(8, 22, 41, 0.75);
}

.topic-column,
.thread-column {
    display: grid;
    align-content: start;
    gap: 0.75rem;
    min-height: 620px;
}

.column-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.6rem;
}

.column-head h3 {
    margin: 0;
}

.column-head small {
    color: var(--text-tertiary);
}

.compose,
.reply-compose,
.scout-form {
    display: grid;
    gap: 0.5rem;
}

.read-only-note {
    margin: 0;
    border: 1px solid rgba(120, 179, 219, 0.28);
    border-radius: 10px;
    padding: 0.5rem 0.62rem;
    background: rgba(8, 22, 41, 0.62);
    color: var(--text-secondary);
    font-size: 0.77rem;
    line-height: 1.35;
}

.compose-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.45rem;
}

.topic-list {
    display: grid;
    gap: 0.55rem;
    max-height: 610px;
    overflow: auto;
    padding-right: 0.18rem;
}

.topic-item {
    border: 1px solid rgba(121, 181, 224, 0.23);
    background: rgba(7, 21, 40, 0.82);
    border-radius: 12px;
    padding: 0.68rem;
    text-align: left;
    color: inherit;
    cursor: pointer;
}

.topic-item.active {
    border-color: rgba(110, 211, 255, 0.8);
    background: linear-gradient(140deg, rgba(16, 45, 81, 0.9), rgba(9, 26, 49, 0.88));
    box-shadow: 0 0 0 1px rgba(110, 211, 255, 0.35);
}

.topic-item header,
.reply-row header {
    display: flex;
    justify-content: space-between;
    gap: 0.45rem;
}

.topic-id {
    font-size: 0.64rem;
    color: #9ce8ff;
}

.topic-item h4 {
    margin: 0.3rem 0 0.25rem;
    font-size: 0.9rem;
}

.topic-item p {
    margin: 0;
    font-size: 0.79rem;
    color: var(--text-secondary);
}

.topic-item footer {
    margin-top: 0.52rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    align-items: center;
}

.meta {
    font-size: 0.68rem;
    color: var(--text-tertiary);
}

.pill {
    font-size: 0.64rem;
    border-radius: 999px;
    padding: 0.14rem 0.5rem;
    border: 1px solid transparent;
}

.lane-security {
    color: #9be7ff;
    border-color: rgba(94, 206, 255, 0.45);
}

.lane-deploy {
    color: #9bc9ff;
    border-color: rgba(117, 164, 255, 0.45);
}

.lane-research {
    color: #88f4d5;
    border-color: rgba(98, 232, 193, 0.45);
}

.lane-trading {
    color: #ffd8a4;
    border-color: rgba(255, 193, 111, 0.45);
}

.lane-governance {
    color: #e7c9ff;
    border-color: rgba(206, 146, 255, 0.45);
}

.lane-external {
    color: #ffd7ee;
    border-color: rgba(255, 166, 219, 0.45);
}

.state-open {
    color: #7de9c3;
    border-color: rgba(86, 216, 166, 0.5);
}

.state-queued {
    color: #9cdfff;
    border-color: rgba(96, 194, 255, 0.5);
}

.state-needs_owner {
    color: #ffd79a;
    border-color: rgba(255, 185, 92, 0.5);
}

.state-blocked {
    color: #ffb2b2;
    border-color: rgba(255, 120, 120, 0.55);
}

.state-resolved {
    color: #9ef7a8;
    border-color: rgba(109, 233, 126, 0.5);
}

.priority-low {
    color: #a8c7e1;
    border-color: rgba(126, 184, 229, 0.38);
}

.priority-medium {
    color: #d1e9ff;
    border-color: rgba(163, 214, 255, 0.42);
}

.priority-high {
    color: #ffd296;
    border-color: rgba(255, 187, 101, 0.52);
}

.priority-critical {
    color: #ffb2b2;
    border-color: rgba(255, 120, 120, 0.58);
}

.opening-post {
    border: 1px solid rgba(127, 185, 224, 0.26);
    border-radius: 12px;
    background: rgba(8, 24, 45, 0.75);
    padding: 0.72rem;
}

.opening-post p {
    margin: 0;
    color: #d5eaff;
    line-height: 1.45;
}

.opening-post small {
    display: inline-block;
    margin-top: 0.5rem;
    color: var(--text-tertiary);
}

.reply-stream {
    display: grid;
    gap: 0.52rem;
    max-height: 420px;
    overflow: auto;
    padding-right: 0.18rem;
}

.reply-row {
    border: 1px solid rgba(120, 179, 219, 0.22);
    border-radius: 10px;
    padding: 0.62rem;
    background: rgba(8, 22, 41, 0.62);
}

.reply-row p {
    margin: 0.42rem 0 0;
    font-size: 0.81rem;
    color: #d4e9fb;
}

.reply-row footer {
    margin-top: 0.4rem;
    color: var(--text-tertiary);
    font-size: 0.7rem;
}

.side-column {
    display: grid;
    gap: 0.75rem;
    align-content: start;
}

.side-card {
    display: grid;
    gap: 0.45rem;
}

.side-card h3 {
    margin: 0;
}

.side-card p {
    margin: 0;
    font-size: 0.8rem;
    color: #c5dff7;
}

.summary-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 0.34rem;
}

.empty {
    margin: 0;
    color: var(--text-tertiary);
    font-size: 0.77rem;
}

.empty-thread {
    align-content: center;
    text-align: center;
}

@media (max-width: 1420px) {
    .architecture-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .architecture-kpis {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .board-layout {
        grid-template-columns: 1fr 1fr;
    }

    .side-column {
        grid-column: 1 / -1;
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 980px) {
    .architecture-head {
        display: grid;
        gap: 0.55rem;
    }

    .architecture-score {
        justify-items: start;
    }

    .architecture-grid {
        grid-template-columns: 1fr 1fr;
    }

    .venue-pulse-grid {
        grid-template-columns: 1fr;
    }

    .filter-row {
        grid-template-columns: 1fr;
    }

    .board-layout {
        grid-template-columns: 1fr;
    }

    .side-column {
        grid-template-columns: 1fr;
    }

    .topic-column,
    .thread-column {
        min-height: auto;
    }
}

@media (max-width: 680px) {
    .architecture-grid,
    .architecture-kpis {
        grid-template-columns: 1fr;
    }
}
</style>

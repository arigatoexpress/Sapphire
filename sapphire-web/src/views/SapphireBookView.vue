<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { fetchControlStatus, fetchSystemLogs, type ControlStatusResponse, type SystemLogEntry } from '../api/client'

type ThreadState = 'active' | 'queued' | 'blocked'
type Lane = 'security' | 'deploy' | 'research'

interface AgentThread {
    id: string
    lane: Lane
    title: string
    state: ThreadState
    updatedAgo: string
    summary: string
    source: string
}

const threads = ref<AgentThread[]>([])
const control = ref<ControlStatusResponse | null>(null)
const loading = ref(true)
const lastSyncEpoch = ref(0)
const nowEpoch = ref(Date.now())
let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const laneLabel: Record<Lane, string> = {
    security: 'SAPPHIRE',
    deploy: 'OBSIDIAN',
    research: 'EMERALD',
}

const laneStyleClass: Record<Lane, string> = {
    security: 'lane-security',
    deploy: 'lane-deploy',
    research: 'lane-research',
}

const stateClass = (state: ThreadState) => `state-${state}`

const syncAge = computed(() => {
    if (!lastSyncEpoch.value) return 'sync pending'
    return `${Math.max(0, Math.round((nowEpoch.value - lastSyncEpoch.value) / 1000))}s ago`
})

const stats = computed(() => ({
    active: threads.value.filter((thread) => thread.state === 'active').length,
    queued: threads.value.filter((thread) => thread.state === 'queued').length,
    blocked: threads.value.filter((thread) => thread.state === 'blocked').length,
    pendingDecisions: Number(control.value?.pending_autonomy_decisions || 0),
}))

const autonomyScore = computed(() => {
    const total = threads.value.length || 1
    const pressure = stats.value.pendingDecisions + stats.value.blocked
    const weighted =
        stats.value.active * 1.2 +
        stats.value.queued * 0.5 -
        pressure * 1.1
    const normalized = Math.round((weighted / total) * 35 + 50)
    return Math.max(5, Math.min(99, normalized))
})

const scoreToneClass = computed(() => {
    if (autonomyScore.value >= 75) return 'tone-strong'
    if (autonomyScore.value >= 55) return 'tone-balanced'
    return 'tone-fragile'
})

const laneStats = computed(() => {
    const counts: Record<Lane, number> = { security: 0, deploy: 0, research: 0 }
    for (const thread of threads.value) counts[thread.lane] += 1
    return [
        { lane: 'security' as Lane, label: 'SAPPHIRE', count: counts.security, focus: 'Security + governance' },
        { lane: 'deploy' as Lane, label: 'OBSIDIAN', count: counts.deploy, focus: 'Runtime + deployment ops' },
        { lane: 'research' as Lane, label: 'EMERALD', count: counts.research, focus: 'Signal + adaptation' },
    ]
})

const leadLane = computed(() => {
    const sorted = laneStats.value.slice().sort((a, b) => b.count - a.count)
    return sorted[0]?.label || 'SAPPHIRE'
})

const queuePressure = computed(() => {
    const pressure = stats.value.pendingDecisions + stats.value.blocked
    if (pressure >= 4) return 'High'
    if (pressure >= 2) return 'Moderate'
    return 'Low'
})

const ownerDirective = computed(() => {
    const raw = String(control.value?.owner_directive || '').trim()
    if (!raw) return 'none'
    if (raw.length <= 160) return raw
    return `${raw.slice(0, 157)}...`
})

const decisionQueue = computed(() => {
    const pending = control.value?.pending_sessions || []
    if (!pending.length) {
        return ['No pending autonomy approvals. Runtime decisions are flowing without backlog.']
    }
    return pending.slice(0, 4).map((session) => {
        const trigger = session.trigger || 'scheduled_cycle'
        const instruction = String(session.instruction || '').trim()
        const summary = instruction.length > 96 ? `${instruction.slice(0, 93)}...` : instruction || 'autonomy decision'
        return `${trigger}: ${summary}`
    })
})

const formatAge = (epochSeconds: number) => {
    const delta = Math.max(0, Math.floor(Date.now() / 1000) - epochSeconds)
    if (delta < 60) return `${delta}s`
    if (delta < 3600) return `${Math.floor(delta / 60)}m`
    if (delta < 86400) return `${Math.floor(delta / 3600)}h`
    return `${Math.floor(delta / 86400)}d`
}

const laneFromLog = (entry: SystemLogEntry): Lane => {
    const tags = (entry.tags || []).map((tag) => String(tag).toLowerCase())
    const message = String(entry.message || '').toLowerCase()
    if (
        tags.some((tag) => ['risk', 'security', 'kill_switch'].includes(tag)) ||
        /(risk|scope|security|permission|guardrail|blocked_scope)/.test(message)
    ) {
        return 'security'
    }
    if (
        tags.some((tag) => ['dispatch', 'control', 'startup', 'auto_resume', 'execution_mode'].includes(tag)) ||
        /(deploy|dispatch|allocation|resume|execution|tradingview)/.test(message)
    ) {
        return 'deploy'
    }
    return 'research'
}

const stateFromLog = (entry: SystemLogEntry): ThreadState => {
    const level = String(entry.level || '').toLowerCase()
    const message = String(entry.message || '').toLowerCase()
    if (level === 'error' || level === 'critical' || /(failed|unavailable|blocked|error)/.test(message)) {
        return 'blocked'
    }
    if (level === 'warning' || /(pending|queued|hold|cooldown)/.test(message)) return 'queued'
    return 'active'
}

const titleFromLog = (entry: SystemLogEntry): string => {
    const source = String(entry.message || '').trim()
    if (!source) return 'System event'
    const sentence = source.replace(/\s+/g, ' ').trim()
    if (sentence.length <= 72) return sentence
    return `${sentence.slice(0, 69)}...`
}

const summaryFromLog = (entry: SystemLogEntry): string => {
    const text = String(entry.message || '').trim()
    if (!text) return 'No details available.'
    if (text.length <= 180) return text
    return `${text.slice(0, 177)}...`
}

const buildThreads = (logs: SystemLogEntry[]): AgentThread[] => {
    return logs
        .slice()
        .reverse()
        .filter((entry) => Number.isFinite(Number(entry.timestamp)))
        .slice(0, 18)
        .map((entry, index) => {
            const ts = Number(entry.timestamp || 0)
            const lane = laneFromLog(entry)
            const state = stateFromLog(entry)
            return {
                id: `LOG-${ts}-${index}`,
                lane,
                title: titleFromLog(entry),
                state,
                updatedAgo: formatAge(ts),
                summary: summaryFromLog(entry),
                source: (entry.tags || []).join(', ') || String(entry.level || 'info').toUpperCase(),
            }
        })
}

const loadBoard = async () => {
    try {
        const [logs, controlPayload] = await Promise.all([fetchSystemLogs(140), fetchControlStatus()])
        if (controlPayload?.ok) control.value = controlPayload

        const nextThreads = buildThreads(logs || [])
        threads.value =
            nextThreads.length > 0
                ? nextThreads
                : [
                      {
                          id: 'LOG-empty',
                          lane: 'deploy',
                          title: 'Awaiting runtime activity',
                          state: 'queued',
                          updatedAgo: 'now',
                          summary: 'No recent control-plane logs were returned. Verify alpha service log stream.',
                          source: 'telemetry',
                      },
                  ]
        lastSyncEpoch.value = Date.now()
    } catch (error) {
        console.error('Failed to load SapphireBook board:', error)
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    loadBoard()
    refreshTimer = setInterval(loadBoard, 12000)
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
    <div class="book-view fade-in">
        <section class="hero card glass-lift">
            <div class="hero-copy">
                <span class="font-mono kicker">SAPPHIREBOOK LIVE</span>
                <h2>Real-time agent coordination board from runtime logs and control state.</h2>
                <p>
                    This forum surface is telemetry-native. Every thread reflects current alpha-engine events, while command authority
                    remains constrained to Telegram.
                </p>
            </div>
            <div class="hero-stats">
                <span class="chip active">Active {{ stats.active }}</span>
                <span class="chip queued">Queued {{ stats.queued }}</span>
                <span class="chip blocked">Blocked {{ stats.blocked }}</span>
                <span class="chip decision">Pending {{ stats.pendingDecisions }}</span>
            </div>
        </section>

        <section class="snapshot-strip">
            <article class="snapshot card glass-lift">
                <p class="font-mono">Autonomy Score</p>
                <strong :class="scoreToneClass">{{ autonomyScore }}%</strong>
                <small>Weighted by live thread state + pending decision pressure.</small>
            </article>
            <article class="snapshot card glass-lift">
                <p class="font-mono">Lead Lane</p>
                <strong>{{ leadLane }}</strong>
                <small>Highest current thread concentration.</small>
            </article>
            <article class="snapshot card glass-lift">
                <p class="font-mono">Queue Pressure</p>
                <strong>{{ queuePressure }}</strong>
                <small>Sync {{ syncAge }} · {{ loading ? 'refreshing' : 'live' }}</small>
            </article>
        </section>

        <section class="grid">
            <article class="threads card">
                <header>
                    <h3 class="font-mono">Live Threads</h3>
                    <small>{{ threads.length }} tracked</small>
                </header>

                <div class="thread-list">
                    <article
                        v-for="(thread, index) in threads"
                        :key="thread.id"
                        class="thread glass-lift fade-in"
                        :class="`stagger-${(index % 4) + 1}`"
                    >
                        <header class="thread-head">
                            <div>
                                <span class="thread-id font-mono">{{ thread.id }}</span>
                                <h4>{{ thread.title }}</h4>
                            </div>
                            <span class="state-pill font-mono" :class="stateClass(thread.state)">
                                {{ thread.state.toUpperCase() }}
                            </span>
                        </header>
                        <p>{{ thread.summary }}</p>
                        <footer>
                            <span class="lane" :class="laneStyleClass[thread.lane]">{{ laneLabel[thread.lane] }}</span>
                            <span class="updated">Updated {{ thread.updatedAgo }} ago</span>
                            <span class="source font-mono">{{ thread.source }}</span>
                        </footer>
                    </article>
                </div>
            </article>

            <aside class="side-stack">
                <article class="lane-board card glass-lift">
                    <h3 class="font-mono">Lane Capacity</h3>
                    <div class="lane-list">
                        <div v-for="lane in laneStats" :key="lane.label" class="lane-row">
                            <div>
                                <strong :class="laneStyleClass[lane.lane]">{{ lane.label }}</strong>
                                <small>{{ lane.focus }}</small>
                            </div>
                            <span class="font-mono">{{ lane.count }}</span>
                        </div>
                    </div>
                </article>

                <article class="decision-board card glass-lift">
                    <h3 class="font-mono">Owner Decision Queue</h3>
                    <ol>
                        <li v-for="item in decisionQueue" :key="item">{{ item }}</li>
                    </ol>
                    <p class="hint">Directive: {{ ownerDirective }}</p>
                </article>
            </aside>
        </section>
    </div>
</template>

<style scoped>
.book-view {
    display: grid;
    gap: 0.9rem;
}

.hero {
    display: grid;
    gap: 0.8rem;
    background:
        radial-gradient(circle at 82% 4%, rgba(65, 184, 255, 0.26), transparent 45%),
        linear-gradient(130deg, rgba(7, 21, 42, 0.94), rgba(7, 24, 42, 0.78));
}

.kicker {
    color: #9de4ff;
    letter-spacing: 0.08em;
    font-size: 0.65rem;
}

.hero h2 {
    margin: 0.35rem 0 0.3rem;
    font-size: 1.12rem;
}

.hero p {
    margin: 0;
    color: var(--text-secondary);
    max-width: 76ch;
}

.hero-stats {
    display: flex;
    gap: 0.45rem;
    flex-wrap: wrap;
}

.chip {
    font-size: 0.73rem;
    padding: 0.2rem 0.58rem;
    border-radius: 999px;
    border: 1px solid transparent;
}

.chip.active {
    border-color: rgba(23, 200, 136, 0.55);
    color: #7cf0c2;
}

.chip.queued {
    border-color: rgba(54, 181, 255, 0.62);
    color: #9cdcff;
}

.chip.blocked {
    border-color: rgba(255, 116, 116, 0.62);
    color: #ffb1b1;
}

.chip.decision {
    border-color: rgba(244, 180, 68, 0.62);
    color: #ffd79a;
}

.snapshot-strip {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.75rem;
}

.snapshot {
    background: rgba(8, 22, 40, 0.74);
    border: 1px solid rgba(120, 185, 231, 0.3);
    display: grid;
    gap: 0.28rem;
}

.snapshot p {
    margin: 0;
    font-size: 0.65rem;
    letter-spacing: 0.08em;
    color: #98d8fb;
}

.snapshot strong {
    font-size: 1.1rem;
    color: #e2f2ff;
}

.snapshot small {
    color: var(--text-secondary);
    font-size: 0.74rem;
}

.tone-strong {
    color: #75edbf;
}

.tone-balanced {
    color: #ffd89f;
}

.tone-fragile {
    color: #ffb6b6;
}

.grid {
    display: grid;
    grid-template-columns: 1.7fr 1fr;
    gap: 0.8rem;
}

.threads header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 0.75rem;
}

.threads h3 {
    margin: 0;
}

.threads small {
    color: var(--text-tertiary);
}

.thread-list {
    display: grid;
    gap: 0.62rem;
}

.thread {
    border: 1px solid rgba(128, 183, 226, 0.26);
    border-radius: var(--radius-md);
    background: rgba(8, 22, 40, 0.7);
    padding: 0.78rem;
}

.thread-head {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
}

.thread-id {
    font-size: 0.64rem;
    color: #99e4ff;
}

.thread h4 {
    margin: 0.24rem 0 0;
    font-size: 0.93rem;
}

.thread p {
    margin: 0.58rem 0 0;
    color: var(--text-secondary);
    font-size: 0.84rem;
}

.thread footer {
    margin-top: 0.72rem;
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 0.5rem;
    color: var(--text-tertiary);
    font-size: 0.72rem;
}

.source {
    opacity: 0.75;
}

.state-pill {
    font-size: 0.61rem;
    border-radius: 999px;
    padding: 0.18rem 0.52rem;
    align-self: flex-start;
}

.state-active {
    color: #78efbf;
    background: rgba(23, 200, 136, 0.18);
}

.state-queued {
    color: #9cdcff;
    background: rgba(54, 181, 255, 0.2);
}

.state-blocked {
    color: #ffb1b1;
    background: rgba(255, 116, 116, 0.2);
}

.lane-security {
    color: #9ce9ff;
}

.lane-deploy {
    color: #98c9ff;
}

.lane-research {
    color: #84f3d1;
}

.side-stack {
    display: grid;
    gap: 0.8rem;
    align-content: start;
}

.lane-board h3,
.decision-board h3 {
    margin: 0 0 0.7rem;
    font-size: 0.84rem;
    letter-spacing: 0.05em;
}

.lane-list {
    display: grid;
    gap: 0.62rem;
}

.lane-row {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    border-bottom: 1px solid rgba(126, 184, 231, 0.18);
    padding-bottom: 0.5rem;
}

.lane-row:last-child {
    border-bottom: none;
    padding-bottom: 0;
}

.lane-row strong {
    display: block;
    font-size: 0.85rem;
}

.lane-row small {
    color: var(--text-tertiary);
    font-size: 0.7rem;
}

.lane-row span {
    font-size: 0.82rem;
    color: var(--text-secondary);
}

.decision-board ol {
    margin: 0;
    padding-left: 1.05rem;
    display: grid;
    gap: 0.45rem;
    color: #cae3fb;
    font-size: 0.83rem;
}

.hint {
    margin: 0.75rem 0 0;
    color: var(--text-tertiary);
    font-size: 0.75rem;
}

@media (max-width: 1100px) {
    .snapshot-strip,
    .grid {
        grid-template-columns: 1fr;
    }
}
</style>

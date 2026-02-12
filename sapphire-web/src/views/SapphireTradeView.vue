<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { fetchPlatformStatus, fetchSystemLogs } from '../api/client'

interface VenueCard {
    id: 'aster' | 'lighter'
    label: string
    status: 'online' | 'degraded' | 'offline'
    mode: string
    notes: string
}

const venues = ref<VenueCard[]>([
    {
        id: 'aster',
        label: 'ASTER',
        status: 'offline',
        mode: 'Awaiting telemetry',
        notes: 'Perps execution lane',
    },
    {
        id: 'lighter',
        label: 'LIGHTER',
        status: 'offline',
        mode: 'Awaiting telemetry',
        notes: 'Execution + liquidity lane',
    },
])

const recentOps = ref<string[]>([])
const loading = ref(true)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const statusClass = (status: VenueCard['status']) => `status-${status}`

const healthyCount = computed(() => venues.value.filter((venue) => venue.status === 'online').length)

const normalizeVenueStatus = (value: unknown): VenueCard['status'] => {
    if (typeof value !== 'string') return 'offline'
    const normalized = value.toLowerCase()
    if (normalized === 'healthy' || normalized === 'online' || normalized === 'active') return 'online'
    if (normalized === 'degraded' || normalized === 'warning') return 'degraded'
    return 'offline'
}

const applyPlatformPayload = (payload: any) => {
    const entries = payload?.platforms || payload?.data || payload || {}
    const next = [...venues.value]

    next.forEach((venue, index) => {
        const raw = entries?.[venue.id] ?? {}
        const status = normalizeVenueStatus(raw?.status ?? raw?.health)
        const mode = raw?.mode || raw?.routing || (status === 'online' ? 'Autonomous execution ready' : 'Waiting for heartbeat')
        const notes = raw?.note || raw?.message || venue.notes
        next[index] = { ...venue, status, mode, notes }
    })

    venues.value = next
}

const loadOpsView = async () => {
    try {
        const [platforms, logs] = await Promise.all([
            fetchPlatformStatus(),
            fetchSystemLogs(),
        ])

        if (platforms) applyPlatformPayload(platforms)
        if (Array.isArray(logs)) {
            recentOps.value = logs
                .map((entry: any) => entry?.message || entry?.msg || String(entry))
                .filter((message: string) => /aster|lighter|deploy|risk|position|execution/i.test(message))
                .slice(-6)
                .reverse()
        }
    } catch (error) {
        console.error('Failed to load trade view data:', error)
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    loadOpsView()
    refreshTimer = setInterval(loadOpsView, 12000)
})

onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
    <div class="trade-view">
        <section class="hero card">
            <h2 class="font-mono">SapphireTrade</h2>
            <p>Operational execution for ASTER and LIGHTER with read-only telemetry. All overrides and trade instructions route through Telegram heartbeat.</p>
            <div class="health-line">
                <span class="chip">
                    Healthy venues: {{ healthyCount }}/{{ venues.length }}
                </span>
                <span class="chip muted">
                    Web control disabled
                </span>
            </div>
        </section>

        <section class="venues-grid">
            <article v-for="venue in venues" :key="venue.id" class="venue-card card">
                <header>
                    <h3 class="font-mono">{{ venue.label }}</h3>
                    <span class="status-pill font-mono" :class="statusClass(venue.status)">
                        {{ venue.status.toUpperCase() }}
                    </span>
                </header>
                <p class="mode">{{ venue.mode }}</p>
                <p class="notes">{{ venue.notes }}</p>
            </article>
        </section>

        <section class="ops-log card">
            <header>
                <h3 class="font-mono">Recent Operations</h3>
                <span class="small">{{ loading ? 'Loading...' : 'Auto-refresh 12s' }}</span>
            </header>
            <ul v-if="recentOps.length > 0">
                <li v-for="(line, idx) in recentOps" :key="idx">{{ line }}</li>
            </ul>
            <p v-else class="empty">
                Waiting for execution telemetry from runtime logs.
            </p>
        </section>
    </div>
</template>

<style scoped>
.trade-view {
    display: grid;
    gap: 1rem;
}

.hero {
    border-radius: 14px;
    background:
        radial-gradient(circle at 85% 15%, rgba(20, 184, 166, 0.2), transparent 48%),
        rgba(8, 15, 23, 0.88);
}

.hero h2 {
    margin: 0 0 0.3rem;
}

.hero p {
    margin: 0;
    color: var(--text-secondary);
    max-width: 74ch;
}

.health-line {
    margin-top: 0.85rem;
    display: flex;
    gap: 0.55rem;
    flex-wrap: wrap;
}

.chip {
    border-radius: 999px;
    padding: 0.2rem 0.6rem;
    font-size: 0.74rem;
    border: 1px solid rgba(16, 185, 129, 0.45);
    color: #6ee7b7;
}

.chip.muted {
    border-color: rgba(56, 189, 248, 0.4);
    color: #7dd3fc;
}

.venues-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 0.8rem;
}

.venue-card {
    border-radius: 12px;
    background: rgba(7, 13, 23, 0.84);
}

.venue-card header {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    align-items: center;
}

.venue-card h3 {
    margin: 0;
    font-size: 0.95rem;
}

.status-pill {
    font-size: 0.64rem;
    border-radius: 999px;
    padding: 0.2rem 0.55rem;
}

.status-online {
    background: rgba(16, 185, 129, 0.16);
    color: #6ee7b7;
}

.status-degraded {
    background: rgba(245, 158, 11, 0.17);
    color: #fcd34d;
}

.status-offline {
    background: rgba(248, 113, 113, 0.16);
    color: #fda4af;
}

.mode {
    margin: 0.7rem 0 0;
    color: #e2e8f0;
}

.notes {
    margin: 0.45rem 0 0;
    color: var(--text-secondary);
    font-size: 0.85rem;
}

.ops-log {
    border-radius: 12px;
    background: rgba(7, 13, 23, 0.84);
}

.ops-log header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.75rem;
}

.ops-log h3 {
    margin: 0;
}

.small {
    font-size: 0.72rem;
    color: var(--text-tertiary);
}

.ops-log ul {
    margin: 0;
    padding-left: 1rem;
    display: grid;
    gap: 0.4rem;
    color: #d1d5db;
}

.ops-log li {
    font-size: 0.84rem;
}

.empty {
    margin: 0;
    color: var(--text-secondary);
}
</style>

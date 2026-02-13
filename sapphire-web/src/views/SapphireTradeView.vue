<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import TradingChart from '../components/TradingChart.vue'
import {
    fetchControlStatus,
    fetchMarketOHLC,
    fetchPlatformStatus,
    fetchSystemLogs,
    type OhlcCandle,
} from '../api/client'

interface VenueCard {
    id: 'aster' | 'lighter'
    label: string
    status: 'online' | 'degraded' | 'offline'
    mode: string
    notes: string
    price: number | null
}

interface VenueChartMeta {
    symbol: string
    trackingSymbol: string
    source: string
    interval: string
    generatedAt: number
}

const venues = ref<VenueCard[]>([
    {
        id: 'aster',
        label: 'ASTER',
        status: 'offline',
        mode: 'Awaiting telemetry',
        notes: 'Execution lane',
        price: null,
    },
    {
        id: 'lighter',
        label: 'LIGHTER',
        status: 'offline',
        mode: 'Awaiting telemetry',
        notes: 'Liquidity lane',
        price: null,
    },
])

const recentOps = ref<string[]>([])
const asterCandles = ref<OhlcCandle[]>([])
const lighterCandles = ref<OhlcCandle[]>([])
const asterMeta = ref<VenueChartMeta>({
    symbol: 'SOL',
    trackingSymbol: 'SOLUSDT',
    source: 'unavailable',
    interval: '1m',
    generatedAt: 0,
})
const lighterMeta = ref<VenueChartMeta>({
    symbol: 'SOL',
    trackingSymbol: 'SOL',
    source: 'unavailable',
    interval: '1m',
    generatedAt: 0,
})
const loading = ref(true)
const lastRefreshEpoch = ref(0)
const nowEpoch = ref(Date.now())
const controlState = ref<{
    tradingview_execution_enabled: boolean
    tradingview_default_quantity: number
    pending_autonomy_decisions: number
} | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const statusClass = (status: VenueCard['status']) => `status-${status}`

const healthyCount = computed(() => venues.value.filter((venue) => venue.status === 'online').length)

const portfolioPosture = computed(() => {
    if (healthyCount.value === venues.value.length) return 'Dual-venue live'
    if (healthyCount.value > 0) return 'Single-venue guarded'
    return 'Fail-safe hold'
})

const refreshAge = computed(() => {
    if (!lastRefreshEpoch.value) return 'sync pending'
    return `${Math.max(0, Math.round((nowEpoch.value - lastRefreshEpoch.value) / 1000))}s ago`
})

const executionModeLabel = computed(() =>
    controlState.value?.tradingview_execution_enabled ? 'signals live' : 'workbench dry-run',
)

const defaultQtyLabel = computed(() => {
    const qty = Number(controlState.value?.tradingview_default_quantity || 0)
    return qty > 0 ? qty.toString() : 'n/a'
})

const pendingDecisionCount = computed(() => Number(controlState.value?.pending_autonomy_decisions || 0))

const formatPrice = (value: number | null) => {
    if (value === null || !Number.isFinite(value) || value <= 0) return 'n/a'
    if (value >= 1000) return `$${value.toFixed(2)}`
    if (value >= 100) return `$${value.toFixed(3)}`
    return `$${value.toFixed(4)}`
}

const asterVenuePrice = computed(() => venues.value.find((item) => item.id === 'aster')?.price ?? null)
const lighterVenuePrice = computed(() => venues.value.find((item) => item.id === 'lighter')?.price ?? null)

const asterLastClose = computed(() => {
    const tail = asterCandles.value[asterCandles.value.length - 1]
    return tail ? Number(tail.close) : null
})

const lighterLastClose = computed(() => {
    const tail = lighterCandles.value[lighterCandles.value.length - 1]
    return tail ? Number(tail.close) : null
})

const effectiveAsterPrice = computed(() => asterVenuePrice.value ?? asterLastClose.value)
const effectiveLighterPrice = computed(() => lighterVenuePrice.value ?? lighterLastClose.value)

const spreadAbs = computed(() => {
    if (effectiveAsterPrice.value === null || effectiveLighterPrice.value === null) return null
    return Math.abs(effectiveAsterPrice.value - effectiveLighterPrice.value)
})

const spreadPct = computed(() => {
    if (effectiveAsterPrice.value === null || effectiveLighterPrice.value === null) return null
    const midpoint = (effectiveAsterPrice.value + effectiveLighterPrice.value) / 2
    if (!Number.isFinite(midpoint) || midpoint <= 0) return null
    return (Math.abs(effectiveAsterPrice.value - effectiveLighterPrice.value) / midpoint) * 100
})

const spreadTone = computed(() => {
    const value = spreadPct.value ?? 0
    if (value >= 1.0) return 'tone-hot'
    if (value >= 0.4) return 'tone-warm'
    return 'tone-calm'
})

const formatBarAge = (candles: OhlcCandle[]) => {
    const last = candles[candles.length - 1] as OhlcCandle | undefined
    if (!last) return 'n/a'
    const ts = Math.floor(Number(last.time) || 0)
    if (ts <= 0) return 'n/a'
    const delta = Math.max(0, Math.round(Date.now() / 1000 - ts))
    return `${delta}s`
}

const asterBarAge = computed(() => formatBarAge(asterCandles.value))
const lighterBarAge = computed(() => formatBarAge(lighterCandles.value))

const normalizeCandles = (candles: OhlcCandle[] | null | undefined): OhlcCandle[] =>
    (candles || [])
        .filter((item) => Number.isFinite(Number(item.time)))
        .map((item) => ({
            time: Number(item.time),
            open: Number(item.open),
            high: Number(item.high),
            low: Number(item.low),
            close: Number(item.close),
            volume: Number.isFinite(Number(item.volume)) ? Number(item.volume) : 0,
        }))
        .filter(
            (item) =>
                Number.isFinite(item.open) &&
                Number.isFinite(item.high) &&
                Number.isFinite(item.low) &&
                Number.isFinite(item.close),
        )
        .sort((a, b) => a.time - b.time)

const normalizeVenueStatus = (value: unknown): VenueCard['status'] => {
    if (typeof value !== 'string') return 'offline'
    const normalized = value.toLowerCase()
    if (normalized === 'healthy' || normalized === 'online' || normalized === 'active') return 'online'
    if (normalized === 'degraded' || normalized === 'warning') return 'degraded'
    return 'offline'
}

const toPrice = (value: unknown): number | null => {
    const numeric = Number(value)
    if (!Number.isFinite(numeric) || numeric <= 0) return null
    return numeric
}

const applyPlatformPayload = (payload: any) => {
    const entries = payload?.platforms || payload?.data || payload || {}
    const next = [...venues.value]

    next.forEach((venue, index) => {
        const raw = entries?.[venue.id] ?? {}
        const status = normalizeVenueStatus(raw?.status ?? raw?.health)
        const mode = raw?.mode || raw?.routing || (status === 'online' ? 'Autonomous ready' : 'Waiting heartbeat')
        const notes = raw?.note || raw?.message || venue.notes
        const price = toPrice(raw?.price ?? raw?.mark_price ?? raw?.markPrice ?? raw?.mid_price ?? raw?.midPrice)
        next[index] = { ...venue, status, mode, notes, price }
    })

    venues.value = next
}

const loadOpsView = async () => {
    try {
        const [platforms, logs, asterOhlc, lighterOhlc, controlPayload] = await Promise.all([
            fetchPlatformStatus(),
            fetchSystemLogs(),
            fetchMarketOHLC({ venue: 'ASTER', symbol: 'SOL', interval: '1m', limit: 220 }),
            fetchMarketOHLC({ venue: 'LIGHTER', symbol: 'SOL', interval: '1m', limit: 220 }),
            fetchControlStatus(),
        ])

        if (platforms) applyPlatformPayload(platforms)
        if (Array.isArray(logs)) {
            recentOps.value = logs
                .map((entry: any) => entry?.message || entry?.msg || String(entry))
                .filter((message: string) =>
                    /aster|lighter|deploy|risk|position|execution|promotion|allocation|heartbeat|ohlc|arb/i.test(message),
                )
                .slice(-10)
                .reverse()
        }

        asterCandles.value = normalizeCandles(asterOhlc?.candles)
        lighterCandles.value = normalizeCandles(lighterOhlc?.candles)

        asterMeta.value = {
            symbol: String(asterOhlc?.symbol || 'SOL').toUpperCase(),
            trackingSymbol: String(asterOhlc?.tracking_symbol || asterOhlc?.symbol || 'SOL').toUpperCase(),
            source: String(asterOhlc?.source || 'unavailable'),
            interval: String(asterOhlc?.interval || '1m'),
            generatedAt: Number(asterOhlc?.generated_at || 0),
        }

        lighterMeta.value = {
            symbol: String(lighterOhlc?.symbol || 'SOL').toUpperCase(),
            trackingSymbol: String(lighterOhlc?.tracking_symbol || lighterOhlc?.symbol || 'SOL').toUpperCase(),
            source: String(lighterOhlc?.source || 'unavailable'),
            interval: String(lighterOhlc?.interval || '1m'),
            generatedAt: Number(lighterOhlc?.generated_at || 0),
        }

        if (controlPayload?.ok) {
            controlState.value = {
                tradingview_execution_enabled: Boolean(controlPayload.tradingview_execution_enabled),
                tradingview_default_quantity: Number(controlPayload.tradingview_default_quantity || 0),
                pending_autonomy_decisions: Number(controlPayload.pending_autonomy_decisions || 0),
            }
        }

        lastRefreshEpoch.value = Date.now()
    } catch (error) {
        console.error('Failed to load trade view data:', error)
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    loadOpsView()
    refreshTimer = setInterval(loadOpsView, 12000)
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
    <div class="trade-view fade-in">
        <section class="hero card glass-lift">
            <div class="hero-copy">
                <span class="font-mono kicker">SAPPHIRETRADE</span>
                <h2>Venue-native execution telemetry for ASTER + LIGHTER.</h2>
                <p>
                    Charts are now split by venue so each panel tracks one feed directly. No cross-venue candle averaging is used in
                    the chart path.
                </p>
            </div>
            <div class="health-line">
                <span class="chip">Healthy venues: {{ healthyCount }}/{{ venues.length }}</span>
                <span class="chip muted">Posture: {{ portfolioPosture }}</span>
                <span class="chip muted">Sync: {{ refreshAge }}</span>
                <span class="chip muted">DEX execution: ASTER + LIGHTER</span>
                <span class="chip muted">TV: {{ executionModeLabel }} · qty {{ defaultQtyLabel }}</span>
                <span class="chip muted">Pending decisions: {{ pendingDecisionCount }}</span>
            </div>
        </section>

        <section class="metric-strip">
            <article class="metric card glass-lift">
                <p class="font-mono">ASTER Mark</p>
                <strong>{{ formatPrice(effectiveAsterPrice) }}</strong>
                <small>
                    feed close {{ formatPrice(asterLastClose) }} · venue mark {{ formatPrice(asterVenuePrice) }}
                </small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">LIGHTER Mark</p>
                <strong>{{ formatPrice(effectiveLighterPrice) }}</strong>
                <small>
                    feed close {{ formatPrice(lighterLastClose) }} · venue mark {{ formatPrice(lighterVenuePrice) }}
                </small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">Cross-Venue Spread</p>
                <strong :class="spreadTone">
                    {{ spreadPct === null ? 'n/a' : `${spreadPct.toFixed(3)}%` }}
                </strong>
                <small>
                    absolute delta {{ spreadAbs === null ? 'n/a' : formatPrice(spreadAbs) }}
                </small>
            </article>
        </section>

        <section class="chart-grid">
            <article class="chart-panel card glass-lift">
                <header>
                    <h3 class="font-mono">ASTER ({{ asterMeta.trackingSymbol }})</h3>
                    <small>
                        source {{ asterMeta.source }} · req {{ asterMeta.symbol }} · {{ asterMeta.interval }} · bar age {{ asterBarAge }}
                    </small>
                </header>
                <TradingChart :candles="asterCandles" :height="290" />
            </article>

            <article class="chart-panel card glass-lift">
                <header>
                    <h3 class="font-mono">LIGHTER ({{ lighterMeta.trackingSymbol }})</h3>
                    <small>
                        source {{ lighterMeta.source }} · req {{ lighterMeta.symbol }} · {{ lighterMeta.interval }} · bar age {{ lighterBarAge }}
                    </small>
                </header>
                <TradingChart :candles="lighterCandles" :height="290" />
            </article>
        </section>

        <section class="venue-board card">
            <header>
                <h3 class="font-mono">Venue State</h3>
                <small>read-only telemetry</small>
            </header>
            <div class="venues-grid">
                <article v-for="venue in venues" :key="venue.id" class="venue-card glass-lift">
                    <header>
                        <h4 class="font-mono">{{ venue.label }}</h4>
                        <span class="status-pill font-mono" :class="statusClass(venue.status)">
                            {{ venue.status.toUpperCase() }}
                        </span>
                    </header>
                    <strong class="price">{{ formatPrice(venue.price) }}</strong>
                    <p class="mode">{{ venue.mode }}</p>
                    <p class="notes">{{ venue.notes }}</p>
                </article>
            </div>
        </section>

        <section class="ops-log card">
            <header>
                <h3 class="font-mono">Recent Operations</h3>
                <span class="small">{{ loading ? 'Loading...' : 'Auto-refresh 12s' }}</span>
            </header>
            <ul v-if="recentOps.length > 0">
                <li v-for="(line, idx) in recentOps" :key="idx">{{ line }}</li>
            </ul>
            <p v-else class="empty">Waiting for execution telemetry from runtime logs.</p>
        </section>
    </div>
</template>

<style scoped>
.trade-view {
    display: grid;
    gap: 0.9rem;
}

.hero {
    display: grid;
    gap: 0.76rem;
    background:
        radial-gradient(circle at 92% 8%, rgba(52, 181, 255, 0.18), transparent 44%),
        linear-gradient(125deg, rgba(8, 24, 43, 0.9), rgba(7, 22, 39, 0.78));
}

.kicker {
    color: #9de4ff;
    letter-spacing: 0.08em;
    font-size: 0.65rem;
}

.hero h2 {
    margin: 0.34rem 0 0.28rem;
    font-size: 1.1rem;
}

.hero p {
    margin: 0;
    color: var(--text-secondary);
    max-width: 72ch;
}

.health-line {
    display: flex;
    gap: 0.42rem;
    flex-wrap: wrap;
}

.chip {
    border-radius: 999px;
    padding: 0.2rem 0.57rem;
    font-size: 0.74rem;
    border: 1px solid rgba(23, 200, 136, 0.55);
    color: #78efbf;
}

.chip.muted {
    border-color: rgba(95, 181, 241, 0.56);
    color: #9cdcff;
}

.metric-strip {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.75rem;
}

.metric {
    background: rgba(8, 22, 40, 0.74);
    border: 1px solid rgba(127, 188, 236, 0.3);
    display: grid;
    gap: 0.24rem;
}

.metric p {
    margin: 0;
    color: #98d8fb;
    font-size: 0.65rem;
    letter-spacing: 0.08em;
}

.metric strong {
    font-size: 1.08rem;
    color: #dff2ff;
}

.metric small {
    color: var(--text-secondary);
    font-size: 0.74rem;
}

.tone-hot {
    color: #ffbe9f;
}

.tone-warm {
    color: #ffd898;
}

.tone-calm {
    color: #84f0cf;
}

.chart-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
}

.chart-panel,
.venue-board {
    background: rgba(8, 22, 40, 0.74);
}

.chart-panel header,
.venue-board header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.72rem;
    gap: 0.65rem;
}

.chart-panel h3,
.venue-board h3 {
    margin: 0;
}

.chart-panel small,
.venue-board small {
    color: var(--text-tertiary);
    font-size: 0.72rem;
}

.venues-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.6rem;
}

.venue-card {
    border: 1px solid rgba(126, 185, 232, 0.26);
    border-radius: var(--radius-md);
    background: rgba(8, 22, 40, 0.7);
    padding: 0.72rem;
}

.venue-card header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.55rem;
    margin-bottom: 0.4rem;
}

.venue-card h4 {
    margin: 0;
    font-size: 0.9rem;
}

.price {
    font-size: 1.02rem;
    color: #d8efff;
}

.status-pill {
    font-size: 0.62rem;
    border-radius: 999px;
    padding: 0.2rem 0.5rem;
}

.status-online {
    background: rgba(23, 200, 136, 0.17);
    color: #78efbf;
}

.status-degraded {
    background: rgba(244, 180, 68, 0.2);
    color: #ffd79a;
}

.status-offline {
    background: rgba(255, 116, 116, 0.2);
    color: #ffb1b1;
}

.mode {
    margin: 0.44rem 0 0;
    color: #d9efff;
    font-size: 0.84rem;
}

.notes {
    margin: 0.4rem 0 0;
    color: var(--text-secondary);
    font-size: 0.78rem;
}

.ops-log {
    border-radius: var(--radius-lg);
    background: rgba(8, 22, 40, 0.74);
}

.ops-log header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.66rem;
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
    gap: 0.38rem;
    color: #d7ebfe;
}

.ops-log li {
    font-size: 0.82rem;
}

.empty {
    margin: 0;
    color: var(--text-secondary);
}

@media (max-width: 1120px) {
    .metric-strip {
        grid-template-columns: 1fr;
    }

    .chart-grid {
        grid-template-columns: 1fr;
    }

    .venues-grid {
        grid-template-columns: 1fr;
    }
}
</style>

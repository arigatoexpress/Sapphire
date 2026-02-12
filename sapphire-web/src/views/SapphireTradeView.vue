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
const chartCandles = ref<OhlcCandle[]>([])
const chartSourceLabel = ref('Waiting for live OHLC feed')
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

const latestMergedClose = computed(() => {
    const tail = chartCandles.value[chartCandles.value.length - 1]
    return tail ? Number(tail.close) : null
})

const executionModeLabel = computed(() =>
    controlState.value?.tradingview_execution_enabled ? 'signals live' : 'workbench dry-run',
)

const defaultQtyLabel = computed(() => {
    const qty = Number(controlState.value?.tradingview_default_quantity || 0)
    return qty > 0 ? qty.toString() : 'n/a'
})

const pendingDecisionCount = computed(() => Number(controlState.value?.pending_autonomy_decisions || 0))

const mergedRangePct = computed(() => {
    if (chartCandles.value.length < 2) return null
    const highs = chartCandles.value.map((item) => Number(item.high))
    const lows = chartCandles.value.map((item) => Number(item.low))
    const tail = chartCandles.value[chartCandles.value.length - 1]
    const close = Number(tail?.close || 0)
    if (!Number.isFinite(close) || close <= 0) return null
    const spread = Math.max(...highs) - Math.min(...lows)
    return (spread / close) * 100
})

const momentumPct = computed(() => {
    if (chartCandles.value.length < 8) return null
    const head = chartCandles.value[0]
    const tail = chartCandles.value[chartCandles.value.length - 1]
    const first = Number(head?.close || 0)
    const last = Number(tail?.close || 0)
    if (!Number.isFinite(first) || first <= 0 || !Number.isFinite(last)) return null
    return ((last - first) / first) * 100
})

const volatilityTone = computed(() => {
    const range = mergedRangePct.value ?? 0
    if (range >= 4) return 'tone-hot'
    if (range >= 2) return 'tone-warm'
    return 'tone-calm'
})

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

const mergeVenueCandles = (series: OhlcCandle[][]): OhlcCandle[] => {
    const byTime = new Map<number, OhlcCandle[]>()
    for (const candles of series) {
        for (const candle of candles) {
            const key = Math.floor(Number(candle.time))
            const existing = byTime.get(key) || []
            existing.push(candle)
            byTime.set(key, existing)
        }
    }

    return Array.from(byTime.entries())
        .sort((a, b) => a[0] - b[0])
        .slice(-180)
        .map(([time, candles]) => {
            const opens = candles.map((item) => Number(item.open))
            const closes = candles.map((item) => Number(item.close))
            const highs = candles.map((item) => Number(item.high))
            const lows = candles.map((item) => Number(item.low))
            const volume = candles.reduce((sum, item) => sum + Number(item.volume || 0), 0)
            const avgOpen = opens.reduce((sum, value) => sum + value, 0) / opens.length
            const avgClose = closes.reduce((sum, value) => sum + value, 0) / closes.length
            return {
                time,
                open: avgOpen,
                high: Math.max(...highs),
                low: Math.min(...lows),
                close: avgClose,
                volume,
            }
        })
}

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
            fetchMarketOHLC({ venue: 'ASTER', symbol: 'SOL', interval: '1m', limit: 180 }),
            fetchMarketOHLC({ venue: 'LIGHTER', symbol: 'SOL', interval: '1m', limit: 180 }),
            fetchControlStatus(),
        ])

        if (platforms) applyPlatformPayload(platforms)
        if (Array.isArray(logs)) {
            recentOps.value = logs
                .map((entry: any) => entry?.message || entry?.msg || String(entry))
                .filter((message: string) =>
                    /aster|lighter|deploy|risk|position|execution|promotion|allocation|heartbeat/i.test(message),
                )
                .slice(-8)
                .reverse()
        }

        const asterCandles = normalizeCandles(asterOhlc?.candles)
        const lighterCandles = normalizeCandles(lighterOhlc?.candles)
        const merged = mergeVenueCandles([asterCandles, lighterCandles])
        chartCandles.value = merged

        if (controlPayload?.ok) {
            controlState.value = {
                tradingview_execution_enabled: Boolean(controlPayload.tradingview_execution_enabled),
                tradingview_default_quantity: Number(controlPayload.tradingview_default_quantity || 0),
                pending_autonomy_decisions: Number(controlPayload.pending_autonomy_decisions || 0),
            }
        }

        if (merged.length > 0) {
            chartSourceLabel.value = `Live OHLC merge · ASTER ${asterCandles.length} + LIGHTER ${lighterCandles.length}`
        } else {
            chartSourceLabel.value = 'Waiting for live OHLC feed'
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
                <h2>Autonomous execution board for ASTER + LIGHTER.</h2>
                <p>DEX-native execution is primary. Web controls remain read-only and operator overrides stay Telegram-routed.</p>
            </div>
            <div class="health-line">
                <span class="chip">
                    Healthy venues: {{ healthyCount }}/{{ venues.length }}
                </span>
                <span class="chip muted">
                    Posture: {{ portfolioPosture }}
                </span>
                <span class="chip muted">
                    Sync: {{ refreshAge }}
                </span>
                <span class="chip muted">
                    DEX execution: ASTER + LIGHTER
                </span>
                <span class="chip muted">
                    TV: {{ executionModeLabel }} · qty {{ defaultQtyLabel }}
                </span>
                <span class="chip muted">
                    Pending decisions: {{ pendingDecisionCount }}
                </span>
            </div>
        </section>

        <section class="metric-strip">
            <article class="metric card glass-lift">
                <p class="font-mono">Merged Mark</p>
                <strong>{{ latestMergedClose === null ? 'n/a' : `$${latestMergedClose.toFixed(3)}` }}</strong>
                <small>Cross-venue weighted close from live OHLC merge.</small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">Range (Window)</p>
                <strong :class="volatilityTone">{{ mergedRangePct === null ? 'n/a' : `${mergedRangePct.toFixed(2)}%` }}</strong>
                <small>High/low spread over the active telemetry window.</small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">Momentum Delta</p>
                <strong :class="{ bullish: (momentumPct || 0) > 0, bearish: (momentumPct || 0) < 0 }">
                    {{ momentumPct === null ? 'n/a' : `${momentumPct.toFixed(2)}%` }}
                </strong>
                <small>Directional delta across the current merged series.</small>
            </article>
        </section>

        <section class="grid">
            <article class="chart-panel card glass-lift">
                <header>
                    <h3 class="font-mono">Cross-Venue Price Pulse</h3>
                    <small>{{ chartSourceLabel }}</small>
                </header>
                <TradingChart :candles="chartCandles" :height="300" />
            </article>

            <article class="venue-board card">
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
                        <strong class="price">
                            {{ venue.price === null ? 'n/a' : `$${venue.price.toFixed(3)}` }}
                        </strong>
                        <p class="mode">{{ venue.mode }}</p>
                        <p class="notes">{{ venue.notes }}</p>
                    </article>
                </div>
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

.grid {
    display: grid;
    grid-template-columns: 1.15fr 1fr;
    gap: 0.8rem;
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

.bullish {
    color: #7deec2;
}

.bearish {
    color: #ffb2b2;
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

    .grid {
        grid-template-columns: 1fr;
    }
}
</style>

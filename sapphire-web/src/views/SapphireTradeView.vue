<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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

interface MarketSnapshot {
    symbol: string
    price: number | null
    change1h: number | null
    change4h: number | null
    volatility: number | null
    source: string
    history: number[]
}

const SYMBOLS = ['BTC', 'ETH', 'SOL', 'AVAX', 'DOGE', 'HYPE']

const selectedSymbol = ref('BTC')
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
const marketSnapshots = ref<MarketSnapshot[]>([])
const asterMeta = ref<VenueChartMeta>({
    symbol: 'BTC',
    trackingSymbol: 'BTCUSDT',
    source: 'unavailable',
    interval: '1m',
    generatedAt: 0,
})
const lighterMeta = ref<VenueChartMeta>({
    symbol: 'BTC',
    trackingSymbol: 'BTC',
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

const formatPct = (value: number | null, digits = 2) => {
    if (value === null || !Number.isFinite(value)) return 'n/a'
    return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

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

const computeChangePct = (history: number[], lookback: number): number | null => {
    if (!Array.isArray(history) || history.length <= lookback) return null
    const latest = Number(history[history.length - 1] || 0)
    const anchor = Number(history[Math.max(0, history.length - 1 - lookback)] || 0)
    if (!Number.isFinite(latest) || !Number.isFinite(anchor) || anchor <= 0) return null
    return ((latest - anchor) / anchor) * 100
}

const estimateVolatility = (history: number[]): number | null => {
    if (!Array.isArray(history) || history.length < 8) return null
    const returns: number[] = []
    for (let i = 1; i < history.length; i += 1) {
        const prev = Number(history[i - 1] || 0)
        const curr = Number(history[i] || 0)
        if (!Number.isFinite(prev) || !Number.isFinite(curr) || prev <= 0) continue
        returns.push((curr - prev) / prev)
    }
    if (returns.length < 5) return null
    const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length
    const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / returns.length
    return Math.sqrt(Math.max(variance, 0)) * 100
}

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

const marketBreadth = computed(() => {
    const snapshots = marketSnapshots.value
    if (!snapshots.length) return { advancing: 0, declining: 0, breadth: 0 }
    const advancing = snapshots.filter((item) => (item.change1h ?? 0) > 0).length
    const declining = snapshots.length - advancing
    const breadth = snapshots.length ? Math.round((advancing / snapshots.length) * 100) : 0
    return { advancing, declining, breadth }
})

const broadMarketPosture = computed(() => {
    const breadth = marketBreadth.value.breadth
    if (breadth >= 66) return 'Risk-on expansion'
    if (breadth >= 45) return 'Balanced rotation'
    return 'Defensive/risk-off'
})

const tradeIdeas = computed(() => {
    const ideas: Array<{ title: string; detail: string; tone: 'bullish' | 'neutral' | 'defensive' }> = []
    const strongest = [...marketSnapshots.value]
        .filter((item) => item.change1h !== null)
        .sort((a, b) => Number(b.change1h || 0) - Number(a.change1h || 0))[0]
    if (strongest && (strongest.change1h || 0) > 1.2) {
        ideas.push({
            title: `Momentum leadership: ${strongest.symbol}`,
            detail: `${formatPct(strongest.change1h)} over 1h with venue-native strength. Consider trend continuation setups with tight invalidation.`,
            tone: 'bullish',
        })
    }

    if ((spreadPct.value || 0) >= 0.45) {
        ideas.push({
            title: `${selectedSymbol.value} cross-venue dislocation`,
            detail: `Spread at ${formatPct(spreadPct.value, 3)} between ASTER/LIGHTER. Candidate for controlled mean-reversion arbitrage checks.`,
            tone: 'neutral',
        })
    }

    if (marketBreadth.value.breadth <= 40) {
        ideas.push({
            title: 'Breadth deterioration guardrail',
            detail: `Only ${marketBreadth.value.advancing}/${marketSnapshots.value.length} tracked assets are advancing. Prefer defensive sizing and stricter filters.`,
            tone: 'defensive',
        })
    }

    if (!ideas.length) {
        ideas.push({
            title: 'Range compression regime',
            detail: 'Cross-asset flow is mixed with contained dislocations. Favor patience and wait for regime expansion before scaling risk.',
            tone: 'neutral',
        })
    }

    return ideas.slice(0, 3)
})

const loadOpsView = async () => {
    try {
        const [platforms, logs, controlPayload, asterOhlc, lighterOhlc, basketPayloads] = await Promise.all([
            fetchPlatformStatus(),
            fetchSystemLogs(),
            fetchControlStatus(),
            fetchMarketOHLC({ venue: 'ASTER', symbol: selectedSymbol.value, interval: '1m', limit: 220 }),
            fetchMarketOHLC({ venue: 'LIGHTER', symbol: selectedSymbol.value, interval: '1m', limit: 220 }),
            Promise.all(
                SYMBOLS.map((symbol) =>
                    fetchMarketOHLC({ venue: 'ASTER', symbol, interval: '5m', limit: 96 }),
                ),
            ),
        ])

        if (platforms) applyPlatformPayload(platforms)

        if (Array.isArray(logs)) {
            recentOps.value = logs
                .map((entry: any) => entry?.message || entry?.msg || String(entry))
                .filter((message: string) =>
                    /aster|lighter|deploy|risk|position|execution|promotion|allocation|heartbeat|ohlc|arb|market/i.test(message),
                )
                .slice(-10)
                .reverse()
        }

        asterCandles.value = normalizeCandles(asterOhlc?.candles)
        lighterCandles.value = normalizeCandles(lighterOhlc?.candles)

        asterMeta.value = {
            symbol: String(asterOhlc?.symbol || selectedSymbol.value).toUpperCase(),
            trackingSymbol: String(asterOhlc?.tracking_symbol || asterOhlc?.symbol || selectedSymbol.value).toUpperCase(),
            source: String(asterOhlc?.source || 'unavailable'),
            interval: String(asterOhlc?.interval || '1m'),
            generatedAt: Number(asterOhlc?.generated_at || 0),
        }

        lighterMeta.value = {
            symbol: String(lighterOhlc?.symbol || selectedSymbol.value).toUpperCase(),
            trackingSymbol: String(lighterOhlc?.tracking_symbol || lighterOhlc?.symbol || selectedSymbol.value).toUpperCase(),
            source: String(lighterOhlc?.source || 'unavailable'),
            interval: String(lighterOhlc?.interval || '1m'),
            generatedAt: Number(lighterOhlc?.generated_at || 0),
        }

        const snapshots: MarketSnapshot[] = SYMBOLS.map((symbol, index) => {
            const payload = basketPayloads[index]
            const candles = normalizeCandles(payload?.candles)
            const history = candles.map((item) => Number(item.close)).filter((value) => Number.isFinite(value))
            const price = history.length ? Number(history[history.length - 1]) : null
            return {
                symbol,
                price,
                change1h: computeChangePct(history, 12),
                change4h: computeChangePct(history, 48),
                volatility: estimateVolatility(history.slice(-48)),
                source: String(payload?.source || 'unavailable'),
                history: history.slice(-30),
            }
        })

        marketSnapshots.value = snapshots

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

watch(selectedSymbol, () => {
    loadOpsView()
})

onMounted(() => {
    loadOpsView()
    refreshTimer = setInterval(loadOpsView, 15000)
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
                <h2>Multi-asset venue intelligence across ASTER + LIGHTER.</h2>
                <p>
                    SapphireTrade now tracks broader market structure, cross-venue dislocations, and actionable setup ideas while keeping
                    execution telemetry grounded in live DEX-native feeds.
                </p>
            </div>
            <div class="hero-controls">
                <label class="symbol-picker">
                    <span class="font-mono">Chart symbol</span>
                    <select v-model="selectedSymbol">
                        <option v-for="symbol in SYMBOLS" :key="symbol" :value="symbol">{{ symbol }}</option>
                    </select>
                </label>
            </div>
            <div class="health-line">
                <span class="chip">Healthy venues: {{ healthyCount }}/{{ venues.length }}</span>
                <span class="chip muted">Posture: {{ portfolioPosture }}</span>
                <span class="chip muted">Market breadth: {{ marketBreadth.breadth }}%</span>
                <span class="chip muted">Regime: {{ broadMarketPosture }}</span>
                <span class="chip muted">TV: {{ executionModeLabel }} · qty {{ defaultQtyLabel }}</span>
                <span class="chip muted">Pending decisions: {{ pendingDecisionCount }}</span>
                <span class="chip muted">Sync: {{ refreshAge }}</span>
            </div>
        </section>

        <section class="metric-strip">
            <article class="metric card glass-lift">
                <p class="font-mono">{{ selectedSymbol }} ASTER Mark</p>
                <strong>{{ formatPrice(effectiveAsterPrice) }}</strong>
                <small>source {{ asterMeta.source }} · {{ asterMeta.interval }}</small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">{{ selectedSymbol }} LIGHTER Mark</p>
                <strong>{{ formatPrice(effectiveLighterPrice) }}</strong>
                <small>source {{ lighterMeta.source }} · {{ lighterMeta.interval }}</small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">Cross-Venue Spread</p>
                <strong :class="spreadTone">{{ spreadPct === null ? 'n/a' : `${spreadPct.toFixed(3)}%` }}</strong>
                <small>absolute {{ spreadAbs === null ? 'n/a' : formatPrice(spreadAbs) }}</small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">Breadth Advance/Decline</p>
                <strong>{{ marketBreadth.advancing }}/{{ marketBreadth.declining }}</strong>
                <small>{{ broadMarketPosture }}</small>
            </article>
        </section>

        <section class="chart-grid">
            <article class="chart-panel card glass-lift">
                <header>
                    <h3 class="font-mono">ASTER ({{ asterMeta.trackingSymbol }})</h3>
                    <small>source {{ asterMeta.source }} · req {{ asterMeta.symbol }} · {{ asterMeta.interval }}</small>
                </header>
                <TradingChart :candles="asterCandles" :height="280" />
            </article>

            <article class="chart-panel card glass-lift">
                <header>
                    <h3 class="font-mono">LIGHTER ({{ lighterMeta.trackingSymbol }})</h3>
                    <small>source {{ lighterMeta.source }} · req {{ lighterMeta.symbol }} · {{ lighterMeta.interval }}</small>
                </header>
                <TradingChart :candles="lighterCandles" :height="280" />
            </article>
        </section>

        <section class="breadth-grid">
            <article v-for="snapshot in marketSnapshots" :key="snapshot.symbol" class="breadth-card card glass-lift">
                <header>
                    <span class="font-mono">{{ snapshot.symbol }}</span>
                    <span :class="(snapshot.change1h || 0) >= 0 ? 'tone-calm' : 'tone-hot'">{{ formatPct(snapshot.change1h) }}</span>
                </header>
                <strong>{{ formatPrice(snapshot.price) }}</strong>
                <small>4h {{ formatPct(snapshot.change4h) }} · vol {{ formatPct(snapshot.volatility) }}</small>
                <svg class="sparkline" viewBox="0 0 100 32" preserveAspectRatio="none">
                    <polyline :points="sparklinePoints(snapshot.history)" />
                </svg>
            </article>
        </section>

        <section class="idea-board card glass-lift">
            <header>
                <h3 class="font-mono">Trade Idea Feed</h3>
                <small>Auto-generated from market breadth + venue dislocation telemetry</small>
            </header>
            <article v-for="idea in tradeIdeas" :key="idea.title" class="idea-item" :class="`idea-${idea.tone}`">
                <h4>{{ idea.title }}</h4>
                <p>{{ idea.detail }}</p>
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
                <span class="small">{{ loading ? 'Loading...' : 'Auto-refresh 15s' }}</span>
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

.hero-controls {
    display: flex;
    justify-content: flex-end;
}

.symbol-picker {
    display: grid;
    gap: 0.22rem;
}

.symbol-picker span {
    font-size: 0.64rem;
    color: #9ddfff;
}

.symbol-picker select {
    background: rgba(8, 24, 43, 0.8);
    border: 1px solid rgba(108, 188, 244, 0.42);
    color: #d7eeff;
    border-radius: 10px;
    padding: 0.34rem 0.52rem;
    font-size: 0.78rem;
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
    grid-template-columns: repeat(4, minmax(0, 1fr));
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
.venue-board,
.idea-board {
    background: rgba(8, 22, 40, 0.74);
}

.chart-panel header,
.venue-board header,
.idea-board header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.72rem;
    gap: 0.65rem;
}

.chart-panel h3,
.venue-board h3,
.idea-board h3 {
    margin: 0;
}

.chart-panel small,
.venue-board small,
.idea-board small {
    color: var(--text-tertiary);
    font-size: 0.72rem;
}

.breadth-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.66rem;
}

.breadth-card {
    display: grid;
    gap: 0.3rem;
    background: rgba(8, 22, 40, 0.74);
}

.breadth-card header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.breadth-card strong {
    font-size: 0.95rem;
    color: #def2ff;
}

.breadth-card small {
    color: var(--text-secondary);
    font-size: 0.72rem;
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

.idea-item {
    border: 1px solid rgba(123, 187, 232, 0.25);
    border-radius: 12px;
    background: rgba(8, 22, 41, 0.66);
    padding: 0.62rem;
    margin-top: 0.52rem;
}

.idea-item h4 {
    margin: 0;
    font-size: 0.83rem;
}

.idea-item p {
    margin: 0.3rem 0 0;
    font-size: 0.78rem;
    color: var(--text-secondary);
    line-height: 1.35;
}

.idea-bullish {
    border-color: rgba(108, 226, 172, 0.42);
}

.idea-neutral {
    border-color: rgba(117, 188, 241, 0.42);
}

.idea-defensive {
    border-color: rgba(255, 175, 121, 0.45);
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

@media (max-width: 1320px) {
    .metric-strip {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .breadth-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 1120px) {
    .chart-grid {
        grid-template-columns: 1fr;
    }

    .venues-grid {
        grid-template-columns: 1fr;
    }
}

@media (max-width: 760px) {
    .metric-strip,
    .breadth-grid {
        grid-template-columns: 1fr;
    }

    .hero-controls {
        justify-content: flex-start;
    }
}
</style>

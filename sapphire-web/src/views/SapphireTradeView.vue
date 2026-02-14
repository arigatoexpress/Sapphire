<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import TradingChart from '../components/TradingChart.vue'
import { useControlStore } from '../stores/control'
import { useMarketStore, SYMBOLS } from '../stores/market'
import { formatPrice, formatPct } from '../utils/formatters'
import { sparklinePoints } from '../utils/market'

const ctrl = useControlStore()
const mkt = useMarketStore()

const selectedSymbol = ref('BTC')

/* ── Derived (chart candles read from market store) ── */

const asterCandles = computed(() => mkt.getCandles('ASTER', selectedSymbol.value, '1m'))
const lighterCandles = computed(() => mkt.getCandles('LIGHTER', selectedSymbol.value, '1m'))

const effectiveAster = computed(() => {
    const last = asterCandles.value[asterCandles.value.length - 1]
    return last ? Number(last.close) : null
})
const effectiveLighter = computed(() => {
    const last = lighterCandles.value[lighterCandles.value.length - 1]
    return last ? Number(last.close) : null
})

const spreadPct = computed(() => {
    if (effectiveAster.value === null || effectiveLighter.value === null) return null
    const mid = (effectiveAster.value + effectiveLighter.value) / 2
    if (!Number.isFinite(mid) || mid <= 0) return null
    return (Math.abs(effectiveAster.value - effectiveLighter.value) / mid) * 100
})

const spreadTone = computed(() => {
    const v = spreadPct.value ?? 0
    if (v >= 1.0) return 'tone-hot'
    if (v >= 0.4) return 'tone-warm'
    return 'tone-calm'
})

const marketBreadth = computed(() => {
    if (!mkt.snapshots.length) return { advancing: 0, declining: 0, breadth: 0 }
    const adv = mkt.snapshots.filter((s) => (s.change1h ?? 0) > 0).length
    return { advancing: adv, declining: mkt.snapshots.length - adv, breadth: Math.round((adv / mkt.snapshots.length) * 100) }
})

const breadthPosture = computed(() => {
    const b = marketBreadth.value.breadth
    if (b >= 66) return 'Risk-on'
    if (b >= 45) return 'Balanced'
    return 'Risk-off'
})

/* ── Freshness (unified from both stores) ── */
const loading = computed(() => ctrl.loading || mkt.loading)
const fetchError = computed(() => ctrl.fetchError || mkt.fetchError)
const lastFetchAt = computed(() => Math.max(ctrl.lastFetchAt, mkt.lastFetchAt))
const dataAge = computed(() => {
    if (!lastFetchAt.value) return null
    return Math.floor((Date.now() - lastFetchAt.value) / 1000)
})
const isStale = computed(() => (dataAge.value ?? 999) > 30)

/* ── Lifecycle ── */

const reload = () => {
    ctrl.refresh()
    mkt.fetchAll(selectedSymbol.value)
}

watch(selectedSymbol, () => mkt.fetchAll(selectedSymbol.value))

onMounted(() => {
    ctrl.subscribe()
    mkt.startPolling(() => selectedSymbol.value)
})

onUnmounted(() => {
    ctrl.unsubscribe()
    mkt.stopPolling()
})
</script>

<template>
    <div class="trade-view fade-in" aria-label="Trade dashboard">
        <div v-if="loading && !lastFetchAt" class="status-bar loading-bar" role="status" aria-live="polite">
            <span class="pulse-dot" aria-hidden="true"></span> Connecting to Sapphire...
        </div>
        <div v-else-if="fetchError" class="status-bar error-bar" role="alert" tabindex="0" @click="reload" @keydown.enter="reload" @keydown.space.prevent="reload">
            {{ fetchError }} — tap to retry
        </div>
        <div v-else-if="isStale" class="status-bar stale-bar" role="status" aria-live="polite">
            Data {{ dataAge }}s old — awaiting refresh
        </div>

        <div class="topstrip">
            <label class="symbol-picker">
                <span class="font-mono" id="symbol-label-trade">SYMBOL</span>
                <select v-model="selectedSymbol" aria-labelledby="symbol-label-trade">
                    <option v-for="s in SYMBOLS" :key="s" :value="s">{{ s }}</option>
                </select>
            </label>
        </div>

        <!-- Skeleton loading state -->
        <template v-if="loading && !lastFetchAt">
            <section class="ops-strip">
                <article v-for="i in 5" :key="i" class="ops-card card glass-lift">
                    <div class="skel-line skel-sm"></div>
                    <div class="skel-line skel-lg"></div>
                </article>
            </section>
            <section class="metric-strip">
                <article v-for="i in 4" :key="i" class="metric card glass-lift">
                    <div class="skel-line skel-sm"></div>
                    <div class="skel-line skel-lg"></div>
                    <div class="skel-line skel-xs"></div>
                </article>
            </section>
            <section class="chart-grid">
                <article v-for="i in 2" :key="i" class="chart-panel card glass-lift">
                    <div class="skel-line skel-sm" style="margin-bottom: 0.7rem"></div>
                    <div class="skel-chart"></div>
                </article>
            </section>
        </template>

        <template v-else>
        <section class="ops-strip" aria-label="Trading operations summary" aria-live="polite">
            <article class="ops-card card glass-lift" aria-label="Total trades">
                <p class="font-mono">Trades</p>
                <strong class="glow">{{ ctrl.totalTrades }}</strong>
            </article>
            <article class="ops-card card glass-lift" aria-label="Win rate">
                <p class="font-mono">Win Rate</p>
                <strong class="glow">{{ ctrl.winRate.toFixed(1) }}%</strong>
            </article>
            <article class="ops-card card glass-lift" :aria-label="`Profit and loss: ${ctrl.realizedPnl >= 0 ? 'positive' : 'negative'} ${Math.abs(ctrl.realizedPnl).toFixed(4)}`">
                <p class="font-mono">PnL</p>
                <strong class="glow" :class="ctrl.realizedPnl >= 0 ? 'tone-calm' : 'tone-hot'">{{ ctrl.realizedPnl >= 0 ? '+' : '' }}{{ ctrl.realizedPnl.toFixed(4) }}</strong>
            </article>
            <article class="ops-card card glass-lift" :aria-label="`Execution stage: ${ctrl.executionStage}, multiplier ${ctrl.stageMultiplier.toFixed(2)}x`">
                <p class="font-mono">Stage</p>
                <strong class="glow" :class="ctrl.executionStage === 'LIVE' ? 'tone-calm' : 'tone-warm'">{{ ctrl.executionStage }}</strong>
                <small>{{ ctrl.stageMultiplier.toFixed(2) }}x</small>
            </article>
            <article class="ops-card card glass-lift" :aria-label="`Dispatch: ${ctrl.killSwitchActive ? 'kill switch active' : ctrl.dexLiveDispatch ? 'live' : 'off'}`">
                <p class="font-mono">Dispatch</p>
                <strong :class="ctrl.killSwitchActive ? 'tone-hot' : ctrl.dexLiveDispatch ? 'tone-calm' : 'tone-warm'">{{ ctrl.killSwitchActive ? 'KILL' : ctrl.dexLiveDispatch ? 'LIVE' : 'OFF' }}</strong>
            </article>
        </section>

        <section class="metric-strip">
            <article class="metric card glass-lift">
                <p class="font-mono">{{ selectedSymbol }} ASTER</p>
                <strong class="glow">{{ formatPrice(effectiveAster) }}</strong>
                <small>{{ mkt.asterMeta.source }} · {{ mkt.asterMeta.interval }}</small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">{{ selectedSymbol }} LIGHTER</p>
                <strong class="glow">{{ formatPrice(effectiveLighter) }}</strong>
                <small>{{ mkt.lighterMeta.source }} · {{ mkt.lighterMeta.interval }}</small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">Cross-Venue Spread</p>
                <strong :class="spreadTone" class="glow">{{ spreadPct === null ? 'n/a' : `${spreadPct.toFixed(3)}%` }}</strong>
                <small>dislocation monitor</small>
            </article>
            <article class="metric card glass-lift">
                <p class="font-mono">Market Breadth</p>
                <strong class="glow">{{ marketBreadth.breadth }}%</strong>
                <small>{{ breadthPosture }} · {{ marketBreadth.advancing }} adv / {{ marketBreadth.declining }} dec</small>
            </article>
        </section>

        <section class="chart-grid">
            <article class="chart-panel card glass-lift">
                <header>
                    <h3 class="font-mono">ASTER ({{ mkt.asterMeta.trackingSymbol }})</h3>
                    <small>{{ mkt.asterMeta.source }} · {{ mkt.asterMeta.interval }}</small>
                </header>
                <TradingChart :candles="asterCandles" :height="400" />
            </article>
            <article class="chart-panel card glass-lift">
                <header>
                    <h3 class="font-mono">LIGHTER ({{ mkt.lighterMeta.trackingSymbol }})</h3>
                    <small>{{ mkt.lighterMeta.source }} · {{ mkt.lighterMeta.interval }}</small>
                </header>
                <TradingChart :candles="lighterCandles" :height="400" />
            </article>
        </section>

        <section class="breadth-section">
            <h3 class="font-mono section-title">Market Breadth Scanner</h3>
            <div class="breadth-grid">
                <article v-for="snap in mkt.snapshots" :key="snap.symbol" class="breadth-card card glass-lift">
                    <header>
                        <span class="breadth-sym">{{ snap.symbol }}</span>
                        <span class="breadth-change" :class="(snap.change1h || 0) >= 0 ? 'tone-calm' : 'tone-hot'">{{ formatPct(snap.change1h) }}</span>
                    </header>
                    <strong>{{ formatPrice(snap.price) }}</strong>
                    <small>4h {{ formatPct(snap.change4h) }} · vol {{ formatPct(snap.volatility) }}</small>
                    <svg class="sparkline" viewBox="0 0 100 38" preserveAspectRatio="none" role="img" :aria-label="`${snap.symbol} price sparkline`">
                        <polyline :points="sparklinePoints(snap.history)" />
                    </svg>
                </article>
            </div>
        </section>
        </template>
    </div>
</template>

<style scoped>
.trade-view {
    display: grid;
    gap: 1rem;
}

.topstrip {
    display: flex;
    justify-content: flex-end;
    align-items: center;
}

.symbol-picker {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.symbol-picker span {
    font-size: 0.72rem;
    color: var(--text-tertiary);
    letter-spacing: 0.06em;
}

.symbol-picker select {
    background: var(--bg-card);
    border: 1px solid var(--border-accent);
    color: var(--text-primary);
    border-radius: var(--radius-sm);
    padding: 0.4rem 0.6rem;
    font-family: var(--font-mono);
    font-size: 0.82rem;
    cursor: pointer;
}

/* ── Operations Strip ── */
.ops-strip {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.6rem;
}

.ops-card {
    display: grid;
    gap: 0.15rem;
    text-align: center;
    padding: 0.55rem 0.4rem;
}

.ops-card p {
    margin: 0;
    color: var(--text-tertiary);
    font-size: 0.62rem;
    letter-spacing: 0.06em;
}

.ops-card strong {
    font-size: 1.15rem;
    color: var(--text-primary);
}

.ops-card small {
    color: var(--text-tertiary);
    font-size: 0.62rem;
}

.metric-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.8rem;
}

.metric {
    display: grid;
    gap: 0.3rem;
}

.metric p {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.72rem;
    letter-spacing: 0.06em;
}

.metric strong {
    font-size: 1.3rem;
    color: var(--text-primary);
}

.metric small {
    color: var(--text-tertiary);
    font-size: 0.72rem;
}

.tone-hot { color: var(--color-error); }
.tone-warm { color: var(--color-warning); }
.tone-calm { color: var(--color-terminal); }

.chart-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
}

.chart-panel header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.7rem;
    gap: 0.5rem;
}

.chart-panel h3 {
    margin: 0;
    font-size: 0.85rem;
}

.chart-panel small {
    color: var(--text-tertiary);
    font-size: 0.72rem;
}

.section-title {
    margin: 0 0 0.6rem;
    font-size: 0.85rem;
}

.breadth-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(160px, 1fr));
    gap: 0.7rem;
}

.breadth-card {
    display: grid;
    gap: 0.3rem;
}

.breadth-card header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.breadth-sym {
    font-size: 0.82rem;
    font-weight: 600;
    letter-spacing: 0.04em;
}

.breadth-change {
    font-size: 0.82rem;
    font-weight: 500;
}

.breadth-card strong {
    font-size: 1.05rem;
    color: var(--text-primary);
}

.breadth-card small {
    color: var(--text-tertiary);
    font-size: 0.72rem;
}

.sparkline {
    width: 100%;
    height: 44px;
    border-radius: var(--radius-sm);
    background: rgba(10, 20, 10, 0.4);
}

.sparkline polyline {
    fill: none;
    stroke: var(--color-terminal);
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
    filter: drop-shadow(0 0 4px rgba(32, 194, 14, 0.4));
}

@media (max-width: 1320px) {
    .metric-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .breadth-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 1120px) {
    .chart-grid { grid-template-columns: 1fr; }
}

/* ── Status Bars ── */
.status-bar {
    padding: 0.45rem 0.8rem;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    border-radius: var(--radius-sm);
    text-align: center;
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

@media (max-width: 760px) {
    .ops-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .metric-strip,
    .breadth-grid { grid-template-columns: 1fr; }
}

/* ── Skeleton Loading ── */
.skel-line {
    border-radius: var(--radius-xs);
    animation: skelPulse 1.6s ease-in-out infinite;
}

.skel-lg {
    width: 55%;
    height: 1.15rem;
    margin: 0 auto;
    background: rgba(32, 194, 14, 0.08);
}

.skel-sm {
    width: 40%;
    height: 0.6rem;
    margin: 0 auto 0.3rem;
    background: rgba(32, 194, 14, 0.05);
}

.skel-xs {
    width: 50%;
    height: 0.5rem;
    margin: 0.2rem auto 0;
    background: rgba(32, 194, 14, 0.04);
}

.skel-chart {
    width: 100%;
    height: 400px;
    border-radius: var(--radius-sm);
    background: rgba(32, 194, 14, 0.03);
    animation: skelPulse 1.6s ease-in-out infinite 0.2s;
}

@keyframes skelPulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 0.85; }
}
</style>

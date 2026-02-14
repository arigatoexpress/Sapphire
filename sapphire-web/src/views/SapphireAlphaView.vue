<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import TradingChart from '../components/TradingChart.vue'
import {
    connectionHealth,
    fetchRoutingInfo,
    fetchSecuritySkillsStatus,
    type SecuritySkillsStatusResponse,
} from '../api/client'
import { useControlStore } from '../stores/control'
import { useMarketStore, SYMBOLS } from '../stores/market'
import { formatPrice, formatPct } from '../utils/formatters'
import { sparklinePoints, computeRSI, computeMomentum } from '../utils/market'

const ctrl = useControlStore()
const mkt = useMarketStore()

const selectedSymbol = ref('BTC')

/* ── Alpha-specific state (routing, security — not shared) ── */
const routingConfidence = ref<number | null>(null)
const routingMode = ref('guarded')
const security = ref<SecuritySkillsStatusResponse | null>(null)

/* ── Chart candles from market store ── */
const alphaCandles = computed(() => mkt.getCandles('ASTER', selectedSymbol.value, '1m'))
const lighterCandles = computed(() => mkt.getCandles('LIGHTER', selectedSymbol.value, '1m'))

const chartSourceLabel = computed(() =>
    alphaCandles.value.length > 0
        ? `ASTER · ${mkt.asterMeta.trackingSymbol} (${mkt.asterMeta.source})`
        : 'Awaiting OHLC feed'
)
const compareSourceLabel = computed(() =>
    lighterCandles.value.length > 0
        ? `LIGHTER · ${mkt.lighterMeta.trackingSymbol} (${mkt.lighterMeta.source})`
        : 'Awaiting venue feed'
)

/* ── Extended snapshots with RSI + momentum (Alpha adds these on top of market store) ── */
interface AlphaSnapshot {
    symbol: string
    price: number | null
    change1h: number | null
    change6h: number | null
    volatility: number | null
    confidence: number
    rsi: number | null
    momentum: number | null
    history: number[]
}

const snapshots = computed<AlphaSnapshot[]>(() =>
    mkt.snapshots.map((s) => {
        const rsi = computeRSI(s.history, 14)
        const momentum = computeMomentum(s.history, 10)
        const confidence = Math.max(0, Math.min(100, Math.round(
            (s.change1h || 0) * 12 + (s.change6h || 0) * 4 - (s.volatility || 0) * 2 + 50
        )))
        return { ...s, rsi, momentum, confidence }
    })
)

/* ── Freshness (unified from both stores + alpha-specific fetches) ── */
const loading = computed(() => ctrl.loading || mkt.loading)
const fetchError = computed(() => ctrl.fetchError || mkt.fetchError)
const lastFetchAt = computed(() => Math.max(ctrl.lastFetchAt, mkt.lastFetchAt))
const dataAge = computed(() => {
    if (!lastFetchAt.value) return null
    return Math.floor((Date.now() - lastFetchAt.value) / 1000)
})
const isStale = computed(() => (dataAge.value ?? 999) > 30)

/* ── Derived ── */

const pendingDecisions = computed(() => ctrl.pendingDecisions)

const executionMode = computed(() => {
    const stage = ctrl.executionStage
    if (stage === 'FULL_LIVE') return 'DEX live'
    if (stage === 'STAGED_LIVE') return 'DEX staged'
    if (stage === 'PAPER') return 'Paper mode'
    return stage
})

const marketBreadth = computed(() => {
    const active = snapshots.value.filter((s) => s.change1h !== null)
    const adv = active.filter((s) => (s.change1h || 0) > 0).length
    return { advancing: adv, declining: Math.max(0, active.length - adv), breadth: active.length ? Math.round((adv / active.length) * 100) : 0 }
})

const macroRegime = computed(() => {
    const b = marketBreadth.value.breadth
    if (b >= 65) return 'Expansion'
    if (b >= 45) return 'Rotation'
    return 'Contraction'
})

const avgRSI = computed(() => {
    const valid = snapshots.value.filter((s) => s.rsi !== null).map((s) => s.rsi!)
    if (!valid.length) return null
    return Math.round(valid.reduce((a, b) => a + b, 0) / valid.length)
})

const rsiTone = computed(() => {
    if (avgRSI.value === null) return ''
    if (avgRSI.value >= 70) return 'tone-hot'
    if (avgRSI.value <= 30) return 'tone-cold'
    return 'tone-neutral'
})

const insightCards = computed(() => [
    {
        title: 'Market Breadth',
        value: `${marketBreadth.value.breadth}%`,
        detail: `${marketBreadth.value.advancing} adv · ${marketBreadth.value.declining} dec · ${macroRegime.value}`,
    },
    {
        title: 'Avg RSI (14)',
        value: avgRSI.value !== null ? `${avgRSI.value}` : 'n/a',
        detail: avgRSI.value !== null ? (avgRSI.value >= 70 ? 'Overbought zone' : avgRSI.value <= 30 ? 'Oversold zone' : 'Neutral range') : 'Calculating...',
    },
    {
        title: 'Routing Confidence',
        value: routingConfidence.value === null ? 'n/a' : `${routingConfidence.value}%`,
        detail: `Mode: ${routingMode.value}`,
    },
    {
        title: 'Signal Throughput',
        value: `${ctrl.totalTrades} trades`,
        detail: `Win ${ctrl.winRate}% · PnL ${ctrl.realizedPnl.toFixed(4)}`,
    },
    {
        title: 'Execution Stage',
        value: ctrl.executionStage,
        detail: `Multiplier ${ctrl.stageMultiplier.toFixed(2)}x`,
    },
    {
        title: 'Skill Security',
        value: security.value?.enabled
            ? security.value?.api_key_configured ? `VT ${security.value.enforcement_mode}` : 'VT key missing'
            : 'VT disabled',
        detail: security.value?.enabled
            ? `Skills ${security.value.skills_dir_exists ? 'ready' : 'missing'} · auto-upload ${security.value.upload_if_missing_default ? 'on' : 'off'}`
            : 'Enable VT for skill scanning',
    },
])

const readinessScore = computed(() => {
    const conf = routingConfidence.value ?? 0
    const execBoost = ctrl.dexLiveDispatch ? 5 : 0
    const qPenalty = Math.min(20, pendingDecisions.value * 4)
    const breadthBoost = Math.round((marketBreadth.value.breadth - 50) * 0.2)
    return Math.max(0, Math.min(100, Math.round(conf + execBoost + breadthBoost - qPenalty)))
})

const readinessTone = computed(() => {
    if (readinessScore.value >= 70) return 'tone-strong'
    if (readinessScore.value >= 50) return 'tone-balanced'
    return 'tone-guarded'
})

const strategyRail = computed(() => [
    { label: 'Ingest', detail: alphaCandles.value.length > 0 ? 'Live DEX feeds active' : 'Awaiting data', status: alphaCandles.value.length > 0 ? 'ready' : 'pending' },
    { label: 'Synthesize', detail: `${snapshots.value.length} assets tracked`, status: snapshots.value.length > 0 ? 'ready' : 'pending' },
    { label: 'Validate', detail: `${pendingDecisions.value} decision(s) pending`, status: pendingDecisions.value > 0 ? 'pending' : 'ready' },
    { label: 'Route', detail: executionMode.value, status: ctrl.rawControl ? 'ready' : 'pending' },
])

const alphaIdeas = computed(() => {
    const ideas: Array<{ title: string; detail: string; tone: 'bullish' | 'neutral' | 'defensive' }> = []
    const leader = [...snapshots.value].filter((s) => s.change1h !== null).sort((a, b) => Number(b.change1h || 0) - Number(a.change1h || 0))[0]

    if (leader && (leader.change1h || 0) > 1.25) {
        ideas.push({
            title: `${leader.symbol} leadership continuation`,
            detail: `${formatPct(leader.change1h)} in 1h with breadth at ${marketBreadth.value.breadth}%.`,
            tone: 'bullish',
        })
    }

    if (avgRSI.value !== null && avgRSI.value >= 70) {
        ideas.push({
            title: 'Overbought market conditions',
            detail: `Average RSI at ${avgRSI.value} — consider defensive positioning.`,
            tone: 'defensive',
        })
    }

    if (marketBreadth.value.breadth <= 40) {
        ideas.push({
            title: 'Defensive allocation posture',
            detail: `Breadth ${marketBreadth.value.breadth}% — ${marketBreadth.value.declining} assets declining. Tighten filters.`,
            tone: 'defensive',
        })
    }

    if (!ideas.length) {
        ideas.push({
            title: 'Neutral discovery regime',
            detail: 'Balanced signals. Focus on high-conviction dislocations.',
            tone: 'neutral',
        })
    }

    return ideas.slice(0, 3)
})

/* ── Alpha-specific fetch (routing + security — not in shared stores) ── */

let _alphaTimer: ReturnType<typeof setInterval> | null = null

const fetchAlphaExtras = async () => {
    try {
        const [routing, securityPayload] = await Promise.all([
            fetchRoutingInfo(),
            fetchSecuritySkillsStatus(),
        ])
        if (securityPayload?.ok) security.value = securityPayload
        const confRaw = Number(routing?.confidence ?? 0)
        routingConfidence.value = Number.isFinite(confRaw) ? Math.max(0, Math.min(100, Math.round(confRaw * 100))) : null
        routingMode.value = String(routing?.mode || 'guarded')
    } catch (err) {
        console.error('Alpha extras fetch error:', err)
    }
}

const reload = () => {
    ctrl.refresh()
    mkt.fetchAll(selectedSymbol.value)
    fetchAlphaExtras()
}

watch(selectedSymbol, () => mkt.fetchAll(selectedSymbol.value))

onMounted(() => {
    ctrl.subscribe()
    mkt.startPolling(() => selectedSymbol.value)
    fetchAlphaExtras()
    _alphaTimer = setInterval(fetchAlphaExtras, 15_000)
})

onUnmounted(() => {
    ctrl.unsubscribe()
    mkt.stopPolling()
    if (_alphaTimer) { clearInterval(_alphaTimer); _alphaTimer = null }
})
</script>

<template>
    <div class="alpha-view fade-in">
        <div v-if="loading && !lastFetchAt" class="status-bar loading-bar">
            <span class="pulse-dot"></span> Initializing Alpha Engine...
        </div>
        <div v-else-if="fetchError" class="status-bar error-bar" @click="reload">
            {{ fetchError }} — tap to retry
        </div>
        <div v-else-if="isStale" class="status-bar stale-bar">
            Data {{ dataAge }}s old — awaiting refresh
        </div>

        <div class="topstrip">
            <label class="symbol-picker">
                <span class="font-mono">FOCUS</span>
                <select v-model="selectedSymbol">
                    <option v-for="s in SYMBOLS" :key="s" :value="s">{{ s }}</option>
                </select>
            </label>
        </div>

        <!-- Skeleton loading state -->
        <template v-if="loading && !lastFetchAt">
            <section class="insights-grid">
                <article v-for="i in 6" :key="i" class="insight card glass-lift">
                    <div class="skel-line skel-sm"></div>
                    <div class="skel-line skel-lg"></div>
                    <div class="skel-line skel-xs"></div>
                </article>
            </section>
            <section class="rail card glass-lift">
                <div class="skel-line skel-sm" style="width: 25%; margin: 0 0 0.7rem"></div>
                <div class="rail-grid">
                    <article v-for="i in 4" :key="i" class="rail-stage">
                        <div class="skel-line skel-sm"></div>
                        <div class="skel-line skel-lg"></div>
                        <div class="skel-line skel-xs"></div>
                    </article>
                </div>
            </section>
            <section class="chart-row">
                <article v-for="i in 2" :key="i" class="chart-panel card glass-lift">
                    <div class="skel-line skel-sm" style="margin-bottom: 0.7rem"></div>
                    <div class="skel-chart"></div>
                </article>
            </section>
        </template>

        <template v-else>
        <section class="insights-grid">
            <article v-for="card in insightCards" :key="card.title" class="insight card glass-lift">
                <p class="font-mono">{{ card.title }}</p>
                <strong class="glow" :class="card.title === 'Avg RSI (14)' ? rsiTone : ''">{{ card.value }}</strong>
                <small>{{ card.detail }}</small>
            </article>
        </section>

        <section class="rail card glass-lift">
            <header>
                <h3 class="font-mono">Strategy Readiness</h3>
                <span class="rail-score" :class="readinessTone">{{ readinessScore }}%</span>
            </header>
            <div class="rail-grid">
                <article v-for="stage in strategyRail" :key="stage.label" class="rail-stage" :class="`stage-${stage.status}`">
                    <p class="font-mono">{{ stage.label }}</p>
                    <strong>{{ stage.status === 'ready' ? 'READY' : 'PENDING' }}</strong>
                    <small>{{ stage.detail }}</small>
                </article>
            </div>
        </section>

        <section class="chart-row">
            <article class="chart-panel card glass-lift">
                <header>
                    <h3 class="font-mono">ASTER Canvas</h3>
                    <small>{{ chartSourceLabel }}</small>
                </header>
                <TradingChart :candles="alphaCandles" :height="400" />
            </article>
            <article class="chart-panel card glass-lift">
                <header>
                    <h3 class="font-mono">LIGHTER Canvas</h3>
                    <small>{{ compareSourceLabel }}</small>
                </header>
                <TradingChart :candles="lighterCandles" :height="400" />
            </article>
        </section>

        <section class="matrix card glass-lift">
            <h3 class="font-mono">Market Intelligence Matrix</h3>
            <div class="matrix-grid">
                <article v-for="snap in snapshots" :key="snap.symbol" class="matrix-item">
                    <header>
                        <strong>{{ snap.symbol }}</strong>
                        <span :class="(snap.change1h || 0) >= 0 ? 'tone-strong' : 'tone-guarded'">{{ formatPct(snap.change1h) }}</span>
                    </header>
                    <p class="matrix-price">{{ formatPrice(snap.price) }}</p>
                    <div class="matrix-indicators">
                        <span class="indicator">
                            <em>RSI</em>
                            <b :class="snap.rsi !== null ? (snap.rsi >= 70 ? 'rsi-hot' : snap.rsi <= 30 ? 'rsi-cold' : 'rsi-neutral') : ''">
                                {{ snap.rsi !== null ? snap.rsi.toFixed(0) : '—' }}
                            </b>
                        </span>
                        <span class="indicator">
                            <em>MOM</em>
                            <b :class="snap.momentum !== null ? ((snap.momentum || 0) >= 0 ? 'mom-up' : 'mom-down') : ''">
                                {{ snap.momentum !== null ? formatPct(snap.momentum, 1) : '—' }}
                            </b>
                        </span>
                        <span class="indicator">
                            <em>VOL</em>
                            <b>{{ formatPct(snap.volatility, 2) }}</b>
                        </span>
                    </div>
                    <small>6h {{ formatPct(snap.change6h) }} · conf {{ snap.confidence }}%</small>
                    <svg class="sparkline" viewBox="0 0 100 34" preserveAspectRatio="none">
                        <polyline :points="sparklinePoints(snap.history)" />
                    </svg>
                </article>
            </div>
        </section>

        <section class="ideas card glass-lift">
            <header>
                <h3 class="font-mono">Alpha Ideas</h3>
                <small>Auto-generated from breadth + RSI + volatility + routing</small>
            </header>
            <article v-for="idea in alphaIdeas" :key="idea.title" class="idea-item" :class="`idea-${idea.tone}`">
                <h4>{{ idea.title }}</h4>
                <p>{{ idea.detail }}</p>
            </article>
        </section>
        </template>
    </div>
</template>

<style scoped>
.alpha-view {
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

/* ── Insight Cards ── */
.insights-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.8rem;
}

.insight {
    display: grid;
    gap: 0.3rem;
}

.insight p {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.72rem;
    letter-spacing: 0.06em;
}

.insight strong {
    font-size: 1.25rem;
    color: var(--text-primary);
}

.insight small {
    color: var(--text-tertiary);
    font-size: 0.72rem;
}

.tone-hot { color: var(--color-error); text-shadow: 0 0 4px rgba(255, 68, 68, 0.3); }
.tone-cold { color: #4488ff; text-shadow: 0 0 4px rgba(68, 136, 255, 0.3); }
.tone-neutral { color: var(--text-primary); }

/* ── Readiness Rail ── */
.rail header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 0.7rem;
}

.rail h3 {
    margin: 0;
    font-size: 0.85rem;
}

.rail-score {
    border-radius: 999px;
    padding: 0.2rem 0.6rem;
    font-size: 0.78rem;
    border: 1px solid var(--border-accent);
    font-family: var(--font-mono);
}

.tone-strong { color: var(--color-terminal); border-color: rgba(32, 194, 14, 0.4); }
.tone-balanced { color: var(--color-warning); border-color: rgba(255, 176, 0, 0.4); }
.tone-guarded { color: var(--color-error); border-color: rgba(255, 68, 68, 0.4); }

.rail-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.6rem;
}

.rail-stage {
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: rgba(10, 20, 10, 0.4);
    padding: 0.6rem;
    display: grid;
    gap: 0.2rem;
}

.rail-stage p {
    margin: 0;
    font-size: 0.68rem;
    letter-spacing: 0.06em;
    color: var(--text-secondary);
}

.rail-stage strong { font-size: 0.82rem; }
.rail-stage small { color: var(--text-tertiary); font-size: 0.72rem; }

.stage-ready strong { color: var(--color-terminal); }
.stage-pending strong { color: var(--color-error); }

/* ── Charts ── */
.chart-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.8rem;
}

.chart-panel header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.7rem;
}

.chart-panel h3 { margin: 0; font-size: 0.85rem; }
.chart-panel small { color: var(--text-tertiary); font-size: 0.72rem; }

/* ── Matrix ── */
.matrix h3 {
    margin: 0 0 0.7rem;
    font-size: 0.85rem;
}

.matrix-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(170px, 1fr));
    gap: 0.7rem;
}

.matrix-item {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 0.6rem 0.7rem;
    background: rgba(10, 20, 10, 0.35);
    display: grid;
    gap: 0.2rem;
}

.matrix-item header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.matrix-item header strong { font-size: 0.85rem; }
.matrix-item header span { font-size: 0.82rem; }

.matrix-price {
    margin: 0;
    color: var(--text-primary);
    font-size: 0.92rem;
    font-weight: 500;
}

.matrix-indicators {
    display: flex;
    gap: 0.6rem;
    margin-top: 0.15rem;
}

.indicator {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.68rem;
}

.indicator em {
    font-style: normal;
    color: var(--text-tertiary);
    font-size: 0.6rem;
    letter-spacing: 0.04em;
}

.indicator b {
    font-weight: 600;
    color: var(--text-secondary);
}

.rsi-hot { color: var(--color-error) !important; }
.rsi-cold { color: #4488ff !important; }
.rsi-neutral { color: var(--text-secondary); }
.mom-up { color: var(--color-terminal) !important; }
.mom-down { color: var(--color-error) !important; }

.matrix-item small {
    color: var(--text-tertiary);
    font-size: 0.68rem;
}

.sparkline {
    width: 100%;
    height: 38px;
    border-radius: var(--radius-xs);
    background: rgba(10, 20, 10, 0.4);
}

.sparkline polyline {
    fill: none;
    stroke: var(--color-terminal);
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
    filter: drop-shadow(0 0 3px rgba(32, 194, 14, 0.4));
}

/* ── Ideas ── */
.ideas header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.6rem;
}

.ideas h3 { margin: 0; font-size: 0.85rem; }
.ideas small { color: var(--text-tertiary); font-size: 0.72rem; }

.idea-item {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: rgba(10, 20, 10, 0.3);
    padding: 0.7rem;
    margin-top: 0.5rem;
}

.idea-item h4 {
    margin: 0;
    font-size: 0.85rem;
    color: var(--text-primary);
}

.idea-item p {
    margin: 0.25rem 0 0;
    font-size: 0.78rem;
    color: var(--text-secondary);
    line-height: 1.5;
}

.idea-bullish { border-color: rgba(32, 194, 14, 0.35); }
.idea-neutral { border-color: var(--border-accent); }
.idea-defensive { border-color: rgba(255, 176, 0, 0.35); }

/* ── Responsive ── */
@media (max-width: 1320px) {
    .insights-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .chart-row { grid-template-columns: 1fr; }
    .matrix-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
    .insights-grid,
    .rail-grid,
    .matrix-grid { grid-template-columns: 1fr; }
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
</style>

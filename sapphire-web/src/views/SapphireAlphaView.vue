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
    <div class="grid gap-4 fade-in" aria-label="Alpha engine dashboard">
        <!-- Status Bar -->
        <StatusBar
            :loading="loading"
            :has-data="!!lastFetchAt"
            :fetch-error="fetchError"
            :is-stale="isStale"
            :data-age="dataAge"
            loading-message="Initializing Alpha Engine..."
            @retry="reload"
        />

        <!-- Symbol Picker -->
        <div class="flex items-center justify-end">
            <SymbolPicker v-model="selectedSymbol" :symbols="SYMBOLS" label="FOCUS" />
        </div>

        <!-- Skeleton loading state -->
        <template v-if="loading && !lastFetchAt">
            <KpiStrip :columns="3" class="max-lg:grid-cols-2 max-md:grid-cols-1">
                <article v-for="i in 6" :key="i" class="grid gap-1 rounded-md border border-border-subtle bg-card p-4 glass-lift">
                    <div class="mx-auto h-2.5 w-2/5 animate-pulse rounded-xs bg-terminal-ghost/50" />
                    <div class="mx-auto h-5 w-3/5 animate-pulse rounded-xs bg-terminal-ghost/80" />
                    <div class="mx-auto mt-0.5 h-2 w-1/2 animate-pulse rounded-xs bg-terminal-ghost/40" />
                </article>
            </KpiStrip>
            <section class="rounded-md border border-border-subtle bg-card p-4 glass-lift">
                <div class="mb-3 h-2.5 w-1/4 animate-pulse rounded-xs bg-terminal-ghost/50" />
                <div class="grid grid-cols-4 gap-2.5 max-md:grid-cols-1">
                    <article v-for="i in 4" :key="i" class="grid gap-1 rounded border border-border-subtle bg-terminal-ghost/20 p-2.5">
                        <div class="mx-auto h-2.5 w-2/5 animate-pulse rounded-xs bg-terminal-ghost/50" />
                        <div class="mx-auto h-5 w-3/5 animate-pulse rounded-xs bg-terminal-ghost/80" />
                        <div class="mx-auto mt-0.5 h-2 w-1/2 animate-pulse rounded-xs bg-terminal-ghost/40" />
                    </article>
                </div>
            </section>
            <section class="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
                <article v-for="i in 2" :key="i" class="rounded-md border border-border-subtle bg-card p-4 glass-lift">
                    <div class="mb-3 h-2.5 w-2/5 animate-pulse rounded-xs bg-terminal-ghost/50" />
                    <div class="h-[400px] w-full animate-pulse rounded bg-terminal-ghost/30" />
                </article>
            </section>
        </template>

        <template v-else>
        <!-- Insight Cards -->
        <KpiStrip :columns="3" class="max-lg:grid-cols-2 max-md:grid-cols-1" aria-label="Alpha engine insights" aria-live="polite">
            <div v-for="card in insightCards" :key="card.title" class="grid gap-0.5" :aria-label="`${card.title}: ${card.value}`">
                <KpiCard
                    :label="card.title"
                    :value="card.value"
                    :tone="card.title === 'Avg RSI (14)' ? (rsiTone === 'tone-hot' ? 'error' : rsiTone === 'tone-cold' ? 'cold' : 'default') : 'default'"
                    glow
                />
                <small class="text-center font-mono text-[0.72rem] text-text-tertiary">{{ card.detail }}</small>
            </div>
        </KpiStrip>

        <!-- Strategy Readiness Rail -->
        <section class="rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm glass-lift" aria-label="Strategy readiness pipeline">
            <SectionHeader title="Strategy Readiness">
                <template #actions>
                    <SyncBadge
                        :text="`${readinessScore}%`"
                        :variant="readinessTone === 'tone-strong' ? 'success' : readinessTone === 'tone-balanced' ? 'warning' : 'error'"
                        :aria-label="`Readiness score: ${readinessScore} percent`"
                    />
                </template>
            </SectionHeader>
            <div class="mt-3 grid grid-cols-4 gap-2.5 max-md:grid-cols-1" role="list">
                <article
                    v-for="stage in strategyRail"
                    :key="stage.label"
                    class="grid gap-0.5 rounded border border-border-subtle bg-terminal-ghost/40 p-2.5"
                    role="listitem"
                    :aria-label="`${stage.label}: ${stage.status === 'ready' ? 'ready' : 'pending'} — ${stage.detail}`"
                >
                    <p class="m-0 font-mono text-[0.68rem] uppercase tracking-wider text-text-secondary">{{ stage.label }}</p>
                    <strong
                        class="text-sm"
                        :class="stage.status === 'ready' ? 'text-terminal' : 'text-error'"
                    >
                        {{ stage.status === 'ready' ? 'READY' : 'PENDING' }}
                    </strong>
                    <small class="text-[0.72rem] text-text-tertiary">{{ stage.detail }}</small>
                </article>
            </div>
        </section>

        <!-- Charts -->
        <section class="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
            <ChartPanel
                title="ASTER Canvas"
                :subtitle="chartSourceLabel"
                :candles="alphaCandles"
                :height="400"
            />
            <ChartPanel
                title="LIGHTER Canvas"
                :subtitle="compareSourceLabel"
                :candles="lighterCandles"
                :height="400"
            />
        </section>

        <!-- Market Intelligence Matrix -->
        <section class="rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm glass-lift">
            <h3 class="m-0 mb-3 font-mono text-sm tracking-wide text-text-primary glow">Market Intelligence Matrix</h3>
            <div class="grid grid-cols-3 gap-3 max-lg:grid-cols-2 max-md:grid-cols-1" style="grid-template-columns: repeat(3, minmax(170px, 1fr))">
                <article
                    v-for="snap in snapshots"
                    :key="snap.symbol"
                    class="grid gap-0.5 rounded border border-border-subtle bg-terminal-ghost/35 px-3 py-2.5"
                >
                    <header class="flex items-center justify-between">
                        <strong class="text-sm">{{ snap.symbol }}</strong>
                        <span
                            class="text-sm"
                            :class="(snap.change1h || 0) >= 0 ? 'text-terminal' : 'text-error'"
                        >
                            {{ formatPct(snap.change1h) }}
                        </span>
                    </header>
                    <p class="m-0 text-[0.92rem] font-medium text-text-primary">{{ formatPrice(snap.price) }}</p>
                    <div class="mt-0.5 flex gap-2.5">
                        <span class="flex items-center gap-1 text-[0.68rem]">
                            <em class="not-italic text-[0.6rem] tracking-wide text-text-tertiary">RSI</em>
                            <b
                                class="font-semibold"
                                :class="snap.rsi !== null ? (snap.rsi >= 70 ? 'text-error' : snap.rsi <= 30 ? 'text-info' : 'text-text-secondary') : 'text-text-secondary'"
                            >
                                {{ snap.rsi !== null ? snap.rsi.toFixed(0) : '—' }}
                            </b>
                        </span>
                        <span class="flex items-center gap-1 text-[0.68rem]">
                            <em class="not-italic text-[0.6rem] tracking-wide text-text-tertiary">MOM</em>
                            <b
                                class="font-semibold"
                                :class="snap.momentum !== null ? ((snap.momentum || 0) >= 0 ? 'text-terminal' : 'text-error') : 'text-text-secondary'"
                            >
                                {{ snap.momentum !== null ? formatPct(snap.momentum, 1) : '—' }}
                            </b>
                        </span>
                        <span class="flex items-center gap-1 text-[0.68rem]">
                            <em class="not-italic text-[0.6rem] tracking-wide text-text-tertiary">VOL</em>
                            <b class="font-semibold text-text-secondary">{{ formatPct(snap.volatility, 2) }}</b>
                        </span>
                    </div>
                    <small class="text-[0.68rem] text-text-tertiary">6h {{ formatPct(snap.change6h) }} · conf {{ snap.confidence }}%</small>
                    <svg class="sparkline" viewBox="0 0 100 34" preserveAspectRatio="none" role="img" :aria-label="`${snap.symbol} price trend`">
                        <polyline :points="sparklinePoints(snap.history)" />
                    </svg>
                </article>
            </div>
        </section>

        <!-- Alpha Ideas -->
        <section class="rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm glass-lift">
            <SectionHeader title="Alpha Ideas">
                <template #actions>
                    <small class="font-mono text-[0.72rem] text-text-tertiary">Auto-generated from breadth + RSI + volatility + routing</small>
                </template>
            </SectionHeader>
            <article
                v-for="idea in alphaIdeas"
                :key="idea.title"
                class="mt-2 rounded border bg-terminal-ghost/30 p-3"
                :class="{
                    'border-terminal/35': idea.tone === 'bullish',
                    'border-warning/35': idea.tone === 'defensive',
                    'border-border-accent': idea.tone === 'neutral',
                }"
            >
                <h4 class="m-0 text-sm text-text-primary">{{ idea.title }}</h4>
                <p class="mt-1 text-[0.78rem] leading-relaxed text-text-secondary">{{ idea.detail }}</p>
            </article>
        </section>
        </template>
    </div>
</template>

<script lang="ts">
import { StatusBar, KpiCard, KpiStrip, SectionHeader, SyncBadge, SymbolPicker, ChartPanel } from '../components/shared/index'

export default {
    components: { StatusBar, KpiCard, KpiStrip, SectionHeader, SyncBadge, SymbolPicker, ChartPanel },
}
</script>

<style scoped>
/* ── Sparkline SVG — minimal scoped styles for SVG rendering ── */
.sparkline {
    width: 100%;
    height: 38px;
    border-radius: 2px;
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
</style>

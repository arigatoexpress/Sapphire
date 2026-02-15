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
    <div class="grid gap-4 fade-in" aria-label="Trade dashboard">
        <!-- ── Status Bar ── -->
        <StatusBar
            :loading="loading"
            :has-data="!!lastFetchAt"
            :fetch-error="fetchError"
            :is-stale="isStale"
            :data-age="dataAge"
            loading-message="Connecting to Sapphire..."
            @retry="reload"
        />

        <!-- ── Symbol Picker ── -->
        <div class="flex justify-end items-center">
            <SymbolPicker v-model="selectedSymbol" :symbols="SYMBOLS" />
        </div>

        <!-- ── Skeleton loading state ── -->
        <template v-if="loading && !lastFetchAt">
            <KpiStrip :columns="5" class="max-md:!grid-cols-3">
                <KpiCard v-for="i in 5" :key="i" label="—" value="—" :loading="true" />
            </KpiStrip>
            <KpiStrip :columns="4" class="max-lg:!grid-cols-2 max-md:!grid-cols-1">
                <KpiCard v-for="i in 4" :key="i" label="—" value="—" :loading="true" />
            </KpiStrip>
            <section class="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
                <article v-for="i in 2" :key="i" class="grid gap-3 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm glass-lift">
                    <div class="mx-auto h-3 w-2/5 animate-pulse rounded-xs bg-terminal-ghost/50" />
                    <div class="h-[400px] w-full animate-pulse rounded-sm bg-terminal-ghost/30" />
                </article>
            </section>
        </template>

        <template v-else>
            <!-- ── Operations Strip (5 KPIs) ── -->
            <KpiStrip :columns="5" aria-label="Trading operations summary" aria-live="polite" class="max-md:!grid-cols-3">
                <KpiCard
                    label="Trades"
                    :value="ctrl.totalTrades"
                    :glow="true"
                    aria-label="Total trades"
                />
                <KpiCard
                    label="Win Rate"
                    :value="`${ctrl.winRate.toFixed(1)}%`"
                    :glow="true"
                    aria-label="Win rate"
                />
                <KpiCard
                    label="PnL"
                    :value="`${ctrl.realizedPnl >= 0 ? '+' : ''}${ctrl.realizedPnl.toFixed(4)}`"
                    :tone="ctrl.realizedPnl >= 0 ? 'success' : 'error'"
                    :glow="true"
                    :aria-label="`Profit and loss: ${ctrl.realizedPnl >= 0 ? 'positive' : 'negative'} ${Math.abs(ctrl.realizedPnl).toFixed(4)}`"
                />
                <!-- Stage card (has subtitle) -->
                <article
                    class="grid gap-0.5 rounded-md border border-border-subtle bg-card px-2 py-2.5 text-center backdrop-blur-sm glass-lift"
                    :aria-label="`Execution stage: ${ctrl.executionStage}, multiplier ${ctrl.stageMultiplier.toFixed(2)}x`"
                >
                    <span class="font-mono text-[0.62rem] uppercase tracking-wider text-text-tertiary">Stage</span>
                    <strong class="font-mono text-lg leading-tight glow" :class="ctrl.executionStage === 'LIVE' ? 'text-terminal' : 'text-warning'">
                        {{ ctrl.executionStage }}
                    </strong>
                    <small class="font-mono text-[0.62rem] text-text-tertiary">{{ ctrl.stageMultiplier.toFixed(2) }}x</small>
                </article>
                <!-- Dispatch card -->
                <KpiCard
                    label="Dispatch"
                    :value="ctrl.killSwitchActive ? 'KILL' : ctrl.dexLiveDispatch ? 'LIVE' : 'OFF'"
                    :tone="ctrl.killSwitchActive ? 'error' : ctrl.dexLiveDispatch ? 'success' : 'warning'"
                    :aria-label="`Dispatch: ${ctrl.killSwitchActive ? 'kill switch active' : ctrl.dexLiveDispatch ? 'live' : 'off'}`"
                />
            </KpiStrip>

            <!-- ── Metric Strip (4 KPIs) ── -->
            <KpiStrip :columns="4" class="max-lg:!grid-cols-2 max-md:!grid-cols-1">
                <!-- Aster price (has subtitle) -->
                <article class="grid gap-0.5 rounded-md border border-border-subtle bg-card px-2 py-2.5 text-center backdrop-blur-sm glass-lift">
                    <span class="font-mono text-[0.62rem] uppercase tracking-wider text-text-tertiary">{{ selectedSymbol }} ASTER</span>
                    <strong class="font-mono text-lg leading-tight text-text-primary glow">{{ formatPrice(effectiveAster) }}</strong>
                    <small class="font-mono text-[0.62rem] text-text-tertiary">{{ mkt.asterMeta.source }} &middot; {{ mkt.asterMeta.interval }}</small>
                </article>
                <!-- Lighter price (has subtitle) -->
                <article class="grid gap-0.5 rounded-md border border-border-subtle bg-card px-2 py-2.5 text-center backdrop-blur-sm glass-lift">
                    <span class="font-mono text-[0.62rem] uppercase tracking-wider text-text-tertiary">{{ selectedSymbol }} LIGHTER</span>
                    <strong class="font-mono text-lg leading-tight text-text-primary glow">{{ formatPrice(effectiveLighter) }}</strong>
                    <small class="font-mono text-[0.62rem] text-text-tertiary">{{ mkt.lighterMeta.source }} &middot; {{ mkt.lighterMeta.interval }}</small>
                </article>
                <!-- Spread (has subtitle) -->
                <article class="grid gap-0.5 rounded-md border border-border-subtle bg-card px-2 py-2.5 text-center backdrop-blur-sm glass-lift">
                    <span class="font-mono text-[0.62rem] uppercase tracking-wider text-text-tertiary">Cross-Venue Spread</span>
                    <strong
                        class="font-mono text-lg leading-tight glow"
                        :class="spreadTone === 'tone-hot' ? 'text-error' : spreadTone === 'tone-warm' ? 'text-warning' : 'text-terminal'"
                    >
                        {{ spreadPct === null ? 'n/a' : `${spreadPct.toFixed(3)}%` }}
                    </strong>
                    <small class="font-mono text-[0.62rem] text-text-tertiary">dislocation monitor</small>
                </article>
                <!-- Breadth (has subtitle) -->
                <article class="grid gap-0.5 rounded-md border border-border-subtle bg-card px-2 py-2.5 text-center backdrop-blur-sm glass-lift">
                    <span class="font-mono text-[0.62rem] uppercase tracking-wider text-text-tertiary">Market Breadth</span>
                    <strong class="font-mono text-lg leading-tight text-text-primary glow">{{ marketBreadth.breadth }}%</strong>
                    <small class="font-mono text-[0.62rem] text-text-tertiary">{{ breadthPosture }} &middot; {{ marketBreadth.advancing }} adv / {{ marketBreadth.declining }} dec</small>
                </article>
            </KpiStrip>

            <!-- ── Chart Grid ── -->
            <section class="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
                <ChartPanel
                    :title="`ASTER (${mkt.asterMeta.trackingSymbol})`"
                    :subtitle="`${mkt.asterMeta.source} \u00b7 ${mkt.asterMeta.interval}`"
                    :candles="asterCandles"
                    :height="400"
                />
                <ChartPanel
                    :title="`LIGHTER (${mkt.lighterMeta.trackingSymbol})`"
                    :subtitle="`${mkt.lighterMeta.source} \u00b7 ${mkt.lighterMeta.interval}`"
                    :candles="lighterCandles"
                    :height="400"
                />
            </section>

            <!-- ── Market Breadth Scanner ── -->
            <section class="grid gap-3">
                <SectionHeader title="Market Breadth Scanner" />
                <div class="grid grid-cols-[repeat(3,minmax(160px,1fr))] gap-3 max-lg:grid-cols-2 max-md:grid-cols-1">
                    <article
                        v-for="snap in mkt.snapshots"
                        :key="snap.symbol"
                        class="grid gap-1 rounded-md border border-border-subtle bg-card p-3 backdrop-blur-sm glass-lift"
                    >
                        <header class="flex justify-between items-center">
                            <span class="text-sm font-semibold tracking-wide">{{ snap.symbol }}</span>
                            <span
                                class="text-sm font-medium"
                                :class="(snap.change1h || 0) >= 0 ? 'text-terminal' : 'text-error'"
                            >
                                {{ formatPct(snap.change1h) }}
                            </span>
                        </header>
                        <strong class="text-base text-text-primary">{{ formatPrice(snap.price) }}</strong>
                        <small class="font-mono text-[0.72rem] text-text-tertiary">
                            4h {{ formatPct(snap.change4h) }} &middot; vol {{ formatPct(snap.volatility) }}
                        </small>
                        <svg
                            class="sparkline"
                            viewBox="0 0 100 38"
                            preserveAspectRatio="none"
                            role="img"
                            :aria-label="`${snap.symbol} price sparkline`"
                        >
                            <polyline :points="sparklinePoints(snap.history)" />
                        </svg>
                    </article>
                </div>
            </section>
        </template>
    </div>
</template>

<script lang="ts">
import { StatusBar, KpiCard, KpiStrip, SectionHeader, SymbolPicker, ChartPanel } from '../components/shared/index'

export default {
    components: { StatusBar, KpiCard, KpiStrip, SectionHeader, SymbolPicker, ChartPanel },
}
</script>

<style scoped>
/* Sparkline SVG — cannot be expressed with Tailwind utilities */
.sparkline {
    width: 100%;
    height: 44px;
    border-radius: 4px;
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
</style>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
    fetchPredictionDashboard,
    type PredictionDashboardResponse,
    type PredictionSignalDto,
    type ArbitrageOpportunityDto,
    type SymbolSentiment,
} from '../api/client'

const loading = ref(true)
const data = ref<PredictionDashboardResponse | null>(null)
const fetchError = ref('')
const lastSyncEpoch = ref(0)
const activeTab = ref<'signals' | 'arbitrage' | 'accuracy' | 'whales'>('signals')
type TabKey = 'signals' | 'arbitrage' | 'accuracy' | 'whales'
const TAB_ORDER: TabKey[] = ['signals', 'arbitrage', 'accuracy', 'whales']
const nextTab = (tab: TabKey): TabKey => TAB_ORDER[(TAB_ORDER.indexOf(tab) + 1) % 4]!
const prevTab = (tab: TabKey): TabKey => TAB_ORDER[(TAB_ORDER.indexOf(tab) + 3) % 4]!

let refreshTimer: ReturnType<typeof setInterval> | null = null

const dataAge = computed(() => {
    if (!lastSyncEpoch.value) return null
    return Math.floor((Date.now() - lastSyncEpoch.value) / 1000)
})

const isStale = computed(() => (dataAge.value ?? 999) > 30)

const totalSignals = computed(() => data.value?.status?.total_signals ?? 0)
const highConviction = computed(() => data.value?.status?.high_conviction_signals ?? 0)
const arbCount = computed(() => data.value?.status?.arbitrage_opportunities ?? 0)
const whaleCount = computed(() => data.value?.whale_alerts?.length ?? 0)

const feedStatuses = computed(() => {
    if (!data.value?.status?.feeds) return []
    return Object.entries(data.value.status.feeds).map(([key, info]) => ({
        ...info,
        source: key,
    }))
})

const sentiments = computed(() => {
    if (!data.value?.sentiments) return []
    return Object.values(data.value.sentiments)
        .filter((s: SymbolSentiment) => s.signal_count > 0)
        .sort((a: SymbolSentiment, b: SymbolSentiment) => b.signal_count - a.signal_count)
})

const accuracy = computed(() => data.value?.accuracy ?? null)

const sentimentColor = (sentiment: string): string => {
    if (sentiment.includes('bullish')) return 'text-bullish'
    if (sentiment.includes('bearish')) return 'text-bearish'
    return 'text-neutral'
}

const riskBadge = (risk: string): { text: string; class: string } => {
    switch (risk) {
        case 'wash_trading': return { text: 'WASH', class: 'risk-severe' }
        case 'insider_pattern': return { text: 'INSIDER', class: 'risk-high' }
        case 'low_liquidity_pump': return { text: 'LOW LIQ', class: 'risk-medium' }
        default: return { text: '', class: '' }
    }
}

const formatPct = (v: number) => `${(v * 100).toFixed(1)}%`
const formatUsd = (v: number) => {
    if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
    if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`
    return `$${v.toFixed(0)}`
}

const fetchData = async () => {
    try {
        const result = await fetchPredictionDashboard()
        if (result) {
            data.value = result
            lastSyncEpoch.value = Date.now()
            fetchError.value = ''
        }
    } catch (e) {
        fetchError.value = String(e)
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    fetchData()
    refreshTimer = setInterval(fetchData, 15000)
})

onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
    <div class="grid gap-4 text-text-primary font-mono text-[0.8rem] fade-in" aria-label="Prediction markets dashboard">
        <!-- Status Bar -->
        <StatusBar
            :loading="loading"
            :has-data="!!lastSyncEpoch"
            :fetch-error="fetchError || null"
            :is-stale="isStale"
            :data-age="dataAge"
            loading-message="Connecting to prediction feeds..."
            @retry="fetchData"
        />

        <!-- Skeleton loading state -->
        <template v-if="loading && !data">
            <KpiStrip :columns="5">
                <div v-for="i in 5" :key="i"
                    class="rounded-md border border-border-subtle bg-card px-2 py-2.5 text-center backdrop-blur-sm glass-lift relative overflow-hidden"
                >
                    <div class="skeleton-value mx-auto mb-1.5 h-6 w-2/5 rounded-xs bg-terminal/8" />
                    <div class="skeleton-label mx-auto h-2.5 w-3/5 rounded-xs bg-terminal/5" />
                </div>
            </KpiStrip>
            <div class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
                <div v-for="i in 6" :key="i"
                    class="rounded-md border border-border-subtle bg-card p-3 backdrop-blur-sm relative overflow-hidden"
                >
                    <div class="skeleton-header mb-2 h-3 w-[30%] rounded-xs bg-terminal/6" />
                    <div class="skeleton-question mb-1.5 h-3 w-[90%] rounded-xs bg-terminal/5" />
                    <div class="skeleton-stats h-2.5 w-1/2 rounded-xs bg-terminal/4" />
                </div>
            </div>
        </template>

        <!-- Real content -->
        <template v-else>
        <!-- Header Stats -->
        <KpiStrip :columns="5">
            <KpiCard label="Markets" :value="totalSignals" tone="success" glow :loading="loading" />
            <KpiCard label="High Conviction" :value="highConviction" tone="warning" :loading="loading" />
            <KpiCard label="Arbitrage" :value="arbCount" tone="cold" :loading="loading" />
            <KpiCard
                label="Whale Alerts"
                :value="whaleCount"
                :tone="whaleCount > 0 ? 'error' : 'default'"
                :loading="loading"
            />
            <KpiCard
                label="Status"
                :value="data?.status?.enabled ? 'LIVE' : 'OFF'"
                :tone="isStale ? 'error' : 'success'"
                :glow="!isStale"
                :loading="loading"
            />
        </KpiStrip>

        <!-- Feed Status -->
        <div class="flex gap-2 flex-wrap" v-if="feedStatuses.length">
            <div
                v-for="feed in feedStatuses"
                :key="feed.source"
                class="rounded-full px-2.5 py-0.5 font-mono text-[0.68rem] font-semibold uppercase tracking-wide"
                :class="
                    feed.running && feed.consecutive_errors === 0
                        ? 'bg-terminal/10 text-terminal border border-terminal/20'
                        : feed.running
                            ? 'bg-warning/10 text-warning border border-warning/20'
                            : 'bg-error/8 text-error border border-error/20'
                "
            >
                {{ feed.source }} &middot; {{ feed.market_count }}
            </div>
        </div>

        <!-- Symbol Sentiments -->
        <div class="flex gap-2 flex-wrap" v-if="sentiments.length">
            <div
                v-for="s in sentiments"
                :key="s.symbol"
                class="flex gap-2 items-center rounded-sm border border-border-subtle bg-card px-2.5 py-0.5 text-[0.7rem]"
            >
                <span class="font-bold">{{ s.symbol }}</span>
                <span :class="
                    s.sentiment.includes('bullish')
                        ? 'text-terminal [text-shadow:0_0_4px_rgba(32,194,14,0.3)]'
                        : s.sentiment.includes('bearish')
                            ? 'text-error [text-shadow:0_0_4px_rgba(255,68,68,0.3)]'
                            : 'text-text-secondary'
                ">{{ s.sentiment.replace('_', ' ') }}</span>
                <span class="text-text-tertiary">{{ formatPct(s.weighted_probability) }}</span>
            </div>
        </div>

        <!-- Tabs -->
        <div class="flex gap-1 border-b border-border-subtle pb-1" role="tablist" aria-label="Prediction data categories">
            <button
                v-for="tab in ['signals', 'arbitrage', 'accuracy', 'whales'] as const"
                :key="tab"
                class="px-3 py-1.5 bg-transparent border-none text-text-tertiary cursor-pointer font-mono text-[0.75rem] tracking-wide border-b-2 border-transparent transition-all duration-150 hover:text-text-secondary"
                :class="activeTab === tab ? '!text-terminal !border-b-terminal [text-shadow:0_0_6px_rgba(32,194,14,0.3)]' : ''"
                role="tab"
                :id="`tab-${tab}`"
                :aria-selected="activeTab === tab"
                :aria-controls="`panel-${tab}`"
                :tabindex="activeTab === tab ? 0 : -1"
                @click="activeTab = tab"
                @keydown.right.prevent="activeTab = nextTab(tab)"
                @keydown.left.prevent="activeTab = prevTab(tab)"
            >
                {{ tab === 'signals' ? `Signals (${data?.signals?.length ?? 0})` :
                   tab === 'arbitrage' ? `Arbitrage (${arbCount})` :
                   tab === 'accuracy' ? 'Accuracy' :
                   `Whales (${whaleCount})` }}
            </button>
        </div>

        <!-- Signals Tab -->
        <div v-if="activeTab === 'signals'" id="panel-signals" role="tabpanel" aria-labelledby="tab-signals" class="min-h-[200px]">
            <div v-if="loading" class="text-center text-text-tertiary py-12 italic">Loading prediction markets...</div>
            <div v-else-if="!data?.signals?.length" class="text-center text-text-tertiary py-12 italic">No signals tracked.</div>
            <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
                <div
                    v-for="sig in data.signals"
                    :key="sig.market_id"
                    class="bg-card border border-border-subtle rounded-md p-3 transition-[border-color,box-shadow] duration-150 backdrop-blur-sm hover:border-border-accent hover:shadow-[var(--glow-sm)]"
                    :class="{
                        'border-warning/30': sig.is_high_conviction,
                        'border-error/30': sig.manipulation_risk !== 'clean'
                    }"
                >
                    <div class="flex gap-1.5 items-center mb-1.5">
                        <span class="px-1.5 py-0.5 bg-terminal/10 text-terminal border border-terminal/20 rounded-xs text-[0.6rem] font-bold uppercase">{{ sig.source }}</span>
                        <span v-if="sig.is_whale_activity" class="px-1.5 py-0.5 bg-info/12 text-info rounded-xs text-[0.6rem] font-bold">WHALE</span>
                        <span v-if="sig.is_volume_spike" class="px-1.5 py-0.5 bg-terminal/10 text-terminal rounded-xs text-[0.6rem] font-bold">SPIKE</span>
                        <span
                            v-if="sig.manipulation_risk !== 'clean'"
                            class="px-1.5 py-0.5 rounded-xs text-[0.6rem] font-bold"
                            :class="
                                riskBadge(sig.manipulation_risk).class === 'risk-severe'
                                    ? 'bg-error/15 text-error'
                                    : riskBadge(sig.manipulation_risk).class === 'risk-high'
                                        ? 'bg-warning/15 text-warning'
                                        : 'bg-[rgba(255,140,0,0.12)] text-[#ff8c00]'
                            "
                        >{{ riskBadge(sig.manipulation_risk).text }}</span>
                    </div>
                    <div class="text-text-primary text-[0.75rem] leading-snug mb-1.5 line-clamp-2">{{ sig.question }}</div>
                    <div class="flex gap-3 items-center mb-1.5">
                        <div
                            class="font-bold text-[0.85rem]"
                            :class="
                                sig.sentiment.includes('bullish')
                                    ? 'text-terminal [text-shadow:0_0_4px_rgba(32,194,14,0.3)]'
                                    : sig.sentiment.includes('bearish')
                                        ? 'text-error [text-shadow:0_0_4px_rgba(255,68,68,0.3)]'
                                        : 'text-text-secondary'
                            "
                        >
                            {{ formatPct(sig.probability) }}
                        </div>
                        <div class="text-text-tertiary">{{ formatUsd(sig.volume_usd) }}</div>
                        <div v-if="sig.momentum !== null"
                            class="text-[0.7rem] font-semibold"
                            :class="sig.momentum > 0
                                ? 'text-terminal [text-shadow:0_0_4px_rgba(32,194,14,0.3)]'
                                : 'text-error [text-shadow:0_0_4px_rgba(255,68,68,0.3)]'"
                        >
                            {{ sig.momentum > 0 ? '+' : '' }}{{ (sig.momentum * 100).toFixed(1) }}%
                        </div>
                        <div v-if="sig.volume_change !== null" class="text-text-tertiary text-[0.65rem]">
                            {{ sig.volume_change.toFixed(1) }}x vol
                        </div>
                    </div>
                    <div class="flex gap-1">
                        <span v-for="sym in sig.symbols" :key="sym"
                            class="px-1.5 py-0.5 bg-warning/8 text-warning border border-warning/15 rounded-xs text-[0.6rem] font-semibold"
                        >{{ sym }}</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Arbitrage Tab -->
        <div v-if="activeTab === 'arbitrage'" id="panel-arbitrage" role="tabpanel" aria-labelledby="tab-arbitrage" class="min-h-[200px]">
            <div v-if="!data?.arbitrage?.length" class="text-center text-text-tertiary py-12 italic">No arbitrage opportunities detected.</div>
            <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
                <div
                    v-for="arb in data.arbitrage"
                    :key="arb.id"
                    class="bg-card border border-info/25 rounded-md p-3 backdrop-blur-sm"
                >
                    <div class="text-text-primary text-[0.75rem] mb-2 line-clamp-2">{{ arb.market_name }}</div>
                    <div class="flex items-center justify-between mb-1.5">
                        <div class="text-center">
                            <span class="block text-text-tertiary text-[0.6rem] uppercase">{{ arb.venue_a }}</span>
                            <span class="block text-[0.85rem] font-bold text-text-primary">{{ formatPct(arb.price_a) }}</span>
                        </div>
                        <div class="text-[1.1rem] font-extrabold text-info glow">{{ arb.spread_pct.toFixed(1) }}%</div>
                        <div class="text-center">
                            <span class="block text-text-tertiary text-[0.6rem] uppercase">{{ arb.venue_b }}</span>
                            <span class="block text-[0.85rem] font-bold text-text-primary">{{ formatPct(arb.price_b) }}</span>
                        </div>
                    </div>
                    <div class="flex justify-between text-text-tertiary text-[0.65rem]">
                        <span>Confidence: {{ arb.confidence.toFixed(0) }}</span>
                        <span>{{ arb.direction }}</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Accuracy Tab -->
        <div v-if="activeTab === 'accuracy'" id="panel-accuracy" role="tabpanel" aria-labelledby="tab-accuracy" class="min-h-[200px]">
            <div v-if="!accuracy || accuracy.total_tracked === 0" class="text-center text-text-tertiary py-12 italic">No predictions tracked yet.</div>
            <div v-else class="max-w-[600px]">
                <div class="flex gap-4 mb-4">
                    <div class="text-center flex-1">
                        <div class="text-[1.3rem] font-bold">{{ accuracy.total_tracked }}</div>
                        <div class="font-mono text-[0.6rem] text-text-tertiary uppercase mt-0.5">Tracked</div>
                    </div>
                    <div class="text-center flex-1">
                        <div class="text-[1.3rem] font-bold">{{ accuracy.total_resolved }}</div>
                        <div class="font-mono text-[0.6rem] text-text-tertiary uppercase mt-0.5">Resolved</div>
                    </div>
                    <div class="text-center flex-1">
                        <div class="text-[1.3rem] font-bold"
                            :class="accuracy.overall_accuracy_pct >= 60
                                ? 'glow'
                                : 'text-warning [text-shadow:0_0_4px_rgba(255,176,0,0.3)]'"
                        >
                            {{ accuracy.overall_accuracy_pct.toFixed(1) }}%
                        </div>
                        <div class="font-mono text-[0.6rem] text-text-tertiary uppercase mt-0.5">Accuracy</div>
                    </div>
                    <div class="text-center flex-1">
                        <div class="text-[1.3rem] font-bold"
                            :class="accuracy.overall_brier <= 0.25
                                ? 'glow'
                                : 'text-warning [text-shadow:0_0_4px_rgba(255,176,0,0.3)]'"
                        >
                            {{ accuracy.overall_brier.toFixed(3) }}
                        </div>
                        <div class="font-mono text-[0.6rem] text-text-tertiary uppercase mt-0.5">Brier Score</div>
                    </div>
                </div>
                <div v-if="accuracy.high_conviction_resolved > 0"
                    class="mt-4 p-3 bg-card border border-border-subtle rounded-sm"
                >
                    <div class="font-mono text-[0.7rem] font-bold text-text-secondary uppercase mb-1.5">High Conviction</div>
                    <div class="text-text-primary">
                        {{ accuracy.high_conviction_resolved }} resolved &middot;
                        {{ accuracy.high_conviction_accuracy_pct.toFixed(1) }}% accurate &middot;
                        Brier {{ accuracy.high_conviction_brier.toFixed(3) }}
                    </div>
                </div>
                <div v-if="Object.keys(accuracy.by_source).length"
                    class="mt-4 p-3 bg-card border border-border-subtle rounded-sm"
                >
                    <div class="font-mono text-[0.7rem] font-bold text-text-secondary uppercase mb-1.5">By Source</div>
                    <div v-for="(stats, source) in accuracy.by_source" :key="source"
                        class="flex justify-between py-1 border-b border-border-subtle"
                    >
                        <span class="font-semibold capitalize">{{ source }}</span>
                        <span>{{ stats.correct }}/{{ stats.total }} correct</span>
                        <span :class="stats.accuracy_pct >= 60
                            ? 'glow'
                            : 'text-warning [text-shadow:0_0_4px_rgba(255,176,0,0.3)]'"
                        >
                            {{ stats.accuracy_pct.toFixed(1) }}%
                        </span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Whales Tab -->
        <div v-if="activeTab === 'whales'" id="panel-whales" role="tabpanel" aria-labelledby="tab-whales" class="min-h-[200px]">
            <div v-if="!data?.whale_alerts?.length" class="text-center text-text-tertiary py-12 italic">No suspicious activity detected.</div>
            <div v-else class="flex flex-col gap-2">
                <div
                    v-for="(alert, idx) in data.whale_alerts"
                    :key="idx"
                    class="p-3 bg-error/5 border border-error/20 rounded-sm text-error text-[0.75rem] leading-relaxed"
                >
                    {{ alert }}
                </div>
            </div>
        </div>
        </template>
    </div>
</template>

<script lang="ts">
import { StatusBar, KpiCard, KpiStrip } from '../components/shared/index'

export default {
    components: { StatusBar, KpiCard, KpiStrip },
}
</script>

<style scoped>
/* Skeleton pulse animation */
.skeleton-value,
.skeleton-label,
.skeleton-header,
.skeleton-question,
.skeleton-stats {
    animation: skelPulse 1.6s ease-in-out infinite;
}
.skeleton-label   { animation-delay: 0.2s; }
.skeleton-question { animation-delay: 0.15s; }
.skeleton-stats   { animation-delay: 0.3s; }

@keyframes skelPulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 0.85; }
}

/* Responsive: 2-col KPI strip on small screens */
@media (max-width: 760px) {
    :deep(.grid[style*="repeat(5"]) {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }
}
</style>

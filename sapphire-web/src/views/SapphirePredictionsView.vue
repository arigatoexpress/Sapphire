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
    <div class="predictions-view fade-in" aria-label="Prediction markets dashboard">
        <!-- Status Bar -->
        <div v-if="loading && !lastSyncEpoch" class="status-bar loading-bar" role="status" aria-live="polite">
            <span class="pulse-dot" aria-hidden="true"></span> Connecting to prediction feeds...
        </div>
        <div v-else-if="fetchError" class="status-bar error-bar" role="alert" tabindex="0" @click="fetchData" @keydown.enter="fetchData" @keydown.space.prevent="fetchData">
            {{ fetchError }} — tap to retry
        </div>
        <div v-else-if="isStale" class="status-bar stale-bar" role="status" aria-live="polite">
            Data {{ dataAge }}s old — awaiting refresh
        </div>

        <!-- Skeleton loading state -->
        <template v-if="loading && !data">
            <div class="stats-bar">
                <div v-for="i in 5" :key="i" class="stat-card skeleton-card">
                    <div class="skeleton-value"></div>
                    <div class="skeleton-label"></div>
                </div>
            </div>
            <div class="signal-grid">
                <div v-for="i in 6" :key="i" class="signal-card skeleton-card">
                    <div class="skeleton-header"></div>
                    <div class="skeleton-question"></div>
                    <div class="skeleton-stats"></div>
                </div>
            </div>
        </template>

        <!-- Real content -->
        <template v-else>
        <!-- Header Stats -->
        <div class="stats-bar">
            <div class="stat-card glass-lift">
                <div class="stat-value glow">{{ totalSignals }}</div>
                <div class="stat-label font-mono">Markets</div>
            </div>
            <div class="stat-card glass-lift">
                <div class="stat-value text-warn">{{ highConviction }}</div>
                <div class="stat-label font-mono">High Conviction</div>
            </div>
            <div class="stat-card glass-lift">
                <div class="stat-value text-info">{{ arbCount }}</div>
                <div class="stat-label font-mono">Arbitrage</div>
            </div>
            <div class="stat-card glass-lift">
                <div class="stat-value" :class="whaleCount > 0 ? 'text-error' : ''">
                    {{ whaleCount }}
                </div>
                <div class="stat-label font-mono">Whale Alerts</div>
            </div>
            <div class="stat-card glass-lift">
                <div class="stat-value" :class="isStale ? 'text-error' : 'glow'">
                    {{ data?.status?.enabled ? 'LIVE' : 'OFF' }}
                </div>
                <div class="stat-label font-mono">Status</div>
            </div>
        </div>

        <!-- Feed Status -->
        <div class="feed-row" v-if="feedStatuses.length">
            <div
                v-for="feed in feedStatuses"
                :key="feed.source"
                class="feed-chip"
                :class="feed.running && feed.consecutive_errors === 0 ? 'feed-ok' : feed.running ? 'feed-warn' : 'feed-off'"
            >
                {{ feed.source }} &middot; {{ feed.market_count }}
            </div>
        </div>

        <!-- Symbol Sentiments -->
        <div class="sentiment-row" v-if="sentiments.length">
            <div
                v-for="s in sentiments"
                :key="s.symbol"
                class="sentiment-chip"
            >
                <span class="font-bold">{{ s.symbol }}</span>
                <span :class="sentimentColor(s.sentiment)">{{ s.sentiment.replace('_', ' ') }}</span>
                <span class="text-dim">{{ formatPct(s.weighted_probability) }}</span>
            </div>
        </div>

        <!-- Tabs -->
        <div class="tab-bar" role="tablist" aria-label="Prediction data categories">
            <button
                v-for="tab in ['signals', 'arbitrage', 'accuracy', 'whales'] as const"
                :key="tab"
                :class="['tab-btn', { active: activeTab === tab }]"
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
        <div v-if="activeTab === 'signals'" id="panel-signals" role="tabpanel" aria-labelledby="tab-signals" class="tab-content">
            <div v-if="loading" class="empty-state">Loading prediction markets...</div>
            <div v-else-if="!data?.signals?.length" class="empty-state">No signals tracked.</div>
            <div v-else class="signal-grid">
                <div
                    v-for="sig in data.signals"
                    :key="sig.market_id"
                    class="signal-card"
                    :class="{ 'signal-hc': sig.is_high_conviction, 'signal-risk': sig.manipulation_risk !== 'clean' }"
                >
                    <div class="signal-header">
                        <span class="source-badge">{{ sig.source }}</span>
                        <span v-if="sig.is_whale_activity" class="whale-badge">WHALE</span>
                        <span v-if="sig.is_volume_spike" class="spike-badge">SPIKE</span>
                        <span
                            v-if="sig.manipulation_risk !== 'clean'"
                            class="risk-badge"
                            :class="riskBadge(sig.manipulation_risk).class"
                        >{{ riskBadge(sig.manipulation_risk).text }}</span>
                    </div>
                    <div class="signal-question">{{ sig.question }}</div>
                    <div class="signal-stats">
                        <div class="prob" :class="sentimentColor(sig.sentiment)">
                            {{ formatPct(sig.probability) }}
                        </div>
                        <div class="vol">{{ formatUsd(sig.volume_usd) }}</div>
                        <div v-if="sig.momentum !== null" class="momentum" :class="sig.momentum > 0 ? 'text-bullish' : 'text-bearish'">
                            {{ sig.momentum > 0 ? '+' : '' }}{{ (sig.momentum * 100).toFixed(1) }}%
                        </div>
                        <div v-if="sig.volume_change !== null" class="vol-change">
                            {{ sig.volume_change.toFixed(1) }}x vol
                        </div>
                    </div>
                    <div class="signal-symbols">
                        <span v-for="sym in sig.symbols" :key="sym" class="symbol-tag">{{ sym }}</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Arbitrage Tab -->
        <div v-if="activeTab === 'arbitrage'" id="panel-arbitrage" role="tabpanel" aria-labelledby="tab-arbitrage" class="tab-content">
            <div v-if="!data?.arbitrage?.length" class="empty-state">No arbitrage opportunities detected.</div>
            <div v-else class="arb-grid">
                <div
                    v-for="arb in data.arbitrage"
                    :key="arb.id"
                    class="arb-card"
                >
                    <div class="arb-name">{{ arb.market_name }}</div>
                    <div class="arb-venues">
                        <div class="venue">
                            <span class="venue-name">{{ arb.venue_a }}</span>
                            <span class="venue-price">{{ formatPct(arb.price_a) }}</span>
                        </div>
                        <div class="arb-spread glow">{{ arb.spread_pct.toFixed(1) }}%</div>
                        <div class="venue">
                            <span class="venue-name">{{ arb.venue_b }}</span>
                            <span class="venue-price">{{ formatPct(arb.price_b) }}</span>
                        </div>
                    </div>
                    <div class="arb-footer">
                        <span>Confidence: {{ arb.confidence.toFixed(0) }}</span>
                        <span>{{ arb.direction }}</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Accuracy Tab -->
        <div v-if="activeTab === 'accuracy'" id="panel-accuracy" role="tabpanel" aria-labelledby="tab-accuracy" class="tab-content">
            <div v-if="!accuracy || accuracy.total_tracked === 0" class="empty-state">No predictions tracked yet.</div>
            <div v-else class="accuracy-panel">
                <div class="accuracy-stats">
                    <div class="acc-stat">
                        <div class="acc-value">{{ accuracy.total_tracked }}</div>
                        <div class="acc-label font-mono">Tracked</div>
                    </div>
                    <div class="acc-stat">
                        <div class="acc-value">{{ accuracy.total_resolved }}</div>
                        <div class="acc-label font-mono">Resolved</div>
                    </div>
                    <div class="acc-stat">
                        <div class="acc-value" :class="accuracy.overall_accuracy_pct >= 60 ? 'glow' : 'text-warn'">
                            {{ accuracy.overall_accuracy_pct.toFixed(1) }}%
                        </div>
                        <div class="acc-label font-mono">Accuracy</div>
                    </div>
                    <div class="acc-stat">
                        <div class="acc-value" :class="accuracy.overall_brier <= 0.25 ? 'glow' : 'text-warn'">
                            {{ accuracy.overall_brier.toFixed(3) }}
                        </div>
                        <div class="acc-label font-mono">Brier Score</div>
                    </div>
                </div>
                <div v-if="accuracy.high_conviction_resolved > 0" class="hc-section">
                    <div class="hc-title font-mono">High Conviction</div>
                    <div class="hc-stats">
                        {{ accuracy.high_conviction_resolved }} resolved &middot;
                        {{ accuracy.high_conviction_accuracy_pct.toFixed(1) }}% accurate &middot;
                        Brier {{ accuracy.high_conviction_brier.toFixed(3) }}
                    </div>
                </div>
                <div v-if="Object.keys(accuracy.by_source).length" class="source-section">
                    <div class="source-title font-mono">By Source</div>
                    <div v-for="(stats, source) in accuracy.by_source" :key="source" class="source-row">
                        <span class="source-name">{{ source }}</span>
                        <span>{{ stats.correct }}/{{ stats.total }} correct</span>
                        <span :class="stats.accuracy_pct >= 60 ? 'glow' : 'text-warn'">
                            {{ stats.accuracy_pct.toFixed(1) }}%
                        </span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Whales Tab -->
        <div v-if="activeTab === 'whales'" id="panel-whales" role="tabpanel" aria-labelledby="tab-whales" class="tab-content">
            <div v-if="!data?.whale_alerts?.length" class="empty-state">No suspicious activity detected.</div>
            <div v-else class="whale-list">
                <div
                    v-for="(alert, idx) in data.whale_alerts"
                    :key="idx"
                    class="whale-alert"
                >
                    {{ alert }}
                </div>
            </div>
        </div>
        </template>
    </div>
</template>

<style scoped>
.predictions-view {
    display: grid;
    gap: 1rem;
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.8rem;
}

.stats-bar {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.6rem;
}

.stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 0.65rem 0.5rem;
    text-align: center;
    backdrop-filter: blur(4px);
}

.stat-value { font-size: 1.3rem; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 0.62rem; color: var(--text-tertiary); margin-top: 0.2rem; }

.text-warn { color: var(--color-warning); text-shadow: 0 0 4px rgba(255, 176, 0, 0.3); }
.text-info { color: var(--color-info); text-shadow: 0 0 4px rgba(96, 165, 250, 0.3); }
.text-error { color: var(--color-error); text-shadow: 0 0 4px rgba(255, 68, 68, 0.3); }
.text-bullish { color: var(--color-terminal); text-shadow: 0 0 4px rgba(32, 194, 14, 0.3); }
.text-bearish { color: var(--color-error); text-shadow: 0 0 4px rgba(255, 68, 68, 0.3); }
.text-neutral { color: var(--text-secondary); }
.text-dim { color: var(--text-tertiary); }

.feed-row, .sentiment-row { display: flex; gap: 0.5rem; flex-wrap: wrap; }

.feed-chip {
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.feed-ok { background: rgba(32, 194, 14, 0.1); color: var(--color-terminal); border: 1px solid rgba(32, 194, 14, 0.2); }
.feed-warn { background: rgba(255, 176, 0, 0.1); color: var(--color-warning); border: 1px solid rgba(255, 176, 0, 0.2); }
.feed-off { background: rgba(255, 68, 68, 0.08); color: var(--color-error); border: 1px solid rgba(255, 68, 68, 0.2); }

.sentiment-chip {
    display: flex; gap: 0.5rem; align-items: center;
    padding: 0.2rem 0.65rem;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    font-size: 0.7rem;
}

.tab-bar {
    display: flex; gap: 0.25rem;
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: 0.25rem;
}

.tab-btn {
    padding: 0.4rem 0.75rem;
    background: transparent; border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    font-size: 0.75rem;
    font-family: var(--font-mono);
    letter-spacing: 0.04em;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
}

.tab-btn:hover { color: var(--text-secondary); }
.tab-btn.active { color: var(--color-terminal); border-bottom-color: var(--color-terminal); text-shadow: 0 0 6px rgba(32, 194, 14, 0.3); }

.tab-content { min-height: 200px; }
.empty-state { text-align: center; color: var(--text-tertiary); padding: 3rem; font-style: italic; }

.signal-grid, .arb-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 0.7rem;
}

.signal-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 0.75rem;
    transition: border-color 0.15s, box-shadow 0.15s;
    backdrop-filter: blur(4px);
}

.signal-card:hover { border-color: var(--border-accent); box-shadow: var(--glow-sm); }
.signal-hc { border-color: rgba(255, 176, 0, 0.3); }
.signal-risk { border-color: rgba(255, 68, 68, 0.3); }

.signal-header { display: flex; gap: 0.35rem; align-items: center; margin-bottom: 0.4rem; }

.source-badge {
    padding: 0.1rem 0.4rem;
    background: rgba(32, 194, 14, 0.1);
    color: var(--color-terminal);
    border: 1px solid rgba(32, 194, 14, 0.2);
    border-radius: var(--radius-xs);
    font-size: 0.6rem; font-weight: 700; text-transform: uppercase;
}

.whale-badge {
    padding: 0.1rem 0.4rem;
    background: rgba(96, 165, 250, 0.12);
    color: var(--color-info);
    border-radius: var(--radius-xs);
    font-size: 0.6rem; font-weight: 700;
}

.spike-badge {
    padding: 0.1rem 0.4rem;
    background: rgba(32, 194, 14, 0.1);
    color: var(--color-terminal);
    border-radius: var(--radius-xs);
    font-size: 0.6rem; font-weight: 700;
}

.risk-badge {
    padding: 0.1rem 0.4rem;
    border-radius: var(--radius-xs);
    font-size: 0.6rem; font-weight: 700;
}

.risk-severe { background: rgba(255, 68, 68, 0.15); color: var(--color-error); }
.risk-high { background: rgba(255, 176, 0, 0.15); color: var(--color-warning); }
.risk-medium { background: rgba(255, 140, 0, 0.12); color: #ff8c00; }

.signal-question {
    color: var(--text-primary);
    font-size: 0.75rem; line-height: 1.3; margin-bottom: 0.4rem;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.signal-stats { display: flex; gap: 0.75rem; align-items: center; margin-bottom: 0.35rem; }
.prob { font-weight: 700; font-size: 0.85rem; }
.vol { color: var(--text-tertiary); }
.momentum { font-size: 0.7rem; font-weight: 600; }
.vol-change { color: var(--text-tertiary); font-size: 0.65rem; }

.signal-symbols { display: flex; gap: 0.25rem; }

.symbol-tag {
    padding: 0.1rem 0.35rem;
    background: rgba(255, 176, 0, 0.08);
    color: var(--color-warning);
    border: 1px solid rgba(255, 176, 0, 0.15);
    border-radius: var(--radius-xs);
    font-size: 0.6rem; font-weight: 600;
}

.arb-card {
    background: var(--bg-card);
    border: 1px solid rgba(96, 165, 250, 0.25);
    border-radius: var(--radius-md);
    padding: 0.75rem;
    backdrop-filter: blur(4px);
}

.arb-name {
    color: var(--text-primary); font-size: 0.75rem; margin-bottom: 0.5rem;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.arb-venues { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.4rem; }
.venue { text-align: center; }
.venue-name { display: block; color: var(--text-tertiary); font-size: 0.6rem; text-transform: uppercase; }
.venue-price { display: block; font-size: 0.85rem; font-weight: 700; color: var(--text-primary); }
.arb-spread { font-size: 1.1rem; font-weight: 800; color: var(--color-info); }
.arb-footer { display: flex; justify-content: space-between; color: var(--text-tertiary); font-size: 0.65rem; }

.accuracy-panel { max-width: 600px; }
.accuracy-stats { display: flex; gap: 1rem; margin-bottom: 1rem; }
.acc-stat { text-align: center; flex: 1; }
.acc-value { font-size: 1.3rem; font-weight: 700; }
.acc-label { font-size: 0.6rem; color: var(--text-tertiary); text-transform: uppercase; margin-top: 0.15rem; }

.hc-section, .source-section {
    margin-top: 1rem; padding: 0.75rem;
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
}

.hc-title, .source-title { font-size: 0.7rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; margin-bottom: 0.4rem; }
.hc-stats { color: var(--text-primary); }

.source-row {
    display: flex; justify-content: space-between;
    padding: 0.25rem 0;
    border-bottom: 1px solid var(--border-subtle);
}

.source-name { font-weight: 600; text-transform: capitalize; }

.whale-list { display: flex; flex-direction: column; gap: 0.5rem; }

.whale-alert {
    padding: 0.75rem;
    background: rgba(255, 68, 68, 0.05);
    border: 1px solid rgba(255, 68, 68, 0.2);
    border-radius: var(--radius-sm);
    color: var(--color-error);
    font-size: 0.75rem; line-height: 1.4;
}

/* ── Status Bars ── */
.status-bar { padding: 0.45rem 0.8rem; font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.04em; border-radius: var(--radius-sm); text-align: center; }
.loading-bar { background: rgba(32, 194, 14, 0.08); color: var(--color-terminal); border: 1px solid rgba(32, 194, 14, 0.15); }
.error-bar { background: rgba(255, 68, 68, 0.08); color: var(--color-error); border: 1px solid rgba(255, 68, 68, 0.2); cursor: pointer; }
.stale-bar { background: rgba(255, 200, 50, 0.06); color: var(--color-warning); border: 1px solid rgba(255, 200, 50, 0.15); }

.pulse-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--color-terminal); margin-right: 0.4rem; animation: pulse 1.2s ease-in-out infinite; }

@keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

/* ── Skeleton ── */
.skeleton-card { position: relative; overflow: hidden; }
.skeleton-value { width: 40%; height: 1.5rem; margin: 0 auto 0.35rem; background: rgba(32, 194, 14, 0.08); border-radius: var(--radius-xs); animation: skelPulse 1.6s ease-in-out infinite; }
.skeleton-label { width: 60%; height: 0.6rem; margin: 0 auto; background: rgba(32, 194, 14, 0.05); border-radius: var(--radius-xs); animation: skelPulse 1.6s ease-in-out infinite 0.2s; }
.skeleton-header { width: 30%; height: 0.7rem; background: rgba(32, 194, 14, 0.06); border-radius: var(--radius-xs); margin-bottom: 0.5rem; animation: skelPulse 1.6s ease-in-out infinite; }
.skeleton-question { width: 90%; height: 0.75rem; background: rgba(32, 194, 14, 0.05); border-radius: var(--radius-xs); margin-bottom: 0.4rem; animation: skelPulse 1.6s ease-in-out infinite 0.15s; }
.skeleton-stats { width: 50%; height: 0.65rem; background: rgba(32, 194, 14, 0.04); border-radius: var(--radius-xs); animation: skelPulse 1.6s ease-in-out infinite 0.3s; }

@keyframes skelPulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 0.85; } }

@media (max-width: 760px) {
    .stats-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>

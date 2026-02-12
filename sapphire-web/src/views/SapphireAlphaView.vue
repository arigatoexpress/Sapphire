<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import TradingChart from '../components/TradingChart.vue'
import { fetchPerformanceStats, fetchRoutingInfo } from '../api/client'

interface InsightCard {
    title: string
    value: string
    detail: string
}

const insightCards = ref<InsightCard[]>([
    {
        title: 'Signal Throughput',
        value: 'n/a',
        detail: 'Awaiting alpha telemetry',
    },
    {
        title: 'Routing Confidence',
        value: 'n/a',
        detail: 'Awaiting confidence payload',
    },
    {
        title: 'Risk Posture',
        value: 'Guarded',
        detail: 'Fail-safe defaults are active',
    },
])

const watchlists = ref([
    { name: 'Core Majors', symbols: 'BTC, ETH, SOL, BNB, AVAX' },
    { name: 'Execution Pair Focus', symbols: 'SOL, ETH, BTC, HYPE, DOGE' },
    { name: 'Volatility Radar', symbols: 'LINK, JUP, PYTH, WIF, BONK' },
])

const strategyIntake = ref([
    'Breakout compression strategy (community Pine)',
    'Market structure and liquidity sweep detector',
    'Volatility regime classifier with trend filter',
    'Cross-venue divergence monitor with confidence gating',
])

const lastRefreshEpoch = ref(0)
const nowEpoch = ref(Date.now())
let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const refreshAge = computed(() => {
    if (!lastRefreshEpoch.value) return 'sync pending'
    return `${Math.max(0, Math.round((nowEpoch.value - lastRefreshEpoch.value) / 1000))}s ago`
})

const riskTone = computed(() => {
    const posture = insightCards.value.find((item) => item.title === 'Risk Posture')?.value || 'Guarded'
    const normalized = posture.toLowerCase()
    if (normalized.includes('offensive')) return 'tone-offensive'
    if (normalized.includes('balanced')) return 'tone-balanced'
    return 'tone-guarded'
})

const loadAlphaStatus = async () => {
    try {
        const [stats, routing] = await Promise.all([fetchPerformanceStats(), fetchRoutingInfo()])

        const totalTrades = Number(stats?.metrics?.system?.total_trades || 0)
        const wins = Number(stats?.metrics?.system?.wins || 0)
        const winRate = totalTrades > 0 ? Math.round((wins / totalTrades) * 100) : 0

        const confidenceRaw = routing?.confidence ?? routing?.data?.confidence ?? routing?.routing?.confidence
        const confidence = typeof confidenceRaw === 'number' ? `${Math.round(confidenceRaw * 100)}%` : 'n/a'

        const routePolicy = routing?.mode || routing?.strategy || 'Policy-driven'
        const posture = winRate >= 60 ? 'Offensive' : winRate >= 50 ? 'Balanced' : 'Guarded'

        insightCards.value = [
            {
                title: 'Signal Throughput',
                value: `${totalTrades} trades`,
                detail: 'Derived from system metrics snapshot',
            },
            {
                title: 'Routing Confidence',
                value: confidence,
                detail: `Mode: ${routePolicy}`,
            },
            {
                title: 'Risk Posture',
                value: posture,
                detail: `Win-rate baseline: ${winRate}%`,
            },
        ]
        lastRefreshEpoch.value = Date.now()
    } catch (error) {
        console.error('Failed to load alpha status:', error)
    }
}

onMounted(() => {
    loadAlphaStatus()
    refreshTimer = setInterval(loadAlphaStatus, 15000)
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
    <div class="alpha-view fade-in">
        <section class="hero card glass-lift">
            <div class="hero-copy">
                <span class="font-mono kicker">SAPPHIRE ALPHA</span>
                <h2>Market intelligence suite powering strategy and routing confidence.</h2>
                <p>
                    TradingView research is integrated into this alpha surface, while execution permissions stay owner-gated
                    through Telegram heartbeat control.
                </p>
            </div>
            <div class="meta-line">
                <span class="chip">Last sync {{ refreshAge }}</span>
                <span class="chip" :class="riskTone">
                    {{ insightCards[2]?.value || 'Guarded' }}
                </span>
            </div>
        </section>

        <section class="insights-grid">
            <article v-for="card in insightCards" :key="card.title" class="insight card glass-lift">
                <h3>{{ card.title }}</h3>
                <strong class="font-mono">{{ card.value }}</strong>
                <p>{{ card.detail }}</p>
            </article>
        </section>

        <section class="grid">
            <article class="chart-panel card">
                <header>
                    <h3 class="font-mono">Strategy Canvas</h3>
                    <small>Signal development display</small>
                </header>
                <TradingChart :base-price="80.4" :height="290" />
            </article>

            <article class="panel card">
                <h3 class="font-mono">Managed Watchlists</h3>
                <div class="watchlist" v-for="item in watchlists" :key="item.name">
                    <span>{{ item.name }}</span>
                    <small>{{ item.symbols }}</small>
                </div>
            </article>

            <article class="panel card">
                <h3 class="font-mono">Community Strategy Intake</h3>
                <ol>
                    <li v-for="scriptName in strategyIntake" :key="scriptName">{{ scriptName }}</li>
                </ol>
                <p class="hint">New strategy approvals are captured through heartbeat prompts before live rollout.</p>
            </article>
        </section>
    </div>
</template>

<style scoped>
.alpha-view {
    display: grid;
    gap: 0.9rem;
}

.hero {
    display: grid;
    gap: 0.74rem;
    background:
        radial-gradient(circle at 90% 6%, rgba(103, 208, 255, 0.2), transparent 40%),
        linear-gradient(130deg, rgba(6, 22, 44, 0.9), rgba(8, 24, 43, 0.75));
}

.kicker {
    color: #9de4ff;
    letter-spacing: 0.08em;
    font-size: 0.65rem;
}

.hero h2 {
    margin: 0.35rem 0 0.25rem;
    font-size: 1.1rem;
}

.hero p {
    margin: 0;
    color: var(--text-secondary);
    max-width: 74ch;
}

.meta-line {
    display: flex;
    gap: 0.44rem;
    flex-wrap: wrap;
}

.chip {
    border-radius: 999px;
    padding: 0.2rem 0.56rem;
    font-size: 0.73rem;
    border: 1px solid rgba(95, 181, 241, 0.55);
    color: #9cdcff;
}

.tone-offensive {
    border-color: rgba(23, 200, 136, 0.55);
    color: #78efbf;
}

.tone-balanced {
    border-color: rgba(244, 180, 68, 0.56);
    color: #ffd79a;
}

.tone-guarded {
    border-color: rgba(255, 116, 116, 0.58);
    color: #ffb1b1;
}

.insights-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 0.75rem;
}

.insight {
    background: rgba(8, 22, 40, 0.74);
}

.insight h3 {
    margin: 0;
    font-size: 0.8rem;
    color: var(--text-secondary);
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.insight strong {
    margin-top: 0.52rem;
    display: inline-block;
    font-size: 1.04rem;
    color: #d6ecff;
}

.insight p {
    margin: 0.46rem 0 0;
    color: var(--text-secondary);
    font-size: 0.84rem;
}

.grid {
    display: grid;
    grid-template-columns: 1.25fr 1fr 1fr;
    gap: 0.8rem;
}

.chart-panel,
.panel {
    background: rgba(8, 22, 40, 0.74);
}

.chart-panel header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.7rem;
}

.chart-panel h3 {
    margin: 0;
}

.chart-panel small {
    color: var(--text-tertiary);
    font-size: 0.72rem;
}

.panel h3 {
    margin: 0 0 0.66rem;
    font-size: 0.84rem;
    letter-spacing: 0.05em;
}

.panel ol {
    margin: 0;
    padding-left: 1.04rem;
    display: grid;
    gap: 0.42rem;
    color: #d4ebff;
    font-size: 0.83rem;
}

.watchlist {
    display: grid;
    gap: 0.2rem;
    padding: 0.44rem 0;
    border-bottom: 1px solid rgba(126, 185, 232, 0.22);
}

.watchlist:last-child {
    border-bottom: none;
}

.watchlist span {
    color: #e8f4ff;
    font-size: 0.87rem;
}

.watchlist small {
    color: var(--text-secondary);
    font-size: 0.76rem;
}

.hint {
    margin: 0.72rem 0 0;
    color: var(--text-tertiary);
    font-size: 0.74rem;
}

@media (max-width: 1240px) {
    .grid {
        grid-template-columns: 1fr;
    }
}
</style>

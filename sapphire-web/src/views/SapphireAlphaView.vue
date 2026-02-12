<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import TradingChart from '../components/TradingChart.vue'
import {
    fetchControlStatus,
    fetchMarketOHLC,
    fetchPerformanceStats,
    fetchRoutingInfo,
    fetchSecuritySkillsStatus,
    fetchTradingViewWorkspace,
    type OhlcCandle,
    type SecuritySkillsStatusResponse,
} from '../api/client'

interface InsightCard {
    title: string
    value: string
    detail: string
}

const alphaCandles = ref<OhlcCandle[]>([])
const chartSourceLabel = ref('Waiting for live OHLC feed')
const routingConfidencePct = ref<number | null>(null)
const totalTrades = ref(0)
const winRate = ref(0)
const realizedPnl = ref(0)
const routingMode = ref('guarded')
const control = ref<any>(null)
const workspace = ref<any>(null)
const security = ref<SecuritySkillsStatusResponse | null>(null)
const lastRefreshEpoch = ref(0)
const nowEpoch = ref(Date.now())
let refreshTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const refreshAge = computed(() => {
    if (!lastRefreshEpoch.value) return 'sync pending'
    return `${Math.max(0, Math.round((nowEpoch.value - lastRefreshEpoch.value) / 1000))}s ago`
})

const executionMode = computed(() =>
    control.value?.tradingview_execution_enabled ? 'TV signals live' : 'TV workbench dry-run',
)

const pendingDecisions = computed(() => Number(control.value?.pending_autonomy_decisions || 0))

const workspaceState = computed(() => workspace.value?.workspace?.state || {})

const watchlists = computed(() => {
    const raw = workspaceState.value?.watchlists || {}
    return Object.entries(raw).map(([name, symbols]) => ({
        name,
        symbols: Array.isArray(symbols) ? symbols.join(', ') : '',
    }))
})

const strategyIntake = computed(() => {
    const indicators = Array.isArray(workspaceState.value?.indicators) ? workspaceState.value.indicators : []
    const strategies = Array.isArray(workspaceState.value?.strategies) ? workspaceState.value.strategies : []
    const scripts = Array.isArray(workspaceState.value?.community_scripts) ? workspaceState.value.community_scripts : []
    const merged = [
        ...strategies.map((name: string) => `Strategy: ${name}`),
        ...indicators.map((name: string) => `Indicator: ${name}`),
        ...scripts.map((name: string) => `Community script: ${name}`),
    ]
    return merged.length > 0 ? merged : ['No active strategy assets in workspace state']
})

const insightCards = computed<InsightCard[]>(() => [
    {
        title: 'Signal Throughput',
        value: `${totalTrades.value} trades`,
        detail: `Win rate ${winRate.value}% · Realized PnL ${realizedPnl.value.toFixed(4)}`,
    },
    {
        title: 'Routing Confidence',
        value: routingConfidencePct.value === null ? 'n/a' : `${routingConfidencePct.value}%`,
        detail: `Mode: ${routingMode.value}`,
    },
    {
        title: 'TradingView Mode',
        value: executionMode.value,
        detail: `Pending decisions: ${pendingDecisions.value}`,
    },
    {
        title: 'Skill Security',
        value: security.value?.enabled
            ? security.value?.api_key_configured
                ? `VT ${security.value.enforcement_mode}`
                : 'VT key missing'
            : 'VT disabled',
        detail: security.value?.enabled
            ? `Skills dir ${security.value.skills_dir_exists ? 'ready' : 'missing'} · upload-on-miss ${security.value.upload_if_missing_default ? 'on' : 'off'}`
            : 'Enable VT guardrail for ClawHub/OpenClaw skill scanning.',
    },
])

const riskTone = computed(() => {
    if ((routingConfidencePct.value || 0) >= 70) return 'tone-offensive'
    if ((routingConfidencePct.value || 0) >= 45) return 'tone-balanced'
    return 'tone-guarded'
})

const readinessScore = computed(() => {
    const confidence = routingConfidencePct.value ?? 0
    const executionBoost = control.value?.tradingview_execution_enabled ? 5 : 0
    const queuePenalty = Math.min(20, pendingDecisions.value * 4)
    const composite = Math.round(confidence + executionBoost - queuePenalty)
    return Math.max(0, Math.min(100, composite))
})

const readinessTone = computed(() => {
    if (readinessScore.value >= 70) return 'readiness-strong'
    if (readinessScore.value >= 50) return 'readiness-balanced'
    return 'readiness-guarded'
})

const strategyRail = computed(() => [
    {
        label: 'Ingest',
        detail: `Assets scope ${workspaceState.value?.assets_scope || 'n/a'}`,
        status: alphaCandles.value.length > 0 ? 'ready' : 'pending',
    },
    {
        label: 'Synthesize',
        detail: `${strategyIntake.value.length} active strategy assets`,
        status: strategyIntake.value[0]?.startsWith('No ') ? 'pending' : 'ready',
    },
    {
        label: 'Validate',
        detail: `${pendingDecisions.value} decision(s) pending`,
        status: pendingDecisions.value > 0 ? 'pending' : 'ready',
    },
    {
        label: 'Route',
        detail: executionMode.value,
        status: control.value ? 'ready' : 'pending',
    },
])

const loadAlphaStatus = async () => {
    try {
        const [stats, routing, workspacePayload, controlPayload, securityPayload] = await Promise.all([
            fetchPerformanceStats(),
            fetchRoutingInfo(),
            fetchTradingViewWorkspace(),
            fetchControlStatus(),
            fetchSecuritySkillsStatus(),
        ])

        if (workspacePayload?.ok) workspace.value = workspacePayload
        if (controlPayload?.ok) control.value = controlPayload
        if (securityPayload?.ok) security.value = securityPayload

        totalTrades.value = Number(stats?.metrics?.system?.total_trades || 0)
        winRate.value = Number(stats?.metrics?.system?.win_rate || 0)
        realizedPnl.value = Number(stats?.metrics?.system?.realized_pnl || 0)

        const confidenceRaw = Number(routing?.confidence ?? 0)
        routingConfidencePct.value = Number.isFinite(confidenceRaw)
            ? Math.max(0, Math.min(100, Math.round(confidenceRaw * 100)))
            : null
        routingMode.value = String(routing?.mode || 'guarded')

        const preferredSymbol = String(workspaceState.value?.selected_symbol || 'SOL').toUpperCase()
        const ohlc = await fetchMarketOHLC({ venue: 'ASTER', symbol: preferredSymbol, interval: '1m', limit: 180 })
        const candles = (ohlc?.candles || [])
            .map((item) => ({
                time: Number(item.time),
                open: Number(item.open),
                high: Number(item.high),
                low: Number(item.low),
                close: Number(item.close),
                volume: Number(item.volume || 0),
            }))
            .filter(
                (item) =>
                    Number.isFinite(item.time) &&
                    Number.isFinite(item.open) &&
                    Number.isFinite(item.high) &&
                    Number.isFinite(item.low) &&
                    Number.isFinite(item.close),
            )
            .sort((a, b) => a.time - b.time)
        alphaCandles.value = candles
        chartSourceLabel.value =
            candles.length > 0
                ? `Live OHLC · ${ohlc?.venue || 'ASTER'} · ${ohlc?.symbol || preferredSymbol} (${ohlc?.source || 'market feed'})`
                : 'Waiting for live OHLC feed'

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
                <span class="font-mono kicker">SAPPHIRE ALPHA LIVE</span>
                <h2>Market-intelligence suite synchronized with runtime routing and TradingView workspace state.</h2>
                <p>
                    DEX-native market data drives live routing and execution context. TradingView remains the strategy workbench for
                    testing, backtesting, and signal iteration.
                </p>
            </div>
            <div class="meta-line">
                <span class="chip">Last sync {{ refreshAge }}</span>
                <span class="chip">{{ executionMode }}</span>
                <span class="chip" :class="riskTone">{{ routingMode }}</span>
            </div>
        </section>

        <section class="insights-grid">
            <article v-for="card in insightCards" :key="card.title" class="insight card glass-lift">
                <h3>{{ card.title }}</h3>
                <strong class="font-mono">{{ card.value }}</strong>
                <p>{{ card.detail }}</p>
            </article>
        </section>

        <section class="strategy-rail card glass-lift">
            <header>
                <h3 class="font-mono">Strategy Readiness Rail</h3>
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

        <section class="grid">
            <article class="chart-panel card">
                <header>
                    <h3 class="font-mono">Strategy Canvas</h3>
                    <small>{{ chartSourceLabel }}</small>
                </header>
                <TradingChart :candles="alphaCandles" :height="290" />
            </article>

            <article class="panel card">
                <h3 class="font-mono">Managed Watchlists</h3>
                <div class="watchlist" v-for="item in watchlists" :key="item.name">
                    <span>{{ item.name }}</span>
                    <small>{{ item.symbols || 'No symbols configured' }}</small>
                </div>
            </article>

            <article class="panel card">
                <h3 class="font-mono">Strategy Asset Intake</h3>
                <ol>
                    <li v-for="scriptName in strategyIntake" :key="scriptName">{{ scriptName }}</li>
                </ol>
                <p class="hint">
                    Workspace: {{ workspace?.workspace?.workspace_label || 'n/a' }} · Active watchlist
                    {{ workspaceState?.active_watchlist || 'n/a' }}
                </p>
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
        radial-gradient(circle at 92% 6%, rgba(103, 208, 255, 0.24), transparent 40%),
        linear-gradient(130deg, rgba(6, 22, 44, 0.92), rgba(8, 24, 43, 0.76));
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

.strategy-rail {
    background: rgba(8, 22, 40, 0.74);
    border: 1px solid rgba(127, 188, 236, 0.32);
}

.strategy-rail header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.7rem;
    margin-bottom: 0.72rem;
}

.strategy-rail h3 {
    margin: 0;
    font-size: 0.84rem;
    letter-spacing: 0.05em;
}

.rail-score {
    border-radius: 999px;
    padding: 0.2rem 0.56rem;
    font-size: 0.73rem;
    border: 1px solid rgba(95, 181, 241, 0.55);
    color: #9cdcff;
}

.readiness-strong {
    border-color: rgba(23, 200, 136, 0.55);
    color: #78efbf;
}

.readiness-balanced {
    border-color: rgba(244, 180, 68, 0.56);
    color: #ffd79a;
}

.readiness-guarded {
    border-color: rgba(255, 116, 116, 0.58);
    color: #ffb1b1;
}

.rail-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.56rem;
}

.rail-stage {
    border-radius: var(--radius-md);
    border: 1px solid rgba(124, 184, 232, 0.28);
    background: rgba(8, 22, 40, 0.7);
    padding: 0.56rem;
    display: grid;
    gap: 0.2rem;
}

.rail-stage p {
    margin: 0;
    font-size: 0.64rem;
    letter-spacing: 0.08em;
    color: #98d8fb;
}

.rail-stage strong {
    font-size: 0.78rem;
}

.rail-stage small {
    color: var(--text-secondary);
    font-size: 0.72rem;
}

.stage-ready strong {
    color: #7beec2;
}

.stage-pending strong {
    color: #ffbbac;
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
    .rail-grid {
        grid-template-columns: 1fr 1fr;
    }

    .grid {
        grid-template-columns: 1fr;
    }
}
</style>

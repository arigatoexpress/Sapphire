<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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

interface AlphaSnapshot {
    symbol: string
    price: number | null
    change1h: number | null
    change6h: number | null
    volatility: number | null
    confidence: number
    history: number[]
}

const INSIGHT_SYMBOLS = ['BTC', 'ETH', 'SOL', 'AVAX', 'DOGE', 'HYPE']

const selectedSymbol = ref('BTC')
const alphaCandles = ref<OhlcCandle[]>([])
const lighterCandles = ref<OhlcCandle[]>([])
const snapshots = ref<AlphaSnapshot[]>([])
const chartSourceLabel = ref('Waiting for live OHLC feed')
const compareSourceLabel = ref('Waiting for venue comparison feed')
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

const formatPct = (value: number | null, digits = 2) => {
    if (value === null || !Number.isFinite(value)) return 'n/a'
    return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

const formatPrice = (value: number | null) => {
    if (value === null || !Number.isFinite(value) || value <= 0) return 'n/a'
    if (value >= 1000) return `$${value.toFixed(2)}`
    if (value >= 100) return `$${value.toFixed(3)}`
    return `$${value.toFixed(4)}`
}

const normalizeCandles = (candles: OhlcCandle[] | null | undefined): OhlcCandle[] =>
    (candles || [])
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
            const y = 28 - ((value - min) / spread) * 22 - 3
            return `${x.toFixed(2)},${y.toFixed(2)}`
        })
        .join(' ')
}

const marketBreadth = computed(() => {
    const active = snapshots.value.filter((item) => item.change1h !== null)
    const advancing = active.filter((item) => (item.change1h || 0) > 0).length
    const breadth = active.length ? Math.round((advancing / active.length) * 100) : 0
    return { advancing, declining: Math.max(0, active.length - advancing), breadth }
})

const macroRegime = computed(() => {
    const score = marketBreadth.value.breadth
    if (score >= 65) return 'Expansion / risk-on'
    if (score >= 45) return 'Rotation / mixed'
    return 'Contraction / risk-off'
})

const strongestMover = computed(() =>
    [...snapshots.value]
        .filter((item) => item.change1h !== null)
        .sort((a, b) => Number(b.change1h || 0) - Number(a.change1h || 0))[0] || null,
)

const selectedSnapshot = computed(
    () => snapshots.value.find((item) => item.symbol === selectedSymbol.value) || null,
)

const alphaIdeas = computed(() => {
    const ideas: Array<{ title: string; detail: string; tone: 'bullish' | 'neutral' | 'defensive' }> = []
    const leader = strongestMover.value

    if (leader && (leader.change1h || 0) > 1.25) {
        ideas.push({
            title: `${leader.symbol} leadership continuation`,
            detail: `${formatPct(leader.change1h)} in 1h with macro breadth at ${marketBreadth.value.breadth}%. Favor trend-confirmation setups over countertrend fades.`,
            tone: 'bullish',
        })
    }

    if ((selectedSnapshot.value?.volatility || 0) > 0.8) {
        ideas.push({
            title: `${selectedSymbol.value} high-volatility watch`,
            detail: `Estimated volatility ${formatPct(selectedSnapshot.value?.volatility || null)} suggests wider ranges. Prefer adaptive stops and smaller initial sizing.`,
            tone: 'neutral',
        })
    }

    if (marketBreadth.value.breadth <= 40) {
        ideas.push({
            title: 'Defensive allocation posture',
            detail: `Breadth is ${marketBreadth.value.breadth}% with ${marketBreadth.value.declining} assets declining. Preserve capital and tighten idea acceptance thresholds.`,
            tone: 'defensive',
        })
    }

    if (!ideas.length) {
        ideas.push({
            title: 'Neutral discovery regime',
            detail: 'Signals are balanced across assets. Focus on high-conviction dislocations and wait for regime expansion.',
            tone: 'neutral',
        })
    }

    return ideas.slice(0, 3)
})

const insightCards = computed<InsightCard[]>(() => [
    {
        title: 'Market Breadth',
        value: `${marketBreadth.value.breadth}%`,
        detail: `${marketBreadth.value.advancing} advancing · ${marketBreadth.value.declining} declining · ${macroRegime.value}`,
    },
    {
        title: 'Routing Confidence',
        value: routingConfidencePct.value === null ? 'n/a' : `${routingConfidencePct.value}%`,
        detail: `Mode: ${routingMode.value}`,
    },
    {
        title: 'Signal Throughput',
        value: `${totalTrades.value} trades`,
        detail: `Win rate ${winRate.value}% · Realized PnL ${realizedPnl.value.toFixed(4)}`,
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
            : 'Enable VT guardrail for skill scanning.',
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
    const breadthBoost = Math.round((marketBreadth.value.breadth - 50) * 0.2)
    const composite = Math.round(confidence + executionBoost + breadthBoost - queuePenalty)
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

        if (workspacePayload?.ok) {
            workspace.value = workspacePayload
            const workspaceSymbol = String(workspacePayload.workspace?.state?.selected_symbol || '').toUpperCase()
            if (workspaceSymbol && !selectedSymbol.value) selectedSymbol.value = workspaceSymbol
        }
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

        const [asterOhlc, lighterOhlc, basketPayloads] = await Promise.all([
            fetchMarketOHLC({ venue: 'ASTER', symbol: selectedSymbol.value, interval: '1m', limit: 220 }),
            fetchMarketOHLC({ venue: 'LIGHTER', symbol: selectedSymbol.value, interval: '1m', limit: 220 }),
            Promise.all(
                INSIGHT_SYMBOLS.map((symbol) =>
                    fetchMarketOHLC({ venue: 'ASTER', symbol, interval: '5m', limit: 120 }),
                ),
            ),
        ])

        alphaCandles.value = normalizeCandles(asterOhlc?.candles)
        lighterCandles.value = normalizeCandles(lighterOhlc?.candles)

        chartSourceLabel.value =
            alphaCandles.value.length > 0
                ? `ASTER · ${asterOhlc?.symbol || selectedSymbol.value} (${asterOhlc?.source || 'market feed'})`
                : 'Waiting for live OHLC feed'

        compareSourceLabel.value =
            lighterCandles.value.length > 0
                ? `LIGHTER · ${lighterOhlc?.symbol || selectedSymbol.value} (${lighterOhlc?.source || 'market feed'})`
                : 'Waiting for venue comparison feed'

        snapshots.value = INSIGHT_SYMBOLS.map((symbol, index) => {
            const payload = basketPayloads[index]
            const candles = normalizeCandles(payload?.candles)
            const history = candles.map((item) => Number(item.close)).filter((value) => Number.isFinite(value))
            const price = history.length ? Number(history[history.length - 1]) : null
            const change1h = computeChangePct(history, 12)
            const change6h = computeChangePct(history, 72)
            const volatility = estimateVolatility(history.slice(-72))
            const confidence = Math.max(
                0,
                Math.min(
                    100,
                    Math.round((change1h || 0) * 12 + (change6h || 0) * 4 - (volatility || 0) * 2 + 50),
                ),
            )
            return {
                symbol,
                price,
                change1h,
                change6h,
                volatility,
                confidence,
                history: history.slice(-30),
            }
        })

        lastRefreshEpoch.value = Date.now()
    } catch (error) {
        console.error('Failed to load alpha status:', error)
    }
}

watch(selectedSymbol, () => {
    loadAlphaStatus()
})

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
                <h2>Broad-market intelligence workbench for idea discovery and strategy validation.</h2>
                <p>
                    DEX-native feeds drive market context while TradingView remains the experimentation workbench. Alpha outputs now span
                    BTC, ETH, SOL, AVAX, DOGE, and HYPE instead of a single-asset lens.
                </p>
            </div>
            <div class="hero-controls">
                <label class="symbol-picker">
                    <span class="font-mono">Focus asset</span>
                    <select v-model="selectedSymbol">
                        <option v-for="symbol in INSIGHT_SYMBOLS" :key="symbol" :value="symbol">{{ symbol }}</option>
                    </select>
                </label>
            </div>
            <div class="meta-line">
                <span class="chip">Last sync {{ refreshAge }}</span>
                <span class="chip">{{ executionMode }}</span>
                <span class="chip" :class="riskTone">{{ routingMode }}</span>
                <span class="chip">Breadth {{ marketBreadth.breadth }}%</span>
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
                    <h3 class="font-mono">ASTER Strategy Canvas</h3>
                    <small>{{ chartSourceLabel }}</small>
                </header>
                <TradingChart :candles="alphaCandles" :height="270" />
            </article>

            <article class="chart-panel card">
                <header>
                    <h3 class="font-mono">LIGHTER Comparison Canvas</h3>
                    <small>{{ compareSourceLabel }}</small>
                </header>
                <TradingChart :candles="lighterCandles" :height="270" />
            </article>

            <article class="panel card matrix-panel">
                <h3 class="font-mono">Market Intelligence Matrix</h3>
                <div class="matrix-grid">
                    <article v-for="snapshot in snapshots" :key="snapshot.symbol" class="matrix-item">
                        <header>
                            <strong>{{ snapshot.symbol }}</strong>
                            <span :class="(snapshot.change1h || 0) >= 0 ? 'tone-offensive' : 'tone-guarded'">{{ formatPct(snapshot.change1h) }}</span>
                        </header>
                        <p>price {{ formatPrice(snapshot.price) }}</p>
                        <small>6h {{ formatPct(snapshot.change6h) }} · confidence {{ snapshot.confidence }}%</small>
                        <svg class="sparkline" viewBox="0 0 100 28" preserveAspectRatio="none">
                            <polyline :points="sparklinePoints(snapshot.history)" />
                        </svg>
                    </article>
                </div>
            </article>
        </section>

        <section class="idea-feed card glass-lift">
            <header>
                <h3 class="font-mono">Alpha Idea Feed</h3>
                <small>Candidate setups generated from live market breadth + volatility + routing context</small>
            </header>
            <article v-for="idea in alphaIdeas" :key="idea.title" class="idea-item" :class="`idea-${idea.tone}`">
                <h4>{{ idea.title }}</h4>
                <p>{{ idea.detail }}</p>
            </article>
        </section>

        <section class="workspace-grid">
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
    color: #78efbf;
}

.tone-balanced {
    color: #ffd79a;
}

.tone-guarded {
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

.grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1.2fr;
    gap: 0.8rem;
}

.chart-panel,
.panel,
.idea-feed {
    background: rgba(8, 22, 40, 0.74);
}

.chart-panel header,
.idea-feed header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.7rem;
}

.chart-panel h3,
.idea-feed h3,
.panel h3 {
    margin: 0;
}

.chart-panel small,
.idea-feed small {
    color: var(--text-tertiary);
    font-size: 0.72rem;
}

.matrix-panel {
    display: grid;
    gap: 0.6rem;
}

.matrix-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
}

.matrix-item {
    border: 1px solid rgba(125, 186, 232, 0.28);
    border-radius: 10px;
    padding: 0.45rem 0.52rem;
    background: rgba(8, 22, 40, 0.66);
    display: grid;
    gap: 0.18rem;
}

.matrix-item header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.matrix-item p,
.matrix-item small {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.74rem;
}

.sparkline {
    width: 100%;
    height: 34px;
    border-radius: 8px;
    background: linear-gradient(180deg, rgba(15, 45, 73, 0.34), rgba(9, 26, 42, 0.24));
}

.sparkline polyline {
    fill: none;
    stroke: #86dcff;
    stroke-width: 2;
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

.workspace-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
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

@media (max-width: 1320px) {
    .grid {
        grid-template-columns: 1fr;
    }

    .workspace-grid {
        grid-template-columns: 1fr;
    }

    .rail-grid {
        grid-template-columns: 1fr 1fr;
    }
}

@media (max-width: 760px) {
    .matrix-grid,
    .rail-grid {
        grid-template-columns: 1fr;
    }

    .hero-controls {
        justify-content: flex-start;
    }
}
</style>

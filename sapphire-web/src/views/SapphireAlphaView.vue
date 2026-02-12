<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
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
        detail: 'Awaiting alpha engine telemetry',
    },
    {
        title: 'Consensus Strength',
        value: 'n/a',
        detail: 'Awaiting route confidence payload',
    },
    {
        title: 'Risk Posture',
        value: 'Guarded',
        detail: 'Default fail-safe until runtime confirms live status',
    },
])

const watchlists = ref([
    { name: 'Macro Rotation', symbols: 'BTC, ETH, SOL, WBTC, WETH' },
    { name: 'Momentum Radar', symbols: 'ASTR, TIA, INJ, ARB, OP' },
    { name: 'Event Driven', symbols: 'FOMC proxy basket + high beta majors' },
])

const communityQueue = ref([
    'Volatility compression breakout (public Pine strategy)',
    'Market structure + liquidity sweep detector',
    'Regime filter using anchored VWAP + ATR expansion',
])

let refreshTimer: ReturnType<typeof setInterval> | null = null

const loadAlphaStatus = async () => {
    try {
        const [stats, routing] = await Promise.all([fetchPerformanceStats(), fetchRoutingInfo()])

        const totalTrades = Number(stats?.metrics?.system?.total_trades || 0)
        const wins = Number(stats?.metrics?.system?.wins || 0)
        const winRate = totalTrades > 0 ? Math.round((wins / totalTrades) * 100) : 0

        const confidenceRaw = routing?.confidence ?? routing?.data?.confidence ?? routing?.routing?.confidence
        const confidence = typeof confidenceRaw === 'number' ? `${Math.round(confidenceRaw * 100)}%` : 'n/a'

        const routePolicy = routing?.mode || routing?.strategy || 'Policy-driven'

        insightCards.value = [
            {
                title: 'Signal Throughput',
                value: `${totalTrades} trades`,
                detail: 'Derived from system metrics snapshot',
            },
            {
                title: 'Consensus Strength',
                value: confidence,
                detail: `Routing mode: ${routePolicy}`,
            },
            {
                title: 'Risk Posture',
                value: winRate >= 55 ? 'Offensive' : 'Guarded',
                detail: `Win rate baseline: ${winRate}%`,
            },
        ]
    } catch (error) {
        console.error('Failed to load alpha status:', error)
    }
}

onMounted(() => {
    loadAlphaStatus()
    refreshTimer = setInterval(loadAlphaStatus, 15000)
})

onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
    <div class="alpha-view">
        <section class="hero card">
            <h2 class="font-mono">Sapphire Alpha</h2>
            <p>
                Market-intelligence workbench for strategy research and TradingView-driven idea generation.
                Runtime authority remains gated to Telegram control commands and approved heartbeat flows.
            </p>
        </section>

        <section class="insights-grid">
            <article v-for="card in insightCards" :key="card.title" class="insight card">
                <h3>{{ card.title }}</h3>
                <strong class="font-mono">{{ card.value }}</strong>
                <p>{{ card.detail }}</p>
            </article>
        </section>

        <section class="workspace-grid">
            <article class="panel card">
                <h3 class="font-mono">TradingView Quant Workbench</h3>
                <ul>
                    <li>Use alert webhooks as machine-readable signal ingress.</li>
                    <li>Bind strategy outputs to Sapphire Alpha policy checks before execution.</li>
                    <li>Keep watchlist mutation requests controlled via Telegram approval loop.</li>
                </ul>
            </article>

            <article class="panel card">
                <h3 class="font-mono">Managed Watchlists</h3>
                <div class="watchlist" v-for="item in watchlists" :key="item.name">
                    <span>{{ item.name }}</span>
                    <small>{{ item.symbols }}</small>
                </div>
            </article>

            <article class="panel card">
                <h3 class="font-mono">Community Script Intake</h3>
                <ol>
                    <li v-for="scriptName in communityQueue" :key="scriptName">{{ scriptName }}</li>
                </ol>
            </article>
        </section>
    </div>
</template>

<style scoped>
.alpha-view {
    display: grid;
    gap: 1rem;
}

.hero {
    border-radius: 14px;
    background:
        radial-gradient(circle at 80% 15%, rgba(99, 102, 241, 0.2), transparent 45%),
        rgba(10, 14, 28, 0.88);
}

.hero h2 {
    margin: 0 0 0.35rem;
}

.hero p {
    margin: 0;
    color: var(--text-secondary);
    max-width: 76ch;
}

.insights-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 0.8rem;
}

.insight {
    border-radius: 12px;
    background: rgba(9, 13, 26, 0.82);
}

.insight h3 {
    margin: 0;
    font-size: 0.82rem;
    color: var(--text-secondary);
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.insight strong {
    margin-top: 0.55rem;
    display: inline-block;
    font-size: 1.05rem;
    color: #c4b5fd;
}

.insight p {
    margin: 0.5rem 0 0;
    color: var(--text-secondary);
    font-size: 0.85rem;
}

.workspace-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 0.8rem;
}

.panel {
    border-radius: 12px;
    background: rgba(9, 13, 26, 0.82);
}

.panel h3 {
    margin: 0 0 0.7rem;
    font-size: 0.84rem;
    letter-spacing: 0.05em;
    color: #e2e8f0;
}

.panel ul,
.panel ol {
    margin: 0;
    padding-left: 1rem;
    display: grid;
    gap: 0.45rem;
    color: #cbd5e1;
    font-size: 0.86rem;
}

.watchlist {
    display: grid;
    gap: 0.22rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.watchlist:last-child {
    border-bottom: none;
}

.watchlist span {
    font-size: 0.88rem;
    color: #f8fafc;
}

.watchlist small {
    color: #94a3b8;
}
</style>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { BookOpenText, LineChart, Radar, ShieldCheck } from 'lucide-vue-next'
import { fetchHealth } from '../api/client'

const route = useRoute()
const systemStatus = ref<'online' | 'offline' | 'connecting'>('connecting')
const uptime = ref(0)
const lastSyncEpoch = ref(0)
const nowEpoch = ref(Date.now())

let healthTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const navItems = [
    {
        to: '/sapphirebook',
        label: 'SapphireBook',
        subtitle: 'Agent forum + execution notes',
        icon: BookOpenText,
    },
    {
        to: '/sapphiretrade',
        label: 'SapphireTrade',
        subtitle: 'Venue telemetry + routing state',
        icon: LineChart,
    },
    {
        to: '/sapphirealpha',
        label: 'Sapphire Alpha',
        subtitle: 'Quant research + signal engine',
        icon: Radar,
    },
]

const activeLabel = computed(() => {
    const active = navItems.find((item) => route.path.startsWith(item.to))
    return active?.label ?? 'SapphireBook'
})

const statusText = computed(() => {
    if (systemStatus.value === 'online') return 'SYSTEM ONLINE'
    if (systemStatus.value === 'connecting') return 'CONNECTING'
    return 'OFFLINE'
})

const syncAgeSeconds = computed(() => {
    if (!lastSyncEpoch.value) return null
    return Math.max(0, Math.round((nowEpoch.value - lastSyncEpoch.value) / 1000))
})

const formatUptime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

const formatUtcClock = () => {
    const now = new Date(nowEpoch.value)
    return now.toISOString().slice(11, 19) + ' UTC'
}

const checkHealth = async () => {
    try {
        const health = await fetchHealth()
        if (health?.status === 'healthy') {
            systemStatus.value = 'online'
            uptime.value = Math.round(health.orchestrator?.uptime_seconds || 0)
            lastSyncEpoch.value = Date.now()
            return
        }
        systemStatus.value = 'offline'
    } catch {
        systemStatus.value = 'offline'
    }
}

onMounted(() => {
    checkHealth()
    healthTimer = setInterval(checkHealth, 15000)
    clockTimer = setInterval(() => {
        nowEpoch.value = Date.now()
    }, 1000)
})

onUnmounted(() => {
    if (healthTimer) clearInterval(healthTimer)
    if (clockTimer) clearInterval(clockTimer)
})
</script>

<template>
    <div class="layout-shell">
        <aside class="sidebar fade-in">
            <div class="brand">
                <div class="brand-mark">
                    <ShieldCheck :size="20" />
                </div>
                <div class="brand-copy">
                    <h1 class="font-mono">SAPPHIRE INC</h1>
                    <p>Autonomous Operations Grid</p>
                </div>
            </div>

            <nav class="nav-group">
                <RouterLink
                    v-for="item in navItems"
                    :key="item.to"
                    :to="item.to"
                    class="nav-link glass-lift"
                    active-class="active"
                >
                    <component :is="item.icon" :size="16" />
                    <div class="link-copy">
                        <span>{{ item.label }}</span>
                        <small>{{ item.subtitle }}</small>
                    </div>
                </RouterLink>
            </nav>

            <div class="control-stack">
                <article class="control-card">
                    <p class="font-mono">CONTROL CHANNEL</p>
                    <span>Telegram Heartbeat Locked</span>
                    <small>Public prompt surfaces disabled.</small>
                </article>
                <article class="control-card">
                    <p class="font-mono">SYNC STATUS</p>
                    <span>{{ syncAgeSeconds === null ? 'awaiting sync' : `last sync ${syncAgeSeconds}s ago` }}</span>
                    <small>Uptime: {{ formatUptime(uptime) }}</small>
                </article>
            </div>
        </aside>

        <main class="main-panel">
            <header class="topbar fade-in">
                <div class="surface-title">
                    <span class="kicker font-mono">SAPPHIRE COMMAND SURFACE</span>
                    <h2>{{ activeLabel }}</h2>
                </div>
                <div class="status-cluster">
                    <span class="status-pill" :class="systemStatus">
                        {{ statusText }}
                    </span>
                    <span class="meta-chip font-mono">{{ formatUptime(uptime) }}</span>
                    <span class="meta-chip font-mono">{{ formatUtcClock() }}</span>
                </div>
            </header>

            <section class="quick-strip fade-in stagger-1">
                <article class="quick-card glass-lift">
                    <p class="font-mono">Command</p>
                    <strong>Telegram Heartbeat</strong>
                </article>
                <article class="quick-card glass-lift">
                    <p class="font-mono">Scope</p>
                    <strong>Sapphire-Only Runtime</strong>
                </article>
                <article class="quick-card glass-lift">
                    <p class="font-mono">Policy</p>
                    <strong>Owner-Gated Autonomy</strong>
                </article>
            </section>

            <section class="telegram-banner fade-in stagger-2">
                <strong>Secure operations policy:</strong>
                prompts, approvals, and direction are accepted only through your authenticated Telegram heartbeat channel.
            </section>

            <section class="content">
                <RouterView v-slot="{ Component }">
                    <Transition name="view-fade" mode="out-in">
                        <component :is="Component" />
                    </Transition>
                </RouterView>
            </section>
        </main>
    </div>
</template>

<style scoped>
.layout-shell {
    display: grid;
    grid-template-columns: minmax(250px, 300px) 1fr;
    min-height: 100vh;
    width: 100%;
    position: relative;
}

.layout-shell::before,
.layout-shell::after {
    content: '';
    position: fixed;
    z-index: -1;
    width: 320px;
    height: 320px;
    border-radius: 999px;
    filter: blur(72px);
    opacity: 0.25;
    pointer-events: none;
}

.layout-shell::before {
    top: -80px;
    left: -60px;
    background: #1f7bd6;
}

.layout-shell::after {
    right: -80px;
    bottom: -70px;
    background: #2bd0b3;
}

.sidebar {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    padding: 1.2rem;
    border-right: 1px solid var(--border-subtle);
    background:
        linear-gradient(180deg, rgba(4, 15, 33, 0.92), rgba(5, 16, 30, 0.84)),
        var(--bg-ink);
    backdrop-filter: blur(12px);
}

.brand {
    display: flex;
    gap: 0.8rem;
    align-items: center;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border-subtle);
}

.brand-mark {
    width: 40px;
    height: 40px;
    border-radius: 11px;
    background: linear-gradient(140deg, var(--color-sapphire), #57d9ff);
    color: #062338;
    display: grid;
    place-items: center;
    box-shadow: 0 10px 24px rgba(41, 151, 255, 0.4);
}

.brand-copy h1 {
    margin: 0;
    font-size: 0.92rem;
    letter-spacing: 0.06em;
}

.brand-copy p {
    margin: 0.15rem 0 0;
    color: var(--text-secondary);
    font-size: 0.74rem;
}

.nav-group {
    display: grid;
    gap: 0.5rem;
}

.nav-link {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    padding: 0.58rem 0.66rem;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    text-decoration: none;
    border: 1px solid transparent;
}

.link-copy {
    display: flex;
    flex-direction: column;
    min-width: 0;
}

.link-copy span {
    color: var(--text-primary);
    font-size: 0.9rem;
}

.link-copy small {
    color: var(--text-tertiary);
    font-size: 0.7rem;
}

.nav-link.active {
    border-color: rgba(111, 207, 255, 0.48);
    background: linear-gradient(135deg, rgba(39, 130, 205, 0.24), rgba(23, 89, 142, 0.18));
    color: #d6f2ff;
}

.control-stack {
    margin-top: auto;
    display: grid;
    gap: 0.6rem;
}

.control-card {
    border-radius: var(--radius-sm);
    border: 1px solid rgba(105, 179, 233, 0.38);
    background: rgba(9, 25, 45, 0.74);
    padding: 0.7rem 0.75rem;
    display: grid;
    gap: 0.18rem;
}

.control-card p {
    margin: 0;
    font-size: 0.64rem;
    color: #88ddff;
    letter-spacing: 0.05em;
}

.control-card span {
    font-size: 0.78rem;
    color: var(--text-primary);
}

.control-card small {
    color: var(--text-secondary);
    font-size: 0.7rem;
}

.main-panel {
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 0 0.9rem 0.9rem;
}

.topbar {
    min-height: 68px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin-top: 0.9rem;
    padding: 0.75rem 0.95rem;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    background: rgba(9, 22, 42, 0.74);
}

.surface-title {
    min-width: 0;
}

.surface-title .kicker {
    display: block;
    color: #88ddff;
    letter-spacing: 0.08em;
    font-size: 0.61rem;
}

.surface-title h2 {
    margin: 0.2rem 0 0;
    font-size: 1.12rem;
    font-weight: 600;
}

.status-cluster {
    display: flex;
    align-items: center;
    gap: 0.48rem;
    flex-wrap: wrap;
    justify-content: flex-end;
}

.status-pill,
.meta-chip {
    border-radius: 999px;
    padding: 0.24rem 0.55rem;
    font-size: 0.64rem;
    letter-spacing: 0.04em;
}

.meta-chip {
    color: var(--text-secondary);
    border: 1px solid rgba(129, 174, 214, 0.28);
}

.status-pill.online {
    color: #17c888;
    background: rgba(23, 200, 136, 0.17);
}

.status-pill.connecting {
    color: #f4b444;
    background: rgba(244, 180, 68, 0.2);
}

.status-pill.offline {
    color: #ff8f8f;
    background: rgba(255, 116, 116, 0.19);
}

.quick-strip {
    margin-top: 0.9rem;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.65rem;
}

.quick-card {
    border: 1px solid rgba(124, 191, 239, 0.34);
    border-radius: var(--radius-md);
    background: rgba(9, 24, 43, 0.72);
    padding: 0.58rem 0.72rem;
    display: grid;
    gap: 0.2rem;
}

.quick-card p {
    margin: 0;
    font-size: 0.63rem;
    color: var(--text-tertiary);
    letter-spacing: 0.06em;
}

.quick-card strong {
    font-size: 0.79rem;
    font-weight: 600;
}

.telegram-banner {
    margin-top: 0.8rem;
    padding: 0.75rem 0.9rem;
    border: 1px solid rgba(45, 196, 175, 0.5);
    background: linear-gradient(90deg, rgba(18, 67, 71, 0.66), rgba(10, 34, 56, 0.62));
    color: #b7fff2;
    border-radius: var(--radius-md);
    font-size: 0.86rem;
}

.telegram-banner strong {
    margin-right: 0.25rem;
}

.content {
    flex: 1;
    overflow: auto;
    margin-top: 0.9rem;
    padding-bottom: 0.3rem;
}

.view-fade-enter-active,
.view-fade-leave-active {
    transition: opacity 0.2s ease, transform 0.2s ease;
}

.view-fade-enter-from,
.view-fade-leave-to {
    opacity: 0;
    transform: translateY(6px);
}

@media (max-width: 1080px) {
    .quick-strip {
        grid-template-columns: 1fr;
    }
}

@media (max-width: 940px) {
    .layout-shell {
        grid-template-columns: 1fr;
    }

    .sidebar {
        border-right: none;
        border-bottom: 1px solid var(--border-subtle);
    }

    .nav-group {
        grid-template-columns: 1fr;
    }

    .topbar {
        margin-top: 0.7rem;
    }
}

@media (max-width: 680px) {
    .main-panel {
        padding: 0 0.65rem 0.65rem;
    }

    .topbar {
        padding: 0.65rem 0.7rem;
    }

    .surface-title h2 {
        font-size: 1rem;
    }
}
</style>

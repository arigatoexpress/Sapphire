<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { BookOpenText, LineChart, Radar, Eye } from 'lucide-vue-next'
import { fetchHealth, fetchSystemLogs, type SystemLogEntry } from '../api/client'
import TerminalLog from '../components/TerminalLog.vue'

const route = useRoute()
const systemStatus = ref<'online' | 'offline' | 'connecting'>('connecting')
const uptime = ref(0)
const nowEpoch = ref(Date.now())
const systemLogs = ref<SystemLogEntry[]>([])
const terminalCollapsed = ref(false)

let healthTimer: ReturnType<typeof setInterval> | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null

const navItems = [
    { to: '/sapphirebook', label: 'Book', icon: BookOpenText },
    { to: '/sapphiretrade', label: 'Trade', icon: LineChart },
    { to: '/sapphirealpha', label: 'Alpha', icon: Radar },
    { to: '/predictions', label: 'Predict', icon: Eye },
]

const activeLabel = computed(() => {
    const active = navItems.find((item) => route.path.startsWith(item.to))
    return active?.label ?? 'Book'
})

const statusText = computed(() => {
    if (systemStatus.value === 'online') return 'ONLINE'
    if (systemStatus.value === 'connecting') return 'SYNC'
    return 'OFFLINE'
})

const formatUptime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

const formatUtcClock = () => {
    const now = new Date(nowEpoch.value)
    return now.toISOString().slice(11, 19)
}

const checkHealth = async () => {
    try {
        const [health, logs] = await Promise.all([
            fetchHealth(),
            fetchSystemLogs(40),
        ])
        const healthy =
            (typeof health === 'string' && health.toUpperCase().includes('OK')) ||
            (typeof health === 'object' &&
                health !== null &&
                (String((health as Record<string, unknown>).status || '').toLowerCase() === 'healthy' ||
                    (health as Record<string, unknown>).ok === true))

        if (healthy) {
            systemStatus.value = 'online'
            const uptimeRaw =
                typeof health === 'object' && health !== null
                    ? Number((health as Record<string, any>).orchestrator?.uptime_seconds || 0)
                    : 0
            if (Number.isFinite(uptimeRaw) && uptimeRaw > 0) uptime.value = Math.round(uptimeRaw)
        } else {
            systemStatus.value = 'offline'
        }

        if (Array.isArray(logs)) systemLogs.value = logs
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
        <header class="topbar fade-in">
            <div class="topbar-brand">
                <span class="brand-icon">&#9670;</span>
                <span class="brand-name">SAPPHIRE</span>
            </div>

            <nav class="nav-group">
                <RouterLink
                    v-for="item in navItems"
                    :key="item.to"
                    :to="item.to"
                    class="nav-link"
                    active-class="active"
                >
                    <component :is="item.icon" :size="15" />
                    <span>{{ item.label }}</span>
                </RouterLink>
            </nav>

            <div class="topbar-right">
                <span class="topbar-meta">{{ formatUtcClock() }} UTC</span>
                <span class="topbar-meta hide-mobile">{{ formatUptime(uptime) }}</span>
                <span class="status-pill" :class="systemStatus">
                    <span class="status-dot"></span>
                    <span class="hide-mobile">{{ statusText }}</span>
                </span>
            </div>
        </header>

        <main class="main-panel">
            <section class="content">
                <RouterView v-slot="{ Component }">
                    <Transition name="view-fade" mode="out-in">
                        <component :is="Component" />
                    </Transition>
                </RouterView>
            </section>

            <section class="terminal-panel fade-in stagger-2">
                <TerminalLog
                    :logs="systemLogs"
                    :collapsed="terminalCollapsed"
                    @toggle="terminalCollapsed = !terminalCollapsed"
                />
            </section>
        </main>
    </div>
</template>

<style scoped>
.layout-shell {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    width: 100%;
}

/* ── Top Bar ── */
.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    padding: 0.5rem 1.2rem;
    border-bottom: 1px solid var(--border-subtle);
    background: rgba(5, 10, 5, 0.7);
    backdrop-filter: blur(8px);
    position: sticky;
    top: 0;
    z-index: 100;
}

.topbar-brand {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
}

.brand-icon {
    font-size: 1.3rem;
    color: var(--color-terminal);
    text-shadow: 0 0 10px rgba(32, 194, 14, 0.6);
    line-height: 1;
}

.brand-name {
    font-family: var(--font-mono);
    font-size: 0.88rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: var(--text-primary);
    text-shadow: 0 0 8px rgba(32, 194, 14, 0.4);
}

/* ── Navigation Tabs ── */
.nav-group {
    display: flex;
    align-items: center;
    gap: 0.25rem;
}

.nav-link {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.45rem 0.75rem;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.82rem;
    font-family: var(--font-mono);
    letter-spacing: 0.04em;
    border: 1px solid transparent;
    transition: all 0.15s ease;
    white-space: nowrap;
}

.nav-link:hover {
    color: var(--text-primary);
    border-color: var(--border-subtle);
    background: rgba(32, 194, 14, 0.03);
}

.nav-link.active {
    border-color: var(--border-accent);
    color: var(--color-terminal);
    background: rgba(32, 194, 14, 0.08);
    text-shadow: 0 0 8px rgba(32, 194, 14, 0.3);
}

/* ── Right Meta ── */
.topbar-right {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    flex-shrink: 0;
}

.topbar-meta {
    font-size: 0.7rem;
    color: var(--text-tertiary);
    letter-spacing: 0.04em;
    font-family: var(--font-mono);
}

.status-pill {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.68rem;
    font-family: var(--font-mono);
    letter-spacing: 0.06em;
    color: var(--text-secondary);
    border: 1px solid var(--border-subtle);
    border-radius: 999px;
    padding: 0.2rem 0.55rem;
}

.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
}

.status-pill.online .status-dot {
    background: var(--color-terminal);
    box-shadow: 0 0 6px rgba(32, 194, 14, 0.6);
}

.status-pill.connecting .status-dot {
    background: var(--color-warning);
    box-shadow: 0 0 6px rgba(255, 176, 0, 0.5);
}

.status-pill.offline .status-dot {
    background: var(--color-error);
    box-shadow: 0 0 6px rgba(255, 68, 68, 0.5);
}

.status-pill.online { border-color: rgba(32, 194, 14, 0.25); color: var(--color-terminal); }
.status-pill.connecting { border-color: rgba(255, 176, 0, 0.25); color: var(--color-warning); }
.status-pill.offline { border-color: rgba(255, 68, 68, 0.25); color: var(--color-error); }

/* ── Main Content ── */
.main-panel {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    padding: 0.8rem 1.2rem;
}

.content {
    flex: 1;
    overflow: auto;
}

.terminal-panel {
    margin-top: 0.8rem;
}

/* ── View Transitions ── */
.view-fade-enter-active,
.view-fade-leave-active {
    transition: opacity 0.2s ease, transform 0.2s ease;
}

.view-fade-enter-from,
.view-fade-leave-to {
    opacity: 0;
    transform: translateY(4px);
}

/* ── Responsive ── */
@media (max-width: 640px) {
    .topbar {
        padding: 0.4rem 0.6rem;
        gap: 0.4rem;
    }
    .brand-name { display: none; }
    .brand-icon { font-size: 1.1rem; }
    .nav-link {
        padding: 0.4rem 0.55rem;
        font-size: 0.75rem;
        gap: 0.3rem;
    }
    .main-panel { padding: 0.5rem 0.6rem; }
    .hide-mobile { display: none; }
}

@media (max-width: 400px) {
    .nav-link span { display: none; }
    .nav-link { padding: 0.4rem 0.5rem; }
    .topbar-meta { font-size: 0.62rem; }
}
</style>

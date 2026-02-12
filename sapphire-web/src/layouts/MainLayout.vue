<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { BookOpenText, LineChart, Radar, ShieldCheck } from 'lucide-vue-next'
import { fetchHealth } from '../api/client'

const route = useRoute()
const systemStatus = ref<'online' | 'offline' | 'connecting'>('connecting')
const uptime = ref(0)
let healthTimer: ReturnType<typeof setInterval> | null = null

const navItems = [
    { to: '/sapphirebook', label: 'SapphireBook', icon: BookOpenText },
    { to: '/sapphiretrade', label: 'SapphireTrade', icon: LineChart },
    { to: '/sapphirealpha', label: 'Sapphire Alpha', icon: Radar },
]

const activeLabel = computed(() => {
    const active = navItems.find((item) => route.path.startsWith(item.to))
    return active?.label ?? 'SapphireBook'
})

const formatUptime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

const checkHealth = async () => {
    try {
        const health = await fetchHealth()
        if (health?.status === 'healthy') {
            systemStatus.value = 'online'
            uptime.value = Math.round(health.orchestrator?.uptime_seconds || 0)
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
})

onUnmounted(() => {
    if (healthTimer) clearInterval(healthTimer)
})
</script>

<template>
    <div class="layout-shell">
        <aside class="sidebar">
            <div class="brand">
                <div class="brand-mark">
                    <ShieldCheck :size="20" />
                </div>
                <div>
                    <h1 class="font-mono">SAPPHIRE INC</h1>
                    <p class="brand-subtitle">Focused Autonomous Stack</p>
                </div>
            </div>

            <nav class="nav-group">
                <RouterLink
                    v-for="item in navItems"
                    :key="item.to"
                    :to="item.to"
                    class="nav-link"
                    active-class="active"
                >
                    <component :is="item.icon" :size="16" />
                    <span>{{ item.label }}</span>
                </RouterLink>
            </nav>

            <div class="security-note">
                <p class="font-mono">CONTROL CHANNEL</p>
                <span>Telegram heartbeat only</span>
                <small>Web command entry is disabled</small>
            </div>
        </aside>

        <main class="main-panel">
            <header class="topbar">
                <div class="surface-title">
                    <span class="font-mono">{{ activeLabel }}</span>
                </div>
                <div class="status-cluster">
                    <span class="status-pill" :class="systemStatus">
                        {{ systemStatus === 'online' ? 'SYSTEM ONLINE' : systemStatus === 'connecting' ? 'CONNECTING' : 'OFFLINE' }}
                    </span>
                    <span class="uptime font-mono">{{ formatUptime(uptime) }}</span>
                </div>
            </header>

            <section class="telegram-banner">
                <strong>Secure operations policy:</strong>
                agent prompts, approvals, and steering run via your authenticated Telegram heartbeat channel only.
            </section>

            <section class="content">
                <RouterView />
            </section>
        </main>
    </div>
</template>

<style scoped>
.layout-shell {
    display: grid;
    grid-template-columns: minmax(220px, 260px) 1fr;
    height: 100vh;
    width: 100vw;
    background: var(--bg-app);
}

.sidebar {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    padding: 1.25rem;
    border-right: 1px solid var(--border-subtle);
    background: rgba(6, 11, 22, 0.88);
    backdrop-filter: blur(12px);
}

.brand {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border-subtle);
}

.brand-mark {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    background: linear-gradient(135deg, #38bdf8 0%, #14b8a6 100%);
    color: #03111d;
    display: grid;
    place-items: center;
}

.brand h1 {
    margin: 0;
    font-size: 0.95rem;
    letter-spacing: 0.04em;
}

.brand-subtitle {
    margin: 0.15rem 0 0;
    color: var(--text-secondary);
    font-size: 0.72rem;
}

.nav-group {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
}

.nav-link {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.55rem 0.65rem;
    border-radius: 10px;
    color: var(--text-secondary);
    text-decoration: none;
    transition: background var(--transition-fast), color var(--transition-fast);
}

.nav-link:hover {
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
}

.nav-link.active {
    background: rgba(56, 189, 248, 0.18);
    color: #67e8f9;
}

.security-note {
    margin-top: auto;
    padding: 0.85rem;
    border-radius: 10px;
    border: 1px solid rgba(56, 189, 248, 0.35);
    background: rgba(8, 20, 36, 0.8);
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}

.security-note p {
    margin: 0;
    color: #67e8f9;
    font-size: 0.65rem;
    letter-spacing: 0.06em;
}

.security-note span {
    font-size: 0.78rem;
    color: var(--text-primary);
}

.security-note small {
    color: var(--text-secondary);
}

.main-panel {
    display: flex;
    flex-direction: column;
    min-width: 0;
}

.topbar {
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1rem 0 1.25rem;
    border-bottom: 1px solid var(--border-subtle);
    background: rgba(7, 13, 24, 0.82);
}

.surface-title {
    color: #cbd5e1;
    letter-spacing: 0.06em;
}

.status-cluster {
    display: flex;
    align-items: center;
    gap: 0.6rem;
}

.status-pill {
    padding: 0.2rem 0.5rem;
    border-radius: 999px;
    font-size: 0.64rem;
    letter-spacing: 0.04em;
}

.status-pill.online {
    color: #10b981;
    background: rgba(16, 185, 129, 0.15);
}

.status-pill.connecting {
    color: #f59e0b;
    background: rgba(245, 158, 11, 0.2);
}

.status-pill.offline {
    color: #f87171;
    background: rgba(248, 113, 113, 0.18);
}

.uptime {
    font-size: 0.7rem;
    color: var(--text-secondary);
}

.telegram-banner {
    margin: 1rem 1rem 0;
    padding: 0.75rem 0.9rem;
    border: 1px solid rgba(20, 184, 166, 0.4);
    background: rgba(10, 31, 33, 0.72);
    color: #99f6e4;
    border-radius: 10px;
    font-size: 0.86rem;
}

.telegram-banner strong {
    margin-right: 0.3rem;
}

.content {
    flex: 1;
    overflow: auto;
    padding: 1rem;
}

@media (max-width: 980px) {
    .layout-shell {
        grid-template-columns: 1fr;
    }

    .sidebar {
        border-right: none;
        border-bottom: 1px solid var(--border-subtle);
    }

    .nav-group {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .security-note {
        margin-top: 0;
    }
}
</style>

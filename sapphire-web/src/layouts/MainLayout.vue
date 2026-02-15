<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { BookOpenText, LineChart, Radar, Eye, Users } from 'lucide-vue-next'
import { fetchHealth, fetchSystemLogs, type SystemLogEntry } from '../api/client'
import { SyncBadge } from '../components/shared/index'
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
    { to: '/agents', label: 'Agents', icon: Users },
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
    <div class="flex min-h-screen w-full flex-col">
        <a href="#main-content" class="skip-link">Skip to content</a>

        <!-- Top Bar -->
        <header
            class="fade-in sticky top-0 z-100 flex items-center justify-between gap-2.5 border-b border-border-subtle bg-[rgba(5,10,5,0.7)] px-5 py-2 backdrop-blur-lg"
            role="banner"
        >
            <!-- Brand -->
            <div class="flex shrink-0 items-center gap-2">
                <span class="text-xl leading-none text-terminal glow-strong" aria-hidden="true">&#9670;</span>
                <h1 class="m-0 font-mono text-sm font-bold tracking-[0.12em] text-text-primary glow">
                    SAPPHIRE
                </h1>
            </div>

            <!-- Navigation -->
            <nav class="flex items-center gap-1" aria-label="Main navigation">
                <RouterLink
                    v-for="item in navItems"
                    :key="item.to"
                    :to="item.to"
                    class="flex items-center gap-1.5 whitespace-nowrap rounded-sm border border-transparent px-3 py-2 font-mono text-sm tracking-wide text-text-secondary no-underline transition-all duration-150 hover:border-border-subtle hover:bg-terminal-ghost/30 hover:text-text-primary"
                    active-class="!border-border-accent !text-terminal !bg-terminal-ghost/80 glow"
                    :aria-current="route.path.startsWith(item.to) ? 'page' : undefined"
                >
                    <component :is="item.icon" :size="15" aria-hidden="true" />
                    <span class="max-[400px]:hidden">{{ item.label }}</span>
                </RouterLink>
            </nav>

            <!-- Right Meta -->
            <div class="flex shrink-0 items-center gap-3">
                <span class="font-mono text-[0.7rem] tracking-wide text-text-tertiary" aria-label="Current UTC time">
                    {{ formatUtcClock() }} UTC
                </span>
                <span class="hidden font-mono text-[0.7rem] tracking-wide text-text-tertiary sm:inline" aria-label="System uptime">
                    {{ formatUptime(uptime) }}
                </span>
                <SyncBadge
                    :text="statusText"
                    :variant="systemStatus === 'online' ? 'success' : systemStatus === 'connecting' ? 'warning' : 'error'"
                    :pulse="true"
                />
            </div>
        </header>

        <!-- Main Content -->
        <main class="flex flex-1 flex-col px-5 py-3" id="main-content">
            <section class="flex-1 overflow-auto" :aria-label="`${activeLabel} dashboard view`">
                <RouterView v-slot="{ Component }">
                    <Transition name="view-fade" mode="out-in">
                        <component :is="Component" />
                    </Transition>
                </RouterView>
            </section>

            <section class="mt-3 fade-in stagger-2" aria-label="System terminal log">
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

/* ── Responsive: very small screens ── */
@media (max-width: 640px) {
    header[role="banner"] {
        padding: 0.4rem 0.6rem;
        gap: 0.4rem;
    }
}
</style>

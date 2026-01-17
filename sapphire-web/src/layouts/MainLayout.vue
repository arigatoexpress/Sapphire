<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { LayoutDashboard, Terminal, Bot, Settings, Activity, Zap, Database } from 'lucide-vue-next'
import { RouterLink, RouterView } from 'vue-router'
import { fetchHealth } from '../api/client'

const systemStatus = ref<'online' | 'offline' | 'connecting'>('connecting')
const orchestratorRunning = ref(false)
const uptime = ref(0)

const checkHealth = async () => {
    try {
        const health = await fetchHealth()
        if (health && health.status === 'healthy') {
            systemStatus.value = 'online'
            orchestratorRunning.value = health.orchestrator?.running || false
            uptime.value = Math.round(health.orchestrator?.uptime_seconds || 0)
        } else {
            systemStatus.value = 'offline'
        }
    } catch {
        systemStatus.value = 'offline'
    }
}

onMounted(() => {
    checkHealth()
    setInterval(checkHealth, 10000)
})

const formatUptime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}
</script>

<template>
    <div class="app-container">
        <nav class="sidebar">
            <div class="logo-section">
                <div class="logo-mark">
                    <Zap :size="22" class="logo-icon" />
                </div>
                <div class="logo-text">
                    <h1 class="font-mono">SAPPHIRE</h1>
                    <span class="version">Claude V1.0</span>
                </div>
            </div>

            <div class="nav-section">
                <span class="nav-label font-mono">MAIN</span>
                <div class="nav-links">
                    <RouterLink to="/" class="nav-item" active-class="active">
                        <LayoutDashboard :size="18" />
                        <span>Dashboard</span>
                    </RouterLink>
                    <RouterLink to="/terminal" class="nav-item" active-class="active">
                        <Terminal :size="18" />
                        <span>Terminal</span>
                    </RouterLink>
                    <RouterLink to="/agents" class="nav-item" active-class="active">
                        <Bot :size="18" />
                        <span>AI Swarm</span>
                    </RouterLink>
                    <RouterLink to="/analytics" class="nav-item" active-class="active">
                        <Activity :size="18" />
                        <span>Analytics</span>
                    </RouterLink>
                </div>
            </div>

            <div class="nav-section">
                <span class="nav-label font-mono">SYSTEM</span>
                <div class="nav-links">
                    <RouterLink to="/memory" class="nav-item" active-class="active">
                        <Database :size="18" />
                        <span>Memory</span>
                    </RouterLink>
                    <RouterLink to="/settings" class="nav-item" active-class="active">
                        <Settings :size="18" />
                        <span>Settings</span>
                    </RouterLink>
                </div>
            </div>

            <div class="sidebar-footer">
                <div class="platform-status">
                    <div class="platform-item">
                        <span class="platform-dot hyperliquid"></span>
                        <span class="font-mono">HL</span>
                    </div>
                    <div class="platform-item">
                        <span class="platform-dot drift"></span>
                        <span class="font-mono">DRIFT</span>
                    </div>
                    <div class="platform-item">
                        <span class="platform-dot aster"></span>
                        <span class="font-mono">ASTER</span>
                    </div>
                    <div class="platform-item">
                        <span class="platform-dot symphony"></span>
                        <span class="font-mono">SYM</span>
                    </div>
                </div>
            </div>
        </nav>

        <main class="main-content">
            <header class="top-bar">
                <div class="status-group">
                    <div class="status-indicator" :class="systemStatus">
                        <div class="indicator-dot"></div>
                        <span class="font-mono status-text">
                            {{ systemStatus === 'online' ? 'SYSTEM ONLINE' : systemStatus === 'connecting' ? 'CONNECTING...' : 'OFFLINE' }}
                        </span>
                    </div>
                    <div v-if="systemStatus === 'online'" class="uptime font-mono">
                        ⏱ {{ formatUptime(uptime) }}
                    </div>
                </div>

                <div class="header-right">
                    <div class="orchestrator-status font-mono" v-if="orchestratorRunning">
                        <span class="pulse-dot"></span>
                        TRADING ACTIVE
                    </div>
                    <button class="btn-connect font-mono">
                        <Zap :size="14" />
                        CONNECT WALLET
                    </button>
                </div>
            </header>

            <div class="content-area">
                <RouterView />
            </div>
        </main>
    </div>
</template>

<style scoped>
.app-container {
    display: flex;
    height: 100vh;
    width: 100vw;
    background: var(--bg-app);
}

/* Sidebar */
.sidebar {
    width: var(--sidebar-width);
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--glass-bg);
    border-right: 1px solid var(--border-subtle);
    padding: 1.25rem;
}

.logo-section {
    display: flex;
    align-items: center;
    gap: 0.875rem;
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border-subtle);
}

.logo-mark {
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, var(--color-brand) 0%, var(--color-purple) 100%);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 20px rgba(0, 212, 255, 0.3);
}

.logo-icon {
    color: #000;
}

.logo-text h1 {
    font-size: 1.125rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #fff 30%, var(--color-brand) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.version {
    font-size: 0.625rem;
    color: var(--text-tertiary);
    font-family: var(--font-mono);
    letter-spacing: 0.03em;
}

.nav-section {
    margin-bottom: 1.5rem;
}

.nav-label {
    font-size: 0.625rem;
    color: var(--text-tertiary);
    letter-spacing: 0.1em;
    margin-bottom: 0.75rem;
    display: block;
    padding-left: 0.5rem;
}

.nav-links {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.625rem 0.75rem;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    text-decoration: none;
    transition: all var(--transition-fast);
    font-size: 0.875rem;
    font-weight: 500;
}

.nav-item:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
}

.nav-item.active {
    background: var(--color-brand-dim);
    color: var(--color-brand);
}

.sidebar-footer {
    margin-top: auto;
    padding-top: 1rem;
    border-top: 1px solid var(--border-subtle);
}

.platform-status {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
}

.platform-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.5625rem;
    color: var(--text-tertiary);
}

.platform-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
}

.platform-dot.hyperliquid { background: var(--platform-hyperliquid); box-shadow: 0 0 8px var(--platform-hyperliquid); }
.platform-dot.drift { background: var(--platform-drift); box-shadow: 0 0 8px var(--platform-drift); }
.platform-dot.aster { background: var(--platform-aster); box-shadow: 0 0 8px var(--platform-aster); }
.platform-dot.symphony { background: var(--platform-symphony); box-shadow: 0 0 8px var(--platform-symphony); }

/* Main Content */
.main-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.top-bar {
    height: var(--header-height);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1.5rem;
    background: var(--glass-bg);
    border-bottom: 1px solid var(--border-subtle);
}

.status-group {
    display: flex;
    align-items: center;
    gap: 1.5rem;
}

.status-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.75rem;
    border-radius: 20px;
    font-size: 0.6875rem;
}

.status-indicator.online {
    background: var(--color-success-dim);
    color: var(--color-success);
}

.status-indicator.connecting {
    background: var(--color-warning-dim);
    color: var(--color-warning);
}

.status-indicator.offline {
    background: var(--color-error-dim);
    color: var(--color-error);
}

.indicator-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 8px currentColor;
    animation: pulse-glow 2s infinite;
}

.uptime {
    font-size: 0.6875rem;
    color: var(--text-tertiary);
}

.header-right {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.orchestrator-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.6875rem;
    color: var(--color-success);
    padding: 0.375rem 0.75rem;
    background: var(--color-success-dim);
    border-radius: 20px;
}

.pulse-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--color-success);
    animation: pulse-glow 1.5s infinite;
}

.btn-connect {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    padding: 0.5rem 1rem;
    border-radius: var(--radius-sm);
    font-size: 0.6875rem;
    cursor: pointer;
    transition: all var(--transition-fast);
}

.btn-connect:hover {
    background: rgba(255, 255, 255, 0.1);
    border-color: var(--color-brand);
    color: var(--color-brand);
}

.content-area {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
}

@keyframes pulse-glow {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
</style>

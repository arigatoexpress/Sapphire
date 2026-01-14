<script setup lang="ts">
import { LayoutDashboard, Terminal, Bot, Settings, Activity } from 'lucide-vue-next'
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="app-container">
    <nav class="sidebar glass">
      <div class="logo">
        <h1 class="font-mono text-gradient">SAPPHIRE</h1>
        <span class="version font-mono">v2.2.8</span>
      </div>

      <div class="nav-links">
        <RouterLink to="/" class="nav-item" active-class="active">
          <LayoutDashboard :size="20" />
          <span>Dashboard</span>
        </RouterLink>
        <RouterLink to="/terminal" class="nav-item">
          <Terminal :size="20" />
          <span>Terminal</span>
        </RouterLink>
        <RouterLink to="/agents" class="nav-item">
          <Bot :size="20" />
          <span>Swarm</span>
        </RouterLink>
        <RouterLink to="/analytics" class="nav-item">
          <Activity :size="20" />
          <span>Analytics</span>
        </RouterLink>
      </div>

      <div class="bottom-links">
        <RouterLink to="/settings" class="nav-item">
          <Settings :size="20" />
          <span>Settings</span>
        </RouterLink>
      </div>
    </nav>

    <main class="main-content">
      <header class="top-bar glass">
        <div class="status-indicator">
          <div class="indicator pulse"></div>
          <span class="font-mono">SYSTEM ONLINE</span>
        </div>
        <div class="wallet-connect">
          <!-- TODO: Wallet Connect -->
          <button class="btn-connect font-mono">CONNECT WALLET</button>
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

.sidebar {
  width: var(--sidebar-width);
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 1.5rem;
  border-right: var(--glass-border);
  z-index: 10;
}

.logo {
  margin-bottom: 2.5rem;
}

.logo h1 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
  letter-spacing: -0.05em;
}

.version {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.nav-links {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  text-decoration: none;
  transition: all 0.2s ease;
  font-weight: 500;
  border: 1px solid transparent;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: rgba(0, 240, 255, 0.1);
  color: var(--color-brand);
  border: 1px solid rgba(0, 240, 255, 0.2);
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.1);
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.top-bar {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2rem;
  border-bottom: var(--glass-border);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.75rem;
  color: var(--color-success);
}

.indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 10px var(--color-success);
}

.pulse {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.btn-connect {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
  padding: 0.5rem 1rem;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-connect:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.3);
}

.content-area {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
}
</style>

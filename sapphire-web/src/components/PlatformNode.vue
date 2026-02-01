<template>
  <div class="platform-node" :class="`platform-${platform.status}`">
    <div class="platform-icon">
      <span v-if="platform.status === 'trading'">⚡</span>
      <span v-else-if="platform.status === 'online'">🟢</span>
      <span v-else>⚪</span>
    </div>
    <div class="platform-info">
      <div class="platform-name">{{ platform.name }}</div>
      <div class="platform-stats">
        <span class="stat">{{ platform.trades }} trades</span>
        <span class="stat">${{ platform.volume.toFixed(2) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  platform: {
    id: string
    name: string
    status: 'online' | 'offline' | 'trading' | 'error'
    trades: number
    volume: number
  }
}>()
</script>

<style scoped>
.platform-node {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(0, 247, 255, 0.2);
  border-radius: 8px;
  transition: all 0.3s ease;
}

.platform-node:hover {
  background: rgba(0, 247, 255, 0.05);
  border-color: rgba(0, 247, 255, 0.5);
  transform: scale(1.05);
}

.platform-trading {
  border-color: rgba(0, 255, 136, 0.6);
  box-shadow: 0 0 20px rgba(0, 255, 136, 0.3);
  animation: trading-pulse 1.5s ease-in-out infinite;
}

@keyframes trading-pulse {
  0%, 100% { box-shadow: 0 0 10px rgba(0, 255, 136, 0.3); }
  50% { box-shadow: 0 0 30px rgba(0, 255, 136, 0.6); }
}

.platform-offline {
  opacity: 0.5;
}

.platform-icon {
  font-size: 1.5rem;
}

.platform-info {
  flex: 1;
}

.platform-name {
  color: #00f7ff;
  font-weight: 700;
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
}

.platform-stats {
  display: flex;
  gap: 1rem;
}

.stat {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.6);
}
</style>

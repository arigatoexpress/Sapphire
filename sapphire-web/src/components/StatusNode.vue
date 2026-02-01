<template>
  <div class="status-node" :class="`status-${component.status}`">
    <div class="node-header">
      <span class="status-indicator"></span>
      <span class="node-name">{{ component.name }}</span>
    </div>
    <div class="health-bar">
      <div class="health-fill" :style="{ width: component.health + '%' }"></div>
    </div>
    <div class="node-stats">
      <span class="health-text">{{ component.health }}%</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  component: {
    id: string
    name: string
    status: 'online' | 'offline' | 'degraded' | 'error'
    health: number
  }
}>()
</script>

<style scoped>
.status-node {
  padding: 1rem;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(0, 247, 255, 0.2);
  border-radius: 8px;
  transition: all 0.3s ease;
}

.status-node:hover {
  background: rgba(0, 247, 255, 0.05);
  border-color: rgba(0, 247, 255, 0.5);
  transform: translateY(-2px);
}

.status-node.status-online {
  border-left: 3px solid #00ff88;
}

.status-node.status-degraded {
  border-left: 3px solid #ffbb00;
}

.status-node.status-error {
  border-left: 3px solid #ff4444;
}

.status-node.status-offline {
  border-left: 3px solid #666;
  opacity: 0.6;
}

.node-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #666;
}

.status-online .status-indicator {
  background: #00ff88;
  box-shadow: 0 0 10px #00ff88;
  animation: pulse-dot 2s ease-in-out infinite;
}

.status-degraded .status-indicator {
  background: #ffbb00;
  box-shadow: 0 0 10px #ffbb00;
}

.status-error .status-indicator {
  background: #ff4444;
  box-shadow: 0 0 10px #ff4444;
  animation: pulse-dot 0.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.node-name {
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.85rem;
  font-weight: 600;
}

.health-bar {
  height: 6px;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.health-fill {
  height: 100%;
  background: linear-gradient(90deg, #00ff88 0%, #00f7ff 100%);
  transition: width 0.5s ease;
  box-shadow: 0 0 10px rgba(0, 255, 136, 0.5);
}

.node-stats {
  display: flex;
  justify-content: flex-end;
}

.health-text {
  font-size: 0.75rem;
  color: #00ff88;
  font-weight: 700;
}
</style>

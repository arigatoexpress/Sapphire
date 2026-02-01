<template>
  <div class="data-feed" :class="`feed-${feed.status}`">
    <div class="feed-header">
      <span class="feed-indicator"></span>
      <span class="feed-name">{{ feed.name }}</span>
    </div>
    <div class="feed-metrics">
      <div class="metric">
        <span class="metric-label">Latency</span>
        <span class="metric-value">{{ feed.latency }}ms</span>
      </div>
      <div class="metric">
        <span class="metric-label">Rate</span>
        <span class="metric-value">{{ feed.rate }}/min</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  feed: {
    id: string
    name: string
    status: 'active' | 'degraded' | 'offline'
    latency: number
    rate: number
  }
}>()
</script>

<style scoped>
.data-feed {
  padding: 0.75rem 1rem;
  background: rgba(0, 0, 0, 0.3);
  border-left: 3px solid rgba(0, 247, 255, 0.3);
  border-radius: 6px;
  transition: all 0.3s ease;
}

.data-feed:hover {
  background: rgba(0, 247, 255, 0.05);
  border-left-color: rgba(0, 247, 255, 0.8);
}

.feed-active {
  border-left-color: #00ff88;
}

.feed-degraded {
  border-left-color: #ffbb00;
}

.feed-offline {
  border-left-color: #ff4444;
  opacity: 0.5;
}

.feed-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.feed-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #666;
}

.feed-active .feed-indicator {
  background: #00ff88;
  box-shadow: 0 0 8px #00ff88;
  animation: blink 1s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.feed-degraded .feed-indicator {
  background: #ffbb00;
  box-shadow: 0 0 8px #ffbb00;
}

.feed-offline .feed-indicator {
  background: #ff4444;
}

.feed-name {
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.85rem;
  font-weight: 600;
}

.feed-metrics {
  display: flex;
  gap: 1.5rem;
  margin-left: 1.25rem;
}

.metric {
  display: flex;
  flex-direction: column;
}

.metric-label {
  font-size: 0.65rem;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.metric-value {
  font-size: 0.75rem;
  color: #00f7ff;
  font-weight: 700;
}
</style>

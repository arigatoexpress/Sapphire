<script setup lang="ts">
defineProps<{
  loading: boolean
  hasData: boolean
  fetchError: string | null
  isStale: boolean
  dataAge: number | null
  loadingMessage?: string
}>()

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div
    v-if="loading && !hasData"
    class="flex items-center justify-center gap-2 rounded-sm border border-terminal-ghost bg-terminal-ghost/80 px-3 py-2 font-mono text-xs tracking-wide text-terminal"
    role="status"
    aria-live="polite"
  >
    <span class="inline-block h-1.5 w-1.5 rounded-full bg-terminal animate-pulse" aria-hidden="true" />
    {{ loadingMessage ?? 'CONNECTING TO SAPPHIRE NETWORK …' }}
  </div>

  <div
    v-else-if="fetchError"
    class="cursor-pointer rounded-sm border border-error/20 bg-error/8 px-3 py-2 text-center font-mono text-xs tracking-wide text-error transition-colors hover:bg-error/12"
    role="alert"
    tabindex="0"
    @click="emit('retry')"
    @keydown.enter="emit('retry')"
  >
    {{ fetchError }} — tap to retry
  </div>

  <div
    v-else-if="isStale"
    class="rounded-sm border border-warning/15 bg-warning/6 px-3 py-2 text-center font-mono text-xs tracking-wide text-warning"
    role="status"
    aria-live="polite"
  >
    Data {{ dataAge }}s old — awaiting refresh
  </div>
</template>

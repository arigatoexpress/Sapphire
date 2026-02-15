<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '../../lib/utils'

const props = defineProps<{
  value: number
  max: number
  label?: string
  tone?: 'default' | 'success' | 'warning' | 'error'
}>()

const percent = computed(() =>
  props.max > 0 ? Math.min(100, Math.round((props.value / props.max) * 100)) : 0
)

const autoTone = computed(() => {
  if (props.tone) return props.tone
  if (percent.value >= 80) return 'error'
  if (percent.value >= 50) return 'warning'
  return 'success'
})

const fillColor: Record<string, string> = {
  default: 'bg-terminal',
  success: 'bg-terminal',
  warning: 'bg-warning',
  error: 'bg-error',
}

const glowColor: Record<string, string> = {
  default: 'shadow-[0_0_8px_rgba(32,194,14,0.4)]',
  success: 'shadow-[0_0_8px_rgba(32,194,14,0.4)]',
  warning: 'shadow-[0_0_8px_rgba(255,176,0,0.4)]',
  error: 'shadow-[0_0_8px_rgba(255,68,68,0.4)]',
}
</script>

<template>
  <div :class="cn('grid gap-1.5', $attrs.class as string)">
    <div v-if="label" class="flex items-baseline justify-between">
      <span class="font-mono text-[0.62rem] uppercase tracking-wider text-text-tertiary">{{ label }}</span>
      <span class="font-mono text-xs tabular-nums text-text-secondary">{{ value }}/{{ max }}</span>
    </div>

    <div class="relative h-2 overflow-hidden rounded-full bg-terminal-ghost/50">
      <div
        :class="cn(
          'absolute inset-y-0 left-0 rounded-full transition-all duration-500 ease-out',
          fillColor[autoTone],
          glowColor[autoTone]
        )"
        :style="{ width: `${percent}%` }"
        role="progressbar"
        :aria-valuenow="value"
        :aria-valuemin="0"
        :aria-valuemax="max"
        :aria-label="label ?? 'gauge'"
      />
    </div>
  </div>
</template>

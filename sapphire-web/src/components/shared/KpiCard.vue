<script setup lang="ts">
import { cn } from '../../lib/utils'

defineProps<{
  label: string
  value: string | number
  tone?: 'default' | 'hot' | 'warm' | 'cold' | 'success' | 'error' | 'warning'
  glow?: boolean
  loading?: boolean
}>()

const toneClasses: Record<string, string> = {
  default: 'text-text-primary',
  hot: 'text-error',
  warm: 'text-warning',
  cold: 'text-info',
  success: 'text-terminal',
  error: 'text-error',
  warning: 'text-warning',
}
</script>

<template>
  <article
    :class="cn(
      'grid gap-0.5 rounded-md border border-border-subtle bg-card px-2 py-2.5 text-center backdrop-blur-sm glass-lift',
      $attrs.class as string
    )"
  >
    <span class="font-mono text-[0.62rem] uppercase tracking-wider text-text-tertiary">
      {{ label }}
    </span>

    <!-- Skeleton state -->
    <template v-if="loading">
      <span class="mx-auto h-5 w-1/2 animate-pulse rounded-xs bg-terminal-ghost" />
    </template>

    <!-- Value -->
    <strong
      v-else
      :class="cn(
        'font-mono text-lg leading-tight',
        toneClasses[tone ?? 'default'],
        glow && 'glow'
      )"
    >
      {{ value }}
    </strong>
  </article>
</template>

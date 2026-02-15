<script setup lang="ts">
import TradingChart from '../TradingChart.vue'
import { cn } from '../../lib/utils'

defineProps<{
  title: string
  subtitle?: string
  candles: Array<{ time: number; open: number; high: number; low: number; close: number; volume?: number }>
  height?: number
}>()
</script>

<template>
  <article
    :class="cn(
      'grid gap-3 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm glass-lift',
      $attrs.class as string
    )"
  >
    <header class="flex items-baseline justify-between">
      <h3 class="m-0 font-mono text-sm tracking-wide text-text-primary glow">{{ title }}</h3>
      <small v-if="subtitle" class="font-mono text-[0.72rem] text-text-tertiary">{{ subtitle }}</small>
    </header>
    <TradingChart :candles="candles" :height="height ?? 400" />
  </article>
</template>

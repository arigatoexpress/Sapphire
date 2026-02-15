<script setup lang="ts">
import { cn } from '../../lib/utils'

defineProps<{
  agent: 'obsidian' | 'emerald' | 'sapphire'
  size?: 'sm' | 'md' | 'lg'
}>()

const agentColors: Record<string, string> = {
  obsidian: 'bg-obsidian shadow-obsidian-glow',
  emerald: 'bg-emerald shadow-emerald-glow',
  sapphire: 'bg-sapphire-blue shadow-sapphire-glow',
}

const sizes: Record<string, string> = {
  sm: 'h-2 w-2',
  md: 'h-3 w-3',
  lg: 'h-4 w-4',
}
</script>

<template>
  <span
    :class="cn(
      'inline-block rounded-full',
      agentColors[agent],
      sizes[size ?? 'sm'],
      $attrs.class as string
    )"
    :aria-label="`${agent} agent`"
    role="img"
  />
</template>

<script setup lang="ts">
import { cn } from '../../lib/utils'
import { cva, type VariantProps } from 'class-variance-authority'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[0.62rem] uppercase tracking-wider transition-colors',
  {
    variants: {
      variant: {
        default: 'border-border-subtle text-text-tertiary',
        success: 'border-terminal-faint text-terminal',
        warning: 'border-warning/20 text-warning',
        error: 'border-error/20 text-error',
        info: 'border-info/20 text-info',
        obsidian: 'border-obsidian/30 text-obsidian',
        emerald: 'border-emerald/30 text-emerald',
        sapphire: 'border-sapphire-blue/30 text-sapphire-blue',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

type BadgeVariants = VariantProps<typeof badgeVariants>

defineProps<{
  text: string
  variant?: BadgeVariants['variant']
  pulse?: boolean
}>()
</script>

<template>
  <span :class="cn(badgeVariants({ variant }), $attrs.class as string)">
    <span
      v-if="pulse"
      class="inline-block h-1.5 w-1.5 rounded-full animate-pulse"
      :class="{
        'bg-terminal': variant === 'success' || !variant || variant === 'default',
        'bg-warning': variant === 'warning',
        'bg-error': variant === 'error',
        'bg-info': variant === 'info',
        'bg-obsidian': variant === 'obsidian',
        'bg-emerald': variant === 'emerald',
        'bg-sapphire-blue': variant === 'sapphire',
      }"
      aria-hidden="true"
    />
    {{ text }}
  </span>
</template>

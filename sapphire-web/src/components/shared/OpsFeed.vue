<script setup lang="ts">
import SectionHeader from './SectionHeader.vue'
import SyncBadge from './SyncBadge.vue'
import { ScrollArea } from '../ui/scroll-area/index'

export interface OpEntry {
  time: string
  level: 'info' | 'warning' | 'error'
  tag?: string
  message: string
  agent?: string
}

defineProps<{
  ops: OpEntry[]
  title?: string
  maxHeight?: string
  showAgent?: boolean
}>()

const levelBorder: Record<string, string> = {
  info: 'border-l-terminal/30',
  warning: 'border-l-warning/40',
  error: 'border-l-error/40',
}

const levelTag: Record<string, string> = {
  info: 'text-terminal',
  warning: 'text-warning',
  error: 'text-error',
}

const agentDot: Record<string, string> = {
  obsidian: 'bg-obsidian',
  emerald: 'bg-emerald',
  sapphire: 'bg-sapphire-blue',
}
</script>

<template>
  <section class="grid gap-2 rounded-md border border-border-subtle bg-card p-4 backdrop-blur-sm">
    <SectionHeader :title="title ?? 'RECENT OPERATIONS'">
      <template #actions>
        <SyncBadge :text="`${ops.length} events`" />
      </template>
    </SectionHeader>

    <ScrollArea :class="maxHeight ? `max-h-[${maxHeight}]` : 'max-h-[220px]'">
      <div class="grid gap-0.5">
        <article
          v-for="(op, i) in ops"
          :key="i"
          :class="[
            'grid items-baseline gap-1.5 rounded-xs border-l-2 px-2 py-1 font-mono text-[0.68rem] leading-snug transition-colors hover:bg-terminal-ghost/50',
            levelBorder[op.level] ?? levelBorder.info,
            showAgent ? 'grid-cols-[8px_58px_32px_1fr]' : 'grid-cols-[58px_32px_1fr]'
          ]"
        >
          <!-- Agent dot (optional) -->
          <span
            v-if="showAgent"
            :class="['inline-block h-2 w-2 rounded-full', agentDot[op.agent ?? ''] ?? 'bg-terminal']"
            aria-hidden="true"
          />

          <!-- Time -->
          <span class="text-text-muted tabular-nums">{{ op.time }}</span>

          <!-- Tag -->
          <span :class="['uppercase', levelTag[op.level] ?? levelTag.info]">
            {{ op.tag ?? op.level.charAt(0).toUpperCase() }}
          </span>

          <!-- Message -->
          <span class="truncate text-text-secondary">{{ op.message }}</span>
        </article>
      </div>
    </ScrollArea>
  </section>
</template>

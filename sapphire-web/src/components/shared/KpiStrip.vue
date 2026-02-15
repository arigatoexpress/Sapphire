<script setup lang="ts">
import { cn } from '../../lib/utils'

defineProps<{
  columns?: number
}>()
</script>

<template>
  <section
    :class="cn(
      'grid gap-2.5',
      $attrs.class as string
    )"
    :style="columns ? { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` } : undefined"
  >
    <slot />
  </section>
</template>

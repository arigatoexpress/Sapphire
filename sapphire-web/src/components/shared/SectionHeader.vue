<script setup lang="ts">
defineProps<{
  title?: string
}>()
</script>

<template>
  <header class="flex items-center justify-between gap-2">
    <h3 v-if="title" class="m-0 font-mono text-sm tracking-wide text-text-primary glow">
      {{ title }}
    </h3>
    <slot v-else name="title" />
    <div class="flex items-center gap-2">
      <slot name="actions" />
    </div>
  </header>
</template>

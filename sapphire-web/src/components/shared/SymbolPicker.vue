<script setup lang="ts">
const model = defineModel<string>({ required: true })

defineProps<{
  symbols: readonly string[]
  label?: string
}>()

const pickerId = `symbol-picker-${Math.random().toString(36).slice(2, 8)}`
</script>

<template>
  <label class="flex items-center gap-2" :for="pickerId">
    <span
      class="font-mono text-[0.72rem] uppercase tracking-widest text-text-tertiary"
    >
      {{ label ?? 'SYMBOL' }}
    </span>
    <select
      :id="pickerId"
      v-model="model"
      class="cursor-pointer rounded-sm border border-border-accent bg-card px-2.5 py-1.5 font-mono text-sm text-text-primary transition-colors hover:border-border-strong focus:border-terminal focus:outline-none focus:ring-1 focus:ring-terminal/30"
    >
      <option v-for="s in symbols" :key="s" :value="s">{{ s }}</option>
    </select>
  </label>
</template>

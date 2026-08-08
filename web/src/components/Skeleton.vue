<template>
  <div class="skeleton" :class="{ 'skeleton-card': card }" role="status" aria-label="Loading…">
    <div v-for="n in lines" :key="n" class="skeleton-line" :class="[width, height]"></div>
  </div>
</template>

<script setup>
defineProps({
  lines: { type: Number, default: 3 },
  /** w-1/4 | w-1/3 | w-1/2 | w-2/3 | w-full */
  width: { type: String, default: 'w-2/3' },
  /** h-4 | h-6 | h-8 */
  height: { type: String, default: 'h-4' },
  card: { type: Boolean, default: true },
})
</script>

<style scoped>
.skeleton { display: flex; flex-direction: column; gap: var(--space-3); }
</style>

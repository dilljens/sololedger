<template>
  <span class="tag" :class="`tag-${color}`"><slot /></span>
</template>

<script setup>
defineProps({
  /** green | red | blue | gray | yellow */
  color: { type: String, default: 'gray' },
})
</script>

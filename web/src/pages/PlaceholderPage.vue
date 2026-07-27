<template>
  <div class="page">
    <div class="page-header">
      <h1>{{ pageTitle }}</h1>
      <p>This page is coming soon in the new UI.</p>
    </div>
    <div class="card" style="padding: 40px; text-align: center;">
      <p style="font-size: 3rem; margin-bottom: 12px;">🚧</p>
      <p class="text-muted">Page being migrated from the classic UI.</p>
      <p class="text-muted text-sm" style="margin-top: 8px;">
        <a :href="`/app/#${route.path}`" target="_blank">Open classic version →</a>
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const pageTitle = computed(() => {
  const name = route.path.replace('/', '')
  return name.charAt(0).toUpperCase() + name.slice(1).replace(/-/g, ' ')
})
</script>

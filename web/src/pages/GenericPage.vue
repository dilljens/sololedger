<template>
  <div class="page">
    <div class="page-header">
      <h1>{{ icon }} {{ title }}</h1>
      <p class="text-muted">{{ description }}</p>
    </div>
    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>
    <div v-else-if="error" class="card error text-center" style="padding:40px;">
      <div style="font-size:2rem;margin-bottom:8px;">⚠️</div>
      <p>{{ error }}</p>
      <button class="btn btn-primary mt-3" @click="load">🔄 Retry</button>
    </div>
    <template v-else>
      <slot :data="data" :load="load">
        <div class="card">
          <pre class="json-display">{{ JSON.stringify(data, null, 2) }}</pre>
        </div>
      </slot>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { apiGet } from '../api.js'

const props = defineProps({
  apiEndpoint: { type: String, required: true },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  icon: { type: String, default: '📄' },
})

const loading = ref(true)
const error = ref('')
const data = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await apiGet(props.apiEndpoint)
  } catch (e) {
    error.value = e.message || 'Failed to load'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
<style scoped>
.json-display {
  font-size: 0.8rem; max-height: 500px; overflow: auto;
  background: var(--gray-50); padding: 16px; border-radius: 8px;
}
</style>

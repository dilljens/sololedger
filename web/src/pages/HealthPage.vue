<template>
  <div class="page">
    <div class="page-header">
      <h1>🔍 Ledger Health</h1>
      <p>Beancount validation and data integrity</p>
    </div>

    <div v-if="loading" class="card"><div class="loading"><div class="spinner"></div>Validating ledger...</div></div>

    <div v-else-if="data.valid" class="card">
      <div class="text-center" style="padding: 30px;">
        <div style="font-size: 3rem; margin-bottom: 12px;">✅</div>
        <h2 class="text-success">Ledger is clean</h2>
        <p class="text-muted">No errors found in your Beancount ledger.</p>
      </div>
      <table class="data-table">
        <tbody>
          <tr><td>Total accounts</td><td class="num">{{ accountCount }}</td></tr>
          <tr><td>Data format</td><td class="num">Plain-text Beancount</td></tr>
          <tr><td>Backup</td><td class="num">Git-versioned</td></tr>
        </tbody>
      </table>
    </div>

    <div v-else class="card">
      <div class="health-errors-banner">
        <strong class="text-error">⚠ {{ data.error_count }} error(s) found</strong>
        <p class="text-muted">Fix these issues to keep your ledger in balance.</p>
      </div>
      <div v-for="(e, i) in data.errors" :key="i" class="health-error">
        <strong>{{ e.message || 'Unknown error' }}</strong>
        <div v-if="e.file" class="text-muted text-sm">{{ e.file }}{{ e.line ? ':' + e.line : '' }}</div>
      </div>
      <button class="btn btn-outline btn-sm mt-3" @click="load">🔄 Re-check</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiGet } from '../api.js'

const loading = ref(true)
const data = ref({ valid: false, error_count: 0, errors: [] })

const accountCount = computed(() => Object.keys(data.value.balances || {}).length)

async function load() {
  loading.value = true
  try {
    const d = await apiGet('/check')
    data.value = { valid: true, error_count: 0, errors: [], balances: d.balances || {} }
  } catch (e) {
    data.value = { valid: false, error_count: 1, errors: [{ message: e.message }] }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.num { text-align: right; font-variant-numeric: tabular-nums; }
.health-errors-banner { background: #fff5f5; border: 1px solid #ffc9c9; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.health-error { background: #fff; border: 1px solid #ffe0e0; border-left: 3px solid #c92a2a; border-radius: 6px; padding: 12px; margin: 8px 0; font-size: 0.85rem; }
</style>

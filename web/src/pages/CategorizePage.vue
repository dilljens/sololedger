<template>
  <div class="page">
    <div class="page-header">
      <h1>🏷️ Categorize</h1>
      <p>Suggest a category for a merchant name</p>
    </div>

    <div class="card">
      <form @submit.prevent="lookup" class="categorize-form">
        <input
          v-model="merchant"
          class="form-input"
          placeholder="Enter merchant name (e.g. AMAZON)"
          :disabled="loading"
        />
        <button class="btn btn-primary" type="submit" :disabled="loading || !merchant">
          {{ loading ? '⏳ Suggesting...' : 'Suggest Category' }}
        </button>
      </form>

      <div v-if="error" class="card error mt-3">⚠ {{ error }}</div>

      <div v-if="result" class="mt-3">
        <div class="result-card" :class="result.account ? 'result-hit' : 'result-miss'">
          <div class="result-label">Merchant</div>
          <div class="result-value">{{ result.merchant || merchant }}</div>

          <div v-if="result.account" class="result-row">
            <span>Suggested account</span>
            <strong>{{ result.account }}</strong>
          </div>
          <div v-if="result.confidence != null" class="result-row">
            <span>Confidence</span>
            <strong>{{ (result.confidence * 100).toFixed(0) }}%</strong>
          </div>
          <div v-if="result.count != null" class="result-row">
            <span>Matches</span>
            <strong>{{ result.count }}</strong>
          </div>
          <div v-if="result.tier" class="result-row">
            <span>Matched by</span>
            <strong>{{ result.tier }}</strong>
          </div>

          <p v-if="!result.account" class="text-muted text-sm mt-2">
            No suggestion found for this merchant. It may need a categorization rule.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { apiGet } from '../api.js'

const merchant = ref('')
const loading = ref(false)
const error = ref('')
const result = ref(null)

async function lookup() {
  const q = merchant.value.trim()
  if (!q || loading.value) return
  loading.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await apiGet(`/categories/suggest?merchant=${encodeURIComponent(q)}`)
  } catch (e) {
    error.value = e.message || 'Failed to get suggestion'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.categorize-form { display: flex; gap: 8px; align-items: center; }
.categorize-form .form-input { flex: 1; }
.result-card {
  padding: 16px;
  border-radius: 8px;
  border: 1px solid var(--gray-200);
}
.result-hit { border-left: 4px solid var(--green-500); }
.result-miss { border-left: 4px solid var(--amber-400, #f59e0b); }
.result-label {
  font-size: 0.75rem;
  color: var(--gray-500);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.result-value { font-size: 1.1rem; font-weight: 600; margin-bottom: 8px; }
.result-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: 0.9rem;
}
</style>

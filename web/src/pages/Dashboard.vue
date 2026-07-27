<template>
  <div class="page">
    <div class="page-header">
      <h1>Dashboard</h1>
      <p v-if="entityLabel" class="text-muted">{{ entityLabel }}</p>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>

    <template v-else-if="error">
      <div class="card error">
        ⚠ {{ error }}
        <button class="btn btn-outline btn-sm" style="margin-left: 12px;" @click="fetchData">Retry</button>
      </div>
    </template>

    <template v-else>
      <!-- Attention items -->
      <div v-if="attentionItems.length" class="attention-list">
        <div
          v-for="item in attentionItems"
          :key="item.id"
          class="attention-item"
          :class="item.severity === 'critical' ? 'attention-critical' : 'attention-warning'"
        >
          <span v-if="item.severity === 'critical'">🔴</span>
          <span v-else>🟡</span>
          <span>{{ item.message }}</span>
        </div>
      </div>

      <!-- Stats cards -->
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">Cash</div>
          <div class="stat-value" :class="{ 'text-success': cash > 0 }">
            {{ fmt(cash) }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Revenue YTD</div>
          <div class="stat-value">{{ fmt(revenue) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Expenses</div>
          <div class="stat-value text-danger">{{ fmt(expenses) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Net Profit</div>
          <div class="stat-value" :class="netProfit >= 0 ? 'text-success' : 'text-danger'">
            {{ fmt(netProfit) }}
          </div>
        </div>
      </div>

      <!-- Tax summary -->
      <div v-if="tax" class="card">
        <h2>Estimated Tax</h2>
        <div class="tax-summary">
          <div class="tax-row">
            <span>Projected annual tax</span>
            <strong>{{ fmt(tax.annual_total_tax) }}</strong>
          </div>
          <div class="tax-row">
            <span>Already paid</span>
            <strong>{{ fmt(tax.already_paid) }}</strong>
          </div>
          <div class="tax-row" v-if="tax.suggested_payment">
            <span>Suggested next payment</span>
            <strong class="text-primary">{{ fmt(tax.suggested_payment) }}</strong>
          </div>
        </div>
        <p v-if="tax.note" class="text-muted text-sm mt-2">{{ tax.note }}</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiGet } from '../api.js'

const loading = ref(true)
const error = ref('')
const cash = ref(0)
const revenue = ref(0)
const expenses = ref(0)
const netProfit = ref(0)
const entityLabel = ref('')
const tax = ref(null)
const attentionItems = ref([])

function fmt(val) {
  if (val == null) return '$0.00'
  const num = typeof val === 'number' ? val : parseFloat(val)
  return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function fetchData() {
  loading.value = true
  error.value = ''
  try {
    const data = await apiGet('/dashboard')
    cash.value = data.cash || 0
    revenue.value = data.gross_revenue || 0
    expenses.value = data.total_expenses || 0
    netProfit.value = data.net_profit || 0
    entityLabel.value = data.entity_label || ''
    tax.value = data.tax || null
    attentionItems.value = data.deadlines || []
  } catch (err) {
    error.value = err.message || 'Failed to load dashboard'
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.tax-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tax-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
}

.attention-list {
  margin-bottom: 16px;
}

.attention-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 6px;
  font-size: 0.85rem;
}

.attention-critical {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.attention-warning {
  background: #fffbeb;
  color: #92400e;
  border: 1px solid #fde68a;
}
</style>

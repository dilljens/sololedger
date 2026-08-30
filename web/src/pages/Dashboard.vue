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
      <!-- Attention items — semantic tokens, no emoji-as-icon reliance -->
      <div v-if="attentionItems.length" class="attention-list">
        <div
          v-for="item in attentionItems"
          :key="item.id"
          class="attention-item"
          :class="item.severity === 'critical' ? 'attention-critical' : 'attention-warning'"
          role="alert"
        >
          <span class="attention-dot" :class="item.severity === 'critical' ? 'dot-red' : 'dot-yellow'" aria-hidden="true"></span>
          <span>{{ item.message }}</span>
        </div>
      </div>
      <div v-else-if="!loading && !error" class="empty-state" style="padding: var(--space-4) 0 var(--space-5);">
        <p class="text-sm text-muted">All clear — no urgent items.</p>
      </div>

      <!-- Stats cards — staggered entrance (fraunces h1 + mono values) -->
      <div class="stat-grid">
        <div class="stat-card" style="--i:0">
          <div class="stat-label">Cash</div>
          <div class="stat-value" :class="{ 'text-success': cash > 0 }">
            {{ fmt(cash) }}
          </div>
        </div>
        <div class="stat-card" style="--i:1">
          <div class="stat-label">Revenue YTD</div>
          <div class="stat-value">{{ fmt(revenue) }}</div>
        </div>
        <div class="stat-card" style="--i:2">
          <div class="stat-label">Expenses</div>
          <div class="stat-value text-danger">{{ fmt(expenses) }}</div>
        </div>
        <div class="stat-card" style="--i:3">
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

    // Attention items: prefer the dedicated /attention endpoint; fall back
    // to mapping the dashboard's deadline fields.
    const fallback = (data.deadlines || []).slice(0, 3).map(d => ({
      id: `deadline-${d.label || d.due}`,
      severity: d.status === 'overdue' ? 'critical' : 'warning',
      message: `${d.label || 'Deadline'} — due ${d.due} (${d.days_until} days)`,
    }))
    try {
      const att = await apiGet('/attention')
      const items = att.items || []
      attentionItems.value = items.length
        ? items.map(it => ({
            id: it.type,
            severity: it.severity === 'critical' ? 'critical' : 'warning',
            message: it.detail ? `${it.label}: ${it.detail}` : it.label,
          }))
        : fallback
    } catch {
      attentionItems.value = fallback
    }
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
.attention-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
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
  background: var(--danger-bg);
  color: var(--danger);
  border: 1px solid var(--danger-border);
}

.attention-warning {
  background: var(--warning-bg);
  color: var(--warning);
  border: 1px solid var(--warning-border);
}
</style>

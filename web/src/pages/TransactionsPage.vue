<template>
  <div class="page">
    <div class="page-header">
      <h1>Transactions</h1>
      <p>Ledger entries</p>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>
    <div v-else-if="error" class="card error">⚠ {{ error }}</div>

    <template v-else>
      <div class="card">
        <div class="stat-grid">
          <div class="stat-card" style="border: none; box-shadow: none;">
            <div class="stat-label">Revenue</div>
            <div class="stat-value">{{ fmt(d.gross_revenue) }}</div>
          </div>
          <div class="stat-card" style="border: none; box-shadow: none;">
            <div class="stat-label">Expenses</div>
            <div class="stat-value text-danger">{{ fmt(d.total_expenses) }}</div>
          </div>
          <div class="stat-card" style="border: none; box-shadow: none;">
            <div class="stat-label">Net</div>
            <div class="stat-value text-success">{{ fmt(d.net_profit) }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <h2>Recent Activity</h2>
        <div v-if="!txns.length" class="empty-state">No transactions found.</div>
        <DataTable v-else
          :columns="[
            { key: 'date', label: 'Date', type: 'date' },
            { key: 'payee', label: 'Payee' },
            { key: 'account', label: 'Account' },
            { key: 'amount', label: 'Amount', type: 'cents' },
          ]"
          :rows="txns"
        >
          <template #cell-account="{ value }"><Tag :color="tagColor(value)">{{ value }}</Tag></template>
        </DataTable>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiGet } from '../api.js'
import DataTable from '../components/DataTable.vue'
import Tag from '../components/Tag.vue'

const loading = ref(true)
const error = ref('')
const d = ref({})

const txns = computed(() =>
  (d.value.recent_transactions || []).slice(0, 15).map(t => ({
    date: t.date,
    payee: t.payee || t.description || '',
    account: t.account || '',
    amount: t.amount != null ? Math.round(Math.abs(t.amount) * 100) : 0,
  }))
)

function fmt(v) {
  if (v == null) return '$0.00'
  const n = Number(v) || 0
  return (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2 })
}
function tagColor(account = '') {
  if (account.startsWith('Income')) return 'green'
  if (account.startsWith('Expenses')) return 'red'
  if (account.startsWith('Assets')) return 'blue'
  return 'gray'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    d.value = await apiGet('/dashboard')
  } catch (e) {
    error.value = e.message || 'Failed to load transactions'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

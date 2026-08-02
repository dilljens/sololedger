<template>
  <div class="page">
    <div class="page-header">
      <h1>🔄 Reconciliation</h1>
      <p>Review and reconcile bank transactions against your ledger</p>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>

    <div v-else-if="error" class="card error text-center" style="padding: 30px;">
      <p>⚠ {{ error }}</p>
      <button class="btn btn-outline mt-2" @click="load">🔄 Retry</button>
    </div>

    <template v-else>
      <!-- Balance summary -->
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">Ledger Balance</div>
          <div class="stat-value">{{ fmt(data.ledger_balance) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Cleared Balance</div>
          <div class="stat-value">{{ fmt(data.cleared_balance) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Uncleared Items</div>
          <div class="stat-value">{{ data.uncleared_count }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Uncleared Total</div>
          <div class="stat-value text-danger">{{ fmt(data.uncleared_total) }}</div>
        </div>
      </div>

      <div class="text-muted text-sm mb-3">
        Balance as of {{ data.balance_date }} |
        <router-link to="/health">Run ledger check →</router-link>
      </div>

      <!-- Uncleared transactions -->
      <div class="card">
        <h2>Uncleared Transactions</h2>
        <p v-if="!data.uncleared?.length" class="text-muted">No uncleared transactions found.</p>
        <DataTable
          v-else
          :columns="[
            { key: 'date', label: 'Date', type: 'date' },
            { key: 'payee', label: 'Payee' },
            { key: 'description', label: 'Description' },
            { key: 'amount', label: 'Amount', type: 'cents' },
          ]"
          :rows="data.uncleared.map(t => ({
            date: t.date,
            payee: t.payee || '',
            description: t.description || '',
            amount: toCents(t.amount),
          }))"
        />
      </div>

      <!-- Links to classic tools -->
      <div class="card mt-3">
        <h3>Reconciliation Tools</h3>
        <p class="text-muted text-sm">
          For advanced reconciliation operations (start, lock, assert), use the classic CLI or the
          <a href="/app/index-classic.html#/recon" target="_blank">classic reconciliation page</a>.
        </p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiGet } from '../api.js'
import DataTable from '../components/DataTable.vue'

const loading = ref(true)
const error = ref('')
const data = ref(null)

function toCents(amount) {
  if (amount == null) return 0
  return Math.round(Math.abs(amount) * 100)
}

function fmt(cents) {
  if (cents == null) return '—'
  const abs = Math.abs(cents)
  return (cents < 0 ? '-' : '') + '$' + abs.toFixed(2)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await apiGet('/reconciliation')
  } catch (e) {
    error.value = e.message || 'Failed to load reconciliation data'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

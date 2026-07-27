<template>
  <div class="page">
    <div class="page-header">
      <h1>🧾 Receipts</h1>
      <p>All receipt documents attached to your ledger</p>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div>Loading receipts...</div>

    <div v-else-if="error" class="card error text-center" style="padding: 30px;">
      <p>⚠ {{ error }}</p>
      <button class="btn btn-outline mt-2" @click="load">🔄 Retry</button>
    </div>

    <template v-else>
      <!-- Empty state -->
      <div v-if="!documents.length" class="card empty-state text-center" style="padding: 40px;">
        <div style="font-size: 3rem; margin-bottom: 12px;">🧾</div>
        <h3>No Receipts Yet</h3>
        <p class="text-muted">Upload a receipt photo or PDF to get started.</p>
        <router-link to="/capture" class="btn btn-primary mt-3" style="display:inline-block;">
          📸 Capture Receipt
        </router-link>
      </div>

      <!-- Receipt list -->
      <div v-else class="card">
        <h2>Attached Receipts ({{ documents.length }})</h2>
        <DataTable
          :columns="[
            { key: 'date', label: 'Date', type: 'date' },
            { key: 'account', label: 'Account' },
            { key: 'file', label: 'File' },
          ]"
          :rows="documents.map(d => ({
            date: d.date,
            account: `<span class=\"tag tag-blue\">${escapeHtml(d.account || '')}</span>`,
            file: `<code style=\"font-size:0.75rem;\">${escapeHtml((d.path || '').split('/').pop())}</code>`,
          }))"
        />
      </div>

      <!-- New receipt CTA -->
      <div class="card mt-3">
        <h2>📸 New Receipt</h2>
        <p class="text-muted">
          Take a photo or upload a PDF receipt. It will be scanned,
          categorized, and permanently attached to your ledger.
        </p>
        <router-link to="/capture" class="btn btn-primary">
          📸 Capture Receipt
        </router-link>
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
const documents = ref([])

function escapeHtml(str) {
  if (!str) return ''
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await apiGet('/receipts/list')
    documents.value = data?.documents || []
  } catch (e) {
    error.value = e.message || 'Failed to load receipts'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Invoices</h1>
      <p>Accounts Receivable: {{ money(ar.total_ar) }}</p>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>

    <template v-else>
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">Outstanding</div>
          <div class="stat-value">{{ money(ar.total_ar) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Open Invoices</div>
          <div class="stat-value">{{ ar.invoice_count }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Overdue</div>
          <div class="stat-value" :class="ar.overdue_count > 0 ? 'text-danger' : 'text-success'">
            {{ ar.overdue_count }} ({{ money(ar.estimated_overdue_amount) }})
          </div>
        </div>
      </div>

      <div class="card">
        <div class="invoices-head">
          <h2>All Invoices</h2>
          <router-link to="/new-invoice" class="btn btn-primary btn-sm">➕ New Invoice</router-link>
        </div>
        <div v-if="!rows.length" class="empty-state">No invoices yet.</div>
        <DataTable v-else
          :columns="[
            { key: 'date', label: 'Date', type: 'date' },
            { key: 'client', label: 'Client' },
            { key: 'description', label: 'Description' },
            { key: 'amount', label: 'Amount', type: 'money' },
            { key: 'status', label: 'Status' },
          ]"
          :rows="rows"
        >
          <template #cell-status="{ row }"><StatusBadge :status="row.paid ? 'paid' : 'unpaid'" :labels="{ paid: 'Paid', unpaid: 'Unpaid' }" /></template>
          <template #actions="{ row }">
            <button class="btn btn-outline btn-sm" @click="downloadPdf(row)">📄 PDF</button>
            <button v-if="!row.paid" class="btn btn-success btn-sm" @click="markPaid(row)">✅ Pay</button>
            <a class="btn btn-outline btn-sm"
               :href="mailtoLink(row)">✉️ Send</a>
          </template>
        </DataTable>
      </div>
    </template>

    <ConfirmDialog v-model="confirmShow" :title="confirmTitle" :message="confirmMessage"
                   confirm-text="Mark Paid" danger @confirm="confirmPaid" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiGet, apiPost, apiDownload } from '../api.js'
import DataTable from '../components/DataTable.vue'
import StatusBadge from '../components/StatusBadge.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const loading = ref(true)
const invoices = ref([])
const ar = ref({ total_ar: 0, invoice_count: 0, overdue_count: 0, estimated_overdue_amount: 0 })

const confirmShow = ref(false)
const confirmTitle = ref('Mark as Paid')
const confirmMessage = ref('')
const pending = ref(null)

const rows = computed(() =>
  (invoices.value || []).map((i, idx) => {
    const num = 'INV-' + ((i.date || '').slice(0, 4) || '2026') + '-' + String(idx + 1).padStart(3, '0')
    return { ...i, num, paid: i.paid === true, amount: i.amount || 0, status: i.paid === true ? 'paid' : 'unpaid' }
  })
)

function money(v) {
  const n = Number(v) || 0
  return (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2 })
}

function mailtoLink(row) {
  const subject = encodeURIComponent(`Invoice ${row.num}`)
  const body = encodeURIComponent(`Hi,\n\nInvoice ${row.num} for ${row.description} is attached.\n\nAmount due: ${money(row.amount)}\n\nThank you!`)
  return `mailto:?subject=${subject}&body=${body}`
}

function markPaid(row) {
  pending.value = row
  confirmTitle.value = 'Mark as Paid'
  confirmMessage.value = `Mark invoice ${row.num} as paid for ${money(row.amount)}?`
  confirmShow.value = true
}

async function confirmPaid() {
  const row = pending.value
  pending.value = null
  if (!row) return
  try {
    await apiPost(`/invoices/${encodeURIComponent(row.num)}/pay`, { amount: row.amount })
    row.paid = true
  } catch (e) {
    alert('Failed to mark paid: ' + (e.message || 'error'))
  }
}

async function downloadPdf(row) {
  try {
    await apiDownload(`/invoices/${encodeURIComponent(row.num)}/pdf`, `${row.num}.pdf`)
  } catch (e) {
    alert('PDF download failed: ' + (e.message || 'error'))
  }
}

async function load() {
  loading.value = true
  try {
    const [inv, arData] = await Promise.all([apiGet('/invoices'), apiGet('/invoices/ar')])
    invoices.value = inv.invoices || []
    ar.value = arData || ar.value
  } catch (e) {
    /* surface via empty state */
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.invoices-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
</style>

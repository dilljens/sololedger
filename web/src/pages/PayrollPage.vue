<template>
  <div class="page">
    <div class="page-header">
      <h1>Payroll</h1>
      <p>S-Corp Payroll Management</p>
    </div>

    <div class="card">
      <h2>Import Gusto Payroll CSV</h2>
      <p class="text-muted text-sm">Upload your Gusto payroll export CSV to record pay period journal entries in the ledger.</p>
      <div class="drop-zone">
        <FileUpload accept=".csv" label="Choose Gusto CSV" icon="📤" @select="onCsvSelect" @clear="clearCsv" />
        <label class="preview-check">
          <input type="checkbox" v-model="preview" /> Preview only (don't write to ledger)
        </label>
        <button class="btn btn-primary" @click="importCsv" :disabled="!csvFile || importing">
          {{ importing ? '⏳ Importing...' : '📤 Import Payroll CSV' }}
        </button>
      </div>
      <div v-if="importMsg" :class="importMsg.ok ? 'text-success' : 'text-danger'" class="text-sm mt-2">{{ importMsg.text }}</div>

      <div v-if="importResult" class="mt-2">
        <p class="text-success text-sm">✅ {{ preview ? 'Parsed' : 'Imported' }} {{ importResult.imported }} pay period(s)</p>
        <DataTable
          :columns="[
            { key: 'date', label: 'Date', type: 'date' },
            { key: 'employee', label: 'Employee' },
            { key: 'gross', label: 'Gross', type: 'money' },
            { key: 'net', label: 'Net', type: 'money' },
          ]"
          :rows="(importResult.rows || []).filter(r => !r.skipped)"
        />
        <p class="text-sm mt-2">
          Total gross: {{ money(importResult.total_gross) }} | Total net: {{ money(importResult.total_net) }}
          | Employer taxes: {{ money(importResult.total_employer_taxes) }}
        </p>
        <p v-if="importResult.errors?.length" class="text-danger text-sm">Errors: {{ importResult.errors.join(', ') }}</p>
      </div>
    </div>

    <div class="card">
      <h2>YTD Payroll Summary</h2>
      <div v-if="summaryLoading" class="text-muted text-sm">Loading...</div>
      <p v-else-if="summary.entity_type !== 'scorp'" class="text-muted text-sm">{{ summary.note || 'Payroll is for S-Corp mode only.' }}</p>
      <table v-else class="data-table">
        <tbody>
          <tr><td>Total Gross Wages YTD</td><td class="num">{{ money(summary.total_gross) }}</td></tr>
          <tr><td><strong>Total Employer Taxes YTD</strong></td><td class="num"><strong>{{ money(summary.total_employer_taxes) }}</strong></td></tr>
          <template v-if="summary.employer_breakdown">
            <tr><td class="text-muted">↳ Social Security (6.2%)</td><td class="num text-muted">{{ money(summary.employer_breakdown.social_security) }}</td></tr>
            <tr><td class="text-muted">↳ Medicare (1.45%)</td><td class="num text-muted">{{ money(summary.employer_breakdown.medicare) }}</td></tr>
            <tr><td class="text-muted">↳ FUTA (0.6%)</td><td class="num text-muted">{{ money(summary.employer_breakdown.futa) }}</td></tr>
            <tr><td class="text-muted">↳ SUTA</td><td class="num text-muted">{{ money(summary.employer_breakdown.suta) }}</td></tr>
          </template>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>Disburse Net Pay</h2>
      <p class="text-muted text-sm">Record the transfer of net pay from your business account to the owner.</p>
      <div class="form-row">
        <FormField v-model="disburse.date" type="date" label="Date" />
        <FormField v-model.number="disburse.amount" type="number" label="Net Pay Amount" placeholder="3461.54" />
        <button class="btn btn-outline align-end" @click="disbursePay" :disabled="disbursing">💰 Record Disbursement</button>
      </div>
      <p v-if="disburse.msg" :class="disburse.ok ? 'text-success' : 'text-danger'" class="text-sm">{{ disburse.msg }}</p>
    </div>

    <ConfirmDialog v-model="disburseConfirm" title="Record Disbursement" :message="disburseConfirmMsg"
                   confirm-text="Record" @confirm="confirmDisburse" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiGet, apiPost, apiUpload } from '../api.js'
import FileUpload from '../components/FileUpload.vue'
import FormField from '../components/FormField.vue'
import DataTable from '../components/DataTable.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const csvFile = ref(null)
const preview = ref(true)
const importing = ref(false)
const importMsg = ref({ text: '', ok: false })
const importResult = ref(null)

const summary = ref({})
const summaryLoading = ref(true)

const disburse = ref({ date: new Date().toISOString().slice(0, 10), amount: null, msg: '', ok: false })
const disbursing = ref(false)
const disburseConfirm = ref(false)
const disburseConfirmMsg = ref('')

function money(v) {
  return '$' + Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })
}

function onCsvSelect(files) {
  csvFile.value = files && files[0] ? files[0] : files
  importResult.value = null
  importMsg.value = { text: '', ok: false }
}

function clearCsv() {
  csvFile.value = null
  importResult.value = null
}

async function importCsv() {
  if (!csvFile.value) return
  importing.value = true
  importMsg.value = { text: '', ok: false }
  try {
    importResult.value = await apiUpload('/payroll/import', csvFile.value, {
      preview: preview.value ? 'true' : 'false',
    })
    importMsg.value = { text: preview.value ? 'Parsed CSV successfully.' : 'Imported successfully.', ok: true }
    if (!preview.value) loadSummary()
  } catch (e) {
    importMsg.value = { text: '⚠ ' + (e.message || 'Import failed'), ok: false }
  } finally {
    importing.value = false
  }
}

async function loadSummary() {
  summaryLoading.value = true
  try {
    summary.value = await apiGet('/payroll/summary')
  } catch (e) {
    summary.value = { note: 'Failed to load payroll summary' }
  } finally {
    summaryLoading.value = false
  }
}

function disbursePay() {
  const d = disburse.value
  if (!d.date || !d.amount || d.amount <= 0) {
    d.msg = '⚠ Enter a valid date and amount.'
    d.ok = false
    return
  }
  disburseConfirmMsg.value = `Record net pay disbursement of ${money(d.amount)} on ${d.date}?`
  disburseConfirm.value = true
}

async function confirmDisburse() {
  disbursing.value = true
  try {
    const result = await apiPost('/payroll/disburse', { date: disburse.value.date, amount: disburse.value.amount })
    disburse.value.msg = `✅ Disbursement recorded: ${money(result.amount)} on ${result.date}`
    disburse.value.ok = true
    disburse.value.amount = null
    loadSummary()
  } catch (e) {
    disburse.value.msg = '⚠ ' + (e.message || 'Failed')
    disburse.value.ok = false
  } finally {
    disbursing.value = false
  }
}

onMounted(loadSummary)
</script>

<style scoped>
.drop-zone { border: 2px dashed var(--gray-300); border-radius: 8px; padding: 20px; display: flex; flex-direction: column; gap: 12px; align-items: center; }
.preview-check { display: inline-flex; align-items: center; gap: 6px; font-size: 0.85rem; cursor: pointer; }
.form-row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
.align-end { margin-bottom: 2px; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
</style>

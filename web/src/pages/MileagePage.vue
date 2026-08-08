<template>
  <div class="page">
    <div class="page-header">
      <h1>🚗 Mileage</h1>
      <p>Track business driving for IRS deductions ({{ year }}: $0.70/mi)</p>
    </div>

    <div v-if="report" class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">Total Miles</div>
        <div class="stat-value">{{ Math.round(report.total_miles) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Deduction</div>
        <div class="stat-value text-success">${{ fmt(report.total_deduction) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Trips</div>
        <div class="stat-value">{{ report.trip_count }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Rate</div>
        <div class="stat-value">${{ Number(report.rate_per_mile || 0.70).toFixed(2) }}/mi</div>
      </div>
    </div>

    <div class="card">
      <h2>Log a Trip</h2>
      <div class="form-row">
        <FormField v-model="form.date" type="date" label="Date" />
        <FormField v-model.number="form.miles" type="number" label="Miles" placeholder="42" />
        <FormField v-model="form.purpose" type="text" label="Purpose" placeholder="Client meeting" />
        <button class="btn btn-primary align-end" @click="logTrip" :disabled="saving">➕ Log Trip</button>
      </div>
      <Alert v-if="form.msg" :variant="form.ok ? 'success' : 'error'" :visible="true" :icon="form.ok ? '✅' : '⚠️'">
        {{ form.msg }}
      </Alert>
    </div>

    <div class="card">
      <h2>Trip Log <span v-if="trips.length" class="text-muted text-sm">({{ trips.length }} trips, {{ totalMiles.toFixed(0) }} mi, ${{ fmt(totalDeduction) }} deduction)</span></h2>
      <div v-if="!trips.length" class="empty-state">
        <div class="icon">🚗</div><h3>No Trips Yet</h3><p>Use the form above to log your first trip.</p>
      </div>
      <DataTable v-else
        :columns="[
          { key: 'date', label: 'Date', type: 'date' },
          { key: 'purpose', label: 'Purpose' },
          { key: 'miles', label: 'Miles' },
          { key: 'deduction', label: 'Deduction', type: 'money' },
        ]"
        :rows="trips.map(t => ({ ...t, miles: Number(t.miles).toFixed(1), deduction: t.deduction || 0 }))"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiGet, apiPost } from '../api.js'
import FormField from '../components/FormField.vue'
import DataTable from '../components/DataTable.vue'
import Alert from '../components/Alert.vue'

const year = new Date().getFullYear()
const trips = ref([])
const report = ref(null)
const saving = ref(false)
const form = ref({ date: new Date().toISOString().slice(0, 10), miles: null, purpose: '', msg: '', ok: false })

const totalMiles = computed(() => trips.value.reduce((s, t) => s + (t.miles || 0), 0))
const totalDeduction = computed(() => trips.value.reduce((s, t) => s + (t.deduction || 0), 0))

function fmt(v) {
  return Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })
}

async function logTrip() {
  const f = form.value
  if (!f.date || !f.miles || !f.purpose.trim()) {
    f.msg = 'Please fill in all fields.'
    f.ok = false
    return
  }
  saving.value = true
  try {
    await apiPost('/mileage/add', { date: f.date, miles: f.miles, purpose: f.purpose.trim(), post_to_ledger: false })
    f.msg = `✅ Logged: ${f.purpose.trim()} — ${f.miles} mi ($${(f.miles * 0.70).toFixed(2)} deduction)`
    f.ok = true
    f.miles = null
    f.purpose = ''
    load()
  } catch (e) {
    f.msg = '⚠ ' + (e.message || 'Failed')
    f.ok = false
  } finally {
    saving.value = false
  }
}

async function load() {
  try {
    const [t, r] = await Promise.all([apiGet('/mileage/trips?limit=20'), apiGet('/mileage/report')])
    trips.value = t.trips || []
    report.value = r
  } catch { /* API unavailable */ }
}

onMounted(load)
</script>

<style scoped>
.form-row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
.align-end { margin-bottom: 2px; }
</style>

<template>
  <div class="page">
    <div class="page-header">
      <h1>➕ New Invoice</h1>
      <p>Create an invoice and optionally generate a PDF</p>
    </div>

    <div class="card">
      <form @submit.prevent="submit">
        <div class="form-grid">
          <div class="form-field">
            <label class="form-label" for="inv-client">Client *</label>
            <input id="inv-client" v-model="form.client" class="form-input" required placeholder="Acme Corp" />
          </div>
          <div class="form-field">
            <label class="form-label" for="inv-description">Description *</label>
            <input id="inv-description" v-model="form.description" class="form-input" required placeholder="Consulting services" />
          </div>
          <div class="form-field">
            <label class="form-label" for="inv-amount">Amount (USD) *</label>
            <input id="inv-amount" v-model.number="form.amount" class="form-input" type="number" step="0.01" min="0" required placeholder="1500.00" />
          </div>
          <div class="form-field">
            <label class="form-label" for="inv-date">Invoice Date</label>
            <input id="inv-date" v-model="form.date" class="form-input" type="date" />
          </div>
          <div class="form-field">
            <label class="form-label" for="inv-due">Due In (days)</label>
            <input id="inv-due" v-model.number="form.due_days" class="form-input" type="number" min="0" step="1" />
          </div>
          <div class="form-field">
            <label class="form-label" for="inv-email">Client Email</label>
            <input id="inv-email" v-model="form.client_email" class="form-input" type="email" placeholder="billing@acme.com" />
          </div>
        </div>

        <div class="form-checks">
          <label class="check-label">
            <input type="checkbox" v-model="form.generate_pdf" /> Generate PDF
          </label>
          <label class="check-label">
            <input type="checkbox" v-model="form.payment_link" /> Add payment link
          </label>
        </div>

        <div class="form-actions">
          <button class="btn btn-primary" type="submit" :disabled="submitting">
            {{ submitting ? '⏳ Creating...' : 'Create Invoice' }}
          </button>
          <router-link to="/invoices" class="btn btn-outline">Cancel</router-link>
        </div>

        <div v-if="error" class="card error mt-3">
          ⚠ {{ error }}
        </div>

        <div v-if="result" class="card mt-3" style="border-left: 4px solid var(--green-500);">
          <h3>✅ Invoice {{ result.number }} created</h3>
          <p>Client: <strong>{{ result.client }}</strong></p>
          <p>Amount: <strong>${{ Number(result.amount).toFixed(2) }}</strong></p>
          <p v-if="result.due">Due: <strong>{{ result.due }}</strong></p>
          <p v-if="result.payment_url">
            Payment link: <a :href="result.payment_url" target="_blank" rel="noopener">{{ result.payment_url }}</a>
          </p>
          <p v-if="result.pdf_path">PDF: <code>{{ result.pdf_path }}</code></p>
          <button class="btn btn-primary mt-2" @click="reset">Create Another</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { apiPost } from '../api.js'

const form = ref({
  client: '',
  description: '',
  amount: null,
  date: '',
  due_days: 30,
  client_email: '',
  generate_pdf: true,
  payment_link: false,
})
const submitting = ref(false)
const error = ref('')
const result = ref(null)

async function submit() {
  if (!form.value.client || !form.value.description || form.value.amount == null) return
  submitting.value = true
  error.value = ''
  result.value = null
  try {
    const payload = {
      client: form.value.client,
      description: form.value.description,
      amount: form.value.amount,
      due_days: form.value.due_days || 30,
      generate_pdf: form.value.generate_pdf,
      payment_link: form.value.payment_link,
    }
    if (form.value.date) payload.date = form.value.date
    if (form.value.client_email) payload.client_email = form.value.client_email
    result.value = await apiPost('/invoices', payload)
  } catch (e) {
    error.value = e.message || 'Failed to create invoice'
  } finally {
    submitting.value = false
  }
}

function reset() {
  result.value = null
  error.value = ''
  form.value = {
    client: '',
    description: '',
    amount: null,
    date: '',
    due_days: 30,
    client_email: '',
    generate_pdf: true,
    payment_link: false,
  }
}
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}
.form-field { display: flex; flex-direction: column; gap: 4px; }
.form-label { font-size: 0.8rem; font-weight: 600; color: var(--gray-600); }
.form-checks { display: flex; gap: 20px; margin-top: 16px; }
.check-label { display: flex; align-items: center; gap: 6px; font-size: 0.9rem; }
.form-actions { display: flex; gap: 12px; margin-top: 20px; }
</style>

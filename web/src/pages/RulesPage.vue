<template>
  <div class="page">
    <div class="page-header">
      <h1>📏 Categorization Rules</h1>
      <p>Pattern-based rules for auto-categorizing transactions</p>
    </div>
    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>
    <div v-else-if="error" class="card error">⚠ {{ error }}</div>
    <template v-else>
      <div class="card">
        <h2>Add Rule</h2>
        <div class="rule-form">
          <input v-model="newRule.pattern" placeholder="Pattern (e.g. AMAZON)" class="form-input" />
          <select v-model="newRule.matcher_type" class="form-input">
            <option value="substring">Substring</option>
            <option value="regex">Regex</option>
            <option value="eq">Exact</option>
          </select>
          <input v-model="newRule.target_account" placeholder="Account (e.g. Expenses:Software)" class="form-input" />
          <button class="btn btn-primary btn-sm" @click="addRule">+ Add</button>
        </div>
      </div>
      <div class="card">
        <h2>Rules ({{ rules.length }})</h2>
        <div v-if="!rules.length" class="text-muted text-center" style="padding:20px;">No rules yet. Add one above.</div>
        <div v-for="r in rules" :key="r.id" class="rule-row">
          <span class="rule-matcher">{{ r.matcher_type }}</span>
          <code class="rule-pattern">{{ r.pattern }}</code>
          <span class="rule-arrow">→</span>
          <span class="rule-account">{{ r.target_account }}</span>
          <span class="rule-priority">#{{ r.priority }}</span>
          <label class="toggle-label"><input type="checkbox" :checked="r.is_active" @change="toggleRule(r)" /></label>
          <button class="btn btn-ghost btn-sm" @click="deleteRule(r.id)">✕</button>
        </div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { apiGet, apiPost, apiPut, apiDelete } from '../api.js'
const loading = ref(true); const error = ref(''); const rules = ref([])
const newRule = ref({ pattern: '', matcher_type: 'substring', target_account: '' })
async function load() {
  try { rules.value = (await apiGet('/rules')).rules } catch (e) { error.value = e.message }
  finally { loading.value = false }
}
async function addRule() {
  if (!newRule.value.pattern || !newRule.value.target_account) return
  await apiPost('/rules', newRule.value)
  newRule.value = { pattern: '', matcher_type: 'substring', target_account: '' }
  await load()
}
async function toggleRule(r) {
  await apiPut(`/rules/${r.id}`, { is_active: !r.is_active })
  await load()
}
async function deleteRule(id) {
  await apiDelete(`/rules/${id}`); await load()
}
onMounted(load)
</script>
<style scoped>
.rule-form { display: flex; gap: 8px; flex-wrap: wrap; align-items: end; }
.rule-row { display: flex; align-items: center; gap: 8px; padding: 8px; border-bottom: 1px solid var(--gray-100); font-size: 0.85rem; }
.rule-matcher { font-size: 0.7rem; background: var(--gray-100); padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
.rule-pattern { font-family: monospace; font-weight: 600; min-width: 120px; }
.rule-arrow { color: var(--gray-400); }
.rule-account { color: var(--primary); font-weight: 600; }
.rule-priority { color: var(--gray-400); font-size: 0.75rem; margin-left: auto; }
.toggle-label { cursor: pointer; }
</style>

<template>
  <div class="line-item-reconciler">
    <div v-if="!items.length" class="empty-state">No line items on this receipt.</div>

    <template v-else>
      <!-- Batch actions -->
      <div class="recon-toolbar">
        <div class="batch-assign">
          <input list="recon-accounts"
                 v-model="batchAccount"
                 placeholder="Account for all lines…"
                 class="form-input input-sm"
                 @keydown.enter="assignBatch" />
          <datalist id="recon-accounts">
            <option v-for="a in accounts" :key="a" :value="a" />
          </datalist>
          <button class="btn btn-ghost btn-sm" @click="assignBatch" :disabled="!batchAccount">
            Apply to all
          </button>
        </div>
        <span class="recon-summary" :class="{ 'recon-balanced': balancePct >= 99.5, 'recon-short': balancePct < 99.5 }">
          Allocated {{ formatMoney(allocatedCents) }} of {{ formatMoney(totalCents) }}
          ({{ balancePct.toFixed(0) }}%)
        </span>
      </div>

      <table class="data-table recon-table">
        <thead>
          <tr>
            <th>Description</th>
            <th>Category</th>
            <th class="num">Amount</th>
            <th class="center">Personal</th>
            <th class="center">Reimb.</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.itemId">
            <td>{{ row.description }}</td>
            <td>
              <input list="recon-accounts"
                     v-model="row.coaAccount"
                     placeholder="Assign account…"
                     class="form-input input-sm"
                     @change="emitUpdate(row)" />
            </td>
            <td class="num">{{ formatMoney(row.totalCents) }}</td>
            <td class="center">
              <input type="checkbox" v-model="row.isPersonal" @change="emitUpdate(row)" />
            </td>
            <td class="center">
              <input type="checkbox" v-model="row.isReimbursable" @change="emitUpdate(row)" />
            </td>
          </tr>
        </tbody>
      </table>

      <div class="recon-footer">
        <span class="text-muted text-sm">
          <template v-if="personalCents > 0">{{ formatMoney(personalCents) }} marked personal (excluded from ledger)</template>
          <template v-else>&nbsp;</template>
        </span>
        <button class="btn btn-success" :disabled="committing || !assignedCount" @click="$emit('commit')">
          {{ committing ? '⏳ Committing…' : `✅ Commit ${assignedCount} line${assignedCount === 1 ? '' : 's'}` }}
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },          // [{id, description, total_cents, coa_account, is_personal, is_reimbursable}]
  accounts: { type: Array, default: () => [] },        // account strings for the dropdown
  totalCents: { type: Number, default: 0 },
  committing: { type: Boolean, default: false },
})

const emit = defineEmits(['update-item', 'commit'])

const batchAccount = ref('')
const rows = ref([])

watch(() => props.items, (items) => {
  rows.value = (items || []).map(i => ({
    itemId: i.id,
    description: i.description || '',
    totalCents: i.total_cents || 0,
    coaAccount: i.coa_account || '',
    isPersonal: !!i.is_personal,
    isReimbursable: !!i.is_reimbursable,
  }))
}, { immediate: true, deep: true })

const allocatedCents = computed(() =>
  rows.value.filter(r => r.coaAccount && !r.isPersonal).reduce((s, r) => s + r.totalCents, 0))
const personalCents = computed(() =>
  rows.value.filter(r => r.isPersonal).reduce((s, r) => s + r.totalCents, 0))
const assignedCount = computed(() =>
  rows.value.filter(r => r.coaAccount && !r.isPersonal).length)
const balancePct = computed(() => {
  if (!props.totalCents) return 0
  return (allocatedCents.value / props.totalCents) * 100
})

function emitUpdate(row) {
  emit('update-item', {
    itemId: row.itemId,
    patch: {
      coa_account: row.coaAccount || null,
      is_personal: row.isPersonal,
      is_reimbursable: row.isReimbursable,
    },
  })
}

function assignBatch() {
  if (!batchAccount.value) return
  rows.value.forEach(r => { r.coaAccount = batchAccount.value })
  rows.value.forEach(emitUpdate)
  batchAccount.value = ''
}

function formatMoney(cents) {
  return '$' + ((cents || 0) / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })
}
</script>

<style scoped>
.line-item-reconciler { width: 100%; }
.recon-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.batch-assign { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 260px; }
.recon-summary { font-size: 0.8rem; font-weight: 600; padding: 4px 10px; border-radius: 999px; }
.recon-balanced { background: var(--success-bg); color: #15803d; }
.recon-short { background: var(--warning-bg); color: #92400e; }
.recon-table th, .recon-table td { padding: 8px 10px; }
.recon-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.recon-table .center { text-align: center; }
.recon-table input[type="checkbox"] { accent-color: var(--primary); }
.recon-table .form-input { min-width: 180px; }
.recon-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; }
</style>

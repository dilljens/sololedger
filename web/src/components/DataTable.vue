<template>
  <div class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="col in columns" :key="col.key" @click="col.sortable !== false && toggleSort(col.key)"
              :class="{ sortable: col.sortable !== false, sorted: sortKey === col.key }">
            {{ col.label || col.key }}
            <span v-if="sortKey === col.key" class="sort-arrow">{{ sortDir === 'asc' ? '▲' : '▼' }}</span>
          </th>
          <th v-if="$slots.actions" class="actions-col">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!sortedRows.length">
          <td :colspan="columns.length + ($slots.actions ? 1 : 0)" class="empty-state">
            <slot name="empty">{{ emptyText }}</slot>
          </td>
        </tr>
        <tr v-for="(row, i) in sortedRows" :key="row.id || i">
          <td v-for="col in columns" :key="col.key">
            <slot :name="`cell-${col.key}`" :row="row" :value="getValue(row, col)">
              {{ formatValue(getValue(row, col), col) }}
            </slot>
          </td>
          <td v-if="$slots.actions" class="actions-col">
            <slot name="actions" :row="row" :index="i" />
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="pageCount > 1" class="pagination">
      <button class="btn btn-ghost btn-sm" :disabled="currentPage <= 1" @click="currentPage--">←</button>
      <span class="text-sm text-muted">{{ currentPage }} / {{ pageCount }}</span>
      <button class="btn btn-ghost btn-sm" :disabled="currentPage >= pageCount" @click="currentPage++">→</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
  pageSize: { type: Number, default: 0 },
  emptyText: { type: String, default: 'No data' },
  initialSort: { type: String, default: '' },
})

const sortKey = ref(props.initialSort)
const sortDir = ref('asc')
const currentPage = ref(1)

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

function getValue(row, col) {
  const val = col.key.split('.').reduce((o, k) => (o != null ? o[k] : undefined), row)
  return val !== undefined ? val : col.default
}

function formatValue(val, col) {
  if (val == null) return col.nullDisplay || '—'
  if (col.type === 'money') {
    const num = typeof val === 'number' ? val : parseFloat(val)
    return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  if (col.type === 'date' && typeof val === 'string' && val.includes('T')) {
    return val.split('T')[0]
  }
  if (col.type === 'cents') {
    return '$' + (Math.abs(val) / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })
  }
  return String(val)
}

const sortedRows = computed(() => {
  let data = [...props.rows]
  if (sortKey.value) {
    data.sort((a, b) => {
      const av = getValue(a, { key: sortKey.value })
      const bv = getValue(b, { key: sortKey.value })
      if (av == null) return 1
      if (bv == null) return -1
      return av < bv ? -1 : av > bv ? 1 : 0
    })
    if (sortDir.value === 'desc') data.reverse()
  }
  if (props.pageSize > 0) {
    const start = (currentPage.value - 1) * props.pageSize
    return data.slice(start, start + props.pageSize)
  }
  return data
})

const pageCount = computed(() =>
  props.pageSize > 0 ? Math.ceil(props.rows.length / props.pageSize) : 1
)
</script>

<style scoped>
.data-table { width: 100%; border-collapse: collapse; }
.data-table th { text-align: left; padding: 8px 12px; font-size: 0.8rem; font-weight: 600; color: var(--gray-500); border-bottom: 2px solid var(--gray-200); }
.data-table th.sortable { cursor: pointer; user-select: none; }
.data-table th.sortable:hover { color: var(--gray-700); }
.sort-arrow { font-size: 0.65rem; margin-left: 4px; }
.data-table td { padding: 8px 12px; border-bottom: 1px solid var(--gray-100); font-size: 0.85rem; }
.data-table tbody tr:hover { background: var(--gray-50); }
.empty-state { text-align: center; padding: 32px; color: var(--gray-400); }
.actions-col { width: 1px; white-space: nowrap; }
.pagination { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px; }
</style>

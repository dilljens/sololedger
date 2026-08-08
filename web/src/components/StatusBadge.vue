<template>
  <span class="badge" :class="badgeClass"><slot>{{ displayText }}</slot></span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: '' },
  /** Explicit variant: success | warning | danger | info | gray (overrides status map) */
  variant: { type: String, default: '' },
  /** status -> label overrides, e.g. { paid: 'Paid', unpaid: 'Due' } */
  labels: { type: Object, default: () => ({}) },
})

const VARIANTS = ['success', 'warning', 'danger', 'info', 'gray']

// Common status -> variant map. Unknown statuses fall back to gray.
const DEFAULT_MAP = {
  active: 'success', healthy: 'success', valid: 'success', committed: 'success',
  filed: 'info', pending: 'warning', processing: 'warning', trialing: 'info', trial: 'info',
  past_due: 'danger', overdue: 'danger', canceled: 'danger', cancelled: 'danger',
  paid: 'success', unpaid: 'danger', failed: 'danger', error: 'danger',
  invalid: 'danger', rejected: 'danger', locked: 'info', unlocked: 'success',
}

const badgeClass = computed(() => {
  const v = props.variant || DEFAULT_MAP[(props.status || '').toLowerCase()] || 'gray'
  return VARIANTS.includes(v) ? `badge-${v}` : 'badge-gray tag-gray'
})

const displayText = computed(() => props.labels[props.status] ?? props.status)
</script>

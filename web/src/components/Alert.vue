<template>
  <div v-if="visible" class="alert" :class="`alert-${variant}`" role="alert">
    <span v-if="icon" class="alert-icon">{{ icon }}</span>
    <div class="alert-body"><slot /></div>
    <button v-if="dismissible" class="alert-close" aria-label="Dismiss" @click="$emit('dismiss')">✕</button>
  </div>
</template>

<script setup>
const props = defineProps({
  /** success | error | warning | info */
  variant: { type: String, default: 'info' },
  visible: { type: Boolean, default: true },
  dismissible: { type: Boolean, default: false },
  icon: { type: String, default: '' },
})

defineEmits(['dismiss'])
</script>

<style scoped>
.alert {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-radius: 8px;
  font-size: 0.875rem;
  line-height: 1.5;
  margin-bottom: var(--space-3);
}
.alert-icon { flex-shrink: 0; line-height: 1.4; }
.alert-body { flex: 1; }
.alert-close {
  background: none; border: none; cursor: pointer;
  color: inherit; opacity: 0.6; font-size: 0.8rem; padding: 0 2px;
}
.alert-close:hover { opacity: 1; }
.alert-success { background: var(--success-bg); color: #15803d; border: 1px solid var(--success-border); }
.alert-error   { background: var(--danger-bg);  color: #991b1b; border: 1px solid var(--danger-border); }
.alert-warning { background: var(--warning-bg); color: #92400e; border: 1px solid var(--warning-border); }
.alert-info    { background: var(--info-bg);    color: #1e40af; border: 1px solid var(--info-border); }
</style>

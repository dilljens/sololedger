<template>
  <div class="page">
    <div class="page-header">
      <h1>Reset Password</h1>
      <p>Choose a new password for your account</p>
    </div>

    <div class="card reset-card">
      <template v-if="done">
        <div class="reset-icon">✅</div>
        <h2>Password updated</h2>
        <p class="text-muted">{{ doneMessage }}</p>
        <button class="btn btn-primary" @click="openSignIn">Sign In</button>
      </template>

      <template v-else>
        <div v-if="error" class="alert alert-error">{{ error }}</div>
        <form @submit.prevent="submit">
          <div class="form-group">
            <label class="form-label" for="reset-password">New password</label>
            <input
              id="reset-password"
              v-model="password"
              type="password"
              class="form-input"
              placeholder="Min 8 characters"
              required
              minlength="8"
              autocomplete="new-password"
            />
          </div>
          <div class="form-group">
            <label class="form-label" for="reset-confirm">Confirm password</label>
            <input
              id="reset-confirm"
              v-model="confirm"
              type="password"
              class="form-input"
              placeholder="Re-enter new password"
              required
              autocomplete="new-password"
            />
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" type="submit" :disabled="submitting">
              {{ submitting ? '⏳' : 'Set New Password' }}
            </button>
          </div>
        </form>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { apiPost } from '../api.js'

const route = useRoute()

const password = ref('')
const confirm = ref('')
const error = ref('')
const submitting = ref(false)
const done = ref(false)
const doneMessage = ref('')

onMounted(() => {
  if (!route.query.token) {
    error.value = 'Missing reset token. Use the link from your reset email.'
  }
})

async function submit() {
  error.value = ''
  if (password.value !== confirm.value) {
    error.value = 'Passwords do not match'
    return
  }
  if (password.value.length < 8) {
    error.value = 'Password must be at least 8 characters'
    return
  }
  submitting.value = true
  try {
    const data = await apiPost('/auth/reset-password', {
      token: route.query.token,
      password: password.value,
    })
    done.value = true
    doneMessage.value = data.message || 'Your password has been reset.'
  } catch (err) {
    error.value = err.data?.error || err.message || 'Failed to reset password'
  } finally {
    submitting.value = false
  }
}

function openSignIn() {
  document.dispatchEvent(new CustomEvent('show-auth-modal'))
}
</script>

<style scoped>
.reset-card {
  max-width: 420px;
  text-align: center;
}

.reset-card form {
  text-align: left;
}

.reset-icon {
  font-size: 2.5rem;
  margin-bottom: 8px;
}

.reset-card h2 {
  margin: 0 0 8px;
  font-size: 1.15rem;
  color: var(--gray-900);
}

.form-actions {
  margin-top: 8px;
}

.form-actions .btn {
  width: 100%;
  justify-content: center;
}

.alert-error {
  background: var(--danger-bg);
  color: var(--danger);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 0.85rem;
  margin-bottom: 16px;
  text-align: left;
}
</style>

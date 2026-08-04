<template>
  <div class="page">
    <div class="page-header">
      <h1>Email Verification</h1>
      <p>Confirm your email to activate your SoloLedger workspace</p>
    </div>

    <div class="card verify-card">
      <div v-if="loading" class="loading"><div class="spinner"></div>Verifying...</div>

      <template v-else-if="verified">
        <div class="verify-icon success">✅</div>
        <h2>Email verified — your workspace is ready</h2>
        <p class="text-muted">
          {{ verifiedEmail ? `The address ${verifiedEmail} has been confirmed.` : 'Your email has been confirmed.' }}
        </p>
        <button class="btn btn-primary" @click="openSignIn">Sign In</button>
      </template>

      <template v-else>
        <div class="verify-icon error">⚠️</div>
        <h2>We couldn't verify your email</h2>
        <p class="text-muted">{{ errorMessage }}</p>

        <div class="resend-form">
          <div class="form-group">
            <label class="form-label" for="verify-email">Email</label>
            <input
              id="verify-email"
              v-model="resendEmail"
              type="email"
              class="form-input"
              placeholder="you@example.com"
              autocomplete="email"
            />
          </div>
          <button class="btn btn-outline" :disabled="resending || !resendEmail" @click="resend">
            {{ resending ? '⏳' : (resendSent ? 'Sent ✓' : 'Resend verification email') }}
          </button>
          <p v-if="resendSent" class="text-sm text-muted resend-note">If that account exists, a verification email was sent.</p>
          <p v-if="resendError" class="text-sm resend-error">{{ resendError }}</p>
        </div>

        <p class="text-sm text-muted" style="margin-top: 16px;">
          Prefer to sign in anyway? <a href="#" @click.prevent="openSignIn">Go to Sign In</a>
        </p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { apiGet, apiPost } from '../api.js'

const route = useRoute()

const loading = ref(true)
const verified = ref(false)
const verifiedEmail = ref('')
const errorMessage = ref('')

const resendEmail = ref(typeof route.query.email === 'string' ? route.query.email : '')
const resending = ref(false)
const resendSent = ref(false)
const resendError = ref('')

onMounted(async () => {
  const token = route.query.token
  if (!token) {
    verified.value = false
    errorMessage.value = 'Missing verification token. Use the link from your verification email.'
    loading.value = false
    return
  }
  try {
    const data = await apiGet(`/auth/verify-email?token=${encodeURIComponent(token)}`)
    verified.value = data.verified === true
    verifiedEmail.value = data.email || ''
    if (!verified.value) errorMessage.value = data.error || 'Verification failed'
  } catch (err) {
    verified.value = false
    errorMessage.value = err.data?.error || err.message || 'Verification failed'
  } finally {
    loading.value = false
  }
})

async function resend() {
  resending.value = true
  resendError.value = ''
  resendSent.value = false
  try {
    await apiPost('/auth/resend-verification', { email: resendEmail.value })
    resendSent.value = true
  } catch (err) {
    resendError.value = err.data?.error || err.message || 'Failed to resend'
  } finally {
    resending.value = false
  }
}

function openSignIn() {
  document.dispatchEvent(new CustomEvent('show-auth-modal'))
}
</script>

<style scoped>
.verify-card {
  max-width: 480px;
  text-align: center;
}

.verify-icon {
  font-size: 2.5rem;
  margin-bottom: 8px;
}

.verify-card h2 {
  margin: 0 0 8px;
  font-size: 1.15rem;
  color: var(--gray-900);
}

.resend-form {
  max-width: 320px;
  margin: 20px auto 0;
  text-align: left;
}

.resend-form .btn {
  width: 100%;
  justify-content: center;
}

.resend-note {
  margin-top: 10px;
}

.resend-error {
  margin-top: 10px;
  color: var(--danger);
}
</style>

<template>
  <div class="modal-overlay" :class="{ visible: isOpen }" @click="close">
    <div class="modal auth-modal" @click.stop>
      <div class="modal-header">
        <h3 id="auth-modal-title">{{ modalTitle }}</h3>
        <button class="icon-btn" @click="close">✕</button>
      </div>

      <!-- Verification pending (after signup with verify_required) -->
      <div v-if="verifyPending" class="modal-body">
        <div class="alert alert-success">✅ Check your inbox to verify your email</div>
        <p class="text-sm text-muted">
          We sent a verification link to <strong>{{ email }}</strong>. Once you verify, you'll be able to sign in.
        </p>
        <button class="btn btn-outline" :disabled="resending" @click="resend">
          {{ resending ? '⏳' : (resendSent ? 'Sent ✓' : 'Resend verification email') }}
        </button>
        <p v-if="resendError" class="alert alert-error">{{ resendError }}</p>
        <p class="text-sm text-muted" style="margin-top: 12px;">
          <a href="#" @click.prevent="backToSignIn">Back to Sign In</a>
        </p>
      </div>

      <!-- Forgot password -->
      <div v-else-if="isForgot" class="modal-body">
        <div class="form-group">
          <label for="auth-email">Email</label>
          <input
            id="auth-email"
            v-model="email"
            type="email"
            class="form-input"
            placeholder="you@example.com"
            required
            autocomplete="email"
          />
        </div>
        <div v-if="forgotSent" class="alert alert-success">{{ forgotSentMessage }}</div>
        <div v-if="error" class="alert alert-error" role="alert">{{ error }}</div>
        <div class="modal-footer">
          <button class="btn btn-primary" :disabled="submitting" @click.prevent="submitForgot">
            {{ submitting ? '⏳' : 'Send Reset Link' }}
          </button>
          <p class="text-sm text-muted" style="margin-top: 8px;">
            Remember it? <a href="#" @click.prevent="backToSignIn">Back to Sign In</a>
          </p>
        </div>
      </div>

      <!-- Sign in / Sign up -->
      <form v-else @submit.prevent="submit">
        <div class="modal-body">
          <div class="form-group">
            <label for="auth-email">Email</label>
            <input
              id="auth-email"
              v-model="email"
              type="email"
              class="form-input"
              placeholder="you@example.com"
              required
              autocomplete="email"
            />
          </div>
          <div class="form-group">
            <label for="auth-password">Password</label>
            <input
              id="auth-password"
              v-model="password"
              type="password"
              class="form-input"
              placeholder="Min 8 characters"
              required
              minlength="8"
              :autocomplete="isSignUp ? 'new-password' : 'current-password'"
            />
            <p v-if="!isSignUp" class="text-sm" style="margin-top: 4px;">
              <a href="#" @click.prevent="toggleForgot">Forgot password?</a>
            </p>
          </div>
          <div v-if="error" class="alert alert-error" role="alert">{{ error }}</div>
          <div v-if="canResend" class="resend-row">
            <button class="btn btn-outline btn-sm" :disabled="resending" @click.prevent="resend">
              {{ resending ? '⏳' : (resendSent ? 'Sent ✓' : 'Resend verification email') }}
            </button>
            <p v-if="resendSent" class="text-sm text-muted resend-hint">If that account exists, a verification email was sent.</p>
          </div>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary" :disabled="submitting">
            {{ submitting ? '⏳' : (isSignUp ? 'Create Account' : 'Sign In') }}
          </button>
          <p class="text-sm text-muted" style="margin-top: 8px;">
            {{ isSignUp ? 'Already have an account?' : "Don't have an account?" }}
            <a href="#" @click.prevent="toggleMode">{{ isSignUp ? 'Sign In' : 'Sign Up' }}</a>
          </p>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { apiPost, setAuthToken, isAuthenticated } from '../api.js'

const isOpen = ref(false)
const isSignUp = ref(false)
const email = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

const verifyPending = ref(false)
const isForgot = ref(false)
const resending = ref(false)
const resendSent = ref(false)
const resendError = ref('')
const canResend = ref(false)
const forgotSent = ref(false)
const forgotSentMessage = ref('')

const modalTitle = computed(() => {
  if (verifyPending.value) return 'Verify Your Email'
  if (isForgot.value) return 'Forgot Password'
  return isSignUp.value ? 'Create Account' : 'Sign In'
})

let listener = null

onMounted(() => {
  listener = () => { isOpen.value = true; error.value = '' }
  document.addEventListener('show-auth-modal', listener)
})

onUnmounted(() => {
  if (listener) document.removeEventListener('show-auth-modal', listener)
})

function close() {
  isOpen.value = false
  error.value = ''
  canResend.value = false
  resendSent.value = false
  verifyPending.value = false
  isForgot.value = false
}

function toggleMode() {
  isSignUp.value = !isSignUp.value
  isForgot.value = false
  verifyPending.value = false
  canResend.value = false
  resendSent.value = false
  error.value = ''
}

function toggleForgot() {
  isForgot.value = true
  canResend.value = false
  error.value = ''
}

function backToSignIn() {
  isForgot.value = false
  verifyPending.value = false
  isSignUp.value = false
  canResend.value = false
  resendSent.value = false
  error.value = ''
}

async function resend() {
  resending.value = true
  resendError.value = ''
  resendSent.value = false
  try {
    await apiPost('/auth/resend-verification', { email: email.value })
    resendSent.value = true
  } catch (err) {
    resendError.value = err.data?.error || err.message || 'Failed to resend'
  } finally {
    resending.value = false
  }
}

async function submitForgot() {
  error.value = ''
  submitting.value = true
  try {
    const data = await apiPost('/auth/forgot-password', { email: email.value })
    forgotSent.value = true
    forgotSentMessage.value = data.message || 'If that account exists, a reset email was sent'
  } catch (err) {
    error.value = err.data?.error || err.message || 'Failed to send reset link'
  } finally {
    submitting.value = false
  }
}

async function submit() {
  error.value = ''
  canResend.value = false
  resendSent.value = false
  submitting.value = true
  try {
    const endpoint = isSignUp.value ? '/auth/signup' : '/auth/signin'
    const data = await apiPost(endpoint, { email: email.value, password: password.value })
    // Production signup requires email verification — keep the modal open
    // and let the user resend the verification email.
    if (isSignUp.value && data.verify_required) {
      verifyPending.value = true
      return
    }
    setAuthToken(data.token)
    localStorage.setItem('user_email', email.value)
    close()
    window.location.reload()
  } catch (err) {
    error.value = err.data?.error || err.message || 'Authentication failed'
    if (err.status === 403 && /not verified/i.test(error.value)) {
      canResend.value = true
    }
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.auth-modal {
  max-width: 420px;
}

.alert-error {
  background: #fef2f2;
  color: #dc2626;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 0.85rem;
  margin-top: 12px;
}

.alert-success {
  background: #f0fdf4;
  color: #15803d;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 0.85rem;
  margin-bottom: 12px;
}

.resend-row {
  margin-top: 12px;
}

.resend-hint {
  margin-top: 6px;
}
</style>

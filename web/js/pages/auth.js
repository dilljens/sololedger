import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast, showConfirm, setSessionToken, setUserInfo, getUserInfo, isAuthenticated, apiSignIn, apiSignUp, apiSignInWithGoogle, apiLogout } from '../api.js';

let _authMode = 'signin';

export function showAuthModal() {
  _authMode = 'signin';
  const overlay = document.getElementById('auth-modal-overlay');
  if (overlay) overlay.style.display = 'flex';
  const email = document.getElementById('auth-email');
  const pass = document.getElementById('auth-password');
  const err = document.getElementById('auth-error');
  if (email) email.value = '';
  if (pass) pass.value = '';
  if (err) err.style.display = 'none';
  document.getElementById('auth-modal-title').textContent = 'Sign In';
  document.getElementById('auth-submit-btn').textContent = 'Sign In';
  document.getElementById('auth-toggle-text').textContent = "Don't have an account?";
  document.getElementById('auth-toggle-link').textContent = 'Sign Up';
  if (email) setTimeout(() => email.focus(), 150);
  updateGoogleClientId();
}
window.showAuthModal = showAuthModal;

export function toggleAuthMode() {
  _authMode = _authMode === 'signin' ? 'signup' : 'signin';
  const title = document.getElementById('auth-modal-title');
  const btn = document.getElementById('auth-submit-btn');
  const toggleText = document.getElementById('auth-toggle-text');
  const toggleLink = document.getElementById('auth-toggle-link');
  const err = document.getElementById('auth-error');
  if (err) err.style.display = 'none';
  if (_authMode === 'signup') {
    title.textContent = 'Sign Up';
    btn.textContent = 'Create Account';
    toggleText.textContent = 'Already have an account?';
    toggleLink.textContent = 'Sign In';
  } else {
    title.textContent = 'Sign In';
    btn.textContent = 'Sign In';
    toggleText.textContent = "Don't have an account?";
    toggleLink.textContent = 'Sign Up';
  }
}
window.toggleAuthMode = toggleAuthMode;

export async function submitSignIn() {
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;
  const errDiv = document.getElementById('auth-error');
  errDiv.style.display = 'none';
  if (!email || !password) {
    errDiv.textContent = 'Please fill in both email and password.';
    errDiv.style.display = 'block';
    return;
  }
  const btn = document.getElementById('auth-submit-btn');
  const origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Please wait...';
  try {
    let data;
    if (_authMode === 'signup') {
      if (password.length < 6) {
        errDiv.textContent = 'Password must be at least 6 characters.';
        errDiv.style.display = 'block';
        btn.disabled = false;
        btn.textContent = origText;
        return;
      }
      data = await apiSignUp(email, password, email.split('@')[0]);
    } else {
      data = await apiSignIn(email, password);
    }
    setSessionToken(data.token);
    setUserInfo(data.user);
    updateSidebarAuth();
    closeAuthModal();
    const active = document.querySelector('[data-page].active');
    if (active) await window.loadPage(active.dataset.page);
    setTimeout(() => window.checkOnboarding(), 600);
  } catch (e) {
    errDiv.textContent = escapeHtml(e.message);
    errDiv.style.display = 'block';
    btn.disabled = false;
    btn.textContent = origText;
  }
}
window.submitSignIn = submitSignIn;

export function closeAuthModal(e) {
  if (e && e.target !== e.currentTarget) return;
  const overlay = document.getElementById('auth-modal-overlay');
  if (overlay) overlay.style.display = 'none';
  const err = document.getElementById('auth-error');
  if (err) err.style.display = 'none';
}
window.closeAuthModal = closeAuthModal;

export async function handleGoogleCredential(response) {
  const errDiv = document.getElementById('auth-error');
  try {
    const data = await apiSignInWithGoogle(response.credential);
    setSessionToken(data.token);
    setUserInfo(data.user);
    updateSidebarAuth();
    closeAuthModal();
    const active = document.querySelector('[data-page].active');
    if (active) await window.loadPage(active.dataset.page);
    setTimeout(() => window.checkOnboarding(), 600);
  } catch (e) {
    errDiv.textContent = escapeHtml(e.message);
    errDiv.style.display = 'block';
  }
}
window.handleGoogleCredential = handleGoogleCredential;

export async function handleLogout() {
  const confirmed = await showConfirm('Sign Out', 'Are you sure you want to sign out?', { confirmText: 'Sign Out' });
  if (!confirmed) return;
  await apiLogout();
  updateSidebarAuth();
  const active = document.querySelector('[data-page].active');
  if (active) await window.loadPage(active.dataset.page);
}
window.handleLogout = handleLogout;

export function updateSidebarAuth() {
  const user = getUserInfo();
  const userInfo = document.getElementById('sidebar-user-info');
  const signinBtn = document.getElementById('sidebar-signin');
  const avatar = document.getElementById('user-avatar');
  const nameSpan = document.getElementById('user-name');
  if (user && isAuthenticated()) {
    userInfo.style.display = 'flex';
    signinBtn.style.display = 'none';
    if (user.picture) avatar.src = user.picture;
    else avatar.style.display = 'none';
    nameSpan.textContent = user.name || user.email || 'User';
  } else {
    userInfo.style.display = 'none';
    signinBtn.style.display = 'flex';
  }
}
window.updateSidebarAuth = updateSidebarAuth;

export function updateGoogleClientId(retries = 5) {
  const container = document.getElementById('google-signin-container');
  const notConfigured = document.getElementById('google-not-configured');
  const divider = document.getElementById('auth-divider-local');
  if (!container) return;
  fetch('/api/v1/auth/google/config')
    .then(r => r.json())
    .then(data => {
      if (!data.success || !data.data.client_id) {
        container.style.display = 'none';
        if (notConfigured) notConfigured.style.display = 'block';
        if (divider) divider.style.display = 'none';
        return;
      }
      const cid = data.data.client_id;
      function render() {
        if (window.google && window.google.accounts) {
          try {
            window.google.accounts.id.initialize({
              client_id: cid,
              callback: window.handleGoogleCredential,
              auto_prompt: false,
            });
            window.google.accounts.id.renderButton(container, {
              type: 'standard',
              shape: 'rectangular',
              theme: 'outline',
              text: 'signin_with',
              size: 'large',
              logo_alignment: 'left',
            });
            container.style.display = '';
            if (notConfigured) notConfigured.style.display = 'none';
            if (divider) divider.style.display = 'flex';
            return true;
          } catch (e) { return false; }
        }
        return false;
      }
      if (!render() && retries > 0) {
        setTimeout(() => updateGoogleClientId(retries - 1), 500);
      }
    })
    .catch(() => {});
}
window.updateGoogleClientId = updateGoogleClientId;

# UI Audit Findings: SoloLedger Web App

> Generated: 2026-07-25
> Scope: Full audit covering UX, WCAG 2.1 AA, PWA, performance, architecture, LLM, and 5-point UX check.

---

## Scorecard Summary

| Dimension | Score (1-10) | Key Gap |
|-----------|:-----------:|---------|
| Visual Design (Refactoring UI) | 7/10 | Inline styles bypass design tokens |
| WCAG 2.1 AA Accessibility | 5/10 | No form labels, no focus trapping, no skip link |
| PWA Installability | 3/10 | **No service worker**, no offline, no apple-touch-icon |
| Performance | 6/10 | No lazy loading, no caching, monolithic bundle |
| Module Architecture | 4/10 | 35+ global functions, 50 inline onclick handlers, duplicated code |
| LLM Integration | 6/10 | Key in plain-text localStorage, no client-side LLM |
| 5-Point UX Check | 5/10 | Missing error/empty states on many pages |

---

## Track A: Critical (Must Fix)

### A1. No service worker — app not installable as PWA
- **Severity:** Critical
- **File:** n/a — missing entirely
- **Issue:** No `sw.js` in the repo. No offline support, no caching strategy, no install prompt. Without a service worker, the browser cannot offer "Add to Home Screen" and the app cannot function offline.
- **Fix:** Create `web/sw.js` with cache-first for static assets (CSS, JS, icons), network-first for API calls. Register in `index.html`.
- **Effort:** 4-6 hours

### A2. Auth form has no `<form>` element — inaccessible
- **Severity:** Critical
- **File:** `web/index.html:71-93`
- **Issue:** Email/password fields are in bare `<div>` tags, not a `<form>`. Labels are `<div>` styled as labels, not `<label for="...">` elements. No `aria-required` or `required` attributes. Error div has no `role="alert"` or `aria-live`. Screen readers cannot associate labels with inputs.
- **Fix:** Wrap inputs in `<form>`, use `<label for="...">`, add `role="alert"` on error div.
- **Effort:** 1-2 hours

### A3. No apple-touch-icon or iOS meta tags — broken PWA on iOS
- **Severity:** Critical
- **File:** `web/index.html` (missing)
- **Issue:** No `<meta name="apple-mobile-web-app-capable">`, no `<link rel="apple-touch-icon">`. iOS users who add to home screen get a screenshot icon and the app opens in Safari, not standalone mode.
- **Fix:** Add meta tag and 152x152 PNG.
- **Effort:** 30 min

### A4. LLM API key in plain-text localStorage, exposed in DOM
- **Severity:** Critical
- **File:** `web/js/pages/settings.js:61` and `web/js/api.js:42-44`
- **Issue:** The API key is stored unencrypted in `localStorage` and rendered directly into an `<input>` element's `value` attribute. Any browser extension or XSS can read it. The key is also synced to server in plain text via POST.
- **Fix:** At minimum, don't pre-fill the input value (use placeholder). Consider server-side session-based key management instead of localStorage.
- **Effort:** 2-4 hours

---

## Track B: High Priority

### B1. Focus not trapped in modals — keyboard trap broken
- **Severity:** High
- **Files:** `web/index.html:60-112` (auth modal), `web/js/api.js:298-328` (confirm modal), `web/index.html:129` (mobile drawer)
- **Issue:** Tab key can escape the modal and reach background content. Screen reader and keyboard-only users lose context.
- **Fix:** Add focus trapping: on modal open, capture Tab to cycle within modal elements. Add `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to the modal heading.
- **Effort:** 3-4 hours

### B2. No empty states for Accounts, Import, Reports pages
- **Severity:** High
- **Files:** `web/js/pages/accounts.js`, `web/js/pages/import.js`, `web/js/pages/reports.js`
- **Issue:** When there's no data, these pages show blank cards/areas without any guidance. Refactoring UI principle: "Write out empty states."
- **Fix:** Add icon + message + CTA button for each empty state.
- **Effort:** 2-3 hours

### B3. Missing error states on 6 pages
- **Severity:** High
- **Files:** `web/js/pages/transactions.js`, `web/js/pages/tax.js` (deadlines), `web/js/pages/reports.js` (both pages), `web/js/pages/mileage.js`, `web/js/pages/categorize.js` (missing retry)
- **Issue:** API errors propagate to `app.js` generic catch or are silently swallowed. No retry buttons, no user-friendly messages.
- **Fix:** Add try/catch to each page with retry button and friendly error message.
- **Effort:** 3-5 hours

### B4. 35+ global window.* functions — namespace pollution
- **Severity:** High
- **Files:** All page files in `web/js/pages/`
- **Issue:** Inline `onclick` in JS-generated HTML forces every handler to be a global. ~35 function and 4 state variables on `window.*`. This prevents modular encapsulation, makes testing harder, and creates collision risk.
- **Fix:** Replace inline `onclick` with event delegation on a root container. Map `data-action` attributes to handler functions. Remove all `window.*` assignments.
- **Effort:** 6-10 hours (large refactor)

### B5. Code duplication across pages
- **Severity:** High
- **Files:** Transaction tables (3 copies), file upload handlers (2 copies), category learning (2 copies)
- **Issue:** Nearly identical rendering code is copy-pasted. Transaction table markup exists in `dashboard.js`, `transactions.js`, and partially in `accounts.js`. OFX/CSV import handlers are duplicated in `onboarding.js`.
- **Fix:** Extract shared components: `TransactionTable`, `FileUploader`, `CategoryLearner`.
- **Effort:** 3-5 hours

### B6. No print stylesheet
- **Severity:** High
- **File:** `web/css/style.css` (missing)
- **Issue:** No `@media print` rules. Pages will print with dark backgrounds, overlapping elements, broken layouts.
- **Fix:** Add print styles: hide sidebar, nav, buttons; show data tables in black/white.
- **Effort:** 1-2 hours

### B7. Missing `aria-live` on auth error and dynamic content
- **Severity:** High
- **Files:** `web/index.html:109` (auth error), `web/js/pages/auth.js:50-54`
- **Issue:** When auth fails, the error message appears visually but screen readers don't announce it. Same for other dynamic error messages across pages.
- **Fix:** Add `role="alert"` or `aria-live="polite"` to error divs.
- **Effort:** 1-2 hours

---

## Track C: Medium Priority

### C1. No API response caching (3 pages call /dashboard)
- **Severity:** Medium
- **Files:** `web/js/pages/dashboard.js`, `web/js/pages/transactions.js`, `web/js/pages/reports.js`
- **Issue:** `/dashboard` is called from 3 different pages with no caching. Each navigation re-fetches the full dashboard data.
- **Fix:** In-memory cache with TTL (e.g., 30s) stored in a shared module.
- **Effort:** 2-3 hours

### C2. Sequential API calls on Mileage page
- **Severity:** Medium
- **File:** `web/js/pages/mileage.js:7-16`
- **Issue:** `/mileage/trips` and `/mileage/report` are fetched sequentially (await then await) instead of parallel (`Promise.all`).
- **Fix:** Use `Promise.all([...])`.
- **Effort:** 15 min

### C3. Mobile drawer has no ARIA dialog semantics
- **Severity:** Medium
- **File:** `web/index.html:129-153`
- **Issue:** The mobile drawer is a `<div>` overlay with no `role="dialog"`, `aria-modal`, or `aria-label`. Focus is not trapped inside.
- **Fix:** Add dialog ARIA attributes and focus trapping.
- **Effort:** 1-2 hours

### C4. Missing `description` meta tag and Open Graph tags
- **Severity:** Medium
- **File:** `web/index.html` (head section)
- **Issue:** No `og:title`, `og:description`, `og:image`. When shared on social media, the link shows only the URL.
- **Fix:** Add OG meta tags with business name and description.
- **Effort:** 30 min

### C5. No keyboard focus indicator for mobile nav
- **Severity:** Medium
- **File:** `web/css/style.css`
- **Issue:** The `.mobile-nav` links don't have `:focus-visible` styles. Keyboard-only users navigating through the bottom nav get no visual cue.
- **Fix:** Add `:focus-visible` outline to mobile nav links.
- **Effort:** 15 min

### C6. `.btn:active` transform not guarded by `prefers-reduced-motion`
- **Severity:** Medium
- **File:** `web/css/style.css:343`
- **Issue:** Button press animation `transform: scale(0.97)` runs even when the user has `prefers-reduced-motion: reduce` set.
- **Fix:** Wrap in `@media (prefers-reduced-motion: no-preference) { ... }`.
- **Effort:** 15 min

### C7. Data URI PNGs in manifest.json — unconventional
- **Severity:** Medium
- **File:** `web/manifest.json`
- **Issue:** Icons 192 and 512 are base64 data URIs inside the manifest, not physical files. Most browsers handle this, but some PWA crawlers may skip them.
- **Fix:** Create physical PNG files and reference by path.
- **Effort:** 30 min

### C8. Zero-profit response shape differs from normal — API inconsistency
- **Severity:** Medium
- **File:** `app/api/taxes.py:99-100`
- **Issue:** When `ytd_net <= 0`, the API returns `{"note": "..."}` while the normal case returns a full structure with nested objects. The frontend had to add special-case handling.
- **Fix:** Return consistent shape with zero values for all fields, ensuring frontend code path is uniform.
- **Effort:** 1-2 hours

---

## Track D: Low Priority (Polish)

### D1. No `aria-current` on active nav link
- **File:** `web/js/app.js:92-93`
- **Issue:** Active sidebar link gets class `active` but no `aria-current="page"`. Screen readers don't know which page is current.
- **Fix:** Add `aria-current="page"` when setting active class.
- **Effort:** 15 min

### D2. No `autofocus` on auth modal email field (uses JS setTimeout)
- **File:** `web/js/pages/auth.js:19`
- **Issue:** Focus is moved to email field via `setTimeout(() => email.focus(), 150)`, which creates a perceptible delay. Also won't work if the modal is opened before the timeout fires.
- **Fix:** Use HTML `autofocus` attribute on the email input.
- **Effort:** 15 min

### D3. No email format validation on auth or setup forms
- **Files:** `web/js/pages/auth.js:47`, `web/js/pages/setup.js`
- **Issue:** Email fields accept any string, including invalid formats.
- **Fix:** Add regex validation for email format before submitting.
- **Effort:** 30 min

### D4. Inconsistent Enter key handling on auth form
- **File:** `web/index.html:75-84`
- **Issue:** Pressing Enter in the password field submits the form; pressing Enter in the email field does nothing.
- **Fix:** Add `onkeydown="if(event.key==='Enter') submitSignIn()"` to the email input, or wrap in `<form>` with `onSubmit`.
- **Effort:** 15 min

### D5. Shared global state (window._receiptData, window._ofxFile)
- **Files:** `web/js/pages/receipts.js`, `web/js/pages/import.js`
- **Issue:** Global variables share state across pages. If a user navigates away and back, the state is lost or stale.
- **Fix:** Module-scoped variables (not on window) or a simple state manager.
- **Effort:** 1-2 hours

### D6. No skip-to-content link
- **File:** `web/index.html` (missing)
- **Issue:** The first tabbable element is the sidebar nav. Keyboard and screen reader users must tab through 16 nav links before reaching main content.
- **Fix:** Add a "Skip to content" link as the first focusable element.
- **Effort:** 30 min

### D7. Static HTML has no h1
- **File:** `web/index.html`
- **Issue:** The initial document has no `<h1>` element. The SPA adds one dynamically, but search engines and screen readers reading the initial load see no heading.
- **Fix:** Add `<h1 class="sr-only">SoloLedger</h1>` or similar visually-hidden heading.
- **Effort:** 15 min

### D8. Mobile nav lacks aria-label
- **File:** `web/index.html:120`
- **Issue:** The mobile `<nav>` has no `aria-label`, making it indistinguishable from the sidebar `<nav aria-label="Main navigation">`.
- **Fix:** Add `aria-label="Mobile navigation"`.
- **Effort:** 5 min

### D9. Sign-out button uses emoji-only label
- **File:** `web/index.html:46`
- **Issue:** The 🚪 emoji is the only visible label. Screen readers will read "door" which isn't clear.
- **Fix:** Add `aria-label="Sign out"` or text alongside the emoji.
- **Effort:** 5 min

### D10. Confirm modal missing aria-labelledby
- **File:** `web/js/api.js:308`
- **Issue:** The modal heading is an `<h3>` but not referenced by `aria-labelledby` on the dialog container. Screen readers may not announce the title.
- **Fix:** Add `id` to the heading and `aria-labelledby` to the overlay.
- **Effort:** 15 min

---

## Recommendations

### Quick Wins (1 session)
1. Fix Enter key on auth email field (D4)
2. Add `aria-label` to mobile nav (D8)
3. Add `aria-label` to sign-out button (D9)
4. Guard button press animation for reduced-motion (C6)
5. Parallelize mileage API calls (C2)
6. Add `aria-current` to active nav link (D1)

### Sprint 1 (2-3 sessions)
1. Wrap auth form in `<form>` with proper labels (A2)
2. Add `role="alert"` to all error divs (B7)
3. Add focus trapping to modals (B1)
4. Add `apple-touch-icon` and iOS meta tags (A3)
5. Add empty states for Accounts, Import, Reports (B2)
6. Add error states with retry for 6 pages (B3)

### Sprint 2 (3-5 sessions)
1. Create service worker for PWA installability (A1)
2. Fix LLM API key storage (A4)
3. Extract shared components (B5)
4. Add API response caching (C1)

### Sprint 3 (5-8 sessions)
1. Replace inline onclick with event delegation (B4)
2. Add print stylesheet (B6)
3. Replace inline styles in JS with CSS classes

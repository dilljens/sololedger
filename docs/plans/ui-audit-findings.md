# UI Audit Findings & Improvement Plan

> Generated: 2026-07-25
> Scope: Full audit covering UX (Refactoring UI principles), WCAG 2.1 AA accessibility,
> PWA installability, performance, module architecture, LLM integration, and 5-point UX check.

---

## Scorecard Summary

| Dimension | Score | Key Gap |
|-----------|:-----:|---------|
| Visual Design (Refactoring UI) | 7/10 | Inline styles bypass design tokens |
| WCAG 2.1 AA Accessibility | 5/10 | Form labels missing `for` attr, no skip-link, no h1 in static HTML |
| PWA Installability | 6/10 | iOS meta tags missing from Vue app, SW needs update |
| Performance | 6/10 | No lazy loading, no data caching, monolithic bundles |
| Module Architecture | 3/10 | 65 global functions, 56 inline onclick handlers, raw innerHTML |
| LLM Integration | 6/10 | Key in localStorage, no client-side LLM, no natural-language queries |
| 5-Point UX Check | 5/10 | Missing empty/error states on many pages, no skeletons |

---

## Track A: Critical (1-2 sessions, high-impact fixes)

### A1. Replace 65 global `window.*` functions with event delegation
- **Severity:** Critical
- **Finding:** 65 functions assigned to `window.*` across 15 page modules. 56 inline `onclick` handlers in JS template strings. This creates collision risk, prevents modular encapsulation, and makes testing harder.
- **Fix pattern:** 
  1. Map `data-action` attributes to handler functions in each page module
  2. Use a root container event listener (event delegation)
  3. Remove all `window.X = X` assignments
- **Effort:** 6-10 hours
- **Dependency:** Blocked by JS framework migration decision (Vue addresses this natively)

### A2. Replace raw `innerHTML` with safer rendering
- **Severity:** Critical
- **Finding:** 100+ `innerHTML` assignments across all JS files. While `escapeHtml()` is used in most (but not all) places, the pattern is inherently error-prone for XSS.
- **Fix pattern:** 
  1. Use Vue templates (already started in `web/src/`)
  2. For legacy JS: extract builder functions (TableBuilder, CardBuilder, FormBuilder) that use `document.createElement` + `textContent`
- **Effort:** 4-8 hours for builder extraction; Vue migration solves permanently

### A3. Replace hardcoded hex colors in JS inline styles
- **Severity:** Critical
- **Finding:** All JS page files use hardcoded hex colors in inline `style="..."` attributes (e.g., `#c92a2a`, `#2b8a3e`, `#888`, `#666`). These don't respect dark mode.
- **Fix:** 
  1. Add CSS utility classes for common patterns: `.text-error`, `.text-success`, `.text-muted`, `.border-default`
  2. Replace inline style strings with class references in JS templates
- **Effort:** 2-4 hours
- **Files:** All page JS files (~15 files)

## Track B: High Priority (3-5 sessions)

### B1. Add form labels with `for` attributes
- **Severity:** High
- **Finding:** Only 2 `<label for="">` exist (auth form). All other forms use styled `<label>` elements or `<span>` without `for` attributes. Screen readers cannot associate labels with inputs.
- **Fix:** Add `for` attributes to all labels, matching `id` on inputs. Wrap in a `<FormField>` component pattern.
- **Effort:** 3-4 hours
- **Files:** accounts.js, import.js, invoices.js, mileage.js, receipts.js, categorize.js, settings.js

### B2. Add proper empty states to all data pages
- **Severity:** High
- **Finding:** The `.empty-state` CSS class exists but is never used. Most pages show inline muted text or nothing when data is empty. Missing: Accounts (no cards), Receipts (no docs), Mileage (no trips), Reports (no data).
- **Fix:** Apply `.empty-state` with icon + message + CTA button (following the existing CSS pattern) to every data-driven view.
- **Effort:** 2-3 hours

### B3. Add skip-to-content link and static h1
- **Severity:** High
- **Finding:** No skip-to-content link exists. The first tabbable element is the sidebar with 16 nav links. Also, no `<h1>` exists in the static HTML (all injected via JS).
- **Fix:** 
  1. Add `<a href="#main-content" class="skip-link">` as first focusable element
  2. Add `<h1 class="sr-only">SoloLedger</h1>` in the app shell HTML
- **Effort:** 30 min

### B4. Add error states with retry to all API-driven pages
- **Severity:** High
- **Finding:** Only 3 pages (reports, transactions, shared.js) use `renderErrorState` with a retry button. All other pages show inline error text or silent failures without retry options.
- **Fix:** Add consistent error handling to every page using the existing `renderErrorState` pattern from `shared.js`.
- **Effort:** 3-5 hours
- **Pages needing retry:** dashboard (no retry), accounts (no retry), import (no retry), receipts (no retry), health (no retry), settings (no retry), tax (no retry), categorize (no retry)

### B5. Fix iOS PWA meta tags in Vue app
- **Severity:** High
- **Finding:** The Vue app's `index.html` is missing: `apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style`, `mobile-web-app-capable`, `viewport-fit=cover`, `og:*` tags. These exist in the classic app but not the Vue entry point.
- **Fix:** Copy missing meta tags from `index-classic.html` to `index.html`.
- **Effort:** 15 min

### B6. Replace emoji icons with SVG sprite system
- **Severity:** High
- **Finding:** 30+ emoji characters used as icons throughout the app. Emoji render differently across platforms, don't support color theming, and have poor accessibility (screen readers read the emoji name).
- **Fix:** 
  1. Create an SVG sprite sheet with the 20 most-used icons
  2. Create an `<Icon name="dashboard" />` component for Vue
  3. For classic JS: use inline SVGs or SVG sprite with `<use>`
- **Effort:** 4-6 hours
- **Note:** Can be done incrementally — replace emoji on migrated Vue pages first

## Track C: Medium Priority (5-8 sessions)

### C1. Implement lazy-loaded module loading
- **Severity:** Medium
- **Finding:** All 17 page JS modules are loaded upfront (each as a separate `<script>` import). No code splitting or lazy loading.
- **Fix:** 
  1. In the class app: use dynamic `import('./pages/X.js')` in the router
  2. In the Vue app: component-level code splitting is already set up via `() => import(...)`
- **Effort:** 2-4 hours (classic app only)

### C2. Add API response caching for `/dashboard` data
- **Severity:** Medium
- **Finding:** `/dashboard` is called from 3 pages (dashboard, transactions, reports) with no caching. Each navigation triggers a fresh fetch.
- **Fix:** Implement in-memory cache with 30s TTL in the API client, keyed by endpoint path.
- **Effort:** 2-3 hours

### C3. Add skeleton loading states to all pages
- **Severity:** Medium
- **Finding:** Only 1 skeleton template exists (used in app.js for initial load). All page transitions show a spinner rather than a content-matching skeleton.
- **Fix:** Create skeleton variants for each page type (stat cards, tables, forms) and show them during API calls.
- **Effort:** 4-6 hours
- **Note:** Vue makes this easier with dynamic skeleton components

### C4. Fix keyboard focus indicator consistency
- **Severity:** Medium
- **Finding:** Focus indicators exist for buttons, inputs, sidebar links, and theme toggle, but not for: mobile nav links `.mobile-nav a`, mobile drawer items `.mobile-drawer-item`, toast close button, confirm dialog buttons.
- **Fix:** Add `:focus-visible` styles to all interactive elements.
- **Effort:** 1-2 hours

### C5. Add `aria-live` regions for dynamic content updates
- **Severity:** Medium
- **Finding:** Only the toast container has `aria-live="polite"`. Dynamic content changes (search results, categorizations, import results) are not announced to screen readers.
- **Fix:** Add `aria-live="polite"` to result containers that update dynamically.
- **Effort:** 2-3 hours

### C6. Increase touch targets to 44×44px on mobile
- **Severity:** Medium
- **Finding:** Bottom nav links have `min-height: 44px` ✅, but: sidebar nav links don't increase on mobile, mobile drawer items don't have explicit touch targets, form inputs are 16px font (correct for iOS zoom prevention).
- **Fix:** Add `min-height: 44px` to all mobile interactive elements.
- **Effort:** 1-2 hours

### C7. Add `autocomplete` attributes to form inputs
- **Severity:** Medium
- **Finding:** Only two auth inputs have `autocomplete`. No other forms have autocomplete hints for password managers, address autofill, etc.
- **Fix:** Add appropriate `autocomplete` attributes to all form inputs.
- **Effort:** 1 hour

### C8. Secure LLM API key storage
- **Severity:** Medium
- **Finding:** LLM API key is stored in `localStorage` in plain text. While the input uses `type="password"`, the key remains accessible to browser extensions and XSS.
- **Fix:** At minimum, don't pre-fill the input value (use placeholder). Better: session-based key management where the server holds the key.
- **Effort:** 4-6 hours (depends on approach)

## Track D: Low Priority (Polish & Enhancement)

### D1. Service worker cache update strategy
- **Severity:** Low
- **Finding:** SW serves static assets cache-first. The 17 assets in `STATIC_ASSETS` are cached on install. If a JS file changes, the user won't see the new version until the SW updates (next session).
- **Fix:** Add version hash to cache key, or use `network-first` with cache fallback for JS files during development.
- **Effort:** 2-3 hours

### D2. Print stylesheet refinement
- **Severity:** Low
- **Finding:** Print styles exist (19 lines) and hide sidebar/modals/buttons. But data tables may overflow the page width, and stat-card layout may break.
- **Fix:** Add table-specific print styles, stat-card print layout, and page-break hints.
- **Effort:** 1-2 hours

### D3. Add Open Graph tags to Vue app
- **Severity:** Low
- **Finding:** OG tags exist in classic app but not Vue entry point. Shared links show raw URL.
- **Fix:** Copy OG meta tags from classic HTML.
- **Effort:** 15 min

### D4. Add natural-language LLM query interface
- **Severity:** Low
- **Finding:** AI/LLM integration exists for categorization only (OpenAI-compatible APIs in `categorizer_llm.py`). No natural-language query capability for asking questions like "How much did I spend on hosting this month?"
- **Fix:** Add a chat/query interface widget that sends natural-language queries to the LLM and displays structured responses.
- **Effort:** 3-5 days

### D5. Add optimistic UI for common actions
- **Severity:** Low
- **Finding:** All actions wait for API confirmation before updating the UI. No optimistic updates with rollback on error.
- **Fix:** For high-frequency actions (mark as paid, log mileage, create transaction): update UI immediately, revert on API error.
- **Effort:** 3-5 days

### D6. Mobile drawer ARIA and focus refinement
- **Severity:** Low
- **Finding:** Mobile drawer has `role="dialog"`, `aria-modal="true"`, and `aria-label`. Focus trap works. But: drawer items don't have `aria-current="page"` for the active page, and close button could have better screen reader text.
- **Fix:** Add `aria-current` to active drawer link, refine close button `aria-label` to "Close navigation menu".
- **Effort:** 30 min

### D7. Reduce motion: button press animation
- **Severity:** Low
- **Finding:** `.btn:active { transform: scale(0.97) }` exists and is already wrapped in `@media (prefers-reduced-motion: no-preference)`. ✅ Fixed.
- **Effort:** ✅ Already done

### D8. Color contrast audit
- **Severity:** Low
- **Finding:** Design tokens use proper contrast ratios (~7:1 for gray-800 on gray-50). However, some badge text colors may be low contrast (e.g., `#92400e` on `#fef3c7` is ~5.2:1 — passes AA but could be improved).
- **Fix:** Audit all text/background pairs with a contrast checker, adjust if below 4.5:1.
- **Effort:** 2-3 hours

---

## Quick Wins (1 session)

1. Add skip-to-content link + static h1 → B3
2. Fix iOS PWA meta tags in Vue app → B5
3. Add `for` attributes to form labels (start with 1-2 pages) → B1 (partial)
4. Add OG tags to Vue app → D3
5. Implement dashboard API caching → C2
6. Increase mobile touch targets → C6
7. Mobile drawer ARIA refinement → D6
8. Add `autocomplete` to form inputs → C7

## Sprint 1 (2-3 sessions)
1. Replace hardcoded hex colors in JS with CSS classes → A3
2. Add error states with retry to all API pages → B4 (start with top 5 pages)
3. Add empty states using `.empty-state` class → B2
4. Add keyboard focus indicators for missing elements → C4
5. Add `aria-live` regions → C5

## Sprint 2 (3-5 sessions)
1. Replace emoji with SVG sprite system → B6
2. Add skeleton loading to all pages → C3
3. Fix LLM API key storage → C8
4. Implement API response caching → C2
5. Incremental form label fixes → B1 (remaining pages)

## Sprint 3 (5-8 sessions)
1. Replace inline handlers with event delegation → A1
2. Extract builder functions from innerHTML patterns → A2
3. Service worker cache strategy update → D1
4. Add lazy-loaded module loading → C1
5. Print stylesheet refinement → D2

## Sprint 4 (Future)
1. Natural-language LLM query interface → D4
2. Optimistic UI → D5
3. Color contrast audit → D8

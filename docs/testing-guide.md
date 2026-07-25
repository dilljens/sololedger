# SoloLedger Testing Guide

## How to Catch Errors Before Deploying

The goal is to catch the 5 categories of bugs we've been hitting:

| Bug Type | Example | How to Catch |
|----------|---------|-------------|
| **Python crash** | `datetime.now()` instead of `datetime.datetime.now()` | `pytest` + local `uvicorn --reload` |
| **JS runtime error** | Service worker caching POST requests | Local browser test + `eslint` |
| **Auth timing** | API calls before session is ready | Browser test (incognito load) |
| **API contract** | Endpoint returns wrong status code | `pytest tests/test_api.py` |
| **Missing template** | Docker image missing ledger files | `bash bin/preflight.sh` |

---

## 1. Local Dev (Fastest Feedback)

Run SoloLedger locally so changes take effect immediately:

```bash
cd /home/dillon/_code/sololedger
.venv/bin/uvicorn app.api:app --reload --host 0.0.0.0 --port 8100
```

Open http://localhost:8100/app/ in a browser.

**Test these before deploying:**
- [ ] Load the app in an incognito window (no session → should show "Sign In Required")
- [ ] Sign up with email/password
- [ ] Sign out, sign back in
- [ ] Open browser console (F12) → check for errors
- [ ] Check the Network tab for 403/401/500 responses

**What we catch:** Python crashes, missing imports, API contract issues, auth timing

---

## 2. API Contract Tests (pytest)

Run the existing test suite:

```bash
cd /home/dillon/_code/sololedger
.venv/bin/python -m pytest tests/ -v
```

These test that endpoints return the right status codes and data shapes.

**What we catch:** Broken API endpoints, wrong return types, plan gating issues

---

## 3. Preflight Script

Run before every deploy to catch common issues:

```bash
cd /home/dillon/_code/sololedger
bash bin/preflight.sh
```

This checks:
- Python syntax errors
- Service worker doesn't cache POST requests
- Static asset paths in sw.js exist
- Google sign-in guard against double init
- Template ledger files exist

**What we catch:** Syntax errors, service worker bugs, missing template files

---

## 4. Browser Console Check (Critical)

**The single most effective way to catch frontend bugs** is to open the browser console after testing. Every console error tells you exactly what file and line broke.

Before deploying any change:
1. Open an **incognito window** (clean state)
2. Open DevTools → Console tab
3. Walk through the app: sign up, navigate pages, import a file, check tax
4. **Look for red errors** (not warnings — warnings are usually harmless)
5. Check for **"Internal Server Error"** in toast messages

**What we catch:** JS runtime errors, API errors, Google sign-in issues, auth timing

---

## 5. Playwright E2E Tests (Future)

For automated browser testing, set up Playwright:

```bash
cd /home/dillon/_code/sololedger
npm init -y
npm install @playwright/test
npx playwright install chromium
```

Then create `e2e/` tests that:
1. Load the app
2. Sign up
3. Check dashboard loads
4. Check tax page loads
5. Sign out and sign back in

---

## Deploy Checklist

Before pushing to production:

```
□ 1. uvicorn --reload local — app loads without errors
□ 2. pytest tests/ -v — all pass
□ 3. bash bin/preflight.sh — all pass
□ 4. Open browser console — no red errors
□ 5. Test: sign up → dashboard → navigate 2 pages
□ 6. Test: incognito → app shows sign-in modal
□ 7. Test: sign in → session persists on refresh
□ 8. Test: the exact bug you fixed doesn't happen anymore
```

The whole checklist takes about 5 minutes once local dev is running.

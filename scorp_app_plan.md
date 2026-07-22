# Plan: Update Web App (SPA + API) with S-Corp Features

**Goal:** Expose all S-Corp features through the FastAPI routes and vanilla-JS SPA frontend.

**Files to change: 8** (3 API, 3 frontend, 1 route registration, 1 page nav)

## Track A: API Routes `[ ]`
- Description: Update REST endpoints to return S-Corp data and add new routes

### A1: Tax Estimate API — branch on entity_type `[ ]`
- **File:** `app/api/taxes.py`
- **Changes:**
  - Read `entity_type` from config
  - Branch `/tax/estimate`: for S-Corp return FICA + 1120-S income; for SMLLC return SE tax (unchanged)
  - Add `entity_type`, `form_label`, `fica`, `form_1120s` fields to the response when S-Corp
  - Schema is backward compatible — SMLLC callers get exactly the same response shape
- ✅ **Checkpoint:** `curl /api/v1/tax/estimate` returns correct data for both entity types
- 📏 Scope: ~1 file, ~30 lines changed

### A2: 1120-S API Route `[ ]`
- **File:** `app/api/taxes.py`
- **Changes:**
  - Add `GET /api/v1/tax/form-1120s` endpoint
  - Returns full 1120-S data (income, deductions, balance sheet, K-1)
  - Returns error with hint if entity_type is SMLLC
- ✅ **Checkpoint:** `curl /api/v1/tax/form-1120s` works in S-Corp mode

### A3: Payroll API Route (new file) `[ ]`
- **File:** `app/api/payroll.py` (new)
- **Changes:**
  - Add `POST /api/v1/payroll/import` — upload Gusto CSV, import to ledger
  - Add `GET /api/v1/payroll/summary` — return year-to-date payroll totals
  - Both endpoints check entity_type is "scorp" or return helpful error
- **Registration:** Import and register in `app/api/__init__.py`
- ✅ **Checkpoint:** Can import a payroll CSV via curl

### A4: Dashboard API — add entity_type `[ ]`
- **File:** `app/api/health.py`
- **Changes:**
  - `/status` and `/dashboard`: add `entity_type` and `entity_label` fields
- ✅ **Checkpoint:** Dashboard response includes entity info

## Track B: Frontend SPA `[ ]`
- Description: Update JS pages to display S-Corp data and add new page

### B1: Tax page — branch display `[ ]`
- **File:** `web/js/pages/tax.js`
- **Changes:**
  - Read `entity_type` from API response
  - If S-Corp: show "S-Corp (1120-S)" header, FICA payroll tax section, 1120-S income
  - If SMLLC: current display (SE tax) — unchanged
  - Add "📋 1120-S Data" download button (S-Corp) / "📋 Schedule C Data" (SMLLC)
- ✅ **Checkpoint:** Tax page renders correctly in both modes

### B2: Dashboard — show entity type `[ ]`
- **File:** `web/js/pages/dashboard.js`
- **Changes:**
  - Show entity type label next to "Your business at a glance" subtitle
- ✅ **Checkpoint:** Dashboard shows entity type

### B3: Payroll page (new) `[ ]`
- **File:** `web/js/pages/payroll.js` (new)
- **Changes:**
  - Upload Gusto CSV → POST to API
  - Show YTD payroll summary
  - Disburse net pay button
- **Nav:** Add link in sidebar/`app.js`
- ✅ **Checkpoint:** Payroll page loads and accepts file upload

## Track C: Nav & Routing `[ ]`
- **File:** `web/js/app.js`, `web/index.html`
- **Changes:**
  - Add "Payroll" nav link
  - Register payroll page in SPA router
- ✅ **Checkpoint:** Nav shows "Payroll" and links work

## Files Changed Summary
| File | Type | Change |
|------|------|--------|
| `app/api/taxes.py` | API | Branch tax estimate, add 1120-S route |
| `app/api/health.py` | API | Add entity_type to dashboard |
| `app/api/payroll.py` | API (new) | Payroll import + summary endpoints |
| `app/api/__init__.py` | API | Register payroll router |
| `web/js/pages/tax.js` | Frontend | S-Corp display branch |
| `web/js/pages/dashboard.js` | Frontend | Entity type label |
| `web/js/pages/payroll.js` | Frontend (new) | Payroll upload page |
| `web/js/app.js` | Frontend | Register payroll page + nav |

## Acceptance Criteria
1. All existing 91 tests still pass
2. `/api/v1/tax/estimate` returns S-Corp data when config has `entity_type = "scorp"`
3. `/api/v1/tax/estimate` returns same data as before when SMLLC
4. `/api/v1/tax/form-1120s` returns 1120-S data in S-Corp mode
5. `/api/v1/payroll/import` accepts Gusto CSV upload
6. `/api/v1/dashboard` includes `entity_type`
7. Tax page shows S-Corp breakdown when applicable
8. Dashboard shows entity type
9. "Payroll" nav link appears and works

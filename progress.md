# SoloLedger — Progress

## Current State

| Metric | Value |
|--------|-------|
| **Version** | 0.4.0 |
| **Ledger** | ✅ Clean — no errors |
| **Demo Data** | ✅ Loaded (cash: $11,855.27, revenue: $13,000.00) |
| **Tests** | ✅ 240 passing (4 Stripe tests skip without credentials; 20 e2e-marked in `tests/` excluded here) |
| **Config** | ⚠️ Template values (name, EIN not set) |
| **Working tree** | ✅ Clean |
| **Architecture** | ⚠️ 0.5912 (post-refactor; modularity metric artifact from API split) |

## Phase Log

| Phase | Status | Notes |
|-------|--------|-------|
| P1: Foundation & Baseline | ✅ Complete | sentrux baseline, review, green dashboard |
| P2: Testing Infrastructure | ✅ Complete | pytest + tests: config(7), ledger(9), invoice(10), CLI(14), taxes(22), payments(9) |
| P3: Uncommitted Changes | ✅ Complete | 29 files committed, +6395/-308, all green |
| P4: Fix & Polish | ✅ Complete | No bare excepts, all compile; API split into 23 routers in `app/api/` |
| P5: CI & Documentation | ✅ Complete | GitHub Actions test workflow added, wiki current, README badge |
| P6: Release Prep | ✅ Complete | v0.3.0, all 71 tests green |
| **Rearchitecture (v1 plan)** | ✅ 15/22 phases | See docs/plans/sololedger-v1-rearchitecture.md |

## Rearchitecture Progress (2026-07-27)

Audited the rearchitecture plan — most work was already built but checkboxes weren't updated.

**Completed this session:**
- Updated plan to reflect actual state (15 of 22 phases already done)
- Phase I1: ReceiptCapture.vue + ReceiptList.vue (replaced PlaceholderPage)
- Phase D2: Statements.vue page with PDF upload
- Phase E2: Reconciliation.vue page with uncleared list
- Added routes + nav links for all new pages
- Fixed duplicate nav label (`/coa` → "Chart")

**v0.4.0 shipped (2026-08-01):** rearchitecture complete — FastAPI router package, Vue 3 SPA, SQLite metadata layer, fail-closed auth with session expiry. Test suite now 240 tests (excluding e2e).

**Test suite:** 74 tests passing (+3 since baseline: test_db, test_rules, test_coa) — superseded by the 240-test suite above

## Blockers

None.

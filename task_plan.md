# SoloLedger — Task Plan

**Version:** 0.2.0
**Goal:** Stabilize, test, and polish the codebase for a reliable v0.3.0 release.

## Phase 1: Foundation & Baseline
- [ ] P1.1: Run `sentrux_scan` to capture current architectural health baseline
- [ ] P1.2: Review uncommitted work — examine diff on modified files, assess untracked files
- [ ] P1.3: Run `llc doctor` and `llc check` to confirm baseline is green
- [ ] P1.4: Create baseline progress.md entry

## Phase 2: Testing Infrastructure
- [ ] P2.1: Create test directory + conftest with shared fixtures (test ledger, config)
- [ ] P2.2: Test `app/config.py` — Config loading, path resolution, env overrides
- [ ] P2.3: Test `app/ledger.py` — Ledger loading, reload caching, balance queries
- [ ] P2.4: Test `app/invoice.py` — Invoice creation, AR check, retainer processing
- [ ] P2.5: Test `app/main.py` CLI commands (smoke tests for each command group)
- [ ] P2.6: Set up `pytest` in pyproject.toml, verify `python -m pytest` works

## Phase 3: Uncommitted Changes Review
- [ ] P3.1: Review diff on `app/api.py`, `app/categorizer.py`, `app/ledger.py`, `app/main.py`, `app/receipts.py`
- [ ] P3.2: Review untracked files: `categorizer_embed.py`, `categorizer_llm.py`, `mileage.py`, `ofx_import.py`, `provision.py`, `reconciliation.py`, `rules.py`
- [ ] P3.3: Stage or document each file; commit coherent batches with good messages
- [ ] P3.4: Run `llc check` + `llc doctor` after each commit to verify nothing broke

## Phase 4: Fix & Polish
- [ ] P4.1: Check for deprecation warnings / Python issues in all modules
- [ ] P4.2: Audit error handling — ensure all `except` clauses are specific, no bare `except:`
- [ ] P4.3: Audit `config.toml` — ensure template placeholders don't crash unconfigured commands
- [ ] P4.4: Run `sentrux_scan` again and compare against Phase 1 baseline

## Phase 5: CI & Documentation
- [ ] P5.1: Add `.github/workflows/test.yml` — run pytest on push/PR
- [ ] P5.2: Verify wiki docs are current (`docs/wiki/_index.md`)
- [ ] P5.3: Update README with test status, coverage badge placeholder

## Phase 6: Release Prep
- [ ] P6.1: Bump version to 0.3.0 in `pyproject.toml` and `app/main.py`
- [ ] P6.2: Final `llc doctor` + `llc check` — all green
- [ ] P6.3: Run `sentrux_session_end` — confirm no architectural degradation
- [ ] P6.4: Update progress.md with final state

## Fallbacks (if main path blocked)

### Fallback A: Dependencies unavailable
- If beancount/plaid-python can't be installed: test with mock objects, skip integration tests
- If pytest not available: use `python -m unittest` or inline assert scripts

### Fallback B: Code issues found
- If diff reveals broken code: revert problematic commits, fix forward
- If circular imports: restructure affected module(s) individually

### Fallback C: External services unavailable
- For Stripe/Plaid/Toggl tests: use mock/stub modules, document test gaps
- For OCR tests: provide sample PDF in test fixtures

## Checkpoints

Each phase ends with a checkpoint:
- **Checkpoint 1** (end of P1): `sentrux_scan` baseline captured, green dashboard
- **Checkpoint 2** (end of P2): `python -m pytest` passes, test coverage > 0%
- **Checkpoint 3** (end of P3): All working changes committed, clean `git status`
- **Checkpoint 4** (end of P4): No regressions, architecture metrics stable
- **Checkpoint 5** (end of P5): CI file present, docs current
- **Checkpoint 6** (end of P6): Version bumped, all green

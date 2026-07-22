# S-Corp Upgrade — Task Plan

**Goal:** Add S-Corp (1120-S) entity support to SoloLedger alongside the existing SMLLC/Schedule C mode.

## Pre-resolved Decisions
- No new dependencies — all S-Corp logic is pure Python
- Entity type defaults to `smllc` — existing users unaffected
- Salary and payroll fields are no-ops in SMLLC mode
- Tax engine branches on `entity_type` at the TaxEstimator level
- CLI output labels adapt based on entity_type

## Track A: Entity Model & Config `[ ]`
- Description: Config fields, Config class, setup wizard update
- 📏 Scope: ~3 files

### Phase A1: Config TOML & Config class `[ ]`
- [ ] Add `entity_type`, `reasonable_salary`, `payroll_frequency` to config.toml template
- [ ] Read new fields in `Config.__init__`
- [ ] Write tests for new config fields

### Phase A2: Setup wizard update `[ ]`
- [ ] Prompt for entity_type in `llc init`
- [ ] Save to config.toml

## Track B: Tax Engine Branching `[ ]`
- Description: Add S-Corp FICA computation alongside SE tax, branch on entity_type
- 📏 Scope: ~2 files

### Phase B1: FICA tax computation `[ ]`
- [ ] Add `fica_tax()` method to TaxEstimator (employee + employer shares)
- [ ] Add `form_1120s_taxable_income()` method
- [ ] Branch `total_projected_tax` on entity_type

### Phase B2: CLI output branching `[ ]`
- [ ] Update `llc tax estimate` to show S-Corp labels/form references
- [ ] Update `llc status` dashboard
- [ ] Update `llc doctor` diagnostic

## Track C: Tests `[ ]`
- Description: Existing tests keep passing, new tests cover S-Corp path
- 📏 Scope: ~1 file

### Phase C1: Tax engine tests `[ ]`
- [ ] Test FICA computation
- [ ] Test 1120-S taxable income
- [ ] Test branching on entity_type
- [ ] Test SMLLC path unchanged

---

## Fallbacks
- If salary not configured in S-Corp mode: warn but use $0 (calculator still works, user gets flagged)
- If payroll provider integration is out of scope: payroll fields are config-only; actual import comes in Phase 4

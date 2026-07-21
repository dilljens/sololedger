# Plan: S-Corp Upgrade for SoloLedger

**Status:** Pending (gate: >$60K net profit)  
**Created:** 2026-07-21  
**Target entity:** Single-member Wyoming LLC electing S-Corp treatment (Form 2553)

---

## Go/No-Go Decision

Wait until **total consulting + product income exceeds ~$60K net profit** in a tax year. Until then, SMLLC/Schedule C is cheaper and simpler — S-Corp compliance (payroll, 941 quarterly filings, W-2, unemployment tax) costs more in time and money than the SE tax savings.

---

## Phase 1 — Entity Model & Config

**Effort: 3-5 days**

- [ ] Add `entity_type` field to `config.toml` (`smllc` | `scorp`)
- [ ] Add `reasonable_salary` (annual $ amount) to config
- [ ] Add `payroll_frequency` (monthly | biweekly | semimonthly) to config
- [ ] Branch all tax calculations on `entity_type` in `app/taxes/`
- [ ] Branch CLI output ("Schedule C" vs "1120-S") in `app/main.py`

## Phase 2 — Chart of Accounts

**Effort: 2-3 days**

Add these Beancount accounts to the standard template:

**New equity accounts:**
- `Equity:RetainedEarnings` — accumulated prior-year earnings
- `Equity:ShareholderDistributions` — non-payroll distributions

**New payroll liability accounts:**
- `Liabilities:PayrollPayable` — wages owed but not yet disbursed
- `Liabilities:PayrollTaxesPayable:SocialSecurity` — employee + employer share
- `Liabilities:PayrollTaxesPayable:Medicare`
- `Liabilities:PayrollTaxesPayable:FederalWithholding`
- `Liabilities:PayrollTaxesPayable:StateWithholding`
- `Liabilities:PayrollTaxesPayable:FUTA`
- `Liabilities:PayrollTaxesPayable:SUTA`

**New payroll expense accounts:**
- `Expenses:Payroll:GrossWages` — officer salary
- `Expenses:Payroll:EmployerSocialSecurity` — 6.2% employer share
- `Expenses:Payroll:EmployerMedicare` — 1.45% employer share
- `Expenses:Payroll:FUTA` — 0.6% on first $7K
- `Expenses:Payroll:SUTA` — state rate (varies, ~0-4%)

## Phase 3 — Tax Engine (S-Corp Path)

**Effort: 3-5 days**

- [ ] Replace self-employment tax (Schedule SE) with FICA computation:
  - Employee side: 6.2% SS + 1.45% Medicare on salary (withheld from gross)
  - Employer side: 6.2% SS + 1.45% Medicare on salary (company expense)
  - Additional Medicare: 0.9% on employee side above $200K
- [ ] Compute 1120-S taxable income: total revenue − salary − employer payroll taxes − business expenses
- [ ] Pass-through allocation to single shareholder (K-1 line 1): 100% of ordinary income
- [ ] Keep existing Schedule C path for SMLLC mode

## Phase 4 — Payroll Integration

**Effort: 1-2 weeks**

**Design decision:** Do NOT build in-house payroll. Integrate with a provider.

**Recommended: Gusto ($40/mo for single employee)**
- Handles: W-2, 941 quarterly filing, federal/state withholdings, Direct Deposit
- Provides: payroll journal entries (import into SoloLedger)
- API: Gusto has a REST API for pulling paystub data

**SoloLedger work:**
- [ ] Add `payroll_provider` config field
- [ ] Add `llc payroll import` command — parse Gusto CSV/API output → ledger entries
- [ ] Auto-create payroll journal entries per pay period:
  - Debit `Expenses:Payroll:GrossWages`
  - Debit `Expenses:Payroll:EmployerSocialSecurity`
  - Debit `Expenses:Payroll:EmployerMedicare`
  - Credit `Liabilities:PayrollPayable` (net pay to owner)
  - Credit `Liabilities:PayrollTaxesPayable:*` (withholdings)
- [ ] Auto-record tax payments when Gusto pays them:
  - Debit `Liabilities:PayrollTaxesPayable:*`
  - Credit `Assets:Bank:BusinessChecking`
- [ ] Record distribution transfers (salary remainder as distribution)

## Phase 5 — 1120-S Data Export

**Effort: 3-5 days**

- [ ] New `llc tax form-1120s` command → output JSON/CSV with:
  - Gross receipts (total Income:*)
  - Officer compensation (Expenses:Payroll:GrossWages)
  - Payroll taxes (Expenses:Payroll:Employer*)
  - All other business expenses
  - Net ordinary income (or loss)
- [ ] K-1 data: single shareholder, 100% allocation
  - Ordinary business income/(loss)
  - Net rental real estate
  - Section 179 deduction
  - Distributions
- [ ] Balance sheet: Assets, Liabilities, Shareholder Equity

## Phase 6 — State Tax Updates

**Effort: 2-3 days**

- [ ] Update `app/taxes/data/state_rates.json` with entity-type branching
- [ ] Add S-Corp specific taxes per state:
  - **CA**: 1.5% S-Corp tax on net income + $800 minimum franchise tax
  - **NY**: S-Corp filing fee ($25-$4,500 based on income)
  - **WY**: No change ($0 income tax, $62 annual report)
  - **TX**: No S-Corp effect ($0 franchise tax under $2.47M)
- [ ] State calculator: branch on `entity_type`

## Phase 7 — Documentation & Migration

**Effort: 1-2 days**

- [ ] Update `llc setup` wizard with entity_type prompt
- [ ] Add migration section in README for existing SMLLC → S-Corp
- [ ] Document chart-of-accounts differences
- [ ] Add "S-Corp considerations" to tax estimation output
- [ ] Update wiki glossary with S-Corp terms (1120-S, K-1, AAA, reasonable salary)

---

## What's NOT Being Built

| Feature | Why Not | Alternative |
|---------|---------|-------------|
| In-house payroll processing | High complexity, legal liability | Gusto ($40/mo) |
| Form 941 preparation | Provider handles it | Gusto auto-files |
| W-2 generation | Provider handles it | Gusto auto-generates |
| Multi-shareholder K-1s | Solo operator only | Not needed |
| Schedule K-2/K-3 | International threshold unlikely | CPA if needed |
| Shareholder basis tracking | Track manually in spreadsheet | Simple for single-owner |

---

## Effort Summary

| Phase | Effort | Can be parallel? |
|-------|--------|-----------------|
| P1: Entity model | 3-5 days | No (foundation) |
| P2: Chart of accounts | 2-3 days | Yes (with P3) |
| P3: Tax engine | 3-5 days | Yes (with P2) |
| P4: Payroll integration | 1-2 wks | Partial (after P1+P2) |
| P5: 1120-S export | 3-5 days | Yes (after P1) |
| P6: State tax | 2-3 days | Yes (with P3) |
| P7: Documentation | 1-2 days | Yes (anytime) |
| **Total** | **~3-4 weeks** | |

---

## When To Execute

1. **Now** (no revenue): Keep SMLLC mode. SoloLedger works as-is.
2. **Revenue starts:** Use SMLLC mode, focus on making money.
3. **>$60K profit:** File Form 2553 with IRS (deadline: 2 months 15 days into tax year, or use late-election relief). Execute Phase 1-7 over ~1 month.

> **One-person rule:** As the sole owner-employee, you must pay yourself a "reasonable salary" via W-2. Everything above that is a distribution (not subject to payroll tax but still flows through on K-1). The IRS watches this — setting salary too low is a red flag.

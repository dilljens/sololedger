# Taxes

Federal and state tax estimation for single-member LLCs. Includes deadline alerts, quarterly estimates, Schedule C prep, and payment integration.

## Key Functions

- `app.taxes.TaxEstimator` — federal + state estimation engine
- `app.taxes.TaxEstimator.quarterly_estimate` — 1040-ES quarterly calculations (8 callers)
- `app.taxes.TaxEstimator.deadline_info` — filing deadline alerts (8 callers)
- `app.taxes.TaxEstimator.net_income` — P&L-driven projections
- `app.taxes.state_calculator` — state-specific tax logic
- `app.reports` — expense reports for Schedule C deduction

## Supported States

| State | Income Tax | Franchise Tax |
|-------|-----------|--------------|
| WY | $0 | $0 |
| CA | 1-13.3% | $800 + graduated |
| TX | $0 | 0.75% >$2.47M |
| NY | 4-10.9% | $0 |
| FL | $0 | $0 |

## Key Files

- `app/taxes/state_calculator.py` — state-specific tax logic
- `app/taxes/__init__.py` — tax module (13 callers, busiest domain)
- `app/taxes/data/state_rates.json` — state rate tables
- `app/notify` — tax deadline email/SMS alerts

# Taxes

Federal and state tax estimation for single-member LLCs.

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
- `app/taxes/__init__.py` — tax module
